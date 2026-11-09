# Run every quality gate that CI runs. Usage: .\scripts\check.ps1
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

.\.venv\Scripts\ruff check src tests
.\.venv\Scripts\ruff format --check src tests
.\.venv\Scripts\python -m mypy src
.\.venv\Scripts\python -m pytest -q
