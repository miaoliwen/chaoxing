# -*- mode: python ; coding: utf-8 -*-
# 瘦身版 spec：255MB -> 目标 <80MB
# 原则：只打包 gui.py -> main.py -> api/* 静态导入链真正需要的东西。
import os

import ddddocr

# ddddocr 1.6.x: DdddOcr(show_ad=False) 即 old=False/beta=False/det=False，
# model_loader.load_ocr_model 只加载 common_old.onnx(13.6MB)。
# common.onnx(54MB, beta 模型) / common_det.onnx(20MB, 目标检测) 永远不会被加载，不打包。
_ddddocr_dir = os.path.dirname(ddddocr.__file__)

datas = [
    (os.path.join(_ddddocr_dir, 'common_old.onnx'), 'ddddocr'),
    ('resource/font_map_table.json', 'resource'),
    # 运行时窗口图标：解包到 bundle 根目录，gui.py 从 _MEIPASS/icon.ico 读取
    ('resource/icon.ico', '.'),
]
binaries = []
# api/captcha.py 顶部 `from ddddocr import DdddOcr` 是静态导入，
# PyInstaller 会自动跟踪 ddddocr 全部运行所需子模块（core/models/preprocessing/utils），
# 不再需要 collect_all 把 fastapi/mcp 服务端和全部 onnx 卷进来。
hiddenimports = ['ddddocr']

# 逐项依据（均为 Observed，来自旧包 Analysis-00.toc / xref / 源码 grep）：
# - cv2 (117MB): 仅 ddddocr/utils/exceptions.py 的 try-import 兜底，OCR 主路径不经过
# - PyQt5 (45MB): PIL.IcnsImagePlugin/PdfImagePlugin 的可选 Qt 导入被静态分析卷入，本项目 GUI 是 tkinter
# - ddddocr.api / __main__ (fastapi/mcp/pydantic-settings 链): 只有 `python -m ddddocr` 起服务才用
# - cryptography (10MB): Required-by 全是本机无关包(androguard/dashscope/pdfminer...)，项目代码零引用
# - matplotlib / botocore / jedi: 可选导入链卷入，项目零引用
# - pathops (skia.dll 5.8MB): fontTools 4.63 的 _g_l_y_f.py 中零引用（cxsecret_font 只用 TTFont/Glyph）
# - flask / celery: 只有 app.py(API服务) 用，GUI 打包入口是 gui.py
excludes = [
    # 其它 GUI 工具包（本项目用 tkinter）
    'PyQt5', 'PyQt6', 'PySide2', 'PySide6', 'wx',
    # ddddocr 自带的服务端子包
    'ddddocr.api', 'ddddocr.__main__',
    # ddddocr 的可选重依赖
    'cv2', 'opencv',
    # 画图 / 科学计算 / 交互式（未使用）
    'matplotlib', 'pandas', 'scipy', 'IPython', 'jedi', 'parso', 'asttokens',
    # 本机安装、经可选导入链被卷入的重依赖（项目零引用）
    'botocore', 'boto3', 's3transfer',
    'cryptography', 'pyOpenSSL', 'pdfminer', 'pdfminer.six', 'androguard',
    'litellm', 'llama_index', 'anthropic',
    'pathops', 'skia_pathops',
    # web 框架 / 任务队列（GUI 不打包 API 服务）
    'flask', 'fastapi', 'uvicorn', 'starlette', 'celery', 'kombu', 'billiard', 'vine', 'mcp',
    # 杂项
    'zmq', 'tornado', 'sqlalchemy', 'pytest',
]


a = Analysis(
    ['gui.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='ChaoxingHelper',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    # vcruntime 被 UPX 压缩会导致 exe 无法启动（PyInstaller 官方已知问题）
    upx_exclude=['vcruntime140.dll', 'vcruntime140_1.dll'],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='resource/icon.ico',
)
