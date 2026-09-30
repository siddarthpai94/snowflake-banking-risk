# risk: signal engine and ranked queue (F4, Friday)

Rules and weights live in `config/bank_demo.yaml` under `risk_rules`. Each rule returns a reason code; the weighted sum is the score. Every alert carries its top three reasons and evidence rows.

Acceptance: every `XCORE_STRUCTURING` person in `ground_truth/injected_patterns.csv.gz` ranks in the top 10% of the queue, and each has the reason codes listed in `expected_reason_codes`.
