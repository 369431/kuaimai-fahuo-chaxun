# -*- coding: utf-8 -*-
"""电脑版主窗口（Qt）。

· 窗口外观：mac 风格标题栏 + 二级菜单 + 浅/深色切换
· 窗口行为：**全部原生** —— 处理 WM_NCCALCSIZE 去掉系统标题栏，但保留标准窗口样式，
  所以拖动 / Aero 贴边 / 双击最大化 / 边缘缩放 / 任务栏 都还是 Windows 原生的（不自己写拖拽）
· 数据：全走本机 127.0.0.1:8790 的现成接口（见 api.py），**主程序一行不用改**

单跑：
    python -m qtui.window                       # 弹登录框
    python -m qtui.window --user admin --pw xxx  # 直接登录
    python -m qtui.window --shot out.png        # 截图后退出（自检用）
"""
import argparse
import json
import ctypes
import os
import sys
import tempfile
import threading
import time
from ctypes import wintypes

from PySide6.QtCore import QObject, Qt, QTimer, Signal
from PySide6.QtGui import QColor, QPainter
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QFileDialog,
                               QFrame, QHBoxLayout, QHeaderView, QInputDialog, QLabel,
                               QLineEdit, QMenu, QMessageBox, QPlainTextEdit, QPushButton,
                               QTableWidget, QTableWidgetItem, QTabWidget, QVBoxLayout,
                               QWidget)

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from qtui import ui as U            # noqa: E402
from qtui.api import Api            # noqa: E402


def _BUILD_TAG():
    """本次构建的打包时间：给"到底跑的是哪个版本"一个一眼可辨的凭据。

    为什么需要：用户反复反馈"点的还是旧版本/没反应"，而光看界面长得一样分不清。
    打包成 exe 时取 exe 自己的时间戳（模块 __file__ 在解包目录里，时间没意义）。
    """
    try:
        p = sys.executable if getattr(sys, "frozen", False) else __file__
        return "（构建 " + time.strftime("%m-%d %H:%M",
                                      time.localtime(os.path.getmtime(p))) + "）"
    except Exception:
        return ""


try:
    import kuaimai_client as kmclient   # 登录逻辑复用桌面端那一套（校验/设备/模式全一致）
except Exception:
    kmclient = None

# ---------------- Win32（原生窗口行为） ----------------
u32 = ctypes.windll.user32
dwm = ctypes.windll.dwmapi
WM_NCCALCSIZE, WM_NCHITTEST = 0x0083, 0x0084
WM_ENTERSIZEMOVE, WM_EXITSIZEMOVE = 0x0231, 0x0232
HTCAPTION, HTCLIENT = 2, 1
HTLEFT, HTRIGHT, HTTOP, HTBOTTOM = 10, 11, 12, 15
HTTOPLEFT, HTTOPRIGHT, HTBOTTOMLEFT, HTBOTTOMRIGHT = 13, 14, 16, 17
DWMWA_WINDOW_CORNER_PREFERENCE = 33
TITLE_H, RESIZE_B = 46, 7

u32.GetWindowRect.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)]
u32.IsZoomed.argtypes = [wintypes.HWND]
u32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
u32.MonitorFromWindow.restype = wintypes.HANDLE


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


class NCCALCSIZE_PARAMS(ctypes.Structure):
    _fields_ = [("rgrc", wintypes.RECT * 3), ("lppos", ctypes.c_void_p)]


u32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.POINTER(MONITORINFO)]


# ---------------- 后台轮询（不卡界面） ----------------
class Dispatcher(QObject):
    """把"在后台线程里算完的结果"安全地丢回主线程执行。

    为什么不用 QTimer.singleShot：QTimer 依赖调用线程里的事件循环，
    在普通 Python 线程里调它可能静默失效（界面就不更新了）。
    用 Signal 则跨线程自动排队到主线程，跟 Poll 是同一套机制。
    """
    call = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.call.connect(self._run, Qt.QueuedConnection)

    def _run(self, fn):
        try:
            fn()
        except Exception:
            pass

    def post(self, fn):
        self.call.emit(fn)


class Poll(QObject):
    got = Signal(object)

    def __init__(self, fn, every_ms, parent=None):
        super().__init__(parent)
        self.fn = fn
        self._busy = False
        self.t = QTimer(self)
        self.t.setInterval(int(every_ms))
        self.t.timeout.connect(self.fire)

    def fire(self):
        if self._busy:
            return
        self._busy = True

        def work():
            try:
                r = self.fn()
            except Exception as e:
                r = {"error": str(e)[:120]}
            try:
                self.got.emit(r)
            finally:
                self._busy = False

        threading.Thread(target=work, daemon=True).start()

    def start(self):
        self.fire()
        self.t.start()


# ---------------- 登录框 ----------------
class LoginDialog(QDialog):
    def __init__(self, api, parent=None):
        super().__init__(parent)
        self.api = api
        self.setWindowTitle("登录 快麦发货查询")
        self.setFixedSize(400, 300)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(9)
        t = QLabel("登录后才能看到数据")
        t.setObjectName("sect")
        lay.addWidget(t)
        tip = QLabel("用【手机扫码登录】那套管理员账号（一般就是 admin）")
        tip.setObjectName("hint")
        tip.setWordWrap(True)
        lay.addWidget(tip)
        self.name = QLineEdit("admin")
        self.name.setPlaceholderText("账号")
        self.name.setMinimumHeight(38)
        lay.addWidget(self.name)
        self.pw = QLineEdit()
        self.pw.setEchoMode(QLineEdit.Password)
        self.pw.setPlaceholderText("密码")
        self.pw.setMinimumHeight(38)
        self.pw.returnPressed.connect(self.do)
        rowp = QHBoxLayout()
        rowp.setSpacing(6)
        rowp.addWidget(self.pw, 1)
        self.eye = QPushButton("👁")
        self.eye.setObjectName("icon")
        self.eye.setCheckable(True)
        self.eye.setFixedWidth(40)
        self.eye.setToolTip("按住/点一下：显示密码（排查输入问题用）")
        self.eye.toggled.connect(
            lambda on: self.pw.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password))
        rowp.addWidget(self.eye)
        lay.addLayout(rowp)
        self.msg = QLabel("")
        self.msg.setObjectName("hint")
        lay.addWidget(self.msg)
        row = QHBoxLayout()
        row.addStretch(1)
        b = U.GlowButton("登  录", primary=True)
        b.clicked.connect(self.do)
        row.addWidget(b)
        lay.addLayout(row)

    def do(self):
        self.msg.setText("登录中…")
        QApplication.processEvents()
        ok, err = self.api.login(self.name.text(), self.pw.text())
        if ok:
            self.accept()
        else:
            self.msg.setText("%s（账号：%s）" % (err or "登录失败", self.name.text().strip()))
            self.msg.setWordWrap(True)


class LoginScreen(QDialog):
    """Qt 版登录窗（替代老的 Tk 登录窗）。

    跟电脑版界面同一套配色/发光按钮，用户看到的就只有一个新程序。
    登录成功后：
      · 用 kuaimai_client.login 拿真正的会话（跟老登录窗走同一套逻辑，行为一致）
      · 把会话写进 --login-out 指定的文件，主程序读到就接着往下走
    """

    def __init__(self, base, out_file, theme="light", parent=None):
        super().__init__(parent)
        self.base = base
        self.out_file = out_file
        self._disp = Dispatcher(self)          # 跨线程回主线程（跟主窗口同一套机制）
        self.setWindowTitle("快麦发货查询")
        self.setFixedSize(470, 430)
        self.setStyleSheet(U.qss(U.LIGHT if theme == "light" else U.DARK))

        lay = QVBoxLayout(self)
        lay.setContentsMargins(26, 22, 26, 20)
        lay.setSpacing(9)

        head = QHBoxLayout()
        brand = QLabel("快麦发货查询")
        brand.setObjectName("brand")
        head.addWidget(brand)
        head.addStretch(1)
        ver = QLabel(" " + str(getattr(kmclient, "APP_VER", "") or "") + " ")
        ver.setObjectName("badge")
        head.addWidget(ver)
        lay.addLayout(head)

        sub = QLabel("登录后才能查询和打印")
        sub.setObjectName("hint")
        lay.addWidget(sub)
        lay.addSpacing(4)

        lay.addWidget(self._lbl("账号"))
        self.name = QLineEdit("admin")
        self.name.setMinimumHeight(42)
        lay.addWidget(self.name)

        lay.addWidget(self._lbl("密码"))
        prow = QHBoxLayout()
        prow.setSpacing(6)
        self.pw = QLineEdit()
        self.pw.setEchoMode(QLineEdit.Password)
        self.pw.setMinimumHeight(42)
        self.pw.returnPressed.connect(self.do_login)
        prow.addWidget(self.pw, 1)
        self.eye = QPushButton("👁")
        self.eye.setObjectName("icon")
        self.eye.setCheckable(True)
        self.eye.setFixedWidth(44)
        self.eye.setToolTip("显示密码（排查输入问题）")
        self.eye.toggled.connect(
            lambda on: self.pw.setEchoMode(QLineEdit.Normal if on else QLineEdit.Password))
        prow.addWidget(self.eye)
        lay.addLayout(prow)

        lay.addWidget(self._lbl("主客户端地址（本机留空；子客户端填主机 IP）"))
        self.host = QLineEdit()
        self.host.setPlaceholderText("例如 192.168.1.5")
        self.host.setMinimumHeight(38)
        lay.addWidget(self.host)

        self.msg = QLabel("")
        self.msg.setObjectName("hint")
        self.msg.setWordWrap(True)
        self.msg.setMinimumHeight(40)
        lay.addWidget(self.msg)
        lay.addStretch(1)

        row = QHBoxLayout()
        self.b_setup = U.GlowButton("首次设置", glow=30)
        self.b_setup.setToolTip("这台电脑是主机、还没建管理员账号时点这里")
        self.b_setup.clicked.connect(self.do_setup)
        row.addWidget(self.b_setup)
        # ★ 登录页也要能「检查更新」：更新跟登录没关系，没登录也该能查、能下。
        b_upd = U.GlowButton("检查更新")
        b_upd.setToolTip("看看有没有新版本（不用登录也能查）")
        b_upd.clicked.connect(lambda *a: self.do_check_update())
        row.addWidget(b_upd)
        row.addStretch(1)
        self.btn = U.GlowButton("登  录", primary=True)
        self.btn.setMinimumHeight(46)
        self.btn.clicked.connect(self.do_login)
        row.addWidget(self.btn)
        lay.addLayout(row)

        # ★ 「首次设置」只在真的还没建管理员时才显示。
        #   以前它无条件挂着，已经建好账号的用户每次开机都看见 → 以为又要「首次设置」，
        #   而且万一点了还会把管理员密码重置掉。这里问一下服务端再决定显不显示。
        QTimer.singleShot(120, self._refresh_setup_btn)

    def _refresh_setup_btn(self):
        if kmclient is None:
            return

        def work():
            try:
                mode, base = self._mode_base()
                ok, st = kmclient.server_state(base)
                need = bool(ok and isinstance(st, dict) and st.get("need_setup"))
            except Exception:
                return

            def ui():
                try:
                    self.b_setup.setVisible(bool(need))
                    if need:
                        self.msg.setText("这台电脑还没建管理员账号：点左下「首次设置」创建。")
                except Exception:
                    pass

            self._disp.post(ui)

        threading.Thread(target=work, daemon=True).start()

    def _lbl(self, t):
        w = QLabel(t)
        w.setObjectName("hint")
        return w

    def _mode_base(self):
        h = (self.host.text() or "").strip()
        if not h:
            return "host", self.base
        if not h.lower().startswith("http"):
            h = "https://" + h
        return "remote", h

    def _busy(self, on, text=""):
        self.btn.setEnabled(not on)
        self.msg.setText(text or ("正在登录…" if on else ""))
        QApplication.processEvents()

    def do_login(self):
        if kmclient is None:
            self.msg.setText("缺少登录模块（kuaimai_client.py），请重新安装。")
            return
        name = (self.name.text() or "").strip()
        pw = self.pw.text()
        if not name or not pw:
            self.msg.setText("账号和密码都要填")
            return
        mode, base = self._mode_base()
        self._busy(True)
        try:
            sess, err = kmclient.login(base, name, pw, mode=mode)
        except Exception as e:
            sess, err = None, str(e)[:150]
        if sess is None or not getattr(sess, "token", ""):
            self._busy(False, "%s（账号：%s）" % (err or "登录失败", name))
            return
        self._save(sess)
        self.accept()

    def do_check_update(self):
        """检查更新（登录页 / 主界面共用同一个窗）。

        ★ 登录页没有 self.api（它只有 base），所以这里一律用 getattr 兜底 ——
          以前直接取 self.api 会 AttributeError，点一下就弹「打不开检查更新窗」。
        """
        cur = ""
        try:
            cur = getattr(getattr(self, "api", None), "ver", "") or ""
        except Exception:
            cur = ""
        if not cur:
            try:
                import kuaimai_client as _kc
                cur = str(getattr(_kc, "APP_VER", "") or "")
            except Exception:
                cur = ""
        try:
            d = CheckUpdateDialog(getattr(self, "api", None),
                                  getattr(self, "theme", "light"), self, current=cur)
            d.exec()
        except Exception as e:
            QMessageBox.warning(self, "检查更新", "打不开检查更新窗：%s" % str(e)[:200])

    def do_setup(self):
        """首次设置管理员（只有主机本机能做）。"""
        if kmclient is None:
            return
        from PySide6.QtWidgets import QInputDialog
        name, ok = QInputDialog.getText(self, "首次设置", "管理员账号：", text="admin")
        if not ok or not (name or "").strip():
            return
        pw, ok = QInputDialog.getText(self, "首次设置", "新密码（至少 4 位）：",
                                      QLineEdit.Password)
        if not ok or not pw:
            return
        if len(pw) < 4:
            self.msg.setText("密码至少 4 位")
            return
        self._busy(True, "正在创建…")
        try:
            sess, err = kmclient.setup(self.base, name.strip(), pw)
        except Exception as e:
            sess, err = None, str(e)[:150]
        if sess is None or not getattr(sess, "token", ""):
            self._busy(False, err or "创建失败")
            return
        self._save(sess)
        self.accept()

    def _save(self, sess):
        """把会话写给主程序（它读到就继续启动后台）。"""
        try:
            data = {
                "mode": getattr(sess, "mode", "host"),
                "base": getattr(sess, "base", self.base),
                "token": getattr(sess, "token", ""),
                "name": getattr(sess, "name", ""),
                "role": getattr(sess, "role", ""),
                "server_name": getattr(sess, "server_name", ""),
            }
            with open(self.out_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False)
        except Exception:
            pass


# ---------------- 主窗口 ----------------
class ClickLabel(QLabel):
    """可点击的 QLabel（状态条用它做「点一下立刻重测」）。"""

    clicked = Signal()

    def mousePressEvent(self, ev):
        try:
            self.clicked.emit()
        except Exception:
            pass
        try:
            QLabel.mousePressEvent(self, ev)
        except Exception:
            pass


def setup_table(t, widths):
    """表格通用外观（模块级函数：Desktop 和各个 QDialog 都要用，不能只在 Desktop 上）。

    · 竖表头隐藏、无网格、整行选择、只读
    · widths 里给 0 的列用 Stretch（自适应剩余宽度），其余固定宽度
    """
    t.verticalHeader().setVisible(False)
    t.setShowGrid(False)
    try:
        t.viewport().setAutoFillBackground(False)
    except Exception:
        pass
    t.setSelectionBehavior(QTableWidget.SelectRows)
    t.setEditTriggers(QTableWidget.NoEditTriggers)
    t.verticalHeader().setDefaultSectionSize(34)
    hh = t.horizontalHeader()
    hh.setSectionResizeMode(QHeaderView.Fixed)
    for i, w in enumerate(widths):
        if w:
            t.setColumnWidth(i, w)
        else:
            hh.setSectionResizeMode(i, QHeaderView.Stretch)


