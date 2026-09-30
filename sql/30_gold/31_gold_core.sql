-- Gold: the canonical banking model across both cores (F2).
-- Column logic follows config/mappings/core_a.yaml and core_b.yaml. Every row keeps
-- source_file and source_row, so any number traces back to one line of one file.
-- Keys are 'core:source_key'. party_id comes from SILVER.PARTY_XREF (entity resolution).
USE ROLE RISK_ADMIN;
USE WAREHOUSE RISK_WH;
USE DATABASE RISK_COPILOT;

-- One row per resolved customer (person or organisation) across all cores.
CREATE OR REPLACE DYNAMIC TABLE GOLD.PARTY
  TARGET_LAG = 'DOWNSTREAM'
  WAREHOUSE = RISK_WH
  COMMENT = 'Resolved customers across all cores. SYNTHETIC DATA.'
AS
SELECT x.party_id,
       MIN(x.party_kind) AS party_kind,
       MIN_BY(s.display_name, x.source_system) AS display_name,
       MIN(s.birth_date) AS birth_date,
       MIN_BY(s.city, x.source_system) AS city,
       MIN_BY(s.state, x.source_system) AS state,
       COUNT(*) AS source_records,
       COUNT(DISTINCT x.source_system) AS cores,
       MAX(IFF(x.source_system = 'core_a', x.source_key, NULL)) AS core_a_key,
       MAX(IFF(x.source_system = 'core_b', x.source_key, NULL)) AS core_b_key,
       MAX(x.link_status) AS link_status,
       MAX(x.link_reasons) AS link_reasons
  FROM SILVER.PARTY_XREF x
  JOIN SILVER.CUSTOMER_STD s ON s.record_id = x.record_id
 GROUP BY x.party_id;

CREATE OR REPLACE DYNAMIC TABLE GOLD.ACCOUNT
  TARGET_LAG = 'DOWNSTREAM'
  WAREHOUSE = RISK_WH
  COMMENT = 'Deposit accounts from all cores; duplicate source keys kept once. SYNTHETIC DATA.'
AS
WITH a AS (
    SELECT 'core_a:' || "ACCT_NO" AS account_id, 'core_a' AS source_system, "ACCT_NO" AS source_key,
           'core_a:' || "CIF_NO" AS customer_record_id,
           CASE "PROD_CD" WHEN 'DDA' THEN 'CHECKING' WHEN 'SAV' THEN 'SAVINGS'
                          WHEN 'MMA' THEN 'MONEY_MARKET' WHEN 'CD' THEN 'CERTIFICATE' END AS product_type,
           "BR_CD" AS branch,
           TRY_TO_DATE("OPEN_DT", 'YYYYMMDD') AS opened_on,
           TRY_TO_DATE("CLOSE_DT", 'YYYYMMDD') AS closed_on,
           CASE "ACCT_STAT" WHEN 'A' THEN 'OPEN' WHEN 'D' THEN 'DORMANT' WHEN 'C' THEN 'CLOSED' END AS status,
           TRY_TO_DATE("DORM_FLAG_DT", 'YYYYMMDD') AS dormant_since,
           TRY_TO_DATE("REACT_DT", 'YYYYMMDD') AS reactivated_on,
           CAST(CAST("CUR_BAL_CENTS" AS DECIMAL(38, 2)) / 100 AS DECIMAL(38, 2)) AS balance_usd,
           CAST("INT_RATE_PCT" AS DECIMAL(10, 3)) AS rate_pct,
           _SOURCE_FILE AS source_file, _SOURCE_ROW AS source_row
      FROM BRONZE.CORE_A_ACCOUNTS
    QUALIFY ROW_NUMBER() OVER (PARTITION BY "ACCT_NO" ORDER BY _SOURCE_ROW) = 1
),
b AS (
    SELECT 'core_b:' || "acct_ref", 'core_b', "acct_ref", 'core_b:' || "party_uuid",
           CASE "product_name" WHEN 'Everyday Checking' THEN 'CHECKING' WHEN 'Business Checking' THEN 'CHECKING'
                               WHEN 'Statement Savings' THEN 'SAVINGS' WHEN 'Money Market' THEN 'MONEY_MARKET'
                               WHEN 'Certificate of Deposit' THEN 'CERTIFICATE' END,
           "branch_name",
           TRY_TO_DATE("opened_on", 'YYYY-MM-DD'),
           TRY_TO_DATE("closed_on", 'YYYY-MM-DD'),
           "acct_status",
           TRY_TO_DATE("dormant_since", 'YYYY-MM-DD'),
           TRY_TO_DATE("reactivated_on", 'YYYY-MM-DD'),
           CAST("ledger_balance" AS DECIMAL(38, 2)),
           CAST("rate_pct" AS DECIMAL(10, 3)),
           _SOURCE_FILE, _SOURCE_ROW
      FROM BRONZE.CORE_B_DEPOSIT_ACCOUNT
),
u AS (SELECT * FROM a UNION ALL SELECT * FROM b)
SELECT u.account_id, u.source_system, u.source_key, x.party_id, u.customer_record_id,
       u.product_type, u.branch, u.opened_on, u.closed_on, u.status, u.dormant_since, u.reactivated_on,
       u.balance_usd, u.rate_pct, u.source_file, u.source_row
  FROM u
  LEFT JOIN SILVER.PARTY_XREF x ON x.record_id = u.customer_record_id;

