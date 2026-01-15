<#
.SYNOPSIS
    Bootstraps a Windows virtual environment for the Finance Tracker.
.DESCRIPTION
    Creates (or reuses) .venv, upgrades pip, and installs requirements.
    Usage: pwsh -File scripts/setup_venv.ps1
#>

param(
    [string]$Python = "python"
)

$ProjectRoot = Split-Path -Parent (Split-Path -Parent $MyInvocation.MyCommand.Definition)
$VenvPath = Join-Path $ProjectRoot ".venv"
$Requirements = Join-Path $ProjectRoot "requirements.txt"

if (-not (Get-Command $Python -ErrorAction SilentlyContinue)) {
    Write-Error "Could not find '$Python'. Pass -Python <path> to this script."
    exit 1
}

if (-not (Test-Path $Requirements)) {
    Write-Error "Missing requirements.txt at $Requirements"
    exit 1
}

if (-not (Test-Path $VenvPath)) {
    Write-Host "Creating virtual environment at $VenvPath"
    & $Python -m venv $VenvPath
} else {
    Write-Host "Reusing virtual environment at $VenvPath"
}

$Activate = Join-Path $VenvPath "Scripts\Activate.ps1"
. $Activate

python -m pip install --upgrade pip
python -m pip install -r $Requirements

Write-Host "`n✓ Virtual environment ready. Activate it later with:"
Write-Host "   . $Activate"
Write-Host "To deactivate, run: deactivate"
