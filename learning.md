# Learning Journal — Paretos Warehouse Staffing Pipeline

> Every bug, fix, experiment, and lesson learned — in plain language, in order.

---

## 2026-06-27 - Cost Evaluation Showed Fake Savings

**Problem**
The cost agent reported very low planned costs (€1,074) and high savings (€65), even though the plan was clearly understaffed. The numbers didn't match reality at all.

**Cause**
The cost evaluation was comparing the plan for a *future* week against *last week's* actuals. Since the dates didn't match, the scoring function returned nothing, and the system fell back to made-up cost numbers.

**Solution**
Replaced the broken date-matching approach with a Monte Carlo simulation. Instead of comparing against specific dates, we now sample from the full history of actual demand to estimate what the plan would cost on average.

**Result**
✅ Cost estimates moved from €1K to €12K range — the right order of magnitude compared to real costs (€14–17K).

**Lesson**
When planning for a future week, you can't score against actuals that don't exist yet. Simulate instead.

---

## 2026-06-27 - Monte Carlo Sampled Errors Instead of Actual Demand

**Problem**
After the first Monte Carlo fix, the simulation still massively underestimated costs. It thought understaffing penalties would be near zero, when in reality they were huge.

**Cause**
The simulation sampled *error deviations* centered around zero, then subtracted them from the plan. This assumed actuals would be close to whatever we planned — which is wrong when the plan is 30% below real demand.

**Solution**
Changed the Monte Carlo to sample *actual historical demand values* directly (e.g., 53, 57, 48 person-days), rather than error deviations.

**Result**
✅ Monte Carlo estimates now align with real costs. Plan cost estimate went from €1K to €12K (real was €17K — close enough for decision-making).

**Lesson**
When simulating costs, sample the thing you're uncertain about (demand), not a derived quantity (errors). Errors centered at zero will always make your plan look perfect.

---

## 2026-06-28 - Cost Agent's Newsvendor Offset Was Double-Counting the Correction

**Problem**
The pipeline's plan was 237.8 person-days for the week, but actual need was 275.2. We were 13.6% under, triggering SLA penalties every day. The plan was actually *worse* than the raw optimiser.

**Cause**
The Cost agent computed its newsvendor offset using *raw optimiser errors* (rec - actual ≈ +10-14 pd per day). But the Planning agent had already corrected for this bias (336 → 262 pd). So the Cost agent was correcting a second time, shaving off another 5 pd/day on top of an already-corrected plan.

Think of it like this:
- Optimiser says "67 people"
- Planning agent correctly says "actually ~53" (close to real need)
- Cost agent sees the old +14 error and says "cut 5 more → 48" (now too low)

**Solution**
Changed the offset calculation to use *residual errors* — the difference between what the corrected plan would have been and what actually happened. After bias correction, these residuals average near zero (+0.1 pd), so the optimal offset is now just -0.4 pd/day instead of -5.0.

**Result**
✅ Fixed. Plan went from 237.8 pd to 259.4 pd (much closer to 275.2 actual).
- Plan cost: €5,114 (was €17,484 with the bug)
- Savings vs raw optimiser: 63% (was negative — we were losing money before)

**Other Things We Tried**
- Looked at widening the offset search range — wouldn't help because the input errors were wrong, not the search range.
- Considered removing the Cost agent's offset entirely — would work but loses the newsvendor optimization benefit.

**Lesson**
When you have a multi-stage correction pipeline, each stage must work on the *residual* from the previous stage, not the original raw data. Otherwise you double-count corrections.

---

## 2026-06-28 - Planning Agent Wasn't Passing DoW Factors to Cost Agent

**Problem**
The Cost agent needed to reconstruct what the corrected plan would have been for historical days (to compute residual errors). It read `dow_factors` from the Planning agent's audit log, but the field was missing.

**Cause**
The Planning agent's audit_log entry included `bias_factor` and `newsvendor` but forgot to include `dow_factors`. The Cost agent fell back to an empty dict, meaning it used only the flat bias factor for every day instead of per-weekday factors.

**Solution**
Added `dow_factors` to the Planning agent's `correction_params` in the audit_log.

**Result**
✅ Cost agent now accurately reconstructs the corrected plan for each historical day.

