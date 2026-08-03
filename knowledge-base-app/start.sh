#!/usr/bin/env bash
# ============================================================
# 自主知识库桌面应用 — Linux/macOS 启动脚本
#
# 功能：
#   1. 自动创建/复用 .venv 虚拟环境
#   2. 安装依赖（首次或 requirements.txt 变更时）
#   3. 启动 PySide6 桌面应用
#
# 用法：
#   chmod +x start.sh && ./start.sh
# ============================================================
set -e

cd "$(dirname "$0")"

VENV_DIR=".venv"
VENV_PYTHON="$VENV_DIR/bin/python"
REQUIREMENTS="requirements.txt"
MARKER="$VENV_DIR/.installed"

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

# ---------- 3. 安装依赖（首次或 requirements.txt 变更） ----------
NEED_INSTALL=0
if [ ! -f "$MARKER" ]; then
    NEED_INSTALL=1
elif [ "$REQUIREMENTS" -nt "$MARKER" ]; then
    NEED_INSTALL=1
fi

if [ "$NEED_INSTALL" = "1" ]; then
    echo "[初始化] 安装依赖（可能需要几分钟，首次较慢）..."
    "$VENV_PYTHON" -m pip install --upgrade pip
    "$VENV_PYTHON" -m pip install -r "$REQUIREMENTS"
    echo "installed" > "$MARKER"
    echo "[初始化] 依赖安装完成。"
fi

# ---------- 4. 启动应用 ----------
echo ""
echo "[启动] 自主知识库桌面应用 ..."
echo ""
exec "$VENV_PYTHON" main.py
