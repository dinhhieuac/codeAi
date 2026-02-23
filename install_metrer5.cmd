Write-Host "==== MT5 Environment Setup Script ====" -ForegroundColor Cyan

# 1. Deactivate nếu đang trong venv
if (Test-Path .venv) {
    Write-Host "Removing old .venv ..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force .venv
}

# 2. Tạo venv bằng Python 3.11
Write-Host "Creating venv with Python 3.11 ..." -ForegroundColor Green
py -3.11 -m venv .venv

# 3. Activate venv
Write-Host "Activating venv ..." -ForegroundColor Green
. .\.venv\Scripts\Activate.ps1

# 4. Upgrade pip
Write-Host "Upgrading pip ..." -ForegroundColor Green
python -m pip install --upgrade pip

# 5. Install MetaTrader5
Write-Host "Installing MetaTrader5 ..." -ForegroundColor Green
pip install MetaTrader5

# 6. Verify
Write-Host "Checking Python version ..." -ForegroundColor Cyan
python --version

Write-Host "Checking MetaTrader5 install ..." -ForegroundColor Cyan
pip show MetaTrader5
pip install requests
pip install pandas
pip install flask

Write-Host "==== DONE ====" -ForegroundColor Green