class Desktop(QWidget):
    def __init__(self, api):
        super().__init__()
        self.api = api
        self.theme = "light"
        self.hwnd = int(self.winId())
        self._dpr = float(self.devicePixelRatioF() or 1.0)
        self._nodrag = []
        self.setObjectName("root")
        self._bg = QColor(U.LIGHT["bg"])
        self.setAttribute(Qt.WA_OpaquePaintEvent, True)
        self.setWindowTitle("快麦发货查询 · 电脑版 · 新版界面Qt%s" % _BUILD_TAG())
        self.resize(1240, 820)
        self.setMinimumSize(940, 600)
        self._build()
        self._apply_theme()
        QTimer.singleShot(60, self._setup_frame)
        QTimer.singleShot(200, self._start_poll)

    # ---------- 菜单动作表 ----------
    # 键 =「主程序侧动作」名字（服务器端白名单）
    _ACTS = {
        "API 设置": "api_settings",
        "对外访问设置": "gateway",
        "子客户端管理": "admin",
        "打印分工": "print_clients",
        "登录 ERP": "erp_login",
        "检查更新": "check_update",
        "打单进度 / 实时日志": None,          # 本地弹日志窗
        "按条件筛选（本地）": "apply_filter",
        "现货可发": "stock",
        "批次查询": "batch",
        "盘点": "stocktake",
        "每日发货量": "ship_stats",
    }
    # 键 =「开关」名字（/api/desktop/opt）
    _TOGGLES = {
        "自动上架推荐货位": "auto_putaway",
        "上架后自动智能审核": "auto_audit",
        "后台扫码监听": "bg_listen",
        "声音提示": "sound",
        "手机访问需口令": "key",
    }

    def _actions(self):
        # ★ 全部用 lambda *a, ... 包一层。
        #   QAction.triggered 会带一个 checked(布尔) 参数；PySide6 按"能接受几个参数"传参，
        #   写成 lambda n=name: 的话它会被当成"能接受 1 个"，于是 checked 把 n 覆盖掉 →
        #   发出去的变成 'False'（实测报"不支持的动作：'False'"）。
        #   lambda *a, n=name: 既能吃掉多余参数，又能把 name 锁在当前这一项上。
        out = {
            "增量刷新": lambda *a: self.do_refresh("inc"),
            "全量重拉": lambda *a: self.do_refresh("full"),
            "刷新货位库存": lambda *a: self.do_refresh("shelf"),
            "刷新锁定数": lambda *a: self.do_refresh("lock"),
            "导出扫码日志 Excel": lambda *a: self.do_export(),
            "清空日志": lambda *a: self.do_clearlog(),
            "可发撤回宽限…": lambda *a: self.do_hold(),
            "打单进度 / 实时日志": lambda *a: self.do_print_progress(),
            "重新登录": lambda *a: self.do_logout(),
            "打开数据目录": lambda *a: self.do_action("open_dir"),
            "打开数据文件": lambda *a: self.do_action("open_db"),
            "关于": lambda *a: self.do_about(),
            # ★ 检查更新也用电脑版自己的窗（以前调主程序弹旧版更新窗）
            "检查更新": lambda *a: self.do_check_update(),
        }
        for label, name in self._ACTS.items():
            if name:
                out[label] = (lambda *a, n=name: self.do_action(n))
            else:
                out[label] = (lambda *a: self.do_log())
        # 能用通用表格接口拿到数据的，走 Qt 表格窗（放在 _ACTS 之后，好覆盖同名项）
        out["现货可发"] = (lambda *a: self._open_dlg(StockDialog, "现货可发"))
        # 「按条件筛选（本地）」= 旧版那个带筛选的现货可发窗，跟「现货可发」是同一个功能
        out["按条件筛选（本地）"] = (lambda *a: self._open_dlg(StockDialog, "按条件筛选"))
        out["改库存日志"] = (lambda *a: self.do_table("adjust_log"))
        out["盘点"] = (lambda *a: self.do_stocktake())
        out["批次查询"] = (lambda *a: self.do_batch())
        out["每日发货量"] = (lambda *a: self.do_ship_stats())
        # ★ 三个设置窗也不再弹旧 Tk 窗了，改成电脑版自己的 Qt 窗
        out["子客户端管理"] = (lambda *a: self._open_dlg(AdminPanelDialog, "子客户端管理"))
        out["打印分工"] = (lambda *a: self._open_dlg(PrintClientsDialog, "打印分工"))
        out["对外访问设置"] = (lambda *a: self._open_dlg(GatewayDialog, "对外访问设置"))
        # ★ API 设置也换成 Qt 窗（以前调主程序弹旧 Tk 窗，用户要求不要看到旧界面）
        out["API 设置"] = (lambda *a: self._open_dlg(ApiSettingsDialog, "API 设置"))
        for label, key in self._TOGGLES.items():
            out[label] = (lambda *a, k=key: self.do_opt(k))
        return out

    _TOGGLE_ACTS = {}

    # ---------- 界面 ----------
    def _build(self):
        self._TOGGLE_ACTS = {}
        self._disp = Dispatcher(self)
        self._ACTION = self._actions()
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.tb = U.MacTitleBar(self, "快麦发货查询", self.api.ver or "电脑版",
                                on_theme=self.toggle_theme)
        self.tb.title.setText("电脑版 · 本机服务（同一进程）")
        # 二级菜单：数据 / 设置 / 系统
        for name, items in (
            ("数据", ["增量刷新", "全量重拉", "刷新货位库存", "刷新锁定数",
                     "导出扫码日志 Excel", "清空日志", "-",
                     "按条件筛选（本地）", "现货可发", "批次查询",
                     "改库存日志", "盘点", "每日发货量"]),
            ("设置", ["API 设置", "对外访问设置", "子客户端管理", "打印分工",
                     "登录 ERP", "-",
                     "可发撤回宽限…", "自动上架推荐货位", "上架后自动智能审核",
                     "后台扫码监听", "声音提示", "手机访问需口令"]),
            ("系统", ["检查更新", "重新登录", "打单进度 / 实时日志", "-",
                     "打开数据目录", "打开数据文件", "关于"]),
        ):
            b = self.tb.menu_button(name)
            m = QMenu(b)
            for it in items:
                if it == "-":
                    m.addSeparator()
                    continue
                act = m.addAction(it)
                if it in self._TOGGLES:            # 开关类：可勾选，勾选状态跟着主程序走
                    act.setCheckable(True)
                    self._TOGGLE_ACTS[self._TOGGLES[it]] = act
                fn = self._ACTION.get(it)
                if fn:
                    act.triggered.connect(fn)
                else:
                    act.setEnabled(False)
            b.setMenu(m)
            self.tb.extra.addWidget(b)
        root.addWidget(self.tb)

        body = QWidget()
        body.setObjectName("body")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(16, 12, 16, 10)
        bl.setSpacing(10)
        root.addWidget(body, 1)

        # ── 扫码行 ──
        p1 = U.panel()
        l1 = QVBoxLayout(p1)
        l1.setContentsMargins(14, 12, 14, 12)
        l1.setSpacing(9)
        head = QLabel("扫码查询")
        head.setObjectName("sect")
        l1.addWidget(head)
        row = QHBoxLayout()
        row.setSpacing(10)
        lb = QLabel("商家编码")
        lb.setObjectName("hint")
        row.addWidget(lb)
        self.ent = QLineEdit()
        self.ent.setPlaceholderText("把光标放这里，扫码枪扫一下 / 或输入后回车")
        self.ent.setMinimumHeight(46)
        self.ent.returnPressed.connect(self.do_lookup)
        row.addWidget(self.ent, 1)
        self.btn_q = U.GlowButton("查 询", primary=True)
        self.btn_q.setMinimumHeight(48)
        self.btn_q.clicked.connect(self.do_lookup)
        row.addWidget(self.btn_q)
        l1.addLayout(row)
        self.hint = QLabel("正在连接本机服务…")
        self.hint.setObjectName("hint")
        l1.addWidget(self.hint)
        # ★ 状态条（原型里画过、但真程序一直没做）：ERP 登录 / 手机端 / 开放平台接口。
        #   数据全来自接口：/api/auth/state 的 user·owner、/api/desktop/state 的 text、
        #   /api/desktop/api_conf 的 appKey·sessionId。
        srow = QHBoxLayout()
        srow.setSpacing(14)
        self.chips = {}
        for key, tip in (("erp", "ERP 登录状态（看自动化浏览器那个会话）。"
                                 "点「登录 ERP」打开浏览器登录后，这里会变成已登录"),
                         ("phone", "外网访问：域名 / 9443 / frpc 隧道 是否都正常"),
                         ("api", "快麦开放平台参数是否配好（API 设置里填）")):
            c = ClickLabel("● —")
            c.setObjectName("hint")
            c.setToolTip(tip)
            c.setCursor(Qt.PointingHandCursor)
            # ★ 点状态条 = 立刻重新检测（不用等下一轮 8 秒）。
            #   用点击子类而不是魔改 mousePressEvent：实例上直接赋值在 PySide6 里容易失效。
            if isinstance(c, ClickLabel):
                c.clicked.connect(lambda k=key: self._poll_chips())
            srow.addWidget(c)
            self.chips[key] = c
        srow.addStretch(1)
        l1.addLayout(srow)
        # ★ 「最近操作」提示行：放在**顶部**扫码区下面。
        #   为什么不在底部状态栏：实测这台机器窗口高 858、屏幕可用高只有 1104，
        #   窗口一往下放，底部状态栏就整个跑到屏幕外面去了，用户根本看不见 →
        #   点「按条件筛选」这类"只改状态文字"的动作就以为没反应。放上面一定看得见。
        self.lbl_hint = QLabel("")
        self.lbl_hint.setObjectName("hint")
        self.lbl_hint.setStyleSheet("color:#0b5394;font-weight:700;")
        l1.addWidget(self.lbl_hint)
        # ★ 更醒目的一条：点完动作直接横一条亮色提示（6 秒后自己消失）。
        #   用户反馈"点了没反应"，所以不能只改一行小字 —— 要有挡不住看不见的东西。
        self.banner = QLabel("")
        self.banner.setWordWrap(True)
        self.banner.setStyleSheet(
            "background:#0b5394;color:#ffffff;font-weight:700;"
            "padding:9px 14px;border-radius:8px;")
        self.banner.setVisible(False)
        l1.addWidget(self.banner)
        bl.addWidget(p1)

        # ── 结果 ──
        p2 = U.panel()
        l2 = QVBoxLayout(p2)
        l2.setContentsMargins(14, 13, 14, 13)
        l2.setSpacing(6)
        self.res_code = QLabel("扫码或输入编码后回车")
        self.res_code.setObjectName("code")
        self.res_code.setAlignment(Qt.AlignCenter)
        l2.addWidget(self.res_code)
        self.res_sub = QLabel("")
        self.res_sub.setAlignment(Qt.AlignCenter)
        self.res_sub.setObjectName("sect")
        l2.addWidget(self.res_sub)
        # ★ 结果表：查「款号」返回的是一个系列（几十个规格），一行标签放不下，
        #   以前只在标签里拼几个字段 → 系列结果直接显示"没有可显示的字段"。
        #   这里把每个规格列出来（跟旧版一样能看到各规格的货位/在架）。
        self.t_res = QTableWidget(0, 6)
        self.t_res.setHorizontalHeaderLabels(["编码", "货位", "在架数", "待发货", "锁定", "订单数"])
        setup_table(self.t_res, [200, 150, 80, 80, 80, 80])
        self.t_res.setMaximumHeight(190)
        self.t_res.setVisible(False)
        l2.addWidget(self.t_res)
        bl.addWidget(p2)

        # ── 记录表（扫码记录 / 波次记录）──
        p3 = U.panel()
        l3 = QVBoxLayout(p3)
        l3.setContentsMargins(10, 8, 10, 10)
        l3.setSpacing(6)
        self.tabs = QTabWidget()
        l3.addWidget(self.tabs)

        # 波次记录（一行 = 一个波次；点一下看详情）
        # ★ 「货位」列已删（平台不返回货位）。
        # ★ 「商家编码」已换成「拣货人」：这一列是网页端波次的 pickerName，
        #   即**拣货/操作这个波次的人**，不是验货人（打包账号只在操作日志里，
        #   而按订单号查那个日志会 ERP 服务端超时，暂时拿不到 —— 别把列名写错误导人）。
        self.t_wave = QTableWidget(0, 8)
        # ★「实发/订单」要给足宽度：内容是「179 / 180」这种，加上表头，
        #   原来 90px 会被截断成「…」（用户反馈过）。所以表头写短一点 + 列宽 110。
        self.t_wave.setHorizontalHeaderLabels(
            ["波次号", "生成时间", "拣货人", "件数", "生成账号", "拣货数量",
             "实发/订单", "波次状态"])
        self._tbl_setup(self.t_wave, widths=[110, 150, 100, 60, 90, 80, 110, 100])
        self.t_wave.cellClicked.connect(self.on_wave_click)
        # ★ 顺序按用户要求调换：波次记录在前，扫码记录在后
        self.tabs.addTab(self.t_wave, "波次记录")

        # 扫码记录
        self.t_scan = QTableWidget(0, 8)
        self.t_scan.setHorizontalHeaderLabels(
            ["时间", "编码", "待发", "货位", "账号", "可打", "状态", "打印"])
        self._tbl_setup(self.t_scan, widths=[120, 0, 60, 90, 80, 60, 100, 60])
        self.tabs.addTab(self.t_scan, "扫码记录")
        # ★ 选中波次的详情行（平台不返回具体货位，就把能拿到的都摊开给用户看）
        self.lbl_wave_info = QLabel("")
        self.lbl_wave_info.setObjectName("hint")
        self.lbl_wave_info.setWordWrap(True)
        l3.addWidget(self.lbl_wave_info)
        # 页签划过发光（扫码记录 / 波次记录）
        self._tabglow = self.tb.tab_glow(self.tabs)
        bl.addWidget(p3, 1)

        # ── 状态栏 ──
        foot = QFrame()
        foot.setObjectName("foot")
        fv = QVBoxLayout(foot)
        fv.setContentsMargins(16, 5, 16, 6)
        fv.setSpacing(1)
        # 上排：主程序状态（这一行每 1.5 秒被自动刷新覆盖）
        fl = QHBoxLayout()
        self.st_left = QLabel("就绪")
        self.st_left.setObjectName("hint")
        fl.addWidget(self.st_left)
        fl.addStretch(1)
        self.st_right = QLabel("")
        self.st_right.setObjectName("dimmer")
        fl.addWidget(self.st_right)
        fv.addLayout(fl)
        # 下排：最近操作提示（★ 顶部那条不会掉到屏幕外的提示行更主要，这里只作补充）
        root.addWidget(foot)
        self._nodrag = list(self.tb.dots) + [self.tb.theme_btn] + \
            [self.tb.extra.itemAt(i).widget() for i in range(self.tb.extra.count())]

    def _tbl_setup(self, t, widths):
        setup_table(t, widths)

    def _apply_theme(self):
        c = U.LIGHT if self.theme == "light" else U.DARK
        self.setStyleSheet(U.qss(c))
        self.tb.theme_btn.setText("☀" if self.theme == "dark" else "☾")
        # 发光颜色跟着主题走：浅色=蓝光，深色=青光
        for b in self.findChildren(U.GlowButton):
            b.set_glow(c.get("glow", "#22d3ee"), c.get("glow_a", 215))
        self._bg = QColor(c["bg"])
        self.update()

    def toggle_theme(self):
        self.theme = "dark" if self.theme == "light" else "light"
        self._apply_theme()

    # ---------- 原生窗口行为 ----------
    def _setup_frame(self):
        self.hwnd = int(self.winId())
        try:
            v = ctypes.c_int(2)       # Win11 圆角
            dwm.DwmSetWindowAttribute(wintypes.HWND(self.hwnd),
                                      ctypes.c_uint(DWMWA_WINDOW_CORNER_PREFERENCE),
                                      ctypes.byref(v), ctypes.sizeof(v))
        except Exception:
            pass
        self._dpr = float(self.devicePixelRatioF() or 1.0)

    def _nodrag_rects(self):
        out = []
        for w in self._nodrag:
            try:
                if w is None:
                    continue
                p = w.mapToGlobal(w.rect().topLeft())
                out.append((int(p.x() * self._dpr), int(p.y() * self._dpr),
                            int((p.x() + w.width()) * self._dpr),
                            int((p.y() + w.height()) * self._dpr)))
            except Exception:
                pass
        return out

    def nativeEvent(self, eventType, message):
        try:
            return self._native(eventType, message)
        except Exception:
            return super().nativeEvent(eventType, message)

    def _native(self, eventType, message):
        if eventType in (b"windows_generic_MSG", b"windows_dispatcher_MSG"):
            msg = wintypes.MSG.from_address(int(message))
            if msg.message == WM_NCCALCSIZE and msg.wParam:
                if u32.IsZoomed(wintypes.HWND(self.hwnd)):
                    p = ctypes.cast(msg.lParam, ctypes.POINTER(NCCALCSIZE_PARAMS)).contents
                    mi = MONITORINFO()
                    mi.cbSize = ctypes.sizeof(MONITORINFO)
                    u32.GetMonitorInfoW(
                        u32.MonitorFromWindow(wintypes.HWND(self.hwnd), 2), ctypes.byref(mi))
                    p.rgrc[0] = mi.rcWork
                return True, 0
            if msg.message == WM_ENTERSIZEMOVE:
                # 开始拖动/缩放：关掉所有发光特效（否则会留残影）
                for b in self.findChildren(U.GlowButton):
                    b.set_glow_enabled(False)
            elif msg.message == WM_EXITSIZEMOVE:
                for b in self.findChildren(U.GlowButton):
                    b.set_glow_enabled(True)
                self.update()
            if msg.message == WM_NCHITTEST:
                x = ctypes.c_short(msg.lParam & 0xFFFF).value
                y = ctypes.c_short((msg.lParam >> 16) & 0xFFFF).value
                r = wintypes.RECT()
                u32.GetWindowRect(wintypes.HWND(self.hwnd), ctypes.byref(r))
                b = RESIZE_B
                L, R = x < r.left + b, x >= r.right - b
                T, B = y < r.top + b, y >= r.bottom - b
                if T and L:
                    return True, HTTOPLEFT
                if T and R:
                    return True, HTTOPRIGHT
                if B and L:
                    return True, HTBOTTOMLEFT
                if B and R:
                    return True, HTBOTTOMRIGHT
                if L:
                    return True, HTLEFT
                if R:
                    return True, HTRIGHT
                if T:
                    return True, HTTOP
                if B:
                    return True, HTBOTTOM
                if y < r.top + int(TITLE_H * self._dpr):
                    for x0, y0, x1, y1 in self._nodrag_rects():
                        if x0 <= x <= x1 and y0 <= y <= y1:
                            return True, HTCLIENT
                    return True, HTCAPTION
        return super().nativeEvent(eventType, message)

    # ---------- 与主程序的生命周期联动 ----------
    def watch_parent(self, pid, every_ms=3000):
        """盯着主程序进程：它没了就自己退出（避免留个连不上的孤儿窗口）。"""
        import ctypes as _ct
        k32 = _ct.windll.kernel32

        def alive():
            try:
                h = k32.OpenProcess(0x00100000, False, int(pid))   # SYNCHRONIZE
                if not h:
                    return False
                k32.CloseHandle(h)
                return True
            except Exception:
                return True

        t = QTimer(self)
        t.setInterval(int(every_ms))
        t.timeout.connect(lambda: (None if alive() else self.close()))
        t.start()

    def closeEvent(self, e):
        """点关闭 = 关掉整个程序（让主程序优雅退出，本窗口随后一起没）。"""
        if getattr(self, "_closing", False):
            return super().closeEvent(e)
        self._closing = True
        try:
            self.api.desktop_action("quit")
        except Exception:
            pass
        super().closeEvent(e)

    # ---------- 防残影 ----------
    def paintEvent(self, e):
        """自己把背景填满：无边框窗口如果背景"不是完全不透明"，拖动时容易留残影。"""
        try:
            p = QPainter(self)
            p.fillRect(self.rect(), getattr(self, "_bg", QColor("#eef2f8")))
        except Exception:
            pass

    # ---------- 数据 ----------
    def _start_poll(self):
        self.p_status = Poll(self.api.desktop_state, 2500, self)
        self.p_status.got.connect(self.on_status)
        self.p_status.start()
        # 状态条（ERP 登录 / 手机端 / 开放平台）：20 秒刷一次就够，别太频繁
        # ★ 8 秒轮询一次（原来 20 秒）：刚在浏览器里登录完 ERP，用户希望马上看到
        #   「ERP 已登录」。服务端那边结果缓存也同步调短了（60→25 秒）。
        self.p_chips = Poll(self._poll_chips, 8000, self)
        self.p_chips.start()
        self.p_scans = Poll(lambda: self.api.scans(300), 5000, self)
        self.p_scans.got.connect(self.on_scans)
        self.p_scans.start()
        self.p_wave = Poll(self.api.wave_records, 15000, self)
        self.p_wave.got.connect(self.on_waves)
        self.p_wave.start()
        # 扫码浮窗：盯最新一条扫码记录，出现新的就弹个大字浮窗
        self._last_scan = None
        self.p_float = Poll(lambda: self.api.scans(1), 2000, self)
        self.p_float.got.connect(self.on_scan_float)
        self.p_float.start()

    def _set_hint(self, txt, bad=False):
        try:
            self.hint.setText(txt)
            self.hint.setStyleSheet("color:%s; font-size:12px;"
                                    % (("#dc2626" if bad else "#059669") if self.theme == "light"
                                       else ("#fb7185" if bad else "#34d399")))
        except Exception:
            pass

    def on_status(self, j):
        if not isinstance(j, dict):
            return
        if j.get("offline") or j.get("error"):
            self._set_hint("本机服务未响应（%s）" % (j.get("error") or "无响应"), True)
            self.st_left.setText("未连接")
            return
        self._set_hint("已连接主程序 %s · 订单库 %s · 编码 %s"
                       % (j.get("ver") or "", j.get("orders", "-"), j.get("codes", "-")))
        busy = j.get("syncing") or j.get("shelf_busy")
        txt = str(j.get("text") or "")
        # 状态栏直接显示主程序那一行真实状态（"正在增量刷新…" 这类都能看到）
        self.st_left.setText(("⏳ " if busy else "") + (txt or "就绪"))
        self.st_right.setText("上次刷新 %s   ·   货位 %s"
                              % (j.get("loaded_at") or "-", j.get("shelf_at") or "-"))
        # 开关勾选状态跟着主程序走（在别处改了也能同步过来）
        opts = j.get("opts") or {}
        for key, act in (self._TOGGLE_ACTS or {}).items():
            try:
                act.blockSignals(True)
                act.setChecked(bool(opts.get(key)))
                act.blockSignals(False)
            except Exception:
                pass

    # ---------- 写操作 ----------
    def _say(self, title, text, kind="info"):
        box = {"info": QMessageBox.information, "warn": QMessageBox.warning,
               "error": QMessageBox.critical}.get(kind, QMessageBox.information)
        box(self, title, text)

    def _ask(self, title, text):
        return QMessageBox.question(self, title, text,
                                    QMessageBox.Yes | QMessageBox.No,
                                    QMessageBox.No) == QMessageBox.Yes

    def do_refresh(self, what):
        names = {"inc": "增量刷新", "full": "全量重拉",
                 "shelf": "刷新货位库存", "lock": "刷新锁定数"}
        nm = names.get(what, what)
        if what == "full" and not self._ask(
                "全量重拉", "全量重拉会重新拉取所有待发货订单，**耗时约 20 分钟**。\n"
                            "期间扫码查询可能变慢。\n\n确定现在开始吗？"):
            return
        self.st_left.setText("%s：已下发给主程序…" % nm)
        self.statusBar_hint("%s：已下发…" % nm)

        def work():
            r = self.api.desktop_refresh(what)
            self._disp.post(lambda: self._after(nm, r))

        threading.Thread(target=work, daemon=True).start()

    def _after(self, nm, r):
        if isinstance(r, dict) and r.get("ok"):
            self.st_left.setText("%s：已开始（进度看这里）" % nm)
            self.statusBar_hint("%s：已下发给主程序" % nm)
        else:
            msg = (r or {}).get("error") or "未知错误"
            self.st_left.setText("%s 失败：%s" % (nm, msg))
            self.statusBar_hint("%s 失败：%s" % (nm, msg))
            self._say("操作失败", msg, "error")

    def do_clearlog(self):
        if not self._ask("清空扫码日志",
                         "确定清空**全部扫码日志**吗？\n\n此操作不可撤销，建议先导出 Excel 备份。"):
            return
        self.st_left.setText("正在清空扫码日志…")

        def work():
            r = self.api.desktop_clearlog()
            self._disp.post(lambda: self._after("清空扫码日志", r))

        threading.Thread(target=work, daemon=True).start()

    # 主程序侧动作 → 点完给用户的即时反馈文案。
    # ★ 为什么要有：像「按条件筛选」这种动作，主程序的活是在**它自己的状态栏**显示一句
    #   「已按条件筛选：…」，而电脑版这边只弹一个 Qt 主窗、Tk 状态栏根本看不见 →
    #   点下去屏幕上什么都没变，用户就以为"没反应"（实测就是这么被反馈的）。
    #   所以这里按动作回一句明确的话，让用户立刻知道成功了。
    _ACT_DONE = {
        "apply_filter": "已按条件筛选（详细结果见主程序状态栏那一行）",
        "check_update": "已检查更新（有新版本会弹窗）",
        "erp_login": "已打开「登录 ERP」窗口",
        "admin": "已打开「子客户端管理」窗口",
        "print_clients": "已打开「打印分工」窗口",
        "gateway": "已打开「对外访问设置」窗口",
        "api_settings": "已打开「API 设置」窗口",
        "stock": "已打开「现货可发」窗口",
        "adjust_log": "已打开「改库存日志」窗口",
        "batch": "已打开「批次查询」窗口",
        "stocktake": "已打开「库存盘点」窗口",
        "print_progress": "已打开「打单进度」窗口",
        "open_dir": "已在主程序那台机器上打开数据目录",
        "open_db": "已在主程序那台机器上定位数据文件",
        "pick_file": "已打开「读导出文件」窗口",
    }

    def do_action(self, name):
        """调主程序侧动作（大多是打开原来的设置窗，窗口会弹在这台机器上）。"""
        self.st_left.setText("正在打开…")

        def work():
            r = self.api.desktop_action(name)
            self._disp.post(lambda: self._after_action(name, r))

        threading.Thread(target=work, daemon=True).start()

    def _after_action(self, name, r):
        """动作反馈：不管成功还是失败，都要有明确的可见提示。

        注意：主程序侧很多动作会**提前 return**（比如「按条件筛选」在订单库为空时
        只在自己的状态栏写一句提示就返回），接口照样回 ok=True。所以这里不能再
        靠"返回了 ok 就当成功"来决定要不要给反馈 —— 一律给。
        """
        if not isinstance(r, dict) or r.get("error"):
            self._after("打开设置", r)
            # 失败也要留痕（_after 里已经记了一次，这里不重复）
            return
        done = self._ACT_DONE.get(str(name)) or "已完成"
        self.st_left.setText(done)
        self.statusBar_hint(done)

    def statusBar_hint(self, text):
        """把结果既记到「最近操作」行，又用醒目的横幅弹一下（6 秒后自动收起）。"""
        try:
            self._hint = ([str(text)] + getattr(self, "_hint", []))[:3]
            lbl = getattr(self, "lbl_hint", None)
            if lbl is not None:
                lbl.setText("最近操作：" + "　·　".join(self._hint))
            b = getattr(self, "banner", None)
            if b is not None:
                b.setText(str(text))
                b.setVisible(True)
                old = getattr(self, "_banner_timer", None)
                if old is not None:
                    try:
                        old.stop()
                    except Exception:
                        pass
                t = QTimer(self)
                t.setSingleShot(True)

                def _hide():
                    try:
                        b.setVisible(False)
                    except Exception:
                        pass

                t.timeout.connect(_hide)
                t.start(6000)
                self._banner_timer = t
        except Exception:
            pass

    def do_opt(self, key):
        def work():
            r = self.api.desktop_opt(key)
            self._disp.post(lambda: self._after("切换开关", r))

        threading.Thread(target=work, daemon=True).start()

    def do_hold(self):
        from PySide6.QtWidgets import QInputDialog
        cur = getattr(self, "_hold", 30)
        v, ok = QInputDialog.getInt(self, "可发撤回宽限",
                                    "网页点「可发」后多少秒内可以撤回？（0～600）",
                                    int(cur or 30), 0, 600, 5)
        if not ok:
            return
        self.st_left.setText("正在保存宽限…")

        def work():
            r = self.api.desktop_opt("hold", int(v))
            self._disp.post(lambda: self._after("可发撤回宽限", r))

        threading.Thread(target=work, daemon=True).start()

    def do_api_settings(self):
        """打开 Qt 版 API 设置（旧版窗口留了入口）。"""
        try:
            d = ApiSettingsDialog(self.api, self.theme, self)
            d.exec()
        except Exception as e:
            self._say("API 设置", "打不开：%s" % str(e)[:150], "error")

    def do_table(self, name):
        """打开通用表格窗（现货可发 / 改库存日志 / …）。列和行都由主程序给。"""
        try:
            d = TableDialog(self.api, name, self.theme, self)
            self.statusBar_hint("已打开：%s" % d.windowTitle())
            d.exec()
        except Exception as e:
            self._say("表格", "打不开：%s" % str(e)[:150], "error")

    def do_stocktake(self):
        """打开「库存盘点（按款号）」（Qt 本地窗；旧版窗口里面也留了入口）。"""
        try:
            d = StocktakeDialog(self.api, self.theme, self)
            self.statusBar_hint("已打开：库存盘点（按款号）")
            d.exec()
        except Exception as e:
            self._say("盘点", "打不开：%s" % str(e)[:150], "error")

    def do_batch(self):
        """打开「批次查询」（Qt 本地窗；窗内留了「旧版窗口」入口）。"""
        try:
            d = BatchDialog(self.api, self.theme, self)
            self.statusBar_hint("已打开：批次查询")
            d.exec()
        except Exception as e:
            self._say("批次查询", "打不开：%s" % str(e)[:150], "error")

    def do_ship_stats(self):
        """打开「每日发货量（按账号）」：选日期 + 选账号。"""
        try:
            d = ShipStatsDialog(self.api, self.theme, self)
            self.statusBar_hint("已打开：每日发货量")
            d.exec()
        except Exception as e:
            self._say("每日发货量", "打不开：%s" % str(e)[:150], "error")

    def _open_dlg(self, cls, label):
        """通用的「打开一个 Qt 设置窗」封装（三个设置窗共用）。"""
        try:
            d = cls(self.api, self.theme, self)
            self.statusBar_hint("已打开：%s" % label)
            d.exec()
        except Exception as e:
            self._say(label, "打不开：%s" % str(e)[:150], "error")

    def do_print_progress(self):
        """打开 Qt 版打单进度（老版窗口留了入口，随时切回）。"""
        try:
            d = PrintProgressDialog(self.api, self.theme, self)
            d.exec()
        except Exception as e:
            self._say("打单进度", "打不开：%s" % str(e)[:150], "error")

    def do_log(self):
        self.st_left.setText("正在读日志…")

        def work():
            r = self.api.desktop_log(200)
            self._disp.post(lambda: self._show_log(r))

        threading.Thread(target=work, daemon=True).start()

    def _show_log(self, r):
        lines = (r or {}).get("lines") or []
        d = QDialog(self)
        d.setWindowTitle("打单进度 / 实时日志（%s 尾部 %d 行）"
                         % ((r or {}).get("file") or "auto_print.log", len(lines)))
        d.resize(900, 560)
        lay = QVBoxLayout(d)
        t = QTableWidget(0, 1)
        t.setHorizontalHeaderLabels(["日志"])
        t.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        t.setShowGrid(False)
        t.setRowCount(len(lines))
        for i, ln in enumerate(lines):
            it = QTableWidgetItem(str(ln))
            t.setItem(i, 0, it)
        lay.addWidget(t)
        row = QHBoxLayout()
        row.addStretch(1)
        b = U.GlowButton("刷 新")
        b.clicked.connect(lambda: (d.accept(), self.do_log()))
        row.addWidget(b)
        b2 = U.GlowButton("关 闭")
        b2.clicked.connect(d.accept)
        row.addWidget(b2)
        lay.addLayout(row)
        d.setStyleSheet(U.qss(U.LIGHT if self.theme == "light" else U.DARK))
        d.exec()

    def do_about(self):
        self._say("关于", "快麦发货查询 · 电脑版\n\n"
                          "界面：Qt（PySide6）+ mac 风格标题栏\n"
                          "数据：本机主程序 %s\n"
                          "登录账号：%s（%s）\n"
                          "权限项：%d 项\n\n"
                          "主程序版本：%s"
                  % (self.api.base, self.api.name or "-", self.api.role or "-",
                     len(self.api.perms or []), self.api.ver or "-"))

    def _open_path(self, p):
        try:
            os.startfile(p)
        except Exception as e:
            self._say("打不开", str(e)[:150], "error")

    def do_open_dir(self):
        self._open_path(os.path.dirname(os.path.abspath(__file__)))

    def do_open_db(self):
        # 数据目录在主程序那台机器上：让主程序帮我们打开（走 action 白名单里的 pick_file 不行，
        # 这里用状态里的信息拼；打不开就直接提示路径）
        self._say("数据目录", "数据库/日志都在主程序那台机器上：\n\n"
                              "%%LOCALAPPDATA%%\\KuaimaiScan\\\n\n"
                              "（这个按钮等主程序那边加了对应动作再真正打开）")

    def do_logout(self):
        if not self._ask("重新登录", "退出当前账号并重新登录？"):
            return
        try:
            self.api.logout()
        except Exception:
            pass
        d = LoginDialog(self.api, self)
        d.setStyleSheet(U.qss(U.LIGHT if self.theme == "light" else U.DARK))
        if d.exec() == QDialog.Accepted:
            self.tb.badge.setText(" " + (self.api.ver or "电脑版") + " ")
            self.st_left.setText("已重新登录：%s" % (self.api.name or "-"))

    def do_export(self):
        import time as _t
        default = os.path.join(os.path.expanduser("~"), "Desktop",
                               "扫码日志_%s.xlsx" % _t.strftime("%Y%m%d_%H%M"))
        dest, _ = QFileDialog.getSaveFileName(self, "导出扫码日志", default,
                                              "Excel 文件 (*.xlsx)")
        if not dest:
            return
        self.st_left.setText("正在导出…")

        def work():
            import urllib.parse
            ok, err = self.api.download("/api/scans/export?" + urllib.parse.urlencode(
                {"limit": 0}), dest)
            self._disp.post(lambda: self._after_export(dest, ok, err))

        threading.Thread(target=work, daemon=True).start()

    def _after_export(self, dest, ok, err):
        if ok:
            self.st_left.setText("已导出：%s" % dest)
        else:
            self.st_left.setText("导出失败：%s" % err)
            self._say("导出失败", err, "error")

    def _poll_chips(self):
        """刷新状态条：ERP 登录 / 快麦接口 / 外网访问（三条都是真检测）。"""
        def work():
            try:
                c = self.api.api_conf() or {}
                st = self.api.desktop_state() or {}
                # ERP 会话探测要连自动化浏览器 → 单独取、给足超时
                try:
                    erp = self.api.get("/api/erp/status", timeout=90)
                except Exception:
                    erp = None
                # 外网访问状态（9443 在听 / frpc 在跑 / 域名）
                try:
                    gw = self.api.gateway()
                except Exception:
                    gw = None
                self._disp.post(lambda: self._fill_chips(None, c, st, erp, gw))
            except Exception:
                pass

        threading.Thread(target=work, daemon=True).start()

    def _fill_chips(self, a, c, st, erp=None, gw=None):
        """状态条三条 —— 只显示最影响使用的真实状态：

          ① ERP：用「波次管理」只读接口探活 ERP 会话（不是程序管理员账号！）
          ② 快麦接口：开放平台 appKey/sessionId 是否已配置
          ③ 外网访问：9443 是否在听 + frpc 隧道是否在跑 + 域名是否已填
        """
        # ① ERP（★ 用快麦接口探活为主，浏览器为兜底 —— 以前只看 9222，浏览器拉起来了
        #      但端口连不上时会误报"未登录"，用户实测反馈过）
        try:
            e = erp if isinstance(erp, dict) else {}
            if not e:
                self._set_chip("erp", "ERP 状态：检测中…", "#8a8a8e")
            elif e.get("erp"):
                self._set_chip("erp", "ERP 已登录 ✓", "#1B7F35")
            else:
                self._set_chip("erp", "ERP：" + str(e.get("why") or "未登录")[:28], "#c62828")
        except Exception:
            pass
        # ② 快麦开放平台接口
        try:
            conf = ((c or {}).get("conf") or {}) if isinstance(c, dict) else {}
            ok = bool(str(conf.get("appKey") or "").strip()
                      and str(conf.get("sessionId") or "").strip())
            self._set_chip("api",
                           "快麦接口已配置 ✓" if ok else "快麦接口未配置（去「API 设置」）",
                           "#1B7F35" if ok else "#c62828")
        except Exception:
            pass
        # ③ 外网访问（手机在外面能不能连上）
        try:
            g = gw if isinstance(gw, dict) else {}
            conf = (g.get("conf") or {}) if isinstance(g, dict) else {}
            stt = (g.get("status") or {}) if isinstance(g, dict) else {}
            domain = str(conf.get("domain") or "").strip()
            https_open = bool(stt.get("https_open"))
            frpc = bool(stt.get("frpc"))
            web_open = bool(stt.get("web_open"))
            if not domain:
                self._set_chip("phone", "外网访问：还没填域名", "#b26a00")
            elif web_open and https_open and frpc:
                self._set_chip("phone", "外网访问正常 · %s" % domain, "#1B7F35")
            else:
                miss = []
                if not web_open:
                    miss.append("本机服务没开")
                if not https_open:
                    miss.append("9443 不在听")
                if not frpc:
                    miss.append("frpc 没跑")
                self._set_chip("phone", "外网访问异常：%s" % "、".join(miss), "#c62828")
        except Exception:
            pass

    def _set_chip(self, key, text, color):
        try:
            lab = (self.chips or {}).get(key)
            if lab is None:
                return
            lab.setText("● " + str(text))
            lab.setStyleSheet("color:%s;font-weight:600;" % color)
        except Exception:
            pass

    def on_scans(self, j):
        rows = (j or {}).get("rows") or (j or {}).get("list") or []
        if not isinstance(rows, list):
            return
        self.t_scan.setRowCount(len(rows))
        for r, it in enumerate(rows):
            if isinstance(it, dict):
                vals = [it.get("time", ""), it.get("code", ""), it.get("pending", ""),
                        it.get("bin", it.get("shelf", "")), it.get("who", ""),
                        it.get("canprint", it.get("print_num", "")),
                        it.get("status", it.get("ok") and "可发" or ""), it.get("printed", "")]
            else:
                vals = list(it) + [""] * 8
            for c in range(8):
                t = QTableWidgetItem(str(vals[c] if c < len(vals) else ""))
                if c in (2, 5, 7):
                    t.setTextAlignment(Qt.AlignVCenter | Qt.AlignRight)
                self.t_scan.setItem(r, c, t)

    def on_waves(self, j):
        """波次记录：一行 = 一个波次。

        ★ 修：以前按 `items` 取值（那是 /api/wave/records 里 records 的形状），
          而界面上用的是 `recent`，字段是 tradesCount / itemCount / pickEndTime /
          status_cn / who —— 结果「生成数量 / 波次状态」两列永远空着（用户看到的就是
          "还是空的"）。现在两个形状都认，状态取平台给的 status_cn。
        ★ 「实发订单数」：服务端按天把「发货」日志扫成 {sid: 打包账号} 缓存
          （见 ship_cache），这里拿波次的 sids 去对，对上的就是真发出去的单数。
          刚开界面时后台还在扫 → 显示「…」，十几秒后自己就出来了。
        """
        recs = (j or {}).get("recent") or []
        if not isinstance(recs, list):
            return
        self._waves = recs
        self._ship_cache = ship = (j or {}).get("ship_cache") or {}
        self._printed = (j or {}).get("printed") or {}
        self.t_wave.setRowCount(len(recs))

        def pick(w, *keys):
            for k in keys:
                v = w.get(k)
                if v not in (None, "", "None"):
                    return v
            return ""

        def ms_to_text(v):
            """毫秒时间戳 → '2026-10-08 15:20'（上游 pickEndTime 只给时间戳）。"""
            try:
                n = int(str(v))
                if n <= 0:
                    return ""
                if n > 10 ** 12:          # 毫秒
                    n //= 1000
                return time.strftime("%Y-%m-%d %H:%M", time.localtime(n))
            except Exception:
                return ""

        for r, w in enumerate(recs):
            items = w.get("items") or w.get("codes") or []
            first = items[0] if items else {}
            qty = first.get("qty")
            if qty in (None, ""):
                qty = first.get("actual")
            if qty in (None, ""):
                qty = w.get("itemCount", "")
            # 状态：平台的 status_cn（已完成/未完成/等待验货/已取消）
            st = str(pick(w, "status_cn", "status_text") or "")
            if not st:
                stt = w.get("status")
                st = "" if stt in (None, "", 0, "0") else str(stt)
            who = w.get("who") or "（非本系统）"
            ts = w.get("ts") or w.get("pickEndTime") or w.get("created_ms") or ""
            # 验货人/拣货人：网页端给的 pickerName（没有就退到指派的人）
            checker = str(w.get("picker") or w.get("assign_picker") or "").strip()
            if not checker:
                checker = str(w.get("sorter") or "").strip()
            # 列：波次号 / 生成时间 / 拣货人 / 件数 / 生成账号 / 拣货数量 / 实发订单数 / 波次状态
            picked = w.get("picked_num")
            plan = w.get("plan_num")
            pick_txt = ""
            if picked not in (None, ""):
                pick_txt = str(picked)
                if plan not in (None, "", picked):
                    pick_txt = "%s / %s" % (picked, plan)
            # 「实发/订单」= 该波次**已打印的订单数 / 订单总数**
            # ★ 数据来自服务端的 printed 映射（走 ERP「波次管理→点波次号」那个接口读 printTimes），
            #   已完成/未完成都能算。这里以前还在用旧的「当日发货日志 + sids」逻辑，
            #   结果那一列永远出不来数字（用户反馈"只能看到…"）。现在统一走 _ship_cell_text。
            ship_txt = self._ship_cell_text(w) or "—"
            ship_tip = ""
            _pr = (getattr(self, "_printed", {}) or {}).get(str(w.get("wave_code") or "")) or {}
            if not _pr:
                ship_tip = "还没读到这个波次的订单（点一下顶上的「刷 新」或稍等几秒）"
            elif _pr.get("n") is None:
                ship_tip = "这个波次的订单暂时读不到（浏览器未就绪或 ERP 未登录）"
            else:
                ship_tip = ("已打印 %s 单 / 订单共 %s 单" % (_pr.get("n"), _pr.get("total") or "?"))
            vals = [w.get("wave_code", "-"), ms_to_text(ts) or str(ts or ""),
                    checker or "—", qty, who, pick_txt, ship_txt, st]
            for c in range(8):
                t = QTableWidgetItem(str(vals[c]))
                if c in (3, 5, 6):
                    t.setTextAlignment(Qt.AlignVCenter | Qt.AlignRight)
                # ★ 每格挂 tooltip：列宽再合适，也可能有超长内容，鼠标停一下就看得全
                if c == 6 and ship_tip:
                    t.setToolTip(ship_tip)
                elif str(vals[c]).strip():
                    t.setToolTip(str(vals[c]))
                self.t_wave.setItem(r, c, t)
            # 状态着色：等待验货=橙，未完成=红，其它/已完成=绿
            try:
                if st:
                    color = ("#b26a00" if "验货" in st else
                             "#c62828" if "未完成" in st else
                             "#1B7F35" if any(x in st for x in ("完成", "已发", "结束")) else "")
                    if color:
                        self.t_wave.item(r, 7).setForeground(QColor(color))
            except Exception:
                pass
        try:
            import collections
            cnt = collections.Counter(
                (str(w.get("status_cn") or "") or "（平台没给状态）") for w in recs)
            dist = "　".join("%s %d" % (k, v) for k, v in cnt.most_common())
            raws = collections.Counter(str(w.get("status")) for w in recs)
            src = str((j or {}).get("src") or "")
            src_txt = {"web": "数据源：ERP 网页波次管理（含已完成/已取消）",
                       "api": "数据源：开放平台接口（只给未完成的）",
                       "" : "数据源：无（读不到实时状态）"}.get(src, src)
            err = str((j or {}).get("error") or "")
            self.lbl_wave_info.setText(
                "共 %d 个波次　·　%s　·　原始 status：%s　·　%s%s\n"
                "点某一行看明细。状态口径：1=未完成/等待验货、3=已完成、4=已取消"
                % (len(recs), src_txt,
                   "　".join("%s×%d" % (k, v) for k, v in raws.most_common()),
                   dist, ("　·　" + err[:80]) if err else ""))
        except Exception:
            pass

    def on_scan_float(self, j):
        """最新一条扫码记录有变化 → 弹浮窗（无边框、置顶、几秒后自动消失）。"""
        rows = (j or {}).get("rows") or (j or {}).get("list") or []
        if not rows or not isinstance(rows[0], dict):
            return
        r = rows[0]
        key = (str(r.get("time") or ""), str(r.get("code") or ""))
        if not key[1] or key == self._last_scan:
            return
        first = self._last_scan is None        # 第一次只记基准，不弹
        self._last_scan = key
        if first:
            return
        try:
            FloatCard.show_on(self, r, self.theme)
        except Exception:
            pass

    def _ship_cell_text(self, it):
        """「实发/订单」= 该波次**已打印订单数 / 属于本波次的订单数**。

        口径（用户确认）：点进波次看到 180 个订单、179 个已打印 → 实发 179。
        数据来源：主程序走 ERP「波次管理 → 点波次号」那个接口
                  （/trade/wave/trade/list/log）读每单 printTimes，
                  并且**只统计订单自带 waveId == 本波次号**的单 ——
                  不过滤会把「已重新分配到别的波次」的单也算进来（含已取消波次，
                  用户抓到过）。

        ★ 这里**只用** printed 映射，不再退回旧的「当日发货日志」兜底：
          那个兜底在数据没到时会吐出一个不可信的数字（用户看到过跟商品种类一样的 9）。
          没数据就老实显示「…」或「—」。
        """
        code = str(it.get("wave_code") or it.get("code") or "")
        rec = (getattr(self, "_printed", {}) or {}).get(code)
        if not isinstance(rec, dict):
            return "…"                      # 还没抓到：显示读取中（后台马上补）
        n, total = rec.get("n"), rec.get("total")
        if n is None:
            return "—"                      # 抓了但读不到（浏览器/ERP 未就绪）
        if total:
            return "%s / %s" % (n, total)
        return str(n)

    def on_wave_click(self, row, col):
        """点波次行：先把明细写到底部详情行（一定看得见），编码多再补一个弹窗。"""
        w = (getattr(self, "_waves", []) or [])
        if row >= len(w):
            return
        it = w[row]
        items = it.get("items") or it.get("codes") or []
        st = str(it.get("status_cn") or it.get("status_text") or "")
        if not st:
            s = it.get("status")
            st = "" if s in (None, "", "0", 0) else str(s)
        bits = ["波次 %s" % it.get("wave_code", "-"),
                "状态 %s" % (st or "（平台没给）"),
                "拣货人 %s" % (str(it.get("picker") or it.get("assign_picker") or "—")),
                "件数 %s" % it.get("itemCount", ""),
                "拣货数量 %s" % (it.get("picked_num") if it.get("picked_num") not in (None, "")
                                 else "—"),
                "实发订单数 %s" % (self._ship_cell_text(it) or "—"),
                "单数 %s" % it.get("tradesCount", ""),
                "生成时间 %s" % (it.get("ts") or "-"),
                "生成账号 %s" % (it.get("who") or "（非本系统）")]
        for label, key in (("ERP 创建人", "creator"), ("分拣人", "sorter")):
            v = str(it.get(key) or "").strip()
            if v:
                bits.append("%s %s" % (label, v))
        pe = it.get("pickEndTime")
        if pe not in (None, "", "None"):
            try:
                n = int(str(pe))
                if n > 10 ** 12:
                    n //= 1000
                pe = time.strftime("%Y-%m-%d %H:%M", time.localtime(n))
            except Exception:
                pass
            bits.append("拣货结束 %s" % pe)
        try:
            self.lbl_wave_info.setText("　·　".join(str(b) for b in bits))
        except Exception:
            pass
        if len(items) < 2:
            return
        box = "\n".join("  %-22s %3s 件   %s" % (x.get("code", ""),
                                                 x.get("qty", x.get("actual", "")),
                                                 x.get("bin", "")) for x in items)
        from PySide6.QtWidgets import QMessageBox
        QMessageBox.information(self, "波次 %s 的全部编码（%d 个）"
                                % (it.get("wave_code", ""), len(items)), box)

    def do_lookup(self):
        code = (self.ent.text() or "").strip()
        if not code:
            return
        self.btn_q.setEnabled(False)
        self.res_code.setText("查询中…")
        self.res_sub.setText(code)

        def work():
            r = self.api.lookup(code)
            self._disp.post(lambda: self._show_lookup(code, r))

        threading.Thread(target=work, daemon=True).start()

    def _show_lookup(self, code, r):
        self.btn_q.setEnabled(True)
        try:
            self.t_res.setRowCount(0)
            self.t_res.setVisible(False)
        except Exception:
            pass
        if not isinstance(r, dict) or r.get("error"):
            self.res_code.setText(code)
            self.res_sub.setText((r or {}).get("error") or "查询失败")
            return
        # ★ 查款号（如 7107）返回的是「系列」：{series:true, items:[每个规格...]}
        #   单查一个编码返回的是平铺字段。两种都要显示（旧版两种都显示）。
        items = r.get("items") or []
        if r.get("series") or (items and not r.get("orders")):
            self.res_code.setText("%s（系列 %d 个规格）"
                                  % (r.get("code") or code, len(items)))
            pend = sum(int(i.get("qty", 0) or 0) for i in items)
            shl = sum(int(i.get("shelf", 0) or 0) for i in items)
            self.res_sub.setText("在架合计 %s　·　待发货合计 %s　·　%s"
                                 % (shl, pend, "在架够 ✓" if shl >= pend else "在架不足 ✗"))
            self.t_res.setVisible(True)
            self.t_res.setRowCount(len(items))
            for row, it in enumerate(items):
                vals = [it.get("code", ""), it.get("bins", ""),
                        it.get("shelf", ""), it.get("qty", ""),
                        it.get("lock", ""), it.get("orders", "")]
                for c, v in enumerate(vals):
                    self.t_res.setItem(row, c, QTableWidgetItem(
                        "" if v is None else str(v)))
            return
        self.res_code.setText(str(r.get("code") or code))
        bits = []
        for k, label in (("canprint", "可发"), ("orders", "订单"), ("pieces", "件数"),
                         ("pending", "待发货"), ("shelf", "在架"),
                         ("lock", "锁定"), ("sellable", "可售"), ("avail", "可用")):
            if r.get(k) not in (None, ""):
                bits.append("%s %s" % (label, r.get(k)))
        # 货位可能是 bins=[[货位, 数量],...]
        bins = r.get("bins") or []
        if bins:
            try:
                bits.append("货位 " + "、".join(
                    "%s%s" % (b[0], ("(%s)" % b[1]) if len(b) > 1 else "")
                    for b in bins[:6]))
            except Exception:
                pass
        elif r.get("bin"):
            bits.append("货位 %s" % r.get("bin"))
        self.res_sub.setText("　·　".join(bits) or "（接口返回里没有可显示的字段）")
        # 单一编码也放进结果表，信息更全
        if bits:
            self.t_res.setVisible(True)
            self.t_res.setRowCount(1)
            for c, v in enumerate([r.get("code") or code,
                                   (bins[0][0] if bins else (r.get("bin") or "")),
                                   r.get("shelf", ""),
                                   r.get("pending", r.get("pieces", "")),
                                   r.get("lock", ""), r.get("orders", "")]):
                self.t_res.setItem(0, c, QTableWidgetItem("" if v is None else str(v)))