CREATE OR REPLACE DYNAMIC TABLE GOLD.LOAN
  TARGET_LAG = 'DOWNSTREAM'
  WAREHOUSE = RISK_WH
  COMMENT = 'Loans from all cores. SYNTHETIC DATA.'
AS
WITH a AS (
    SELECT 'core_a:' || "LOAN_NO" AS loan_id, 'core_a' AS source_system, "LOAN_NO" AS source_key,
           'core_a:' || "CIF_NO" AS customer_record_id,
           CASE "LOAN_TYP" WHEN 'MORT' THEN 'MORTGAGE' WHEN 'PERS' THEN 'PERSONAL' WHEN 'CI' THEN 'C_AND_I'
                           ELSE "LOAN_TYP" END AS loan_type,
           "BR_CD" AS branch,
           TRY_TO_DATE("ORIG_DT", 'YYYYMMDD') AS originated_on,
           TRY_TO_DATE("MAT_DT", 'YYYYMMDD') AS matures_on,
           CAST(CAST("ORIG_AMT_CENTS" AS DECIMAL(38, 2)) / 100 AS DECIMAL(38, 2)) AS original_amount_usd,
           CAST(CAST("CUR_PRIN_CENTS" AS DECIMAL(38, 2)) / 100 AS DECIMAL(38, 2)) AS principal_usd,
           CAST("INT_RATE_PCT" AS DECIMAL(10, 3)) AS rate_pct,
           CASE "COLL_TYP" WHEN 'CRE-OFF' THEN 'OFFICE' WHEN 'CRE-RET' THEN 'RETAIL' WHEN 'CRE-MF' THEN 'MULTIFAMILY'
                           WHEN 'CRE-IND' THEN 'INDUSTRIAL' WHEN 'CRE-CON' THEN 'CONSTRUCTION' END AS cre_category,
           ("OWNER_OCC_FLG" = 'Y') AS owner_occupied,
           CAST("DPD" AS INTEGER) AS days_past_due,
           _SOURCE_FILE AS source_file, _SOURCE_ROW AS source_row
      FROM BRONZE.CORE_A_LOANS
),
b AS (
    SELECT 'core_b:' || "note_number", 'core_b', "note_number", 'core_b:' || "party_uuid",
           CASE "product_name" WHEN 'Auto Loan' THEN 'AUTO' WHEN 'Residential Mortgage' THEN 'MORTGAGE'
                               WHEN 'Home Equity Line' THEN 'HELOC' WHEN 'Personal Loan' THEN 'PERSONAL'
                               WHEN 'Commercial Real Estate' THEN 'CRE' WHEN 'Commercial & Industrial' THEN 'C_AND_I' END,
           "branch_name",
           TRY_TO_DATE("booked_on", 'YYYY-MM-DD'),
           TRY_TO_DATE("maturity_on", 'YYYY-MM-DD'),
           CAST("original_amount" AS DECIMAL(38, 2)),
           CAST("principal_outstanding" AS DECIMAL(38, 2)),
           CAST("interest_rate_pct" AS DECIMAL(10, 3)),
           CASE WHEN "product_name" <> 'Commercial Real Estate' THEN NULL
                WHEN "collateral_desc" LIKE 'Office%' THEN 'OFFICE'
                WHEN "collateral_desc" LIKE 'Retail%' THEN 'RETAIL'
                WHEN "collateral_desc" LIKE 'Apartment%' THEN 'MULTIFAMILY'
                WHEN "collateral_desc" LIKE 'Warehouse%' THEN 'INDUSTRIAL'
                WHEN "collateral_desc" LIKE 'Construction%' THEN 'CONSTRUCTION' END,
           ("owner_occupied" = 'true'),
           CAST("days_delinquent" AS INTEGER),
           _SOURCE_FILE, _SOURCE_ROW
      FROM BRONZE.CORE_B_LOAN
),
u AS (SELECT * FROM a UNION ALL SELECT * FROM b)
SELECT u.loan_id, u.source_system, u.source_key, x.party_id, u.customer_record_id, u.loan_type, u.branch,
       u.originated_on, u.matures_on, u.original_amount_usd, u.principal_usd, u.rate_pct, u.cre_category,
       u.owner_occupied, u.days_past_due, u.source_file, u.source_row
  FROM u
  LEFT JOIN SILVER.PARTY_XREF x ON x.record_id = u.customer_record_id;

