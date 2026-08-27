$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

if (-not (Test-Path ".venv\Scripts\python.exe")) {
    throw "Environnement absent. Lancez d'abord .\scripts\Setup.ps1"
}

& ".venv\Scripts\python.exe" -m uvicorn apps.api.main:app --host 127.0.0.1 --port 8016
