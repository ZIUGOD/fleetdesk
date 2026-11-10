# Install dist\FleetDesk-Setup.exe silently, check that FleetDesk starts, then uninstall it and
# check that nothing is left. Run on a CI machine: it installs into the current user's profile.
$ErrorActionPreference = "Stop"
Set-Location (Split-Path $PSScriptRoot -Parent)

$app = Join-Path $env:LOCALAPPDATA "Programs\FleetDesk"
$version = "http://127.0.0.1:5000/version"

function Wait-Until([scriptblock] $condition, [int] $seconds, [string] $failure) {
    for ($i = 0; $i -lt $seconds; $i++) {
        if (& $condition) { return }
        Start-Sleep 1
    }
    throw $failure
}

function Test-Running {
    try { Invoke-RestMethod $version -TimeoutSec 2 | Out-Null; return $true } catch { return $false }
}

# Not Start-Process -Wait: it also waits for every process the installer starts, and the
# installer leaves FleetDesk running, so it would never return.
$setup = Start-Process dist\FleetDesk-Setup.exe -PassThru `
    -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART", "/TASKS=desktopicon"
$null = $setup.Handle  # keeps ExitCode readable after the process ends (PowerShell 5)
if (-not $setup.WaitForExit(300000)) { throw "Installer did not finish within 5 minutes" }
if ($setup.ExitCode -ne 0) { throw "Installer exited with code $($setup.ExitCode)" }

foreach ($path in "$app\runtime\pythonw.exe", "$app\unins000.exe", "$app\fleetdesk.ico") {
    if (-not (Test-Path $path)) { throw "Missing after install: $path" }
}
$startMenu = Join-Path ([Environment]::GetFolderPath("Programs")) "FleetDesk.lnk"
if (-not (Test-Path $startMenu)) { throw "Start menu shortcut missing" }
$entry = Get-ItemProperty "HKCU:\Software\Microsoft\Windows\CurrentVersion\Uninstall\*" |
    Where-Object DisplayName -eq "FleetDesk"
if (-not $entry) { throw "No entry in Settings > Apps" }

# The installer's [Run] entry starts FleetDesk even after a silent install.
Wait-Until { Test-Running } 40 "FleetDesk did not start after install"
$running = (Invoke-RestMethod $version).version
Write-Host "Installed FleetDesk $running ($($entry.DisplayVersion)) is running"

# The uninstaller relaunches itself from a temp copy, so wait on the result, not the process.
Start-Process "$app\unins000.exe" -ArgumentList "/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"
Wait-Until { -not (Test-Path "$app\runtime") } 60 "Uninstall left the runtime behind"
Wait-Until { -not (Test-Running) } 10 "FleetDesk still running after uninstall"
if (Test-Path $startMenu) { throw "Start menu shortcut left behind" }
Write-Host "Uninstalled cleanly"