**Lesson**
When agents pass data through shared state (audit_log), make sure all required fields are included. Silent fallbacks to defaults can hide bugs.

---

## 2026-06-28 - Full Agent Audit (All Clear)

**Problem**
Needed to verify every agent's calculations were correct before proceeding.

**What We Checked**
- **Forecast agent** — MAPE/bias for picks, outbound, inbound. DoW volume patterns. Intra-week CV. Admin=8 validation. ✅ All correct.
- **Knowledge agent** — Claude validates planner notes against data evidence. Proper JSON parsing with truncation recovery. Stale notes filtered. ✅ Correct.
- **Regime agent** — Bayesian changepoint detection on error ratios. Detects Sep 15 picking shift. ✅ Correct.
- **Planning agent** — Bias factor → DoW factors → regime adjustment → newsvendor offset → claimed_effect constraints → Red Team re-plan boosts. ✅ Correct.
- **Cost agent** — Now uses residual errors for offset, demand sampling for evaluation. ✅ Fixed and correct.
- **Red Team agent** — Claude identifies failure scenarios, stress-tests with probability × cost. Fragile days feed back to re-plan. ✅ Correct.
- **Debrief agent** — Pulls Monte Carlo cost evaluation, generates Claude report. ✅ Correct.
- **Stats modules** (bias_correction, dow_adjustment, corrections.py) — All use `mean_actual / mean_rec` ratio correctly. ✅ Correct.

**Key Numbers After Fix**
| Metric | Value |
|---|---|
| Raw optimiser | 336.0 pd (+60.8 over actual) |
| Our plan | 259.4 pd (-15.8 under actual) |
| Actual need | 275.2 pd |
| Plan cost | €5,114 |
| Baseline cost | €13,972 |
| Savings | 63% |

**Lesson**
A flat ~17% trim gets you 86% of the way (per the challenge README). Our pipeline does ~22% trim with per-day nuance and gets 63% cost savings. The remaining gap is the irreducible noise in daily demand — you can't predict whether Tuesday needs 57 or 51 people.

---

## 2026-06-27 - Built 12-Phase Research Analysis Report

**Problem**
Needed a comprehensive, evidence-based research analysis of the warehouse staffing dataset — not just code and numbers, but academic grounding, consulting frameworks, case studies, and an executive summary.

**Solution**
Built a single `analysis.py` script that was rewritten phase-by-phase to generate a cumulative markdown report (`analysis_report.md`). Each run appended new sections:
- **Phase 1–2:** Dataset understanding + deep data analysis (descriptive stats, error decomposition, correlations, cost simulation)
- **Phase 3–5:** Academic literature (5 papers), consulting reports (McKinsey/Deloitte/Gartner/PwC/BCG), case studies (Amazon/DHL/Ocado/Kuehne+Nagel)
- **Phase 6–12:** Evidence synthesis, recommendations, alternative strategies, explainability, gap analysis, confidence scoring, executive summary

**Result**
✅ 720-line markdown report covering all 12 phases. Key findings confirmed by multiple evidence sources:
- Optimiser overstaffs 100% of days by +19.5% (systematic, not noise)
- Volume forecasts are accurate — the rate card is the problem
- Wednesday dip (~4 person-days), pick-by-light regime shift (~27%), autumn ramp (~13%)
- Three alternative strategies costed: flat trim, DoW-adjusted, full compound model

**What Worked**
- Rewriting one file per phase kept things simple and avoided dependency sprawl
- Cross-referencing data findings against academic papers caught real patterns (e.g., newsvendor critical ratio validates the "cut toward truth" guidance)

**What Didn't Work**
- First attempt tried running multiple separate scripts — got messy. Consolidated to one rewritable file.
- User had to cancel a few long-running executions before settling on the single-file approach.

**Lesson**
For iterative analysis, a single script that appends to a cumulative report is cleaner than multiple scripts. Each phase builds on the previous one's data loads, so sharing state within one file avoids redundant I/O.

---

## 2026-06-28 - Added Universal Framework & Phase 0

**Problem**
The 12-phase report was excellent but dataset-specific. Needed to make the analysis pipeline **domain-agnostic** — applicable to any structured dataset, not just warehouse staffing.

