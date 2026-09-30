-- F5 document search without AI: one searchable row per policy section, investigator note and KYC summary.
-- Each row carries a ready-made citation and its lineage (source_file, source_row or page).
-- search_text is lower-case with punctuation removed and padded with spaces, so a term can be matched at
-- the start of a word (' aggreg' matches aggregate, aggregated, aggregation). Queries: search/search.py.
USE ROLE RISK_ADMIN;
USE WAREHOUSE RISK_WH;
USE DATABASE RISK_COPILOT;

CREATE OR REPLACE DYNAMIC TABLE SEARCH.DOC_CHUNK
  TARGET_LAG = 'DOWNSTREAM'
  WAREHOUSE = RISK_WH
  COMMENT = 'Searchable documents with citations: policy sections, investigator notes, KYC summaries. SYNTHETIC DATA.'
AS
WITH policy AS (
    SELECT chunk_id AS doc_id, 'POLICY' AS doc_type,
           section AS title,
           'BSA/AML Policy v7.2, section ' || section || IFF(parent_section <> '', ' (' || parent_section || ')', '')
             || ', page ' || CAST(page AS VARCHAR) AS citation,
           CAST(NULL AS VARCHAR) AS party_id, CAST(NULL AS VARCHAR) AS source_system, CAST(NULL AS DATE) AS doc_date,
           page, section, chunk_text AS body,
           parent_section || ' ' || section || ' ' || section || ' ' || chunk_text AS raw_text,
           document AS source_file, CAST(NULL AS BIGINT) AS source_row
      FROM SEARCH.POLICY_CHUNK
),
notes AS (
    SELECT n."note_id", 'NOTE',
           'Investigator note ' || n."note_id" || ' on ' || n."core" || ' alert ' || n."alert_ref",
           'Investigator note ' || n."note_id" || ' (' || n."core" || ' alert ' || n."alert_ref" || ', '
             || n."author" || ', ' || LEFT(n."created_at", 10) || ')',
           x.party_id, n."core", TRY_TO_DATE(LEFT(n."created_at", 10), 'YYYY-MM-DD'),
           CAST(NULL AS INTEGER), CAST(NULL AS VARCHAR), n."note_text",
           n."note_text",
           n._SOURCE_FILE, n._SOURCE_ROW
      FROM BRONZE.DOC_INVESTIGATOR_NOTES n
      LEFT JOIN SILVER.PARTY_XREF x ON x.record_id = n."core" || ':' || n."customer_ref"
),
kyc AS (
    SELECT k."kyc_id", 'KYC',
           'KYC summary ' || k."kyc_id" || ' (' || k."core" || ')',
           'KYC summary ' || k."kyc_id" || ' (' || k."core" || ' customer ' || k."customer_ref" || ', reviewed '
             || k."review_date" || ')',
           x.party_id, k."core", TRY_TO_DATE(k."review_date", 'YYYY-MM-DD'),
           CAST(NULL AS INTEGER), CAST(NULL AS VARCHAR), k."summary_text",
           k."occupation_or_business" || ' ' || k."summary_text",
           k._SOURCE_FILE, k._SOURCE_ROW
      FROM BRONZE.DOC_KYC_SUMMARIES k
      LEFT JOIN SILVER.PARTY_XREF x ON x.record_id = k."core" || ':' || k."customer_ref"
),
u AS (SELECT * FROM policy UNION ALL SELECT * FROM notes UNION ALL SELECT * FROM kyc)
SELECT doc_id, doc_type, title, citation, party_id, source_system, doc_date, page, section, body,
       ' ' || TRIM(REGEXP_REPLACE(LOWER(raw_text), '[^a-z0-9$]+', ' ')) || ' ' AS search_text,
       source_file, source_row
  FROM u;

GRANT USAGE ON SCHEMA SEARCH TO ROLE RISK_ANALYST;
GRANT SELECT ON ALL TABLES IN SCHEMA SEARCH TO ROLE RISK_ANALYST;
GRANT SELECT ON ALL DYNAMIC TABLES IN SCHEMA SEARCH TO ROLE RISK_ANALYST;
