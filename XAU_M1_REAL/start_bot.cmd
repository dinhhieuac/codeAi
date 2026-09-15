@echo off
setlocal
title XAU_M1_REAL - Bot Launcher

set "PYTHONUTF8=1"
set "PYTHONIOENCODING=utf-8"

:: Set directories
set "CURR_DIR=%~dp0"
if "%CURR_DIR:~-1%"=="\" set "CURR_DIR=%CURR_DIR:~0,-1%"

if exist "%CURR_DIR%\strategy_1_trend_ha_v1.1.py" (
    set "XAU_DIR=%CURR_DIR%"
    set "ROOT_DIR=%CURR_DIR%\.."
) else if exist "%CURR_DIR%\XAU_M1_REAL" (
    set "XAU_DIR=%CURR_DIR%\XAU_M1_REAL"
    set "ROOT_DIR=%CURR_DIR%"
) else (
    set "XAU_DIR=%CURR_DIR%"
    set "ROOT_DIR=%CURR_DIR%"
)

:: Find Python executable
set "PYTHON_EXE="
if exist "%ROOT_DIR%\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%ROOT_DIR%\.venv\Scripts\python.exe"
) else if exist "%XAU_DIR%\.venv\Scripts\python.exe" (
    set "PYTHON_EXE=%XAU_DIR%\.venv\Scripts\python.exe"
) else (
    where py.exe >nul 2>nul
    if %errorlevel% equ 0 (
        set "PYTHON_EXE=py -3.11"
    ) else (
        where python.exe >nul 2>nul
        if %errorlevel% equ 0 (
            set "PYTHON_EXE=python"
        )
    )
)

:MENU
cls
echo ======================================================================
echo           XAU_M1_REAL - TRINH KHOI CHAY BOT GIAO DICH
echo ======================================================================
echo  Thu muc bot: %XAU_DIR%
if defined PYTHON_EXE (
    echo  Python:     %PYTHON_EXE%
) else (
    echo  Python:     [CHUA TIM THAY PYTHON / VENV] (Hay chay install_libraries.cmd)
)
echo ======================================================================
echo  [1] strategy_1_trend_ha_v1.1.py   (Version 1.1)
echo  [2] strategy_1_trend_ha_v2.1.py   (Version 2.1)
echo  [3] strategy_1_trend_ha_v2.py     (Version 2.0)
echo  [4] strategy_1_trend_ha_v3.py     (Version 3.0)
echo  [5] strategy_1_trend_ha.py        (Original Version)
echo ----------------------------------------------------------------------
echo  [6] Chay TAT CA 5 bot tren        (Moi bot 1 cua so rieng)
echo  [7] Chay Update DB                (update_db.py)
echo  [8] Chay Dashboard                (dashboard.py)
echo ----------------------------------------------------------------------
echo  [9] Cai dat / Kiem tra thu vien   (install_libraries.cmd)
echo  [0] Thoat (Exit)
echo ======================================================================
echo.

set "user_choice="
set /p user_choice="Chon so [0-9] roi an Enter: "

:: Remove spaces
if defined user_choice set "user_choice=%user_choice: =%"

if "%user_choice:~0,1%"=="1" goto RUN_V1_1
if "%user_choice:~0,1%"=="2" goto RUN_V2_1
if "%user_choice:~0,1%"=="3" goto RUN_V2
if "%user_choice:~0,1%"=="4" goto RUN_V3
if "%user_choice:~0,1%"=="5" goto RUN_ORIGINAL
if "%user_choice:~0,1%"=="6" goto RUN_ALL
if "%user_choice:~0,1%"=="7" goto RUN_UPDATE_DB
if "%user_choice:~0,1%"=="8" goto RUN_DASHBOARD
if "%user_choice:~0,1%"=="9" goto RUN_INSTALL_LIBS
if "%user_choice:~0,1%"=="0" goto EXIT_PROG

echo.
echo [!] Lua chon khong hop le. Vui long nhap so tu 0 den 9.
timeout /t 2 >nul
goto MENU

:CHECK_PYTHON
if not defined PYTHON_EXE (
    echo.
    echo [!] KHONG TIM THAY PYTHON!
    echo Vui long chay install_libraries.cmd de tao moi truong .venv va cai thu vien.
    echo.
    pause
    goto MENU
)
goto :eof

:RUN_INSTALL_LIBS
if exist "%CURR_DIR%\install_libraries.cmd" (
    call "%CURR_DIR%\install_libraries.cmd"
) else if exist "%ROOT_DIR%\install_libraries.cmd" (
    call "%ROOT_DIR%\install_libraries.cmd"
)
goto MENU

