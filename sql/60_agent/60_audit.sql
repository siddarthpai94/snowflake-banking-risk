-- F6 audit trail: every question asked of the copilot, the route chosen, the rule that chose it and
-- the citations behind the answer. Written by agent/answer.py:log_question. No AI anywhere in the path.
USE ROLE RISK_ADMIN;
USE WAREHOUSE RISK_WH;
USE DATABASE RISK_COPILOT;

CREATE TABLE IF NOT EXISTS AUDIT.QUESTION_LOG (
    log_id      VARCHAR,
    logged_at   TIMESTAMP_NTZ,
    app_user    VARCHAR,
    question    VARCHAR,
    route       VARCHAR,
    rule        VARCHAR,
    answered_as VARCHAR,
    headline    VARCHAR,
    row_count   INTEGER,
    citations   VARCHAR,
    party_id    VARCHAR
);

GRANT SELECT, INSERT ON TABLE AUDIT.QUESTION_LOG TO ROLE RISK_INVESTIGATOR;
