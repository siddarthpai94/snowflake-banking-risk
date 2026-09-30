# Design decisions

*As of 30 Sep 2026. All data is synthetic.*

## 1. No AI, and no Cortex Code (CoCo)

**Decision.** The copilot uses no AI of any kind: no Cortex AI functions, no Cortex Analyst, Cortex Search or Cortex Agents, no LLM calls, and CoCo was not used to write it. Every answer comes from plain SQL, written rules, reviewed templates and keyword scoring.

**Why.**
- The project sponsor (CEO) asked for the copilot to be built without AI or CoCo.
- The trial account cannot use them anyway. `AI_COMPLETE` returned error 399258 on this trial, and Cortex Code stopped at sign-in with "Cortex Code is not enabled" for the account.
- For a compliance tool, determinism is a feature. The same question gives the same answer, every figure traces to source rows, and a reviewer can read every rule.

**What replaced each AI component in the build plan.**

| Build plan | Built instead | Where |
| --- | --- | --- |
| Cortex Analyst (F3) | Metric views plus a catalogue of 18 reviewed questions with fixed SQL; a keyword matcher picks the question and refuses when unsure | `sql/40_semantic/`, `semantic/` |
| Risk scoring (F4) | 8 transparent SQL rules with weights from `config/bank_demo.yaml` | `sql/30_gold/32_risk_engine.sql` |
| Cortex Search (F5) | BM25 keyword scoring in plain SQL, with a citation on every hit | `sql/50_search/`, `search/` |
| Cortex Agent (F6) | A rule-based router; every answer names the rule that chose its route | `agent/router.py` |
| LLM case narrative (F7) | Reviewed sentence templates filled from a frozen evidence snapshot; SHA-256 fingerprints; four-eyes approval | `outputs/` |
| CoCo onboarding skill (F9) | A rule-based profiler and mapper that writes Bronze, canonical and data-quality SQL for a new core | `onboarding/` |

**What it costs.** The question matcher only answers questions in the catalogue (19 of 20 unseen rewordings matched; the miss is refused, not answered wrongly). Search finds words, not meaning (10 of 12 policy questions correct first time). Narratives read as templates. These limits are measured on holdout data and stated, not hidden.

## 2. Honest evaluation

Rules were tuned on a small dev dataset (seed 7) and on tuning sets of questions. Results are reported on a holdout dataset (seed 20261015) and holdout question sets that no rule was tuned on. Where a rule was changed after looking at the demo data, the README says so.

## 3. Synthetic data only

No real or client data is used or may be added. Tax IDs are random tokens, never SSN-shaped. Ground truth sits in the EVAL schema, which the app and analyst roles cannot read.

## 4. Snowflake-native where the trial allows

Silver, Gold, the risk engine, metric views, the question catalogue, search and the audit tables are all dynamic tables, views or tables in Snowflake. Two steps run locally because the Snowflake feature they would use is AI: policy PDF extraction (pypdf) and the F9 profiler. Both write plain SQL that is then run in Snowflake.

## 5. One-command rebuild

`scripts/build_all.ps1` (Windows) and `scripts/build_all.sh` load Bronze, run every build step in order and finish with the three acceptance checks, stopping at the first error.
