Write-Host "==== MT5 Environment Setup Script ====" -ForegroundColor Cyan

# 1. Deactivate nếu đang trong venv
if (Test-Path .venv) {
    Write-Host "Removing old .venv ..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force .venv
}

# 2. Tạo venv bằng Python 3.11 (hoặc python mặc định nếu py không có)
Write-Host "Creating venv with Python 3.11 ..." -ForegroundColor Green
if (Get-Command py -ErrorAction SilentlyContinue) {
    py -3.11 -m venv .venv
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    python -m venv .venv
} else {
    Write-Host "LỖI: Chưa cài đặt Python trên máy tính. Vui lòng cài đặt Python 3.11 (tích chọn Add Python to PATH) trước khi chạy." -ForegroundColor Red
    pause
    exit 1
}

# 3. Activate venv
Write-Host "Activating venv ..." -ForegroundColor Green
. .\.venv\Scripts\Activate.ps1

# 4. Upgrade pip
Write-Host "Upgrading pip ..." -ForegroundColor Green
python -m pip install --upgrade pip

# 5. Install MetaTrader5 & dependencies
Write-Host "Installing MetaTrader5, pandas, flask, requests..." -ForegroundColor Green
pip install MetaTrader5 requests pandas flask

# 6. Verify
Write-Host "Checking Python version ..." -ForegroundColor Cyan
python --version

Write-Host "Checking MetaTrader5 install ..." -ForegroundColor Cyan
pip show MetaTrader5

Write-Host "==== DONE ====" -ForegroundColor Green
