"""原生窗口特效 — Windows DWM 圆角，其他平台自动回退

- Windows 11 22H2+：DWMWA_WINDOW_CORNER_PREFERENCE 强制圆角。
- 背景：由 QML AuroraBackground 提供深空极光渐变，**不透明**，不使用 Acrylic/Mica。
- 旧版 Windows / 其他平台：静默回退（QML 内部渐变背景仍然完整呈现）。
"""
from __future__ import annotations

import logging
import sys

logger = logging.getLogger(__name__)

# DWM 属性常量
_DWMWA_WINDOW_CORNER_PREFERENCE = 33
_DWMWA_SYSTEMBACKDROP_TYPE = 38
_DWMWCP_ROUND = 2
_DWMSBT_MAINWINDOW = 2   # Mica
_DWMSBT_TRANSIENTWINDOW = 3  # Acrylic


def apply_glass_effect(qwindow) -> bool:
    """对 QWindow 应用亚克力背景与圆角。成功返回 True，失败静默回退。"""
    if sys.platform != "win32":
        return False
    try:
        import ctypes

        hwnd = int(qwindow.winId())
        dwm = ctypes.windll.dwmapi

        # 圆角
        corner = ctypes.c_int(_DWMWCP_ROUND)
        dwm.DwmSetWindowAttribute(
            ctypes.c_void_p(hwnd), ctypes.c_uint(_DWMWA_WINDOW_CORNER_PREFERENCE),
            ctypes.byref(corner), ctypes.sizeof(corner),
        )

        # 背景材质：用户要求不透明，不再应用 Acrylic/Mica
        # for backdrop in (_DWMSBT_TRANSIENTWINDOW, _DWMSBT_MAINWINDOW):
        #     val = ctypes.c_int(backdrop)
        #     hr = dwm.DwmSetWindowAttribute(
        #         ctypes.c_void_p(hwnd),
        #         ctypes.c_uint(_DWMWA_SYSTEMBACKDROP_TYPE),
        #         ctypes.byref(val), ctypes.sizeof(val),
        #     )
        #     if hr == 0:
        #         logger.info(f"DWM 背景材质已应用: backdrop={backdrop}")
        #         return True
        return True
    except Exception as e:
        logger.warning(f"窗口特效应用失败（回退到内置渐变背景）: {e}")
        return False
