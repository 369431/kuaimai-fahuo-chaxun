# -*- coding: utf-8 -*-
"""电脑版「单进程」宿主（v1.84 内核改动）。

**为什么要有这个文件**：以前 ui=qt 是两个进程 ——
  ① 老 Tk 主程序进程：起内置网页服务、跑订单/货位/锁定数抓取、自动打单/上架/审核/9443 中转；
  ② Qt 窗口进程：只是个客户端，连 ① 拿数据。
用户要的是「完全的新版本、不依赖旧版本」，所以这个模块把 ① 的活儿搬进
**电脑版自己的进程**里来：

  · 自己起内置网页服务（ensure_web_server，lan=True）
  · 自己建 ScanApp（业务核心：索引/扫码/打印/上架/审核都在它身上）
  · 自己跑全部后台任务（自动打单 watcher、自动上架、9443 中转、心跳、单实例互斥）
  · 自己驱动 Tk 事件循环（Qt 里挂一个 30ms 的定时器抽 Tk 事件）

设计上的两条硬约束（踩过坑才这么写）：
  1. **Tk 根窗必须存在**：ScanApp 和它的一堆设置窗到处在用 Tk StringVar；
     不能因为「界面上看不到 Tk」就把 root 去掉。
  2. **Tk 只能在主线程建**：所以本模块要求调用方在**主线程**调 start()，
     然后让 Tk 的 mainloop 跑在主线程；Qt 事件循环由 Tk 的 after 回调抽。
     反过来（Qt 主、Tk 辅）会让 Tk 掉进非主线程，那是不允许的。
"""
import os
import subprocess
import sys
import tempfile
import threading
import time
import traceback

import tkinter as tk

import kuaimai_scan as KS
import kuaimai_client as kmc

DESKTOP = os.path.dirname(os.path.abspath(__file__))
UI_QT_MODULE = "qtui.window"


