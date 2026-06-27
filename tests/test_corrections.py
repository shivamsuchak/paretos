"""Tests for statistical corrections (bias, DoW, regime, combined)."""

from datetime import date

import pytest

from paretos_stats.bias_correction import compute_bias_factor, apply_bias_correction
from paretos_stats.dow_adjustment import compute_dow_factors, apply_dow_correction
from paretos_stats.corrections import CorrectionEngine
from paretos_core.schemas import CorrectionParams


class TestBiasCorrection:
    def test_factor_on_real_data(self, store):
        factor = compute_bias_factor(store.recommendations, store.actuals)
        # Analysis showed ~0.837 (−16.3%)
        assert 0.75 < factor < 0.95, f"Expected bias factor around 0.837, got {factor}"

    def test_apply_correction(self):
        corrected = apply_bias_correction(65.0, 0.837)
        assert corrected == pytest.approx(54.405)

    def test_factor_no_data(self):
        factor = compute_bias_factor([], [])
        assert factor == 1.0


class TestDoWCorrection:
    def test_wednesday_dip(self, store):
        factors = compute_dow_factors(store.recommendations, store.actuals)
        # All DoW factors should be below 1.0 (correcting overstaffing)
        assert factors["Wed"] < 1.0, "Wednesday factor should be below 1.0"
        # Factors should vary across days (not all identical)
        vals = [factors[d] for d in ["Mon", "Tue", "Wed", "Thu", "Fri"]]
        assert max(vals) - min(vals) > 0.001, "DoW factors should show variation"

    def test_all_days_present(self, store):
        factors = compute_dow_factors(store.recommendations, store.actuals)
        for dow in ["Mon", "Tue", "Wed", "Thu", "Fri"]:
            assert dow in factors

    def test_apply_correction(self):
        corrected = apply_dow_correction(65.0, date(2026, 5, 20), {"Wed": 0.80})
        assert corrected == pytest.approx(52.0)  # 2026-05-20 is a Wednesday


class TestCorrectionEngine:
    def test_calibration(self, store):
        engine = CorrectionEngine.from_training_data(
            store.recommendations,
            store.actuals,
        )
        assert 0.75 < engine.params.bias_factor < 0.95

    def test_correction_reduces_overstaffing(self, store):
        engine = CorrectionEngine.from_training_data(
            store.recommendations,
            store.actuals,
        )
        rec = store.recommendations[0]
        plan = engine.correct_day(rec)
        # Corrected should be less than original (since we over-recommend)
        assert plan.planned_operative_person_days < rec.total_operative_person_days

    def test_correction_with_regime(self, store):
        engine = CorrectionEngine.from_training_data(
            store.recommendations,
            store.actuals,
            picking_regime_start=date(2026, 8, 24),
            picking_regime_factor=0.73,
        )
        # Find a post-regime day with picking
        post_regime_recs = [
            r for r in store.recommendations
            if r.date >= date(2026, 8, 24) and "Picking" in r.by_activity
        ]
        if post_regime_recs:
            rec = post_regime_recs[0]
            plan_with = engine.correct_day(rec)

            # Compare to correction without regime
            engine_no_regime = CorrectionEngine.from_training_data(
                store.recommendations,
                store.actuals,
            )
            plan_without = engine_no_regime.correct_day(rec)

            # With regime correction should plan lower (picking needs reduced)
            assert plan_with.planned_operative_person_days < plan_without.planned_operative_person_days

    def test_newsvendor_offset(self, store):
        engine_zero = CorrectionEngine.from_training_data(
            store.recommendations, store.actuals, newsvendor_offset=0.0
        )
        engine_neg = CorrectionEngine.from_training_data(
            store.recommendations, store.actuals, newsvendor_offset=-1.0
        )
        rec = store.recommendations[0]
        plan_zero = engine_zero.correct_day(rec)
        plan_neg = engine_neg.correct_day(rec)
        assert plan_neg.planned_operative_person_days < plan_zero.planned_operative_person_days

    def test_plan_nonnegative(self, store):
        engine = CorrectionEngine.from_training_data(
            store.recommendations,
            store.actuals,
            newsvendor_offset=-1000.0,
        )
        rec = store.recommendations[0]
        plan = engine.correct_day(rec)
        assert plan.planned_operative_person_days >= 0
