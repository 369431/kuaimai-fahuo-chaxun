# -*- coding: utf-8 -*-
"""检查更新的窗口部分：后台查 + 发现新版的弹窗（一键下载安装）。"""
import os
import threading
import tkinter as tk
import webbrowser
from tkinter import ttk, messagebox

import kuaimai_update as upd
import kuaimai_uikit as uikit

BG = "#f2f2f7"
BLUE = "#0b5394"
GREEN = "#1B7F35"


def check_in_background(widget, current, on_result=None, timeout=10):
    """后台拉清单（不卡界面）；on_result(info) 在 UI 线程回调。"""
    try:
        uikit.start(widget)
    except Exception:
        pass

    def work():
        try:
            info = upd.check(current, timeout=timeout)
        except Exception as e:
            info = {"ok": False, "has_update": False, "latest": "", "error": str(e)[:120]}
        if on_result:
            uikit.post(widget, on_result, info)

    threading.Thread(target=work, daemon=True).start()


def ask_update(parent, info, current, on_done=None, on_later=None):
    """发现新版本的弹窗。info = kuaimai_update.check() 的返回。"""
    win = tk.Toplevel(parent)
    win.title("发现新版本 %s" % (info.get("latest") or ""))
    win.geometry("560x420")
    win.minsize(480, 320)
    try:
        win.configure(bg=BG)
        # 刻意**不用** win.transient(parent)：transient 在 Windows 上会把窗口变成「被主窗口拥有」，
        # 任务栏里没有它的按钮 —— 最小化之后就找不回来了（用户反馈「下载时不可以最小化、一直在桌面」）。
        # 改成普通窗口：有自己的任务栏按钮，最小化/还原都正常；构造时手动提到最前面一次就够。
        win.lift()
        win.focus_force()
    except Exception:
        pass
    try:
        uikit.start(win)
    except Exception:
        pass

    def _show():
        """把窗口弄回前台：下载期间用户可能把它最小化了，有结果时必须让他看得见。"""
        try:
            win.deiconify()
            win.lift()
            win.focus_force()
        except Exception:
            pass

    head = tk.Frame(win, bg=BG)
    head.pack(fill=tk.X, padx=14, pady=(12, 2))
    tk.Label(head, text="发现新版本 %s" % (info.get("latest") or ""), bg=BG, fg="#1d1d1f",
             font=("Microsoft YaHei", 15, "bold")).pack(anchor="w")
    tk.Label(head, text="当前版本 %s　→　新版本 %s%s"
                        % (current, info.get("latest") or "", "（建议尽快更新）" if info.get("mandatory") else ""),
             bg=BG, fg="#6e6e73", font=("Microsoft YaHei", 9)).pack(anchor="w", pady=(2, 0))

    box = ttk.LabelFrame(win, text="这版改了什么", padding=8)
    box.pack(fill=tk.BOTH, expand=True, padx=14, pady=8)
    txt = tk.Text(box, wrap="word", font=("Microsoft YaHei", 10), height=8)
    txt.pack(fill=tk.BOTH, expand=True)
    txt.insert("1.0", str(info.get("notes") or "（清单里没写更新说明）"))
    txt.configure(state="disabled")

    tip = tk.Label(win, text="", bg=BG, fg=BLUE, font=("Microsoft YaHei", 9), wraplength=520,
                   justify="left", anchor="w")
    tip.pack(fill=tk.X, padx=14)
    pb = ttk.Progressbar(win, mode="determinate", maximum=100, length=520)
    pb.pack(fill=tk.X, padx=14, pady=(4, 0))
    pb.pack_forget()

    bar = ttk.Frame(win, padding=(14, 8))
    bar.pack(fill=tk.X)
    has_setup = bool(info.get("setup_url"))
    btn_install = ttk.Button(bar, text="下载并安装", style="Accent.TButton")
    btn_install.pack(side=tk.LEFT)
    if not has_setup:
        btn_install.state(["disabled"])
    ttk.Button(bar, text="打开发布页", command=lambda: webbrowser.open(str(info.get("page_url") or upd.RELEASES_PAGE))
               ).pack(side=tk.LEFT, padx=6)
    ttk.Button(bar, text="最小化", command=lambda: win.iconify()).pack(side=tk.RIGHT, padx=6)
    ttk.Button(bar, text="稍后", command=lambda: _later()).pack(side=tk.RIGHT)

    def _later():
        try:
            if callable(on_later):
                on_later(info)
        except Exception:
            pass
        win.destroy()

    def do_install():
        if not has_setup:
            webbrowser.open(str(info.get("page_url") or upd.RELEASES_PAGE))
            return
        btn_install.state(["disabled"])
        pb.pack(fill=tk.X, padx=14, pady=(4, 0))
        tip.config(text="正在下载安装包…")

        def prog(got, total, pct):
            def apply():
                try:
                    pb.configure(value=pct or 0)
                    tip.config(text="下载中 %.1f MB%s" % (got / 1048576.0,
                                                         (" / %.1f MB" % (total / 1048576.0)) if total else ""))
                except Exception:
                    pass
            uikit.post(win, apply)

        def work():
            path, err = upd.download_setup(info, progress=prog)

            def done():
                _show()                    # 下载期间用户可能把它最小化了：有结果先弄回前台
                if err:
                    tip.config(text=err, fg="#d70015")
                    btn_install.state(["!disabled"])
                    pb.pack_forget()
                    messagebox.showerror("下载失败", err, parent=win)
                    return
                tip.config(text="下载完成，正在静默安装…", fg=GREEN)
                okr, msg = upd.run_setup(path)
                if okr:
                    messagebox.showinfo(
                        "正在更新",
                        "安装包已下载：\n%s\n\n"
                        "接下来会静默安装（不再弹安装向导，只显示一个进度条）：\n"
                        "· 安装器会自动关掉本程序（和 9443 中转）\n"
                        "· 装完自动重新打开，就是新版了\n\n"
                        "如果窗口没自己消失，等几秒安装结束它会自行退出。" % path, parent=win)
                    try:
                        if callable(on_done):
                            on_done(path)
                    except Exception:
                        pass
                    win.destroy()
                else:
                    tip.config(text=msg, fg="#d70015")
                    messagebox.showerror("打不开安装包", msg, parent=win)
                    btn_install.state(["!disabled"])
            uikit.post(win, done)

        threading.Thread(target=work, daemon=True).start()

    btn_install.configure(command=do_install)
    return win
