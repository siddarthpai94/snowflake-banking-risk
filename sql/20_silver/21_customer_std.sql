-- F2 Silver: one standardised row per customer record from every onboarded core.
-- Each core's quirks (name order, date formats, token prefixes, address style) are
-- normalised here so matching compares like with like. Lineage columns carry through.
USE ROLE RISK_ADMIN;
USE WAREHOUSE RISK_WH;
USE DATABASE RISK_COPILOT;

CREATE OR REPLACE DYNAMIC TABLE SILVER.CUSTOMER_STD
  TARGET_LAG = 'DOWNSTREAM'
  WAREHOUSE = RISK_WH
  COMMENT = 'Standardised customer records from all cores (one row per source record). SYNTHETIC DATA.'
AS
WITH core_a AS (
    SELECT 'core_a' AS source_system,
           "CIF_NO" AS source_key,
           IFF("CUST_TYPE" = 'B', 'ORG', 'PERSON') AS party_kind,
           NULLIF(UPPER(TRIM("FIRST_NM")), '') AS first_name,
           NULLIF(UPPER(TRIM("MID_INIT")), '') AS middle_initial,
           NULLIF(UPPER(TRIM("LAST_NM")), '') AS last_name,
           NULLIF(UPPER(TRIM("SFX")), '') AS name_suffix,
           NULLIF(UPPER(TRIM("BUS_NM")), '') AS org_name,
           "BIRTH_DT" AS dob_raw,
           IFF("BIRTH_DT" = '00000000', NULL, TRY_TO_DATE("BIRTH_DT", 'YYYYMMDD')) AS dob_parsed,
           NULLIF(LOWER(TRIM("TAX_ID_TKN")), '') AS tax_token,
           UPPER(TRIM("ADDR_LN1")) AS street_raw,
           UPPER(TRIM("CITY")) AS city,
           UPPER(TRIM("ST")) AS state,
           TRIM("ZIP5") AS zip_raw,
           REGEXP_REPLACE("PHONE_NO", '[^0-9]', '') AS phone_digits,
           LOWER(TRIM("EMAIL_ADDR")) AS email,
           "OCCUP_DESC" AS occupation,
           "RISK_RTG" AS risk_rating_raw,
           _SOURCE_FILE AS source_file,
           _SOURCE_ROW AS source_row
      FROM BRONZE.CORE_A_CUSTOMERS
),
core_b_raw AS (
    SELECT *,
           TRIM(SPLIT_PART("full_name", ',', 1)) AS nm_last,
           TRIM(SPLIT_PART("full_name", ',', 2)) AS nm_rest,
           TRIM(SPLIT_PART("city_state_zip", ',', 1)) AS csz_city,
           TRIM(SPLIT_PART("city_state_zip", ',', 2)) AS csz_rest
      FROM BRONZE.CORE_B_PARTY
),
core_b AS (
    SELECT 'core_b' AS source_system,
           "party_uuid" AS source_key,
           IFF("party_kind" = 'ORG', 'ORG', 'PERSON') AS party_kind,
           IFF("party_kind" = 'ORG', NULL, NULLIF(SPLIT_PART(nm_rest, ' ', 1), '')) AS first_name,
           IFF("party_kind" = 'ORG', NULL, IFF(LENGTH(SPLIT_PART(nm_rest, ' ', 2)) = 1, SPLIT_PART(nm_rest, ' ', 2), NULL)) AS middle_initial,
           IFF("party_kind" = 'ORG', NULL, NULLIF(nm_last, '')) AS last_name,
           IFF("party_kind" = 'ORG', NULL,
               CASE WHEN SPLIT_PART(nm_rest, ' ', 3) IN ('JR', 'SR', 'II', 'III', 'IV') THEN SPLIT_PART(nm_rest, ' ', 3)
                    WHEN SPLIT_PART(nm_rest, ' ', 2) IN ('JR', 'SR', 'II', 'III', 'IV') THEN SPLIT_PART(nm_rest, ' ', 2) END) AS name_suffix,
           IFF("party_kind" = 'ORG', UPPER(TRIM("full_name")), NULL) AS org_name,
           "dob" AS dob_raw,
           TRY_TO_DATE("dob", 'MM/DD/YYYY') AS dob_parsed,
           NULLIF(REGEXP_REPLACE(LOWER(TRIM("ssn_token")), '^tkn_', ''), '') AS tax_token,
           UPPER(TRIM("street")) AS street_raw,
           UPPER(csz_city) AS city,
           UPPER(SPLIT_PART(csz_rest, ' ', 1)) AS state,
           SPLIT_PART(csz_rest, ' ', 2) AS zip_raw,
           REGEXP_REPLACE("phone_num", '[^0-9]', '') AS phone_digits,
           LOWER(TRIM("email_addr")) AS email,
           "employer_or_industry" AS occupation,
           "kyc_risk" AS risk_rating_raw,
           _SOURCE_FILE AS source_file,
           _SOURCE_ROW AS source_row
      FROM core_b_raw
),
unioned AS (
    SELECT * FROM core_a
    UNION ALL
    SELECT * FROM core_b
)
SELECT source_system,
       source_key,
       source_system || ':' || source_key AS record_id,
       party_kind,
       first_name,
       middle_initial,
       last_name,
       name_suffix,
       org_name,
       COALESCE(org_name, TRIM(COALESCE(first_name, '') || ' ' || COALESCE(last_name, ''))) AS display_name,
       IFF(dob_parsed > CURRENT_DATE() OR dob_parsed < '1900-01-01', NULL, dob_parsed) AS birth_date,
       dob_raw,
       dob_parsed,
       tax_token,
       REGEXP_SUBSTR(street_raw, '^[0-9]+') AS street_no,
       -- USPS-style suffix abbreviations so '12 OAK STREET' and '12 OAK ST' compare equal
       REGEXP_REPLACE(REGEXP_REPLACE(REGEXP_REPLACE(REGEXP_REPLACE(REGEXP_REPLACE(REGEXP_REPLACE(
       REGEXP_REPLACE(REGEXP_REPLACE(REGEXP_REPLACE(
           TRIM(REGEXP_REPLACE(street_raw, '^[0-9]+', '')),
           ' STREET$', ' ST'), ' AVENUE$', ' AVE'), ' ROAD$', ' RD'), ' DRIVE$', ' DR'), ' LANE$', ' LN'),
           ' COURT$', ' CT'), ' BOULEVARD$', ' BLVD'), ' PLACE$', ' PL'), ' TERRACE$', ' TER') AS street_name,
       city,
       state,
       IFF(REGEXP_LIKE(zip_raw, '^[0-9]{5}$') AND zip_raw <> '00000', zip_raw, NULL) AS zip5,
       zip_raw,
       IFF(LENGTH(phone_digits) = 10, phone_digits, NULL) AS phone,
       email,
       occupation,
       risk_rating_raw,
       source_file,
       source_row
  FROM unioned;
