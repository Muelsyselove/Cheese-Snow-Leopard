@echo off
chcp 65001 >nul 2>&1
setlocal EnableDelayedExpansion

REM ============================================================
REM 自主知识库桌面应用 — Windows 启动脚本
REM
REM 功能:
REM   1. 定位 Python(系统 > py 启动器 > 本地嵌入式;均无则自动下载嵌入式)
REM   2. 创建/复用 .venv 虚拟环境
REM   3. 交互选择安装模式(core 快速 / full 完整含 ML 包)
REM   4. 镜像回退(清华 → 阿里 → 官方 PyPI)
REM   5. 增量检测(requirements 更新或模式切换时重装)
REM   6. 启动 PySide6 桌面应用
REM
REM 用法:
REM   start.bat              交互模式(首次询问安装模式)
REM   start.bat --core       强制仅装核心依赖
REM   start.bat --full       强制装完整依赖(含 paddlepaddle/torch)
REM   start.bat --reinstall  强制重装当前模式依赖
REM ============================================================

cd /d "%~dp0"

set "VENV_DIR=.venv"
set "VENV_PYTHON=%VENV_DIR%\Scripts\python.exe"
set "VENV_PIP=%VENV_DIR%\Scripts\pip.exe"
set "CORE_REQ=requirements-core.txt"
set "FULL_REQ=requirements.txt"
set "MARKER=%VENV_DIR%\.installed"
set "MODE_FILE=%VENV_DIR%\.install_mode"

set "MIRROR_TSINGHUA=https://pypi.tuna.tsinghua.edu.cn/simple"
set "MIRROR_ALIYUN=https://mirrors.aliyun.com/pypi/simple/"

REM 嵌入式 Python(系统无 Python 时自动下载到此目录)
set "EMBED_DIR=.python"
set "EMBED_PYTHON=.python\python.exe"

REM ---------- 0. 解析参数 ----------
set "FORCE_MODE="
set "REINSTALL=0"
:parse_args
if "%~1"=="" goto :args_done
if /i "%~1"=="--full" set "FORCE_MODE=full"
if /i "%~1"=="--core" set "FORCE_MODE=core"
if /i "%~1"=="--reinstall" set "REINSTALL=1"
if /i "%~1"=="--help" goto :show_help
shift
goto :parse_args
:args_done

REM ---------- 1. 定位 Python ----------
REM 优先级: 系统 python > py 启动器 > 本地嵌入式 > 自动下载嵌入式
set "PYTHON_CMD="
set "USE_EMBEDDED=0"

REM 1a. 系统 python(排除 WindowsApps Store 占位符,非真实 Python 返回 9009)
for /f "tokens=* delims=" %%p in ('where python 2^>nul') do (
    echo %%p | findstr /i /c:"WindowsApps" >nul || (
        if not defined PYTHON_CMD set "PYTHON_CMD=%%p"
    )
)
if defined PYTHON_CMD goto :check_pyver

REM 1b. py 启动器(解析为实际 python.exe 路径,避免后续引号问题)
where py >nul 2>&1
if not errorlevel 1 (
    for /f "tokens=* delims=" %%e in ('py -3 -c "import sys; print(sys.executable)" 2^>nul') do (
        set "PYTHON_CMD=%%e"
    )
    if defined PYTHON_CMD goto :check_pyver
)

REM 1c. 已下载的嵌入式 Python(无 venv 模块,跳过 venv 直接使用)
if exist "%EMBED_PYTHON%" (
    set "PYTHON_CMD=%EMBED_PYTHON%"
    set "USE_EMBEDDED=1"
    goto :check_pyver
)

REM 1d. 自动下载并安装嵌入式 Python
call :install_embedded_python
if not errorlevel 1 (
    set "PYTHON_CMD=%EMBED_PYTHON%"
    set "USE_EMBEDDED=1"
    goto :check_pyver
)
echo [错误] Python 定位与自动安装均失败,请手动安装 Python 3.10+:
echo        https://www.python.org/downloads/
pause
exit /b 1

