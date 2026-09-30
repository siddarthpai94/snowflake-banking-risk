-- F4 risk engine: transparent rules, weighted score, reason codes and evidence.
-- No AI: every score is a sum of rule weights from GOLD.CONFIG_RISK_RULE, and every
-- threshold comes from GOLD.CONFIG_PARAM (config/bank_demo.yaml).
USE ROLE RISK_ADMIN;
USE WAREHOUSE RISK_WH;
USE DATABASE RISK_COPILOT;

-- One row per rule that fired for a customer, with the evidence behind it.
CREATE OR REPLACE DYNAMIC TABLE GOLD.RISK_SIGNAL
  TARGET_LAG = 'DOWNSTREAM'
  WAREHOUSE = RISK_WH
  COMMENT = 'Fired risk rules per resolved customer, with evidence. SYNTHETIC DATA.'
AS
WITH p AS (
    SELECT MAX(IFF(name = 'thresholds.ctr_cash_threshold_usd', num_value, NULL))      AS ctr_usd,
           MAX(IFF(name = 'thresholds.cross_core_cash_total_usd', num_value, NULL))   AS xcore_usd,
           MAX(IFF(name = 'thresholds.structuring_band_low_usd', num_value, NULL))    AS band_low_usd,
           CAST(MAX(IFF(name = 'thresholds.near_threshold_min_count', num_value, NULL)) AS INTEGER) AS near_min_count,
           CAST(MAX(IFF(name = 'thresholds.dormancy_days', num_value, NULL)) AS INTEGER) AS dormancy_days,
           MAX(IFF(name = 'thresholds.reactivation_inflow_usd', num_value, NULL))     AS react_inflow_usd,
           MAX(IFF(name = 'thresholds.rapid_in_out_pct_out', num_value, NULL))        AS rapid_pct,
           CAST(MAX(IFF(name = 'thresholds.rapid_in_out_hours', num_value, NULL)) AS INTEGER) AS rapid_hours,
           MAX(IFF(name = 'thresholds.rapid_in_out_min_inflow_usd', num_value, NULL)) AS rapid_min_usd,
           MAX(IFF(name = 'thresholds.kyc_cash_multiple', num_value, NULL))           AS kyc_multiple,
           MAX(IFF(name = 'thresholds.kyc_cash_min_usd', num_value, NULL))            AS kyc_min_usd,
           MAX(IFF(name = 'thresholds.kyc_consistent_max_multiple', num_value, NULL)) AS kyc_ok_multiple,
           CAST(MAX(IFF(name = 'risk_queue.window_days', num_value, NULL)) AS INTEGER) AS window_days,
           CAST(MAX(IFF(name = 'risk_queue.pattern_lookback_days', num_value, NULL)) AS INTEGER) AS lookback_days
      FROM GOLD.CONFIG_PARAM
),
ref AS (SELECT MAX(posted_date) AS as_of FROM GOLD.TRANSACTION),
cash AS (
    SELECT t.party_id, t.source_system, t.posted_date, t.amount_usd, t.ctr_filed
      FROM GOLD.TRANSACTION t CROSS JOIN ref CROSS JOIN p
     WHERE t.txn_type = 'CASH_DEPOSIT' AND t.party_id IS NOT NULL
       AND t.posted_date > ref.as_of - p.window_days
),
cash_party AS (
    SELECT party_id,
           SUM(amount_usd) AS total_usd,
           SUM(IFF(source_system = 'core_a', amount_usd, 0)) AS core_a_usd,
           SUM(IFF(source_system = 'core_b', amount_usd, 0)) AS core_b_usd,
           COUNT(DISTINCT source_system) AS n_cores,
           COUNT(*) AS n_deposits,
           MIN(posted_date) AS first_date, MAX(posted_date) AS last_date
      FROM cash
     GROUP BY party_id
),
r_xcore AS (
    SELECT c.party_id, 'XCORE_CASH_30D' AS rule_code, c.total_usd AS amount_usd, c.n_deposits AS evidence_count,
           c.first_date AS evidence_from, c.last_date AS evidence_to,
           'Cash deposits in both cores: Core A $' || CAST(ROUND(c.core_a_usd) AS BIGINT)
             || ' + Core B $' || CAST(ROUND(c.core_b_usd) AS BIGINT) || ' = $' || CAST(ROUND(c.total_usd) AS BIGINT)
             || ' in ' || CAST(p.window_days AS BIGINT) || ' days' AS evidence_text
      FROM cash_party c CROSS JOIN p
     WHERE c.n_cores >= 2 AND c.total_usd > p.xcore_usd
),
cash_day AS (
    SELECT t.party_id, t.posted_date,
           SUM(t.amount_usd) AS day_usd,
           COUNT(DISTINCT t.source_system) AS n_cores,
           MAX(IFF(t.ctr_filed, 1, 0)) AS any_ctr
      FROM GOLD.TRANSACTION t CROSS JOIN ref CROSS JOIN p
     WHERE t.txn_type = 'CASH_DEPOSIT' AND t.party_id IS NOT NULL
       AND t.posted_date > ref.as_of - p.lookback_days
     GROUP BY t.party_id, t.posted_date
),
r_ctr AS (
    SELECT d.party_id, 'CTR_AGGREGATION_MISSED' AS rule_code, MAX(d.day_usd) AS amount_usd, COUNT(*) AS evidence_count,
           MIN(d.posted_date) AS evidence_from, MAX(d.posted_date) AS evidence_to,
           CAST(COUNT(*) AS BIGINT) || ' business day(s) with same-day cash across both cores over $'
             || CAST(ROUND(MAX(p.ctr_usd)) AS BIGINT) || ' and no CTR; largest $' || CAST(ROUND(MAX(d.day_usd)) AS BIGINT)
             || ' on ' || CAST(MAX_BY(d.posted_date, d.day_usd) AS VARCHAR) AS evidence_text
      FROM cash_day d CROSS JOIN p
     WHERE d.n_cores >= 2 AND d.day_usd > p.ctr_usd AND d.any_ctr = 0
     GROUP BY d.party_id
),
-- Near-threshold cash in ANY rolling window of window_days within the look-back, not only the latest one
band AS (
    SELECT t.party_id, t.posted_date, t.amount_usd
      FROM GOLD.TRANSACTION t CROSS JOIN ref CROSS JOIN p
     WHERE t.txn_type = 'CASH_DEPOSIT' AND t.party_id IS NOT NULL
       AND t.posted_date > ref.as_of - p.lookback_days
       AND t.amount_usd >= p.band_low_usd AND t.amount_usd < p.ctr_usd
),
band_win AS (
    SELECT s.party_id, s.posted_date AS win_start, MAX(e.posted_date) AS win_end,
           COUNT(*) AS n_deposits, SUM(e.amount_usd) AS total_usd
      FROM (SELECT DISTINCT party_id, posted_date FROM band) s
      JOIN band e ON e.party_id = s.party_id
       AND e.posted_date >= s.posted_date
      CROSS JOIN p
     WHERE e.posted_date < s.posted_date + p.window_days
     GROUP BY s.party_id, s.posted_date
),
r_near AS (
    SELECT w.party_id, 'NEAR_THRESHOLD_CASH' AS rule_code,
           MAX_BY(w.total_usd, w.n_deposits * 1e12 + w.total_usd) AS amount_usd, MAX(w.n_deposits) AS evidence_count,
           MAX_BY(w.win_start, w.n_deposits * 1e12 + w.total_usd) AS evidence_from,
           MAX_BY(w.win_end, w.n_deposits * 1e12 + w.total_usd) AS evidence_to,
           CAST(MAX(w.n_deposits) AS VARCHAR) || ' cash deposits between $' || CAST(ROUND(MAX(p.band_low_usd)) AS BIGINT)
             || ' and $' || CAST(ROUND(MAX(p.ctr_usd)) AS BIGINT) || ' totalling $'
             || CAST(ROUND(MAX_BY(w.total_usd, w.n_deposits * 1e12 + w.total_usd)) AS BIGINT)
             || ' within ' || CAST(MAX(p.window_days) AS VARCHAR) || ' days, from '
             || CAST(MAX_BY(w.win_start, w.n_deposits * 1e12 + w.total_usd) AS VARCHAR) AS evidence_text
      FROM band_win w CROSS JOIN p
     WHERE w.n_deposits >= p.near_min_count
     GROUP BY w.party_id
),
inflow AS (
    SELECT t.txn_id, t.party_id, t.account_id, t.posted_at, t.posted_date, t.amount_usd, t.counterparty
      FROM GOLD.TRANSACTION t CROSS JOIN ref CROSS JOIN p
     WHERE t.txn_type IN ('WIRE_IN', 'ACH_CREDIT') AND t.party_id IS NOT NULL
       AND t.amount_usd >= p.rapid_min_usd AND t.posted_date > ref.as_of - p.lookback_days
),
rapid AS (
    SELECT i.txn_id, i.party_id, i.posted_date, i.amount_usd AS in_usd, i.counterparty,
           SUM(o.amount_usd) AS out_usd
      FROM inflow i
      JOIN GOLD.TRANSACTION o ON o.account_id = i.account_id
       AND o.txn_type IN ('WIRE_OUT', 'ACH_DEBIT')
       AND o.posted_date BETWEEN i.posted_date AND i.posted_date + 3
      CROSS JOIN p
     WHERE DATEDIFF('second', i.posted_at, o.posted_at) BETWEEN 1 AND p.rapid_hours * 3600
     GROUP BY i.txn_id, i.party_id, i.posted_date, i.amount_usd, i.counterparty
),
r_rapid AS (
    SELECT r.party_id, 'RAPID_IN_OUT' AS rule_code, MAX(r.in_usd) AS amount_usd, COUNT(*) AS evidence_count,
           MIN(r.posted_date) AS evidence_from, MAX(r.posted_date) AS evidence_to,
           '$' || CAST(ROUND(MAX(r.in_usd)) AS BIGINT) || ' in from ' || MAX_BY(r.counterparty, r.in_usd)
             || ', $' || CAST(ROUND(MAX_BY(r.out_usd, r.in_usd)) AS BIGINT) || ' out within '
             || CAST(MAX(p.rapid_hours) AS BIGINT) || ' hours' AS evidence_text
      FROM rapid r CROSS JOIN p
     WHERE r.out_usd >= p.rapid_pct * r.in_usd
     GROUP BY r.party_id
),
react AS (
    SELECT a.party_id, a.account_id, a.dormant_since, a.reactivated_on,
           SUM(t.amount_usd) AS inflow_usd
      FROM GOLD.ACCOUNT a
      JOIN GOLD.TRANSACTION t ON t.account_id = a.account_id
       AND t.direction = 'CREDIT'
       AND t.posted_date BETWEEN a.reactivated_on AND a.reactivated_on + 30
      CROSS JOIN p
     WHERE a.reactivated_on IS NOT NULL AND a.party_id IS NOT NULL
       AND a.reactivated_on - a.dormant_since >= p.dormancy_days
     GROUP BY a.party_id, a.account_id, a.dormant_since, a.reactivated_on
),
r_react AS (
    SELECT r.party_id, 'DORMANT_REACTIVATION' AS rule_code, MAX(r.inflow_usd) AS amount_usd, COUNT(*) AS evidence_count,
           MIN(r.reactivated_on) AS evidence_from, MAX(r.reactivated_on) AS evidence_to,
           'Account dormant since ' || CAST(MIN(r.dormant_since) AS VARCHAR) || ' reactivated on '
             || CAST(MAX(r.reactivated_on) AS VARCHAR) || ' with $' || CAST(ROUND(MAX(r.inflow_usd)) AS BIGINT)
             || ' inflow within 30 days' AS evidence_text
      FROM react r CROSS JOIN p
     WHERE r.inflow_usd >= p.react_inflow_usd
     GROUP BY r.party_id
),
kyc AS (
    SELECT party_id, MAX(expected_monthly_cash_usd) AS expected_cash_usd,
           COUNT(DISTINCT source_system) AS n_cores, COUNT(DISTINCT occupation) AS n_occupations,
           MIN(occupation) AS occ_1, MAX(occupation) AS occ_2
      FROM GOLD.KYC_PROFILE
     WHERE party_id IS NOT NULL
     GROUP BY party_id
),
-- Best 30-day cash total per customer: the latest window, or the busiest rolling near-threshold window
cash_best AS (
    SELECT party_id, MAX(total_usd) AS best_usd, MAX(n_deposits) AS n_deposits
      FROM (SELECT party_id, total_usd, n_deposits FROM cash_party
            UNION ALL SELECT party_id, total_usd, n_deposits FROM band_win) u
     GROUP BY party_id
),
r_kyc AS (
    SELECT c.party_id, 'KYC_MISMATCH' AS rule_code, c.best_usd AS amount_usd, c.n_deposits AS evidence_count,
           CAST(NULL AS DATE) AS evidence_from, CAST(NULL AS DATE) AS evidence_to,
           '$' || CAST(ROUND(c.best_usd) AS BIGINT) || ' cash within ' || CAST(p.window_days AS VARCHAR)
             || ' days against expected monthly cash of $' || CAST(ROUND(k.expected_cash_usd) AS BIGINT)
             || ' in KYC' AS evidence_text
      FROM cash_best c JOIN kyc k ON k.party_id = c.party_id CROSS JOIN p
     WHERE c.best_usd > p.kyc_multiple * k.expected_cash_usd AND c.best_usd > p.kyc_min_usd
),
-- Mitigating: cash activity is within what the KYC profile expects (negative weight)
r_kyc_ok AS (
    SELECT c.party_id, 'KYC_CONSISTENT_CASH' AS rule_code, c.best_usd AS amount_usd, c.n_deposits AS evidence_count,
           CAST(NULL AS DATE) AS evidence_from, CAST(NULL AS DATE) AS evidence_to,
           'Mitigating: $' || CAST(ROUND(c.best_usd) AS BIGINT) || ' cash within ' || CAST(p.window_days AS VARCHAR)
             || ' days is in line with expected monthly cash of $' || CAST(ROUND(k.expected_cash_usd) AS BIGINT)
             || ' in KYC' AS evidence_text
      FROM cash_best c JOIN kyc k ON k.party_id = c.party_id CROSS JOIN p
     WHERE c.best_usd > p.kyc_min_usd AND c.best_usd <= p.kyc_ok_multiple * k.expected_cash_usd
),
r_kyc2 AS (
    SELECT k.party_id, 'KYC_INCONSISTENT_ACROSS_CORES' AS rule_code, CAST(NULL AS DECIMAL(38, 2)) AS amount_usd,
           k.n_cores AS evidence_count, CAST(NULL AS DATE) AS evidence_from, CAST(NULL AS DATE) AS evidence_to,
           'KYC occupation differs between cores: ' || k.occ_1 || ' vs ' || k.occ_2 AS evidence_text
      FROM kyc k
     WHERE k.n_cores >= 2 AND k.n_occupations > 1
),
fired AS (
    SELECT * FROM r_xcore UNION ALL SELECT * FROM r_ctr UNION ALL SELECT * FROM r_near
    UNION ALL SELECT * FROM r_rapid UNION ALL SELECT * FROM r_react UNION ALL SELECT * FROM r_kyc UNION ALL SELECT * FROM r_kyc_ok
    UNION ALL SELECT * FROM r_kyc2
)
SELECT f.party_id, f.rule_code, w.weight, w.description AS rule_description, f.amount_usd, f.evidence_count,
       f.evidence_from, f.evidence_to, f.evidence_text
  FROM fired f
  JOIN GOLD.CONFIG_RISK_RULE w ON w.rule_code = f.rule_code;

