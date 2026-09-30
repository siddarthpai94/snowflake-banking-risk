-- Thursday proof (F2): one customer across both cores, from the Gold model, with lineage.
-- Deborah Sanford (synthetic) holds records in Core A and Core B. Change the name to look at anyone.
USE ROLE RISK_ADMIN;
USE WAREHOUSE RISK_WH;
USE DATABASE RISK_COPILOT;

SET customer_name = 'DEBORAH SANFORD';

-- 1. One resolved customer, and the source records that were linked to make it
SELECT p.party_id, p.display_name, p.birth_date, p.city, p.state, p.cores, p.core_a_key, p.core_b_key,
       x.source_system, x.source_key, x.link_status, x.link_reasons
  FROM GOLD.PARTY p
  JOIN SILVER.PARTY_XREF x ON x.party_id = p.party_id
 WHERE p.display_name = $customer_name AND p.cores = 2;

-- 2. Accounts in both cores
SELECT a.account_id, a.source_system, a.product_type, a.branch, a.status, a.opened_on, a.balance_usd,
       a.source_file, a.source_row
  FROM GOLD.ACCOUNT a JOIN GOLD.PARTY p ON p.party_id = a.party_id
 WHERE p.display_name = $customer_name AND p.cores = 2
 ORDER BY a.source_system, a.account_id;

-- 3. Loans in both cores
SELECT l.loan_id, l.source_system, l.loan_type, l.principal_usd, l.days_past_due, l.source_file, l.source_row
  FROM GOLD.LOAN l JOIN GOLD.PARTY p ON p.party_id = l.party_id
 WHERE p.display_name = $customer_name AND p.cores = 2;

-- 4. Cash deposits in the last 30 days, both cores, each traced to its source file and row
SELECT t.posted_at, t.source_system, t.account_id, t.amount_usd, t.branch, t.ctr_filed, t.source_file, t.source_row
  FROM GOLD.TRANSACTION t JOIN GOLD.PARTY p ON p.party_id = t.party_id
 WHERE p.display_name = $customer_name AND p.cores = 2
   AND t.txn_type = 'CASH_DEPOSIT' AND t.posted_date > DATE '2026-08-31' - 30
 ORDER BY t.posted_at;

-- 5. KYC in each core, legacy alerts, and what the risk engine says
SELECT k.source_system, k.occupation, k.expected_monthly_cash_usd, k.risk_rating, k.review_date
  FROM GOLD.KYC_PROFILE k JOIN GOLD.PARTY p ON p.party_id = k.party_id
 WHERE p.display_name = $customer_name AND p.cores = 2;

SELECT a.alert_id, a.scenario, a.alert_date, a.status, a.disposition
  FROM GOLD.ALERT a JOIN GOLD.PARTY p ON p.party_id = a.party_id
 WHERE p.display_name = $customer_name AND p.cores = 2;

SELECT s.rule_code, s.weight, s.evidence_text
  FROM GOLD.RISK_SIGNAL s JOIN GOLD.PARTY p ON p.party_id = s.party_id
 WHERE p.display_name = $customer_name AND p.cores = 2
 ORDER BY s.weight DESC;

SELECT q.queue_rank, q.queue_size, q.origin, q.priority_score, q.reasons
  FROM GOLD.ALERT_QUEUE q JOIN GOLD.PARTY p ON p.party_id = q.party_id
 WHERE p.display_name = $customer_name AND p.cores = 2;
