-- F2 resolution: every source record gets a party_id; low-confidence pairs go to a review queue.
-- A record joins another record's party only through a mutual-best AUTO_LINK pair, so one
-- weak pair can never chain two different people together.
USE ROLE RISK_ADMIN;
USE WAREHOUSE RISK_WH;
USE DATABASE RISK_COPILOT;

CREATE OR REPLACE DYNAMIC TABLE SILVER.AUTO_LINKS
  TARGET_LAG = 'DOWNSTREAM'
  WAREHOUSE = RISK_WH
  COMMENT = 'Accepted cross-core links: AUTO_LINK pairs that are each side''s best candidate.'
AS
WITH auto AS (
    SELECT a_id, b_id, match_score, reason_codes,
           ROW_NUMBER() OVER (PARTITION BY a_id ORDER BY match_score DESC, b_id) AS rank_a,
           ROW_NUMBER() OVER (PARTITION BY b_id ORDER BY match_score DESC, a_id) AS rank_b
      FROM SILVER.MATCH_CANDIDATES
     WHERE decision = 'AUTO_LINK'
)
SELECT a_id, b_id, match_score, reason_codes
  FROM auto
 WHERE rank_a = 1 AND rank_b = 1;

CREATE OR REPLACE DYNAMIC TABLE SILVER.PARTY_XREF
  TARGET_LAG = 'DOWNSTREAM'
  WAREHOUSE = RISK_WH
  COMMENT = 'Source record to party_id. Linked records share the party of their Core A record.'
AS
SELECT s.record_id, s.source_system, s.source_key, s.party_kind, s.display_name,
       'PTY_' || LEFT(MD5(COALESCE(l1.a_id, l2.a_id, s.record_id)), 16) AS party_id,
       IFF(l1.a_id IS NOT NULL OR l2.a_id IS NOT NULL, 'LINKED', 'SINGLE') AS link_status,
       COALESCE(l1.match_score, l2.match_score) AS link_score,
       COALESCE(l1.reason_codes, l2.reason_codes) AS link_reasons,
       s.source_file, s.source_row
  FROM SILVER.CUSTOMER_STD s
  LEFT JOIN SILVER.AUTO_LINKS l1 ON l1.a_id = s.record_id
  LEFT JOIN SILVER.AUTO_LINKS l2 ON l2.b_id = s.record_id;

-- Human review queue: REVIEW pairs where neither record is already linked.
CREATE OR REPLACE DYNAMIC TABLE SILVER.MATCH_REVIEW_QUEUE
  TARGET_LAG = 'DOWNSTREAM'
  WAREHOUSE = RISK_WH
  COMMENT = 'Uncertain pairs for an investigator to confirm or reject (F2 exception queue).'
AS
SELECT c.a_id, c.b_id, c.a_name, c.b_name, c.match_score, c.reason_codes,
       CASE
           WHEN c.dob_conflict THEN 'Names and address agree but dates of birth differ (possible relatives)'
           WHEN NOT c.first_match THEN 'Same surname and date of birth but different given names (possible twins)'
           WHEN NOT c.last_match THEN 'Given name, date of birth, address and phone agree but the surname differs (name change?)'
           WHEN NOT (c.addr_equal OR c.phone_equal) THEN 'Name and date of birth agree but nothing else corroborates'
           ELSE 'Evidence incomplete'
       END AS review_reason
  FROM SILVER.MATCH_CANDIDATES c
  LEFT JOIN SILVER.AUTO_LINKS la ON la.a_id = c.a_id
  LEFT JOIN SILVER.AUTO_LINKS lb ON lb.b_id = c.b_id
 WHERE c.decision = 'REVIEW'
   AND la.a_id IS NULL
   AND lb.b_id IS NULL;
