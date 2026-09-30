-- Answer the 15 golden questions (docs/spec.md) from the Gold model only, as (question_id, metric, value).
-- Compare with ground_truth/golden_answers.json. tests/test_f4_gold_risk.py runs this file on DuckDB and
-- checks every value; in Snowflake, run it and compare by eye. As-of date: 31 Aug 2026 (config).
USE ROLE RISK_ADMIN;
USE WAREHOUSE RISK_WH;
USE DATABASE RISK_COPILOT;

WITH
g01 AS (SELECT 'G01' AS question_id, source_system || '_records' AS metric, CAST(COUNT(*) AS VARCHAR) AS value
          FROM SILVER.CUSTOMER_STD WHERE source_system IN ('core_a', 'core_b') GROUP BY source_system),
g02 AS (SELECT 'G02' AS question_id, 'unique_customers' AS metric, CAST(COUNT(*) AS VARCHAR) AS value FROM GOLD.PARTY),
g03 AS (SELECT 'G03' AS question_id, 'alerts' AS metric, CAST(COUNT(*) AS VARCHAR) AS value
          FROM GOLD.ALERT WHERE alert_date BETWEEN DATE '2026-08-01' AND DATE '2026-08-31'),
q2c AS (SELECT * FROM GOLD.ALERT WHERE closed_on BETWEEN DATE '2026-04-01' AND DATE '2026-06-30'),
g04 AS (SELECT 'G04' AS question_id, 'false_positive_rate_pct' AS metric,
               CAST(ROUND(100.0 * SUM(IFF(disposition = 'FALSE_POSITIVE', 1, 0)) / COUNT(*), 1) AS VARCHAR) AS value FROM q2c),
b90 AS (SELECT branch, COUNT(*) AS n,
               ROW_NUMBER() OVER (ORDER BY COUNT(*) DESC, branch) AS rn
          FROM GOLD.ALERT WHERE alert_date > DATE '2026-08-31' - 90 GROUP BY branch),
g05 AS (SELECT 'G05' AS question_id, 'rank' || CAST(rn AS VARCHAR) AS metric,
               branch || '=' || CAST(n AS VARCHAR) AS value FROM b90 WHERE rn <= 3),
g06 AS (SELECT 'G06' AS question_id, 'open_over_30_days' AS metric, CAST(COUNT(*) AS VARCHAR) AS value
          FROM GOLD.ALERT WHERE status <> 'CLOSED' AND alert_date < DATE '2026-08-01'),
g06b AS (SELECT 'G06' AS question_id, 'open_total' AS metric, CAST(COUNT(*) AS VARCHAR) AS value
          FROM GOLD.ALERT WHERE status <> 'CLOSED'),
g07 AS (SELECT 'G07' AS question_id, 'cash_deposits_usd' AS metric, CAST(ROUND(SUM(amount_usd), 2) AS VARCHAR) AS value
          FROM GOLD.TRANSACTION WHERE txn_type = 'CASH_DEPOSIT' AND posted_date BETWEEN DATE '2026-08-01' AND DATE '2026-08-31'),
g08 AS (SELECT 'G08' AS question_id, 'cash_withdrawals_usd' AS metric, CAST(ROUND(SUM(amount_usd), 2) AS VARCHAR) AS value
          FROM GOLD.TRANSACTION WHERE txn_type IN ('CASH_WITHDRAWAL', 'ATM_WITHDRAWAL')
           AND posted_date BETWEEN DATE '2026-08-01' AND DATE '2026-08-31'),
dep AS (SELECT source_system, SUM(balance_usd) AS usd FROM GOLD.ACCOUNT WHERE status IN ('OPEN', 'DORMANT') GROUP BY source_system),
lns AS (SELECT SUM(principal_usd) AS usd FROM GOLD.LOAN),
g09 AS (SELECT 'G09' AS question_id, 'loan_to_deposit_pct' AS metric,
               CAST(ROUND(100.0 * (SELECT usd FROM lns) / (SELECT SUM(usd) FROM dep), 1) AS VARCHAR) AS value),
cap AS (SELECT num_value AS usd FROM GOLD.CONFIG_PARAM WHERE name = 'capital.total_risk_based_capital_usd'),
g10 AS (SELECT 'G10' AS question_id, 'cre_to_capital_pct' AS metric,
               CAST(ROUND(100.0 * SUM(l.principal_usd) / MAX(c.usd), 1) AS VARCHAR) AS value
          FROM GOLD.LOAN l CROSS JOIN cap c WHERE l.cre_category IS NOT NULL AND NOT l.owner_occupied),
g11 AS (SELECT 'G11' AS question_id, source_system || '_deposits_usd' AS metric, CAST(ROUND(usd, 2) AS VARCHAR) AS value FROM dep),
g12 AS (SELECT 'G12' AS question_id, 'dormant_accounts' AS metric, CAST(COUNT(*) AS VARCHAR) AS value
          FROM GOLD.ACCOUNT WHERE status = 'DORMANT'),
c30 AS (SELECT t.party_id, SUM(t.amount_usd) AS usd,
               ROW_NUMBER() OVER (ORDER BY SUM(t.amount_usd) DESC) AS rn
          FROM GOLD.TRANSACTION t
         WHERE t.txn_type = 'CASH_DEPOSIT' AND t.posted_date BETWEEN DATE '2026-08-02' AND DATE '2026-08-31'
         GROUP BY t.party_id),
g13 AS (SELECT 'G13' AS question_id, 'rank' || CAST(c.rn AS VARCHAR) AS metric,
               p.display_name || '=' || CAST(ROUND(c.usd, 2) AS VARCHAR) AS value
          FROM c30 c JOIN GOLD.PARTY p ON p.party_id = c.party_id WHERE c.rn <= 5),
g14 AS (SELECT 'G14' AS question_id, 'avg_days_to_close' AS metric,
               CAST(ROUND(AVG(closed_on - alert_date), 1) AS VARCHAR) AS value FROM q2c),
g15 AS (SELECT 'G15' AS question_id, 'loans_90_plus' AS metric, CAST(COUNT(*) AS VARCHAR) AS value
          FROM GOLD.LOAN WHERE days_past_due >= 90),
g15b AS (SELECT 'G15' AS question_id, 'principal_usd' AS metric, CAST(ROUND(SUM(principal_usd), 2) AS VARCHAR) AS value
          FROM GOLD.LOAN WHERE days_past_due >= 90)
SELECT * FROM g01 UNION ALL SELECT * FROM g02 UNION ALL SELECT * FROM g03 UNION ALL SELECT * FROM g04
UNION ALL SELECT * FROM g05 UNION ALL SELECT * FROM g06 UNION ALL SELECT * FROM g06b UNION ALL SELECT * FROM g07
UNION ALL SELECT * FROM g08 UNION ALL SELECT * FROM g09 UNION ALL SELECT * FROM g10 UNION ALL SELECT * FROM g11
UNION ALL SELECT * FROM g12 UNION ALL SELECT * FROM g13 UNION ALL SELECT * FROM g14 UNION ALL SELECT * FROM g15
UNION ALL SELECT * FROM g15b
ORDER BY question_id, metric;
