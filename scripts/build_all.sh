#!/usr/bin/env bash
# One-command rebuild in Snowflake: Bronze load, every build step in order, then the three acceptance checks.
# Stops at the first error. No AI features are used.
#
#   scripts/build_all.sh [--setup] [--skip-load]
#
#   --setup      also run sql/00_setup/00_setup.sql (needs ACCOUNTADMIN; first time only)
#   --skip-load  Bronze is already loaded; start at Silver
# Needs: python -m data_gen.generate (the dataset) and a working `snow connection add`.
set -euo pipefail
REPO="$(cd "$(dirname "$0")/.." && pwd)"
CONN="${SNOW_CONNECTION:-default}"
SETUP=""; LOAD=1
while [[ $# -gt 0 ]]; do
  case "$1" in
    --setup) SETUP="--setup" ;;
    --skip-load) LOAD=0 ;;
    *) echo "unknown option $1" >&2; exit 2 ;;
  esac
  shift
done

run_sql() { echo ">> $1"; snow sql -c "$CONN" -f "$REPO/sql/$1"; }

if [[ $LOAD -eq 1 ]]; then "$REPO/scripts/load_to_snowflake.sh" $SETUP --with-eval; fi

for f in 00_setup/90_environment_check.sql \
         20_silver/20_reference.sql 20_silver/21_customer_std.sql 20_silver/22_match_candidates.sql \
         20_silver/23_party_resolution.sql 20_silver/24_dq_exceptions.sql \
         30_gold/30_config.sql 30_gold/31_gold_core.sql 30_gold/32_risk_engine.sql \
         40_semantic/40_metric_views.sql 40_semantic/41_question_catalog.sql \
         50_search/50_policy_chunks.sql 50_search/51_doc_chunk.sql \
         60_agent/60_audit.sql 70_outputs/70_case_output.sql; do
  run_sql "$f"
done

echo "== Acceptance checks =="
run_sql 20_silver/90_eval_matching.sql   # expect 0 false merges, recall >= 95%
run_sql 30_gold/91_eval_risk.sql         # expect PASS
run_sql 30_gold/92_golden_check.sql      # expect 15 of 15 correct
echo "Build complete. Start the app with: streamlit run app/streamlit_app.py"
