@echo off
chcp 65001 >nul
title Setup MT5 Environment
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_metrer5.ps1"
if %errorlevel% neq 0 (
    echo.
    echo Có lỗi xảy ra trong quá trình cài đặt.
)
pause