CREATE OR REPLACE DYNAMIC TABLE GOLD.TRANSACTION
  TARGET_LAG = 'DOWNSTREAM'
  WAREHOUSE = RISK_WH
  COMMENT = 'Posted transactions from all cores with canonical type, direction and party. SYNTHETIC DATA.'
AS
WITH a AS (
    SELECT 'core_a:' || "TXN_ID" AS txn_id, 'core_a' AS source_system, 'core_a:' || "ACCT_NO" AS account_id,
           "POST_DT" || "POST_TM" AS ts_text,
           CASE "TXN_CD" WHEN 'CDEP' THEN 'CASH_DEPOSIT' WHEN 'CWDR' THEN 'CASH_WITHDRAWAL'
                         WHEN 'ATMW' THEN 'ATM_WITHDRAWAL' WHEN 'ACHC' THEN 'ACH_CREDIT' WHEN 'ACHD' THEN 'ACH_DEBIT'
                         WHEN 'WIRI' THEN 'WIRE_IN' WHEN 'WIRO' THEN 'WIRE_OUT' WHEN 'CHKP' THEN 'CHECK_PAID'
                         WHEN 'CARD' THEN 'CARD_PURCHASE' WHEN 'XFRI' THEN 'TRANSFER_IN' WHEN 'XFRO' THEN 'TRANSFER_OUT'
                         WHEN 'INTC' THEN 'INTEREST' END AS txn_type,
           CAST(CAST("AMT_CENTS" AS DECIMAL(38, 2)) / 100 AS DECIMAL(38, 2)) AS amount_signed_usd,
           CASE "CHNL_CD" WHEN 'BR' THEN 'BRANCH' WHEN 'ATM' THEN 'ATM' WHEN 'OLB' THEN 'ONLINE'
                          WHEN 'MOB' THEN 'MOBILE' WHEN 'SYS' THEN 'SYSTEM' END AS channel,
           NULLIF("BR_CD", '') AS branch,
           ("CTR_FLG" = 'Y') AS ctr_filed,
           NULLIF("CPTY_NM", '') AS counterparty,
           NULLIF("CPTY_BANK", '') AS counterparty_institution,
           _SOURCE_FILE AS source_file, _SOURCE_ROW AS source_row
      FROM BRONZE.CORE_A_TXNS
),
b AS (
    SELECT 'core_b:' || "txn_uuid" AS txn_id, 'core_b' AS source_system, 'core_b:' || "acct_ref" AS account_id,
           LEFT("txn_timestamp", 19) AS ts_text,
           CASE "txn_type_desc" WHEN 'Cash Deposit' THEN 'CASH_DEPOSIT' WHEN 'Cash Withdrawal' THEN 'CASH_WITHDRAWAL'
                                WHEN 'ATM Withdrawal' THEN 'ATM_WITHDRAWAL' WHEN 'ACH Credit' THEN 'ACH_CREDIT'
                                WHEN 'ACH Debit' THEN 'ACH_DEBIT' WHEN 'Incoming Wire' THEN 'WIRE_IN'
                                WHEN 'Outgoing Wire' THEN 'WIRE_OUT' WHEN 'Check Paid' THEN 'CHECK_PAID'
                                WHEN 'Debit Card Purchase' THEN 'CARD_PURCHASE' WHEN 'Transfer In' THEN 'TRANSFER_IN'
                                WHEN 'Transfer Out' THEN 'TRANSFER_OUT' WHEN 'Interest Credit' THEN 'INTEREST' END AS txn_type,
           IFF("dr_cr" = 'C', 1, -1) * CAST("amount" AS DECIMAL(38, 2)) AS amount_signed_usd,
           CASE "channel_desc" WHEN 'Teller' THEN 'BRANCH' WHEN 'ATM' THEN 'ATM' WHEN 'Online Banking' THEN 'ONLINE'
                               WHEN 'Mobile App' THEN 'MOBILE' WHEN 'System' THEN 'SYSTEM' END AS channel,
           NULLIF("branch_name", '') AS branch,
           ("ctr_filed" = 'true') AS ctr_filed,
           NULLIF("counterparty", '') AS counterparty,
           NULLIF("counterparty_institution", '') AS counterparty_institution,
           _SOURCE_FILE AS source_file, _SOURCE_ROW AS source_row
      FROM BRONZE.CORE_B_TXN
),
u AS (
    SELECT txn_id, source_system, account_id,
           TRY_TO_TIMESTAMP(ts_text, 'YYYYMMDDHH24MISS') AS posted_at, txn_type, amount_signed_usd, channel,
           branch, ctr_filed, counterparty, counterparty_institution, source_file, source_row
      FROM a
    UNION ALL
    SELECT txn_id, source_system, account_id,
           TRY_TO_TIMESTAMP(ts_text, 'YYYY-MM-DD"T"HH24:MI:SS'), txn_type, amount_signed_usd, channel,
           branch, ctr_filed, counterparty, counterparty_institution, source_file, source_row
      FROM b
)
SELECT u.txn_id, u.source_system, u.account_id, acc.party_id,
       u.posted_at, CAST(u.posted_at AS DATE) AS posted_date,
       u.txn_type, IFF(u.amount_signed_usd >= 0, 'CREDIT', 'DEBIT') AS direction,
       ABS(u.amount_signed_usd) AS amount_usd, u.amount_signed_usd,
       u.channel, u.branch, u.ctr_filed, u.counterparty, u.counterparty_institution,
       u.source_file, u.source_row
  FROM u
  LEFT JOIN GOLD.ACCOUNT acc ON acc.account_id = u.account_id;

