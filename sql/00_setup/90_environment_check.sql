-- Environment check after setup. No AI features are used or needed.
-- Expect: your region and version, RISK_WH (XSMALL, auto-suspend 60), and the schemas BRONZE, SILVER, GOLD, SEMANTIC, APP, AUDIT and EVAL
-- (SEARCH is created later by 50_search/50_policy_chunks.sql).
USE ROLE RISK_ADMIN;
USE WAREHOUSE RISK_WH;
USE DATABASE RISK_COPILOT;

SELECT CURRENT_REGION() AS region, CURRENT_VERSION() AS version, CURRENT_ROLE() AS role, CURRENT_WAREHOUSE() AS warehouse;
SHOW WAREHOUSES LIKE 'RISK_WH';
SHOW SCHEMAS IN DATABASE RISK_COPILOT;
