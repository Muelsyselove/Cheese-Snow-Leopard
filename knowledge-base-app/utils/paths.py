"""数据存储路径统一管理

所有应用产生的数据默认存放在程序所在目录的 data/ 文件夹下，按类别分类：
  data/
    chat/             对话历史 SQLite 数据库
    files/            原始文件存储（LocalFS 对象存储）
    mineru/           MinerU 解析中间产物
    models/           模型缓存（HF_HOME / MODELSCOPE_CACHE）
    cache/            通用缓存
    logs/             日志文件
    tmp/              临时文件

用户可在设置中调整 data 根目录，调用 migrate_data_root() 自动迁移全部内容。
路径根由 config.yaml 的 paths.data_root 控制，未配置时默认为程序目录下 ./data。
"""
from __future__ import annotations

import logging
import os
import shutil
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# 程序根目录：
# - 开发模式：main.py 所在目录（即 utils/ 的上一级）
# - PyInstaller 打包后：exe 所在目录（数据随 exe 存放，便于用户查看/迁移）
if getattr(sys, "frozen", False):
    APP_ROOT = os.path.dirname(os.path.abspath(sys.executable))
else:
    APP_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DATA_ROOT = os.path.join(APP_ROOT, "data")

# 数据子目录名
SUBDIRS = {
    "chat": "chat",
    "files": "files",
    "mineru": "mineru",
    "models": "models",
    "cache": "cache",
    "logs": "logs",
    "tmp": "tmp",
    "db": "db",
    "qdrant": "qdrant",
}

# 当前数据根目录（启动时由 init_paths() 设置）
_data_root: str = DEFAULT_DATA_ROOT


def init_paths(data_root: str | None = None):
    """初始化数据路径，创建所有子目录，并设置模型缓存环境变量。

    应在 main.py 启动最早期调用，确保所有后续路径都指向新位置。
    """
    global _data_root
    _data_root = os.path.abspath(data_root or DEFAULT_DATA_ROOT)
    # 创建所有子目录
    for sub in SUBDIRS.values():
        os.makedirs(os.path.join(_data_root, sub), exist_ok=True)
    # 设置模型缓存环境变量，避免 HuggingFace / ModelScope 下载到 C 盘
    models_dir = os.path.join(_data_root, SUBDIRS["models"])
    os.environ.setdefault("HF_HOME", models_dir)
    os.environ.setdefault("HUGGINGFACE_HUB_CACHE", models_dir)
    os.environ.setdefault("TRANSFORMERS_CACHE", models_dir)
    os.environ.setdefault("MODELSCOPE_CACHE", models_dir)
    logger.info(f"数据根目录初始化: {_data_root}")


def get_data_root() -> str:
    """获取当前数据根目录"""
    return _data_root


def get_path(name: str) -> str:
    """获取指定类别的数据目录绝对路径

    Args:
        name: 类别名（chat/files/mineru/models/cache/logs/tmp）
    """
    sub = SUBDIRS.get(name)
    if sub is None:
        raise ValueError(f"未知数据类别: {name}，可选: {list(SUBDIRS.keys())}")
    return os.path.join(_data_root, sub)


def get_chat_db_path() -> str:
    """对话历史 SQLite 数据库路径"""
    return os.path.join(get_path("chat"), "chat_history.db")


def get_mineru_output_dir() -> str:
    """MinerU 解析输出目录"""
    return os.path.join(get_path("mineru"), "output")


def get_files_root() -> str:
    """原始文件存储根目录"""
    return get_path("files")


def get_models_dir() -> str:
    """模型缓存目录"""
    return get_path("models")


def get_tmp_dir() -> str:
    """临时文件目录"""
    return get_path("tmp")


def get_logs_dir() -> str:
    """日志目录"""
    return get_path("logs")


def get_metadata_db_path() -> str:
    """元数据 SQLite 数据库路径（零配置回退方案）"""
    return os.path.join(get_path("db"), "knowledge_base.db")


def get_qdrant_local_path() -> str:
    """Qdrant 本地嵌入式存储目录（零配置回退方案，无需服务器）"""
    return get_path("qdrant")


def migrate_data_root(new_root: str) -> tuple[bool, str]:
    """迁移数据根目录到新位置

    将当前 data_root 下所有子目录内容复制到 new_root，然后更新内部指针。
    原目录保留不删除（用户可手动清理）。

    Returns:
        (success, message)
    """
    global _data_root
    new_root = os.path.abspath(new_root)
    if new_root == _data_root:
        return True, "新位置与当前位置相同，无需迁移"
    try:
        # 创建新根目录及子目录
        for sub in SUBDIRS.values():
            os.makedirs(os.path.join(new_root, sub), exist_ok=True)
        # 复制每个子目录内容
        for sub in SUBDIRS.values():
            src = os.path.join(_data_root, sub)
            dst = os.path.join(new_root, sub)
            if not os.path.isdir(src):
                continue
            for item in os.listdir(src):
                s = os.path.join(src, item)
                d = os.path.join(dst, item)
                if os.path.exists(d):
                    # 已存在则跳过（避免覆盖）
                    continue
                if os.path.isdir(s):
                    shutil.copytree(s, d)
                else:
                    shutil.copy2(s, d)
        # 更新指针
        old_root = _data_root
        _data_root = new_root
        # 更新环境变量
        models_dir = os.path.join(new_root, SUBDIRS["models"])
        os.environ["HF_HOME"] = models_dir
        os.environ["HUGGINGFACE_HUB_CACHE"] = models_dir
        os.environ["TRANSFORMERS_CACHE"] = models_dir
        os.environ["MODELSCOPE_CACHE"] = models_dir
        logger.info(f"数据已从 {old_root} 迁移到 {new_root}")
        return True, f"数据已迁移到 {new_root}\n原目录 {old_root} 保留，可手动删除。"
    except Exception as e:
        logger.error(f"数据迁移失败: {e}", exc_info=True)
        return False, f"迁移失败: {e}"


def is_default_root() -> bool:
    """当前是否使用默认程序目录"""
    return os.path.abspath(_data_root) == os.path.abspath(DEFAULT_DATA_ROOT)
