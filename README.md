# Sahasranshu Risk Copilot

A risk, fraud and regulatory intelligence copilot on Snowflake, built with Cortex Code (CoCo) CLI for the Snowflake CoCo CLI Hackathon 2026, problem statement #01.

**The demo scenario.** A community bank has just acquired another bank. It now runs two core systems, its alert volume has jumped, and the compliance team must answer the regulator with evidence. The copilot unifies both cores, ranks the risk, and drafts audit-ready output with citations.

> **All data in this repository is synthetic.** Kestrel Valley Bank, Pellbrook Savings Bank and every person in the data are fictional. Tax IDs are random tokens, never SSN-shaped values. No real or client data may be added.

## Status

| Feature | Status |
| --- | --- |
| F1 Synthetic two-core bank generator | **Done**: 50,000 customer records, 80,000 accounts, 20,000 loans, 2.07M transactions, 1,502 alerts, 2,873 investigator notes, 2,541 KYC summaries, BSA policy PDF, ground truth |
| F2 Canonical model + entity resolution | **Silver done and measured locally** (see results); Gold canonical tables next |
| F3 Semantic view | Spec and 15 golden questions with expected answers ready (`docs/spec.md`) |
| F4 Risk engine | Rules and weights in `config/bank_demo.yaml`; expected reason codes in ground truth |
| F5 Document search | Notes, KYC summaries and the policy PDF generated; page index recorded for citations |
| F6 Agent, F7 Outputs, F8 App, F9 CoCo skill | Not started (Friday-Saturday). F9 test fixture (Core C) and target mapping format ready |

## Setup (8 commands)

```bash
git clone <repo-url> sahasranshu-risk-copilot && cd sahasranshu-risk-copilot
pip install -r requirements.txt
python -m data_gen.generate                        # about 65 s; writes data/out/demo (58 MB)
python -m pytest tests -q                          # 26 acceptance tests, about 15 s
python scripts/local_duckdb.py --data data/out/demo # optional pre-flight of the Silver SQL on DuckDB
snow connection add                                # once: your Snowflake trial account
scripts/load_to_snowflake.sh --setup --with-eval   # roles, warehouse, stage, Bronze load, reconciliation
snow sql -f sql/00_setup/90_capability_check.sql   # confirms Cortex features in your region
```

Then build Silver in order: `20_reference.sql`, `21_customer_std.sql`, `22_match_candidates.sql`, `23_party_resolution.sql`, `24_dq_exceptions.sql` (each with `snow sql -f`).

The same profile and seed always produce byte-identical files; `data/out/demo/manifest.json` lists a SHA-256 for every file.

## Results so far

These were measured on DuckDB running the same Silver SQL through `scripts/local_duckdb.py`. **They have not yet been measured in Snowflake**, and the matching assertions must be re-run there.

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
sql/00_setup/              roles, warehouse, schemas, stage, file format, capability check
sql/10_bronze/             Bronze tables and COPY (generated from data_gen/schemas.py), load reconciliation
sql/20_silver/             standardisation, entity resolution, review queue, data-quality exceptions (F2)
sql/30_gold/               canonical banking model (next)
semantic/ risk/ search/ agent/ outputs/ app/   F3-F8 (next)
coco_skills/onboard_core/  custom CoCo skill (F9)
scripts/                   Bronze SQL generator, Snowflake loader, local DuckDB pre-flight
tests/                     acceptance tests; tests/results/ holds measured results
docs/                      one-page spec, CoCo usage log
```

## Known limits

- The Silver SQL is written for Snowflake but so far has only run on DuckDB through a translation layer. Snowflake's `JAROWINKLER_SIMILARITY` returns an integer, so borderline scores may round differently.
- The matcher uses a standard nickname dictionary. The generator draws nickname variations from the same list, which flatters recall on nickname cases. Real deployments should use a larger dictionary.
- Balances are a single as-of snapshot; there is no history table yet.
- The capital figure is a configured input, because the synthetic data has no balance sheet.
- Regulatory references in the policy PDF are summaries for a demonstration, not legal advice.
