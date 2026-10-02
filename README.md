# Sahasranshu Risk Copilot

A risk, fraud and regulatory intelligence copilot on Snowflake for the Snowflake Hackathon 2026, problem statement #01.

**Built without AI.** No Cortex AI functions, no LLMs and no Cortex Code: every answer comes from plain SQL, written rules, reviewed templates and keyword scoring, so the same question always gives the same answer and every figure traces to source rows. Why, and what replaced each AI component: [`docs/decisions.md`](docs/decisions.md).

**The demo scenario.** A community bank has just acquired another bank. It now runs two core systems, its alert volume has jumped, and the compliance team must answer the regulator with evidence. The copilot unifies both cores, ranks the risk, and drafts audit-ready output with citations.

> **All data in this repository is synthetic.** Kestrel Valley Bank, Pellbrook Savings Bank and every person in the data are fictional. Tax IDs are random tokens, never SSN-shaped values. No real or client data may be added.

## Status

| Feature | Status |
| --- | --- |
| F1 Synthetic two-core bank generator | **Done**: 50,000 customer records, 80,000 accounts, 20,000 loans, 2.07M transactions, 1,502 alerts, 2,873 investigator notes, 2,541 KYC summaries, BSA policy PDF, ground truth |
| F2 Canonical model + entity resolution | **Silver done and verified in Snowflake** (matches DuckDB exactly). **Gold built and verified in Snowflake**: all 15 golden questions answered correctly from Gold |
| F3 Governed questions (no AI) | **Built**: metric views, a catalogue of 18 reviewed questions and a keyword matcher. 15 of 15 golden questions and D01-D03 correct; matcher 19 of 20 on unseen rewordings. Try `python scripts/ask.py "how many alerts last month"` |
| F4 Risk engine | **Built** (`sql/30_gold/32_risk_engine.sql`): 8 transparent rules, weighted score, reason codes, evidence and a ranked queue. All 25 cross-core structurers rank 1-25 of 472; **F4 acceptance PASS in Snowflake** |
| F5 Document search (no AI) | **Built**: BM25 keyword search over 32 policy sections, 2,873 notes and 2,541 KYC summaries, every hit with a citation. D04 finds section 4.2, page 3; 10 of 12 policy questions correct first time. Try `python -m search.search "..."` |
| F6 Router (no AI) | **Built**: rule-based router (catalogue, search, customer view, narrative, clarify) with the rule shown on every answer and an audit log. D01-D05 correct three runs in a row. Try `python scripts/copilot.py "..."` |
| F7 Case narratives (no AI) | **Built**: narrative from a frozen evidence snapshot and reviewed templates, every claim with a policy page or source row; four-eyes approval; PDF with DRAFT watermark; reproduces byte for byte from its audit record. Try `python scripts/case.py draft --top --author you` |
| F8 App (no AI) | **Built**: Streamlit, four screens (overview, data health, queue and customer, ask and cases); every summary figure opens to its source rows in one or two clicks. Run `streamlit run app/streamlit_app.py` |
| F9 Onboard a new core (no AI) | **Built**: rule-based profiler and mapper plus a runbook. Core B and Core A from scratch agree with the hand-written mappings (100% on names, tax tokens, dates, contact details); Core C, never seen: 297 of 300 links to Core A, 0 false; generated data-quality tests find every injected issue. Try `python -m onboarding.onboard --core core_c --files data/out/demo/core_c`. See `onboarding/` |

## Setup

```bash
git clone <repo-url> sahasranshu-risk-copilot && cd sahasranshu-risk-copilot
pip install -r requirements.txt
python -m data_gen.generate                        # about 65 s; writes data/out/demo (58 MB)
python -m pytest tests -q                          # 108 acceptance tests, about 35 s
python scripts/local_duckdb.py --data data/out/demo # optional pre-flight of the Silver and Gold SQL on DuckDB
snow connection add                                # once: your Snowflake trial account
scripts/build_all.sh --setup                       # roles, warehouse, Bronze load, every build step, 3 acceptance checks
streamlit run app/streamlit_app.py                 # the app
```

On Windows PowerShell: `powershell -ExecutionPolicy Bypass -File scripts\build_all.ps1 -Setup`. The build stops at the first error; fix it and rerun with `-SkipLoad` (`--skip-load`). It ends with the matching evaluation (0 false merges), the F4 risk check (PASS) and the golden check (15 of 15).

### Signing in to the app

The app opens on a sign-in page. Three fictional demo users, all with the password `Demo@2026`:

