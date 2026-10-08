# -*- mode: python ; coding: utf-8 -*-
"""快麦扫码查询 —— PyInstaller 单文件打包配置（入库版，全相对路径）

用法（在仓库根目录跑；也可以直接用 packaging\build.ps1 一键走完）：
    python -m PyInstaller --noconfirm --distpath <出包目录> --workpath <临时目录> packaging\快麦扫码查询.spec

注意：
- 传了 .spec 就**不能再传 --onefile / --onedir**（报 makespec options not valid when a .spec file is given）。
- hiddenimports 必须带上「只在运行时 import」的自建模块（kuaimai_print / kuaimai_print_ui /
  kuaimai_print_jobs / auto_print_watcher / auto_putaway / auto_audit），否则打出来的 exe 点「打单」或
  开「自动上架」「上架后自动智能审核」会 ModuleNotFoundError。
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
                   'kuaimai_print', 'kuaimai_print_ui', 'kuaimai_print_jobs', 'kuaimai_wave',
                   'auto_print_watcher', 'auto_putaway', 'auto_audit',
                   # v1.70：电脑版(Qt)界面。只在 --qt-window 那条分支里 import，
                   # 属于"运行时才导入"，必须写进 hiddenimports 否则打出来点了没反应。
                   'qtui', 'qtui.window', 'qtui.api', 'qtui.ui',
                   # v1.84：单进程启动器 + 宿主（引擎搬进电脑版自己的进程）。
                   # 运行时才 import，漏了会静默退回老两进程流程。
                   'kuaimai_qt_main', 'kuaimai_host',
                   'PySide6', 'PySide6.QtCore', 'PySide6.QtGui', 'PySide6.QtWidgets'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # v1.70：PySide6 会拖进来一大堆用不到的模块（WebEngine 一个就 150MB+）。
    # 电脑版界面只用了 QtCore / QtGui / QtWidgets，其余全排掉，包能小一半以上。
    excludes=[
        'PySide6.QtWebEngineCore', 'PySide6.QtWebEngineWidgets', 'PySide6.QtWebEngineQuick',
        'PySide6.QtQml', 'PySide6.QtQuick', 'PySide6.QtQuick3D', 'PySide6.QtQuickWidgets',
        'PySide6.Qt3DCore', 'PySide6.Qt3DRender', 'PySide6.Qt3DInput', 'PySide6.Qt3DAnimation',
        'PySide6.Qt3DExtras', 'PySide6.Qt3DLogic',
        'PySide6.QtCharts', 'PySide6.QtDataVisualization', 'PySide6.QtGraphs',
        'PySide6.QtMultimedia', 'PySide6.QtMultimediaWidgets', 'PySide6.QtSpatialAudio',
        'PySide6.QtPdf', 'PySide6.QtPdfWidgets',
        'PySide6.QtDesigner', 'PySide6.QtHelp', 'PySide6.QtUiTools', 'PySide6.QtTest',
        'PySide6.QtBluetooth', 'PySide6.QtNfc', 'PySide6.QtPositioning', 'PySide6.QtLocation',
        'PySide6.QtSensors', 'PySide6.QtSerialPort', 'PySide6.QtRemoteObjects',
        'PySide6.QtScxml', 'PySide6.QtStateMachine', 'PySide6.QtTextToSpeech',
        'PySide6.QtWebChannel', 'PySide6.QtWebSockets', 'PySide6.QtHttpServer',
        'PySide6.QtSql', 'PySide6.QtConcurrent', 'PySide6.QtDBus',
        'PySide6.QtOpenGL', 'PySide6.QtOpenGLWidgets', 'PySide6.QtOpenGLFunctions',
        'PySide6.QtPrintSupport', 'PySide6.QtSvg', 'PySide6.QtSvgWidgets',
        'PySide6.QtNetworkAuth', 'PySide6.QtXml', 'PySide6.QtCore5Compat',
    ],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

# v1.73：onefile → onedir。
# onefile 每次启动都要把 44MB 解包到 %TEMP%（主程序 5~8 秒、登录后再起 Qt 窗口又 8~13 秒）；
# onedir 不解包，主程序和 Qt 窗口都能 1 秒内起来。
# 构建脚本会把产物**拍平**到 staging 根目录（exe 和 _internal 平级），
# 这样安装后的 exe 路径跟以前一模一样，快捷方式 / 自启脚本 / 数据目录都不用改。
exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='快麦扫码查询',
    icon=_ICON,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
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
    name='快麦扫码查询',
)
