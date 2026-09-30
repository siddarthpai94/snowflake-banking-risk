# One-page spec: Sahasranshu Risk Copilot

*As of 30 Sep 2026. All data is synthetic; every institution and person is fictional.*

**Scenario.** Kestrel Valley Bank (Core A) acquired Pellbrook Savings Bank (Core B) on 30 Jun 2026. Both cores still run, but they are one legal entity for BSA purposes. The same customer can hold accounts in both cores under different IDs, so cash that looks ordinary in each core can add up to structuring once the cores are joined.

## Canonical data model

Bronze keeps each file as delivered, plus `_SOURCE_FILE` and `_SOURCE_ROW`. Silver standardises and resolves identities. Gold is the canonical model the semantic view, the risk engine and the app read. History is a single as-of snapshot (31 Aug 2026) for the hackathon; SCD2 comes later.

| Entity (Gold) | Key | Built from | Notes |
| --- | --- | --- | --- |
| `party` | `party_id` (`PTY_` + 16 hex) | `SILVER.PARTY_XREF` | One per resolved real customer; people and organisations |
| `party_source_record` | `record_id` (`core:key`) | `SILVER.PARTY_XREF` | Links every source record to its party with link status, score and reasons |
| `household` | `household_id` | standardised address | People at the same normalised street address and ZIP |
| `account` | `account_id` (`core:key`) | Bronze accounts + mapping | `CHECKING`, `SAVINGS`, `MONEY_MARKET`, `CERTIFICATE`; status `OPEN`/`DORMANT`/`CLOSED`; dormant and reactivation dates |
| `loan` | `loan_id` (`core:key`) | Bronze loans + mapping | Canonical loan type, CRE category, owner-occupied flag, days past due |
| `transaction` | `txn_id` (`core:key`) | Bronze transactions + mapping | Canonical type, signed amount, channel, branch, CTR flag, counterparty |
| `alert` | `alert_id` (`core:key`) | both legacy monitoring systems | Canonical scenario, status, disposition, dates, owner |
| `branch` | `branch_id` (`core:code`) | branch files | 12 Core A and 6 Core B branches |
| `dq_exception` | rule + record | `SILVER.DQ_EXCEPTIONS` | Missing or future DOB, invalid ZIP, duplicate key, orphan account |

The column-level mappings are in `config/mappings/core_a.yaml` and `core_b.yaml`. They are also the target format for the F9 onboarding skill.

**Identity rules** (`sql/20_silver/22_match_candidates.sql`). Different non-null tax-id tokens always reject; the same token plus the same DOB auto-links. Without a token, name plus DOB must be corroborated by address or phone to auto-link, and everything weaker goes to the review queue. Links are 1:1 and mutual-best, so a weak pair can never chain two people together.

## Injected patterns (exact counts in the demo dataset)

| Pattern | Count | What the demo must show |
| --- | --- | --- |
| Cross-core structuring | 25 people | $51k-$58.5k cash in 30 days split across both cores; each deposit under $10k; each core under its $30k legacy rule; no legacy alert |
| Missed CTR aggregation | 8 of the 25 | Same-day cash in both cores over $10k, with no CTR |
| KYC conflict across cores | 10 of the 25 | Occupation differs between the two cores' KYC files |
| Single-core structuring | 15 | Visible to one legacy system; an open legacy alert exists |
| Cash-intensive businesses (legitimate) | 10 | $65k-$95k cash a month, CTRs filed; KYC explains it |
| Rapid in-out | 30 accounts | $40k-$150k in, 90-98% out within 48 hours; 10 have legacy alerts |
| Dormant reactivation | 40 accounts | Dormant over a year, then a $15k-$60k inflow emptied within 10 days |
| Duplicate identities | 4,000 (8% of records) | 3,300 clean, 550 variant (nickname, typo, moved), 150 hard (no token in Core B) |
| Look-alike different people | 150 pairs | Jr/Sr, twins, same name and DOB; 40 have no token in Core B; must never merge |
| Data-quality issues | 440 | 250 missing DOB, 20 future DOB, 120 invalid ZIP, 10 duplicate account keys, 40 orphan accounts |

Ground truth for all of these is in `ground_truth/`, which is loaded only into the `EVAL` schema and never shown to the app or the agent.

## 15 golden questions (F3; target: at least 13 correct through Cortex Analyst)

Expected answers and metric definitions are in `ground_truth/golden_answers.json`. The values below are for the demo dataset (seed 20260930).

| ID | Question | Expected answer |
| --- | --- | --- |
| G01 | How many customer records does each core hold? | Core A 32,000; Core B 18,000 |
| G02 | How many unique customers across both cores after matching? | 46,000 true (tolerance 0.5%) |
| G03 | How many AML alerts in August 2026? | 293 |
| G04 | False-positive rate for alerts closed in Q2 2026? | 89.5% (657 of 734) |
| G05 | Top three branches by alerts in the last 90 days? | Pellbrook Downtown 56, Wrenfield 56, A04 54 |
| G06 | Alerts open more than 30 days after they were raised? | 69 (of 246 open) |
| G07 | Cash deposits across both cores, August 2026? | $13,317,811.79 |
| G08 | Cash and ATM withdrawals, August 2026? | $6,687,362.27 |
| G09 | Loan-to-deposit ratio at 31 Aug 2026? | 66.2% |
| G10 | Non-owner-occupied CRE as % of total risk-based capital? | 198.9% ($527.0M / $265.0M) |
| G11 | Deposit balances by core? | Core A $1,896.9M; Core B $970.1M |
| G12 | Dormant accounts at 31 Aug 2026? | 500 |
| G13 | Top five customers by cash deposited in the last 30 days? | Five cash-intensive businesses led by Harrison Family Restaurant LLC ($109,107.02) |
| G14 | Average days to close alerts closed in Q2 2026? | 15.3 |
| G15 | Loans 90+ days past due and their principal? | 85 loans, $6,994,765.60 |

## 5 demo questions (F6; target: correct three runs in a row)

| ID | Question | Expected answer |
| --- | --- | --- |
| D01 | Which customers moved more than $50k in cash across both cores in 30 days, and what do their KYC files say? | 35 customers: the 25 structurers, whose KYC expects little cash, and 10 businesses whose KYC expects it |
| D02 | On which days did a customer's cash across both cores exceed $10,000 with no CTR? | 8 person-days |
| D03 | Which alerts should my team work first today, and why? | All 25 cross-core structurers in the top 10% of the queue, each with three or more reason codes |
| D04 | What does our BSA policy say about aggregating cash across the two cores? | Policy section 4.2 Aggregation, page 3 |
| D05 | Draft a case narrative for the highest-risk customer in the queue. | Deborah Sanford: $28,810 in Core A and $29,160 in Core B, one same-day cross-core day with no CTR, then a $48,299.60 wire out |

## Metric definitions used by the answers

- **False-positive rate:** alerts closed with disposition false positive, divided by all alerts closed in the period.
- **Loan-to-deposit:** outstanding principal over balances of open and dormant deposit accounts.
- **CRE concentration:** CRE loans not flagged owner-occupied (including construction and multifamily) over total risk-based capital from `config/bank_demo.yaml`.
- **Cross-core cash:** cash deposits per resolved person across both cores in the 30 days to the as-of date.
- **Missed CTR aggregation:** same person, same business day, cash deposits in both cores totalling over $10,000, with no CTR flag in either core.
