-- Wednesday setup check: is every capability the build plan depends on available here?
-- Run as RISK_ADMIN after 00_setup.sql:  snow sql -f sql/00_setup/90_capability_check.sql
-- Any statement that errors marks a capability to swap for the plan's fallback
-- (AI_COMPLETE plus plain SQL). Record the result in docs/capability_check.md.

USE ROLE RISK_ADMIN;
USE WAREHOUSE RISK_WH;
USE DATABASE RISK_COPILOT;

SELECT CURRENT_ACCOUNT() AS account, CURRENT_REGION() AS region, CURRENT_VERSION() AS version;

-- F4/F7: LLM functions. If a model is not in this region, try another or enable cross-region inference.
SELECT AI_COMPLETE('llama3.1-8b', 'Reply with the single word OK.') AS ai_complete_check;
SELECT AI_CLASSIFY('Customer deposited cash just under ten thousand dollars at three branches.',
                   ['possible structuring', 'routine activity']) AS ai_classify_check;
-- F2: similarity functions available for entity resolution
SELECT AI_SIMILARITY('Robert Smith, 12 Oak St', 'Bob Smith, 12 Oak Street') AS ai_similarity_check,
       JAROWINKLER_SIMILARITY('ROBERT SMITH', 'BOB SMITH') AS jarowinkler_check,
       EDITDISTANCE('Harrison', 'Harison') AS editdistance_check;

-- F3/F5/F6/F8: object types exist in this account (an empty result is fine; an error is not)
SHOW SEMANTIC VIEWS IN ACCOUNT;
SHOW CORTEX SEARCH SERVICES IN ACCOUNT;
SHOW AGENTS IN ACCOUNT;
SHOW STREAMLITS IN ACCOUNT;
SHOW DYNAMIC TABLES IN ACCOUNT;