class CheckUpdateDialog(QDialog):
    """检查更新（登录页和主界面共用）。

    直接调 kuaimai_update.check()：它会同时问多个源（jsDelivr / raw / GitHub API）
    取版本号最高的那个，避免某个 CDN 缓存导致误报「已是最新版」。
    登录页也要能点 —— 更新跟登录没关系，没登录也该能检查。
    """

    def __init__(self, api, theme="light", parent=None, current=""):
        super().__init__(parent)
        self.api = api
        self._disp = Dispatcher(self)
        self._info = {}
        self.setWindowTitle("检查更新")
        self.resize(620, 460)
        self.setStyleSheet(U.qss(U.LIGHT if theme == "light" else U.DARK))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(16, 14, 16, 12)
        lay.setSpacing(8)

        self.lbl_cur = QLabel("当前版本：%s" % (current or "?"))
        self.lbl_cur.setObjectName("sect")
        lay.addWidget(self.lbl_cur)
        self.lbl_st = QLabel("正在检查更新…")
        self.lbl_st.setObjectName("hint")
        self.lbl_st.setWordWrap(True)
        lay.addWidget(self.lbl_st)

        self.txt = QPlainTextEdit()
        self.txt.setReadOnly(True)
        self.txt.setPlaceholderText("有新版本时，这里显示更新说明")
        lay.addWidget(self.txt, 1)

        row = QHBoxLayout()
        self.lbl_msg = QLabel("")
        self.lbl_msg.setObjectName("hint")
        row.addWidget(self.lbl_msg)
        row.addStretch(1)
        self.b_dl = U.GlowButton("下载并安装", primary=True)
        self.b_dl.setToolTip("下载安装包并运行安装程序")
        self.b_dl.clicked.connect(lambda *a: self.do_download())
        self.b_dl.setVisible(False)
        row.addWidget(self.b_dl)
        self.b_page = U.GlowButton("打开下载页")
        self.b_page.clicked.connect(lambda *a: self.open_page())
        self.b_page.setVisible(False)
        row.addWidget(self.b_page)
        b_again = U.GlowButton("重新检查")
        b_again.clicked.connect(lambda *a: self.check())
        row.addWidget(b_again)
        b_cl = U.GlowButton("关 闭")
        b_cl.clicked.connect(self.accept)
        row.addWidget(b_cl)
        lay.addLayout(row)
        QTimer.singleShot(150, self.check)

    def check(self):
        self.lbl_st.setText("正在检查更新…")
        self.txt.setPlainText("")
        self.b_dl.setVisible(False)
        self.b_page.setVisible(False)
        self._info = {}

        def work():
            info = {"ok": False, "error": "缺少 kuaimai_update 模块"}
            try:
                import kuaimai_update as upd
                info = upd.check(self.lbl_cur.text().replace("当前版本：", "").strip())
            except Exception as e:
                info = {"ok": False, "error": str(e)[:180]}
            self._disp.post(lambda: self.fill(info))

        threading.Thread(target=work, daemon=True).start()

    def fill(self, info):
        self._info = info or {}
        if not self._info.get("ok"):
            self.lbl_st.setText("检查失败：%s" % str(self._info.get("error") or "未知原因")[:160])
            self.lbl_st.setStyleSheet("color:#c62828;")
            self.lbl_msg.setText("（可能没网，或 GitHub 访问不了）")
            return
        latest = str(self._info.get("latest") or "")
        if not self._info.get("has_update"):
            self.lbl_st.setText("已是最新版 ✓")
            self.lbl_st.setStyleSheet("color:#1B7F35;")
            self.txt.setPlainText("当前已经是最新版，不用更新。")
            return
        self.lbl_st.setText("发现新版本：%s" % latest)
        self.lbl_st.setStyleSheet("color:#0b5394;")
        self.txt.setPlainText(str(self._info.get("notes") or "（这次没有写更新说明）"))
        self.b_dl.setVisible(bool(self._info.get("setup_url")))
        self.b_page.setVisible(True)

    def open_page(self):
        url = str(self._info.get("page_url") or
                  "https://github.com/369431/kuaimai-fahuo-chaxun/releases/latest")
        try:
            os.startfile(url)
        except Exception:
            try:
                import subprocess
                subprocess.Popen(["cmd", "/c", "start", "", url])
            except Exception as e:
                QMessageBox.warning(self, "打开失败", str(e)[:200])

    def do_download(self):
        self.lbl_msg.setText("正在下载安装包…")

        def work():
            path, err = "", ""
            try:
                import kuaimai_update as upd

                def prog(done, total, pct):
                    self._disp.post(lambda: self.lbl_msg.setText(
                        "正在下载…%s" % (("%.0f%%（%.1f/%.1f MB）"
                                          % (pct, done / 1048576.0, total / 1048576.0))
                                         if total else "%.1f MB" % (done / 1048576.0))))

                path, err = upd.download_setup(self._info, progress=prog)
            except Exception as e:
                path, err = "", str(e)[:150]
            if path:
                self._disp.post(lambda: self._launch(path))
            else:
                self._disp.post(lambda: self.lbl_msg.setText(
                    "下载失败：%s（可点「打开下载页」手动下载）" % str(err)[:130]))

        threading.Thread(target=work, daemon=True).start()

    def _launch(self, path):
        self.lbl_msg.setText("下载完成，正在启动安装程序…")
        try:
            os.startfile(str(path))
        except Exception as e:
            QMessageBox.warning(self, "启动安装失败", "%s\n\n文件在：%s" % (str(e)[:160], path))


