@echo off
rem ============================================================
rem  HLTV three scrapers - Windows one-click build launcher
rem  Build the 3 exe files for the friend's Windows PC.
rem  Prerequisite: Python 3.11 installed on THIS Windows machine.
rem ============================================================
chcp 65001 >nul
where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found on PATH.
    echo Please install Python 3.11 from https://www.python.org/downloads/
    echo and check "Add Python to PATH" during setup, then run this again.
    pause
    exit /b 1
)
python "%~dp0build_windows.py"
echo.
pause
