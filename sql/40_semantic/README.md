# semantic: governed questions without AI (F3)

The build plan used Cortex Analyst for F3. The trial account cannot use Cortex AI and the decision is to build without AI, so F3 is three plain parts:

| Part | File | What it does |
| --- | --- | --- |
| Metric views | `sql/40_semantic/40_metric_views.sql` | `SEMANTIC.V_ALERT`, `V_DEPOSIT`, `V_LOAN`, `V_CASH`, `V_CUSTOMER_RECORD`, `V_AS_OF`. One definition per metric; the glossary is `SEMANTIC.METRIC_DEFINITION` |
| Question catalogue | `semantic/questions.yaml` -> `sql/40_semantic/41_question_catalog.sql` | The 15 golden questions and demo questions D01-D03, each with reviewed SQL, a one-line headline and checks against ground truth |
| Matcher | `semantic/matcher.py` | Maps a typed question to the catalogue by rarity-weighted keyword overlap. When it is not confident it shows the three closest questions instead of guessing |

Try it: `python scripts/ask.py "how many alerts did we get last month"` (runs on Snowflake through `snow sql`), or `python scripts/ask.py --list`.

## Results

| Measure | Result |
| --- | --- |
| Golden questions answered correctly (bar in build plan: 13 of 15) | **15 of 15** on the demo, holdout and small datasets |
| Demo questions D01-D03 correct | 3 of 3 (35 customers, 25 unexplained by KYC; 8 missed-CTR days; Deborah Sanford first) |
| Matcher, tuning rewordings (57) | 57 of 57 (was 48 of 57 before fixing three bugs: punctuation, stemming, filler words) |
| Matcher, holdout rewordings never used for tuning (20) | **19 of 20**; the miss was "not confident", so the user is asked to pick. No confident wrong answers |

Limits: only questions in the catalogue can be answered. A new question needs new reviewed SQL (a pull request to `questions.yaml`), which is deliberate for a regulated setting. Dates in the catalogue are the demo's as-of month (August 2026).

To add a question: add an entry to `questions.yaml`, run `python scripts/emit_question_catalog.py`, then `snow sql -c default -f sql/40_semantic/41_question_catalog.sql`.
