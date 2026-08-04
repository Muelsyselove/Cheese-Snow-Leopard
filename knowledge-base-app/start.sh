#!/usr/bin/env bash
# ============================================================
# 自主知识库桌面应用 — Linux/macOS 启动脚本
#
# 功能:
#   1. 校验 Python 3.10+
#   2. 创建/复用 .venv 虚拟环境
#   3. 交互选择安装模式(core 快速 / full 完整含 ML 包)
#   4. 镜像回退(清华 → 阿里 → 官方 PyPI)
#   5. 增量检测(requirements 更新或模式切换时重装)
#   6. 启动 PySide6 桌面应用
#
# 用法:
#   ./start.sh              交互模式(首次询问安装模式)
#   ./start.sh --core       强制仅装核心依赖
#   ./start.sh --full       强制装完整依赖(含 paddlepaddle/torch)
#   ./start.sh --reinstall  强制重装当前模式依赖
#   ./start.sh --help       显示此帮助
# ============================================================
set -e
cd "$(dirname "$0")"

VENV_DIR=".venv"
VENV_PYTHON="$VENV_DIR/bin/python"
CORE_REQ="requirements-core.txt"
FULL_REQ="requirements.txt"
MARKER="$VENV_DIR/.installed"
MODE_FILE="$VENV_DIR/.install_mode"

MIRROR_TSINGHUA="https://pypi.tuna.tsinghua.edu.cn/simple"
MIRROR_ALIYUN="https://mirrors.aliyun.com/pypi/simple/"

# ---------- 0. 解析参数 ----------
FORCE_MODE=""
REINSTALL=0
for arg in "$@"; do
    case "$arg" in
        --full)      FORCE_MODE="full" ;;
        --core)      FORCE_MODE="core" ;;
        --reinstall) REINSTALL=1 ;;
        --help)
            echo "用法: $0 [选项]"
            echo ""
            echo "选项:"
            echo "  (无参数)    交互模式(首次询问安装模式,后续沿用)"
            echo "  --core      强制仅装核心依赖(快速,约 100MB)"
            echo "  --full      强制装完整依赖(含 paddlepaddle/torch,约 2GB)"
            echo "  --reinstall 强制重装当前模式依赖"
            echo "  --help      显示此帮助"
            exit 0
            ;;
        *) echo "[警告] 未知参数: $arg" ;;
    esac
done

# ---------- 1. 校验 Python ----------
# 优先 python3,回退 python(部分 macOS/Windows Git Bash 仅后者在 PATH)
PYTHON_BIN=""
if command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
else
    echo "[错误] 未找到 python3/python,请先安装 Python 3.10+。"
    exit 1
fi

