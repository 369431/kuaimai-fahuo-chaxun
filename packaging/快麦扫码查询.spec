# -*- mode: python ; coding: utf-8 -*-
"""快麦扫码查询 —— PyInstaller 单文件打包配置（入库版，全相对路径）

用法（在仓库根目录跑；也可以直接用 packaging\build.ps1 一键走完）：
    python -m PyInstaller --noconfirm --distpath <出包目录> --workpath <临时目录> packaging\快麦扫码查询.spec

注意：
- 传了 .spec 就**不能再传 --onefile / --onedir**（报 makespec options not valid when a .spec file is given）。
- hiddenimports 必须带上「只在运行时 import」的自建模块（kuaimai_print / kuaimai_print_ui /
  kuaimai_print_jobs / auto_print_watcher），否则打出来的 exe 点「打单」会 ModuleNotFoundError。
  websocket = websocket-client，内联 CDP 连 9222 要用。
  ✅ 所以**不要**用 README 里那条裸 --onefile 命令打正式包。
- 路径用 SPECPATH（spec 所在目录）推，换电脑/换目录都不用改。
"""

import os

_HERE = os.path.abspath(SPECPATH)          # …\<仓库>\packaging
_ROOT = os.path.dirname(_HERE)            # …\<仓库>
_SRC = os.path.join(_ROOT, "desktop")
_ICON = os.path.join(_HERE, "assets", "kuaimai.ico")

a = Analysis(
    [os.path.join(_SRC, "kuaimai_scan.py")],
    pathex=[_SRC],
    binaries=[],
    datas=[],
    hiddenimports=['winsound', 'websocket',
                   'kuaimai_webui', 'kuaimai_db', 'kuaimai_auth', 'kuaimai_login_ui',
                   'kuaimai_perms', 'kuaimai_client', 'kuaimai_login_window',
                   'kuaimai_admin_panel', 'kuaimai_gateway', 'kuaimai_gateway_ui',
                   'kuaimai_update', 'kuaimai_update_ui', 'kuaimai_uikit',
                   'kuaimai_print', 'kuaimai_print_ui', 'kuaimai_print_jobs',
                   'auto_print_watcher'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
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
    name='快麦扫码查询',
    icon=_ICON,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
