# paretos

**Compounding Decision Intelligence for Warehouse Staffing Optimisation**

A multi-agent AI system that learns from weekly staffing decisions at a warehouse distribution centre. Each week the system ingests an optimiser's staffing recommendation, applies statistical corrections calibrated on historical performance, runs adversarial risk analysis, and produces a cost-optimised staffing plan — getting smarter every cycle.

Built for the [paretos "Compounding Decisions" hackathon](https://www.paretos.com/).

---

## Features

- **8-agent LangGraph pipeline** — Forecast, Knowledge Curation, Regime Detection, Planning, Cost Optimisation, Red Team, Human Review, and Debrief agents collaborate in a directed graph
- **Statistical correction stack** — bias correction, day-of-week factors, regime detection (pick-by-light), newsvendor optimisation
- **Real-time dashboard** — WebSocket-powered browser UI showing agent thinking, KPI tiles, risk scenarios, and marketplace atoms (follows the paretos design system)
- **Walk-forward backtesting** — simulates 20 weekly decision cycles with strict no-future-data-leakage
- **Micro-Shift Marketplace** — decomposes staffing plans into 2-hour claimable work atoms with dynamic pricing and German labour law (ArbZG) compliance
- **Asymmetric cost model** — overstaffing (€230/pd idle) vs understaffing (€41.40/pd overtime + €600 SLA penalty beyond 2.0 pd tolerance)
- **Knowledge curation** — Claude validates planner notes against data evidence, scores confidence, and retires stale beliefs
- **CLI** — backtest, holdout predictions, baseline costs, changepoint detection, dataset info

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.11+ |
| Agent framework | LangGraph |
| LLM | Anthropic Claude (via `anthropic` SDK) |
| Data validation | Pydantic v2 |
| Statistics | pandas, NumPy, SciPy, ruptures (changepoint detection) |
| Database | SQLite (build from CSV), DuckDB (optional) |
| Dashboard | Vanilla HTML/CSS/JS, WebSockets |
| Marketplace API | FastAPI + Uvicorn |
| Testing | pytest, Hypothesis |
| Linting | Ruff, mypy |

---

## Project Structure

```
paretos/
├── src/
│   ├── paretos_core/          # Config, schemas, cost model, data loading, exceptions
│   ├── paretos_stats/         # Bias correction, DoW adjustment, changepoint, corrections
│   ├── paretos_eval/          # Cost scoring and performance evaluation
│   ├── paretos_pipeline/      # Walk-forward backtest, CLI
│   ├── paretos_agents/        # LangGraph nodes, orchestrator, prompts, LLM client
│   │   └── dashboard/         # Real-time browser UI (index.html)
│   └── paretos_marketplace/   # Work atoms, pricing, matching, FastAPI endpoints
├── tests/                     # pytest test suite
├── data/
│   ├── clean/                 # Tidy CSVs (start here)
│   ├── recommendations/       # 24 raw weekly optimiser plans
│   ├── actuals/               # 20 training weeks of ground truth
│   ├── cost_model.json        # Asymmetric cost parameters
│   └── decision_log.json      # 15 planner notes (messy, intentionally inconsistent)
├── run_pipeline.py            # Run the multi-agent pipeline with live dashboard
├── run_marketplace.py         # Start the marketplace API server
├── build_database.py          # Build SQLite DB from raw CSV/JSON
├── pyproject.toml             # Dependencies and project config
├── .env.example               # Environment variable template
└── learning.md                # Running journal of bugs, fixes, and lessons
```

---

## Prerequisites

- **Python 3.11+**
- **Anthropic API key** (required for the agent pipeline; the backtest/CLI works without it)

---

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/<your-username>/paretos.git
cd paretos
```

### 2. Create a virtual environment

```bash
python -m venv .venv
source .venv/bin/activate   # macOS / Linux
# .venv\Scripts\activate    # Windows
```

### 3. Install dependencies

```bash
# Core only (backtest, CLI, stats — no LLM required)
pip install -e .

# With agent pipeline (requires Anthropic API key)
pip install -e ".[agents]"

# With marketplace API
pip install -e ".[marketplace]"

# With development tools
pip install -e ".[dev]"

# Everything
pip install -e ".[agents,marketplace,dev]"
```

### 4. Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and add your Anthropic API key:

```
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

The backtest and CLI commands work without an API key. The agent pipeline requires it.

---

## Usage

### Run the backtest (no API key needed)

```bash
# Run all three strategies and compare
paretos backtest

# Or directly
python -m paretos_pipeline.cli backtest
```

### Run the multi-agent pipeline (requires API key)

```bash
# With live dashboard (opens browser)
python run_pipeline.py

# Without dashboard
python run_pipeline.py --no-viz

# Specific training week (0-19)
python run_pipeline.py --week 15
```

### CLI commands

```bash
paretos backtest              # Walk-forward backtest (strategies A/B/C)
paretos holdout               # Generate holdout predictions
paretos baseline              # Show raw optimiser cost
paretos detect                # Detect changepoints in staffing KPIs
paretos info                  # Dataset summary
```

### Start the marketplace API

```bash
python run_marketplace.py             # Default port 8000
python run_marketplace.py --port 8100 # Custom port
```

### Build the SQLite database

```bash
python build_database.py
```

This creates `paretos.db` from the raw CSV/JSON data files.

### Run tests

```bash
pytest
```

---

## Configuration

All settings can be configured via environment variables or a `.env` file. See `.env.example` for the full list. Key settings:

| Variable | Default | Description |
|---|---|---|
| `ANTHROPIC_API_KEY` | (required for agents) | Anthropic API key |
| `PRIMARY_LLM_MODEL` | `claude-sonnet-4-6` | Primary LLM model |
| `DATA_DIR` | `./data` | Root data directory |
| `LOG_LEVEL` | `INFO` | Logging level |
| `NEWSVENDOR_CRITICAL_RATIO` | `0.15` | Target percentile for cost optimisation |
| `SLA_TOLERANCE_PD` | `2.0` | Understaffing SLA threshold (person-days) |
| `REGIME_SENSITIVITY` | `0.05` | Changepoint detection sensitivity |

---

## Troubleshooting

**`ANTHROPIC_API_KEY not set`**
The agent pipeline requires an Anthropic API key. Copy `.env.example` to `.env` and fill in your key. The backtest and CLI work without it.

**`ModuleNotFoundError: No module named 'langgraph'`**
Install the agents extras: `pip install -e ".[agents]"`

**`ModuleNotFoundError: No module named 'fastapi'`**
Install the marketplace extras: `pip install -e ".[marketplace]"`

**Tests fail with import errors**
Make sure you installed in editable mode: `pip install -e ".[dev]"`

**Dashboard doesn't open**
The dashboard requires the `websockets` package (included in `[agents]`). It opens automatically at `http://localhost:8768` when running `python run_pipeline.py`.

---

## Dataset Reference

The `data/` directory contains the hackathon dataset from the paretos "Compounding Decisions" challenge. See `data/clean/` for tidy CSVs. Key files:

| File | Description |
|---|---|
| `clean/present_long.csv` | Daily actual staffing (total & operative person-days) |
| `clean/recommendations_long.csv` | Per-activity per-day optimiser plans |
| `clean/volumes_long.csv` | Forecast vs realised picks/outbound/inbound |
| `decision_log.json` | 15 planner notes (messy, some contradictory) |
| `cost_model.json` | Asymmetric cost parameters for scoring |

**Training period:** 20 weeks (May-Sep 2026). **Holdout:** 4 weeks (October 2026, actuals withheld).

---

## License

This project was built for the paretos hackathon. The dataset is synthetic and safe to share.
