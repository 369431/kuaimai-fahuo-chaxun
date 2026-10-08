# -*- coding: utf-8 -*-
"""电脑版单进程启动器（v1.84）。

**它解决的问题**：以前 ui=qt 是「老 Tk 主程序当引擎 + Qt 窗口当客户端」两个进程。
现在由这个启动器把引擎搬进电脑版自己的进程：

    这个进程（电脑版）
      ├── Tk 根窗（隐藏/全透明，业务核心 ScanApp 靠它）
      ├── 内置网页服务（手机端访问的就是它）
      ├── 全部后台任务（自动打单 / 自动上架 / 9443 中转 / 心跳 / 索引抓取）
      └── Qt 窗口（独立进程，只负责画面，连本进程的服务）

用法：
    python kuaimai_qt_main.py                # 单进程模式启动
    python kuaimai_qt_main.py --tk           # 退回老行为（起 Tk 主界面），应急用
"""
import os
import sys
import time
import traceback

DESKTOP = os.path.dirname(os.path.abspath(__file__))
if DESKTOP not in sys.path:
    sys.path.insert(0, DESKTOP)


def _log(msg):
    """同时写 stderr 和 %TEMP%\\km_qt_main.log。

    为什么写文件：打包成 GUI exe 后 stderr 不接到任何地方（诊断时看不到输出），
    而单进程启动流程出问题必须能留下痕迹。
    """
    line = "%s [qt-main] %s\n" % (time.strftime("%H:%M:%S"), msg)
    try:
        sys.stderr.write(line)
        sys.stderr.flush()
    except Exception:
        pass
    try:
        import tempfile
        with open(os.path.join(tempfile.gettempdir(), "km_qt_main.log"), "a",
                  encoding="utf-8") as f:
            f.write(line)
    except Exception:
        pass


def main():
    _log("启动器进入 main() pid=%d argv=%r" % (os.getpid(), sys.argv[1:]))
    import kuaimai_scan as KS
    import kuaimai_client as kmc

    # 应急开关：KM_TK_UI=1 或 --tk 就走老路（老 main()），方便出问题时立刻回退
    if "--tk" in sys.argv or str(os.environ.get("KM_TK_UI") or "") == "1":
        _log("走了 --tk/KM_TK_UI 老路")
        return KS.main()

    if kmc is None:
        _log("缺少 kuaimai_client，无法启动")
        return 2

    import kuaimai_host as HOST

    host = HOST.Host()

    # ---------- 1) 先起服务 + 弹 Qt 登录窗拿会话 ----------
    session = None
    try:
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        KS._RAISE_ROOT["root"] = root
        try:
            import kuaimai_theme
            kuaimai_theme.apply(root)
        except Exception:
            pass
        data = host.login_via_qt(root)
        _log("登录返回：%s" % ("拿到 token" if (isinstance(data, dict) and data.get("token"))
                              else "没拿到（%r）" % (data,)))
        try:
            root.destroy()
        except Exception:
            pass
        if isinstance(data, dict) and data.get("token"):
            session = kmc.Session(mode=data.get("mode") or "host",
                                  base=data.get("base") or "",
                                  token=data["token"],
                                  name=data.get("name") or "",
                                  role=data.get("role") or "",
                                  server_name=data.get("server_name") or "")
    except Exception:
        _log("登录阶段异常：\n" + traceback.format_exc()[-1200:])
        session = None

    if session is None:
        # 登录窗被关掉/失败 → 回退老流程（会自己弹 Tk 登录窗）
        _log("Qt 登录未完成，回退老流程")
        return KS.main()

    # ---------- 2) 起主机（Tk 根窗 + 服务 + ScanApp + 全部后台任务）----------
    try:
        host.start(session, show_tk=False, lan=True)
        _log("宿主已起：服务端 app=%s 端口=%s"
             % (type(__import__("kuaimai_scan")._WebHandler.app).__name__, host._port()))
    except Exception:
        _log("宿主启动失败：\n" + traceback.format_exc()[-1500:])
        return 3

    # ---------- 2b) 诊断模式：只看服务端挂的是谁，不起 Qt 窗口、几秒后退出 ----------
    #   用途：排查"接口全打在占位对象上"这类问题（冻结版里没法进调试器）。
    if str(os.environ.get("KM_HOST_DIAG") or "") == "1":
        try:
            import kuaimai_scan as _KS
            _log("DIAG 服务端 app=%s 端口=%s lan=%s"
                 % (type(_KS._WebHandler.app).__name__, host._port(),
                    _KS._WEB_STATE.get("lan")))
            _log("DIAG ScanApp=%r  _LIVE_APP=%r"
                 % (type(host.app).__name__,
                    (type(_KS._LIVE_APP.get("app")).__name__
                     if _KS._LIVE_APP.get("app") is not None else None)))
            for _i in range(10):
                try:
                    host.root.update()
                except Exception:
                    pass
                time.sleep(0.5)
            _log("DIAG 5 秒后 app=%s" % type(_KS._WebHandler.app).__name__)
        except Exception:
            _log("DIAG 异常：\n" + traceback.format_exc()[-600:])
        try:
            host.root.destroy()
        except Exception:
            pass
        return 0

    # ---------- 3) 起 Qt 窗口（只负责画面，连本进程的服务）----------
    try:
        host.start_qt(token=getattr(session, "token", "") or "",
                      user=getattr(session, "name", "") or "")
    except Exception:
        _log("Qt 窗口启动失败：\n" + traceback.format_exc()[-800:])
        # Qt 起不来就把 Tk 界面放出来，别让用户啥都看不到
        try:
            host.root.attributes("-alpha", 1.0)
            host.root.deiconify()
        except Exception:
            pass

    _log("单进程模式已就绪：pid=%d 端口=%d" % (os.getpid(), host._port()))
    try:
        host.run()          # Tk mainloop 占住主线程
    except KeyboardInterrupt:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
