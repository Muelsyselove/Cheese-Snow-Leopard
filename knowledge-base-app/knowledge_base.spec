# -*- mode: python ; coding: utf-8 -*-
"""自主知识库桌面应用 — PyInstaller 打包配置

产物：dist/KnowledgeBase/KnowledgeBase.exe（onedir，windowed 无控制台窗口）

使用：
    python -m PyInstaller --noconfirm --clean knowledge_base.spec
（推荐直接运行 build_exe.bat，自动准备环境与后续拷贝）

说明：
- console=False → 启动不弹出 cmd 窗口，初始化期间由 ui_web/splash.py
  启动画面接管（跟随主题设置）。
- 建议用 core 依赖环境构建（见 requirements-core.txt），重型 ML 包
  （torch/paddle 等）已列入 excludes，打出的 exe 与 core 模式能力一致。
- config.yaml 会被打包进 _internal 作为默认配置；运行时若 exe 旁缺失
  config.yaml，main.py 会自动复制一份到 exe 旁供用户编辑。
"""
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

datas = [
    ("ui_web/static", "ui_web/static"),
    ("ui_old_v2/qml", "ui_old_v2/qml"),
    ("ui_old_v2/i18n", "ui_old_v2/i18n"),
    ("config.yaml", "."),
]
datas += collect_data_files("webview")

hiddenimports = []
hiddenimports += collect_submodules("webview.platforms")
hiddenimports += [
    "keyring.backends.Windows",
    "clr_loader",
    "pythonnet",
    "sqlalchemy.dialects.postgresql",
]

excludes = [
    # 重型 ML 依赖（core 模式不含，避免产物膨胀数 GB）
    "torch", "paddle", "paddleocr", "paddlepaddle",
    "transformers", "FlagEmbedding", "mineru", "lmdeploy",
    # 无关 GUI 框架
    "tkinter", "PyQt5", "PyQt6", "PySide2",
]


a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="KnowledgeBase",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,          # windowed：无 cmd 窗口
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="KnowledgeBase",
)