| Username | Person | Role | Can do |
|---|---|---|---|
| `analyst` | Maya Collins, BSA analyst | Analyst | View every screen, ask questions |
| `investigator` | Daniel Ortiz, financial crimes investigator | Investigator | Also draft case narratives |
| `approver` | Sarah Whitfield, BSA officer | Approver | Also approve or reject cases, never their own |

The profile and **Sign out** are at the top right. Five wrong passwords lock that username for 30 seconds. Passwords are
stored only as salted PBKDF2-SHA256 hashes in `config/users.yaml`; make a new hash with
`python app/auth.py hash "new password"`. Roles are checked again in `outputs/case_store.py`, not just by the buttons.
This is a demo gate: in production the bank's single sign-on and Snowflake roles are the access control.

To run the app offline without Snowflake, build a local copy and point the app at it (PowerShell):

```powershell
python scripts/local_duckdb.py --data data/out/demo --db data/out/app.duckdb
$env:RISK_COPILOT_BACKEND = "duckdb:data/out/app.duckdb"
streamlit run app/streamlit_app.py
```

The steps the build runs, if you want them one at a time (`snow sql -f` each):

Silver in order: `20_reference.sql`, `21_customer_std.sql`, `22_match_candidates.sql`, `23_party_resolution.sql`, `24_dq_exceptions.sql` (each with `snow sql -f`).

Gold and the risk engine: `30_gold/30_config.sql`, `31_gold_core.sql`, `32_risk_engine.sql`. Check with `90_customer_360_proof.sql`, `91_eval_risk.sql` and `92_golden_check.sql`.

The semantic layer: `40_semantic/40_metric_views.sql` and `41_question_catalog.sql`. Ask questions with `python scripts/ask.py "..."`.

Document search: `50_search/50_policy_chunks.sql` and `51_doc_chunk.sql`. Search with `python -m search.search "..."`.

The audit log: `60_agent/60_audit.sql`. Ask anything with `python scripts/copilot.py "..."`.

Case outputs: `70_outputs/70_case_output.sql`. Draft, approve and export with `python scripts/case.py ...`.

If you change `config/bank_demo.yaml`, run `python scripts/emit_config_sql.py` and then `30_config.sql` again.

The same profile and seed always produce byte-identical files; `data/out/demo/manifest.json` lists a SHA-256 for every file.

## Results so far

The matching results below were first measured on DuckDB through `scripts/local_duckdb.py`, then **reproduced exactly in Snowflake** on the demo dataset (`sql/20_silver/90_eval_matching.sql`).

The matching rules were tuned on the small dev dataset (seed 7). They were then checked on a holdout dataset (seed 20261015) that no rule was tuned on.

| Measure | Holdout (seed 20261015) | Demo dataset (seed 20260930) |
| --- | --- | --- |
| True cross-core duplicates | 4,000 | 4,000 |
| Auto-linked, all correct | 3,959 | 3,948 |
| False merges | **0** | **0** |
| Recall before review | 98.97% | 98.70% |
| Recall after the review queue | 100% | 100% |
| Look-alike pairs merged | 0 of 150 | 0 of 150 |
| Review queue size | 89 | 93 |
| Injected data-quality issues found | 440 of 440, no false alarms | 440 of 440, no false alarms |

The F2 acceptance test in the build plan (at least 95% of duplicates matched) passes. One matching rule, a date-of-birth plus ZIP blocking key, was added after inspecting misses on the demo dataset. That is why the holdout column is the honest measure.

## Risk engine results (F4)

No AI is used. Each rule is a SQL query with thresholds from `config/bank_demo.yaml`; the score is the sum of the weights of the rules that fired, kept within 0 to 100. Every fired rule carries a sentence of evidence with amounts and dates.

| Rule | Weight | Fires when |
| --- | --- | --- |
| XCORE_CASH_30D | 35 | cash deposits in both cores total over $50,000 in the last 30 days |
| CTR_AGGREGATION_MISSED | 30 | same-day cash across both cores is over $10,000 with no CTR filed |
| RAPID_IN_OUT | 25 | at least 90% of a wire or ACH inflow of $25,000 or more leaves within 48 hours |
| NEAR_THRESHOLD_CASH | 20 | 4 or more cash deposits of $7,000 to $9,999 within any 30-day window |
| DORMANT_REACTIVATION | 20 | an account dormant over 365 days receives $10,000 or more within 30 days of reactivation |
| KYC_MISMATCH | 15 | 30-day cash is over 3 times the KYC expected monthly cash (and over $10,000) |
| KYC_INCONSISTENT_ACROSS_CORES | 10 | the two cores' KYC files give different occupations |
| KYC_CONSISTENT_CASH | -20 | mitigating: 30-day cash is within 1.5 times the KYC expected monthly cash |

