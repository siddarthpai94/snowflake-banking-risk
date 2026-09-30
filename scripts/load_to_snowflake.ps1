<#
Upload the generated synthetic dataset to Snowflake and load Bronze (Windows PowerShell version).

  powershell -ExecutionPolicy Bypass -File scripts\load_to_snowflake.ps1 -Setup -WithEval

Needs the Snowflake CLI ("snow") with a working connection (snow connection add).
  -Setup      run sql\00_setup\00_setup.sql first (needs ACCOUNTADMIN)
  -WithEval   also load ground truth into the EVAL schema (for acceptance tests)
  -Data       dataset folder (default data\out\demo)
  -Connection Snowflake CLI connection name (default "default")
#>
param(
    [switch]$Setup,
    [switch]$WithEval,
    [string]$Data = "",
    [string]$Connection = $(if ($env:SNOW_CONNECTION) { $env:SNOW_CONNECTION } else { "default" })
)
$ErrorActionPreference = "Stop"
$Repo = Split-Path -Parent $PSScriptRoot
if (-not $Data) { $Data = Join-Path $Repo "data\out\demo" }
$Data = (Resolve-Path $Data).Path

if (-not (Test-Path (Join-Path $Data "manifest.json"))) {
    throw "No dataset at $Data. Run: python -m data_gen.generate"
}
if (-not (Get-Command snow -ErrorAction SilentlyContinue)) {
    throw "Snowflake CLI 'snow' not found. Run: pip install snowflake-cli"
}

function Run-Sql([string]$File) {
    Write-Host ">> $File" -ForegroundColor Cyan
    & snow sql -c $Connection -f $File
    if ($LASTEXITCODE -ne 0) { throw "snow sql failed on $File" }
}

if ($Setup) { Run-Sql (Join-Path $Repo "sql\00_setup\00_setup.sql") }

# PUT needs forward slashes: file://C:/Users/...
$lines = @("USE ROLE RISK_ADMIN;", "USE WAREHOUSE RISK_WH;", "USE DATABASE RISK_COPILOT;")
foreach ($dir in @("core_a", "core_b", "core_c", "documents")) {
    Get-ChildItem -File (Join-Path $Data $dir) | ForEach-Object {
        $p = $_.FullName -replace '\\', '/'
        $lines += "PUT 'file://$p' @RISK_COPILOT.BRONZE.RAW_STAGE/$dir/ AUTO_COMPRESS = FALSE OVERWRITE = TRUE;"
    }
}
if ($WithEval) {
    Get-ChildItem -File (Join-Path $Data "ground_truth") | ForEach-Object {
        $p = $_.FullName -replace '\\', '/'
        $lines += "PUT 'file://$p' @RISK_COPILOT.EVAL.GT_STAGE/ground_truth/ AUTO_COMPRESS = FALSE OVERWRITE = TRUE;"
    }
}
$lines += "ALTER STAGE RISK_COPILOT.BRONZE.RAW_STAGE REFRESH;"
$puts = Join-Path $env:TEMP "risk_copilot_puts.sql"
Set-Content -Path $puts -Value $lines -Encoding ascii
Run-Sql $puts

Run-Sql (Join-Path $Repo "sql\10_bronze\10_tables.sql")
$copy = Join-Path $Repo "sql\10_bronze\11_copy.sql"
if (-not $WithEval) {
    # skip the EVAL tables when ground truth was not uploaded
    $blocks = (Get-Content $copy -Raw) -split "`n`n" | Where-Object { $_ -notmatch "EVAL\." }
    $copy = Join-Path $env:TEMP "risk_copilot_copy.sql"
    Set-Content -Path $copy -Value ($blocks -join "`n`n") -Encoding ascii
}
Run-Sql $copy
Run-Sql (Join-Path $Repo "sql\10_bronze\12_load_reconciliation.sql")
Write-Host "Bronze loaded from $Data. Every row of V_LOAD_RECONCILIATION should read MATCH." -ForegroundColor Green