def _L(*parts):
    """宿主日志：写 %TEMP%\\km_host.log。

    打包成 GUI exe 后 stderr 不接任何地方，而启动流程一卡住就整个软件不可用，
    必须留下痕迹（这次就是靠它定位到"卡在等登录文件"的）。
    """
    try:
        line = "%s [host] %s\n" % (time.strftime("%H:%M:%S"),
                                   " ".join(str(p) for p in parts))
        with open(os.path.join(tempfile.gettempdir(), "km_host.log"), "a",
                  encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


class Host(object):
    """单进程宿主：持有 root / app / session，负责全部后台启动。"""

    def __init__(self):
        self.root = None
        self.app = None
        self.session = None
        self.qt_proc = None
        self._qt_thread = None
        self.err = ""

    # ---------- 登录 ----------
    def login(self, name="", pw=""):
        """拿会话。给了账号密码就直接登；没给就调 Qt 登录窗（还是这一个进程之外的小窗，
        登录本身需要「还没登录」的状态，放子进程最省事，跟原来一致）。"""
        if name and pw:
            sess, err = kmc.login("http://127.0.0.1:%d" % self._port(), name, pw, mode="host")
            if sess is None:
                return None, err
            return sess, ""
        return None, ""

    def _port(self):
        return int(KS._WEB_STATE.get("port") or KS.WEB_PORT)

    # ---------- 登录（单进程模式专用）----------
    def login_via_qt(self, root, wait_secs=900):
        """弹 Qt 登录窗拿会话，成功后**关掉登录窗进程**（它不会变成主界面）。

        跟 kuaimai_scan.qt_login_session 的区别：那个函数是「登录窗登录后自己继续当主界面」，
        单进程模式里主界面由本进程自己起（host.start_qt），所以必须把登录窗收掉，
        否则会出现两个电脑版窗口。
        """
        import subprocess
        import tempfile
        try:
            KS.ensure_web_server(None, lan=False)
        except Exception:
            return None
        port = int(KS._WEB_STATE.get("port") or KS.WEB_PORT)
        base = "http://127.0.0.1:%d" % port
        # ★ 这个文件名必须和传给 Qt 窗口的 --login-out 完全一致，否则永远等不到登录结果。
        #   （踩过：这里写成 km_qt_login_<pid>.json，而登录窗被要求写 km_qt_session_<pid>.json，
        #     结果 launcher 一直卡在等待，主界面永远不接管 → 功能全废。）
        out = os.path.join(tempfile.gettempdir(), "km_qt_session_%d.json" % os.getpid())
        try:
            if os.path.isfile(out):
                os.remove(out)
        except Exception:
            pass
        if getattr(sys, "frozen", False):
            args = [sys.executable, "--qt-window", "--base", base, "--login-out", out]
        else:
            args = [sys.executable, "-m", UI_QT_MODULE, "--base", base, "--login-out", out]
        try:
            env = dict(os.environ)
            env["PYTHONPATH"] = DESKTOP + os.pathsep + env.get("PYTHONPATH", "")
            proc = subprocess.Popen(args, cwd=DESKTOP, env=env, close_fds=True)
        except Exception:
            return None
        t0 = time.time()
        try:
            while time.time() - t0 < float(wait_secs):
                if os.path.isfile(out):
                    data = None
                    try:
                        import json
                        with open(out, "r", encoding="utf-8") as f:
                            data = json.load(f)
                    except Exception:
                        data = None
                    if isinstance(data, dict) and data.get("token"):
                        _L("读到会话文件：", out)
                        return data
                    # 文件在但内容不对（可能正写到一半）→ 等一下再看
                if proc.poll() is not None:
                    _L("login", "登录窗进程已退出，但没读到会话文件")
                    return None                     # 用户把登录窗关了
                try:
                    root.update()                   # 让 Tk 别僵住
                except Exception:
                    pass
                time.sleep(0.15)
        finally:
            try:
                if proc.poll() is None:
                    proc.terminate()                # ★ 收掉登录窗（主界面我们自己起）
            except Exception:
                pass
        return None

    # ---------- 启动 ----------
    def start(self, session, show_tk=False, lan=True):
        """在**主线程**调用：建 Tk 根窗 → 起服务 → 建 ScanApp → 跑后台任务。

        lan=True：对外监听（0.0.0.0），手机端才能连；跟旧 main() 的 host 模式一致。
        """
        root = tk.Tk()
        if show_tk:
            root.deiconify()
        else:
            root.withdraw()
        KS._RAISE_ROOT["root"] = root
        self.root = root
        try:
            import kuaimai_theme
            kuaimai_theme.apply(root)
        except Exception:
            pass

        self.session = session
        try:
            KS.stop_web_server(clear_login=False)
        except Exception:
            pass
        KS.ensure_web_server(None, lan=bool(lan))
        port = self._port()
        try:
            session._port = port
        except Exception:
            pass

        app = KS.ScanApp(root, session)
        self.app = app
        # ★ 诊断：ScanApp 造完之后，内置服务手里挂的是谁？
        #   （单进程启动器必须确认服务挂上了真 app，否则接口全打在占位对象上）
        try:
            who = type(KS._WebHandler.app).__name__
            _L("ScanApp 造好：服务端 app=%s 端口=%d" % (who, self._port()))
            if who != "ScanApp":
                KS._WebHandler.app = app
                KS._WEB_STATE["app"] = app
                _L("已把服务端 app 纠正为 ScanApp")
        except Exception:
            pass

        # ★ 界面上看不到 Tk，但设置窗要用它当父窗口 → 全透明而不是 withdraw
        #   （withdraw 会让 transient 子窗「存在但不显示」，实测确认过）
        if not show_tk:
            try:
                root.attributes("-alpha", 0.0)
            except Exception:
                root.withdraw()

        self._start_services()
        self._bind_app()
        self._start_app_watchdog()
        return app

    def _bind_app(self):
        """把内置服务的 app 强制指向真 ScanApp。

        为什么需要（打包版实测踩到）：单进程启动器里服务重启了一次
        （登录阶段回环 → 主机阶段对外），重启后 _WebHandler.app 有可能还挂在
        登录阶段的占位对象 _NullHost 上 —— 那种情况下所有接口都会回
        「还没登录：请先在程序里登录」，界面看着正常但一条数据都出不来。
        所以这里在启动期强制绑定一次。
        """
        try:
            if self.app is not None:
                KS._WebHandler.app = self.app
                KS._WEB_STATE["app"] = self.app
                return type(KS._WebHandler.app).__name__
        except Exception:
            pass
        return ""

    def _start_app_watchdog(self):
        """后台看门狗：每 5 秒确认一次服务端还挂着真 ScanApp，被改回去就纠回来。"""
        def loop():
            while True:
                time.sleep(5)
                try:
                    if getattr(KS._WebHandler, "app", None) is not self.app:
                        self._bind_app()
                except Exception:
                    pass
        try:
            t = threading.Thread(target=loop, daemon=True)
            t.start()
        except Exception:
            pass

    def _start_services(self):
        """全部后台任务：心跳、自动打单、自动上架，都由 ScanApp 自己的 __init__
        前面已经起了一部分；这里补齐剩下的（跟旧 main() 的后半段一致）。"""
        app = self.app
        sess = self.session
        # ★ 先把当前 token 记到服务端状态并同步给业务会话 ——
        #   必须在起后台任务（自动打单/上架）**之前**做，否则监听第一轮就 401
        #   「请先登录」（真机踩过：会话带着一个读不到的旧 token）。
        try:
            KS._note_login(sess.name, sess.role, sess.mode,
                           token=str(getattr(sess, "token", "") or ""))
        except Exception:
            pass
        try:
            sess.start_heartbeat()
        except Exception:
            pass
        try:
            KS.start_auto_print_watcher(
                KS.DB_FILE if getattr(sess, "mode", "") == "host" else None, session=sess)
        except Exception:
            pass
        try:
            KS.start_auto_putaway_watcher(
                sess, shelf_map_getter=lambda: getattr(app, "shelf_map", {}) or {})
        except Exception:
            pass
        try:
            KS._note_login(sess.name, sess.role, sess.mode,
                           token=str(getattr(sess, "token", "") or ""))
        except Exception:
            pass

    # ---------- Qt 窗口 ----------
    def start_qt(self, token="", user=""):
        """起电脑版 Qt 窗口（**同一个进程之外的独立窗口进程**，
        但它连的是本进程起的服务 —— 服务与业务已经不再依赖老 Tk 主程序）。"""
        here = DESKTOP
        base = "http://127.0.0.1:%d" % self._port()
        if getattr(sys, "frozen", False):
            args = [sys.executable, "--qt-window", "--base", base]
        else:
            args = [sys.executable, "-m", UI_QT_MODULE, "--base", base]
        args += ["--parent-pid", str(os.getpid()), "--login-out", self._session_file()]
        try:
            env = dict(os.environ)
            env["PYTHONPATH"] = here + os.pathsep + env.get("PYTHONPATH", "")
            env["KM_QT_TOKEN"] = str(token or "")
            env["KM_QT_USER"] = str(user or "")
            self.qt_proc = subprocess.Popen(args, cwd=here, env=env, close_fds=True)
        except Exception:
            self.qt_proc = None
        return self.qt_proc

    def _session_file(self):
        return os.path.join(tempfile.gettempdir(), "km_host_session.json")

    # ---------- 跑起来 ----------
    def run(self):
        """主线程跑 Tk 事件循环；Qt 事件循环由定时器抽。"""
        self.root.mainloop()
