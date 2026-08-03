"""依赖管理服务 — 检查/安装/卸载可选依赖包

将可选依赖按"功能组件"分组，UI 层通过组件名操作，不直接接触 pip。
安装过程在后台线程执行，通过信号通知进度。
"""
from __future__ import annotations

import subprocess
import sys
from dataclasses import dataclass

from PySide6.QtCore import QObject, Signal


@dataclass
class DependencyComponent:
    """一个可选功能组件及其依赖包"""
    key: str                    # 组件唯一标识
    name: str                   # 显示名称
    description: str            # 功能描述
    packages: list[str]         # pip 包名列表（带版本约束）
    provider_config: dict | None = None  # 对应 config 中的 provider 值（可选）


# 可选功能组件清单（与 requirements.txt 中的可选项对齐）
OPTIONAL_COMPONENTS: list[DependencyComponent] = [
    DependencyComponent(
        key="vlm_paddleocr",
        name="VLM 方案A：PaddleOCR-VL",
        description="CPU 可运行的文档图像识别方案（paddlepaddle + paddleocr）",
        packages=["paddlepaddle>=2.6.0", "paddleocr>=2.7.0"],
        provider_config={"section": "vlm", "value": "A"},
    ),
    DependencyComponent(
        key="vlm_mineru",
        name="VLM 方案B：MinerU 框架",
        description="含 vlm/pipeline 两后端，vlm 需 GPU，pipeline 可 CPU 降级",
        packages=["mineru>=2.5.0"],
        provider_config={"section": "vlm", "value": "B"},
    ),
    DependencyComponent(
        key="vlm_minicpm",
        name="VLM 方案C：MiniCPM-V 4.5",
        description="需 GPU + lmdeploy 部署，精度最高",
        packages=["lmdeploy>=0.4.0"],
        provider_config={"section": "vlm", "value": "C"},
    ),
    DependencyComponent(
        key="embed_bge",
        name="Embedding 方案A：BGE-M3",
        description="三模态向量（dense + sparse + colbert），会拉取 torch",
        packages=["FlagEmbedding>=1.2.10"],
        provider_config={"section": "embedding", "value": "A"},
    ),
    DependencyComponent(
        key="embed_qwen3",
        name="Embedding 方案B：Qwen3-Embedding",
        description="纯 dense 向量，需 transformers + torch",
        packages=["transformers>=4.44.0", "torch>=2.3.0"],
        provider_config={"section": "embedding", "value": "B"},
    ),
    DependencyComponent(
        key="langgraph",
        name="Agent 编排：LangGraph",
        description="多步检索-生成流程编排（langgraph + langchain-core）",
        packages=["langgraph>=0.2.0", "langchain-core>=0.3.0"],
        provider_config=None,
    ),
]

# 核心（必需）依赖，用于状态展示
CORE_PACKAGES: list[str] = [
    "PySide6", "PyMuPDF", "PyYAML", "keyring", "openai",
    "qdrant-client", "psycopg2-binary", "SQLAlchemy", "minio", "tenacity",
]


def _get_pip() -> list[str]:
    """返回当前 Python 解释器对应的 pip 命令"""
    return [sys.executable, "-m", "pip"]


def is_package_installed(package_spec: str) -> bool:
    """检查单个包是否已安装。

    package_spec 可能带版本约束（如 "paddlepaddle>=2.6.0"），
    取包名部分用 importlib.metadata 检查。
    """
    import re
    from importlib import metadata
    # 提取包名（去掉版本约束）
    name = re.split(r"[<>=!~;\s]", package_spec, maxsplit=1)[0]
    # 归一化：pip 包名中的 - 对应 metadata 中的 _
    norm = name.replace("-", "_").lower()
    try:
        metadata.version(name)
        return True
    except metadata.PackageNotFoundError:
        # 尝试归一化名（部分包名带下划线）
        try:
            metadata.distribution(norm)
            return True
        except metadata.PackageNotFoundError:
            return False


def get_installed_status() -> dict[str, bool]:
    """返回所有可选组件的安装状态 {component_key: installed}"""
    return {
        comp.key: all(is_package_installed(p) for p in comp.packages)
        for comp in OPTIONAL_COMPONENTS
    }


def get_core_status() -> dict[str, bool]:
    """返回核心依赖的安装状态 {package: installed}"""
    return {p: is_package_installed(p) for p in CORE_PACKAGES}


class InstallWorker(QObject):
    """后台安装/卸载 worker

    信号：
        progress(str): 实时输出（pip stdout 行）
        finished(bool, str): 完成（成功/失败, 消息）
    """
    progress = Signal(str)
    finished = Signal(bool, str)

    def __init__(self, packages: list[str], install: bool = True,
                 mirror: str | None = None):
        super().__init__()
        self.packages = packages
        self.install = install
        self.mirror = mirror
        self._proc: subprocess.Popen | None = None

    def run(self):
        cmd = _get_pip()
        if self.install:
            cmd += ["install", "--no-cache-dir", "--progress-bar", "off"]
            if self.mirror:
                cmd += ["-i", self.mirror]
        else:
            cmd += ["uninstall", "-y"]
        cmd += self.packages

        try:
            self._proc = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                bufsize=1,
            )
            assert self._proc.stdout is not None
            for line in self._proc.stdout:
                self.progress.emit(line.rstrip("\r\n"))
            self._proc.wait()
            code = self._proc.returncode
            if code == 0:
                action = "安装" if self.install else "卸载"
                self.finished.emit(True, f"{action}完成")
            else:
                self.finished.emit(False, f"pip 退出码 {code}")
        except Exception as e:
            self.finished.emit(False, f"执行失败: {e}")

    def cancel(self):
        if self._proc and self._proc.poll() is None:
            self._proc.terminate()


class DependencyService:
    """依赖管理服务 — UI 层调用接口"""

    MIRROR_TSINGHUA = "https://pypi.tuna.tsinghua.edu.cn/simple"

    def __init__(self, mirror: str | None = None):
        self.mirror = mirror or self.MIRROR_TSINGHUA

    def list_components(self) -> list[DependencyComponent]:
        return OPTIONAL_COMPONENTS

    def get_status(self) -> dict[str, bool]:
        return get_installed_status()

    def get_core_status(self) -> dict[str, bool]:
        return get_core_status()

    def create_install_worker(self, component_keys: list[str],
                              install: bool = True) -> InstallWorker:
        """创建安装/卸载 worker（由调用者 moveToThread 并 start）"""
        pkgs: list[str] = []
        for comp in OPTIONAL_COMPONENTS:
            if comp.key in component_keys:
                pkgs.extend(comp.packages)
        return InstallWorker(pkgs, install=install, mirror=self.mirror)