-- Score per customer: sum of fired rule weights, kept within 0-100, with the top three risk-raising
-- reasons. Mitigating rules (negative weight) are listed separately.
CREATE OR REPLACE DYNAMIC TABLE GOLD.RISK_SCORE
  TARGET_LAG = 'DOWNSTREAM'
  WAREHOUSE = RISK_WH
  COMMENT = 'Customer risk score from rule weights, with top reasons. SYNTHETIC DATA.'
AS
WITH ranked AS (
    SELECT s.*, ROW_NUMBER() OVER (PARTITION BY s.party_id ORDER BY s.weight DESC, s.rule_code) AS rn
      FROM GOLD.RISK_SIGNAL s
)
SELECT r.party_id, pt.display_name, pt.cores,
       GREATEST(0, LEAST(100, SUM(r.weight))) AS risk_score,
       SUM(r.weight) AS raw_score,
       COUNT(*) AS rules_fired,
       LISTAGG(IFF(r.rn <= 3 AND r.weight > 0, r.rule_code, NULL), '; ') WITHIN GROUP (ORDER BY r.rn) AS top_reasons,
       LISTAGG(IFF(r.rn <= 3 AND r.weight > 0, r.evidence_text, NULL), ' | ') WITHIN GROUP (ORDER BY r.rn) AS top_evidence,
       LISTAGG(IFF(r.weight < 0, r.rule_code, NULL), '; ') WITHIN GROUP (ORDER BY r.rn) AS mitigating,
       MAX(r.amount_usd) AS max_amount_usd
  FROM ranked r
  LEFT JOIN GOLD.PARTY pt ON pt.party_id = r.party_id
 GROUP BY r.party_id, pt.display_name, pt.cores;

