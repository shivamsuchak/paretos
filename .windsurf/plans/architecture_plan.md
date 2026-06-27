# AI Engineering & Multi-Agent Architecture Plan
# Warehouse Staffing Optimisation — Helios Logistics DC Rhein-Main
### Compounding Decision Intelligence Platform

---

# Table of Contents

1. [Project Understanding](#1-project-understanding)
2. [Requirements Analysis](#2-requirements-analysis)
3. [AI Framework Research & Selection](#3-ai-framework-research--selection)
4. [Modular Architecture Design](#4-modular-architecture-design)
5. [Multi-Agent System Design](#5-multi-agent-system-design)
6. [Data Architecture](#6-data-architecture)
7. [API & Credential Management](#7-api--credential-management)
8. [Implementation Roadmap](#8-implementation-roadmap)
9. [Testing Strategy](#9-testing-strategy)
10. [Development Standards](#10-development-standards)
11. [Risk Mitigation](#11-risk-mitigation)
12. [Open Questions & Assumptions](#12-open-questions--assumptions)

---

# 1. Project Understanding

## 1.1 Business Problem Summary

Helios Logistics DC Rhein-Main uses a deterministic staffing optimiser with a **stale rate card** that has never been recalibrated. This causes:

- **100% systematic overstaffing** — every working day, averaging +10.4 person-days (+19.5%)
- **€234,600 wasted** over 20 weeks in idle labour
- **Asymmetric cost blindness** — overstaffing costs €230/pd vs understaffing at €41.40/pd (within tolerance)
- **No feedback loop** — actuals never fed back; planner knowledge exists only in informal notes
- **Regime blindness** — structural shifts (e.g., pick-by-light ~27% reduction) go undetected

## 1.2 Core Insight

> A flat −16.3% correction captures **92% of savings** with zero AI. AI/LLMs add value at the **knowledge curation**, **regime detection**, and **decision-support** layers — not at the core statistical correction.

This shapes our architecture: **deterministic statistical corrections first, AI agents for intelligence amplification second**.

## 1.3 Data Assets

| File | Schema | Purpose |
|---|---|---|
| `clean/present_long.csv` | `date, present_total_person_days, present_operative_person_days` | Ground truth (operative = total − 8 admin) |
| `clean/recommendations_long.csv` | `decision_date, planned_week_start, date, activity, group, recommended_person_days` | 15-activity recommendations per day |
| `clean/volumes_long.csv` | `date, picks_forecast/realized, outbound_forecast/realized, inbound_forecast/realized` | Volume forecast accuracy (±1–2%) |
| `data/decision_log.json` | 15 planner notes with `id, captured_on, author, scope, note, claimed_effect` | Unverified institutional knowledge |
| `data/cost_model.json` | Overstaffing €230/pd, understaffing €41.40/pd + €600 SLA penalty beyond 2.0 pd tolerance | Asymmetric cost function |

**Training data:** 20 weeks (May–September 2026), 98 working days
**Holdout:** 4 weeks (October 2026), actuals withheld

## 1.4 Key Domain Values

- **Overstaffing cost:** €230/person-day (idle wage)
- **Understaffing cost:** €41.40/pd (18% overtime premium) + €600/pd beyond 2.0 pd SLA tolerance
- **Newsvendor critical ratio:** cu/(cu+co) ≈ 0.15 → target 15th percentile
- **Pick-by-light gain:** ~27% reduction in picking person-days (from 2026-08-24)
- **Wednesday dip:** ~4 person-days systematic pattern
- **Decision cycle:** Weekly (Tuesday recommendation → Mon–Fri execution → actuals feedback)

---

# 2. Requirements Analysis

## 2.1 Functional Requirements

### FR-1: Statistical Correction Engine
- Apply bias correction (−16.3% flat trim) to optimiser recommendations
- Apply day-of-week adjustment factors (especially Wednesday −4 pd)
- Apply pick-by-light regime adjustment (−27% picking post Aug 24)
- Calculate newsvendor-optimal staffing quantile (15th percentile)

### FR-2: Knowledge Curation System
- Ingest planner notes (NL text) from decision log
- Parse claims, extract structured effects (fixed, scale_pct, add, conditional)
- Validate claims against historical actuals data
- Assign confidence scores; detect contradictions (e.g., L08 vs L09)
- Auto-flag notes older than 6 weeks for revalidation (per Fildes et al.)
- Retire stale knowledge; promote validated knowledge

### FR-3: Regime Detection
- Monitor KPIs for structural shifts using Bayesian changepoint detection
- Detect pick-by-light-type events within <5 days
- Trigger rate-card recalibration when regime change confirmed
- Maintain false positive rate <10%

### FR-4: Forecast & Volume Analysis
- Analyse volume forecast accuracy trends
- Detect seasonal ramps (autumn, flu season)
- Provide volume context to planning agents

### FR-5: Planning Adjustment
- Combine bias correction, regime state, DoW factors, validated knowledge, and cost model
- Produce adjusted staffing plan (date, planned_operative_person_days)
- Support planner review/override before commitment

### FR-6: Cost Optimisation
- Apply newsvendor-optimal bias using Monte Carlo simulation
- Respect SLA tolerance as hard constraint
- Report cost vs baseline for each cycle

### FR-7: Debrief Report Generation
- Generate weekly plan-vs-actual comparison narratives
- LLM-generated, data-grounded, planner-reviewed
- Standardised format; highlights key deviations and learnings

### FR-8: Compounding Loop
- Close the feedback loop: actuals → learning → next cycle adjustment
- Track knowledge lifecycle: capture → validate → apply → monitor → retire
- Measure gap closure over successive cycles

## 2.2 Non-Functional Requirements

| ID | Requirement | Target |
|---|---|---|
| NFR-1 | Pipeline execution time | <5 minutes per weekly cycle |
| NFR-2 | System uptime | 99.5% during planning hours |
| NFR-3 | LLM response latency | <30s per agent call |
| NFR-4 | Data freshness | Actuals ingested within 1 hour of availability |
| NFR-5 | Audit trail | Every decision, override, and outcome logged |
| NFR-6 | Cost transparency | LLM API costs tracked per agent per cycle |
| NFR-7 | Scalability | Architecture supports multi-site deployment |
| NFR-8 | Modularity | Each agent independently testable and replaceable |
| NFR-9 | Security | No PII in LLM prompts; API keys in env vars |
| NFR-10 | Reproducibility | Deterministic outputs for same inputs (where applicable) |

---

# 3. AI Framework Research & Selection

## 3.1 Framework Landscape (2025–2026)

| Framework | Architecture | Multi-Agent | State Mgmt | LLM Agnostic | Maturity | Python | License |
|---|---|---|---|---|---|---|---|
| **LangGraph** | Graph-based DAG | ✅ Native | ✅ Built-in checkpointing | ✅ Via LangChain | Mature (v1.0+) | ✅ | MIT |
| **CrewAI** | Role-based teams | ✅ Native | ⚠️ Basic | ✅ | Mature | ✅ | MIT |
| **AutoGen** | Conversation-driven | ✅ Native | ⚠️ Limited | ✅ | Maintenance mode | ✅ | MIT |
| **PydanticAI** | Type-safe agents | ⚠️ Manual | ⚠️ Manual | ✅ 20+ providers | Growing | ✅ | MIT |
| **OpenAI Agents SDK** | Runtime-based | ✅ Handoff | ⚠️ Basic | ❌ OpenAI only | New | ✅ | MIT |
| **Agno** | Fast agent SDK | ✅ Teams | ⚠️ Basic | ✅ | Growing | ✅ | MIT |
| **Semantic Kernel** | Enterprise plugins | ✅ | ✅ | ✅ | Mature | ✅ C# | MIT |
| **Haystack** | Pipeline-based | ⚠️ | ✅ | ✅ | Mature | ✅ | Apache |
| **DSPy** | Prompt programming | ❌ | ❌ | ✅ | Research | ✅ | MIT |
| **PocketFlow** | Minimalist graph | ⚠️ Manual | ✅ | ✅ | New | ✅ | MIT |

## 3.2 Evaluation Against Project Requirements

| Criterion | Weight | LangGraph | CrewAI | PydanticAI | OpenAI SDK |
|---|---|---|---|---|---|
| **Stateful graph orchestration** | 25% | ★★★★★ | ★★★☆☆ | ★★☆☆☆ | ★★★☆☆ |
| **Multi-agent coordination** | 20% | ★★★★★ | ★★★★☆ | ★★☆☆☆ | ★★★★☆ |
| **Human-in-the-loop support** | 15% | ★★★★★ | ★★★☆☆ | ★★★☆☆ | ★★☆☆☆ |
| **Tool integration (code exec, DB)** | 15% | ★★★★★ | ★★★★☆ | ★★★★☆ | ★★★☆☆ |
| **LLM provider flexibility** | 10% | ★★★★★ | ★★★★☆ | ★★★★★ | ★☆☆☆☆ |
| **Observability & debugging** | 5% | ★★★★★ | ★★★☆☆ | ★★★★☆ | ★★★☆☆ |
| **Community & ecosystem** | 5% | ★★★★★ | ★★★★☆ | ★★★☆☆ | ★★★★☆ |
| **Production readiness** | 5% | ★★★★★ | ★★★☆☆ | ★★★☆☆ | ★★☆☆☆ |
| **Weighted Score** | | **4.65** | **3.45** | **2.85** | **2.75** |

## 3.3 Framework Decision: **LangGraph**

**Rationale:**

1. **Graph-based orchestration** maps directly to our pipeline (Forecast → Knowledge → Regime → Planning → Cost → Debrief → Human Review). Each agent is a node; edges define data flow and conditional branching.

2. **Built-in state management** with checkpointing enables:
   - Resuming failed pipelines from the last successful node
   - Human-in-the-loop interrupts (planner review gates)
   - Audit trail of state transitions

3. **Battle-tested at scale** — v1.0+ released late 2025; default runtime for production LangChain applications. Well-documented patterns for multi-agent systems.

4. **LLM-agnostic** — supports GPT-4o, Claude 3.5 Sonnet, Llama, Mistral, etc. via LangChain integrations. No vendor lock-in.

5. **Native tool use** — agents can call Python functions, database queries, statistical libraries directly as tools.

6. **Observability** — first-class support for LangSmith tracing; compatible with Langfuse and OpenTelemetry.

**Trade-offs acknowledged:**
- Steeper learning curve than CrewAI (graph thinking vs role-based thinking)
- LangChain ecosystem coupling (mitigated: LangGraph can work standalone)
- No native A2A/MCP protocol support yet (not needed for single-site deployment)

**Alternatives kept as fallback:**
- **PydanticAI** for type-safe individual agent implementations (can be used alongside LangGraph)
- **CrewAI** if rapid prototyping is prioritised over fine-grained control in PoC

## 3.4 Supporting Technology Decisions

| Layer | Choice | Rationale |
|---|---|---|
| **Primary LLM** | GPT-4o | Best reasoning for knowledge curation; strong tool use |
| **Secondary LLM** | Claude 3.5 Sonnet | Alternative for complex reasoning; avoids single-vendor |
| **Small/cheap LLM** | GPT-4o-mini | Report generation, simple NL tasks, low cost |
| **Vector DB** | ChromaDB (start) → Weaviate (scale) | Small corpus (<100 docs); zero-infra start |
| **Data platform** | DuckDB (start) → PostgreSQL (prod) | Analytical queries on CSVs; zero-infra start |
| **Orchestration** | LangGraph (agent) + Cron/Airflow (schedule) | LangGraph handles agent flow; cron for weekly trigger |
| **Monitoring** | LangSmith + structured logging | LLM trace analysis + operational KPIs |
| **RAG evaluation** | RAGAS | Standardised RAG quality metrics |
| **Changepoint detection** | `bayesian-changepoint-detection` / `ruptures` | Adams & MacKay (2007) implementation |
| **Statistical tools** | pandas, numpy, scipy, statsmodels | Standard Python data science stack |

---

# 4. Modular Architecture Design

## 4.1 High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    PRESENTATION LAYER                            │
│  CLI Interface │ Report Output │ (Future: Web Dashboard)        │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                    ORCHESTRATION LAYER                           │
│              LangGraph State Machine (Weekly Cycle)              │
│     ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐  ┌──────┐│
│     │Forec.│→ │Knowl.│→ │Regime│→ │Plan. │→ │Cost  │→ │Debrief││
│     │Agent │  │Agent │  │Agent │  │Agent │  │Agent │  │Agent  ││
│     └──────┘  └──────┘  └──────┘  └──────┘  └──────┘  └──────┘│
│                    ↕ Human Review Gate ↕                         │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                    INTELLIGENCE LAYER                            │
│  LLM Provider │ RAG Pipeline │ Statistical Engine │ Cost Engine │
└────────────────────────────┬────────────────────────────────────┘
                             │
┌────────────────────────────▼────────────────────────────────────┐
│                    DATA LAYER                                    │
│  DuckDB │ ChromaDB │ File System │ Audit Log │ Knowledge Store  │
└─────────────────────────────────────────────────────────────────┘
```

## 4.2 Module Breakdown

### Module 1: `paretos_core` — Core Data & Configuration
**Responsibility:** Data loading, validation, configuration, cost model
```
paretos_core/
├── __init__.py
├── config.py           # Environment variables, paths, constants
├── cost_model.py       # Asymmetric cost function, newsvendor math
├── data_loader.py      # CSV/JSON ingestion with validation
├── schemas.py          # Pydantic models for all data structures
└── exceptions.py       # Custom exception hierarchy
```

**Key classes:**
- `CostModel` — implements scoring: overstaffing €230/pd, understaffing €41.40 + €600 SLA penalty
- `StaffingPlan` — Pydantic model: `date, planned_operative_person_days`
- `WeeklyData` — container for recommendation + actuals + volumes for one cycle

### Module 2: `paretos_stats` — Statistical Engine
**Responsibility:** All deterministic/statistical computations (no LLMs)
```
paretos_stats/
├── __init__.py
├── bias_correction.py   # Flat trim, rolling bias, per-activity
├── dow_adjustment.py    # Day-of-week factors (Mon–Fri)
├── changepoint.py       # Bayesian changepoint detection (Adams & MacKay)
├── newsvendor.py        # Critical ratio, optimal quantile calculation
├── forecast_accuracy.py # Volume forecast error analysis
├── monte_carlo.py       # Cost simulation under uncertainty
└── regime_state.py      # Regime tracking state machine
```

**Design principle:** Pure functions where possible. No LLM calls. Deterministic and testable.

### Module 3: `paretos_knowledge` — Knowledge Management
**Responsibility:** Decision log curation, RAG pipeline, knowledge lifecycle
```
paretos_knowledge/
├── __init__.py
├── note_parser.py       # NL → structured claim extraction (LLM-powered)
├── note_validator.py    # Validate claims against actuals data
├── knowledge_store.py   # CRUD for validated notes with confidence scores
├── contradiction.py     # Detect and flag conflicting notes
├── staleness.py         # Auto-flag notes older than threshold
├── embeddings.py        # Embedding generation for RAG
└── retrieval.py         # Semantic search over knowledge base
```

**Key lifecycle:** Capture → Parse → Validate → Score → Apply → Monitor → Retire

### Module 4: `paretos_agents` — Multi-Agent System
**Responsibility:** LangGraph agent definitions, tools, prompts, orchestration
```
paretos_agents/
├── __init__.py
├── orchestrator.py      # LangGraph state machine definition
├── state.py             # Shared state schema for the graph
├── agents/
│   ├── forecast_agent.py
│   ├── knowledge_agent.py
│   ├── regime_agent.py
│   ├── planning_agent.py
│   ├── cost_agent.py
│   └── debrief_agent.py
├── tools/
│   ├── data_tools.py    # Query actuals, recommendations, volumes
│   ├── stats_tools.py   # Statistical computation tools
│   ├── knowledge_tools.py  # Knowledge base CRUD tools
│   └── cost_tools.py    # Cost calculation tools
├── prompts/
│   ├── knowledge_curation.py
│   ├── debrief_generation.py
│   └── planning_explanation.py
└── checkpoints.py       # Human-in-the-loop interrupt logic
```

### Module 5: `paretos_pipeline` — Execution Pipeline
**Responsibility:** Weekly cycle execution, scheduling, entry points
```
paretos_pipeline/
├── __init__.py
├── weekly_cycle.py      # Main pipeline: ingest → agents → output
├── holdout_runner.py    # Generate holdout predictions
├── backtest.py          # Walk-forward backtesting over training weeks
└── cli.py               # Command-line interface
```

### Module 6: `paretos_reports` — Output & Reporting
**Responsibility:** Report generation, plan output, dashboards
```
paretos_reports/
├── __init__.py
├── debrief_report.py    # Weekly debrief markdown/PDF
├── plan_output.py       # Staffing plan CSV output (scoring format)
├── cost_summary.py      # Cost analysis vs baseline/perfect
└── knowledge_report.py  # Knowledge base status report
```

### Module 7: `paretos_eval` — Evaluation & Monitoring
**Responsibility:** Quality metrics, RAG evaluation, agent performance
```
paretos_eval/
├── __init__.py
├── scoring.py           # Cost scoring against actuals
├── rag_eval.py          # RAGAS metrics for knowledge retrieval
├── agent_eval.py        # Per-agent performance tracking
├── drift_monitor.py     # Model/correction drift detection
└── cost_tracker.py      # LLM API cost tracking per agent
```

## 4.3 Dependency Graph

```
paretos_core (foundation — no internal deps)
    ↑
paretos_stats (depends on: core)
    ↑
paretos_knowledge (depends on: core, stats)
    ↑
paretos_agents (depends on: core, stats, knowledge)
    ↑
paretos_pipeline (depends on: core, agents)
    ↑
paretos_reports (depends on: core, pipeline)
    ↑
paretos_eval (depends on: core, stats, pipeline)
```

---

# 5. Multi-Agent System Design

## 5.1 Agent Overview

| Agent | Role | LLM Required | Automation Level | Human Gate |
|---|---|---|---|---|
| **Forecast Agent** | Volume forecast accuracy analysis | No | Fully autonomous | No |
| **Knowledge Agent** | Parse, validate, curate planner notes | Yes (GPT-4o) | Semi-autonomous | Note retirement |
| **Regime Agent** | Detect structural shifts in KPIs | No | Autonomous detection | Parameter changes |
| **Planning Agent** | Combine corrections into adjusted plan | Optional (explanation) | Semi-autonomous | Plan commitment |
| **Cost Agent** | Newsvendor-optimal bias application | No | Semi-autonomous | Offset changes |
| **Debrief Agent** | Generate weekly narrative reports | Yes (GPT-4o-mini) | Autonomous generation | Distribution |

## 5.2 LangGraph State Schema

```python
from typing import TypedDict, Optional, Annotated
from datetime import date

class PipelineState(TypedDict):
    # Inputs
    cycle_date: date                        # Decision Tuesday
    planned_week_start: date                # Following Monday
    raw_recommendations: dict               # Activity-level recs
    actuals: Optional[dict]                 # Previous week actuals (if available)
    volumes: Optional[dict]                 # Volume forecasts + realised

    # Agent outputs (accumulated through graph)
    forecast_context: dict                  # Forecast Agent output
    knowledge_updates: list[dict]           # Knowledge Agent output
    regime_flags: dict                      # Regime Agent output
    adjusted_plan: dict                     # Planning Agent output
    optimised_plan: dict                    # Cost Agent output
    debrief_report: str                     # Debrief Agent output

    # Governance
    human_approved: bool                    # Planner review gate
    overrides: list[dict]                   # Planner manual overrides
    audit_log: list[dict]                   # Full decision trace

    # Error handling
    errors: list[str]                       # Agent-level errors
    fallback_used: bool                     # Whether fallback was triggered
```

## 5.3 Agent Specifications

### Agent 1: Forecast & Volume Analysis Agent

| Attribute | Detail |
|---|---|
| **Input** | `volumes` (forecast vs realised), historical accuracy |
| **Output** | `forecast_context`: accuracy metrics, trend flags, confidence |
| **Tools** | `query_volumes()`, `calculate_mape()`, `detect_trend()` |
| **LLM** | None (pure statistical) |
| **Failure mode** | Return empty context; pipeline continues |
| **Metrics** | Forecast error tracking over cycles |

**Implementation:** Pure Python function node in LangGraph. No LLM call needed. Computes MAPE, bias direction, trend indicators (autumn ramp detection).

### Agent 2: Knowledge Curation Agent

| Attribute | Detail |
|---|---|
| **Input** | New/existing notes from decision log, actuals data |
| **Output** | `knowledge_updates`: validated notes with confidence scores |
| **Tools** | `parse_note()`, `validate_claim()`, `search_knowledge()`, `flag_contradiction()`, `check_staleness()` |
| **LLM** | GPT-4o (NL parsing, reasoning about contradictions) |
| **Memory** | ChromaDB vector store for semantic search over notes |
| **Human gate** | Before retiring or promoting notes |
| **Failure mode** | Skip curation; preserve existing knowledge state |
| **Metrics** | Precision/recall vs analyst assessment; notes curated per cycle |

**Prompt strategy:**
1. System prompt defines the curation role and output schema
2. Each note is parsed into structured `ClaimEffect` (Pydantic model)
3. Statistical validation tool called to test claim against actuals
4. LLM reasons about confidence given evidence
5. Contradiction detection across existing knowledge base

**Example flow for note L08 vs L09 (summer volume contradiction):**
```
L08 (Selin): "Cut operative plan ~15% through late-summer weeks"
L09 (Jonas): "Heat is KILLING throughput. We actually needed more hours."
→ Knowledge Agent detects contradiction on scope "operative" for weeks W30–W33
→ Calls validate_claim() against actuals for those weeks
→ Assigns confidence: L08=0.4, L09=0.6 (data supports higher need due to heat)
→ Flags for human resolution; neither applied until resolved
```

### Agent 3: Regime Detection Agent

| Attribute | Detail |
|---|---|
| **Input** | Time series of error ratios (recommended/actual) |
| **Output** | `regime_flags`: detected changepoints with probabilities |
| **Tools** | `run_bayesian_changepoint()`, `run_cusum()`, `compare_regimes()` |
| **LLM** | None (pure statistical) |
| **Human gate** | Before applying parameter changes |
| **Failure mode** | Return no flags; continue with current regime |
| **Metrics** | Detection latency (<5 days); false positive rate (<10%) |

**Implementation:** Uses `ruptures` or custom Bayesian online changepoint detection (Adams & MacKay 2007). Monitors:
- Rolling mean of error ratio
- Activity-level error ratios (especially picking)
- Volume-to-person-day conversion factor drift

**Known regime:** Pick-by-light (Aug 24) — system should detect this within 5 observations.

### Agent 4: Planning Adjustment Agent

| Attribute | Detail |
|---|---|
| **Input** | Raw recommendation, `forecast_context`, `knowledge_updates`, `regime_flags`, cost model |
| **Output** | `adjusted_plan`: `{date: planned_operative_person_days}` |
| **Tools** | `apply_bias_correction()`, `apply_dow_factors()`, `apply_regime_adjustment()`, `apply_knowledge_rules()` |
| **LLM** | Optional GPT-4o-mini for generating human-readable explanation of adjustments |
| **Human gate** | **Yes — planner reviews and approves/overrides before commitment** |
| **Failure mode** | Fall back to last-known-good correction parameters |
| **Metrics** | Weekly cost vs baseline; % gap closed |

**Correction stack (applied in order):**
1. Flat bias correction (−16.3% × raw recommendation)
2. Day-of-week factors (per-weekday multipliers)
3. Regime adjustment (if active: e.g., −27% picking post pick-by-light)
4. Knowledge-based rules (validated notes with confidence > threshold)
5. Newsvendor offset (from Cost Agent, if available)

### Agent 5: Cost Optimisation Agent

| Attribute | Detail |
|---|---|
| **Input** | `adjusted_plan`, error distribution, cost model |
| **Output** | `optimised_plan`: newsvendor-adjusted staffing levels |
| **Tools** | `compute_newsvendor_quantile()`, `run_monte_carlo()`, `evaluate_cost()` |
| **LLM** | None (pure mathematical) |
| **Human gate** | Before changing newsvendor offset (management approval for deliberate understaffing) |
| **Failure mode** | Return adjusted plan unchanged |
| **Metrics** | Actual cost vs predicted; SLA compliance rate |

**Newsvendor logic:**
- Critical ratio: cu/(cu+co) where cu = €41.40 (understaffing) and co = €230 (overstaffing)
- Optimal quantile: ~0.15 → target 15th percentile of error distribution
- SLA hard constraint: never plan more than 2.0 pd below expected need
- Monte Carlo simulation for confidence interval on cost outcomes

### Agent 6: Debrief Report Agent

| Attribute | Detail |
|---|---|
| **Input** | All agent outputs, actuals vs plan comparison |
| **Output** | `debrief_report`: structured markdown narrative |
| **Tools** | `get_weekly_comparison()`, `summarise_knowledge_changes()`, `get_cost_breakdown()` |
| **LLM** | GPT-4o-mini (narrative generation) |
| **Human gate** | Planner reviews before distribution |
| **Failure mode** | Generate data-only summary without narrative |
| **Metrics** | Planner satisfaction score; report generation time |

**Report sections:**
1. Executive summary (cost performance vs baseline)
2. Plan vs actual comparison (daily breakdown)
3. Key deviations and root causes
4. Knowledge base updates (new/retired/promoted notes)
5. Regime status (any detected changes)
6. Recommendations for next cycle

## 5.4 LangGraph Execution Flow

```python
# Simplified LangGraph definition
from langgraph.graph import StateGraph, END

workflow = StateGraph(PipelineState)

# Add agent nodes
workflow.add_node("forecast", forecast_agent)
workflow.add_node("knowledge", knowledge_agent)
workflow.add_node("regime", regime_agent)
workflow.add_node("planning", planning_agent)
workflow.add_node("cost_opt", cost_agent)
workflow.add_node("debrief", debrief_agent)
workflow.add_node("human_review", human_review_gate)

# Define edges
workflow.set_entry_point("forecast")

# Forecast and Knowledge run in parallel, then feed into Regime
workflow.add_edge("forecast", "regime")
workflow.add_edge("knowledge", "regime")

# Sequential: Regime → Planning → Cost → Human Review → Debrief
workflow.add_edge("regime", "planning")
workflow.add_edge("planning", "cost_opt")
workflow.add_edge("cost_opt", "human_review")

# Conditional: Human approves → Debrief; Human rejects → Planning (loop)
workflow.add_conditional_edges(
    "human_review",
    lambda state: "debrief" if state["human_approved"] else "planning",
    {"debrief": "debrief", "planning": "planning"}
)

workflow.add_edge("debrief", END)
```

**Parallel execution:** Forecast and Knowledge agents run concurrently (no data dependency). Regime agent waits for both before proceeding.

**Human-in-the-loop:** After Cost Agent produces optimised plan, execution pauses at `human_review` node. Planner reviews via CLI/report, approves or overrides. LangGraph's checkpoint system enables this naturally.

## 5.5 Shared Memory Architecture

| Store | Technology | Contents | Access Pattern |
|---|---|---|---|
| **Operational DB** | DuckDB | Raw CSVs, actuals, recommendations, volumes | All agents (read); Data loader (write) |
| **Knowledge Base** | ChromaDB + JSON | Validated notes with embeddings and confidence | Knowledge Agent (write); All (read) |
| **Regime State** | JSON file / DuckDB | Current flags, changepoint history, regime parameters | Regime Agent (write); Planning (read) |
| **Correction Parameters** | JSON config | Bias factor, DoW multipliers, newsvendor offset | Planning + Cost (read/write) |
| **Audit Log** | Structured JSON/SQLite | Every agent decision, human override, cost outcome | All agents (append); Orchestrator (read) |
| **LLM Trace Store** | LangSmith / local logs | Prompt/response pairs, token usage, latency | Eval module (read) |

## 5.6 Error Recovery & Graceful Degradation

| Scenario | Response | Fallback |
|---|---|---|
| LLM API unavailable | Skip LLM-dependent agents | Use last-known correction parameters |
| Knowledge Agent fails | Skip curation for this cycle | Existing knowledge base unchanged |
| Regime detection false alarm | Planner rejects → log rejection | Continue with current regime state |
| Data quality issue | Validate checksums; halt if critical | Hold previous corrections |
| Contradictory knowledge | Flag for human resolution | Neither claim applied until resolved |
| Agent timeout (>60s) | Cancel and proceed with fallback | Previous cycle's output used |
| Full pipeline failure | Alert planner; use raw recommendation | Manual planning (current state) |

---

# 6. Data Architecture

## 6.1 Data Flow

```
Raw Files (CSV/JSON)
    ↓ [data_loader.py]
DuckDB (normalised tables)
    ↓ [agent tools]
Agent Processing (LangGraph)
    ↓ [plan_output.py]
Staffing Plan CSV (scoring format: date, planned_operative_person_days)
    ↓ [scoring.py]
Cost Evaluation (vs baseline, vs perfect)
```

## 6.2 DuckDB Schema

```sql
-- Recommendations (activity-level)
CREATE TABLE recommendations (
    decision_date DATE,
    planned_week_start DATE,
    date DATE,
    activity VARCHAR,
    group_name VARCHAR,
    recommended_person_days DOUBLE
);

-- Actuals (daily totals)
CREATE TABLE actuals (
    date DATE PRIMARY KEY,
    present_total_person_days DOUBLE,
    present_operative_person_days DOUBLE
);

-- Volumes
CREATE TABLE volumes (
    date DATE PRIMARY KEY,
    picks_forecast INTEGER,
    picks_realized INTEGER,
    outbound_forecast INTEGER,
    outbound_realized INTEGER,
    inbound_forecast INTEGER,
    inbound_realized INTEGER
);

-- Knowledge base (curated notes)
CREATE TABLE knowledge (
    id VARCHAR PRIMARY KEY,
    captured_on DATE,
    author VARCHAR,
    scope VARCHAR,
    note TEXT,
    claimed_effect JSON,
    validation_status VARCHAR,  -- 'pending', 'validated', 'rejected', 'stale'
    confidence DOUBLE,
    validated_on DATE,
    retired_on DATE
);

-- Audit log
CREATE TABLE audit_log (
    id INTEGER PRIMARY KEY,
    cycle_date DATE,
    agent VARCHAR,
    action VARCHAR,
    input_summary JSON,
    output_summary JSON,
    human_override BOOLEAN,
    timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Correction parameters (versioned)
CREATE TABLE correction_params (
    version INTEGER PRIMARY KEY,
    effective_from DATE,
    bias_factor DOUBLE,
    dow_factors JSON,  -- {"Mon": 1.0, "Tue": 0.98, ...}
    regime_adjustments JSON,
    newsvendor_offset DOUBLE,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## 6.3 Walk-Forward Backtesting

The system processes 20 training weeks sequentially, simulating the compounding loop:

```
Week 1 (May 18): Recommendation → Correction (minimal) → Plan → Actuals arrive → Learn
Week 2 (May 25): Recommendation → Correction (updated) → Plan → Actuals arrive → Learn
...
Week 20 (Oct 5): Recommendation → Correction (compounded 19 weeks) → Plan
Week 21-24 (Holdout): Recommendation → Correction (final parameters) → Plan → Submit
```

Each week uses ONLY information available up to that decision date. No future data leakage.

---

# 7. API & Credential Management

## 7.1 Environment Variables

```bash
# .env (NOT committed to version control)

# LLM Providers
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# LLM Configuration
PRIMARY_LLM_MODEL=gpt-4o
SECONDARY_LLM_MODEL=claude-3-5-sonnet-20241022
SMALL_LLM_MODEL=gpt-4o-mini
LLM_TEMPERATURE=0.1        # Low temp for deterministic outputs
LLM_MAX_TOKENS=4096

# Data Paths
DATA_DIR=/Users/shivamsuchak/Documents/paretos/data
CLEAN_DATA_DIR=/Users/shivamsuchak/Documents/paretos/data/clean

# Database
DUCKDB_PATH=./paretos.duckdb

# Vector Store
CHROMA_PERSIST_DIR=./chroma_db
EMBEDDING_MODEL=text-embedding-3-small

# Monitoring
LANGCHAIN_TRACING_V2=true
LANGCHAIN_API_KEY=ls-...
LANGCHAIN_PROJECT=paretos-staffing

# Logging
LOG_LEVEL=INFO
LOG_FILE=./logs/paretos.log

# Agent Configuration
KNOWLEDGE_STALENESS_WEEKS=6
NEWSVENDOR_CRITICAL_RATIO=0.15
SLA_TOLERANCE_PD=2.0
REGIME_SENSITIVITY=0.05
```

## 7.2 Security Practices

1. **`.env` in `.gitignore`** — never committed
2. **`.env.example`** committed with placeholder values for onboarding
3. **No PII in LLM prompts** — operational data only (volumes, person-days)
4. **API key validation on startup** — fail fast with clear error message
5. **Token usage tracking** — per-agent, per-cycle cost monitoring
6. **Rate limiting** — respect API rate limits with exponential backoff

---

# 8. Implementation Roadmap

## Phase 1: Foundation (Week 1) — Core + Stats

**Objective:** Build the deterministic correction engine that captures 92% of savings.

**Deliverables:**
- [ ] Project scaffolding (virtualenv, pyproject.toml, pre-commit hooks)
- [ ] `paretos_core`: data loader, schemas, cost model, config
- [ ] `paretos_stats`: bias correction, DoW adjustment, regime state
- [ ] `paretos_eval`: scoring against actuals
- [ ] Walk-forward backtest over 20 training weeks
- [ ] Holdout predictions using flat trim + DoW

**Success criteria:**
- >85% cost gap closure on training data
- All 20 weeks processed sequentially without data leakage
- Cost scoring matches reference implementation
- Unit tests pass for all statistical modules

**Dependencies:** None (self-contained)

**Risks:** Low — deterministic computations, well-understood math

## Phase 2: Knowledge System (Week 2) — Knowledge + RAG

**Objective:** Build LLM-powered knowledge curation that compounds planner wisdom.

**Deliverables:**
- [ ] `paretos_knowledge`: note parser, validator, knowledge store, contradiction detector
- [ ] ChromaDB vector store with embeddings for decision log
- [ ] LLM integration (GPT-4o) for NL parsing and reasoning
- [ ] Validation of all 15 decision log entries against actuals
- [ ] Knowledge lifecycle implementation (capture → validate → retire)

**Success criteria:**
- ≥80% note validation accuracy vs manual assessment
- L08/L09 contradiction detected automatically
- L03 → L11/L12 staleness transition detected (12% → 27%)
- Pick-by-light regime change surfaced from notes

**Dependencies:** Phase 1 (core, stats, data access)

**Risks:** Medium — LLM hallucination; requires prompt engineering iteration

## Phase 3: Multi-Agent Pipeline (Week 3) — Agents + Orchestration

**Objective:** Wire agents into LangGraph pipeline with human-in-the-loop.

**Deliverables:**
- [ ] `paretos_agents`: all 6 agents as LangGraph nodes
- [ ] LangGraph state machine with full execution flow
- [ ] Human review gate (CLI-based approve/override)
- [ ] Agent tools (data queries, stats computations, knowledge operations)
- [ ] Walk-forward backtest with full agent pipeline

**Success criteria:**
- Full pipeline executes for 20 training weeks
- Compounding improvement visible across weeks
- Human-in-the-loop gate functional
- Cost improvement > flat trim alone (>86% gap closure)

**Dependencies:** Phase 1 + Phase 2

**Risks:** Medium — LangGraph integration complexity; agent coordination

## Phase 4: Optimisation & Polish (Week 4) — Cost Optimisation + Reports + Evaluation

**Objective:** Add newsvendor optimisation, debrief reports, holdout submission, and comprehensive evaluation.

**Deliverables:**
- [ ] `paretos_stats`: newsvendor optimisation, Monte Carlo simulation
- [ ] `paretos_agents`: Cost Agent, Debrief Agent fully functional
- [ ] `paretos_reports`: weekly debrief markdown generation
- [ ] `paretos_eval`: full evaluation suite (scoring, RAG eval, agent performance)
- [ ] Final holdout predictions
- [ ] Comprehensive documentation

**Success criteria:**
- Newsvendor optimisation improves cost vs naive trim
- SLA tolerance never violated (hard constraint)
- Debrief reports pass manual review
- Complete audit trail for all 24 cycles
- All tests pass; documentation complete

**Dependencies:** Phases 1–3

**Risks:** Medium — Monte Carlo tuning; balancing undershoot vs SLA risk

## Phase Summary

| Phase | Duration | Key Delivery | Risk |
|---|---|---|---|
| 1: Foundation | 1 week | Deterministic correction engine (92% savings) | Low |
| 2: Knowledge | 1 week | LLM knowledge curation + RAG | Medium |
| 3: Agents | 1 week | Full multi-agent pipeline | Medium |
| 4: Optimisation | 1 week | Cost optimisation + reports + holdout | Medium |

---

# 9. Testing Strategy

## 9.1 Test Hierarchy

```
Unit Tests (pytest)
├── paretos_core/tests/       — Data loading, schemas, cost model
├── paretos_stats/tests/      — All statistical functions
├── paretos_knowledge/tests/  — Note parsing, validation, staleness
├── paretos_agents/tests/     — Individual agent logic
├── paretos_eval/tests/       — Scoring, metrics

Integration Tests
├── test_pipeline_e2e.py      — Full pipeline on 1 training week
├── test_agent_chain.py       — Multi-agent data flow
├── test_knowledge_loop.py    — Full curation lifecycle

Property-Based Tests (Hypothesis)
├── test_cost_model_props.py  — Cost function edge cases
├── test_corrections_props.py — Correction factor bounds

Regression Tests
├── test_known_outputs.py     — Golden-file tests for known inputs
├── test_holdout_stable.py    — Holdout predictions don't regress
```

## 9.2 Key Test Cases

| Module | Test | Assertion |
|---|---|---|
| `cost_model` | Overstaffing of 5 pd | Cost = 5 × €230 = €1,150 |
| `cost_model` | Understaffing of 1 pd (within tolerance) | Cost = 1 × €41.40 = €41.40 |
| `cost_model` | Understaffing of 3 pd (exceeds tolerance) | Cost = 2 × €41.40 + 1 × €600 = €682.80 |
| `bias_correction` | −16.3% on 65 pd recommendation | Result = 54.41 pd |
| `dow_adjustment` | Wednesday factor applied | Result includes ~4 pd reduction |
| `changepoint` | Pick-by-light detection | Changepoint detected within 5 observations of Aug 24 |
| `note_parser` | L01 "transit always 4" | Parsed as `ClaimEffect(kind='fixed', activity='transit', value=4)` |
| `contradiction` | L08 vs L09 | Contradiction flagged on scope 'operative' |
| `staleness` | L03 (Jun 9, −12%) after L11 (Aug 25, −25%) | L03 flagged as stale |
| `newsvendor` | Critical ratio 0.15 | Target 15th percentile of error distribution |
| `scoring` | Week 1 baseline vs corrected plan | Corrected plan has lower cost |

## 9.3 Testing Principles

1. **No mocking of statistical functions** — test with real data subsets
2. **LLM calls mocked in unit tests** — use recorded responses
3. **Integration tests use live LLM** — with small, targeted prompts
4. **Walk-forward validation** — no future data leakage
5. **Golden-file tests** — known inputs → expected outputs checked in
6. **Property-based tests** for cost model edge cases (Hypothesis library)

---

# 10. Development Standards

## 10.1 Project Structure

```
paretos/
├── .env                      # Secrets (gitignored)
├── .env.example              # Template with placeholders
├── .gitignore
├── pyproject.toml            # Dependencies, build config, tool config
├── README.md                 # Existing dataset documentation
├── architecture_plan.md      # This document
├── data/                     # Existing data (unchanged)
│   ├── clean/
│   ├── actuals/
│   ├── recommendations/
│   ├── cost_model.json
│   └── decision_log.json
├── src/
│   ├── paretos_core/
│   ├── paretos_stats/
│   ├── paretos_knowledge/
│   ├── paretos_agents/
│   ├── paretos_pipeline/
│   ├── paretos_reports/
│   └── paretos_eval/
├── tests/
│   ├── unit/
│   ├── integration/
│   └── conftest.py
├── notebooks/                # Exploratory analysis
├── logs/                     # Runtime logs (gitignored)
└── output/                   # Generated plans and reports (gitignored)
```

## 10.2 Python Environment

```bash
# Virtual environment
python -m venv .venv
source .venv/bin/activate

# Dependency management via pyproject.toml
pip install -e ".[dev]"
```

**Key dependencies:**
```toml
[project]
dependencies = [
    "langgraph>=0.2",
    "langchain-core>=0.3",
    "langchain-openai>=0.2",
    "langchain-anthropic>=0.2",
    "chromadb>=0.5",
    "duckdb>=1.0",
    "pydantic>=2.0",
    "pandas>=2.0",
    "numpy>=1.26",
    "scipy>=1.12",
    "ruptures>=1.1",          # Changepoint detection
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "pytest-cov>=5.0",
    "hypothesis>=6.0",
    "ruff>=0.5",
    "mypy>=1.10",
    "pre-commit>=3.0",
]
```

## 10.3 Coding Standards

- **Formatter/Linter:** Ruff (replaces black + isort + flake8)
- **Type checking:** mypy (strict mode)
- **Docstrings:** Google style
- **Max line length:** 100 characters
- **Naming:** snake_case functions/variables, PascalCase classes
- **Pydantic models** for all data structures crossing module boundaries
- **No global state** — all configuration via dependency injection
- **Pure functions** wherever possible (especially in `paretos_stats`)

## 10.4 Git Workflow

- `main` — stable, tested, deployable
- `develop` — integration branch
- Feature branches: `feature/phase-X-module-name`
- Commit messages: conventional commits (`feat:`, `fix:`, `test:`, `docs:`)
- Pre-commit hooks: ruff format + lint + mypy

---

# 11. Risk Mitigation

| Risk | Likelihood | Impact | Mitigation | Owner |
|---|---|---|---|---|
| **LLM hallucination** in knowledge curation | Medium | High | Structured output validation; data-grounded prompts; human review | Knowledge Agent |
| **Overfitting** to 98 training rows | Medium | Medium | Walk-forward validation; simple models first; regularisation | Stats module |
| **Pick-by-light regime** missed | Low | High | Bayesian changepoint + planner note corroboration | Regime Agent |
| **Cost model asymmetry** misapplied | Low | High | Hard SLA constraint; Monte Carlo validation | Cost Agent |
| **Agent coordination failure** | Medium | Medium | Graceful degradation; fallback to last-known-good | Orchestrator |
| **API rate limits / outages** | Low | Medium | Retry with backoff; fallback to non-LLM path | All LLM agents |
| **Scope creep** | Medium | Medium | Phase gates; clear deliverables per phase | Project lead |
| **Data leakage** in walk-forward | Low | High | Strict temporal filtering; code review | Backtest module |

---

# 12. Open Questions & Assumptions

## 12.1 Assumptions (Used Defaults)

| # | Assumption | Default Used | Impact if Wrong |
|---|---|---|---|
| A1 | LLM provider: OpenAI primary | GPT-4o + GPT-4o-mini | Swap to Claude via LangChain; minimal code change |
| A2 | Deployment: local development | Single-machine execution | Scale to cloud later if needed |
| A3 | Human-in-the-loop: CLI-based | Terminal prompts for approval | Can add web UI in future phase |
| A4 | Scheduling: manual trigger | Developer runs pipeline | Add cron/Airflow for production |
| A5 | Budget: moderate LLM spend | ~€200–500/month API costs | Use smaller models or local Llama to reduce |
| A6 | Holdout scoring: standard format | `date,planned_operative_person_days` CSV | Verify with scoring.py reference |
| A7 | Admin always 8 person-days | Excluded from optimisation | Confirmed in cost_model.json |
| A8 | Walk-forward: weekly granularity | 20 sequential training cycles | Could be daily but weekly matches decision cycle |

## 12.2 Questions for User Review

1. **LLM preference:** GPT-4o vs Claude 3.5 Sonnet as primary? (Defaulted to GPT-4o)
2. **Budget constraints:** Any hard ceiling on monthly LLM API costs?
3. **Holdout submission format:** Is `date,planned_operative_person_days` CSV correct?
4. **Evaluation priority:** Cost minimisation vs knowledge quality vs both?
5. **Human-in-the-loop UX:** CLI sufficient or need web interface?
6. **Multi-site scope:** Plan for single-site only, or design for future multi-site now?
7. **Deployment target:** Local only, or cloud deployment needed?

---

# Next Steps

**Awaiting your approval** to proceed with Phase 1 implementation. Upon approval, I will:

1. Set up project scaffolding (`pyproject.toml`, virtual environment, directory structure)
2. Implement `paretos_core` (data loading, schemas, cost model, configuration)
3. Implement `paretos_stats` (bias correction, DoW adjustment, changepoint detection)
4. Implement `paretos_eval` (scoring against actuals)
5. Run walk-forward backtest over 20 training weeks
6. Generate initial holdout predictions

---

*Architecture plan generated based on AI Strategy Report (June 27, 2026), Analysis Report, dataset documentation, and current AI framework research (2025–2026).*
