# outputs: audit-ready case narratives with four-eyes approval (F7), without AI

| Part | File | What it does |
| --- | --- | --- |
| Evidence | `outputs/narrative.py:gather_evidence` | Freezes every fact the narrative uses: customer, risk signals, cash deposits in the review window, large outflows after them, KYC, legacy alerts, thresholds, policy pages |
| Template | `outputs/templates/reasons.yaml` + `render_narrative` | One reviewed paragraph per risk rule, each tied to a policy section. Page numbers are looked up from `SEARCH.POLICY_CHUNK`, never typed |
| Store and approval | `outputs/case_store.py`, `sql/70_outputs/70_case_output.sql` | `AUDIT.CASE_OUTPUT` (text, frozen evidence, SHA-256 of both), `AUDIT.CASE_APPROVAL`, `AUDIT.V_CASE_STATUS` |
| Export | `outputs/export_pdf.py` | PDF with a "DRAFT - NOT APPROVED" watermark until approved; footer carries the output id and text fingerprint |
| Command | `scripts/case.py` | `draft`, `list`, `show`, `approve`, `reject`, `export`, `verify` |

Rules from `config/bank_demo.yaml` (`report`): no output is final without an approval, and the author can never approve their own output (checked ignoring case and spaces). An approval records the fingerprint of the exact text approved; tampered text is refused.

## Results

| Measure | Result |
| --- | --- |
| D05 narrative for the highest-risk customer states every expected fact | Pass: Deborah Sanford; Core A $28,810.00 in 3 deposits, Core B $29,160.00 in 4; each deposit under $10,000; each core under its $30,000 legacy rule; same-day cash on 2026-08-10 with no CTR; wire of $48,299.60 to Silverline Holdings on 2026-08-27; KYC expected cash; both cores |
| Every policy citation has the right page | Pass (checked against `SEARCH.POLICY_CHUNK`) |
| Output reproduces from its audit record (build-plan bar) | Pass: re-rendered text, stored text and stored evidence all match their fingerprints |
| Author approving own output; second decision; edited text | All refused |

Found by the tests and fixed: `reproduce` first compared the re-rendered text only with the stored fingerprint, so an edit to the stored text went unnoticed. It now checks the stored text too.
