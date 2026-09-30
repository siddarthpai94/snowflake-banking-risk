#!/usr/bin/env bash
# Upload the generated synthetic dataset to Snowflake and load Bronze.
#
#   scripts/load_to_snowflake.sh [--setup] [--with-eval] [--data data/out/demo]
#
# Needs the Snowflake CLI ("snow") with a working connection:
#   snow connection add            # once
#   export SNOW_CONNECTION=default # or your connection name
#
# --setup      run sql/00_setup/00_setup.sql first (needs ACCOUNTADMIN)
# --with-eval  also load ground truth into the EVAL schema (for acceptance tests)
set -euo pipefail

REPO="$(cd "$(dirname "$0")/.." && pwd)"
DATA="$REPO/data/out/demo"
CONN="${SNOW_CONNECTION:-default}"
SETUP=0
EVAL=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --setup) SETUP=1 ;;
    --with-eval) EVAL=1 ;;
    --data) DATA="$(cd "$2" && pwd)"; shift ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
  shift
done

[[ -f "$DATA/manifest.json" ]] || { echo "No dataset at $DATA. Run: python -m data_gen.generate" >&2; exit 1; }
command -v snow >/dev/null || { echo "Snowflake CLI 'snow' not found. See README." >&2; exit 1; }

run_sql() { echo ">> $1"; snow sql -c "$CONN" -f "$1"; }

if [[ $SETUP -eq 1 ]]; then run_sql "$REPO/sql/00_setup/00_setup.sql"; fi

# One PUT per file into a matching stage folder. AUTO_COMPRESS=FALSE keeps the
# .csv.gz files as they are and keeps the policy PDF parseable.
PUTS="$(mktemp)"
trap 'rm -f "$PUTS"' EXIT
{
  echo "USE ROLE RISK_ADMIN; USE WAREHOUSE RISK_WH; USE DATABASE RISK_COPILOT;"
  for dir in core_a core_b core_c documents; do
    for f in "$DATA/$dir"/*; do
      echo "PUT 'file://$f' @RISK_COPILOT.BRONZE.RAW_STAGE/$dir/ AUTO_COMPRESS = FALSE OVERWRITE = TRUE;"
    done
  done
  if [[ $EVAL -eq 1 ]]; then
    for f in "$DATA/ground_truth"/*; do
      echo "PUT 'file://$f' @RISK_COPILOT.EVAL.GT_STAGE/ground_truth/ AUTO_COMPRESS = FALSE OVERWRITE = TRUE;"
    done
  fi
  echo "ALTER STAGE RISK_COPILOT.BRONZE.RAW_STAGE REFRESH;"
} > "$PUTS"
run_sql "$PUTS"

run_sql "$REPO/sql/10_bronze/10_tables.sql"
if [[ $EVAL -eq 1 ]]; then
  run_sql "$REPO/sql/10_bronze/11_copy.sql"
else
  # skip the EVAL tables when ground truth was not uploaded
  FILTERED="$(mktemp)"
  python3 - "$REPO/sql/10_bronze/11_copy.sql" > "$FILTERED" <<'PY'
import sys
text = open(sys.argv[1]).read()
blocks = text.split("\n\n")
print("\n\n".join(b for b in blocks if "EVAL." not in b))
PY
  run_sql "$FILTERED"
  rm -f "$FILTERED"
fi
run_sql "$REPO/sql/10_bronze/12_load_reconciliation.sql"
echo "Bronze loaded from $DATA. Every row of V_LOAD_RECONCILIATION should read MATCH."
