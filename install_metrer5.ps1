Write-Host "==== MT5 Environment Setup Script ====" -ForegroundColor Cyan

# 1. Tim Python 3.11 tren he thong
$pythonCmd = $null
if (Test-Path "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe") {
    $pythonCmd = "$env:LOCALAPPDATA\Programs\Python\Python311\python.exe"
} elseif (Get-Command py -ErrorAction SilentlyContinue) {
    $pythonCmd = "py -3.11"
} elseif (Get-Command python -ErrorAction SilentlyContinue) {
    $pythonCmd = "python"
}

# 2. Kiem tra / Tao venv neu chua co (khong xoa de tranh lock file)
if (-not (Test-Path ".venv\Scripts\python.exe")) {
    Write-Host "Creating venv with Python 3.11 ..." -ForegroundColor Green
    if ($pythonCmd -eq $null) {
        Write-Host "LỖI: Chưa cài đặt Python trên máy tính. Vui lòng cài đặt Python 3.11." -ForegroundColor Red
        pause
        exit 1
    }
    & $pythonCmd -m venv .venv
} else {
    Write-Host ".venv already exists." -ForegroundColor Green
}

$venvPython = ".venv\Scripts\python.exe"

# 3. Upgrade pip
Write-Host "Upgrading pip ..." -ForegroundColor Green
& $venvPython -m pip install --upgrade pip --quiet

# 4. Install MetaTrader5 & dependencies
Write-Host "Installing MetaTrader5, pandas, numpy, flask, requests..." -ForegroundColor Green
& $venvPython -m pip install -r requirements.txt

# 5. Verify
Write-Host "Checking Python & Library installation ..." -ForegroundColor Cyan
& $venvPython -c "import MetaTrader5 as mt5; import pandas, numpy, requests, flask; print('MT5 version:', mt5.__version__); print('All libraries loaded successfully!')"

Write-Host "==== DONE ====" -ForegroundColor Green
