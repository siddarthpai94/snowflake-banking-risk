-- F2 entity resolution: candidate pairs across cores, evidence, and a rule-based decision.
--
-- Decisions are deterministic rules with hard guards, so every link can be explained:
--   * different non-null tax-id tokens      -> REJECT (tokens come from one shared vault)
--   * same token and same date of birth    -> AUTO_LINK
--   * no token to compare: name + DOB must be corroborated by address or phone to AUTO_LINK;
--     otherwise the pair goes to REVIEW (twins, junior/senior, same name and DOB, changed surname)
-- A surname matches when Jaro-Winkler >= 88 or it is one keystroke away (KERR / KEIR).
-- match_score is a 0-100 evidence summary for display; it does not make the decision.
USE ROLE RISK_ADMIN;
USE WAREHOUSE RISK_WH;
USE DATABASE RISK_COPILOT;

CREATE OR REPLACE DYNAMIC TABLE SILVER.MATCH_CANDIDATES
  TARGET_LAG = 'DOWNSTREAM'
  WAREHOUSE = RISK_WH
  COMMENT = 'Cross-core candidate pairs with evidence, score, decision and reason codes. SYNTHETIC DATA.'
AS
WITH a AS (SELECT * FROM SILVER.CUSTOMER_STD WHERE source_system = 'core_a'),
     b AS (SELECT * FROM SILVER.CUSTOMER_STD WHERE source_system = 'core_b'),