**Solution**
Added 7 new sections to `analysis_report.md`:
1. **Phase 0 — Universal Dataset Adaptation:** Auto-inferred dataset type, domain, target variable, stakeholders, applicable methods. Mapped 6 analogous domains (retail inventory, hospital staffing, energy trading, manufacturing, call centres, marketing).
2. **Universal Analysis Framework (5 modules):** Data Understanding, Data Quality, Exploratory Analysis (auto-selected methods), Statistical Analysis (with applicability notes), ML Recommendations (with fit/interpretability ratings).
3. **Universal Research Mapping:** Retrieved papers by structural analogy, not just keywords — e.g., newsvendor from inventory, changepoint from signal processing.
4. **Reusable Decision Framework:** 7-step decision tree applicable to any plan-vs-actual problem.
5. **Execution Planner:** 7-phase plan (Data Collection → Monitoring) with status tracking.
6. **Knowledge Transfer:** Separated generalisable patterns (5) from dataset-specific findings (4). Listed reusable feature engineering, statistical tests, and 6 common pitfalls.
7. **Adaptive Reasoning Rules:** Self-documenting 8-step reasoning trace.

**Result**
✅ Report grew from 720 to 997 lines. Framework is genuinely reusable — the decision tree and module structure work for any domain with plan-vs-actual feedback and asymmetric costs.

**What Worked**
- Writing the new sections in a separate temp script (`phase0_append.py`) and appending to the existing report — avoided re-running all 12 phases
- Mapping by structural analogy (not keywords) found relevant research from healthcare, energy, and revenue management that pure "warehouse staffing" searches would miss

**What Didn't Work**
- First attempt tried to edit `analysis.py` with a single massive replacement (~500 lines). The edit timed out. Split into a separate script to stay under limits.

**Lesson**
When appending large sections to a report, use a dedicated append script rather than rewriting the entire main script. Also: research mapping by structural analogy ("what's the same shape of problem?") is more powerful than keyword search ("warehouse staffing optimization").

---

## 2026-06-28 - Key Analytical Findings Summary

**Problem**
Consolidating the most important findings for quick reference.

**Key Findings (confirmed across data + literature + consulting)**
1. **Optimiser overstaffs every single day** — +10.4 person-days (+19.5%). Not noise, pure systematic bias from a stale rate card.
2. **Volume forecasts are accurate** (±1–2%) — the rate card (volume → person-days conversion) is the root cause, not demand forecasting.
3. **Wednesday consistently needs ~4 fewer person-days** — strong DoW pattern the optimiser ignores.
4. **Pick-by-light (Aug 24) reduced picking needs ~27%** — optimiser didn't adjust, widening the gap.
5. **Autumn ramp is real** — October needs ~13% more than the summer trough, but only 2 data points confirm it.
6. **Planner notes are ~55% helpful, ~30% harmful** — must be validated against data, not blindly trusted. L08 vs L09 contradiction resolved by data in L08's favour.

**Experiments & Cost Results**
| Strategy | Training Cost | Savings vs Baseline |
|---|---|---|
| Baseline (raw optimiser) | ~€234K | 0% |
| A: Flat −16% trim | Lower | ~85% gap closed |
| B: DoW-adjusted trim | Lower still | ~90% gap closed |
| C: Full compound (DoW + picking + newsvendor) | Lowest | ~95% gap closed |

**Lesson**
The first 85% of improvement comes from one simple insight (the optimiser is biased — just trim it). The next 10% comes from patterns (DoW, regime changes). The last 5% is where diminishing returns kick in (newsvendor tuning, seasonal adjustments). Know when to stop optimising.

---

## 2026-06-28 — UI redesign to paretos design system

**Problem**
The dashboard used a dark-themed UI (Inter font, teal/coral accents, dark mode toggle) that didn't match the paretos brand.

**Cause**
The original dashboard was built with a generic dark dev-tool aesthetic. The paretos design system requires a sober monochrome look: white surfaces, black primary actions, #CCC borders, Aeonik Pro typography, and the magenta-amber gradient used only on the brand mark.