class TableDialog(QDialog):
    """通用表格窗：列和行全由主程序 /api/desktop/table 给（现货可发 / 改库存日志 / 库存盘点）。

    ★ 这个类是 v1.83 漏掉的：window.py 里 do_table() 一直在调 TableDialog，
      但从来没有定义过它（也没 import）→ 点「现货可发 / 改库存日志」直接
      NameError，被 except 抓住弹「打不开：name 'TableDialog' is not defined」。
      用户看现象就是「这几个功能没办法使用」。所以这里把它补齐。

    特性：
      · 数据在后台线程拉，回来走 Dispatcher 回主线程刷表（不卡界面）
      · 列/行/说明全部来自主程序，形状无关（接口自己推列）
      · 「打开旧版窗口」：调同一个动作让主程序弹老的 Tk 设置窗 —— 保证零功能损失
    """

    def __init__(self, api, name, theme="light", parent=None, kw=""):
        super().__init__(parent)
        self.api = api
        self.name = str(name)
        self.kw = str(kw or "")
        self._disp = Dispatcher(self)
        self.setStyleSheet(U.qss(U.LIGHT if theme == "light" else U.DARK))
        self.resize(1040, 660)

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)

        head = QHBoxLayout()
        self.lbl = QLabel("正在读取…")
        self.lbl.setObjectName("sect")
        head.addWidget(self.lbl)
        head.addStretch(1)
        self.lbl_kw = QLabel("")
        self.lbl_kw.setObjectName("hint")
        head.addWidget(self.lbl_kw)
        lay.addLayout(head)

        self.note = QLabel("")
        self.note.setObjectName("hint")
        self.note.setWordWrap(True)
        self.note.setVisible(False)
        lay.addWidget(self.note)

        self.t = QTableWidget(0, 0)
        self.t.setShowGrid(False)
        self.t.setSelectionBehavior(QTableWidget.SelectRows)
        self.t.setEditTriggers(QTableWidget.NoEditTriggers)
        self.t.verticalHeader().setVisible(False)
        self.t.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.t.horizontalHeader().setSectionResizeMode(QHeaderView.Interactive)
        lay.addWidget(self.t, 1)

        row = QHBoxLayout()
        self.status = QLabel("")
        self.status.setObjectName("hint")
        row.addWidget(self.status)
        row.addStretch(1)
        b_old = U.GlowButton("打开旧版窗口")
        b_old.clicked.connect(lambda *a: self.api.desktop_action(self.name))
        row.addWidget(b_old)
        b_re = U.GlowButton("刷 新")
        b_re.clicked.connect(lambda *a: self.reload())
        row.addWidget(b_re)
        b_cl = U.GlowButton("关 闭", primary=True)
        b_cl.clicked.connect(self.accept)
        row.addWidget(b_cl)
        lay.addLayout(row)

        self.reload()

    def reload(self):
        self.status.setText("正在读取…")
        self._seq = int(getattr(self, "_seq", 0)) + 1
        seq = self._seq
        path, params, to = self._request()      # 子类决定查什么数据源

        def work():
            try:
                import urllib.parse
                r = self.api.get(path + "?" + urllib.parse.urlencode(params), timeout=to)
            except Exception as e:
                r = {"error": str(e)[:150]}
            # ★ 只认最后一次请求的结果：连续点「查询」时，先发的慢响应不能把后发的盖掉
            if seq == self._seq:
                self._disp.post(lambda: self.fill(r))

        threading.Thread(target=work, daemon=True).start()

    def _request(self):
        """返回 (path, params, timeout)。子类覆盖它就换了数据源。"""
        if self.name == "stocktake":
            return ("/api/desktop/table",
                    {"name": "stocktake", "kw": getattr(self, "kw", "")}, 90)
        return ("/api/desktop/table", {"name": self.name}, 90)

    def fill(self, r):
        r = r if isinstance(r, dict) else {}
        if r.get("error"):
            msg = str(r.get("error"))
            if r.get("login") or r.get("offline"):
                msg = "服务未响应或登录已失效：%s" % msg
            self.status.setText("读取失败：%s" % msg)
            self.t.setRowCount(0)
            self.t.setColumnCount(0)
            return
        cols = [str(c) for c in (r.get("columns") or [])]
        rows = r.get("rows") or []
        title = str(r.get("title") or self.name)
        self.setWindowTitle(title)
        self.lbl.setText(title)
        if self.kw:
            self.lbl_kw.setText("款号：%s" % self.kw)
        note = str(r.get("note") or "")
        self.note.setText(note)
        self.note.setVisible(bool(note))
        if not cols:
            self.t.setRowCount(0)
            self.t.setColumnCount(0)
            self.status.setText("没有数据（共 0 行）" + ("　·　" + note if note else ""))
            return
        self.t.setColumnCount(len(cols))
        self.t.setHorizontalHeaderLabels(cols)
        self.t.setRowCount(len(rows))
        for i, row in enumerate(rows):
            for j in range(len(cols)):
                v = row[j] if j < len(row) else ""
                self.t.setItem(i, j, QTableWidgetItem("" if v is None else str(v)))
        self.t.resizeColumnsToContents()
        total = int(r.get("count") or len(rows))
        shown = int(r.get("shown") or len(rows))
        self.status.setText("共 %d 行" % total if shown >= total
                            else "共 %d 行（表格显示前 %d 行）" % (total, shown))


