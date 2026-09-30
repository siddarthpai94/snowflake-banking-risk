# app: Streamlit app (F8), without AI

`app/streamlit_app.py` puts the whole copilot on four screens, as in the build plan:

| Screen | What it shows | Summary to evidence rows |
| --- | --- | --- |
| Executive overview | Six headline figures (golden questions), top of the queue, customers per risk rule | Pick a figure: its source rows appear (1 click). Select a queue row, then Open (2 clicks) |
| Data integration health | Load reconciliation vs control totals, entity-resolution counts and review queue, data-quality exceptions by rule | Pick a rule: its records with source file and row (1 click) |
| Alert queue & customer | Ranked queue with filters; one customer across both cores: score, reasons, accounts, cash with source rows, KYC, alerts, notes, loans | Select a row (1 click) |
| Ask & cases | Any question, routed by rules (D01-D05 buttons); case narratives with approve / reject / verify / PDF; the audit log | - |

"You are" in the sidebar is recorded on every question, draft and approval; the author of a case cannot approve it.

## Run it

```
pip install streamlit snowflake-connector-python
streamlit run app/streamlit_app.py
```

It uses the Snowflake connection named `default` (the one `snow connection add` created), with role RISK_ADMIN. If the Python connector cannot connect, it falls back to the Snowflake CLI (slower). Offline: `RISK_COPILOT_BACKEND=duckdb:<file>` with a DuckDB file from `scripts/local_duckdb.py`.

Tests: `tests/test_f8_app.py` renders every screen headless and checks the numbers, the click-through to source rows and the four-eyes rule.
