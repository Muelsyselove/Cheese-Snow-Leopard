@echo off
setlocal enabledelayedexpansion
REM ============================================================
REM Knowledge Base Desktop App - Windows Launcher
REM
REM 1. Create/reuse .venv
REM 2. Install deps (first run or requirements.txt changed)
REM 3. Launch PySide6 app
REM
REM Usage: double-click or run start.bat in terminal
REM ============================================================

cd /d "%~dp0"

set "VENV_DIR=.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "VENV_PIP=%VENV_DIR%\Scripts\pip.exe"
set "REQUIREMENTS=requirements.txt"
set "MARKER=.venv\.installed"

REM ---------- 1. Check system Python ----------
where python >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.10+ and add to PATH.
    echo         https://www.python.org/downloads/
    pause
    exit /b 1
)

REM ---------- 2. Create venv (first run) ----------
if not exist "%VENV_PYTHON%" (
    echo [INIT] Creating venv %VENV_DIR% ...
    python -m venv %VENV_DIR%
    if errorlevel 1 (
        echo [ERROR] venv creation failed.
        pause
        exit /b 1
    )
    echo [INIT] venv created.
)

REM ---------- 3. Install deps (first run or requirements.txt changed) ----------
set "NEED_INSTALL=0"
if not exist "%MARKER%" set "NEED_INSTALL=1"

if exist "%MARKER%" (
    for %%F in ("%REQUIREMENTS%") do set "REQ_TIME=%%~tF"
    for %%F in ("%MARKER%") do set "MRK_TIME=%%~tF"
    if "!REQ_TIME!" gtr "!MRK_TIME!" set "NEED_INSTALL=1"
)

if "!NEED_INSTALL!"=="1" (
    echo [INIT] Installing deps (may take a few minutes)...
    "%VENV_PYTHON%" -m pip install --upgrade pip
    "%VENV_PIP%" install -r %REQUIREMENTS%
    if errorlevel 1 (
        echo [ERROR] Deps install failed. Check network or requirements.txt.
        pause
        exit /b 1
    )
    echo installed > "%MARKER%"
    echo [INIT] Deps installed.
)

REM ---------- 4. Launch app ----------
echo.
echo [START] Knowledge Base Desktop App ...
echo.
"%VENV_PYTHON%" main.py

if errorlevel 1 (
    echo.
    echo [ERROR] App exited with code %errorlevel%.
    pause
)