class StocktakeDialog(TableDialog):
    """库存盘点（按款号）：在通用表格窗上加一个「款号」输入框 + 查询按钮。

    和网页版 /stocktake 同口径：一个货位一行（款号 / 编码 / 货位 / 在架数 / 待发货件数），
    按尺码 S<M<L<XL<2XL 排序。改库存/盘0 仍然在网页版或「现货可发」里做。
    """

    def __init__(self, api, theme="light", parent=None, kw=""):
        super().__init__(api, "stocktake", theme, parent, kw=kw)
        self.setWindowTitle("库存盘点（按款号）")
        box = QHBoxLayout()
        lb = QLabel("款号")
        box.addWidget(lb)
        self.ent = QLineEdit(self.kw)
        self.ent.setPlaceholderText("输入款号，如 7107，回车查询")
        self.ent.setMinimumHeight(34)
        self.ent.returnPressed.connect(lambda *a: self.requery())
        box.addWidget(self.ent, 1)
        b = U.GlowButton("查 询", primary=True)
        b.clicked.connect(lambda *a: self.requery())
        box.addWidget(b)
        # 插到标题行下面（索引 1）
        self.layout().insertLayout(1, box)

    def requery(self):
        self.kw = (self.ent.text() or "").strip()
        self.lbl_kw.setText(("款号：%s" % self.kw) if self.kw else "")
        self.reload()


class BatchDialog(TableDialog):
    """批次查询（按打印批次号）：新版的通用表格窗 + 批次号输入 + 天数。

    以前这个菜单只能让主程序弹**旧 Tk 窗**，现在电脑版有自己的窗，外观一致。
    数据来源：/api/desktop/table?name=batch&kw=<批次号>&days=<天数>
    """

    def __init__(self, api, theme="light", parent=None, kw="", days=3):
        # ★ 必须在 super().__init__ 之前把 kw/days 准备好：
        #   TableDialog.__init__ 结尾就会调 self.reload()，而 reload 要读这两个值。
        #   之前放在 super 之后 → 一点菜单就 AttributeError（打不开）。
        self.kw = str(kw or "")
        self.days = int(days or 3)
        self._ship_mode = False
        super().__init__(api, "batch", theme, parent, kw=self.kw)
        self.setWindowTitle("批次查询（按打印批次号）")
        box = QHBoxLayout()
        lb = QLabel("打印批次号")
        box.addWidget(lb)
        self.ent = QLineEdit(str(kw or ""))
        self.ent.setPlaceholderText("输入批次号，回车查询")
        self.ent.setMinimumHeight(34)
        self.ent.returnPressed.connect(lambda *a: self.requery())
        box.addWidget(self.ent, 1)
        box.addWidget(QLabel("查最近"))
        self.sp = QComboBox()
        for d in (1, 3, 7, 14, 30, 60, 90):
            self.sp.addItem("%d 天" % d, d)
        try:
            self.sp.setCurrentIndex(max(0, [1, 3, 7, 14, 30, 60, 90].index(self.days)))
        except Exception:
            self.sp.setCurrentIndex(1)
        box.addWidget(self.sp)
        b = U.GlowButton("查 询", primary=True)
        b.clicked.connect(lambda *a: self.requery())
        box.addWidget(b)
        # ★ 「发货明细」：打包账号（验货人）+ 实际发货数量。
        #   单独一个按钮是因为要翻很多页日志（一个批次上千条），别拖慢普通查询。
        self.b_ship = U.GlowButton("发货明细（谁打包/实发几件）")
        self.b_ship.setToolTip("读操作日志：每个订单是哪个打包账号发的、实际发了多少件")
        self.b_ship.clicked.connect(lambda *a: self.ship())
        box.addWidget(self.b_ship)
        b_old = U.GlowButton("旧版窗口")
        b_old.setToolTip("打开原来的 Tk 批次窗（有按货位汇总等更多视图）")
        b_old.clicked.connect(lambda *a: self.api.desktop_action("batch"))
        box.addWidget(b_old)
        # 插到标题行下面（索引 1）
        self.layout().insertLayout(1, box)

    def _request(self):
        """批次查询：把 kw / days 一起发给服务端。"""
        return ("/api/desktop/table",
                {"name": "batch",
                 "kw": str(getattr(self, "kw", "") or ""),
                 "days": int(getattr(self, "days", 3) or 3)}, 180)

    def ship(self):
        """切到「发货明细」视图（打包账号 / 实际发货件数）。"""
        self.kw = (self.ent.text() or "").strip()
        try:
            self.days = int(self.sp.currentData() or 90)
        except Exception:
            self.days = 90
        if not self.kw:
            self.status.setText("先输入批次号，再点「发货明细」")
            return
        self._ship_mode = True
        self._seq = int(getattr(self, "_seq", 0)) + 1
        seq = self._seq
        self.status.setText("正在读发货日志（可能要十几秒）…")
        want, days = self.kw, self.days

        def work():
            try:
                import urllib.parse
                r = self.api.get("/api/desktop/table?" + urllib.parse.urlencode(
                    {"name": "ship", "kw": want, "days": days}), timeout=600)
            except Exception as e:
                r = {"error": str(e)[:150]}
            if seq == self._seq:
                self._disp.post(lambda: self.fill(r))

        threading.Thread(target=work, daemon=True).start()

    def requery(self):
        self.kw = (self.ent.text() or "").strip()
        try:
            self.days = int(self.sp.currentData() or 3)
        except Exception:
            self.days = 3
        self._ship_mode = False
        self.lbl_kw.setText(("批次：%s" % self.kw) if self.kw else "")
        self.reload()


class ShipStatsDialog(TableDialog):
    """每日发货量：选日期（可区间）+ 选账号（可全部），列出每个账号每天发了多少单/多少件。

    数据来源：ERP「发货」操作日志（action="发货"，实测秒回）。
    每行 = 一天 × 一个账号；表尾追加每个账号的「合计」行。
    """

    def __init__(self, api, theme="light", parent=None):
        self.date_from = time.strftime("%Y-%m-%d")
        self.date_to = ""
        self.who = ""
        self._ship_mode = True
        super().__init__(api, "ship_stats", theme, parent)
        self.setWindowTitle("每日发货量（按账号）")
        self.resize(1080, 660)

        box = QHBoxLayout()
        box.addWidget(QLabel("从"))
        self.d1 = QLineEdit(self.date_from)
        self.d1.setPlaceholderText("YYYY-MM-DD")
        self.d1.setFixedWidth(120)
        self.d1.setMinimumHeight(32)
        box.addWidget(self.d1)
        box.addWidget(QLabel("到"))
        self.d2 = QLineEdit("")
        self.d2.setPlaceholderText("留空=同一天")
        self.d2.setFixedWidth(120)
        self.d2.setMinimumHeight(32)
        box.addWidget(self.d2)
        box.addWidget(QLabel("账号"))
        self.cb = QComboBox()
        self.cb.addItem("全部账号", "")
        for a in ("打包1", "打包2", "打包3", "打包4"):
            self.cb.addItem(a, a)
        self.cb.setEditable(True)
        self.cb.setMinimumHeight(32)
        self.cb.setToolTip("下拉里是常见的打包账号，也可以自己输别的账号名")
        box.addWidget(self.cb, 1)
        b = U.GlowButton("查 询", primary=True)
        b.clicked.connect(lambda *a: self.requery())
        box.addWidget(b)
        box.addWidget(QLabel("今天"))
        b_t = U.GlowButton("今天")
        b_t.clicked.connect(lambda *a: self._today())
        box.addWidget(b_t)
        b_y = U.GlowButton("昨天")
        b_y.clicked.connect(lambda *a: self._days_ago(1))
        box.addWidget(b_y)
        b_w = U.GlowButton("最近7天")
        b_w.clicked.connect(lambda *a: self._range(6))
        box.addWidget(b_w)
        self.d1.returnPressed.connect(lambda *a: self.requery())
        self.d2.returnPressed.connect(lambda *a: self.requery())
        self.layout().insertLayout(1, box)
        self.reload()

    def _today(self):
        self.d1.setText(time.strftime("%Y-%m-%d"))
        self.d2.setText("")
        self.requery()

    def _days_ago(self, n):
        self.d1.setText(time.strftime("%Y-%m-%d", time.localtime(time.time() - n * 86400)))
        self.d2.setText("")
        self.requery()

    def _range(self, back):
        self.d1.setText(time.strftime("%Y-%m-%d", time.localtime(time.time() - back * 86400)))
        self.d2.setText(time.strftime("%Y-%m-%d"))
        self.requery()

    def _request(self):
        return ("/api/desktop/table",
                {"name": "ship_stats",
                 "from": str(getattr(self, "date_from", "") or ""),
                 "to": str(getattr(self, "date_to", "") or ""),
                 "who": str(getattr(self, "who", "") or "")}, 600)

    def requery(self):
        self.date_from = (self.d1.text() or "").strip()
        self.date_to = (self.d2.text() or "").strip()
        try:
            self.who = str(self.cb.currentData() or "").strip() or \
                       (self.cb.currentText() or "").strip()
        except Exception:
            self.who = ""
        if self.who == "全部账号":
            self.who = ""
        self.reload()


