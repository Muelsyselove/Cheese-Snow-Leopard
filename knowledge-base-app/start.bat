@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

REM ============================================================
REM 自主知识库桌面应用 — Windows 启动脚本
REM
REM 功能：
REM   1. 自动创建/复用 .venv 虚拟环境
REM   2. 安装依赖（首次或 requirements.txt 变更时）
REM   3. 启动 PySide6 桌面应用
REM
REM 用法：
REM   双击运行 或 在终端执行 start.bat
REM ============================================================

cd /d "%~dp0"

set "VENV_DIR=.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "VENV_PIP=%VENV_DIR%\Scripts\pip.exe"
set "REQUIREMENTS=requirements.txt"
set "MARKER=.venv\.installed"

REM ---------- 1. 检查系统 Python ----------
where python >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，请先安装 Python 3.10+ 并加入 PATH。
    echo        下载地址：https://www.python.org/downloads/
    pause
    exit /b 1
)

REM ---------- 2. 创建虚拟环境（首次） ----------
if not exist "%VENV_PYTHON%" (
    echo [初始化] 创建虚拟环境 %VENV_DIR% ...
    python -m venv %VENV_DIR%
    if errorlevel 1 (
        echo [错误] 虚拟环境创建失败。
        pause
        exit /b 1
    )
    echo [初始化] 虚拟环境已创建。
)

REM ---------- 3. 安装依赖（首次或 requirements.txt 变更） ----------
REM 通过 .installed 标记文件判断是否需要安装；
REM requirements.txt 变更后删除 .venv\.installed 即可触发重装。
set "NEED_INSTALL=0"
if not exist "%MARKER%" set "NEED_INSTALL=1"

REM 比对修改时间：requirements.txt 比 marker 新则重装
if exist "%MARKER%" (
    for %%F in ("%REQUIREMENTS%") do set "REQ_TIME=%%~tF"
    for %%F in ("%MARKER%") do set "MRK_TIME=%%~tF"
    if "!REQ_TIME!" gtr "!MRK_TIME!" set "NEED_INSTALL=1"
)

if "!NEED_INSTALL!"=="1" (
    echo [初始化] 安装依赖（可能需要几分钟，首次较慢）...
    "%VENV_PYTHON%" -m pip install --upgrade pip
    "%VENV_PIP%" install -r %REQUIREMENTS%
    if errorlevel 1 (
        echo [错误] 依赖安装失败，请检查网络或 requirements.txt。
        pause
        exit /b 1
    )
    REM 写入安装标记
    echo installed > "%MARKER%"
    echo [初始化] 依赖安装完成。
)

REM ---------- 4. 启动应用 ----------
echo.
echo [启动] 自主知识库桌面应用 ...
echo.
"%VENV_PYTHON%" main.py

REM 异常退出时暂停以便查看错误
if errorlevel 1 (
    echo.
    echo [错误] 应用异常退出（退出码 %errorlevel%）。
    pause
)

endlocal
