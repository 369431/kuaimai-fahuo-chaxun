# -*- coding: utf-8 -*-
"""检查更新的窗口部分：后台查 + 发现新版的弹窗（一键下载安装）。"""
import os
import threading
import tkinter as tk
import webbrowser
from tkinter import ttk, messagebox

import kuaimai_update as upd

BG = "#f2f2f7"
BLUE = "#0b5394"
GREEN = "#1B7F35"


def check_in_background(widget, current, on_result=None, timeout=10):
    """后台拉清单（不卡界面）；on_result(info) 在 UI 线程回调。"""
    def work():
        try:
            info = upd.check(current, timeout=timeout)
        except Exception as e:
            info = {"ok": False, "has_update": False, "latest": "", "error": str(e)[:120]}
        if on_result:
            try:
                widget.after(0, lambda: on_result(info))
            except Exception:
                pass

    threading.Thread(target=work, daemon=True).start()


def ask_update(parent, info, current, on_done=None, on_later=None):
    """发现新版本的弹窗。info = kuaimai_update.check() 的返回。"""
    win = tk.Toplevel(parent)
    win.title("发现新版本 %s" % (info.get("latest") or ""))
    win.geometry("560x420")
    win.minsize(520, 360)
    try:
        win.configure(bg=BG)
        win.transient(parent)
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
            try:
                win.after(0, apply)
            except Exception:
                pass

        def work():
            path, err = upd.download_setup(info, progress=prog)

            def done():
                if err:
                    tip.config(text=err, fg="#d70015")
                    btn_install.state(["!disabled"])
                    pb.pack_forget()
                    messagebox.showerror("下载失败", err, parent=win)
                    return
                tip.config(text="下载完成，正在启动安装程序…", fg=GREEN)
                okr, msg = upd.run_setup(path)
                if okr:
                    messagebox.showinfo(
                        "准备安装",
                        "安装包已下载：\n%s\n\n接下来安装向导会自己关掉正在运行的程序，装完重新打开就是新版。"
                        % path, parent=win)
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
            try:
                win.after(0, done)
            except Exception:
                pass

        threading.Thread(target=work, daemon=True).start()

    btn_install.configure(command=do_install)
    return win