class StockDialog(QDialog):
    """现货可发（带完整控制栏）—— 对齐旧版那个窗。

    旧版这个窗不只是表格，上面有一排控件，这里全都做出来：
      编码/款号搜索 · 排序 · 只看筛选 · 隐藏已发 · 查询 · 导出 Excel ·
      标记已发 · 撤回 · 清空已发 · 改库存 · 操作日志
    """

    ONLY = [("全部", "all"), ("只看加急且有货", "urg_free"), ("只看有加急", "urgent"),
            ("只看可发（>0）", "free"), ("只看缺货（<0）", "short"), ("只看有待发货", "orders")]
    SORT = [("加急有货优先（可发多→少）", "urg_free"), ("可发数量（多→少）", "free"),
            ("加急件数（多→少）", "urgent"), ("在架数（多→少）", "shelf"),
            ("待发货件数（多→少）", "pieces"), ("编码 A→Z", "code")]

    def __init__(self, api, theme="light", parent=None):
        super().__init__(parent)
        self.api = api
        self._disp = Dispatcher(self)
        self._seq = 0
        self.rows = []
        self.setWindowTitle("现货可发（在架 / 待发货 / 可发件数）")
        self.resize(1240, 720)
        self.setStyleSheet(U.qss(U.LIGHT if theme == "light" else U.DARK))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(12, 12, 12, 10)
        lay.setSpacing(8)

        # ── 控制栏 ──
        bar = QHBoxLayout()
        bar.setSpacing(6)
        bar.addWidget(QLabel("编码/款号"))
        self.ed_kw = QLineEdit()
        self.ed_kw.setPlaceholderText("输入编码或款号，回车查询")
        self.ed_kw.setMinimumWidth(180)
        self.ed_kw.returnPressed.connect(lambda *a: self.reload())
        bar.addWidget(self.ed_kw)

        bar.addWidget(QLabel("排序"))
        self.cb_sort = QComboBox()
        for t, v in self.SORT:
            self.cb_sort.addItem(t, v)
        self.cb_sort.currentIndexChanged.connect(lambda *a: self.reload())
        bar.addWidget(self.cb_sort)

        bar.addWidget(QLabel("只看"))
        self.cb_only = QComboBox()
        for t, v in self.ONLY:
            self.cb_only.addItem(t, v)
        self.cb_only.currentIndexChanged.connect(lambda *a: self.reload())
        bar.addWidget(self.cb_only)

        self.ck_hide = QCheckBox("隐藏已发")
        self.ck_hide.setChecked(True)
        self.ck_hide.stateChanged.connect(lambda *a: self.reload())
        bar.addWidget(self.ck_hide)

        b_q = U.GlowButton("查 询")
        b_q.clicked.connect(lambda *a: self.reload())
        bar.addWidget(b_q)
        bar.addStretch(1)
        for label, fn, tip in (
                ("导出 Excel", lambda: self.act("export"), "把当前筛选结果导出到 导出\\ 目录"),
                ("标记已发", lambda: self.mark(True), "把选中的编码标记为「可发」（可以打了）"),
                ("撤回", lambda: self.mark(False), "撤回选中编码的「可发」标记"),
                ("清空已发", self.clear_sent, "清掉全部「可发」标记"),
                ("改库存", self.adjust, "按货位改库存（会真实改快麦，需二次确认）"),
                ("操作日志", lambda: self.open_log(), "看改库存的操作日志")):
            b = U.GlowButton(label)
            b.setToolTip(tip)
            b.clicked.connect(lambda *a, f=fn: f())
            bar.addWidget(b)
        lay.addLayout(bar)

        # ── 表格 ──
        self.t = QTableWidget(0, 14)
        setup_table(self.t, [200, 130, 80, 110, 110, 80, 80, 90, 130, 90, 80, 70, 90, 90])
        self.t.setSelectionBehavior(QTableWidget.SelectRows)
        lay.addWidget(self.t, 1)

        # ── 底部 ──
        foot = QHBoxLayout()
        self.msg = QLabel("")
        self.msg.setObjectName("hint")
        foot.addWidget(self.msg)
        foot.addStretch(1)
        b_old = U.GlowButton("打开旧版窗口")
        b_old.setToolTip("打开原来的 Tk 现货可发窗（应急用）")
        b_old.clicked.connect(lambda *a: self.api.desktop_action("stock"))
        foot.addWidget(b_old)
        b_cl = U.GlowButton("关 闭", primary=True)
        b_cl.clicked.connect(self.accept)
        foot.addWidget(b_cl)
        lay.addLayout(foot)
        self.reload()

    def _cur(self, cb):
        try:
            return cb.currentData() or ""
        except Exception:
            return ""

    def reload(self):
        self._seq += 1
        seq = self._seq
        kw = self.ed_kw.text().strip()
        only = self._cur(self.cb_only) or "all"
        sort = self._cur(self.cb_sort) or "free"
        hide = self.ck_hide.isChecked()
        self.msg.setText("正在查询…")

        def work():
            try:
                r = self.api.stock(kw, only, sort, hide)
            except Exception as e:
                r = {"error": str(e)[:150]}
            self._disp.post(lambda: self.fill(seq, r))

        threading.Thread(target=work, daemon=True).start()

    def fill(self, seq, r):
        if seq != self._seq:
            return                        # 过期响应丢掉（用户又改了条件）
        r = r if isinstance(r, dict) else {}
        if r.get("error"):
            self.msg.setText("查询失败：%s" % str(r.get("error"))[:130])
            return
        cols = r.get("columns") or []
        rows = r.get("rows") or []
        self.rows = rows
        self.t.setColumnCount(max(1, len(cols)))
        self.t.setHorizontalHeaderLabels([str(c) for c in cols] or ["（无列）"])
        self.t.setRowCount(len(rows))
        for ri, row in enumerate(rows):
            for ci, v in enumerate(row):
                self.t.setItem(ri, ci, QTableWidgetItem("" if v is None else str(v)))
        self.msg.setText("共 %s 行%s" % (r.get("count", len(rows)),
                                        ("　（已隐藏「已发」）" if self.ck_hide.isChecked()
                                         else "")))

    def _sel_codes(self):
        out = []
        for idx in sorted({i.row() for i in self.t.selectedIndexes()}):
            it = self.t.item(idx, 0)
            if it is not None and it.text():
                out.append(it.text())
        return out

    def act(self, action, **kw):
        self.msg.setText("正在执行…")

        def work():
            try:
                r = self.api.stock_act(action, **kw)
            except Exception as e:
                r = {"error": str(e)[:180]}
            self._disp.post(lambda: self._done(action, r))

        threading.Thread(target=work, daemon=True).start()

    def _done(self, action, r):
        r = r if isinstance(r, dict) else {}
        if r.get("ok"):
            self.msg.setText(str(r.get("msg") or "完成 ✓"))
            self.reload()
        else:
            err = str(r.get("error") or "未知错误")
            if err == "need_confirm":
                self.msg.setText("需要确认")
            else:
                self.msg.setText("失败：%s" % err[:140])
                QMessageBox.warning(self, "操作失败", err[:300])

    def mark(self, on):
        codes = self._sel_codes()
        if not codes:
            QMessageBox.information(self, "提示", "先在表格里选中要操作的编码")
            return
        self.act("mark" if on else "undo", codes=codes)

    def clear_sent(self):
        if not QMessageBox.question(self, "确认", "清掉全部「可发」标记？") == QMessageBox.Yes:
            return
        self.act("clear_sent")

    def adjust(self):
        codes = self._sel_codes()
        if not codes:
            QMessageBox.information(self, "提示", "先在表格里选中要改库存的编码")
            return
        code = codes[0]

        def work():
            try:
                r = self.api.stock_act("bins", code=code)
            except Exception as e:
                r = {"error": str(e)[:150]}
            self._disp.post(lambda: self._ask_adjust(code, r))

        threading.Thread(target=work, daemon=True).start()

    def _ask_adjust(self, code, r):
        bins = ((r or {}).get("bins") or {}).get("bins") or []
        hint = "、".join("%s=%s" % (b[0], b[1]) for b in bins) if bins else "无货位记录"
        bin_code, ok = QInputDialog.getText(
            self, "改库存", "编码 %s\n货位号（现有：%s）" % (code, hint),
            QLineEdit.Normal, str(bins[0][0]) if bins else "")
        if not ok or not bin_code.strip():
            return
        bin_code = bin_code.strip()
        cur = None
        for b in bins:
            if str(b[0]).upper() == bin_code.upper():
                cur = b[1]
        qty, ok = QInputDialog.getText(
            self, "改库存", "把 %s 货位 %s 改成多少件？（当前 %s）"
            % (code, bin_code, ("%s 件" % cur) if cur is not None else "无记录"),
            QLineEdit.Normal, "0" if cur is None else str(cur))
        if not ok:
            return
        try:
            q = int(str(qty).strip())
            if q < 0:
                raise ValueError
        except Exception:
            QMessageBox.warning(self, "改库存", "数量要填 0 或正整数")
            return
        if QMessageBox.question(
                self, "确认改库存",
                "编码：%s\n货位：%s\n%s → %d 件\n\n【这会真实修改快麦里的库存，不可撤销】\n继续？"
                % (code, bin_code, ("当前 %s 件" % cur) if cur is not None else "当前无记录", q)
        ) != QMessageBox.Yes:
            return
        self.act("adjust", code=code, bin=bin_code, qty=q, confirm=True)

    def open_log(self):
        try:
            d = TableDialog(self.api, "adjust_log", self.theme, self)
            d.exec()
        except Exception as e:
            QMessageBox.warning(self, "操作日志", str(e)[:200])


class PrintClientsDialog(QDialog):
    """打印分工（哪个账号由哪台电脑自动打）—— Qt 版，替代旧 Tk 窗。

    数据：GET/POST /api/desktop/print_clients（map=账号→电脑、local=本机身份）。
    「不自动打」= 该账号不写进文件（跟旧窗同一口径）。
    """

    def __init__(self, api, theme="light", parent=None):
        super().__init__(parent)
        self.api = api
        self._disp = Dispatcher(self)
        self.setWindowTitle("打印分工（哪个账号由哪台电脑自动打）")
        self.resize(620, 520)
        self.setStyleSheet(U.qss(U.LIGHT if theme == "light" else U.DARK))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)
        head = QLabel("账号 → 哪台电脑自动打")
        head.setObjectName("sect")
        lay.addWidget(head)
        tip = QLabel("「不自动打」的账号不写进文件。下面的「本机身份」是这台电脑的身份，"
                     "每台电脑各存一份。")
        tip.setObjectName("hint")
        tip.setWordWrap(True)
        lay.addWidget(tip)

        self.rows_box = QVBoxLayout()
        lay.addLayout(self.rows_box)
        self.combos = {}
        self.box = None

        row = QHBoxLayout()
        self.msg = QLabel("")
        self.msg.setObjectName("hint")
        row.addWidget(self.msg)
        row.addStretch(1)
        b_old = U.GlowButton("旧版窗口")
        b_old.setToolTip("打开原来的 Tk 打印分工窗")
        b_old.clicked.connect(lambda *a: self.api.desktop_action("print_clients"))
        row.addWidget(b_old)
        b_save = U.GlowButton("保 存", primary=True)
        b_save.clicked.connect(lambda *a: self.save())
        row.addWidget(b_save)
        b_cl = U.GlowButton("关 闭")
        b_cl.clicked.connect(self.accept)
        row.addWidget(b_cl)
        lay.addLayout(row)
        self.load()

    def load(self):
        self.msg.setText("正在读取…")

        def work():
            try:
                r = self.api.print_clients()
            except Exception as e:
                r = {"error": str(e)[:150]}
            self._disp.post(lambda: self.fill(r))

        threading.Thread(target=work, daemon=True).start()

    def fill(self, r):
        r = r if isinstance(r, dict) else {}
        if r.get("error"):
            self.msg.setText("读取失败：%s" % str(r.get("error"))[:120])
            return
        self._data = r
        # 清掉旧的
        while self.rows_box.count():
            it = self.rows_box.takeAt(0)
            w = it.widget()
            if w is not None:
                w.deleteLater()
        cur = r.get("map") or {}
        ids = list(r.get("ids") or ["pc1", "pc2", "pc3"])
        names = list(r.get("accounts") or [])
        for n in list(cur.keys()):          # 已配过但这次没枚举到的账号也显示
            if n and n not in names:
                names.append(n)
        self.combos = {}
        for name in names:
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 0, 0, 0)
            lb = QLabel(str(name))
            lb.setMinimumWidth(160)
            h.addWidget(lb)
            cb = QComboBox()
            cb.addItem("不自动打", "")
            for cid in ids:
                cb.addItem("这台电脑是 %s" % cid, cid)
            want = str(cur.get(str(name)) or "")
            i = cb.findData(want)
            cb.setCurrentIndex(i if i >= 0 else 0)
            cb.setMinimumHeight(30)
            h.addWidget(cb, 1)
            self.rows_box.addWidget(row)
            self.combos[str(name)] = cb
        # 本机身份
        row = QWidget()
        h = QHBoxLayout(row)
        h.setContentsMargins(0, 6, 0, 0)
        lb = QLabel("本机身份")
        lb.setMinimumWidth(160)
        h.addWidget(lb)
        self.local = QComboBox()
        for cid in ids:
            self.local.addItem(cid, cid)
        li = self.local.findData(str(r.get("local") or "pc1"))
        self.local.setCurrentIndex(li if li >= 0 else 0)
        self.local.setMinimumHeight(30)
        h.addWidget(self.local, 1)
        self.rows_box.addWidget(row)
        self.msg.setText("共 %d 个账号（本机身份 %s）" % (len(names), r.get("local") or "pc1"))

    def save(self):
        m = {}
        for name, cb in (self.combos or {}).items():
            v = cb.currentData() or ""
            if v:
                m[name] = v
        local = ""
        try:
            local = self.local.currentData() or ""
        except Exception:
            pass
        self.msg.setText("正在保存…")

        def work():
            try:
                r = self.api.save_print_clients(m, local)
            except Exception as e:
                r = {"error": str(e)[:150]}
            self._disp.post(lambda: self._saved(r))

        threading.Thread(target=work, daemon=True).start()

    def _saved(self, r):
        if isinstance(r, dict) and r.get("ok"):
            self.msg.setText("已保存 ✓（本机身份 %s）" % (self.local.currentText()))
        else:
            self.msg.setText("保存失败：%s" % str((r or {}).get("error") or "未知错误")[:120])


class GatewayDialog(QDialog):
    """对外访问设置（域名 / frp 隧道 / HTTPS 证书）—— Qt 版，替代旧 Tk 窗。

    数据：GET/POST /api/desktop/gateway（网关是本机模块，主程序里直接调）。
    私钥内容不会被接口回传，只列证书文件名。
    """

    FIELDS = (("domain", "域名（手机访问用，如 km.example.com）"),
              ("server_addr", "frp 服务器地址"),
              ("server_port", "frp 服务器端口"),
              ("token", "frp token"),
              ("https_port", "HTTPS 端口（默认 9443）"),
              ("web_port", "本机网页端口（默认 8790）"))

    def __init__(self, api, theme="light", parent=None):
        super().__init__(parent)
        self.api = api
        self._disp = Dispatcher(self)
        self.setWindowTitle("对外访问设置（域名 / frp / 证书）")
        self.resize(720, 620)
        self.setStyleSheet(U.qss(U.LIGHT if theme == "light" else U.DARK))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)
        head = QLabel("对外访问设置")
        head.setObjectName("sect")
        lay.addWidget(head)
        tip = QLabel("只有主客户端那台需要设；子客户端不用管。证书私钥不会被上传/回传。")
        tip.setObjectName("hint")
        tip.setWordWrap(True)
        lay.addWidget(tip)

        form = QWidget()
        fl = QVBoxLayout(form)
        fl.setContentsMargins(0, 0, 0, 0)
        self.edits = {}
        for key, label in self.FIELDS:
            r = QHBoxLayout()
            lb = QLabel(label)
            lb.setMinimumWidth(220)
            lb.setObjectName("hint")
            r.addWidget(lb)
            e = QLineEdit()
            e.setMinimumHeight(30)
            r.addWidget(e, 1)
            fl.addLayout(r)
            self.edits[key] = e
        lay.addWidget(form)

        self.st = QLabel("")
        self.st.setObjectName("hint")
        self.st.setWordWrap(True)
        lay.addWidget(self.st)
        self.certs = QLabel("")
        self.certs.setObjectName("dimmer")
        self.certs.setWordWrap(True)
        lay.addWidget(self.certs)

        row = QHBoxLayout()
        self.msg = QLabel("")
        self.msg.setObjectName("hint")
        row.addWidget(self.msg)
        row.addStretch(1)
        b_old = U.GlowButton("旧版窗口")
        b_old.setToolTip("打开原来的 Tk 对外访问设置窗（有装证书等更多操作）")
        b_old.clicked.connect(lambda *a: self.api.desktop_action("gateway"))
        row.addWidget(b_old)
        b_re = U.GlowButton("刷 新")
        b_re.setToolTip("重新检查端口 / 进程 / 证书状态")
        b_re.clicked.connect(lambda *a: self.load())
        row.addWidget(b_re)
        b_save = U.GlowButton("保存", primary=True)
        b_save.clicked.connect(lambda *a: self.act("save"))
        row.addWidget(b_save)
        b_go = U.GlowButton("保存并启动隧道")
        b_go.clicked.connect(lambda *a: self.act("start"))
        row.addWidget(b_go)
        b_stop = U.GlowButton("停止")
        b_stop.clicked.connect(lambda *a: self.act("stop"))
        row.addWidget(b_stop)
        b_cl = U.GlowButton("关 闭")
        b_cl.clicked.connect(self.accept)
        row.addWidget(b_cl)
        lay.addLayout(row)
        self.load()

    def load(self):
        self.msg.setText("正在读取…")

        def work():
            try:
                r = self.api.gateway()
            except Exception as e:
                r = {"error": str(e)[:150]}
            self._disp.post(lambda: self.fill(r))

        threading.Thread(target=work, daemon=True).start()

    def fill(self, r):
        r = r if isinstance(r, dict) else {}
        if r.get("error"):
            self.msg.setText("读取失败：%s" % str(r.get("error"))[:120])
            return
        conf = r.get("conf") or {}
        for k, e in (self.edits or {}).items():
            try:
                e.setText("" if conf.get(k) is None else str(conf.get(k)))
            except Exception:
                pass
        st = r.get("status") or {}
        cfg = st.get("cfg") or conf or {}
        # ★ 跟旧 Tk 窗同一个口径，做成人话（用户要的就是这几行）
        lines = []
        url = str(st.get("url") or "")
        lines.append("对外地址：%s%s"
                     % (url or "（还没填域名）",
                        "　← 子客户端/手机就填这个" if url else ""))
        try:
            https_port = int(cfg.get("https_port") or 9443)
        except Exception:
            https_port = 9443
        lines.append("本机服务：%s %s　·　HTTPS 中转 %s %s　·　frpc 隧道 %s"
                     % (cfg.get("web_port") or 8790,
                        "在听 ✓" if st.get("web_open") else "没在听 ✗",
                        https_port,
                        "在听 ✓" if st.get("https_open") else "没在听 ✗",
                        "在跑 ✓" if st.get("frpc") else "没跑 ✗"))
        cert = st.get("cert") or {}
        if cert:
            left = cert.get("days_left")
            left_txt = ("还有 %s 天" % left) if isinstance(left, int) else ""
            lines.append("证书：%s（到期 %s %s）　共 %s 份"
                         % (cert.get("domain") or cert.get("name") or "-",
                            cert.get("not_after") or "未知", left_txt,
                            st.get("cert_count") or 0))
            if isinstance(left, int) and left < 15:
                lines.append("⚠ 证书快到期了：重新申请后在这里装新的 .crt / .key")
        else:
            lines.append("证书：还没有（手机摄像头扫码必须 https，先把证书装进来）")
        lines.append("frpc.toml：%s　·　开机自启：%s"
                     % ("有" if st.get("frpc_toml") else "没有",
                        "已开" if st.get("autostart") else "没开"))
        lines.append("服务目录：%s" % str(cfg.get("serv_root") or "-"))
        self.st.setText("\n".join(lines))
        certs = r.get("certs") or []
        paths = r.get("paths") or {}
        self.certs.setText("证书目录：%s\n目录里的文件：%s"
                           % (paths.get("cert_dir") or "-", "、".join(certs) or "（空）"))
        self.msg.setText("点「刷 新」可重新检查端口/进程状态")

    def act(self, action):
        self.msg.setText("正在执行 %s…" % action)
        conf = {}
        for k, e in (self.edits or {}).items():
            v = (e.text() or "").strip()
            if v:
                conf[k] = v

        def work():
            try:
                if action == "save":
                    r = self.api.gateway_action("save", conf=conf)
                else:
                    if conf:
                        self.api.gateway_action("save", conf=conf)
                    r = self.api.gateway_action(action)
            except Exception as e:
                r = {"error": str(e)[:150]}
            self._disp.post(lambda: self._done(action, r))

        threading.Thread(target=work, daemon=True).start()

    def _done(self, action, r):
        if isinstance(r, dict) and (r.get("ok") or r.get("msg")):
            self.msg.setText("已%s ✓" % {"save": "保存", "start": "启动", "stop": "停止"}
                             .get(action, action) + ("　" + str(r.get("msg"))[:80]
                                                     if r.get("msg") else ""))
            self.load()
        else:
            self.msg.setText("失败：%s" % str((r or {}).get("error") or "未知错误")[:140])


