"""启动载入界面（Splash）— 无边框圆角窗口 + 旋转光环/进度条动画

颜色跟随应用主题设置（与 ui_web/static/css/app.css 令牌保持一致）：
1. 优先读取 <data_root>/cache/theme_state.json
   （前端每次切换主题时经 WebBridge.save_theme_state 持久化，含自定义主题令牌）
2. 其次回退 config.yaml 的 ui.theme（dark/light 内置调色板）
3. 最终回退深色主题

线程模型：窗口与动画运行在 Qt 主线程；main.py 的初始化在后台线程执行，
通过 report()（Qt Signal，跨线程自动排队）上报阶段文本与进度。
"""
from __future__ import annotations

import json
import logging
import os
import sys

import yaml
from PySide6.QtCore import (
    QEasingCurve,
    QPropertyAnimation,
    QRectF,
    Qt,
    QTimer,
    Signal,
)
from PySide6.QtGui import (
    QColor,
    QConicalGradient,
    QFont,
    QLinearGradient,
    QPainter,
    QPainterPath,
    QPen,
    QRadialGradient,
)
from PySide6.QtWidgets import QApplication, QWidget

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------
# 调色板（镜像 ui_web/static/css/app.css 的 :root / [data-theme="light"]）
# ---------------------------------------------------------------
DARK_PALETTE = {
    "bg_top": "#141B36",
    "bg_mid": "#0B0F1E",
    "bg_bottom": "#0F1531",
    "text_primary": "#F2F5FF",
    "text_secondary": "#B9C1DA",
    "text_muted": "#7D87A8",
    "accent": "#22D3EE",
    "accent_violet": "#A78BFA",
}

LIGHT_PALETTE = {
    "bg_top": "#FBF7EE",
    "bg_mid": "#F6F1E5",
    "bg_bottom": "#EFE8D8",
    "text_primary": "#3A382F",
    "text_secondary": "#6E6A5E",
    "text_muted": "#A09A8B",
    "accent": "#0CA5C0",
    "accent_violet": "#8B7CF6",
}

# 前端令牌名 → 调色板键（自定义主题可覆盖这些令牌）
_TOKEN_MAP = {
    "--bg-top": "bg_top",
    "--bg-mid": "bg_mid",
    "--bg-bottom": "bg_bottom",
    "--text-primary": "text_primary",
    "--text-secondary": "text_secondary",
    "--text-muted": "text_muted",
    "--accent": "accent",
    "--accent-violet": "accent_violet",
}

_STRINGS = {
    "zh_CN": {
        "title": "知识学爆",
        "subtitle": "Cheese Snow Leopard",
        "starting": "正在启动…",
    },
    "en_US": {
        "title": "Cheese Snow Leopard",
        "subtitle": "Knowledge Base",
        "starting": "Starting…",
    },
}


