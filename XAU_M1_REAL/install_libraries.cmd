@echo off
setlocal enabledelayedexpansion
title Cai dat thu vien MT5 va Bot

set "CURR_DIR=%~dp0"
if "%CURR_DIR:~-1%"=="\" set "CURR_DIR=%CURR_DIR:~0,-1%"

if exist "%CURR_DIR%\..\.venv\Scripts\python.exe" (
    set "ROOT_DIR=%CURR_DIR%\.."
) else (
    set "ROOT_DIR=%CURR_DIR%"
)

echo ======================================================================
echo           CAI DAT THU VIEN CHO BOT XAU_M1_REAL
echo ======================================================================
echo.

:: 1. Tim Python de tao venv neu chua co
set "PYTHON_SYS="
if exist "%LOCALAPPDATA%\Programs\Python\Python311\python.exe" (
    set "PYTHON_SYS=%LOCALAPPDATA%\Programs\Python\Python311\python.exe"
) else (
    where py.exe >nul 2>nul
    if !errorlevel! equ 0 (
        set "PYTHON_SYS=py -3.11"
    ) else (
        where python.exe >nul 2>nul
        if !errorlevel! equ 0 (
            set "PYTHON_SYS=python"
        )
    )
)

:: 2. Kiem tra / Tao .venv
if not exist "%ROOT_DIR%\.venv\Scripts\python.exe" (
    echo [*] Dang tao moi truong ao .venv ...
    if not defined PYTHON_SYS (
        echo [!] Khong tim thay Python 3.11 de tao .venv!
        echo Vui long cai dat Python 3.11 truoc.
        pause
        exit /b 1
    )
    %PYTHON_SYS% -m venv "%ROOT_DIR%\.venv"
    if !errorlevel! neq 0 (
        echo [!] Loi khi tao .venv.
        pause
        exit /b 1
    )
    echo [OK] Da tao .venv thanh cong.
) else (
    echo [OK] Da tim thay .venv: %ROOT_DIR%\.venv
)

set "VENV_PYTHON=%ROOT_DIR%\.venv\Scripts\python.exe"

:: 3. Nang cap pip
echo.
echo [*] Dang kiem tra va nang cap pip ...
"%VENV_PYTHON%" -m pip install --upgrade pip --quiet

:: 4. Cai dat cac thu vien can thiet
echo.
echo [*] Dang cai dat cac thu vien: MetaTrader5, pandas, numpy, requests, flask ...
if exist "%CURR_DIR%\requirements.txt" (
    "%VENV_PYTHON%" -m pip install -r "%CURR_DIR%\requirements.txt"
) else if exist "%ROOT_DIR%\requirements.txt" (
    "%VENV_PYTHON%" -m pip install -r "%ROOT_DIR%\requirements.txt"
) else (
    "%VENV_PYTHON%" -m pip install MetaTrader5 pandas numpy requests flask
)

if !errorlevel! neq 0 (
    echo.
    echo [!] Co loi xay ra trong qua trinh cai dat thu vien.
    pause
    exit /b 1
)

:: 5. Kiem tra import
echo.
echo [*] Dang kiem tra lai cac thu vien da cai dat ...
"%VENV_PYTHON%" -c "import MetaTrader5 as mt5; import pandas; import numpy; import requests; import flask; print('MT5 Version:', mt5.__version__); print('Pandas Version:', pandas.__version__); print('Numpy Version:', numpy.__version__); print('Requests Version:', requests.__version__); print('Flask Version:', flask.__version__)"

if !errorlevel! equ 0 (
    echo.
    echo ======================================================================
    echo  [THANH CONG] Tat ca thu vien da duoc cai dat va san sang su dung!
    echo ======================================================================
) else (
    echo.
    echo [!] Kiem tra thu vien that bai.
)

echo.
pause
exit /b 0
