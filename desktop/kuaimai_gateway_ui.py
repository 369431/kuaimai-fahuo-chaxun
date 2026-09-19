# -*- coding: utf-8 -*-
"""「对外访问设置」窗口：域名 / frp 隧道 / HTTPS 证书 / 一键启动。

对应原来安装向导里填的那几项（frp 服务器、端口、token、.crt+.key），
现在装完软件也能改、能看状态、能一键起隧道。
"""
import os
import threading
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import kuaimai_gateway as gw

BG = "#f2f2f7"
BLUE = "#0b5394"
GREEN = "#1B7F35"


def open_gateway_dialog(app):
    """app 需要有 .root（主窗口）。"""
    try:
        old = getattr(app, "_gw_win", None)
        if old is not None and old.winfo_exists():
            old.lift()
            old.focus_force()
            return old
    except Exception:
        pass
    d = GatewayDialog(app)
    app._gw_win = d.win
    return d.win


class GatewayDialog:
    def __init__(self, app):
        self.app = app
        self.cfg = gw.load_config()
        self._busy = False
        self._crt_path = ""
        self._key_path = ""

        win = tk.Toplevel(app.root)
        self.win = win
        win.title("对外访问设置（域名 / frp / 证书）")
        win.geometry("760x620")
        win.minsize(700, 560)
        try:
            win.configure(bg=BG)
        except Exception:
            pass

        head = tk.Frame(win, bg=BG)
        head.pack(fill=tk.X, padx=14, pady=(12, 2))
        tk.Label(head, text="对外访问设置", bg=BG, fg="#1d1d1f",
                 font=("Microsoft YaHei", 15, "bold")).pack(anchor="w")
        tk.Label(head, text="装完软件也能改：域名、frp 服务器/token、HTTPS 证书；改完点「保存并重启」就行。\n"
                            "（只有主客户端那台需要设；子客户端不用管）",
                 bg=BG, fg="#6e6e73", font=("Microsoft YaHei", 9), justify="left").pack(anchor="w")

        # ---- 状态 ----
        box = ttk.LabelFrame(win, text="当前状态", padding=8)
        box.pack(fill=tk.X, padx=14, pady=8)
        self.status_txt = tk.Label(box, text="正在检查…", bg=BG, fg=BLUE,
                                   font=("Microsoft YaHei", 9), justify="left", anchor="w", wraplength=690)
        self.status_txt.pack(fill=tk.X)
        srow = ttk.Frame(box)
        srow.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(srow, text="刷新状态", command=self.refresh).pack(side=tk.LEFT)
        ttk.Button(srow, text="打开证书文件夹", command=self._open_cert_dir).pack(side=tk.LEFT, padx=6)
        ttk.Button(srow, text="看中转日志", command=self._open_relay_log).pack(side=tk.LEFT)

        # ---- 表单 ----
        form = ttk.LabelFrame(win, text="配置", padding=10)
        form.pack(fill=tk.X, padx=14, pady=4)
        form.columnconfigure(1, weight=1)

        def row(r, label, var, hint="", width=None, show=None):
            ttk.Label(form, text=label).grid(row=r, column=0, sticky="w", pady=4)
            e = ttk.Entry(form, textvariable=var, font=("Consolas", 11), show=show)
            if width:
                e.configure(width=width)
            e.grid(row=r, column=1, sticky="ew", padx=8, pady=4)
            if hint:
                ttk.Label(form, text=hint, foreground="#6e6e73").grid(row=r, column=2, sticky="w")
            return e

        self.domain = tk.StringVar(value=self.cfg.get("domain") or "")
        self.server = tk.StringVar(value=self.cfg.get("server_addr") or gw.DEFAULT_SERVER)
        self.sport = tk.StringVar(value=str(self.cfg.get("server_port") or gw.DEFAULT_SERVER_PORT))
        self.token = tk.StringVar(value=self.cfg.get("token") or "")
        self.hport = tk.StringVar(value=str(self.cfg.get("https_port") or gw.DEFAULT_HTTPS_PORT))
        self.expose443 = tk.BooleanVar(value=bool(self.cfg.get("expose_443", True)))

        row(0, "域名", self.domain, "证书和访问地址都用它（例 kmcx.cc）")
        row(1, "frp 服务器地址", self.server, "客户机连的服务器（106.52.122.158）")
        row(2, "frp 服务器端口", self.sport, "默认 7000", width=8)
        row(3, "frp token", self.token, "和服务器 frps 上的一致", show="*")
        row(4, "对外 HTTPS 端口", self.hport, "默认 9443", width=8)
        ttk.Checkbutton(form, text="同时把 443 也映射到这台（手机上不用带端口）",
                        variable=self.expose443).grid(row=5, column=0, columnspan=3, sticky="w", pady=(4, 0))

        # ---- 证书 ----
        cert = ttk.LabelFrame(win, text="HTTPS 证书（手机开摄像头必须 https）", padding=10)
        cert.pack(fill=tk.X, padx=14, pady=4)
        self.cert_txt = tk.Label(cert, text="", bg=BG, fg="#6e6e73", font=("Microsoft YaHei", 9),
                                 justify="left", anchor="w", wraplength=690)
        self.cert_txt.pack(fill=tk.X)
        crow = ttk.Frame(cert)
        crow.pack(fill=tk.X, pady=(6, 0))
        ttk.Button(crow, text="选择 .crt 和 .key 并安装…", command=self._pick_cert).pack(side=tk.LEFT)
        self.cert_msg = tk.Label(crow, text="", bg=BG, fg="#6e6e73", font=("Microsoft YaHei", 9))
        self.cert_msg.pack(side=tk.LEFT, padx=8)

        # ---- 动作 ----
        bar = ttk.Frame(win, padding=(14, 4))
        bar.pack(fill=tk.X)
        ttk.Button(bar, text="保存配置", command=lambda: self._save(restart=False)).pack(side=tk.LEFT)
        ttk.Button(bar, text="保存并重启隧道", style="Accent.TButton",
                   command=lambda: self._save(restart=True)).pack(side=tk.LEFT, padx=6)
        ttk.Button(bar, text="只重启 HTTPS 中转", command=lambda: self._relay_restart()).pack(side=tk.LEFT)
        ttk.Button(bar, text="一键启动全部", command=self._start_all).pack(side=tk.LEFT, padx=6)

        bar2 = ttk.Frame(win, padding=(14, 0))
        bar2.pack(fill=tk.X)
        self.autostart = tk.BooleanVar(value=gw.has_autostart())
        ttk.Checkbutton(bar2, text="开机自动启动（程序 + frpc）", variable=self.autostart,
                        command=self._toggle_autostart).pack(side=tk.LEFT)
        ttk.Button(bar2, text="关闭", command=win.destroy).pack(side=tk.RIGHT)

        foot = tk.Frame(win, bg=BG)
        foot.pack(fill=tk.X, padx=14, pady=(6, 12))
        self.msg = tk.Label(foot, text="", bg=BG, fg="#d70015", font=("Microsoft YaHei", 9),
                            justify="left", anchor="w", wraplength=690)
        self.msg.pack(fill=tk.X)

        self.refresh()

    # ---------------- 工具 ----------------
    def _say(self, text, ok=True):
        try:
            self.msg.config(text=text, fg=GREEN if ok else "#d70015")
        except Exception:
            pass

    def _bg(self, fn, done=None):
        if self._busy:
            return
        self._busy = True

        def work():
            try:
                res = fn()
            except Exception as e:
                res = (False, str(e)[:150])
            def fin():
                self._busy = False
                if done:
                    done(res)
            try:
                self.win.after(0, fin)
            except Exception:
                pass

        threading.Thread(target=work, daemon=True).start()

    def _open_cert_dir(self):
        d = gw.paths()["cert_dir"]
        try:
            os.makedirs(d, exist_ok=True)
            os.startfile(d)
        except Exception as e:
            self._say("打不开证书目录：%s" % str(e)[:100], ok=False)

    def _open_relay_log(self):
        p = os.path.join(gw.paths()["https_dir"], "km_https.log")
        try:
            if not os.path.exists(p):
                self._say("还没有 km_https.log（中转没起过？）", ok=False)
                return
            os.startfile(p)
        except Exception as e:
            self._say("打不开日志：%s" % str(e)[:100], ok=False)

    # ---------------- 状态 ----------------
    def refresh(self):
        self.status_txt.config(text="正在检查…（端口 / 进程 / 证书）")

        def work():
            st = gw.status()
            return st

        def done(st):
            cfg = st.get("cfg") or {}
            cert = st.get("cert") or {}
            lines = []
            lines.append("对外地址：%s%s" % (st.get("url") or "（还没填域名）",
                                        "　← 子客户端/手机就填这个" if st.get("url") else ""))
            lines.append("本机服务：8790 %s　·　HTTPS 中转 %s %s　·　frpc %s"
                         % ("在听" if st.get("web_open") else "没在听",
                            int(cfg.get("https_port") or gw.DEFAULT_HTTPS_PORT),
                            "在听" if st.get("https_open") else "没在听",
                            "在跑" if st.get("frpc") else "没跑"))
            if cert:
                left = cert.get("days_left")
                left_txt = ("还有 %d 天" % left) if isinstance(left, int) else ""
                lines.append("证书：%s（到期 %s %s）　共 %d 份"
                             % (cert.get("domain"), cert.get("not_after") or "未知", left_txt,
                                st.get("cert_count") or 0))
                if isinstance(left, int) and left < 15:
                    lines.append("⚠ 证书快到期了：重新申请后在这里「选择 .crt 和 .key 并安装」换掉即可")
            else:
                lines.append("证书：还没有（手机摄像头扫码必须 https，先把证书装进来）")
            lines.append("frpc.toml：%s　·　开机自启：%s"
                         % ("有" if st.get("frpc_toml") else "没有",
                            "已开" if st.get("autostart") else "没开"))
            self.status_txt.config(text="\n".join(lines))
            self.cert_txt.config(text=("当前证书：%s（到期 %s）" % (cert.get("domain"), cert.get("not_after") or "未知"))
                                      if cert else "还没有证书")

        self._bg(work, done)

    # ---------------- 证书 ----------------
    def _pick_cert(self):
        files = filedialog.askopenfilenames(
            title="选证书 .crt 和私钥 .key（两个一起选）",
            filetypes=[("证书 / 私钥", "*.crt *.key *.pem"), ("所有文件", "*.*")])
        if not files:
            return
        crt = key = ""
        for f in files:
            low = str(f).lower()
            if low.endswith(".key") or low.endswith("_key.pem") or low.endswith("key.pem"):
                key = str(f)
            elif low.endswith(".crt") or low.endswith(".pem"):
                crt = crt or str(f)
        if not crt or not key:
            if len(files) == 1:
                self._say("要选两个文件：证书 .crt 和私钥 .key", ok=False)
                return
            crt, key = str(files[0]), str(files[1])
        dom = self.domain.get().strip()

        def work():
            return gw.install_cert(crt, key, dom)

        def done(res):
            ok, msg, domain = res
            if ok:
                self.cert_msg.config(text="✓ 已装证书", fg=GREEN)
                self.domain.set(domain)
                self._say("证书已装好：%s。接着点「保存并重启隧道」就会用新证书。" % msg)
                self.refresh()
            else:
                self.cert_msg.config(text="✗ 没装上", fg="#d70015")
                self._say(msg, ok=False)

        self._bg(work, done)

    # ---------------- 保存 / 启动 ----------------
    def _collect(self):
        cfg = gw.load_config()
        cfg["domain"] = self.domain.get().strip()
        cfg["server_addr"] = self.server.get().strip() or gw.DEFAULT_SERVER
        try:
            cfg["server_port"] = int(str(self.sport.get()).strip() or gw.DEFAULT_SERVER_PORT)
        except Exception:
            cfg["server_port"] = gw.DEFAULT_SERVER_PORT
        cfg["token"] = self.token.get().strip()
        try:
            cfg["https_port"] = int(str(self.hport.get()).strip() or gw.DEFAULT_HTTPS_PORT)
        except Exception:
            cfg["https_port"] = gw.DEFAULT_HTTPS_PORT
        cfg["expose_443"] = bool(self.expose443.get())
        return cfg

    def _save(self, restart=True):
        cfg = self._collect()
        if not cfg.get("token"):
            if not messagebox.askyesno("还没填 frp token",
                                       "没填 frp token 的话隧道连不上。\n还是要保存吗？", parent=self.win):
                return
        ok, msg = gw.save_config(cfg)
        if not ok:
            self._say("保存失败：%s" % msg, ok=False)
            return
        ok2, msg2 = gw.write_frpc_toml(cfg)
        if not ok2:
            self._say("配置存了，但 frpc.toml 没写成：%s" % msg2, ok=False)
            return
        self._say("已保存。frpc.toml 也重写好了。")

        def work():
            out = []
            if restart:
                if gw.proc_running("frpc.exe") or gw.task_state(gw.TASK_FRPC):
                    okf, msgf = gw.start_frpc()
                    out.append(("隧道已重启" if okf else "隧道没起来：%s" % msgf))
                okr, msgr = gw.start_relay(cfg)
                out.append(("HTTPS 中转已重启" if okr else "HTTPS 中转：%s" % msgr))
            return out

        def done(out):
            if out:
                self._say("　·　".join(out), ok=all("没" not in x for x in out))
            self.refresh()

        if restart:
            self._bg(work, done)

    def _relay_restart(self):
        cfg = self._collect()
        gw.save_config(cfg)
        gw.write_frpc_toml(cfg)

        def work():
            return [gw.start_relay(cfg)]

        def done(res):
            (ok, msg), = res
            self._say("HTTPS 中转已重启。" if ok else "HTTPS 中转没起来：%s" % msg, ok=ok)
            self.refresh()

        self._bg(work, done)

    def _start_all(self):
        cfg = self._collect()
        ok, msg = gw.save_config(cfg)
        if ok:
            gw.write_frpc_toml(cfg)

        def work():
            out = []
            okf, msgf = gw.start_frpc()
            out.append(("frpc 在跑" if okf else "frpc：%s" % msgf))
            okr, msgr = gw.start_relay(cfg)
            out.append(("HTTPS 中转在听 %d" % int(cfg.get("https_port") or gw.DEFAULT_HTTPS_PORT)
                        if okr else "HTTPS 中转：%s" % msgr))
            return out

        def done(out):
            self._say("　·　".join(out))
            self.refresh()

        self._bg(work, done)

    def _toggle_autostart(self):
        want = bool(self.autostart.get())

        def work():
            return gw.set_autostart(want)

        def done(res):
            ok, msg = res if isinstance(res, tuple) else (True, "")
            if ok:
                self._say("开机自启已%s" % ("打开" if want else "关闭"))
            else:
                self.autostart.set(gw.has_autostart())
                self._say("改开机自启失败：%s" % (msg or "")[:150], ok=False)

        self._bg(work, done)