:check_pyver
REM 调用真实 python,解析版本号并校验 >= 3.10
for /f "tokens=* delims=" %%v in ('"!PYTHON_CMD!" --version 2^>^&1') do set "PYVER_LINE=%%v"
powershell -NoProfile -Command "$line='%PYVER_LINE%'; if ($line -match 'Python\s+(\d+)\.(\d+)') { $maj=[int]$Matches[1]; $min=[int]$Matches[2]; if ($maj -lt 3 -or ($maj -eq 3 -and $min -lt 10)) { exit 1 } else { exit 0 } } else { exit 2 }"
set "PYCHECK=!errorlevel!"
if "!PYCHECK!"=="0" (
    echo [信息] %PYVER_LINE% 已就绪。
    goto :venv_step
)
if "!PYCHECK!"=="1" (
    echo [错误] Python 版本过低: %PYVER_LINE%,需要 3.10+。
) else (
    echo [错误] 无法解析 Python 版本: %PYVER_LINE%
    echo        PYTHON_CMD=!PYTHON_CMD!
)
pause
exit /b 1

REM ---------- 2. 创建虚拟环境(嵌入式 Python 跳过,无 venv 模块) ----------
:venv_step
if "!USE_EMBEDDED!"=="1" (
    set "VENV_PYTHON=%EMBED_PYTHON%"
    set "MARKER=%EMBED_DIR%\.installed"
    set "MODE_FILE=%EMBED_DIR%\.install_mode"
    REM 确保 _pth 包含项目根目录(已安装的嵌入式 Python 可能缺少此配置)
    call :update_embedded_pth
    echo [信息] 使用嵌入式 Python,跳过虚拟环境创建。
    goto :venv_ready
)
if exist "%VENV_PYTHON%" goto :venv_ready
echo [初始化] 创建虚拟环境 %VENV_DIR% ...
"!PYTHON_CMD!" -m venv %VENV_DIR%
if %errorlevel%==0 goto :venv_created
echo [错误] 虚拟环境创建失败。
pause
exit /b 1
:venv_created
echo [初始化] 虚拟环境已创建。

:venv_ready
REM ---------- 3. 决定安装模式 ----------
set "EXISTING_MODE=none"
if exist "%MODE_FILE%" (
    set /p EXISTING_MODE=<"%MODE_FILE%"
)
if "!EXISTING_MODE!"=="" set "EXISTING_MODE=none"

if defined FORCE_MODE (
    set "TARGET_MODE=!FORCE_MODE!"
    echo [信息] 命令行指定模式: !TARGET_MODE!
    goto :decide_install
)
if not exist "%MARKER%" goto :ask_mode
set "TARGET_MODE=!EXISTING_MODE!"
echo [信息] 沿用已安装模式: !TARGET_MODE!
goto :decide_install

:ask_mode
echo.
echo 请选择依赖安装模式:
echo   [1] core 快速安装 约 100MB,1-2 分钟 — 仅 UI + 轻量依赖
echo       含 PySide6/openai/qdrant-client/psycopg2/minio/PyMuPDF 等
echo   [2] full 完整安装 约 2GB,5-15 分钟 — 含 paddlepaddle/torch/FlagEmbedding
echo       额外支持 VLM 文档解析 + BGE 向量化(需 GPU 或较强 CPU)
echo.
set "CHOICE=1"
set /p "CHOICE=请输入 1 或 2 (默认 1): "
if "!CHOICE!"=="2" (
    set "TARGET_MODE=full"
) else (
    set "TARGET_MODE=core"
)

:decide_install
REM ---------- 4. 判断是否需要安装 ----------
set "NEED_INSTALL=0"
if "%REINSTALL%"=="1" set "NEED_INSTALL=1"
if not exist "%MARKER%" set "NEED_INSTALL=1"
if /i "!TARGET_MODE!" neq "!EXISTING_MODE!" set "NEED_INSTALL=1"

if "!NEED_INSTALL!"=="0" if exist "%MARKER%" (
    set "REQ_FILE_FOR_CHECK=!CORE_REQ!"
    if /i "!TARGET_MODE!"=="full" set "REQ_FILE_FOR_CHECK=!FULL_REQ!"
    powershell -NoProfile -Command "if ((Get-Item '!REQ_FILE_FOR_CHECK!' -ErrorAction SilentlyContinue).LastWriteTime -gt (Get-Item '%MARKER%').LastWriteTime) { exit 0 } else { exit 1 }"
    if !errorlevel!==0 (
        set "NEED_INSTALL=1"
        echo [信息] 检测到 !REQ_FILE_FOR_CHECK! 已更新,将重新安装。
    )
)