PYVER=$("$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')
PYMAJOR=$("$PYTHON_BIN" -c 'import sys; print(sys.version_info.major)')
PYMINOR=$("$PYTHON_BIN" -c 'import sys; print(sys.version_info.minor)')
if [ "$PYMAJOR" -lt 3 ] || { [ "$PYMAJOR" -eq 3 ] && [ "$PYMINOR" -lt 10 ]; }; then
    echo "[错误] Python 版本过低: $PYVER,需要 3.10+。"
    exit 1
fi
echo "[信息] Python $PYVER ($PYTHON_BIN) 已就绪。"

# ---------- 2. 创建虚拟环境 ----------
if [ ! -f "$VENV_PYTHON" ]; then
    echo "[初始化] 创建虚拟环境 $VENV_DIR ..."
    "$PYTHON_BIN" -m venv "$VENV_DIR"
    echo "[初始化] 虚拟环境已创建。"
fi

# ---------- 3. 决定安装模式 ----------
EXISTING_MODE="none"
if [ -f "$MODE_FILE" ]; then
    EXISTING_MODE=$(tr -d '[:space:]' < "$MODE_FILE")
    [ -z "$EXISTING_MODE" ] && EXISTING_MODE="none"
fi

if [ -n "$FORCE_MODE" ]; then
    TARGET_MODE="$FORCE_MODE"
    echo "[信息] 命令行指定模式: $TARGET_MODE"
elif [ ! -f "$MARKER" ]; then
    echo ""
    echo "请选择依赖安装模式:"
    echo "  [1] core 快速安装 约 100MB,1-2 分钟 — 仅 UI + 轻量依赖"
    echo "      含 PySide6/openai/qdrant-client/psycopg2/minio/PyMuPDF 等"
    echo "  [2] full 完整安装 约 2GB,5-15 分钟 — 含 paddlepaddle/torch/FlagEmbedding"
    echo "      额外支持 VLM 文档解析 + BGE 向量化(需 GPU 或较强 CPU)"
    echo ""
    CHOICE="1"
    read -p "请输入 1 或 2 (默认 1): " CHOICE
    if [ "$CHOICE" = "2" ]; then
        TARGET_MODE="full"
    else
        TARGET_MODE="core"
    fi
else
    TARGET_MODE="$EXISTING_MODE"
    echo "[信息] 沿用已安装模式: $TARGET_MODE"
fi

# ---------- 4. 判断是否需要安装 ----------
NEED_INSTALL=0
[ "$REINSTALL" = "1" ] && NEED_INSTALL=1
[ ! -f "$MARKER" ] && NEED_INSTALL=1
[ "$TARGET_MODE" != "$EXISTING_MODE" ] && NEED_INSTALL=1

if [ "$NEED_INSTALL" = "0" ] && [ -f "$MARKER" ]; then
    REQ_FILE_FOR_CHECK="$CORE_REQ"
    [ "$TARGET_MODE" = "full" ] && REQ_FILE_FOR_CHECK="$FULL_REQ"
    if [ "$REQ_FILE_FOR_CHECK" -nt "$MARKER" ]; then
        NEED_INSTALL=1
        echo "[信息] 检测到 $REQ_FILE_FOR_CHECK 已更新,将重新安装。"
    fi
fi

if [ "$NEED_INSTALL" = "1" ]; then
    # ---------- 5. 安装依赖(镜像回退) ----------
    REQ_FILE="$CORE_REQ"
    [ "$TARGET_MODE" = "full" ] && REQ_FILE="$FULL_REQ"

    echo "[初始化] 安装 $TARGET_MODE 依赖($REQ_FILE)..."

    pip_upgrade() {
        local mirror="$1"
        if [ -z "$mirror" ]; then
            "$VENV_PYTHON" -m pip install --upgrade pip --no-cache-dir
        else
            "$VENV_PYTHON" -m pip install --upgrade pip --no-cache-dir -i "$mirror"
        fi
    }

    install_deps() {
        local req="$1"; local mirror="$2"
        if [ -z "$mirror" ]; then
            "$VENV_PYTHON" -m pip install -r "$req" --no-cache-dir --progress-bar off
        else
            "$VENV_PYTHON" -m pip install -r "$req" --no-cache-dir --progress-bar off -i "$mirror"
        fi
    }

    echo "[初始化] 升级 pip(镜像回退)..."
    if ! pip_upgrade "$MIRROR_TSINGHUA"; then
        echo "[警告]   清华镜像失败,回退阿里云..."
        if ! pip_upgrade "$MIRROR_ALIYUN"; then
            echo "[警告]   阿里云失败,回退官方 PyPI(可能较慢)..."
            pip_upgrade "" || { echo "[错误] pip 升级失败,请检查网络。"; exit 1; }
        fi
    fi

    if ! install_deps "$REQ_FILE" "$MIRROR_TSINGHUA"; then
        echo "[警告]   清华镜像失败,尝试阿里云..."
        if ! install_deps "$REQ_FILE" "$MIRROR_ALIYUN"; then
            echo "[警告]   阿里云失败,尝试官方 PyPI(可能较慢)..."
            install_deps "$REQ_FILE" "" || {
                echo "[错误] 依赖安装失败。请手动执行:"
                echo "  $VENV_PYTHON -m pip install -r $REQ_FILE"
                exit 1
            }
        fi
    fi

    echo "installed" > "$MARKER"
    echo "$TARGET_MODE" > "$MODE_FILE"
    echo "[初始化] $TARGET_MODE 依赖安装完成。"
    if [ "$TARGET_MODE" = "core" ]; then
        echo "[提示] 当前为 core 模式,VLM 解析/BGE 向量化不可用。"
        echo "       如需完整功能: ./start.sh --full"
    fi
fi

# ---------- 6. 启动应用 ----------
echo ""
echo "[启动] 自主知识库桌面应用 ...(模式: $TARGET_MODE)"
echo ""
exec "$VENV_PYTHON" main.py