CREATE OR REPLACE DYNAMIC TABLE GOLD.ALERT
  TARGET_LAG = 'DOWNSTREAM'
  WAREHOUSE = RISK_WH
  COMMENT = 'Legacy monitoring alerts from both cores, canonical scenario, status and disposition. SYNTHETIC DATA.'
AS
WITH a AS (
    SELECT 'core_a:' || "ALERT_ID" AS alert_id, 'core_a' AS source_system, "ALERT_ID" AS source_key,
           'core_a:' || "CIF_NO" AS customer_record_id, 'core_a:' || "ACCT_NO" AS account_id,
           CASE "RULE_CD" WHEN 'LCT01' THEN 'LARGE_CASH' WHEN 'STR02' THEN 'STRUCTURING' WHEN 'VEL03' THEN 'VELOCITY'
                          WHEN 'WIR04' THEN 'HIGH_RISK_WIRE' WHEN 'RMV05' THEN 'RAPID_MOVEMENT'
                          WHEN 'DRM06' THEN 'DORMANT_ACTIVITY' END AS scenario,
           TRY_TO_DATE("ALERT_DT", 'YYYYMMDD') AS alert_date,
           CAST("ALERT_SCORE" AS INTEGER) AS legacy_score,
           CASE "ALERT_STAT" WHEN 'OPEN' THEN 'OPEN' WHEN 'WIP' THEN 'IN_PROGRESS' WHEN 'CLOSED' THEN 'CLOSED' END AS status,
           CASE "DISPO_CD" WHEN 'FP' THEN 'FALSE_POSITIVE' WHEN 'NSR' THEN 'NO_SAR_AFTER_REVIEW'
                           WHEN 'SAR' THEN 'SAR_FILED' END AS disposition,
           TRY_TO_DATE("CLOSE_DT", 'YYYYMMDD') AS closed_on,
           "ASSIGNED_TO" AS owner,
           "BR_CD" AS branch,
           _SOURCE_FILE AS source_file, _SOURCE_ROW AS source_row
      FROM BRONZE.CORE_A_AML_ALERTS
),
b AS (
    SELECT 'core_b:' || c."case_ref", 'core_b', c."case_ref", 'core_b:' || c."party_uuid", 'core_b:' || c."acct_ref",
           CASE c."scenario_name" WHEN 'Large Cash Activity' THEN 'LARGE_CASH' WHEN 'Possible Structuring' THEN 'STRUCTURING'
                                  WHEN 'High Velocity' THEN 'VELOCITY' WHEN 'High Risk Geography Wire' THEN 'HIGH_RISK_WIRE'
                                  WHEN 'Rapid Movement of Funds' THEN 'RAPID_MOVEMENT'
                                  WHEN 'Dormant Account Activity' THEN 'DORMANT_ACTIVITY' END,
           TRY_TO_DATE(LEFT(c."created_at", 10), 'YYYY-MM-DD'),
           CASE c."priority" WHEN 'P1' THEN 90 WHEN 'P2' THEN 75 ELSE 50 END,
           CASE c."state" WHEN 'NEW' THEN 'OPEN' WHEN 'IN_REVIEW' THEN 'IN_PROGRESS' WHEN 'ESCALATED' THEN 'IN_PROGRESS'
                          WHEN 'CLOSED' THEN 'CLOSED' END,
           CASE c."outcome" WHEN 'NOT_SUSPICIOUS' THEN 'FALSE_POSITIVE' WHEN 'NO_SAR_AFTER_REVIEW' THEN 'NO_SAR_AFTER_REVIEW'
                            WHEN 'SAR_FILED' THEN 'SAR_FILED' END,
           TRY_TO_DATE(LEFT(c."closed_at", 10), 'YYYY-MM-DD'),
           c."analyst",
           d."branch_name",
           c._SOURCE_FILE, c._SOURCE_ROW
      FROM BRONZE.CORE_B_CASE_ALERT c
      LEFT JOIN BRONZE.CORE_B_DEPOSIT_ACCOUNT d ON d."acct_ref" = c."acct_ref"
),
u AS (SELECT * FROM a UNION ALL SELECT * FROM b)
SELECT u.alert_id, u.source_system, u.source_key, x.party_id, u.account_id, u.scenario, u.alert_date,
       u.legacy_score, u.status, u.disposition, u.closed_on, u.owner, u.branch, u.source_file, u.source_row
  FROM u
  LEFT JOIN SILVER.PARTY_XREF x ON x.record_id = u.customer_record_id;

