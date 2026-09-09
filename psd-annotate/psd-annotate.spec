# -*- mode: python ; coding: utf-8 -*-
# PyInstaller 打包配置：把 PSD 标注工具打成单文件 exe（psd-annotate.exe）
#
# 用法（Windows）：在 psd-annotate 目录下执行
#   pyinstaller --noconfirm psd-annotate.spec
# 前置：已安装 requirements.txt 依赖与 pyinstaller
# （推荐直接运行项目根目录 build_exe.bat 一键完成）

a = Analysis(
    ['launcher.py'],
    pathex=[],
    binaries=[],
    # 前端页面打进 exe（运行时解压到 _MEIPASS，由 core.BASE_DIR 定位）
    datas=[('static', 'static')],
    hiddenimports=[
        # psd-tools[composite] 的矢量渲染扩展（try/except 导入，需显式声明）
        'aggdraw',
        # launcher 中函数内延迟导入，显式声明防止静态分析遗漏
        'mcp_server',
        # uvicorn（MCP streamable-http 依赖）运行时动态加载的子模块
        'uvicorn.loops.auto',
        'uvicorn.loops.asyncio',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.http.h11_impl',
        'uvicorn.protocols.http.httptools_impl',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan.on',
        'uvicorn.lifespan.off',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='psd-annotate',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    runtime_tmpdir=None,
    # 保留控制台窗口显示服务日志，Ctrl+C 退出
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
