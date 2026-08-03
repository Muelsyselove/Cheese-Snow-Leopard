@echo off
REM ============================================================
REM Knowledge Base Desktop App - Windows Launcher
REM
REM 1. Create/reuse .venv
REM 2. Install CORE deps (fast, excludes heavy ML packages)
REM 3. Launch PySide6 app
REM
REM Heavy deps (paddlepaddle, FlagEmbedding/torch) are NOT
REM auto-installed. Run: pip install -r requirements.txt
REM for full functionality.
REM
REM Usage: double-click or run start.bat in terminal
REM ============================================================

cd /d "%~dp0"

set "VENV_DIR=.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "VENV_PIP=%VENV_DIR%\Scripts\pip.exe"
set "CORE_REQUIREMENTS=requirements-core.txt"
set "MARKER=.venv\.installed"
set "PIP_MIRROR=-i https://pypi.tuna.tsinghua.edu.cn/simple"

REM ---------- 1. Check system Python ----------
where python >nul 2>&1
if %errorlevel%==0 goto :check_venv
echo [ERROR] Python not found. Please install Python 3.10+ and add to PATH.
echo         https://www.python.org/downloads/
pause
exit /b 1

:check_venv
REM ---------- 2. Create venv (first run) ----------
if exist "%VENV_PYTHON%" goto :check_marker
echo [INIT] Creating venv %VENV_DIR% ...
python -m venv %VENV_DIR%
if %errorlevel%==0 goto :venv_done
echo [ERROR] venv creation failed.
pause
exit /b 1

:venv_done
echo [INIT] venv created.

:check_marker
REM ---------- 3. Install CORE deps (fast, first run only) ----------
if exist "%MARKER%" goto :launch_app
echo [INIT] Installing core deps (fast, ~1 min with mirror)...
echo [INIT]   - PySide6, PyYAML, keyring, openai, qdrant-client...
echo [INIT]   - Using Tsinghua mirror for speed.
echo [INIT]   - Heavy ML packages (paddlepaddle/torch) are SKIPPED.
"%VENV_PYTHON%" -m pip install --upgrade pip %PIP_MIRROR% --no-cache-dir
if %errorlevel%==0 goto :install_deps
echo [ERROR] pip upgrade failed.
pause
exit /b 1

:install_deps
"%VENV_PIP%" install -r %CORE_REQUIREMENTS% %PIP_MIRROR% --no-cache-dir --progress-bar off
if %errorlevel%==0 goto :deps_done
echo [ERROR] Core deps install failed. Check network or try:
echo         %VENV_PIP% install -r %CORE_REQUIREMENTS%
pause
exit /b 1

:deps_done
echo installed > "%MARKER%"
echo [INIT] Core deps installed.
echo [INIT] For full functionality (VLM parsing, BGE embedding):
echo [INIT]   %VENV_PIP% install -r requirements.txt

:launch_app
REM ---------- 4. Launch app ----------
echo.
echo [START] Knowledge Base Desktop App ...
echo.
"%VENV_PYTHON%" main.py
set "EXIT_CODE=%errorlevel%"

echo.
if %EXIT_CODE%==0 echo [INFO] App exited normally.
if not %EXIT_CODE%==0 echo [ERROR] App exited with code %EXIT_CODE%.
echo.
echo Press any key to close this window ...
pause >nul
exit /b %EXIT_CODE%
