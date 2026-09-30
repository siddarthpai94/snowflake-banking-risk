-- F2 data-quality checks: completeness, validity, duplicate keys and orphan records.
-- One row per exception, with the rule, severity and the source row it came from.
USE ROLE RISK_ADMIN;
USE WAREHOUSE RISK_WH;
USE DATABASE RISK_COPILOT;

CREATE OR REPLACE DYNAMIC TABLE SILVER.DQ_EXCEPTIONS
  TARGET_LAG = 'DOWNSTREAM'
  WAREHOUSE = RISK_WH
  COMMENT = 'Data-quality exceptions from every onboarded core. SYNTHETIC DATA.'
AS
SELECT 'DQ_MISSING_DOB' AS rule_id, 'WARNING' AS severity, source_system, 'CUSTOMER' AS entity,
       source_key AS record_key, 'birth_date' AS field, dob_raw AS observed_value, source_file, source_row
  FROM SILVER.CUSTOMER_STD
 WHERE party_kind = 'PERSON'
   AND dob_parsed IS NULL
UNION ALL
SELECT 'DQ_FUTURE_DOB', 'CRITICAL', source_system, 'CUSTOMER', source_key, 'birth_date', dob_raw, source_file, source_row
  FROM SILVER.CUSTOMER_STD
 WHERE party_kind = 'PERSON' AND dob_parsed > CURRENT_DATE()
UNION ALL
SELECT 'DQ_INVALID_ZIP', 'WARNING', source_system, 'CUSTOMER', source_key, 'zip', zip_raw, source_file, source_row
  FROM SILVER.CUSTOMER_STD
 WHERE zip5 IS NULL
UNION ALL
SELECT 'DQ_DUPLICATE_KEY', 'CRITICAL', 'core_a', 'ACCOUNT', "ACCT_NO", 'ACCT_NO',
       COUNT(*)::VARCHAR || ' rows', MIN(_SOURCE_FILE), MIN(_SOURCE_ROW)
  FROM BRONZE.CORE_A_ACCOUNTS
 GROUP BY "ACCT_NO"
HAVING COUNT(*) > 1
UNION ALL
SELECT 'DQ_ORPHAN_ACCOUNT', 'CRITICAL', 'core_b', 'ACCOUNT', d."acct_ref", 'party_uuid', d."party_uuid",
       d._SOURCE_FILE, d._SOURCE_ROW
  FROM BRONZE.CORE_B_DEPOSIT_ACCOUNT d
  LEFT JOIN BRONZE.CORE_B_PARTY p ON p."party_uuid" = d."party_uuid"
 WHERE p."party_uuid" IS NULL
UNION ALL
SELECT 'DQ_ORPHAN_ACCOUNT', 'CRITICAL', 'core_a', 'ACCOUNT', d."ACCT_NO", 'CIF_NO', d."CIF_NO",
       d._SOURCE_FILE, d._SOURCE_ROW
  FROM BRONZE.CORE_A_ACCOUNTS d
  LEFT JOIN BRONZE.CORE_A_CUSTOMERS c ON c."CIF_NO" = d."CIF_NO"
 WHERE c."CIF_NO" IS NULL;