-- KYC profiles from both cores (structured fields from the KYC summary documents)
CREATE OR REPLACE DYNAMIC TABLE GOLD.KYC_PROFILE
  TARGET_LAG = 'DOWNSTREAM'
  WAREHOUSE = RISK_WH
  COMMENT = 'KYC profiles per source record, linked to the resolved party. SYNTHETIC DATA.'
AS
SELECT k."kyc_id" AS kyc_id, k."core" AS source_system, x.party_id,
       k."core" || ':' || k."customer_ref" AS customer_record_id,
       TRY_TO_DATE(k."review_date", 'YYYY-MM-DD') AS review_date,
       k."risk_rating" AS risk_rating,
       k."occupation_or_business" AS occupation,
       CAST(k."expected_monthly_cash_usd" AS DECIMAL(38, 2)) AS expected_monthly_cash_usd,
       CAST(k."expected_monthly_wires_usd" AS DECIMAL(38, 2)) AS expected_monthly_wires_usd,
       k."source_of_funds" AS source_of_funds,
       k."summary_text" AS summary_text,
       k._SOURCE_FILE AS source_file, k._SOURCE_ROW AS source_row
  FROM BRONZE.DOC_KYC_SUMMARIES k
  LEFT JOIN SILVER.PARTY_XREF x ON x.record_id = k."core" || ':' || k."customer_ref";

CREATE OR REPLACE DYNAMIC TABLE GOLD.BRANCH
  TARGET_LAG = 'DOWNSTREAM'
  WAREHOUSE = RISK_WH
  COMMENT = 'Branches of both cores. SYNTHETIC DATA.'
AS
SELECT 'core_a:' || "BR_CD" AS branch_id, 'core_a' AS source_system, "BR_CD" AS branch_code, "BR_NM" AS branch_name,
       "CITY" AS city, "ST" AS state
  FROM BRONZE.CORE_A_BRANCHES
UNION ALL
SELECT 'core_b:' || "branch_name", 'core_b', "branch_name", "branch_name", "branch_city", "branch_state"
  FROM BRONZE.CORE_B_BRANCH;
