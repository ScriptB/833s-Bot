\
# Bootstrap for local Windows development
# Run from repo root: powershell -ExecutionPolicy Bypass -File .\scripts\windows_bootstrap.ps1

$ErrorActionPreference = "Stop"

python -m venv .venv
.\.venv\Scripts\Activate.ps1

python -m pip install -U pip
pip install -e .
Write-Host "Installed. Create .env then run: python -m guardian"
