# Run FleetDesk from source. Usage: .\scripts\dev.ps1 [-Reinstall] [-Sample]
#   -Reinstall  reinstall dependencies (after editing pyproject.toml)
#   -Sample     generate fictitious workbooks in .\sample-data and point the app at them
param([switch]$Reinstall, [switch]$Sample)

$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

if (-not (Test-Path .venv)) { python -m venv .venv; $Reinstall = $true }
if ($Reinstall) { .\.venv\Scripts\python -m pip install -q -e ".[dev]" }

if ($Sample) {
    .\.venv\Scripts\python -m fleetdesk.sample_data sample-data --months 3
    $env:FLEETDESK_SETTINGS = (Join-Path $PWD "sample-data\settings.json")
    $settings = @{ source = (Join-Path $PWD "sample-data"); theme = "dark"; company_name = "Transportadora Exemplo" }
    $settings | ConvertTo-Json | Set-Content -Encoding utf8 $env:FLEETDESK_SETTINGS
}

.\.venv\Scripts\python -m fleetdesk
