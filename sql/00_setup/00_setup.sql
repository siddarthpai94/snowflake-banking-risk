-- One-time account setup for the Sahasranshu Risk Copilot.
-- Run as ACCOUNTADMIN on a fresh trial account:  snow sql -f sql/00_setup/00_setup.sql
-- ALL DATA IS SYNTHETIC. No real customer data may ever be loaded into this account.

USE ROLE ACCOUNTADMIN;

-- Roles: analysts see masked PII (F11), investigators see full detail, admin builds.
CREATE ROLE IF NOT EXISTS RISK_ANALYST      COMMENT = 'Reads Gold, semantic views and the app; PII masked';
CREATE ROLE IF NOT EXISTS RISK_INVESTIGATOR COMMENT = 'Analyst plus unmasked PII and case actions';
CREATE ROLE IF NOT EXISTS RISK_ADMIN        COMMENT = 'Builds and owns every object';
GRANT ROLE RISK_ANALYST TO ROLE RISK_INVESTIGATOR;
GRANT ROLE RISK_INVESTIGATOR TO ROLE RISK_ADMIN;
GRANT ROLE RISK_ADMIN TO ROLE SYSADMIN;
SET setup_user = CURRENT_USER();
GRANT ROLE RISK_ADMIN TO USER IDENTIFIER($setup_user);

-- No AI: the copilot uses plain SQL, rules and templates only. No Cortex AI role is granted.

-- Smallest warehouse, suspends after 60 seconds (protects trial credits)
CREATE WAREHOUSE IF NOT EXISTS RISK_WH
  WAREHOUSE_SIZE = XSMALL AUTO_SUSPEND = 60 AUTO_RESUME = TRUE INITIALLY_SUSPENDED = TRUE
  COMMENT = 'Risk Copilot build and app warehouse';
GRANT USAGE, OPERATE ON WAREHOUSE RISK_WH TO ROLE RISK_ANALYST;
GRANT ALL ON WAREHOUSE RISK_WH TO ROLE RISK_ADMIN;

CREATE DATABASE IF NOT EXISTS RISK_COPILOT COMMENT = 'Sahasranshu Risk Copilot - SYNTHETIC DATA ONLY';
GRANT OWNERSHIP ON DATABASE RISK_COPILOT TO ROLE RISK_ADMIN COPY CURRENT GRANTS;
GRANT CREATE DATABASE ON ACCOUNT TO ROLE RISK_ADMIN;

USE ROLE RISK_ADMIN;
USE WAREHOUSE RISK_WH;
USE DATABASE RISK_COPILOT;

CREATE SCHEMA IF NOT EXISTS BRONZE   COMMENT = 'Raw files as delivered, one table per source file, with lineage columns';
CREATE SCHEMA IF NOT EXISTS SILVER   COMMENT = 'Typed, cleaned, standardised per source; entity resolution; data-quality results';
CREATE SCHEMA IF NOT EXISTS GOLD     COMMENT = 'Canonical banking model across all cores';
CREATE SCHEMA IF NOT EXISTS SEMANTIC COMMENT = 'Governed metric views and the reviewed question catalogue (F3)';
CREATE SCHEMA IF NOT EXISTS APP      COMMENT = 'Reserved for app objects (F8)';
CREATE SCHEMA IF NOT EXISTS AUDIT    COMMENT = 'Copilot audit log, approvals, case outputs (F7)';
CREATE SCHEMA IF NOT EXISTS EVAL     COMMENT = 'Ground truth for acceptance tests only. Never granted to app or analyst roles.';

-- CSV files are gzip-compressed with one header row; empty fields load as NULL.
CREATE FILE FORMAT IF NOT EXISTS BRONZE.FF_CSV_GZ
  TYPE = CSV COMPRESSION = GZIP SKIP_HEADER = 1 FIELD_OPTIONALLY_ENCLOSED_BY = '"'
  EMPTY_FIELD_AS_NULL = TRUE NULL_IF = ('') ENCODING = 'UTF8'
  ERROR_ON_COLUMN_COUNT_MISMATCH = TRUE;

-- Server-side encryption for staged files.
CREATE STAGE IF NOT EXISTS BRONZE.RAW_STAGE
  DIRECTORY = (ENABLE = TRUE) ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')
  COMMENT = 'Synthetic core extracts and documents';
CREATE STAGE IF NOT EXISTS EVAL.GT_STAGE
  ENCRYPTION = (TYPE = 'SNOWFLAKE_SSE')
  COMMENT = 'Ground-truth files for acceptance tests';

-- Analysts read Gold, semantic and app objects only. EVAL and BRONZE stay private to RISK_ADMIN.
GRANT USAGE ON DATABASE RISK_COPILOT TO ROLE RISK_ANALYST;
GRANT USAGE ON SCHEMA GOLD TO ROLE RISK_ANALYST;
GRANT USAGE ON SCHEMA SEMANTIC TO ROLE RISK_ANALYST;
GRANT USAGE ON SCHEMA APP TO ROLE RISK_ANALYST;
GRANT SELECT ON FUTURE TABLES IN SCHEMA GOLD TO ROLE RISK_ANALYST;
GRANT SELECT ON FUTURE VIEWS IN SCHEMA GOLD TO ROLE RISK_ANALYST;
GRANT SELECT ON FUTURE DYNAMIC TABLES IN SCHEMA GOLD TO ROLE RISK_ANALYST;
GRANT USAGE ON SCHEMA AUDIT TO ROLE RISK_INVESTIGATOR;

-- Setup check: run 90_environment_check.sql next.
