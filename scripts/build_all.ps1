<#
One-command rebuild in Snowflake (Windows PowerShell): Bronze load, every build step in order, then the
three acceptance checks. Stops at the first error. No AI features are used.

  powershell -ExecutionPolicy Bypass -File scripts\build_all.ps1            # load + build + checks
  powershell -ExecutionPolicy Bypass -File scripts\build_all.ps1 -Setup     # first time: also roles, warehouse, schemas
  powershell -ExecutionPolicy Bypass -File scripts\build_all.ps1 -SkipLoad  # Bronze already loaded

Needs: python -m data_gen.generate (the dataset) and a working "snow connection add".
#>
param(
    [switch]$Setup,
    [switch]$SkipLoad,
    [string]$Connection = $(if ($env:SNOW_CONNECTION) { $env:SNOW_CONNECTION } else { "default" })
)
$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot

function Run-Sql([string]$Rel) {
    $file = Join-Path $Repo ("sql\" + ($Rel -replace '/', '\'))
    Write-Host ">> $Rel" -ForegroundColor Cyan
    & snow sql -c $Connection -f $file
    if ($LASTEXITCODE -ne 0) { throw "snow sql failed on $Rel - fix it, then rerun with -SkipLoad" }
}

if (-not $SkipLoad) {
    $loader = Join-Path $PSScriptRoot "load_to_snowflake.ps1"
    if ($Setup) { & $loader -Setup -WithEval -Connection $Connection } else { & $loader -WithEval -Connection $Connection }
}

$steps = @(
    "00_setup/90_environment_check.sql",
    "20_silver/20_reference.sql", "20_silver/21_customer_std.sql", "20_silver/22_match_candidates.sql",
    "20_silver/23_party_resolution.sql", "20_silver/24_dq_exceptions.sql",
    "30_gold/30_config.sql", "30_gold/31_gold_core.sql", "30_gold/32_risk_engine.sql",
    "40_semantic/40_metric_views.sql", "40_semantic/41_question_catalog.sql",
    "50_search/50_policy_chunks.sql", "50_search/51_doc_chunk.sql",
    "60_agent/60_audit.sql", "70_outputs/70_case_output.sql"
)
foreach ($s in $steps) { Run-Sql $s }

Write-Host "== Acceptance checks ==" -ForegroundColor Yellow
Run-Sql "20_silver/90_eval_matching.sql"   # expect 0 false merges, recall >= 95%
Run-Sql "30_gold/91_eval_risk.sql"         # expect PASS
Run-Sql "30_gold/92_golden_check.sql"      # expect 15 of 15 correct
Write-Host "Build complete. Start the app with: streamlit run app/streamlit_app.py" -ForegroundColor Green