The queue (`GOLD.ALERT_QUEUE`) combines open legacy alerts with new engine alerts for customers scoring 20 or more. Legacy scores count at 0.6 because they are uncalibrated. Ties are broken by the uncapped weight total, then the largest amount.

| Injected pattern | Demo (seed 20260930) | Holdout (seed 20261015) |
| --- | --- | --- |
| Cross-core structurers in the queue top 10% | **25 of 25** (ranks 1-25 of 472) | **25 of 25** (ranks 1-25 of 431) |
| Patterns firing every expected reason code | 110 of 110 | 110 of 110 |
| Single-core structurers, worst rank | 121 | 93 |
| Legitimate cash businesses in the queue | 2 of 10 (low, rank 292 or below) | 0 of 10 |
| CTR aggregation misses found (D02) | 8 of 8 | 8 of 8 |
| Top of queue matches D05 | yes (Deborah Sanford) | yes |

Rapid-movement and dormant-reactivation patterns enter the queue on one rule each, so they rank below the structurers. That is by design: they are single signals.

## How the demo question is answered

The flagship question: *"Which customers moved more than $50k in cash across both cores in 30 days, and what do their KYC files say?"* The ground truth answer is 35 customers:

- **25 structurers.** Each split $51k to $58.5k of cash across the two cores, with every deposit under $10,000 and each core under its own $30,000 legacy rule, so neither legacy system raised an alert. Their KYC files expect little or no cash. Eight had same-day cash in both cores over $10,000 with no CTR filed, which breaks the policy's cross-core aggregation rule (policy section 4.2, page 3). Ten have a different occupation in each core's KYC file.
- **10 cash-intensive businesses**, such as restaurants and laundromats, whose KYC files expect exactly this cash.

## Repository layout

```
config/bank_demo.yaml      thresholds, rule weights, matching guards (F14)
config/mappings/           Core A and Core B -> canonical mappings (target format for F9)
config/reference/          nickname dictionary used as matching evidence
data_gen/                  synthetic cores, documents and ground truth (F1)
sql/00_setup/              roles, warehouse, schemas, stage, file format, environment check
sql/10_bronze/             Bronze tables and COPY (generated from data_gen/schemas.py), load reconciliation
sql/20_silver/             standardisation, entity resolution, review queue, data-quality exceptions (F2)
sql/30_gold/               canonical banking model, config tables, risk engine and queue (F2, F4, F14)
sql/40_semantic/           metric views and question catalogue (F3)
sql/50_search/             policy sections and the searchable document table (F5)
sql/60_agent/              audit log of every question (F6)
sql/70_outputs/            case outputs and approvals (F7)
semantic/                  question catalogue and keyword matcher (F3)
search/                    policy PDF extraction and BM25 search (F5)
agent/                     rule-based router and answer builder (F6)
outputs/                   case narrative, approval store, PDF export (F7)
app/                       Streamlit app (F8)
onboarding/                new-core onboarding tool, runbook, worked examples for Core B and Core C (F9)
scripts/                   one-command build, Snowflake loader, CLIs, Bronze SQL generator, local DuckDB pre-flight
tests/                     acceptance tests; tests/results/ holds measured results
docs/                      one-page spec, design decisions (why no AI), demo video script
```

## Known limits

- Silver, Gold and the risk engine give identical results on DuckDB and Snowflake (checked on 30 Sep 2026).
- The risk engine's thresholds were set before looking at the demo data, but two changes followed inspection of the small dev dataset: near-threshold cash uses any 30-day window, and the mitigating KYC rule allows 1.5 times the expected cash. The holdout column is the honest measure.
- One ground-truth definition was aligned with the engine: the "highest-risk customer" (D05) is now chosen by configured rule weights rather than by counting reason codes. The demo answer did not change.
- The matcher uses a standard nickname dictionary. The generator draws nickname variations from the same list, which flatters recall on nickname cases. Real deployments should use a larger dictionary.
- Balances are a single as-of snapshot; there is no history table yet.
- The capital figure is a configured input, because the synthetic data has no balance sheet.
- Regulatory references in the policy PDF are summaries for a demonstration, not legal advice.
