# Demo video script (about 5 minutes)

*All data is synthetic. Kestrel Valley Bank and Pellbrook Savings Bank are fictional.*

Before recording: run `scripts\build_all.ps1 -SkipLoad` (or the full build) and confirm the three checks pass, then `streamlit run app/streamlit_app.py`. Delete any draft cases you made while rehearsing, or use a fresh author name.

| Time | Screen | Show | Say |
| --- | --- | --- | --- |
| 0:00 | Title / Executive overview | The overview KPIs | "Kestrel Valley Bank has just acquired Pellbrook. Two core systems, alerts up, and the regulator wants evidence. This copilot runs entirely on Snowflake with no AI: plain SQL, written rules and reviewed templates, so every answer is repeatable and traceable." |
| 0:30 | Executive overview | Open "G03 Alerts in August" to its source rows | "Every figure opens to the rows behind it, with the source file and row number." |
| 1:00 | Data integration health | Match results, review queue, DQ exceptions | "50,000 customer records across both cores. 3,948 duplicates linked automatically with zero false merges; the uncertain ones go to a review queue. Every injected data-quality issue is found." |
| 1:45 | Alert queue & customer | The ranked queue; open the top customer | "The risk engine is eight rules you can read. All 25 cross-core structurers rank in the top 25 of 472, and neither legacy system alerted on any of them, because each core only saw half the cash." |
| 2:30 | Customer view | Reason codes and evidence sentences for Deborah Sanford | "Each reason has evidence: amounts, dates, and the policy it breaks, cash in both cores on the same day, over $10,000, with no CTR." |
| 3:00 | Ask & cases | Ask the D01 question, then the D04 policy question | "Questions go to reviewed SQL or keyword search. The answer shows which rule routed it and cites policy section 4.2, page 3. If it isn't sure, it says so instead of guessing." |
| 3:45 | Ask & cases | Draft the narrative, try to approve as the author (blocked), approve as a second person, download the PDF | "The narrative is built from a frozen evidence snapshot. The author cannot approve their own case. Once approved, the PDF drops its DRAFT watermark." |
| 4:20 | Terminal | `python scripts/case.py verify ...` | "Any approved case reproduces byte for byte from its audit record, and any change to the stored text is caught." |
| 4:40 | Terminal | `python -m onboarding.onboard ...` on Core C, then the DQ table in Snowflake | "A third core we had never seen: the onboarding tool profiles it, maps it and writes the SQL. 297 of 300 customers linked with no false links, and its data-quality tests flag the unmapped 'card' channel for review." |
| 5:00 | Close | README results table | "Measured on holdout data, synthetic throughout, rebuilt with one command." |
