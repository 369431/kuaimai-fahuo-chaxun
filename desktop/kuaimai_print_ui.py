# -*- coding: utf-8 -*-
"""打单窗口（独立小工具，可后续嵌进主程序）。

用法：python desktop/kuaimai_print_ui.py
流程：填/扫「商家编码」+「可打单数量」→ 预演（列单核对）→ 开始打单（取号→打印）→ 结果回显
规则（见 docs/打单对接.md）：只打一单一件、编码必须一致、加急→超时→剩余时间排序、
                              打印次数>0 才跳过；打印后**不自动标「已打」**（人工确认出纸后自己标）。
依赖：自动化 Edge 窗口（CDP 127.0.0.1:9222）已打开并登录 ERP 打单页。
"""
import os
import sys
import threading
import tkinter as tk
from tkinter import messagebox, ttk

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import kuaimai_print as K  # noqa


class PrintWin(object):
    def __init__(self, root):
        self.root = root
        root.title("打单（扫码编码 → 预演 → 打印）")
        root.geometry("900x560")
        top = ttk.Frame(root, padding=8)
        top.pack(fill="x")

        ttk.Label(top, text="商家编码：").pack(side="left")
        self.code = ttk.Entry(top, width=28)
        self.code.pack(side="left")
        self.code.bind("<Return>", lambda e: self.do_preview())

        ttk.Label(top, text="可打单数量：").pack(side="left", padx=(10, 0))
        self.qty = tk.Spinbox(top, from_=1, to=500, width=5)
        self.qty.pack(side="left")

        self.b_pre = ttk.Button(top, text="预演", command=self.do_preview)
        self.b_pre.pack(side="left", padx=6)
        self.b_run = ttk.Button(top, text="开始打单", command=self.do_run, state="disabled")
        self.b_run.pack(side="left")
        ttk.Button(top, text="清空", command=self.clear).pack(side="left", padx=6)
        self.silent = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="静默打单（不弹确认）", variable=self.silent).pack(side="left", padx=6)

        self.status = ttk.Label(root, text="待预演", foreground="#666")
        self.status.pack(fill="x", padx=10)

        self.txt = tk.Text(root, wrap="none", font=("Consolas", 10))
        self.txt.pack(fill="both", expand=True, padx=8, pady=6)
        self.picked = []
        self.queue = []

    # ---------- 工具 ----------
    def log(self, s):
        self.txt.insert("end", s + "\n")
        self.txt.see("end")

    def clear(self):
        self.txt.delete("1.0", "end")
        self.picked = []
        self.b_run.config(state="disabled")
        self.status.config(text="待预演")

    def _code_qty(self):
        code = self.code.get().strip()
        try:
            qty = int(self.qty.get())
        except Exception:
            qty = 0
        if not code or qty <= 0:
            messagebox.showwarning("打单", "请先填「商家编码」和「可打单数量」")
            return None, 0
        return code, qty

    def _busy(self, on, note=""):
        st = "disabled" if on else "normal"
        self.b_pre.config(state=st)
        self.b_run.config(state=st)
        self.status.config(text=note or ("处理中…" if on else "就绪"))

    # ---------- 预演 ----------
    def do_preview(self):
        code, qty = self._code_qty()
        if not code:
            return
        st, msg = K.ensure_browser()      # 自检：没跑就自动起；未登录提示登录；已登录静默
        if st != "ok":
            self.log("【浏览器】%s" % msg)
            messagebox.showinfo("打单", msg)
            return
        self._busy(True, "正在实时查单…")

        def work():
            try:
                orders = K.fetch_orders_live(code)
                picked, skipped = K.pick_orders(orders, qty, code=code)
            except SystemExit as e:
                orders, picked, skipped = None, None, str(e)
            except Exception as e:
                orders, picked, skipped = None, None, str(e)
            self.root.after(0, self._preview_done, code, qty, orders, picked, skipped)

        threading.Thread(target=work, daemon=True).start()

    def _preview_done(self, code, qty, orders, picked, skipped):
        self._busy(False)
        if orders is None:
            self.log("【预演失败】%s" % skipped)
            self.log("→ 若提示找不到页面：请先打开**自动化 Edge**，登录 ERP 打单页，保持窗口开着。")
            messagebox.showerror("预演失败", str(skipped))
            return
        self.txt.delete("1.0", "end")
        self.log("编码 %s | 要打 %s 单 | 实时查到 %d 单" % (code, qty, len(orders)))
        self.log("-" * 92)
        for o in sorted(orders, key=K.sort_key):
            can, why = K.is_single_item(o.get("items") or [])
            r = o.get("remain")
            self.log("%s %s 剩余=%s 已打=%s 加急=%s %s → %s" % (
                o["sid"], (o.get("short_id") or "").ljust(9),
                ("%.1fh" % r) if isinstance(r, float) else "?", o.get("print_count"),
                "是" if o.get("urgent") else "否", (o.get("express") or "")[:6],
                ("可打:" + why) if can else ("不可打:" + why)))
        self.log("-" * 92)
        self.log("→ 将打 %d 单：%s" % (len(picked), ", ".join("%s(%s)" % (p["sid"], p.get("short_id")) for p in picked)))
        for sid, why in skipped[:20]:
            self.log("   跳过 %s：%s" % (sid, why))
        self.picked = picked
        self.b_run.config(state=("normal" if picked else "disabled"))
        self.status.config(text="预演完成：将打 %d 单（确认无误后点「开始打单」）" % len(picked))
        self.txt.see("1.0")          # 停在最上面：方便看第一单的剩余时间

    # ---------- 真打 ----------
    def do_run(self):
        if not self.picked:
            return
        n = len(self.picked)
        if not self.silent.get() and not messagebox.askyesno(
                "确认打单", "将取号并打印 %d 单（不可撤回，会真的出纸）：\n%s\n\n确定继续？" % (
                    n, ", ".join(p.get("short_id") or p["sid"] for p in self.picked))):
            return
        code = self.code.get().strip()
        qty = len(self.picked)
        st, msg = K.ensure_browser()
        if st != "ok":
            self.log("【浏览器】%s" % msg)
            messagebox.showinfo("打单", msg)
            return
        self._busy(True, "取号 + 打印中…")

        def work():
            try:
                picked, skipped, logs = K.do_print(code, qty, dry_run=False)
            except SystemExit as e:
                picked, skipped, logs = None, None, [str(e)]
            except Exception as e:
                picked, skipped, logs = None, None, ["异常: %s" % e]
            self.root.after(0, self._run_done, picked, logs)

        threading.Thread(target=work, daemon=True).start()

    def _run_done(self, picked, logs):
        self._busy(False)
        self.log("")
        self.log("=== 打单结果 ===")
        if picked is None:
            for l in logs or []:
                self.log("  " + str(l))
            messagebox.showerror("打单失败", "\n".join(str(x) for x in (logs or [])[:3]))
            return
        for l in logs or []:
            self.log("  " + str(l))
        self.log("提示：请在打印机旁确认真的出纸；本工具**不会**自动标「已打」，")
        self.log("     请确认出单后自行在扫码记录里标记。")
        self.root.after(2000, self._next_job)      # 队列：处理下一条

    # ---------- 供主程序调用 ----------
    def set_code(self, code, qty=1):
        self.code.delete(0, "end")
        self.code.insert(0, str(code))
        self.qty.delete(0, "end")
        self.qty.insert(0, str(qty))
        self.do_preview()

    # ---------- 待打队列（供主程序传入选中的扫码行） ----------
    def set_queue(self, jobs):
        """jobs = [(商家编码, 可打单数量), ...]：逐条预演，打印完自动下一条。"""
        self.queue = [tuple(j) for j in (jobs or [])]
        self.log("待打队列 %d 条：%s" % (len(self.queue),
                                       ", ".join("%s×%s" % (c, q) for c, q in self.queue)))
        self._next_job()

    def _next_job(self):
        if not self.queue:
            self.status.config(text="队列已处理完")
            return
        code, qty = self.queue.pop(0)
        self.set_code(code, qty)      # 触发预演（人工确认后再打）


def open_window(jobs=None, master=None):
    """打开打单窗口。

    master 传主程序窗口时用 Toplevel（共用同一个 Tk 根）——**不会出现字体变小/发虚**；
    不传则自己起一个根窗口（单独运行本文件时用）。
    """
    if master is not None:
        win = tk.Toplevel(master)
        w = PrintWin(win)
        if jobs:
            w.set_queue(jobs)
        try:
            win.transient(master)
            win.lift()
        except Exception:
            pass
        return w
    root = tk.Tk()
    try:
        ttk.Style().theme_use("vista")
    except Exception:
        pass
    win = PrintWin(root)
    if jobs:
        win.set_queue(jobs)
    root.mainloop()
    return win


def main():
    open_window()


if __name__ == "__main__":
    main()
