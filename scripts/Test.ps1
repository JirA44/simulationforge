$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    throw "Environnement absent. Lancez d'abord .\scripts\Setup.ps1"
}

& ".venv\Scripts\python.exe" -m pytest
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
& ".venv\Scripts\python.exe" -m compileall -q apps tests
if ($LASTEXITCODE -ne 0) { exit $LASTEXITCODE }
Write-Host "Tests SimulationForge V1.05 validés."
