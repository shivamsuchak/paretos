"""Tests for the asymmetric cost model."""

from datetime import date

import pytest

from paretos_core.cost_model import CostModel
from paretos_core.schemas import DailyActual, StaffingPlan


@pytest.fixture
def cm() -> CostModel:
    return CostModel(
        overstaffing_cost=230.0,
        overtime_premium_pct=18.0,
        sla_tolerance_pd=2.0,
        sla_penalty_per_pd=600.0,
        regular_cost_per_pd=230.0,
    )


class TestComputeDailyCost:
    def test_perfect_plan(self, cm: CostModel):
        """planned == actual → zero cost."""
        assert cm.compute_daily_cost(50.0, 50.0) == 0.0

    def test_overstaffing_simple(self, cm: CostModel):
        """5 surplus person-days → 5 × €230 = €1,150."""
        assert cm.compute_daily_cost(55.0, 50.0) == pytest.approx(1150.0)

    def test_overstaffing_1pd(self, cm: CostModel):
        """1 surplus → €230."""
        assert cm.compute_daily_cost(51.0, 50.0) == pytest.approx(230.0)

    def test_understaffing_within_tolerance(self, cm: CostModel):
        """1 pd shortfall (within 2.0 tolerance) → 1 × €41.40."""
        assert cm.compute_daily_cost(49.0, 50.0) == pytest.approx(41.4)

    def test_understaffing_at_tolerance(self, cm: CostModel):
        """2.0 pd shortfall (exactly at tolerance) → 2 × €41.40 = €82.80."""
        assert cm.compute_daily_cost(48.0, 50.0) == pytest.approx(82.8)

    def test_understaffing_beyond_tolerance(self, cm: CostModel):
        """3 pd shortfall: 2×€41.40 + 1×€600 = €682.80."""
        cost = cm.compute_daily_cost(47.0, 50.0)
        expected = 2 * 41.4 + 1 * 600.0
        assert cost == pytest.approx(expected)

    def test_understaffing_well_beyond(self, cm: CostModel):
        """5 pd shortfall: 2×€41.40 + 3×€600 = €1,882.80."""
        cost = cm.compute_daily_cost(45.0, 50.0)
        expected = 2 * 41.4 + 3 * 600.0
        assert cost == pytest.approx(expected)

    def test_asymmetry(self, cm: CostModel):
        """Overstaffing by 1 is more expensive than understaffing by 1."""
        over_cost = cm.compute_daily_cost(51.0, 50.0)
        under_cost = cm.compute_daily_cost(49.0, 50.0)
        assert over_cost > under_cost
        assert over_cost == pytest.approx(230.0)
        assert under_cost == pytest.approx(41.4)

    def test_sla_penalty_explosion(self, cm: CostModel):
        """Beyond SLA tolerance, cost explodes. 2.1 pd shortfall costs more than 2.0."""
        cost_at_tol = cm.compute_daily_cost(48.0, 50.0)
        cost_beyond = cm.compute_daily_cost(47.9, 50.0)
        assert cost_beyond > cost_at_tol

    def test_negative_inputs_raise(self, cm: CostModel):
        """Negative person-days should raise."""
        with pytest.raises(Exception):
            cm.compute_daily_cost(-1.0, 50.0)
        with pytest.raises(Exception):
            cm.compute_daily_cost(50.0, -1.0)

    def test_zero_actual(self, cm: CostModel):
        """Planned > 0 but actual = 0 → all overstaffed."""
        cost = cm.compute_daily_cost(10.0, 0.0)
        assert cost == pytest.approx(2300.0)


class TestEvaluateDay:
    def test_evaluate_overstaffed(self, cm: CostModel):
        plan = StaffingPlan(date=date(2026, 5, 18), planned_operative_person_days=60.0)
        actual = DailyActual(
            date=date(2026, 5, 18),
            present_total_person_days=64.25,
            present_operative_person_days=56.25,
        )
        result = cm.evaluate_day(plan, actual)
        assert result.overstaffed is True
        assert result.error == pytest.approx(3.75)
        assert result.cost == pytest.approx(3.75 * 230.0)

    def test_date_mismatch_raises(self, cm: CostModel):
        plan = StaffingPlan(date=date(2026, 5, 18), planned_operative_person_days=60.0)
        actual = DailyActual(
            date=date(2026, 5, 19),
            present_total_person_days=62.0,
            present_operative_person_days=54.0,
        )
        with pytest.raises(Exception):
            cm.evaluate_day(plan, actual)


class TestFromJson:
    def test_load_real_file(self, cost_model: CostModel):
        """Load from the actual dataset file."""
        assert cost_model.overstaffing_cost == 230.0
        assert cost_model.overtime_cost_per_pd == pytest.approx(41.4)
        assert cost_model.sla_tolerance_pd == 2.0
        assert cost_model.sla_penalty_per_pd == 600.0
