# agent: rule-based router and answers (F6), without AI

The build plan used a Cortex Agent. Without AI, F6 is a router whose rules are readable in one file (`agent/router.py`). Every answer says which rule chose its route, and every question is written to `AUDIT.QUESTION_LOG`.

| Order | Route | Fires when | Goes to |
| --- | --- | --- | --- |
| 1 | NARRATIVE | "draft / write up / narrative" + a named customer or "highest-risk" | F7 report (customer evidence today) |
| 2 | CATALOG | data wording ("which customers", "how many", "$50k") + a confident catalogue match | F3 reviewed question |
| 3 | SEARCH | KYC-file, notes or policy wording | F5 search, with citations |
| 4 | CUSTOMER | a known customer's name appears (looked up in `GOLD.PARTY`) | customer view: profile, risk, signals, accounts, loans, KYC, alerts, notes |
| 5 | CATALOG | the keyword matcher is confident | F3 reviewed question |
| 6 | CLARIFY | nothing above | the three closest reviewed questions |

Try it: `python scripts/copilot.py "Tell me about Deborah Sanford"` (add `--no-log` to skip the audit log).

## Results

| Measure | Result |
| --- | --- |
| Five demo questions D01-D05 correct, three runs in a row (build-plan bar) | **Pass** (identical answers each run) |
| Router, 24 questions written with the rules | 24 of 24 |
| Router, 12 questions written afterwards and run once | **10 of 12**, then 12 of 12 after two general fixes (possessive names "McDaniel's"; "what are the rules for ...") |

A third fix came from the D01-D05 test: the real D01 wording ends "...and what do their KYC files say?", which the KYC-document rule caught. Rule 2 (data wording + confident catalogue match) now runs before document search.

Limits: a question the rules do not cover falls to CLARIFY, and a confident catalogue match can be wrong. The answer always names the reviewed question it used ("Answered: G12 ..."), so a wrong match is visible.
