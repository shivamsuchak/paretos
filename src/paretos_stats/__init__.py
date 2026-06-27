"""Statistical engine: bias correction, DoW adjustment, regime detection, newsvendor."""

from paretos_stats.bias_correction import compute_bias_factor, apply_bias_correction
from paretos_stats.dow_adjustment import compute_dow_factors, apply_dow_correction
from paretos_stats.corrections import CorrectionEngine

__all__ = [
    "compute_bias_factor",
    "apply_bias_correction",
    "compute_dow_factors",
    "apply_dow_correction",
    "CorrectionEngine",
]