**Solution**
Rewrote the entire CSS layer while keeping all JavaScript untouched:
- Replaced all CSS variables: dark surfaces to white, teal to violet (selection), coral to semantic red
- Fonts: Inter to Aeonik Pro (with Roboto/Helvetica fallback), JetBrains Mono to Consolas
- Topbar: 44px to 60px with gradient logo box (60x60) containing arch SVG in white
- Cards/KPIs: borders only (no shadows), 7px radius, white backgrounds
- Buttons: primary = black bg, reject = bordered white (no colored buttons)
- Removed dark mode toggle entirely (spec says no dark mode)
- Removed all emoji from buttons and text (spec says never)
- Tabs: active = black underline (not teal)
- Added prefers-reduced-motion support
- Backdrop: solid rgba(0,0,0,0.4) with no blur

**Result**
Dashboard now matches the paretos design system. All functionality preserved.

**Other Things We Tried**
N/A — direct CSS/HTML-only rewrite following the spec.

**Lesson**
When a design system spec exists, treat it as a checklist. Map each token to CSS variables first, then update components. Keeping JS untouched guarantees zero functional regressions.

---

## 28 Jun 2025 — KPI Tooltip System

**Problem**
The dashboard KPI metric cards showed values but gave no context — a planner couldn't tell what "Gap Closure 43.5%" means, why it's that value, or how to act on it.

**Cause**
The `kpi()` JS helper only rendered label, value, and subtitle. No tooltip parameter or UI affordance existed.

**Solution**
1. Added a `tip` parameter to the `kpi()` function that renders a `<span class="kpi-tip">?</span>` with a `data-tip` attribute.
2. Added CSS-only tooltip using `::after` pseudo-element — dark background, 280px width, appears on hover above the ? icon.
3. Changed `.kpi` overflow from `hidden` to `visible` so tooltips render outside the card, and added border-radius to the `::before` accent bar to prevent visual bleed.
4. Wrote contextual tooltips for all 17 KPI cards across Results (12) and Marketplace (4) and Errors (1). Each tooltip explains: what the metric means, why it has this value for our data, and how to use it for decision-making.

**Result**
Every KPI card now has a small ? icon next to the label. Hovering shows a rich tooltip with domain-specific guidance. No functionality changed.

**Other Things We Tried**
N/A — pure CSS tooltip approach worked on first attempt.

**Lesson**
CSS-only tooltips with `data-tip` + `::after` are simpler than JS-powered ones and don't require event listeners. The key gotcha is `overflow:hidden` on parent elements clipping the tooltip — fix with `overflow:visible` and add border-radius to any `::before`/`::after` decorations that previously relied on clipping.

---

## 2026-06-28 — Full Codebase Architecture Audit

**Problem**
Needed a comprehensive audit of every source file, dependency, and cross-reference before proceeding with further development.

**What We Found**

1. **LLM provider mismatch:** `config.py` defined `openai_api_key` and defaulted to `gpt-4o`/`gpt-4o-mini`, but `llm.py` exclusively uses the Anthropic SDK with Claude. `.env.example` also listed OpenAI models as defaults.
2. **Missing direct dependencies:** `pyproject.toml` didn't list `anthropic` (imported directly by `llm.py`), `websockets` (imported by `trace_server.py`), or `fastapi`/`uvicorn` (imported by `paretos_marketplace/api.py`).
3. **`debug_trace.py`** is a standalone debugging script at the repo root — useful but not referenced by any module. Not a bug, just a loose file.
4. **All modules well-connected:** Every module (`paretos_core`, `paretos_stats`, `paretos_eval`, `paretos_pipeline`, `paretos_agents`, `paretos_marketplace`) is imported and used by at least one other module. No dead modules.

**Solution**
- Changed `config.py`: `openai_api_key` → `anthropic_api_key`, model defaults → `claude-sonnet-4-6`
- Changed `.env.example`: Anthropic key first, OpenAI commented out, model defaults → Claude
- Added to `pyproject.toml` agents group: `anthropic>=0.34`, `websockets>=12.0`
- Added new `marketplace` optional group: `fastapi>=0.110`, `uvicorn>=0.29`

**Result**
Config, dependencies, and `.env.example` now match what the code actually uses. No functional changes — just alignment.

**Lesson**
When a codebase evolves (e.g., switching from OpenAI to Anthropic), config files and dependency manifests can get out of sync with the actual imports. A full cross-reference audit catches these silently broken assumptions before they cause runtime errors.

---
