-- Load reconciliation: Bronze row counts and amount totals against each core's
-- extract control totals. This is the "reconciliation count goes green" check.
-- Duplicate keys and orphan rows are data-quality findings for Silver; they do
-- not break load reconciliation, because control totals describe the files as sent.
USE ROLE RISK_ADMIN;
USE WAREHOUSE RISK_WH;
USE DATABASE RISK_COPILOT;

CREATE OR REPLACE VIEW BRONZE.V_LOAD_RECONCILIATION
  COMMENT = 'Bronze load vs extract control totals, per file. SYNTHETIC DATA.'
AS
WITH loaded AS (
    SELECT 'core_a' AS core, 'customers.csv' AS file_name, COUNT(*) AS rows_loaded, NULL::NUMBER(38,2) AS amount_loaded
      FROM BRONZE.CORE_A_CUSTOMERS
    UNION ALL SELECT 'core_a', 'accounts.csv', COUNT(*), SUM(TO_NUMBER("CUR_BAL_CENTS")) / 100 FROM BRONZE.CORE_A_ACCOUNTS
    UNION ALL SELECT 'core_a', 'loans.csv', COUNT(*), SUM(TO_NUMBER("CUR_PRIN_CENTS")) / 100 FROM BRONZE.CORE_A_LOANS
    UNION ALL SELECT 'core_a', 'transactions.csv', COUNT(*), SUM(TO_NUMBER("AMT_CENTS")) / 100 FROM BRONZE.CORE_A_TXNS
    UNION ALL SELECT 'core_a', 'aml_alerts.csv', COUNT(*), NULL FROM BRONZE.CORE_A_AML_ALERTS
    UNION ALL SELECT 'core_b', 'party.csv', COUNT(*), NULL FROM BRONZE.CORE_B_PARTY
    UNION ALL SELECT 'core_b', 'deposit_account.csv', COUNT(*), SUM(TO_NUMBER("ledger_balance", 38, 2)) FROM BRONZE.CORE_B_DEPOSIT_ACCOUNT
    UNION ALL SELECT 'core_b', 'loan.csv', COUNT(*), SUM(TO_NUMBER("principal_outstanding", 38, 2)) FROM BRONZE.CORE_B_LOAN
    UNION ALL SELECT 'core_b', 'txn.csv', COUNT(*),
                     SUM(IFF("dr_cr" = 'C', 1, -1) * TO_NUMBER("amount", 38, 2)) FROM BRONZE.CORE_B_TXN
    UNION ALL SELECT 'core_b', 'case_alert.csv', COUNT(*), NULL FROM BRONZE.CORE_B_CASE_ALERT
),
expected AS (
    SELECT 'core_a' AS core, "FILE_NM" AS file_name, TO_NUMBER("REC_CNT") AS rows_expected,
           TO_NUMBER("AMT_TOTAL_CENTS") / 100 AS amount_expected
      FROM BRONZE.CORE_A_CONTROL_TOTALS
    UNION ALL
    SELECT 'core_b', "file_name", TO_NUMBER("record_count"), TO_NUMBER("amount_total", 38, 2)
      FROM BRONZE.CORE_B_CONTROL_TOTALS
)
SELECT e.core, e.file_name, e.rows_expected, l.rows_loaded, e.amount_expected, l.amount_loaded,
       IFF(e.rows_expected = l.rows_loaded
           AND (e.amount_expected IS NULL OR e.amount_expected = l.amount_loaded), 'MATCH', 'BREAK') AS status
  FROM expected e
  LEFT JOIN loaded l ON l.core = e.core AND l.file_name = e.file_name
 ORDER BY e.core, e.file_name;

-- Expect every row MATCH:
SELECT * FROM BRONZE.V_LOAD_RECONCILIATION;
