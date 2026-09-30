"""Schema registry: the single source of truth for every file the generator writes.

The generator validates its output against these column lists, and
scripts/emit_bronze_sql.py renders the Snowflake Bronze DDL and COPY statements
from them, so files and load SQL cannot drift apart.

Core A and Core B deliberately share no column names, ID formats or date formats.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class Table:
    name: str            # Bronze table name in Snowflake
    path: str            # relative output path
    columns: tuple       # (column, description)
    source: str          # core_a | core_b | core_c | documents | ground_truth
    description: str


def _t(name, path, source, description, cols):
    return Table(name, path, tuple(cols), source, description)


CORE_A = [
    _t("CORE_A_CUSTOMERS", "core_a/customers.csv.gz", "core_a",
       "Kestrel Valley legacy core: customer master (CIF)", [
           ("CIF_NO", "9-digit customer information file number"),
           ("CUST_TYPE", "I = individual, B = business"),
           ("FIRST_NM", "First name (individuals)"),
           ("MID_INIT", "Middle initial"),
           ("LAST_NM", "Last name (individuals)"),
           ("SFX", "Suffix, e.g. JR, SR"),
           ("BUS_NM", "Legal business name (businesses)"),
           ("BIRTH_DT", "Date of birth YYYYMMDD; 00000000 when missing"),
           ("TAX_ID_TKN", "Tokenised SSN/EIN, upper-case hex"),
           ("ADDR_LN1", "Street address, abbreviated suffix"),
           ("CITY", "City"),
           ("ST", "State code"),
           ("ZIP5", "5-digit ZIP"),
           ("PHONE_NO", "10 digits, no punctuation"),
           ("EMAIL_ADDR", "Email"),
           ("CUST_SINCE_DT", "Relationship start YYYYMMDD"),
           ("RISK_RTG", "KYC risk rating L/M/H"),
           ("OCCUP_DESC", "Occupation or line of business"),
           ("HOME_BR_CD", "Home branch code"),
       ]),
    _t("CORE_A_ACCOUNTS", "core_a/accounts.csv.gz", "core_a",
       "Kestrel Valley legacy core: deposit accounts", [
           ("ACCT_NO", "10-digit account number"),
           ("CIF_NO", "Owner CIF"),
           ("PROD_CD", "DDA, SAV, MMA, CD"),
           ("BR_CD", "Branch code"),
           ("OPEN_DT", "YYYYMMDD"),
           ("CLOSE_DT", "YYYYMMDD or blank"),
           ("ACCT_STAT", "A active, D dormant, C closed"),
           ("DORM_FLAG_DT", "Date flagged dormant YYYYMMDD or blank"),
           ("REACT_DT", "Date reactivated YYYYMMDD or blank"),
           ("CUR_BAL_CENTS", "Ledger balance in cents at as-of date"),
           ("INT_RATE_PCT", "Interest rate, percent"),
       ]),
    _t("CORE_A_LOANS", "core_a/loans.csv.gz", "core_a",
       "Kestrel Valley legacy core: loans", [
           ("LOAN_NO", "Loan number L + 9 digits"),
           ("CIF_NO", "Borrower CIF"),
           ("LOAN_TYP", "AUTO, MORT, HELOC, PERS, CRE, CI"),
           ("BR_CD", "Branch code"),
           ("ORIG_DT", "YYYYMMDD"),
           ("MAT_DT", "YYYYMMDD"),
           ("ORIG_AMT_CENTS", "Original amount in cents"),
           ("CUR_PRIN_CENTS", "Outstanding principal in cents"),
           ("INT_RATE_PCT", "Interest rate, percent"),
           ("COLL_TYP", "Collateral type code"),
           ("OWNER_OCC_FLG", "Y/N owner-occupied (real estate)"),
           ("DPD", "Days past due"),
       ]),
    _t("CORE_A_TXNS", "core_a/transactions.csv.gz", "core_a",
       "Kestrel Valley legacy core: posted transactions", [
           ("TXN_ID", "14-digit transaction id"),
           ("ACCT_NO", "Account number"),
           ("POST_DT", "Posting date YYYYMMDD"),
           ("POST_TM", "Posting time HHMMSS, local"),
           ("TXN_CD", "CDEP, CWDR, ATMW, ACHC, ACHD, WIRI, WIRO, CHKP, CARD, XFRI, XFRO, INTC"),
           ("AMT_CENTS", "Signed amount in cents (credit positive)"),
           ("CHNL_CD", "BR branch, ATM, OLB online, MOB mobile, SYS system"),
           ("BR_CD", "Branch where conducted, blank if not in branch"),
           ("CTR_FLG", "Y if a CTR was filed for this cash transaction"),
           ("CPTY_NM", "Counterparty name"),
           ("CPTY_BANK", "Counterparty institution"),
       ]),
    _t("CORE_A_AML_ALERTS", "core_a/aml_alerts.csv.gz", "core_a",
       "Kestrel Valley legacy transaction-monitoring alerts", [
           ("ALERT_ID", "Numeric alert id"),
           ("CIF_NO", "Customer CIF"),
           ("ACCT_NO", "Primary account"),
           ("RULE_CD", "LCT01 large cash, STR02 structuring, VEL03 velocity, WIR04 high-risk wire, RMV05 rapid movement, DRM06 dormant reactivation"),
           ("ALERT_DT", "YYYYMMDD"),
           ("ALERT_SCORE", "Legacy score 0-100"),
           ("ALERT_STAT", "OPEN, WIP, CLOSED"),
           ("DISPO_CD", "FP false positive, NSR no SAR after review, SAR SAR filed, blank if open"),
           ("CLOSE_DT", "YYYYMMDD or blank"),
           ("ASSIGNED_TO", "Investigator user id"),
           ("BR_CD", "Branch of the account"),
       ]),
    _t("CORE_A_BRANCHES", "core_a/branches.csv.gz", "core_a",
       "Kestrel Valley branches", [
           ("BR_CD", "Branch code"), ("BR_NM", "Branch name"), ("CITY", "City"), ("ST", "State"),
       ]),
    _t("CORE_A_CONTROL_TOTALS", "core_a/control_totals.csv.gz", "core_a",
       "Extract control totals written by the Core A extract job", [
           ("FILE_NM", "Extract file"), ("REC_CNT", "Record count"),
           ("AMT_TOTAL_CENTS", "Sum of the file's amount column in cents, blank if none"),
           ("AS_OF_DT", "YYYYMMDD"),
       ]),
]

CORE_B = [
    _t("CORE_B_PARTY", "core_b/party.csv.gz", "core_b",
       "Pellbrook legacy core: parties", [
           ("party_uuid", "UUID v4"),
           ("party_kind", "PERSON or ORG"),
           ("full_name", "LAST, FIRST M for persons; legal name for orgs"),
           ("dob", "MM/DD/YYYY or blank"),
           ("ssn_token", "Tokenised SSN/EIN: tkn_ + lower-case hex, or blank"),
           ("street", "Street address, long-form suffix"),
           ("city_state_zip", "City, ST 12345"),
           ("phone_num", "(NNN) NNN-NNNN"),
           ("email_addr", "Email"),
           ("relationship_start", "ISO date"),
           ("kyc_risk", "1 (low) to 5 (high)"),
           ("employer_or_industry", "Employer, occupation or industry"),
           ("home_branch", "Branch name"),
       ]),
    _t("CORE_B_DEPOSIT_ACCOUNT", "core_b/deposit_account.csv.gz", "core_b",
       "Pellbrook legacy core: deposit accounts", [
           ("acct_ref", "PB- + 8 digits"),
           ("party_uuid", "Owner party"),
           ("product_name", "Everyday Checking, Business Checking, Statement Savings, Money Market, Certificate of Deposit"),
           ("branch_name", "Branch name"),
           ("opened_on", "ISO date"),
           ("closed_on", "ISO date or blank"),
           ("acct_status", "OPEN, DORMANT, CLOSED"),
           ("dormant_since", "ISO date or blank"),
           ("reactivated_on", "ISO date or blank"),
           ("ledger_balance", "Decimal dollars"),
           ("rate_pct", "Interest rate, percent"),
       ]),
    _t("CORE_B_LOAN", "core_b/loan.csv.gz", "core_b",
       "Pellbrook legacy core: loans", [
           ("note_number", "LN-YYYY-######"),
           ("party_uuid", "Borrower party"),
           ("product_name", "Auto Loan, Residential Mortgage, Home Equity Line, Personal Loan, Commercial Real Estate, Commercial & Industrial"),
           ("branch_name", "Branch name"),
           ("booked_on", "ISO date"),
           ("maturity_on", "ISO date"),
           ("original_amount", "Decimal dollars"),
           ("principal_outstanding", "Decimal dollars"),
           ("interest_rate_pct", "Percent"),
           ("collateral_desc", "Free-text collateral description"),
           ("owner_occupied", "true/false"),
           ("days_delinquent", "Days past due"),
       ]),
    _t("CORE_B_TXN", "core_b/txn.csv.gz", "core_b",
       "Pellbrook legacy core: transactions", [
           ("txn_uuid", "UUID v4"),
           ("acct_ref", "Account"),
           ("txn_timestamp", "ISO 8601 with UTC offset"),
           ("amount", "Positive decimal dollars"),
           ("dr_cr", "D debit, C credit"),
           ("txn_type_desc", "Cash Deposit, Cash Withdrawal, ATM Withdrawal, ACH Credit, ACH Debit, Incoming Wire, Outgoing Wire, Check Paid, Debit Card Purchase, Transfer In, Transfer Out, Interest Credit"),
           ("channel_desc", "Teller, ATM, Online Banking, Mobile App, System"),
           ("branch_name", "Branch where conducted, blank if not in branch"),
           ("ctr_filed", "true/false"),
           ("counterparty", "Counterparty name"),
           ("counterparty_institution", "Counterparty institution"),
       ]),
    _t("CORE_B_CASE_ALERT", "core_b/case_alert.csv.gz", "core_b",
       "Pellbrook legacy transaction-monitoring alerts", [
           ("case_ref", "AL-2026-######"),
           ("party_uuid", "Party"),
           ("acct_ref", "Primary account"),
           ("scenario_name", "Monitoring scenario"),
           ("created_at", "ISO timestamp"),
           ("priority", "P1, P2, P3"),
           ("state", "NEW, IN_REVIEW, ESCALATED, CLOSED"),
           ("outcome", "NOT_SUSPICIOUS, NO_SAR_AFTER_REVIEW, SAR_FILED, or blank"),
           ("closed_at", "ISO timestamp or blank"),
           ("analyst", "Analyst name"),
       ]),
    _t("CORE_B_BRANCH", "core_b/branch.csv.gz", "core_b",
       "Pellbrook branches", [
           ("branch_name", "Branch name"), ("branch_city", "City"), ("branch_state", "State"),
           ("opened_year", "Year opened"),
       ]),
    _t("CORE_B_CONTROL_TOTALS", "core_b/control_totals.csv.gz", "core_b",
       "Extract control totals written by the Core B extract job", [
           ("file_name", "Extract file"), ("record_count", "Record count"),
           ("amount_total", "Sum of the file's amount column in dollars, blank if none"),
           ("as_of", "ISO date"),
       ]),
]

CORE_C = [
    _t("CORE_C_CUSTOMERS", "core_c/customers.csv.gz", "core_c",
       "Third core (onboarding-skill test only): customers", [
           ("custId", "C- + 7 digits"), ("givenName", "Given name"), ("familyName", "Family name"),
           ("birthDate", "YYYY/MM/DD"), ("taxRef", "Tax token with dashes"),
           ("addressLine", "Street"), ("cityName", "City"), ("stateCode", "State"),
           ("postalCode", "ZIP"), ("mobile", "+1 NNN NNN NNNN"), ("createdTs", "Epoch seconds"),
       ]),
    _t("CORE_C_ACCOUNTS", "core_c/accounts.csv.gz", "core_c",
       "Third core: accounts", [
           ("accountId", "Account id"), ("custId", "Owner"), ("accountType", "CHK, SVG"),
           ("balanceAmt", "Dollars"), ("openedDate", "YYYY/MM/DD"), ("statusCode", "1 open, 2 dormant, 9 closed"),
       ]),
    _t("CORE_C_POSTINGS", "core_c/postings.csv.gz", "core_c",
       "Third core: postings", [
           ("postingId", "Posting id"), ("accountId", "Account"), ("postedTs", "Epoch seconds"),
           ("amt", "Signed dollars"), ("typeCode", "CSHIN, CSHOUT, EFTIN, EFTOUT, POS"), ("channel", "Channel"),
       ]),
]

DOCUMENTS = [
    _t("DOC_INVESTIGATOR_NOTES", "documents/investigator_notes.csv.gz", "documents",
       "Investigator case notes from both legacy monitoring systems", [
           ("note_id", "Note id"), ("core", "core_a or core_b"), ("alert_ref", "Alert id in that core"),
           ("customer_ref", "CIF_NO or party_uuid"), ("author", "Investigator"),
           ("created_at", "ISO timestamp"), ("note_text", "Note text (synthetic)"),
       ]),
    _t("DOC_KYC_SUMMARIES", "documents/kyc_summaries.csv.gz", "documents",
       "KYC profile summaries from both cores", [
           ("kyc_id", "KYC record id"), ("core", "core_a or core_b"),
           ("customer_ref", "CIF_NO or party_uuid"), ("review_date", "ISO date"),
           ("risk_rating", "Low, Medium, High"), ("occupation_or_business", "Occupation or business"),
           ("expected_monthly_cash_usd", "Expected monthly cash"),
           ("expected_monthly_wires_usd", "Expected monthly wires"),
           ("source_of_funds", "Declared source of funds"), ("summary_text", "Summary (synthetic)"),
       ]),
]

GROUND_TRUTH = [
    _t("GT_PERSON_MAP", "ground_truth/person_map.csv.gz", "ground_truth",
       "Every source customer record mapped to its true person", [
           ("person_id", "True person id"), ("core", "core_a, core_b, core_c"),
           ("customer_ref", "Source key"), ("record_role", "Role of the record"),
       ]),
    _t("GT_DUPLICATE_LINKS", "ground_truth/duplicate_links.csv.gz", "ground_truth",
       "True cross-core duplicate identities", [
           ("person_id", "True person"), ("core_a_cif", "CIF_NO"), ("core_b_party_uuid", "party_uuid"),
           ("tier", "A clean, B variant, C hard"), ("variation", "What differs"),
       ]),
    _t("GT_LOOKALIKE_PAIRS", "ground_truth/lookalike_pairs.csv.gz", "ground_truth",
       "Different people who look alike across cores; must never be merged", [
           ("pair_id", "Pair id"), ("lookalike_type", "JR_SR, TWINS, SAME_NAME_DOB"),
           ("core_a_cif", "CIF_NO"), ("core_b_party_uuid", "party_uuid"),
           ("person_id_a", "Person"), ("person_id_b", "Person"), ("core_b_token_missing", "true/false"),
       ]),
    _t("GT_INJECTED_PATTERNS", "ground_truth/injected_patterns.csv.gz", "ground_truth",
       "Every injected risk pattern", [
           ("pattern_id", "Pattern id"), ("pattern_type", "Type"), ("person_id", "True person"),
           ("cores", "Cores involved"), ("customer_refs", "Source keys; semicolon separated"),
           ("account_refs", "Accounts; semicolon separated"),
           ("window_start", "ISO date"), ("window_end", "ISO date"),
           ("total_amount_usd", "Pattern amount"), ("expected_reason_codes", "Reason codes the risk engine should give"),
           ("legacy_alert_refs", "Existing legacy alerts, if any"), ("detail", "Detail"),
       ]),
    _t("GT_DQ_ISSUES", "ground_truth/dq_issues.csv.gz", "ground_truth",
       "Injected data-quality issues", [
           ("issue_id", "Issue id"), ("issue_type", "Type"), ("core", "Core"),
           ("table_name", "Bronze table"), ("record_key", "Record key"), ("field", "Field"),
       ]),
]

ALL_TABLES = CORE_A + CORE_B + CORE_C + DOCUMENTS + GROUND_TRUTH
BY_NAME = {t.name: t for t in ALL_TABLES}


def columns(name):
    return [c for c, _ in BY_NAME[name].columns]