if "!NEED_INSTALL!"=="0" goto :launch_app

REM ---------- 5. 安装依赖(镜像回退) ----------
set "REQ_FILE=!CORE_REQ!"
if /i "!TARGET_MODE!"=="full" set "REQ_FILE=!FULL_REQ!"

echo [初始化] 安装 !TARGET_MODE! 依赖(!REQ_FILE!)...
echo [初始化] 升级 pip(镜像回退)...
call :pip_upgrade_with_fallback
if %errorlevel%==0 goto :install_deps
echo [错误] pip 升级失败,请检查网络。
pause
exit /b 1

:install_deps
call :install_deps_with_fallback "!REQ_FILE!"
if %errorlevel%==0 goto :deps_done
echo [错误] 依赖安装失败。请手动执行:
echo        "%VENV_PYTHON%" -m pip install -r !REQ_FILE!
pause
exit /b 1

:deps_done
echo installed > "%MARKER%"
> "%MODE_FILE%" echo !TARGET_MODE!
echo [初始化] !TARGET_MODE! 依赖安装完成。
if /i "!TARGET_MODE!"=="core" (
    echo [提示] 当前为 core 模式,VLM 解析/BGE 向量化不可用。
    echo        如需完整功能: start.bat --full
)

:launch_app
REM ---------- 6. 引导依赖服务(PG/Qdrant/MinIO + DB 初始化 + 凭据) ----------
echo.
echo [引导] 检测并启动依赖服务 ...
"%VENV_PYTHON%" -m scripts.bootstrap
set "BOOT_RC=%errorlevel%"
if not "%BOOT_RC%"=="0" (
    echo [警告] 依赖服务引导未完全成功,应用仍将启动,部分功能可能不可用。
    echo        可在设置页面手动配置或重新运行 start.bat。
    echo.
)

REM ---------- 7. 启动应用 ----------
echo.
echo [启动] 自主知识库桌面应用 ...(模式: !TARGET_MODE!)
echo.
"%VENV_PYTHON%" main.py
set "EXIT_CODE=%errorlevel%"

echo.
if %EXIT_CODE%==0 echo [信息] 应用正常退出。
if not %EXIT_CODE%==0 echo [错误] 应用退出码 %EXIT_CODE%。
echo.
echo 按任意键关闭窗口...
pause >nul
exit /b %EXIT_CODE%

REM ============================================================
REM 子过程:升级 pip(镜像回退)
REM ============================================================
:pip_upgrade_with_fallback
echo [初始化]   尝试清华镜像...
"%VENV_PYTHON%" -m pip install --upgrade pip --no-cache-dir -i %MIRROR_TSINGHUA%
if %errorlevel%==0 exit /b 0
echo [警告]   清华镜像失败,尝试阿里云...
"%VENV_PYTHON%" -m pip install --upgrade pip --no-cache-dir -i %MIRROR_ALIYUN%
if %errorlevel%==0 exit /b 0
echo [警告]   阿里云失败,尝试官方 PyPI(可能较慢)...
"%VENV_PYTHON%" -m pip install --upgrade pip --no-cache-dir
exit /b %errorlevel%

REM ============================================================
REM 子过程:安装依赖(镜像回退)
REM %1 = requirements 文件
REM ============================================================
:install_deps_with_fallback
echo [初始化]   尝试清华镜像...
"%VENV_PYTHON%" -m pip install -r "%~1" --no-cache-dir --progress-bar off -i %MIRROR_TSINGHUA%
if %errorlevel%==0 exit /b 0
echo [警告]   清华镜像失败,尝试阿里云...
"%VENV_PYTHON%" -m pip install -r "%~1" --no-cache-dir --progress-bar off -i %MIRROR_ALIYUN%
if %errorlevel%==0 exit /b 0
echo [警告]   阿里云失败,尝试官方 PyPI(可能较慢)...
"%VENV_PYTHON%" -m pip install -r "%~1" --no-cache-dir --progress-bar off
exit /b %errorlevel%

:show_help
echo 用法: start.bat [选项]
echo.
echo 选项:
echo   (无参数)    交互模式(首次询问安装模式,后续沿用)
echo   --core      强制仅装核心依赖(快速,约 100MB)
echo   --full      强制装完整依赖(含 paddlepaddle/torch,约 2GB)
echo   --reinstall 强制重装当前模式依赖
echo   --help      显示此帮助
exit /b 0

