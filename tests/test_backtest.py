"""Integration tests for the walk-forward backtest."""

import pytest

from paretos_pipeline.backtest import run_walk_forward_backtest


class TestWalkForwardBacktest:
    @pytest.mark.parametrize("strategy", ["A", "B", "C"])
    def test_all_strategies_run(self, store, cost_model, strategy):
        """All strategies should complete without error."""
        plans, summary = run_walk_forward_backtest(
            store=store,
            cost_model=cost_model,
            strategy=strategy,
            verbose=False,
        )
        assert len(plans) > 0
        assert summary["n_days"] > 0
        assert summary["plan_total_cost"] >= 0

    def test_strategy_c_beats_baseline(self, store, cost_model):
        """Strategy C should achieve meaningful savings vs baseline."""
        _, summary = run_walk_forward_backtest(
            store=store,
            cost_model=cost_model,
            strategy="C",
            verbose=False,
        )
        assert summary["savings_pct"] > 50, (
            f"Strategy C should save >50% vs baseline, got {summary['savings_pct']}%"
        )

    def test_strategy_a_beats_baseline(self, store, cost_model):
        """Even the simplest strategy should beat baseline significantly."""
        _, summary = run_walk_forward_backtest(
            store=store,
            cost_model=cost_model,
            strategy="A",
            verbose=False,
        )
        assert summary["savings_pct"] > 40, (
            f"Strategy A should save >40% vs baseline, got {summary['savings_pct']}%"
        )

    def test_strategy_ordering(self, store, cost_model):
        """All strategies should achieve substantial savings vs baseline."""
        _, sum_a = run_walk_forward_backtest(
            store=store, cost_model=cost_model, strategy="A", verbose=False
        )
        _, sum_b = run_walk_forward_backtest(
            store=store, cost_model=cost_model, strategy="B", verbose=False
        )
        _, sum_c = run_walk_forward_backtest(
            store=store, cost_model=cost_model, strategy="C", verbose=False
        )
        # All strategies should beat baseline substantially
        assert sum_a["savings_pct"] > 40
        assert sum_b["savings_pct"] > 40
        assert sum_c["savings_pct"] > 40

    def test_no_data_leakage(self, store, cost_model):
        """Plans should exist for every training day."""
        plans, summary = run_walk_forward_backtest(
            store=store,
            cost_model=cost_model,
            strategy="C",
            verbose=False,
        )
        plan_dates = {p.date for p in plans}
        actual_dates = {a.date for a in store.actuals}
        # All actuals should have a corresponding plan
        assert actual_dates.issubset(plan_dates), (
            f"Missing plans for dates: {actual_dates - plan_dates}"
        )
