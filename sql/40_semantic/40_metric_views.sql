-- F3 semantic layer, built without AI: governed views with one definition per metric.
-- The question catalogue (41_question_catalog.sql) and the app read only these views and GOLD.
-- Every definition here is also listed in SEMANTIC.METRIC_DEFINITION.
USE ROLE RISK_ADMIN;
USE WAREHOUSE RISK_WH;
USE DATABASE RISK_COPILOT;

-- The reporting date for "as of" questions, from config/bank_demo.yaml
CREATE OR REPLACE VIEW SEMANTIC.V_AS_OF AS
SELECT CAST(text_value AS DATE) AS as_of_date
  FROM GOLD.CONFIG_PARAM WHERE name = 'institution.as_of_date';

-- Source customer records per core and the resolved customer each belongs to
CREATE OR REPLACE VIEW SEMANTIC.V_CUSTOMER_RECORD AS
SELECT x.record_id, x.source_system, x.source_key, x.party_id, x.link_status
  FROM SILVER.PARTY_XREF x
 WHERE x.source_system IN ('core_a', 'core_b');

-- Alerts: volume, open, false-positive and time-to-close are all defined here
CREATE OR REPLACE VIEW SEMANTIC.V_ALERT AS
SELECT a.alert_id, a.source_system, a.party_id, p.display_name, a.account_id, a.scenario,
       a.alert_date, DATE_TRUNC('month', a.alert_date) AS alert_month,
       a.status, (a.status <> 'CLOSED') AS is_open,
       a.disposition, (a.disposition = 'FALSE_POSITIVE') AS is_false_positive,
       a.closed_on, a.closed_on - a.alert_date AS days_to_close,
       a.branch, a.legacy_score, a.owner, a.source_file, a.source_row
  FROM GOLD.ALERT a
  LEFT JOIN GOLD.PARTY p ON p.party_id = a.party_id;

-- Deposit balances count open and dormant accounts only (closed accounts hold no balance)
CREATE OR REPLACE VIEW SEMANTIC.V_DEPOSIT AS
SELECT a.account_id, a.source_system, a.party_id, a.product_type, a.branch, a.status,
       (a.status = 'DORMANT') AS is_dormant, a.balance_usd, a.source_file, a.source_row
  FROM GOLD.ACCOUNT a
 WHERE a.status IN ('OPEN', 'DORMANT');

-- Loans: CRE and past-due flags defined once
CREATE OR REPLACE VIEW SEMANTIC.V_LOAN AS
SELECT l.loan_id, l.source_system, l.party_id, l.loan_type, l.branch, l.principal_usd, l.days_past_due,
       (l.cre_category IS NOT NULL) AS is_cre,
       (l.cre_category IS NOT NULL AND NOT l.owner_occupied) AS is_non_owner_occupied_cre,
       (l.days_past_due >= 90) AS is_90_plus_past_due,
       l.cre_category, l.owner_occupied, l.source_file, l.source_row
  FROM GOLD.LOAN l;

-- Cash: teller cash deposits are cash in; teller and ATM withdrawals are cash out
CREATE OR REPLACE VIEW SEMANTIC.V_CASH AS
SELECT t.txn_id, t.source_system, t.account_id, t.party_id, p.display_name, t.posted_at, t.posted_date,
       CASE WHEN t.txn_type = 'CASH_DEPOSIT' THEN 'IN' ELSE 'OUT' END AS cash_direction,
       t.txn_type, t.amount_usd, t.branch, t.ctr_filed, t.source_file, t.source_row
  FROM GOLD.TRANSACTION t
  LEFT JOIN GOLD.PARTY p ON p.party_id = t.party_id
 WHERE t.txn_type IN ('CASH_DEPOSIT', 'CASH_WITHDRAWAL', 'ATM_WITHDRAWAL');

-- The glossary shown next to every answer
CREATE OR REPLACE TABLE SEMANTIC.METRIC_DEFINITION (metric VARCHAR, definition VARCHAR, source_view VARCHAR);
INSERT INTO SEMANTIC.METRIC_DEFINITION (metric, definition, source_view) VALUES
  ('customer records', 'Rows in each core''s customer file, individuals and businesses.', 'SEMANTIC.V_CUSTOMER_RECORD'),
  ('unique customers', 'Resolved customers after cross-core entity resolution (auto-links only).', 'GOLD.PARTY'),
  ('alert volume', 'Legacy monitoring alerts by alert date, both cores.', 'SEMANTIC.V_ALERT'),
  ('open alert', 'An alert whose status is not CLOSED (Core B NEW, IN_REVIEW and ESCALATED count as open).', 'SEMANTIC.V_ALERT'),
  ('false-positive rate', 'Alerts closed as false positive (Core A FP, Core B NOT_SUSPICIOUS) divided by all alerts closed in the period.', 'SEMANTIC.V_ALERT'),
  ('days to close', 'Close date minus alert date, for closed alerts.', 'SEMANTIC.V_ALERT'),
  ('deposit balances', 'Balances of open and dormant deposit accounts at the as-of date.', 'SEMANTIC.V_DEPOSIT'),
  ('dormant account', 'Deposit account in dormant status at the as-of date; reactivated accounts are not dormant.', 'SEMANTIC.V_DEPOSIT'),
  ('cash in', 'Teller cash deposits.', 'SEMANTIC.V_CASH'),
  ('cash out', 'Teller cash withdrawals and ATM withdrawals.', 'SEMANTIC.V_CASH'),
  ('loan-to-deposit ratio', 'Outstanding loan principal divided by deposit balances, both cores.', 'SEMANTIC.V_LOAN, SEMANTIC.V_DEPOSIT'),
  ('non-owner-occupied CRE', 'CRE loans not flagged owner-occupied, including construction and multifamily.', 'SEMANTIC.V_LOAN'),
  ('CRE concentration', 'Non-owner-occupied CRE principal divided by total risk-based capital from config.', 'SEMANTIC.V_LOAN, GOLD.CONFIG_PARAM'),
  ('90+ days past due', 'Loans with 90 or more days past due at the as-of date.', 'SEMANTIC.V_LOAN'),
  ('risk score', 'Sum of the weights of the risk rules that fired, kept within 0-100 (GOLD.CONFIG_RISK_RULE).', 'GOLD.RISK_SCORE');

-- Analysts and the app read the semantic layer
GRANT SELECT ON ALL VIEWS IN SCHEMA SEMANTIC TO ROLE RISK_ANALYST;
GRANT SELECT ON ALL TABLES IN SCHEMA SEMANTIC TO ROLE RISK_ANALYST;
