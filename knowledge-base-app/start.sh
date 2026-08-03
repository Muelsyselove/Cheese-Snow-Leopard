#!/usr/bin/env bash
# ============================================================
# 自主知识库桌面应用 — Linux/macOS 启动脚本
#
# 功能：
#   1. 自动创建/复用 .venv 虚拟环境
#   2. 安装核心依赖（快速，排除重型 ML 包）
#   3. 启动 PySide6 桌面应用
#
# 重型依赖（paddlepaddle、FlagEmbedding/torch）不会自动安装。
# 完整功能请额外执行: pip install -r requirements.txt
#
# 用法：
#   chmod +x start.sh && ./start.sh
# ============================================================
set -e

cd "$(dirname "$0")"

VENV_DIR=".venv"
VENV_PYTHON="$VENV_DIR/bin/python"
CORE_REQUIREMENTS="requirements-core.txt"
MARKER="$VENV_DIR/.installed"
PIP_MIRROR="-i https://pypi.tuna.tsinghua.edu.cn/simple"

# ---------- 1. 检查系统 Python ----------
if ! command -v python3 >/dev/null 2>&1; then
    echo "[错误] 未找到 python3，请先安装 Python 3.10+。"
    exit 1
fi

# ---------- 2. 创建虚拟环境（首次） ----------
if [ ! -f "$VENV_PYTHON" ]; then
    echo "[初始化] 创建虚拟环境 $VENV_DIR ..."
    python3 -m venv "$VENV_DIR"
    echo "[初始化] 虚拟环境已创建。"
fi

# ---------- 3. 安装核心依赖（快速，仅首次） ----------
NEED_INSTALL=0
if [ ! -f "$MARKER" ]; then
    NEED_INSTALL=1
elif [ "$CORE_REQUIREMENTS" -nt "$MARKER" ]; then
    NEED_INSTALL=1
fi

if [ "$NEED_INSTALL" = "1" ]; then
    echo "[初始化] 安装核心依赖（快速，约1分钟）..."
    echo "[初始化]   - PySide6, PyYAML, keyring, openai, qdrant-client..."
    echo "[初始化]   - 使用清华镜像加速"
    echo "[初始化]   - 重型 ML 包（paddlepaddle/torch）已跳过"
    "$VENV_PYTHON" -m pip install --upgrade pip $PIP_MIRROR --no-cache-dir
    "$VENV_PYTHON" -m pip install -r "$CORE_REQUIREMENTS" $PIP_MIRROR --no-cache-dir --progress-bar off
    echo "installed" > "$MARKER"
    echo "[初始化] 核心依赖安装完成。"
    echo "[初始化] 如需完整功能（VLM 解析、BGE 向量化）:"
    echo "[初始化]   $VENV_PYTHON -m pip install -r requirements.txt"
fi

# ---------- 4. 启动应用 ----------
echo ""
echo "[启动] 自主知识库桌面应用 ..."
echo ""
exec "$VENV_PYTHON" main.py