REM ============================================================
REM 子过程:自动下载并安装嵌入式 Python
REM 产物: .python\python.exe(含 pip)
REM ============================================================
:install_embedded_python
set "EP_VERSION=3.12.7"
set "EP_ZIP=python-!EP_VERSION!-embed-amd64.zip"
set "EP_URL=https://www.python.org/ftp/python/!EP_VERSION!/!EP_ZIP!"
set "EP_TEMP=%TEMP%\!EP_ZIP!"
set "EP_GETPIP=%TEMP%\get-pip.py"
set "EP_GETPIP_URL=https://bootstrap.pypa.io/get-pip.py"

echo [初始化] 未检测到 Python,自动下载嵌入式 Python !EP_VERSION! ...
if not exist "%EMBED_DIR%" mkdir "%EMBED_DIR%"

echo [初始化]   [1/4] 下载 !EP_ZIP! ...
where curl >nul 2>&1
if not errorlevel 1 (
    curl -L --fail -# -o "!EP_TEMP!" "!EP_URL!"
) else (
    powershell -NoProfile -Command "Invoke-WebRequest -Uri '!EP_URL!' -OutFile '!EP_TEMP!' -UseBasicParsing"
)
if not exist "!EP_TEMP!" (
    echo [错误]   下载失败,请检查网络后重试: !EP_URL!
    exit /b 1
)

echo [初始化]   [2/4] 解压到 %EMBED_DIR% ...
powershell -NoProfile -Command "Expand-Archive -Path '!EP_TEMP!' -DestinationPath '%EMBED_DIR%' -Force"
del "!EP_TEMP!" 2>nul
if not exist "%EMBED_PYTHON%" (
    echo [错误]   解压失败,zip 可能损坏,请删除 %EMBED_DIR% 后重试。
    exit /b 1
)

echo [初始化]   [3/4] 启用 site-packages + 项目根目录(编辑 ._pth)...
REM _pth 文件中: '.' = .python/ 目录, '..' = 项目根目录(用于 import config/ui/services 等)
REM 注意: _pth 存在时 PYTHONPATH 被忽略,必须在此添加项目路径
powershell -NoProfile -Command "Get-ChildItem -Path '%EMBED_DIR%\python*._pth' | ForEach-Object { $content = (Get-Content $_.FullName) -replace '^#import site', 'import site'; if (-not ($content -match '^\.\.$')) { $content += '..' }; $content | Set-Content $_.FullName }"

echo [初始化]   [4/4] 引导 pip ...
where curl >nul 2>&1
if not errorlevel 1 (
    curl -L --fail -# -o "!EP_GETPIP!" "!EP_GETPIP_URL!"
) else (
    powershell -NoProfile -Command "Invoke-WebRequest -Uri '!EP_GETPIP_URL!' -OutFile '!EP_GETPIP!' -UseBasicParsing"
)
if not exist "!EP_GETPIP!" (
    echo [错误]   get-pip.py 下载失败。
    exit /b 1
)
"%EMBED_PYTHON%" "!EP_GETPIP!" --no-cache-dir -i %MIRROR_TSINGHUA%
set "EP_RC=!errorlevel!"
del "!EP_GETPIP!" 2>nul
if not "!EP_RC!"=="0" (
    echo [错误]   pip 引导失败(退出码 !EP_RC!)。
    exit /b 1
)

echo [初始化] 嵌入式 Python !EP_VERSION! 安装完成。
exit /b 0

REM ============================================================
REM 子过程:更新嵌入式 Python 的 _pth 文件
REM 确保 _pth 包含 '..'(项目根目录),否则无法 import config/ui 等模块
REM ============================================================
:update_embedded_pth
if not exist "%EMBED_DIR%" exit /b 0
powershell -NoProfile -Command "Get-ChildItem -Path '%EMBED_DIR%\python*._pth' -ErrorAction SilentlyContinue | ForEach-Object { $content = (Get-Content $_.FullName) -replace '^#import site', 'import site'; if (-not ($content -match '^\.\.$')) { $content += '..' }; $content | Set-Content $_.FullName }"
exit /b 0