class AdminPanelDialog(QDialog):
    """子客户端管理（在线设备 / 账号 / 权限）—— Qt 版，替代旧 Tk 窗。

    接口：/api/devices（本机+账号列表）、/api/users（增删改踢）、/api/perms（权限）。
    """

    def __init__(self, api, theme="light", parent=None):
        super().__init__(parent)
        self.api = api
        self._disp = Dispatcher(self)
        self.setWindowTitle("子客户端管理")
        self.resize(980, 640)
        self.setStyleSheet(U.qss(U.LIGHT if theme == "light" else U.DARK))
        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 12, 14, 12)
        lay.setSpacing(8)
        head = QLabel("子客户端管理")
        head.setObjectName("sect")
        lay.addWidget(head)
        self.host = QLabel("")
        self.host.setObjectName("hint")
        self.host.setWordWrap(True)
        lay.addWidget(self.host)

        self.tabs = QTabWidget()
        self.t_dev = QTableWidget(0, 6)
        self.t_dev.setHorizontalHeaderLabels(["账号", "角色", "在线", "设备", "最后登录", "主账号"])
        setup_table(self.t_dev, [140, 90, 70, 0, 150, 80])
        self.tabs.addTab(self.t_dev, "在线设备 / 账号")

        self.t_perm = QTableWidget(0, 3)
        self.t_perm.setHorizontalHeaderLabels(["权限键", "说明", "允许"])
        setup_table(self.t_perm, [220, 0, 80])
        # ★ 权限页整页做成一个容器：表格 + 按钮栏（全选/全不选/恢复默认/刷新）
        #   +「电脑端和网页端同时在线」开关。旧版有这些，之前全漏了。
        ptab = QWidget()
        pv = QVBoxLayout(ptab)
        pv.setContentsMargins(0, 6, 0, 0)
        pv.setSpacing(6)
        pbar = QHBoxLayout()
        pbar.setSpacing(6)
        self.lbl_perm_info = QLabel("")
        self.lbl_perm_info.setObjectName("hint")
        pbar.addWidget(self.lbl_perm_info)
        pbar.addStretch(1)
        for label, fn, tip in (
                ("全 选", lambda: self.set_all_perms(True), "把当前账号的权限全部勾上"),
                ("全不选", lambda: self.set_all_perms(False), "把当前账号的权限全部取消"),
                ("恢复默认", self.restore_default_perms, "每个权限恢复成出厂默认值"),
                ("保存权限", lambda: self.save_perms(), "保存当前账号的权限勾选"),
                ("刷新", lambda: self.load(), "重新读取账号与权限")):
            b = U.GlowButton(label)
            b.setToolTip(tip)
            b.clicked.connect(lambda *a, f=fn: f())
            pbar.addWidget(b)
        self.ck_multi = QCheckBox("电脑端和网页端同时在线（允许该账号两端一起登录）")
        self.ck_multi.setToolTip("勾上：同一账号可以电脑版和网页端同时在线；"
                                 "不勾：后登录的会把前一个挤下线")
        self.ck_multi.clicked.connect(lambda *a: self.save_multi())
        pv.addWidget(self.ck_multi)
        pv.addWidget(self.t_perm, 1)
        pv.addLayout(pbar)
        self.tabs.addTab(ptab, "权限")
        lay.addWidget(self.tabs, 1)

        row = QHBoxLayout()
        self.msg = QLabel("")
        self.msg.setObjectName("hint")
        row.addWidget(self.msg)
        row.addStretch(1)
        self.who = QComboBox()
        self.who.setMinimumWidth(160)
        row.addWidget(self.who)
        for label, fn in (("踢下线", lambda: self.user_act("kick")),
                          ("加入", lambda: self.user_act("add")),
                          ("改密码", lambda: self.user_act("passwd")),
                          ("删除", lambda: self.user_act("del")),
                          ("保存权限", lambda: self.save_perms())):
            b = U.GlowButton(label)
            b.clicked.connect(lambda *a, f=fn: f())
            row.addWidget(b)
        b_old = U.GlowButton("旧版窗口")
        b_old.setToolTip("打开原来的 Tk 子客户端管理窗")
        b_old.clicked.connect(lambda *a: self.api.desktop_action("admin"))
        row.addWidget(b_old)
        b_re = U.GlowButton("刷 新")
        b_re.clicked.connect(lambda *a: self.load())
        row.addWidget(b_re)
        b_cl = U.GlowButton("关 闭", primary=True)
        b_cl.clicked.connect(self.accept)
        row.addWidget(b_cl)
        lay.addLayout(row)
        self.load()

    def load(self):
        self.msg.setText("正在读取…")

        def work():
            try:
                d = self.api.devices()
                p = self.api.perms_payload()
            except Exception as e:
                d, p = {"error": str(e)[:150]}, {}
            self._disp.post(lambda: self.fill(d, p))

        threading.Thread(target=work, daemon=True).start()

    def fill(self, d, p):
        d = d if isinstance(d, dict) else {}
        if d.get("error"):
            self.msg.setText("读取失败：%s" % str(d.get("error"))[:120])
            return
        host = d.get("host") or {}
        self.host.setText("本机：%s（%s / %s）　·　服务端口 %s　·　IP %s"
                          % (host.get("pc") or "-", host.get("name") or "-",
                             host.get("role") or "-", d.get("port") or "-",
                             "、".join((d.get("ips") or [])[:4]) or "-"))
        devs = d.get("devices") or []
        self.t_dev.setRowCount(len(devs))
        for r, u in enumerate(devs):
            vals = [u.get("name", ""), u.get("role", ""),
                    "在线" if u.get("online") else "离线",
                    u.get("device", ""), u.get("last_login", ""),
                    "是" if u.get("owner") else ""]
            for c, v in enumerate(vals):
                it = QTableWidgetItem("" if v is None else str(v))
                self.t_dev.setItem(r, c, it)
        self.t_dev.resizeColumnsToContents()
        # 账号下拉
        cur = self.who.currentText()
        self.who.clear()
        for u in devs:
            if u.get("name"):
                self.who.addItem(str(u["name"]))
        i = self.who.findText(cur)
        if i >= 0:
            self.who.setCurrentIndex(i)
        # ★ 每个账号的权限 + 是否允许两端同时在线（旧版是按账号切换显示的）
        self._perm_users = {str(u.get("name")): u for u in devs if u.get("name")}
        try:
            if not getattr(self, "_perm_hooked", False):
                self.who.currentTextChanged.connect(lambda *a: self._show_user_perms())
                self._perm_hooked = True
        except Exception:
            pass
        self._show_user_perms()
        # 权限表
        cat = []
        try:
            cat = (p or {}).get("catalog") or []
        except Exception:
            cat = []
        keys = []
        self._perm_default = {}
        for it in cat:
            if isinstance(it, dict) and it.get("key"):
                keys.append((it["key"], it.get("label") or it.get("name") or "",
                             it.get("group") or ""))
                if "default" in it:
                    self._perm_default[it["key"]] = bool(it.get("default"))
        # 按分组排（旧版也是按分组显示的）
        _order = {}
        for i, it in enumerate(cat if isinstance(cat, list) else []):
            if isinstance(it, dict) and it.get("group"):
                _order.setdefault(it["group"], i)
        keys.sort(key=lambda x: (_order.get(x[2], 999), str(x[0])))
        self.t_perm.setRowCount(len(keys))
        for r, (k, label, grp) in enumerate(keys):
            shown = "%s　·　%s" % (grp, k) if grp else k
            self.t_perm.setItem(r, 0, QTableWidgetItem(shown))
            self.t_perm.setItem(r, 1, QTableWidgetItem(str(label)))
            cb = QCheckBox()
            self.t_perm.setCellWidget(r, 2, cb)
            # 反查数据里这个键的值，确定勾选状态
            cb.setChecked(bool((self._perm_vals or {}).get(k)))
            cb.stateChanged.connect(lambda *a: self._perm_dirty())
        self.t_perm.resizeColumnsToContents()
        # 「同时在线」开关跟着当前选中的账号走
        try:
            u = self._perm_user or {}
            self.ck_multi.setChecked(bool(u.get("allow_multi_device")))
        except Exception:
            pass
        self.lbl_perm_info.setText("账号 %d 个　·　权限项 %d 个" % (len(devs), len(keys)))

    def user_act(self, action):
        name = (self.who.currentText() or "").strip()
        if not name:
            self.msg.setText("先选一个账号")
            return
        pw = ""
        if action in ("add", "passwd"):
            from PySide6.QtWidgets import QInputDialog
            pw, ok = QInputDialog.getText(self, "密码", "给 %s 设密码（至少 4 位）：" % name,
                                          QLineEdit.Password)
            if not ok or not pw:
                return

        def work():
            try:
                r = self.api.users_action(action, name=name, pw=pw)
            except Exception as e:
                r = {"error": str(e)[:150]}
            self._disp.post(lambda: self._user_done(action, r))

        threading.Thread(target=work, daemon=True).start()

    def _user_done(self, action, r):
        if isinstance(r, dict) and r.get("ok"):
            self.msg.setText("已%s ✓" % action)
            self.load()
        else:
            self.msg.setText("失败：%s" % str((r or {}).get("error") or "未知错误")[:140])

    def _show_user_perms(self):
        """把当前选中账号的权限勾选状态和「同时在线」开关刷到界面上。"""
        name = (self.who.currentText() or "").strip()
        u = (self._perm_users or {}).get(name) or {}
        self._perm_user = u
        self._perm_vals = dict(u.get("perms") or {})
        for r in range(self.t_perm.rowCount()):
            it = self.t_perm.item(r, 0)
            cb = self.t_perm.cellWidget(r, 2)
            if it is None or cb is None:
                continue
            key = str(it.text()).split("·")[-1].strip()
            try:
                cb.blockSignals(True)
                cb.setChecked(bool(self._perm_vals.get(key)))
                cb.blockSignals(False)
            except Exception:
                pass
        try:
            self.ck_multi.blockSignals(True)
            self.ck_multi.setChecked(bool(u.get("allow_multi_device")))
            self.ck_multi.blockSignals(False)
        except Exception:
            pass
        self.lbl_perm_info.setText("当前账号：%s（%s）　勾选 %d 项"
                                   % (name or "-", u.get("role") or "-",
                                      sum(1 for v in (self._perm_vals or {}).values() if v)))

    def _perm_dirty(self):
        self.lbl_perm_info.setText("有未保存的改动（点「保存权限」生效）")

    def set_all_perms(self, on):
        """全选 / 全不选（旧版两个按钮就是这个）。"""
        for r in range(self.t_perm.rowCount()):
            cb = self.t_perm.cellWidget(r, 2)
            if cb is not None:
                cb.setChecked(bool(on))
        self._perm_dirty()

    def restore_default_perms(self):
        """恢复默认：按权限清单里的 default 值勾选（不直接写库，跟旧版一样要点保存）。"""
        for r in range(self.t_perm.rowCount()):
            it = self.t_perm.item(r, 0)
            cb = self.t_perm.cellWidget(r, 2)
            if it is None or cb is None:
                continue
            key = str(it.text()).split("·")[-1].strip()
            cb.setChecked(bool((self._perm_default or {}).get(key)))
        self._perm_dirty()

    def save_multi(self):
        """保存「电脑端和网页端同时在线」。"""
        name = (self.who.currentText() or "").strip()
        if not name:
            return
        on = bool(self.ck_multi.isChecked())
        self.msg.setText("正在设置…")

        def work():
            try:
                r = self.api.set_multi_device(name, on)
            except Exception as e:
                r = {"error": str(e)[:150]}
            self._disp.post(lambda: self._multi_done(name, on, r))

        threading.Thread(target=work, daemon=True).start()

    def _multi_done(self, name, on, r):
        if isinstance(r, dict) and r.get("ok"):
            self.msg.setText("%s：电脑端和网页端同时在线 = %s ✓" % (name, "开" if on else "关"))
            self.load()
        else:
            self.msg.setText("设置失败：%s" % str((r or {}).get("error") or "未知错误")[:140])
            try:
                self.ck_multi.setChecked(not on)     # 失败回滚勾选状态
            except Exception:
                pass

    def save_perms(self):
        name = (self.who.currentText() or "").strip()
        if not name:
            return
        vals = {}
        for r in range(self.t_perm.rowCount()):
            k = self.t_perm.item(r, 0)
            cb = self.t_perm.cellWidget(r, 2)
            if k is not None and cb is not None:
                vals[k.text()] = bool(cb.isChecked())
        self.msg.setText("正在保存权限…")

        def work():
            try:
                r = self.api.save_perms(name, vals)
            except Exception as e:
                r = {"error": str(e)[:150]}
            self._disp.post(lambda: self._perm_done(r))

        threading.Thread(target=work, daemon=True).start()

    def _perm_done(self, r):
        if isinstance(r, dict) and r.get("ok"):
            self.msg.setText("权限已保存 ✓")
        else:
            self.msg.setText("保存失败：%s" % (str((r or {}).get("error") or "未知错误")[:140]))


