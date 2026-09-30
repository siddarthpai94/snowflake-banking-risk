-- F4 acceptance in Snowflake: score the risk engine against the injected patterns (needs the EVAL schema).
-- Build-plan / D03 acceptance: every XCORE_STRUCTURING person ranks in the top 10% of the queue with at
-- least three of their expected reason codes. DuckDB pre-flight on the demo data: all 25 rank 1-25 of 472
-- (top 5.3%), and all 120 injected patterns fire every expected reason code.
USE ROLE RISK_ADMIN;
USE WAREHOUSE RISK_WH;
USE DATABASE RISK_COPILOT;

-- One row per injected pattern: its customer, score, best queue rank and which expected codes fired
CREATE OR REPLACE TEMPORARY TABLE EVAL.RISK_PATTERN_RESULT AS
WITH pat AS (
    SELECT g."pattern_id" AS pattern_id, g."pattern_type" AS pattern_type, g."expected_reason_codes" AS expected,
           c.value::VARCHAR AS core, SPLIT(g."customer_refs", ';')[c.index]::VARCHAR AS customer_ref
      FROM EVAL.GT_INJECTED_PATTERNS g,
           LATERAL FLATTEN(input => SPLIT(g."cores", ';')) c
),
pp AS (
    SELECT DISTINCT pat.pattern_id, pat.pattern_type, pat.expected, x.party_id
      FROM pat JOIN SILVER.PARTY_XREF x ON x.record_id = pat.core || ':' || pat.customer_ref
),
best AS (SELECT party_id, MIN(queue_rank) AS queue_rank, MAX(queue_size) AS queue_size
           FROM GOLD.ALERT_QUEUE GROUP BY party_id),
exp AS (
    SELECT pp.pattern_id, e.value::VARCHAR AS code
      FROM pp, LATERAL FLATTEN(input => SPLIT(pp.expected, ';')) e
     WHERE NOT STARTSWITH(pp.expected, 'EXPECTED_')
),
hits AS (
    SELECT e.pattern_id, COUNT(*) AS n_expected, COUNT(s.rule_code) AS n_expected_fired
      FROM exp e
      JOIN pp ON pp.pattern_id = e.pattern_id
      LEFT JOIN GOLD.RISK_SIGNAL s ON s.party_id = pp.party_id AND s.rule_code = e.code
     GROUP BY e.pattern_id
)
SELECT pp.pattern_id, pp.pattern_type, pp.party_id, pt.display_name, COALESCE(sc.risk_score, 0) AS risk_score,
       b.queue_rank, b.queue_size, ROUND(100 * b.queue_rank / b.queue_size, 1) AS queue_pct,
       h.n_expected, h.n_expected_fired, sc.top_reasons, pp.expected
  FROM pp
  LEFT JOIN GOLD.PARTY pt ON pt.party_id = pp.party_id
  LEFT JOIN GOLD.RISK_SCORE sc ON sc.party_id = pp.party_id
  LEFT JOIN best b ON b.party_id = pp.party_id
  LEFT JOIN hits h ON h.pattern_id = pp.pattern_id;

-- Summary by pattern type
SELECT pattern_type, COUNT(*) AS patterns,
       COUNT(queue_rank) AS in_queue,
       MAX(queue_rank) AS worst_rank, MAX(queue_size) AS queue_size, MAX(queue_pct) AS worst_pct,
       MIN(risk_score) AS min_score, MAX(risk_score) AS max_score,
       IFF(MAX(n_expected) IS NULL, NULL, SUM(IFF(n_expected_fired = n_expected, 1, 0))) AS all_expected_codes_fired  -- NULL: no codes expected
  FROM EVAL.RISK_PATTERN_RESULT
 GROUP BY pattern_type
 ORDER BY pattern_type;

-- The acceptance line: should read 25 | 25 | 25 | PASS on the demo data
SELECT COUNT(*) AS xcs_persons,
       SUM(IFF(queue_pct <= 10, 1, 0)) AS in_top_10_pct,
       SUM(IFF(n_expected_fired >= 3, 1, 0)) AS with_3_plus_expected_codes,
       IFF(COUNT(*) = SUM(IFF(queue_pct <= 10 AND n_expected_fired >= 3, 1, 0)), 'PASS', 'FAIL') AS f4_acceptance
  FROM EVAL.RISK_PATTERN_RESULT
 WHERE pattern_type = 'XCORE_STRUCTURING';

-- Top of the queue (D05: the first row should be Deborah Sanford)
SELECT queue_rank, origin, display_name, priority_score, reasons
  FROM GOLD.ALERT_QUEUE
 WHERE queue_rank <= 10
 ORDER BY queue_rank;