def _read_yaml_config() -> dict:
    """读取 config.yaml（仅用于早期主题/语言探测，失败静默返回空）"""
    try:
        with open("config.yaml", "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    except Exception:
        return {}


def resolve_language() -> str:
    lang = str((_read_yaml_config().get("ui") or {}).get("language", "zh_CN"))
    return lang if lang in _STRINGS else "zh_CN"


def resolve_palette() -> dict:
    """解析启动画面调色板：theme_state.json > config.yaml ui.theme > dark"""
    cfg = _read_yaml_config()
    ui_cfg = cfg.get("ui") or {}
    base = "light" if str(ui_cfg.get("theme", "dark")).strip().lower() == "light" else "dark"
    tokens: dict = {}

    # 数据根目录（与 utils.paths 逻辑一致，但此处 init_paths 尚未执行）
    data_root = (cfg.get("paths") or {}).get("data_root")
    if not data_root:
        if getattr(sys, "frozen", False):
            app_root = os.path.dirname(os.path.abspath(sys.executable))
        else:
            app_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        data_root = os.path.join(app_root, "data")

    state_path = os.path.join(data_root, "cache", "theme_state.json")
    try:
        with open(state_path, "r", encoding="utf-8") as f:
            state = json.load(f)
        if state.get("base") in ("light", "dark"):
            base = state["base"]
        if isinstance(state.get("tokens"), dict):
            tokens = state["tokens"]
    except Exception:
        pass  # 文件不存在或损坏时静默回退

    palette = dict(LIGHT_PALETTE if base == "light" else DARK_PALETTE)
    for raw_key, value in tokens.items():
        if not isinstance(value, str) or not value.strip():
            continue
        key = raw_key if raw_key.startswith("--") else "--" + raw_key
        name = _TOKEN_MAP.get(key)
        if name:
            palette[name] = value.strip()
    return palette


class SplashScreen(QWidget):
    """无边框启动画面：旋转光环 + 平滑进度条 + 阶段文本"""

    progressChanged = Signal(str, float)

    WIDTH, HEIGHT = 460, 300

    def __init__(self, parent=None):
        super().__init__(parent)
        self._palette = resolve_palette()
        strings = _STRINGS.get(resolve_language(), _STRINGS["zh_CN"])
        self._title = strings["title"]
        self._subtitle = strings["subtitle"]
        self._status = strings["starting"]

        self._target = 0.0   # 目标进度（0~1）
        self._shown = 0.0    # 当前渲染进度（向目标平滑逼近）
        self._angle = 0      # 光环旋转角

        self.setWindowFlags(
            Qt.WindowType.FramelessWindowHint
            | Qt.WindowType.WindowStaysOnTopHint
            | Qt.WindowType.Tool
        )
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        self.setFixedSize(self.WIDTH, self.HEIGHT)
        self.setWindowTitle(self._title)

        self.progressChanged.connect(self._on_progress)

        self._timer = QTimer(self)
        self._timer.setInterval(16)  # ~60fps
        self._timer.timeout.connect(self._tick)
        self._timer.start()

        self._center_on_screen()

        # 淡入
        self.setWindowOpacity(0.0)
        self._fade = QPropertyAnimation(self, b"windowOpacity", self)
        self._fade.setDuration(320)
        self._fade.setStartValue(0.0)
        self._fade.setEndValue(1.0)
        self._fade.setEasingCurve(QEasingCurve.Type.OutCubic)

    # ----------------------------------------------------------- 外部接口
    def report(self, text: str, fraction: float):
        """上报初始化阶段（任意线程可调用，经 Signal 排队到 UI 线程）"""
        try:
            self.progressChanged.emit(str(text), float(fraction))
        except Exception:
            pass

    # ----------------------------------------------------------- 内部
    def show(self):  # noqa: A003 - QWidget API
        super().show()
        self._fade.start()

    def _center_on_screen(self):
        screen = QApplication.primaryScreen()
        if screen is None:
            return
        geo = screen.availableGeometry()
        self.move(
            geo.center().x() - self.WIDTH // 2,
            geo.center().y() - self.HEIGHT // 2,
        )

    def _on_progress(self, text: str, fraction: float):
        if text:
            self._status = text
        self._target = max(0.0, min(1.0, fraction))

    def _tick(self):
        self._angle = (self._angle + 6) % 360
        # 进度平滑逼近目标值
        self._shown += (self._target - self._shown) * 0.12
        if abs(self._target - self._shown) < 0.002:
            self._shown = self._target
        self.update()

    # ----------------------------------------------------------- 绘制
    def _color(self, name: str, alpha: int | None = None) -> QColor:
        c = QColor(self._palette[name])
        if alpha is not None:
            c.setAlpha(alpha)
        return c

    def paintEvent(self, event):  # noqa: N802 - Qt API
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)

        w, h = self.width(), self.height()

        # --- 圆角背景（160° 三色渐变，与应用一致） ---
        path = QPainterPath()
        path.addRoundedRect(QRectF(0.5, 0.5, w - 1, h - 1), 18, 18)
        bg = QLinearGradient(0, 0, w * 0.6, h)
        bg.setColorAt(0.0, self._color("bg_top"))
        bg.setColorAt(0.52, self._color("bg_mid"))
        bg.setColorAt(1.0, self._color("bg_bottom"))
        p.fillPath(path, bg)

        # 细描边（accent 微光）
        p.setPen(QPen(self._color("accent", 60), 1))
        p.drawPath(path)

        # --- 旋转光环 ---
        cx, cy, r = w / 2.0, 104.0, 30.0

        glow = QRadialGradient(cx, cy, r * 2.4)
        glow.setColorAt(0.0, self._color("accent", 46))
        glow.setColorAt(1.0, self._color("accent", 0))
        p.setBrush(glow)
        p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(QRectF(cx - r * 2.4, cy - r * 2.4, r * 4.8, r * 4.8))

        # 底环
        ring_rect = QRectF(cx - r, cy - r, r * 2, r * 2)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.setPen(QPen(self._color("accent", 40), 5, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap))
        p.drawEllipse(ring_rect)

        # 彗星弧（锥形渐变随角度旋转）
        conical = QConicalGradient(cx, cy, -self._angle)
        conical.setColorAt(0.0, self._color("accent"))
        conical.setColorAt(0.75, self._color("accent_violet"))
        conical.setColorAt(1.0, self._color("accent"))
        pen = QPen(5)
        pen.setBrush(conical)
        pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        p.setPen(pen)
        p.drawArc(ring_rect, int(-self._angle * 16), int(270 * 16))

        # --- 文本 ---
        font = QFont()
        font.setPointSize(20)
        font.setBold(True)
        p.setFont(font)
        p.setPen(self._color("text_primary"))
        p.drawText(QRectF(0, 158, w, 32),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                   self._title)

        font.setPointSize(10)
        font.setBold(False)
        p.setFont(font)
        p.setPen(self._color("text_muted"))
        p.drawText(QRectF(0, 190, w, 20),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                   self._subtitle)

        p.setPen(self._color("text_secondary"))
        p.drawText(QRectF(40, 222, w - 80, 20),
                   Qt.AlignmentFlag.AlignHCenter | Qt.AlignmentFlag.AlignVCenter,
                   self._status)

        # --- 进度条 ---
        bar_x, bar_w, bar_h, bar_y = 60.0, w - 120.0, 5.0, 254.0
        track = QPainterPath()
        track.addRoundedRect(QRectF(bar_x, bar_y, bar_w, bar_h), 2.5, 2.5)
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(self._color("accent", 36))
        p.drawPath(track)

        fill_w = bar_w * self._shown
        if fill_w > 0.5:
            fill = QPainterPath()
            fill.addRoundedRect(QRectF(bar_x, bar_y, fill_w, bar_h), 2.5, 2.5)
            grad = QLinearGradient(bar_x, 0, bar_x + bar_w, 0)
            grad.setColorAt(0.0, self._color("accent"))
            grad.setColorAt(1.0, self._color("accent_violet"))
            p.setBrush(grad)
            p.drawPath(fill)

        p.end()


def create_splash() -> tuple[QApplication, SplashScreen]:
    """创建（或复用）QApplication 并显示 Splash，返回 (app, splash)"""
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    splash = SplashScreen()
    splash.show()
    app.processEvents()
    return app, splash