class PrintProgressDialog(QDialog):
    """打单进度 / 实时日志（Qt 版，替代老的 Tk 窗口）。

    两个选项卡：
      · 任务  —— printing / queue / done / failed 四组 + 最近记录
      · 日志  —— 打单日志尾部 + 自动上架/审核日志尾部
    1.5 秒自刷新；底部保留「打开旧版窗口」，复杂操作随时切回去，功能一个不少。
    """

    def __init__(self, api, theme="light", parent=None):
        super().__init__(parent)
        self.api = api
        self.setWindowTitle("打单进度（实时）")
        self.resize(880, 620)
        self.setStyleSheet(U.qss(U.LIGHT if theme == "light" else U.DARK))

        lay = QVBoxLayout(self)
        lay.setContentsMargins(14, 14, 14, 12)
        lay.setSpacing(9)

        head = QHBoxLayout()
        self.lbl = QLabel("正在读取…")
        self.lbl.setObjectName("sect")
        head.addWidget(self.lbl)
        head.addStretch(1)
        self.tabs = QTabWidget()
        lay.addLayout(head)

        # --- 任务表 ---
        self.t_jobs = QTableWidget(0, 6)
        self.t_jobs.setHorizontalHeaderLabels(["状态", "任务号", "商家编码", "件数", "打印机/客户端", "备注"])
        self._setup_table(self.t_jobs, [70, 100, 0, 60, 150, 0])
        self.tabs.addTab(self.t_jobs, "打单任务")

        # --- 日志 ---
        self.t_log = QTableWidget(0, 1)
        self.t_log.setHorizontalHeaderLabels(["打单日志"])
        self._setup_table(self.t_log, [0])
        self.tabs.addTab(self.t_log, "实时日志")

        lay.addWidget(self.tabs, 1)

        row = QHBoxLayout()
        self.b_old = U.GlowButton("打开旧版窗口", glow=26)
        self.b_old.setToolTip("旧版窗口功能最全（暂停自动打单等），打不开的都在那边")
        self.b_old.clicked.connect(lambda: self._act("open_tk"))
        row.addWidget(self.b_old)
        b_dir = U.GlowButton("打开数据目录", glow=26)
        b_dir.clicked.connect(lambda: self._act("open_dir"))
        row.addWidget(b_dir)
        row.addStretch(1)
        b_clr = U.GlowButton("清空失败任务", glow=26)
        b_clr.clicked.connect(lambda: self._act("clear_failed"))
        row.addWidget(b_clr)
        b_del = U.GlowButton("删除选中", glow=26)
        b_del.clicked.connect(self._delete_selected)
        row.addWidget(b_del)
        b_r = U.GlowButton("刷 新", glow=30)
        b_r.clicked.connect(self.reload)
        row.addWidget(b_r)
        lay.addLayout(row)

        self._disp = Dispatcher(self)
        self._timer = QTimer(self)
        self._timer.setInterval(1500)
        self._timer.timeout.connect(self.reload)
        self._timer.start()
        QTimer.singleShot(50, self.reload)

    def _setup_table(self, t, widths):
        t.verticalHeader().setVisible(False)
        t.setShowGrid(False)
        t.setSelectionBehavior(QTableWidget.SelectRows)
        t.setEditTriggers(QTableWidget.NoEditTriggers)
        t.verticalHeader().setDefaultSectionSize(30)
        hh = t.horizontalHeader()
        hh.setSectionResizeMode(QHeaderView.Fixed)
        for i, w in enumerate(widths):
            if w:
                t.setColumnWidth(i, w)
            else:
                hh.setSectionResizeMode(i, QHeaderView.Stretch)

    # ---------- 数据 ----------
    def reload(self):
        def work():
            r = self.api.print_progress()
            self._disp.post(lambda: self._render(r))
        threading.Thread(target=work, daemon=True).start()

    def _render(self, r):
        if not isinstance(r, dict) or r.get("offline"):
            self.lbl.setText("本机服务未响应")
            return
        if r.get("ok") is False:
            self.lbl.setText("读取失败：%s" % str(r.get("err"))[:80])
            return
        lv = r.get("live") or {}
        cnt = lv.get("counts") or {}
        pg = r.get("progress") or {}
        self.lbl.setText("打印中 %s · 排队 %s · 完成 %s · 失败 %s　%s"
                         % (cnt.get("printing", len(lv.get("printing") or [])),
                            cnt.get("queue", len(lv.get("queue") or [])),
                            cnt.get("done", len(lv.get("done") or [])),
                            cnt.get("failed", len(lv.get("failed") or [])),
                            str(pg.get("text") or "")[:60]))

        rows = []
        for key, cn in (("printing", "打印中"), ("queue", "排队"),
                        ("done", "已完成"), ("failed", "失败")):
            for it in (lv.get(key) or []):
                if isinstance(it, dict):
                    rows.append((cn, it))
        self._ids = []
        self.t_jobs.setRowCount(len(rows))
        for i, (cn, it) in enumerate(rows):
            vals = [cn, str(it.get("id", "")), str(it.get("code") or it.get("trade") or ""),
                    str(it.get("qty", "")), str(it.get("printer") or it.get("client") or ""),
                    str(it.get("msg") or it.get("note") or "")[:60]]
            for c in range(6):
                self.t_jobs.setItem(i, c, QTableWidgetItem(vals[c]))
            try:
                self._ids.append(int(it.get("id")))
            except Exception:
                self._ids.append(None)

        logs = list((r.get("log") or []))
        logs += ["---- 自动上架 / 智能审核 ----"] + list((r.get("auto_log") or []))
        self.t_log.setRowCount(len(logs))
        for i, ln in enumerate(logs):
            self.t_log.setItem(i, 0, QTableWidgetItem(str(ln)))

    # ---------- 动作 ----------
    def _act(self, what):
        if what == "open_tk":
            # 旧版窗口（功能最全）：让主程序去开
            self.api.desktop_action("print_progress")
            return

        def work():
            r = self.api.print_action(what)
            self._disp.post(lambda: self._after(what, r))
        threading.Thread(target=work, daemon=True).start()

    def _after(self, what, r):
        if isinstance(r, dict) and r.get("ok"):
            if what == "clear_failed":
                self.lbl.setText("已清空失败任务：%s 条" % r.get("deleted", 0))
            elif what == "open_dir":
                self.lbl.setText("已在主程序那台电脑打开数据目录")
            self.reload()
        else:
            msg = (r or {}).get("error") or "操作失败"
            QMessageBox.warning(self, "打单进度", msg)

    def _delete_selected(self):
        ids = []
        for idx in self.t_jobs.selectionModel().selectedRows() if self.t_jobs.selectionModel() else []:
            i = idx.row()
            v = self._ids[i] if i < len(self._ids or []) else None
            if v:
                ids.append(v)
        if not ids:
            QMessageBox.information(self, "删除选中", "先在列表里选一行（可按住 Ctrl 多选）")
            return
        if QMessageBox.question(self, "删除选中", "确定删除选中的 %d 条打单任务？" % len(ids),
                                QMessageBox.Yes | QMessageBox.No,
                                QMessageBox.No) != QMessageBox.Yes:
            return

        def work():
            r = self.api.print_action("delete", ids=ids)
            self._disp.post(lambda: self._after("delete", r))
        threading.Thread(target=work, daemon=True).start()

    def closeEvent(self, e):
        try:
            self._timer.stop()
        except Exception:
            pass
        super().closeEvent(e)


class ApiSettingsDialog(QDialog):
    """API 设置（Qt 版）—— 换账号 / 换网关 / 换版本。

    字段跟旧设置窗完全一致，保存走主程序的 save_api_conf（同一套逻辑、同一个文件）。
    底部保留「打开旧版窗口」：那边还有"测试连接""恢复默认"等。
    """

    FIELDS = [
        ("gateway", "网关地址", False),
        ("version", "API 版本", False),
        ("appKey", "appKey", False),
        ("appSecret", "appSecret", True),
        ("refreshToken", "refreshToken", True),
        ("sessionId", "sessionId (accessToken)", True),
        ("signMethod", "签名方式", False),
        ("signUpper", "签名结果大写（1/0）", False),
    ]

    def __init__(self, api, theme="light", parent=None):
        super().__init__(parent)
        self.api = api
        self.setWindowTitle("API 设置（换账号 / 换网关 / 换版本）")
        self.resize(560, 520)
        self.setStyleSheet(U.qss(U.LIGHT if theme == "light" else U.DARK))

        lay = QVBoxLayout(self)
        lay.setContentsMargins(20, 18, 20, 16)
        lay.setSpacing(8)
        tip = QLabel("改完点「保存并应用」。这些值存在程序目录的 kuaimai_api.json，"
                     "可直接拷到别的电脑，不用重打包。")
        tip.setObjectName("hint")
        tip.setWordWrap(True)
        lay.addWidget(tip)

        self.ents = {}
        form = QVBoxLayout()
        form.setSpacing(6)
        for key, label, secret in self.FIELDS:
            row = QHBoxLayout()
            row.setSpacing(8)
            lb = QLabel(label)
            lb.setObjectName("sect")
            lb.setFixedWidth(150)
            row.addWidget(lb)
            e = QLineEdit()
            e.setMinimumHeight(34)
            if secret:
                e.setEchoMode(QLineEdit.Password)
            row.addWidget(e, 1)
            if secret:
                eye = QPushButton("👁")
                eye.setObjectName("icon")
                eye.setCheckable(True)
                eye.setFixedWidth(40)
                eye.toggled.connect(lambda on, w=e: w.setEchoMode(
                    QLineEdit.Normal if on else QLineEdit.Password))
                row.addWidget(eye)
            self.ents[key] = e
            form.addLayout(row)
        lay.addLayout(form)

        self.msg = QLabel("正在读取…")
        self.msg.setObjectName("hint")
        self.msg.setWordWrap(True)
        lay.addWidget(self.msg)
        lay.addStretch(1)

        btns = QHBoxLayout()
        b_old = U.GlowButton("打开旧版窗口", glow=26)
        b_old.setToolTip("旧版窗口里还有「测试连接」「恢复默认」")
        b_old.clicked.connect(lambda: self.api.desktop_action("api_settings"))
        btns.addWidget(b_old)
        btns.addStretch(1)
        b_c = U.GlowButton("关 闭")
        b_c.clicked.connect(self.accept)
        btns.addWidget(b_c)
        b_s = U.GlowButton("保存并应用", primary=True)
        b_s.clicked.connect(self.do_save)
        btns.addWidget(b_s)
        lay.addLayout(btns)

        self._disp = Dispatcher(self)
        QTimer.singleShot(30, self.reload)

    def reload(self):
        def work():
            r = self.api.api_conf()
            self._disp.post(lambda: self._render(r))
        threading.Thread(target=work, daemon=True).start()

    def _render(self, r):
        if not isinstance(r, dict) or r.get("offline"):
            self.msg.setText("本机服务未响应")
            return
        if r.get("error"):
            self.msg.setText(str(r.get("error"))[:120])
            return
        conf = r.get("conf") or {}
        for k, e in self.ents.items():
            e.setText(str(conf.get(k, "")))
        self.msg.setText("已读取当前参数（网关 %s，版本 %s）"
                         % (conf.get("gateway") or "-", conf.get("version") or "-"))

    def do_save(self):
        conf = {k: e.text() for k, e in self.ents.items()}
        self.msg.setText("正在保存…")

        def work():
            r = self.api.save_api_conf(conf)
            self._disp.post(lambda: self._after(r))
        threading.Thread(target=work, daemon=True).start()

    def _after(self, r):
        if isinstance(r, dict) and r.get("ok"):
            self.msg.setText("已保存并生效：网关 %s，版本 %s"
                             % (r.get("gateway") or "-", r.get("version") or "-"))
        else:
            msg = (r or {}).get("error") or "保存失败"
            self.msg.setText(msg)
            QMessageBox.warning(self, "API 设置", msg)


class FloatCard(QWidget):
    """扫码浮窗：无边框、置顶、不抢焦点，扫完在屏幕上方弹一张大字卡片，几秒后自己消失。

    这就是原来 Tkinter 那个「扫码浮窗」的 Qt 版。
    """

    _cur = None

    def __init__(self, parent, theme="light"):
        super().__init__(parent, Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint | Qt.Tool)
        self.setAttribute(Qt.WA_TranslucentBackground, False)
        c = U.LIGHT if theme == "light" else U.DARK
        self.setStyleSheet(U.qss(c))
        self.setObjectName("root")
        self._bg = QColor(c["panel"])

    def paintEvent(self, e):
        try:
            p = QPainter(self)
            p.fillRect(self.rect(), self._bg)
        except Exception:
            pass

    @classmethod
    def show_on(cls, parent, row, theme="light"):
        if cls._cur is not None:
            try:
                cls._cur.close()
            except Exception:
                pass
        w = FloatCard(parent, theme)
        lay = QVBoxLayout(w)
        lay.setContentsMargins(26, 18, 26, 18)
        lay.setSpacing(4)
        code = QLabel(str(row.get("code") or "-"))
        code.setObjectName("code")
        code.setAlignment(Qt.AlignCenter)
        lay.addWidget(code)
        bits = []
        for k, lab in (("pending", "待发货"), ("bin", "货位"), ("shelf", "在架"),
                       ("canprint", "可打"), ("who", "账号")):
            v = row.get(k)
            if v not in (None, "", 0, "0"):
                bits.append("%s %s" % (lab, v))
        sub = QLabel("　·　".join(bits) or "（这条记录没有更多信息）")
        sub.setObjectName("sect")
        sub.setAlignment(Qt.AlignCenter)
        lay.addWidget(sub)
        tip = QLabel("点一下关闭")
        tip.setObjectName("dimmer")
        tip.setAlignment(Qt.AlignCenter)
        lay.addWidget(tip)
        w.adjustSize()
        scr = QApplication.primaryScreen().availableGeometry()
        w.move(int(scr.center().x() - w.width() / 2), int(scr.top() + 90))
        w.show()
        w.raise_()
        w.mousePressEvent = lambda e: w.close()
        QTimer.singleShot(8000, w.close)      # 8 秒后自动关
        cls._cur = w
        return w


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8790")
    ap.add_argument("--token", default="")
    ap.add_argument("--user", default="")
    ap.add_argument("--pw", default="")
    ap.add_argument("--shot", default="")
    ap.add_argument("--parent-pid", type=int, default=0)
    ap.add_argument("--login-out", default="", help="登录模式：把会话写到这个文件")
    a = ap.parse_args()

    app = QApplication(sys.argv)

    # ① 登录模式：先弹 Qt 登录窗，把会话写给主程序，然后接着当主界面用
    if a.login_out:
        ls = LoginScreen(a.base, a.login_out)
        if ls.exec() != QDialog.Accepted:
            return 0
        try:
            with open(a.login_out, "r", encoding="utf-8") as f:
                _sess = json.load(f)
            # ★ 千万不要在这里删这个文件！
            #   单进程模式下「启动器」还要读它才能接着启动业务核心（ScanApp/内置服务）。
            #   以前这里 os.remove 了，导致启动器永远读不到会话、一直卡在等待，
            #   服务端就一直是登录阶段的占位对象 → 界面上所有按钮都回「请先登录」。
            #   删文件交给启动器（它读完会自己收拾）。
        except Exception:
            _sess = {}
        a.token = str(_sess.get("token") or "")
        a.user = str(_sess.get("name") or "")
        a.base = str(_sess.get("base") or a.base)

    api = Api(a.base)
    # ① 主程序直接给的会话（最常见）：拿来就用，**不再让用户登录第二遍**
    tok = a.token or os.environ.get("KM_QT_TOKEN") or ""
    who = a.user or os.environ.get("KM_QT_USER") or ""
    # ★ 诊断日志：界面这一侧以前完全是黑盒，出问题（按钮全 401）只能靠猜。
    #   把 token / 会话校验结果记到 %TEMP%\km_qt_client.log，一眼就能看出是不是
    #   "界面手里没有有效 token"。
    try:
        with open(os.path.join(tempfile.gettempdir(), "km_qt_client.log"), "a",
                  encoding="utf-8") as _f:
            _f.write("%s [qt-client] 启动 base=%s token=%s user=%s parent=%s login_out=%s\n"
                     % (time.strftime("%H:%M:%S"), a.base, (tok or "")[:8], who,
                        a.parent_pid, a.login_out))
    except Exception:
        pass
    if tok:
        api.token = tok
        api.name = who
        st = api.desktop_state()
        _ok = isinstance(st, dict) and not st.get("error") and not st.get("offline")
        try:
            with open(os.path.join(tempfile.gettempdir(), "km_qt_client.log"), "a",
                      encoding="utf-8") as _f:
                _f.write("%s [qt-client] 会话校验 ok=%s 返回=%s\n"
                         % (time.strftime("%H:%M:%S"), _ok,
                            str(st)[:200].replace("\n", " ")))
        except Exception:
            pass
        if _ok:
            api.ver = str(st.get("ver") or "")
        else:
            # ★ 自愈：服务端不认这个 token 时，去读**权威会话文件**（启动器写的那份）
            #   再试一次。否则界面手里会一直是一个坏 token，所有按钮都回「请先登录」。
            _fixed = False
            try:
                _sp = os.path.join(tempfile.gettempdir(), "km_host_session.json")
                if os.path.isfile(_sp):
                    with open(_sp, "r", encoding="utf-8") as _f:
                        _d = json.load(_f)
                    _t2 = str((_d or {}).get("token") or "")
                    if _t2 and _t2 != tok:
                        api.token = _t2
                        st2 = api.desktop_state()
                        _ok2 = (isinstance(st2, dict) and not st2.get("error")
                                and not st2.get("offline"))
                        try:
                            with open(os.path.join(tempfile.gettempdir(),
                                                   "km_qt_client.log"), "a",
                                      encoding="utf-8") as _f:
                                _f.write("%s [qt-client] 自愈：改用权威会话文件 token=%s ok=%s\n"
                                         % (time.strftime("%H:%M:%S"), _t2[:8], _ok2))
                        except Exception:
                            pass
                        if _ok2:
                            _fixed = True
                            api.ver = str(st2.get("ver") or "")
            except Exception:
                pass
            if not _fixed:
                # token 真的不好使了 → 清掉，退回落登录框
                api.token = ""
    # ② 没带会话：命令行给了账号密码就直接登，否则弹登录框
    if not api.token:
        if a.user and a.pw:
            ok, err = api.login(a.user, a.pw)
            if not ok:
                print("登录失败:", err)
        else:
            d = LoginDialog(api)
            if d.exec() != QDialog.Accepted:
                return 0

    w = Desktop(api)
    if a.parent_pid:
        w.watch_parent(a.parent_pid)      # 主程序退出后，这个窗口也自己退
    w.show()
    if a.shot:
        def shoot():
            try:
                w.activateWindow()
                w.raise_()
                app.processEvents()
                w.grab().save(a.shot)
                print("已截图:", a.shot)
            except Exception as e:
                print("截图失败:", e)
            app.quit()
        QTimer.singleShot(3500, shoot)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