:RUN_V1_1
call :CHECK_PYTHON
echo.
echo [*] Dang khoi chay: strategy_1_trend_ha_v1.1.py (Version 1.1) ...
start "XAU Bot - HA v1.1" cmd /k "chcp 65001 >nul && cd /d "%XAU_DIR%" && title XAU_M1_REAL - HA v1.1 && "%PYTHON_EXE%" -X utf8 strategy_1_trend_ha_v1.1.py"
goto DONE_LAUNCH

:RUN_V2_1
call :CHECK_PYTHON
echo.
echo [*] Dang khoi chay: strategy_1_trend_ha_v2.1.py (Version 2.1) ...
start "XAU Bot - HA v2.1" cmd /k "chcp 65001 >nul && cd /d "%XAU_DIR%" && title XAU_M1_REAL - HA v2.1 && "%PYTHON_EXE%" -X utf8 strategy_1_trend_ha_v2.1.py"
goto DONE_LAUNCH

:RUN_V2
call :CHECK_PYTHON
echo.
echo [*] Dang khoi chay: strategy_1_trend_ha_v2.py (Version 2.0) ...
start "XAU Bot - HA v2.0" cmd /k "chcp 65001 >nul && cd /d "%XAU_DIR%" && title XAU_M1_REAL - HA v2.0 && "%PYTHON_EXE%" -X utf8 strategy_1_trend_ha_v2.py"
goto DONE_LAUNCH

:RUN_V3
call :CHECK_PYTHON
echo.
echo [*] Dang khoi chay: strategy_1_trend_ha_v3.py (Version 3.0) ...
start "XAU Bot - HA v3.0" cmd /k "chcp 65001 >nul && cd /d "%XAU_DIR%" && title XAU_M1_REAL - HA v3.0 && "%PYTHON_EXE%" -X utf8 strategy_1_trend_ha_v3.py"
goto DONE_LAUNCH

:RUN_ORIGINAL
call :CHECK_PYTHON
echo.
echo [*] Dang khoi chay: strategy_1_trend_ha.py (Original Version) ...
start "XAU Bot - HA Original" cmd /k "chcp 65001 >nul && cd /d "%XAU_DIR%" && title XAU_M1_REAL - HA Original && "%PYTHON_EXE%" -X utf8 strategy_1_trend_ha.py"
goto DONE_LAUNCH

:RUN_ALL
call :CHECK_PYTHON
echo.
echo [*] Dang khoi chay TAT CA 5 bot trong tung cua so rieng...
start "XAU Bot - HA v1.1" cmd /k "chcp 65001 >nul && cd /d "%XAU_DIR%" && title XAU_M1_REAL - HA v1.1 && "%PYTHON_EXE%" -X utf8 strategy_1_trend_ha_v1.1.py"
start "XAU Bot - HA v2.1" cmd /k "chcp 65001 >nul && cd /d "%XAU_DIR%" && title XAU_M1_REAL - HA v2.1 && "%PYTHON_EXE%" -X utf8 strategy_1_trend_ha_v2.1.py"
start "XAU Bot - HA v2.0" cmd /k "chcp 65001 >nul && cd /d "%XAU_DIR%" && title XAU_M1_REAL - HA v2.0 && "%PYTHON_EXE%" -X utf8 strategy_1_trend_ha_v2.py"
start "XAU Bot - HA v3.0" cmd /k "chcp 65001 >nul && cd /d "%XAU_DIR%" && title XAU_M1_REAL - HA v3.0 && "%PYTHON_EXE%" -X utf8 strategy_1_trend_ha_v3.py"
start "XAU Bot - HA Original" cmd /k "chcp 65001 >nul && cd /d "%XAU_DIR%" && title XAU_M1_REAL - HA Original && "%PYTHON_EXE%" -X utf8 strategy_1_trend_ha.py"
goto DONE_LAUNCH

:RUN_UPDATE_DB
call :CHECK_PYTHON
echo.
echo [*] Dang khoi chay: update_db.py ...
start "XAU Bot - Update DB" cmd /k "chcp 65001 >nul && cd /d "%XAU_DIR%" && title XAU_M1_REAL - Update DB && "%PYTHON_EXE%" -X utf8 update_db.py"
goto DONE_LAUNCH

:RUN_DASHBOARD
call :CHECK_PYTHON
echo.
echo [*] Dang khoi chay: dashboard.py ...
start "XAU Bot - Dashboard" cmd /k "chcp 65001 >nul && cd /d "%XAU_DIR%" && title XAU_M1_REAL - Dashboard && "%PYTHON_EXE%" -X utf8 dashboard.py"
goto DONE_LAUNCH

:DONE_LAUNCH
echo.
echo [OK] Da gui lenh khoi chay thanh cong!
echo.
set "post_choice="
set /p post_choice="Nhap [1] de ve Menu, [0] de Thoat: "
if "%post_choice:~0,1%"=="0" goto EXIT_PROG
goto MENU

:EXIT_PROG
echo.
echo Tam biet!
exit /b 0