-- The investigator's work queue: open legacy alerts plus new engine alerts, ranked.
-- Legacy scores are uncalibrated, so they count at risk_queue.legacy_score_weight.
-- Ties: uncapped rule-weight total first, then the largest amount in the evidence.
CREATE OR REPLACE DYNAMIC TABLE GOLD.ALERT_QUEUE
  TARGET_LAG = 'DOWNSTREAM'
  WAREHOUSE = RISK_WH
  COMMENT = 'Ranked alert queue across both cores and the risk engine. SYNTHETIC DATA.'
AS
WITH p AS (
    SELECT MAX(IFF(name = 'risk_queue.min_score_for_new_alert', num_value, NULL)) AS min_new,
           MAX(IFF(name = 'risk_queue.legacy_score_weight', num_value, NULL))    AS legacy_w
      FROM GOLD.CONFIG_PARAM
),
legacy AS (
    SELECT a.alert_id AS queue_item_id, 'LEGACY_' || UPPER(a.source_system) AS origin, a.party_id,
           a.scenario, a.alert_date, a.legacy_score,
           COALESCE(s.risk_score, 0) AS engine_score,
           GREATEST(COALESCE(s.risk_score, 0), a.legacy_score * p.legacy_w) AS priority_score,
           s.raw_score AS engine_raw_score,
           COALESCE(s.top_reasons, 'LEGACY_' || a.scenario) AS reasons,
           s.top_evidence AS evidence, s.max_amount_usd
      FROM GOLD.ALERT a CROSS JOIN p
      LEFT JOIN GOLD.RISK_SCORE s ON s.party_id = a.party_id
     WHERE a.status <> 'CLOSED'
),
engine AS (
    SELECT 'ENGINE:' || s.party_id AS queue_item_id, 'RISK_ENGINE' AS origin, s.party_id,
           'ENGINE_' || SPLIT_PART(s.top_reasons, ';', 1) AS scenario, CAST(NULL AS DATE) AS alert_date,
           CAST(NULL AS INTEGER) AS legacy_score, s.risk_score AS engine_score,
           CAST(s.risk_score AS DOUBLE) AS priority_score, s.raw_score AS engine_raw_score, s.top_reasons AS reasons, s.top_evidence AS evidence,
           s.max_amount_usd
      FROM GOLD.RISK_SCORE s CROSS JOIN p
      LEFT JOIN (SELECT DISTINCT party_id FROM GOLD.ALERT WHERE status <> 'CLOSED') open_a ON open_a.party_id = s.party_id
     WHERE s.risk_score >= p.min_new AND open_a.party_id IS NULL
),
q AS (SELECT * FROM legacy UNION ALL SELECT * FROM engine)
SELECT q.*, pt.display_name, pt.cores,
       ROW_NUMBER() OVER (ORDER BY q.priority_score DESC, q.engine_raw_score DESC NULLS LAST,
                           q.max_amount_usd DESC NULLS LAST, q.queue_item_id) AS queue_rank,
       COUNT(*) OVER () AS queue_size
  FROM q
  LEFT JOIN GOLD.PARTY pt ON pt.party_id = q.party_id;