pairs AS (
    -- block 1: same tax-id token
    SELECT a.record_id AS a_id, b.record_id AS b_id
      FROM a JOIN b ON a.tax_token = b.tax_token
    UNION
    -- block 2: same date of birth and surname initial (people only)
    SELECT a.record_id, b.record_id
      FROM a JOIN b ON a.birth_date = b.birth_date AND LEFT(a.last_name, 1) = LEFT(b.last_name, 1)
     WHERE a.party_kind = 'PERSON' AND b.party_kind = 'PERSON'
    UNION
    -- block 4: same date of birth and ZIP (catches typos in the first letters of the surname)
    SELECT a.record_id, b.record_id
      FROM a JOIN b ON a.birth_date = b.birth_date AND a.zip5 = b.zip5
     WHERE a.party_kind = 'PERSON' AND b.party_kind = 'PERSON'
    UNION
    -- block 3: same ZIP and surname (catches records with no DOB)
    SELECT a.record_id, b.record_id
      FROM a JOIN b ON a.zip5 = b.zip5 AND a.last_name = b.last_name
     WHERE a.party_kind = 'PERSON' AND b.party_kind = 'PERSON'
),
ev AS (
    SELECT p.a_id, p.b_id,
           a.source_key AS a_key, b.source_key AS b_key,
           a.party_kind AS a_kind, b.party_kind AS b_kind,
           a.display_name AS a_name, b.display_name AS b_name,
           (a.tax_token IS NOT NULL AND b.tax_token IS NOT NULL) AS tin_both,
           COALESCE(a.tax_token = b.tax_token, FALSE) AS tin_equal,
           (a.birth_date IS NOT NULL AND b.birth_date IS NOT NULL) AS dob_both,
           COALESCE(a.birth_date = b.birth_date, FALSE) AS dob_equal,
           COALESCE(JAROWINKLER_SIMILARITY(a.last_name, b.last_name), 0) AS last_sim,
           COALESCE(JAROWINKLER_SIMILARITY(a.first_name, b.first_name), 0) AS first_sim,
           COALESCE(EDITDISTANCE(a.last_name, b.last_name), 99) AS last_edits,
           COALESCE(a.first_name = b.first_name, FALSE) AS first_exact,
           (n1.nickname IS NOT NULL OR n2.nickname IS NOT NULL) AS first_nickname,
           COALESCE(a.street_no = b.street_no AND a.street_name = b.street_name, FALSE) AS addr_equal,
           COALESCE(a.zip5 = b.zip5, FALSE) AS zip_equal,
           COALESCE(a.phone = b.phone, FALSE) AS phone_equal,
           COALESCE(a.name_suffix <> b.name_suffix, FALSE) AS suffix_conflict,
           COALESCE(a.org_name = b.org_name, FALSE) AS org_name_equal
      FROM pairs p
      JOIN a ON a.record_id = p.a_id
      JOIN b ON b.record_id = p.b_id
      LEFT JOIN SILVER.REF_NICKNAME n1 ON n1.nickname = b.first_name AND n1.given_name = a.first_name
      LEFT JOIN SILVER.REF_NICKNAME n2 ON n2.nickname = a.first_name AND n2.given_name = b.first_name
),
flags AS (
    SELECT *,
           (tin_both AND NOT tin_equal) AS tin_conflict,
           (dob_both AND NOT dob_equal) AS dob_conflict,
           (last_sim >= 88 OR last_edits <= 1) AS last_match,
           (first_exact OR first_nickname OR first_sim >= 90) AS first_match
      FROM ev
)
SELECT a_id, b_id, a_key, b_key, a_kind, b_kind, a_name, b_name,
       tin_equal, tin_conflict, dob_equal, dob_conflict, last_sim, first_sim, first_nickname,
       last_match, first_match, addr_equal, zip_equal, phone_equal, suffix_conflict,
       GREATEST(0, LEAST(100,
           40 * IFF(tin_equal, 1, 0) + 25 * IFF(dob_equal, 1, 0) + 10 * IFF(last_match, 1, 0)
         + 10 * IFF(first_match, 1, 0) + 10 * IFF(addr_equal, 1, 0) + 5 * IFF(phone_equal, 1, 0)
         - 60 * IFF(tin_conflict, 1, 0) - 30 * IFF(dob_conflict, 1, 0) - 20 * IFF(suffix_conflict, 1, 0))) AS match_score,
       CASE
           WHEN a_kind <> b_kind THEN 'REJECT'
           WHEN tin_conflict THEN 'REJECT'
           WHEN a_kind = 'ORG' THEN IFF(tin_equal, 'AUTO_LINK', IFF(org_name_equal, 'REVIEW', 'REJECT'))
           WHEN tin_equal AND dob_equal THEN 'AUTO_LINK'
           WHEN tin_equal AND NOT dob_both AND last_match THEN 'AUTO_LINK'
           WHEN tin_equal THEN 'REVIEW'
           WHEN dob_equal AND last_match AND first_match AND (addr_equal OR phone_equal) AND NOT suffix_conflict THEN 'AUTO_LINK'
           WHEN dob_equal AND last_match THEN 'REVIEW'
           WHEN last_match AND first_match AND (addr_equal OR phone_equal) THEN 'REVIEW'
           WHEN dob_equal AND first_match AND addr_equal AND phone_equal THEN 'REVIEW'  -- surname changed?
           ELSE 'REJECT'
       END AS decision,
       RTRIM(
           IFF(tin_equal, 'TAX_TOKEN_EQUAL;', '') || IFF(tin_conflict, 'TAX_TOKEN_CONFLICT;', '')
        || IFF(NOT tin_both, 'TAX_TOKEN_MISSING;', '')
        || IFF(dob_equal, 'DOB_EQUAL;', '') || IFF(dob_conflict, 'DOB_CONFLICT;', '')
        || IFF(last_match, 'SURNAME_MATCH;', 'SURNAME_DIFFERENT;')
        || IFF(first_exact, 'GIVEN_NAME_EQUAL;', IFF(first_nickname, 'GIVEN_NAME_NICKNAME;', IFF(first_match, 'GIVEN_NAME_SIMILAR;', 'GIVEN_NAME_DIFFERENT;')))
        || IFF(addr_equal, 'ADDRESS_EQUAL;', '') || IFF(phone_equal, 'PHONE_EQUAL;', '')
        || IFF(suffix_conflict, 'SUFFIX_CONFLICT;', ''), ';') AS reason_codes
  FROM flags;
