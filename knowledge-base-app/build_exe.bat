@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

REM ============================================================
REM 自主知识库桌面应用 — Windows 打包脚本（PyInstaller）
REM
REM 产物: dist\KnowledgeBase\KnowledgeBase.exe
REM   - windowed 模式，启动无 cmd 窗口
REM   - 启动期间显示主题感知的载入界面（Splash 动画）
REM
REM 说明:
REM   1. 复用 .venv（无则用系统 Python 创建，并安装 core 依赖）
REM   2. 自动安装/更新 pyinstaller
REM   3. 按 knowledge_base.spec 打包（onedir）
REM   4. 将 config.yaml 复制到产物目录（供用户编辑）
REM
REM 注意: 打包体积与能力与 core 模式一致（不含 torch/paddle 等 ML 包）。
REM ============================================================

cd /d "%~dp0"

set "VENV_DIR=.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "DIST_DIR=dist\KnowledgeBase"
set "MIRROR_TSINGHUA=https://pypi.tuna.tsinghua.edu.cn/simple"

REM ---------- 1. 定位/准备 Python ----------
set "PYTHON_CMD="
if exist "%VENV_PYTHON%" (
    set "PYTHON_CMD=%VENV_PYTHON%"
    echo [信息] 复用虚拟环境 %VENV_DIR%
    goto :check_pyinstaller
)

where python >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到 Python，也未发现 %VENV_DIR%。
    echo        请先运行 start.bat 完成环境初始化，或安装 Python 3.10+。
    pause
    exit /b 1
)
for /f "tokens=* delims=" %%e in ('python -c "import sys; print(sys.executable)" 2^>nul') do (
    set "PYTHON_CMD=%%e"
)
if not defined PYTHON_CMD (
    echo [错误] 无法解析系统 Python 路径。
    pause
    exit /b 1
)

echo [初始化] 创建虚拟环境 %VENV_DIR% ...
"%PYTHON_CMD%" -m venv %VENV_DIR%
if not %errorlevel%==0 (
    echo [错误] 虚拟环境创建失败。
    pause
    exit /b 1
)
set "PYTHON_CMD=%VENV_PYTHON%"

echo [初始化] 安装 core 依赖 ...
"%PYTHON_CMD%" -m pip install -r requirements-core.txt --no-cache-dir -i %MIRROR_TSINGHUA%
if not %errorlevel%==0 (
    echo [错误] core 依赖安装失败，请检查网络后重试。
    pause
    exit /b 1
)

:check_pyinstaller
REM ---------- 2. 确保 pyinstaller ----------
"%PYTHON_CMD%" -c "import PyInstaller" >nul 2>&1
if not %errorlevel%==0 (
    echo [初始化] 安装 PyInstaller ...
    "%PYTHON_CMD%" -m pip install "pyinstaller>=6.0" --no-cache-dir -i %MIRROR_TSINGHUA%
    if not %errorlevel%==0 (
        echo [错误] PyInstaller 安装失败。
        pause
        exit /b 1
    )
)

REM ---------- 3. 打包 ----------
echo.
echo [打包] 开始构建（windowed，无控制台窗口）...
"%PYTHON_CMD%" -m PyInstaller --noconfirm --clean knowledge_base.spec
if not %errorlevel%==0 (
    echo [错误] 打包失败，请检查上方日志。
    pause
    exit /b 1
)

REM ---------- 4. 拷贝外部可编辑配置 ----------
if not exist "%DIST_DIR%\config.yaml" (
    copy /y "config.yaml" "%DIST_DIR%\config.yaml" >nul
    echo [信息] 已复制 config.yaml 到 %DIST_DIR%
)

echo.
echo [完成] 产物目录: %DIST_DIR%
echo        启动: %DIST_DIR%\KnowledgeBase.exe
echo.
echo 按任意键关闭窗口...
pause >nul
exit /b 0
