"""Tests for data loading and aggregation."""

from datetime import date

import pytest


class TestLoadActuals:
    def test_loads_all_records(self, store):
        assert len(store.actuals) > 0

    def test_fields_populated(self, store):
        a = store.actuals[0]
        assert isinstance(a.date, date)
        assert a.present_operative_person_days >= 0
        assert a.present_total_person_days >= a.present_operative_person_days

    def test_no_nulls(self, store):
        for a in store.actuals:
            assert a.present_operative_person_days is not None


class TestLoadRecommendations:
    def test_loads_all_records(self, store):
        assert len(store.recommendations_raw) > 0

    def test_aggregation(self, store):
        recs = store.recommendations
        assert len(recs) > 0
        for r in recs:
            assert r.total_operative_person_days > 0
            assert len(r.by_activity) > 0

    def test_picking_activity_exists(self, store):
        has_picking = any("Picking" in r.by_activity for r in store.recommendations)
        assert has_picking, "Should have Picking activity in recommendations"


class TestLoadVolumes:
    def test_loads_all_records(self, store):
        assert len(store.volumes) > 0

    def test_forecast_vs_realized(self, store):
        v = store.volumes[0]
        assert v.picks_forecast > 0
        assert v.picks_realized > 0


class TestLoadDecisionLog:
    def test_loads_entries(self, store):
        assert len(store.decision_log) > 0

    def test_entry_fields(self, store):
        entry = store.decision_log[0]
        assert entry.id
        assert entry.note
        assert entry.author


class TestWeeklyCycles:
    def test_builds_cycles(self, store):
        cycles = store.weekly_cycles
        assert len(cycles) > 0

    def test_training_holdout_split(self, store):
        training = store.training_weeks()
        holdout = store.holdout_weeks()
        assert len(training) > 0
        assert len(training) + len(holdout) == len(store.weekly_cycles)

    def test_training_has_actuals(self, store):
        for w in store.training_weeks():
            assert w.actuals is not None
            assert len(w.actuals) > 0

    def test_holdout_no_actuals(self, store):
        for w in store.holdout_weeks():
            assert w.actuals is None or len(w.actuals) == 0
