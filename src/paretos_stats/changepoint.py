"""Changepoint detection for regime shifts in staffing KPIs.

Uses the `ruptures` library to detect structural changes in the error ratio
(recommended / actual), which indicates events like pick-by-light deployment.
"""

from __future__ import annotations

from datetime import date
from typing import Sequence

import numpy as np

from paretos_core.schemas import DailyActual, DailyRecommendationTotal


def compute_error_ratios(
    recommendations: Sequence[DailyRecommendationTotal],
    actuals: Sequence[DailyActual],
) -> tuple[list[date], list[float]]:
    """Compute daily error ratios (rec / actual) for matched dates.

    Returns:
        Tuple of (dates, ratios) sorted by date.
    """
    actuals_by_date = {a.date: a.present_operative_person_days for a in actuals}

    pairs = []
    for rec in recommendations:
        if rec.date in actuals_by_date and actuals_by_date[rec.date] > 0:
            ratio = rec.total_operative_person_days / actuals_by_date[rec.date]
            pairs.append((rec.date, ratio))

    pairs.sort(key=lambda x: x[0])
    dates = [p[0] for p in pairs]
    ratios = [p[1] for p in pairs]
    return dates, ratios


def detect_changepoints(
    dates: list[date],
    values: list[float],
    n_bkps: int = 1,
    model: str = "l2",
    min_size: int = 5,
) -> list[dict]:
    """Detect changepoints in a time series using ruptures.

    Args:
        dates: Ordered dates corresponding to values.
        values: Time series values (e.g., error ratios).
        n_bkps: Expected number of breakpoints.
        model: Cost model for ruptures ('l2', 'l1', 'rbf').
        min_size: Minimum segment length.

    Returns:
        List of changepoint dicts with date, index, and segment means.
    """
    try:
        import ruptures as rpt
    except ImportError:
        raise ImportError("ruptures is required for changepoint detection: pip install ruptures")

    signal = np.array(values).reshape(-1, 1)
    algo = rpt.Pelt(model=model, min_size=min_size).fit(signal)
    result = algo.predict(pen=10)

    # ruptures returns breakpoint indices (exclusive end of segment)
    changepoints = []
    prev_idx = 0
    for bkp_idx in result:
        if bkp_idx < len(values):
            seg_before = values[prev_idx:bkp_idx]
            seg_after = values[bkp_idx:] if bkp_idx < len(values) else []
            changepoints.append({
                "index": bkp_idx,
                "date": dates[bkp_idx] if bkp_idx < len(dates) else dates[-1],
                "mean_before": float(np.mean(seg_before)) if seg_before else None,
                "mean_after": float(np.mean(seg_after)) if seg_after else None,
                "shift": (
                    float(np.mean(seg_after) - np.mean(seg_before))
                    if seg_before and seg_after
                    else None
                ),
            })
            prev_idx = bkp_idx

    return changepoints


def cusum_detect(
    values: list[float],
    threshold: float = 4.0,
    drift: float = 0.5,
) -> int | None:
    """Cumulative Sum (CUSUM) change detection.

    Detects upward mean shift in a time series. Returns the index of the
    first alarm, or None if no shift detected.

    Args:
        values: Time series values.
        threshold: Decision threshold (h) — higher = fewer false alarms.
        drift: Allowance parameter (k) — half the expected shift magnitude.

    Reference: Page (1954); used alongside Bayesian detection per Adams & MacKay (2007).
    """
    mu = float(np.mean(values))
    sigma = float(np.std(values)) if np.std(values) > 0 else 1.0
    s_pos = 0.0
    for i, v in enumerate(values):
        z = (v - mu) / sigma
        s_pos = max(0.0, s_pos + z - drift)
        if s_pos > threshold:
            return i
    return None


def detect_picking_regime_change(
    recommendations: Sequence[DailyRecommendationTotal],
    actuals: Sequence[DailyActual],
) -> dict | None:
    """Detect structural regime changes using both PELT and CUSUM.

    Uses ruptures (PELT) as the primary detector and CUSUM as a
    complementary method. A shift is reported if EITHER method detects it,
    with higher confidence when both agree.

    Returns:
        Dict with changepoint details, or None if not detected.
    """
    dates, ratios = compute_error_ratios(recommendations, actuals)
    if len(dates) < 15:
        return None

    # ── Primary: PELT changepoint detection ──
    pelt_result = None
    changepoints = detect_changepoints(dates, ratios, n_bkps=1)
    for cp in changepoints:
        if cp["shift"] is not None and cp["shift"] > 0.05:
            pelt_result = cp
            break

    # ── Complementary: CUSUM detection ──
    cusum_idx = cusum_detect(ratios, threshold=4.0, drift=0.5)
    cusum_date = dates[cusum_idx] if cusum_idx is not None else None

    # ── Combine results ──
    if pelt_result:
        both_agree = (
            cusum_date is not None
            and abs((cusum_date - pelt_result["date"]).days) <= 10
        )
        return {
            "detected": True,
            "date": pelt_result["date"],
            "shift_magnitude": pelt_result["shift"],
            "mean_ratio_before": pelt_result["mean_before"],
            "mean_ratio_after": pelt_result["mean_after"],
            "detection_method": "pelt+cusum" if both_agree else "pelt",
            "cusum_date": str(cusum_date) if cusum_date else None,
            "confidence": "high" if both_agree else "medium",
            "interpretation": (
                f"Error ratio shifted +{pelt_result['shift']:.3f} around {pelt_result['date']}. "
                f"Optimiser over-recommends more after this date, consistent with "
                f"a productivity improvement (e.g., pick-by-light)."
                + (f" CUSUM independently confirmed shift at {cusum_date}." if both_agree else "")
            ),
        }
    elif cusum_idx is not None:
        # CUSUM detected but PELT didn't — lower confidence signal
        before = ratios[:cusum_idx]
        after = ratios[cusum_idx:]
        shift = float(np.mean(after) - np.mean(before)) if before and after else 0
        if shift > 0.03:  # Lower threshold for CUSUM-only
            return {
                "detected": True,
                "date": cusum_date,
                "shift_magnitude": round(shift, 4),
                "mean_ratio_before": round(float(np.mean(before)), 4) if before else None,
                "mean_ratio_after": round(float(np.mean(after)), 4) if after else None,
                "detection_method": "cusum",
                "cusum_date": str(cusum_date),
                "confidence": "low",
                "interpretation": (
                    f"CUSUM detected potential shift +{shift:.3f} at {cusum_date}. "
                    f"PELT did not confirm — treat with caution."
                ),
            }

    return None
