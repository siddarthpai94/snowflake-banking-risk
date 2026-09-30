-- F7 audit-ready outputs: every draft, its frozen evidence and every approval decision.
-- Written by outputs/case_store.py. An output is final only with an APPROVED decision by someone other
-- than its author (config/bank_demo.yaml: report.approval_required, report.approver_cannot_be_author).
USE ROLE RISK_ADMIN;
USE WAREHOUSE RISK_WH;
USE DATABASE RISK_COPILOT;

CREATE TABLE IF NOT EXISTS AUDIT.CASE_OUTPUT (
    output_id      VARCHAR,
    output_type    VARCHAR,        -- CASE_NARRATIVE
    party_id       VARCHAR,
    subject        VARCHAR,
    author         VARCHAR,
    created_at     TIMESTAMP_NTZ,
    generator      VARCHAR,        -- code and template version that produced the text
    evidence_json  VARCHAR,        -- frozen evidence snapshot: every fact the text uses
    evidence_sha256 VARCHAR,
    content_md     VARCHAR,
    content_sha256 VARCHAR
);

CREATE TABLE IF NOT EXISTS AUDIT.CASE_APPROVAL (
    approval_id    VARCHAR,
    output_id      VARCHAR,
    decision       VARCHAR,        -- APPROVED | REJECTED
    approver       VARCHAR,
    decided_at     TIMESTAMP_NTZ,
    content_sha256 VARCHAR,        -- the exact text that was approved
    comment_text   VARCHAR
);

-- Status of every output: DRAFT until a decision exists; the latest decision wins
CREATE OR REPLACE VIEW AUDIT.V_CASE_STATUS AS
SELECT o.output_id, o.output_type, o.subject, o.author, o.created_at,
       COALESCE(d.decision, 'DRAFT') AS status, d.approver, d.decided_at, d.comment_text,
       (d.content_sha256 = o.content_sha256) AS approved_text_matches
  FROM AUDIT.CASE_OUTPUT o
  LEFT JOIN (SELECT *, ROW_NUMBER() OVER (PARTITION BY output_id ORDER BY decided_at DESC) AS rn
               FROM AUDIT.CASE_APPROVAL) d
    ON d.output_id = o.output_id AND d.rn = 1;

GRANT SELECT, INSERT ON TABLE AUDIT.CASE_OUTPUT TO ROLE RISK_INVESTIGATOR;
GRANT SELECT, INSERT ON TABLE AUDIT.CASE_APPROVAL TO ROLE RISK_INVESTIGATOR;
GRANT SELECT ON VIEW AUDIT.V_CASE_STATUS TO ROLE RISK_INVESTIGATOR;
