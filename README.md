# Paretos — Warehouse Staffing Database

## SQLite Database (`paretos.db`)

All raw and clean CSV/JSON data has been consolidated into a single normalized SQLite
database for easy querying. Build it from source with `python build_database.py`.

### Schema

```
┌─────────────────────┐       ┌──────────────────────────────┐
│ activities          │       │ recommendations              │
├─────────────────────┤       ├──────────────────────────────┤
│ id            (PK)  │◄──────│ activity_id        (FK)      │
│ name          (UQ)  │       │ id                 (PK)      │
│ activity_group      │       │ decision_date                │
│   ('operative'|     │       │ planned_week_start           │
│    'admin')         │       │ date                         │
└─────────────────────┘       │ recommended_person_days      │
                              │ UQ(decision_date, date,      │
                              │    activity_id)              │
                              └──────────────────────────────┘

┌──────────────────────────────────┐  ┌──────────────────────────────────┐
│ daily_actuals                    │  │ daily_volumes                    │
├──────────────────────────────────┤  ├──────────────────────────────────┤
│ id                    (PK)      │  │ id                    (PK)      │
│ date                  (UQ, IDX) │  │ date                  (UQ, IDX) │
│ week_start                      │  │ week_start                      │
│ present_total_person_days       │  │ picks_forecast                  │
│ present_operative_person_days   │  │ picks_realized                  │
└──────────────────────────────────┘  │ outbound_forecast               │
                                      │ outbound_realized               │
                                      │ inbound_forecast                │
                                      │ inbound_realized                │
                                      └──────────────────────────────────┘

┌──────────────────────────────────┐
│ cost_model  (single row, id=1)  │
├──────────────────────────────────┤
│ currency                        │
│ regular_cost_per_person_day     │
│ overstaffing_idle_cost          │
│ understaffing_overtime_pct      │
│ understaffing_sla_tolerance_pd  │
│ understaffing_sla_penalty       │
│ scoring_note                    │
└──────────────────────────────────┘

┌─────────────────────────┐       ┌──────────────────────────────┐
│ decision_log_authors    │       │ decision_log                 │
├─────────────────────────┤       ├──────────────────────────────┤
│ id              (PK)    │◄──────│ author_id          (FK)      │
│ name            (UQ)    │       │ id                 (PK)      │
│ role                    │       │ entry_id           (UQ)      │
└─────────────────────────┘       │ captured_on        (IDX)     │
                                  │ scope                        │
                                  │ note                         │
                                  │ claimed_effect     (JSON)    │
                                  └──────────────────────────────┘
```

### Table Details

| Table | Rows | Description |
|---|---|---|
| `activities` | 19 | Lookup: 15 operative + 4 admin activity names |
| `daily_actuals` | 98 | Actual staffing per day (total & operative person-days) |
| `daily_volumes` | 98 | Forecast vs realized picks / outbound / inbound |
| `recommendations` | 1,862 | Per-activity per-day staffing plans (19 activities × 98 days) |
| `cost_model` | 1 | Scoring parameters (€230 overstaffing, €41.40 + €600 SLA understaffing) |
| `decision_log_authors` | 3 | Planner lookup (Maya, Jonas, Selin) |
| `decision_log` | 15 | Planner notes with claimed effects stored as JSON |

**Date range:** 2026-05-18 → 2026-10-02 &nbsp;|&nbsp; **Indexes:** on `date`, `decision_date`, `captured_on`

### Example Queries

```sql
-- Daily recommended operative total vs actual
SELECT r.date,
       SUM(r.recommended_person_days) AS planned_operative,
       a.present_operative_person_days AS actual_operative
FROM recommendations r
JOIN activities act ON r.activity_id = act.id
JOIN daily_actuals a ON r.date = a.date
WHERE act.activity_group = 'operative'
GROUP BY r.date;

-- Forecast accuracy for picks
SELECT date,
       picks_forecast,
       picks_realized,
       ROUND(100.0 * (picks_realized - picks_forecast) / picks_forecast, 1) AS pct_error
FROM daily_volumes;
```


