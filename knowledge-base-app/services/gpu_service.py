"""GPU 检测与计算设备选择

职责：
1. 枚举可用 NVIDIA GPU（nvidia-smi 优先，torch.cuda 兜底，均带超时/异常保护）
2. 解析用户偏好为生效设备：auto → 显存最大的 GPU；cuda:N → 指定卡；cpu → 仅 CPU
3. 启动早期通过 CUDA_VISIBLE_DEVICES 统一生效（对 torch / vllm / MinerU /
   FlagEmbedding 等所有适配器一致，无需逐个传 device 参数）

约束：
- subprocess.run 必须带 timeout（项目硬性约束）
- 本模块不 import torch 于顶层，仅在兜底分支内延迟导入
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# 生效设备偏好值的合法形式
DEVICE_AUTO = "auto"
DEVICE_CPU = "cpu"
_DEVICE_GPU_RE = re.compile(r"^cuda:(\d+)$")


@dataclass
class GpuInfo:
    index: int
    name: str
    vram_mb: int

    @property
    def label(self) -> str:
        return f"GPU {self.index} · {self.name} · {self.vram_mb // 1024} GB"


# ------------------------------------------------------------ 检测
def detect_gpus() -> list[GpuInfo]:
    """枚举 NVIDIA GPU。无 GPU / 无驱动时返回空列表。"""
    gpus = _detect_via_nvidia_smi()
    if gpus is not None:
        return gpus
    return _detect_via_torch()


def _detect_via_nvidia_smi() -> list[GpuInfo] | None:
    """nvidia-smi 查询（3s 超时）。返回 None 表示 nvidia-smi 不可用。"""
    try:
        r = subprocess.run(
            ["nvidia-smi", "--query-gpu=index,name,memory.total",
             "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=3,
        )
        if r.returncode != 0:
            return None
        gpus = []
        for line in r.stdout.strip().splitlines():
            parts = [p.strip() for p in line.split(",")]
            if len(parts) >= 3 and parts[0].isdigit():
                gpus.append(GpuInfo(
                    index=int(parts[0]), name=parts[1],
                    vram_mb=int(float(parts[2])),
                ))
        return gpus
    except Exception as e:
        logger.debug(f"nvidia-smi 检测失败: {e}")
        return None


def _detect_via_torch() -> list[GpuInfo]:
    try:
        import torch
        if not torch.cuda.is_available():
            return []
        return [
            GpuInfo(index=i,
                    name=torch.cuda.get_device_name(i),
                    vram_mb=torch.cuda.get_device_properties(i).total_memory // (1024 * 1024))
            for i in range(torch.cuda.device_count())
        ]
    except Exception:
        return []


# ------------------------------------------------------------ 解析
def strongest_gpu(gpus: list[GpuInfo]) -> GpuInfo | None:
    """性能最强的 GPU（以显存为主要指标；同显存取索引小者）"""
    if not gpus:
        return None
    return max(gpus, key=lambda g: (g.vram_mb, -g.index))


def resolve_device_index(preference: str, gpus: list[GpuInfo] | None = None) -> int | None:
    """解析偏好为物理 GPU 索引；返回 None 表示仅 CPU。

    - "auto"   → 最强 GPU（无 GPU 则 None）
    - "cpu"    → None
    - "cuda:N" → N（越界时回退 auto）
    """
    preference = (preference or DEVICE_AUTO).strip().lower()
    if preference == DEVICE_CPU:
        return None
    if gpus is None:
        gpus = detect_gpus()
    m = _DEVICE_GPU_RE.match(preference)
    if m:
        idx = int(m.group(1))
        if any(g.index == idx for g in gpus):
            return idx
        logger.warning(f"配置的 GPU 索引 {idx} 不存在，回退 auto")
    best = strongest_gpu(gpus)
    return best.index if best else None


def apply_compute_device(preference: str) -> str:
    """启动早期应用设备偏好：设置 CUDA_VISIBLE_DEVICES，返回生效描述。

    必须在任何 CUDA 上下文初始化之前调用（torch import 本身安全，
    CUDA 上下文在首次调用时才创建）。
    """
    gpus = detect_gpus()
    idx = resolve_device_index(preference, gpus)
    if idx is None:
        if (preference or "").strip().lower() not in ("", DEVICE_CPU):
            logger.info("无可用 GPU 或已选择仅 CPU，CUDA 已禁用")
        os.environ["CUDA_VISIBLE_DEVICES"] = ""
        return "cpu"
    os.environ["CUDA_VISIBLE_DEVICES"] = str(idx)
    info = next((g for g in gpus if g.index == idx), None)
    desc = f"cuda:{idx} ({info.name})" if info else f"cuda:{idx}"
    logger.info(f"计算设备: {desc}")
    return desc
