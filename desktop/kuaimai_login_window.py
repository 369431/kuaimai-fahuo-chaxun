# -*- coding: utf-8 -*-
"""桌面端登录窗：一个窗口两种身份。

· 本机（主客户端）：本机跑服务、有数据；没有管理员账号时就在这里做「首次设置」
· 子客户端：连局域网里的主客户端，账号/权限/数据都在主端，本机不放快麦凭据

用法（在主程序里）：
    sess = ask_login(root, ensure_server)
    if not sess: 退出
"""
import threading
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

import kuaimai_client as kmc
import kuaimai_uikit as uikit

try:
    import kuaimai_update as kmupd          # 检查更新
except Exception:
    kmupd = None
try:
    import kuaimai_update_ui as kmupdui
except Exception:
    kmupdui = None

BG = "#f2f2f7"
BLUE = "#0b5394"


class LoginWindow:
    def __init__(self, parent, ensure_server, default_port=kmc.DEFAULT_PORT):
        self.parent = parent
        self.ensure_server = ensure_server
        self.default_port = int(default_port or kmc.DEFAULT_PORT)
        self.session = None
        self.cfg = kmc.load_config()
        self._busy = False
        self._found = []

        win = tk.Toplevel(parent)
        self.win = win
        win.title("快麦扫码查询 %s · 登录" % kmc.APP_VER)
        win.geometry("580x720")
        win.minsize(560, 660)
        win.resizable(True, True)
        try:
            win.configure(bg=BG)
        except Exception:
            pass
        # 注意：**不能** win.transient(parent)。
        # main() 里 root 是 withdraw 的，而 Tk 的规则是「owner 不可见 → 子窗口也不显示」，
        # 一 transient 就永远看不到登录窗（进程在跑、屏幕上一个窗口都没有）。
        try:
            win.deiconify()
            win.lift()
        except Exception:
            pass

        head = tk.Frame(win, bg=BG)
        head.pack(fill=tk.X, padx=16, pady=(14, 4))
        tk.Label(head, text="快麦发货查询 %s" % kmc.APP_VER, bg=BG, fg="#1d1d1f",
                 font=("Microsoft YaHei", 17, "bold")).pack(anchor="w")
        self.sub = tk.Label(head, text="登录后才能看到数据：管理员账号 = 主客户端，其它账号 = 子客户端",
                            bg=BG, fg="#6e6e73", font=("Microsoft YaHei", 9))
        self.sub.pack(anchor="w", pady=(2, 0))

        # 先把底部两栏占好位置（side=BOTTOM），再用 Notebook 填剩下空间：
        # 这样无论标签页内容多高，「登录/退出」都不会被挤出可视区。
        bar = tk.Frame(win, bg=BG)
        bar.pack(side=tk.BOTTOM, fill=tk.X, padx=16, pady=(0, 12))
        ttk.Button(bar, text="检查更新", command=self._check_update).pack(side=tk.LEFT)
        ttk.Button(bar, text="退出", command=self._cancel).pack(side=tk.RIGHT)
        self.login_btn = ttk.Button(bar, text="登  录", style="Accent.TButton", command=self._submit)
        self.login_btn.pack(side=tk.RIGHT, padx=8)

        foot = tk.Frame(win, bg=BG)
        foot.pack(side=tk.BOTTOM, fill=tk.X, padx=16, pady=(0, 4))
        self.msg = tk.Label(foot, text="", bg=BG, fg="#d70015", font=("Microsoft YaHei", 9),
                            wraplength=520, justify="left")
        self.msg.pack(anchor="w")
        self.memo = tk.BooleanVar(value=bool(self.cfg.get("remember", True)))
        ttk.Checkbutton(foot, text="记住账号与本机设置（不记密码）",
                        variable=self.memo).pack(anchor="w", pady=(4, 0))

        self.nb = ttk.Notebook(win)
        self.nb.pack(fill=tk.BOTH, expand=True, padx=16, pady=8)
        self.tab_host = ttk.Frame(self.nb, padding=12)
        self.tab_remote = ttk.Frame(self.nb, padding=12)
        self.nb.add(self.tab_host, text="  本机登录（这台就是主客户端）  ")
        self.nb.add(self.tab_remote, text="  子客户端（连别的主客户端）  ")

        self._build_host(self.tab_host)
        self._build_remote(self.tab_remote)

        win.protocol("WM_DELETE_WINDOW", self._cancel)
        win.bind("<Return>", lambda e: self._submit())
        win.bind("<Escape>", lambda e: self._cancel())
        try:
            win.grab_set()
        except Exception:
            pass

        mode = str(self.cfg.get("mode") or "host")
        self.nb.select(self.tab_remote if mode == "remote" else self.tab_host)
        self.nb.bind("<<NotebookTabChanged>>", lambda e: self._on_tab())
        self._on_tab()
        win.after(120, self._focus_entry)
        win.after(3000, lambda: self._check_update(silent=True))   # 登录前也悄悄查一次更新
        self._upd_info = None
        try:
            uikit.start(win)          # 让后台线程能安全地把结果交回界面
        except Exception:
            pass

    def _check_update(self, silent=False):
        """拉 version.json：silent=True 时只在窗口里提示，不弹窗。"""
        if kmupd is None or kmupdui is None:
            if not silent:
                messagebox.showwarning("检查更新", "缺少更新模块（kuaimai_update*.py）", parent=self.win)
            return
        if (not silent) and self._upd_info and self._upd_info.get("has_update"):
            kmupdui.ask_update(self.win, self._upd_info, kmc.APP_VER)
            return
        if not silent:
            self._set_msg("正在检查更新…", ok=True)

        def done(info):
            self._upd_info = info
            if not info.get("ok"):
                if not silent:
                    messagebox.showwarning("检查更新", str(info.get("error") or "检查失败"), parent=self.win)
                return
            if not info.get("has_update"):
                if not silent:
                    messagebox.showinfo("检查更新", "已经是最新版 %s" % kmc.APP_VER, parent=self.win)
                return
            self._set_msg("发现新版本 %s → 点「检查更新」下载" % info.get("latest"), ok=True)
            if not silent:
                kmupdui.ask_update(self.win, info, kmc.APP_VER)

        kmupdui.check_in_background(self.win, kmc.APP_VER, done)

    # ---------------- 本机（主客户端） ----------------
    def _build_host(self, f):
        self.host_info = tk.Label(f, text="正在检查本机服务…", fg=BLUE, bg=BG,
                                  font=("Microsoft YaHei", 9), wraplength=440, justify="left")
        self.host_info.pack(anchor="w", pady=(0, 8))
        ttk.Label(f, text="账号").pack(anchor="w")
        self.host_name = tk.StringVar(value=str(self.cfg.get("host_name") or ""))
        self.host_name_ent = ttk.Entry(f, textvariable=self.host_name, font=("Microsoft YaHei", 11))
        self.host_name_ent.pack(fill=tk.X, pady=(2, 8))
        ttk.Label(f, text="密码").pack(anchor="w")
        self.host_pw = tk.StringVar()
        self.host_pw_ent = ttk.Entry(f, textvariable=self.host_pw, show="*", font=("Microsoft YaHei", 11))
        self.host_pw_ent.pack(fill=tk.X, pady=(2, 8))
        self.host_pw2 = tk.StringVar()
        self.host_pw2_lbl = ttk.Label(f, text="再输一次密码（首次设置）")
        self.host_pw2_ent = ttk.Entry(f, textvariable=self.host_pw2, show="*", font=("Microsoft YaHei", 11))
        self.host_hint = tk.Label(
            f, text="本机就是主客户端：数据、快麦凭据都在这台电脑上。\n"
                    "第一次用请先创建管理员账号（也只能在这台电脑上创建）。",
            bg=BG, fg="#6e6e73", font=("Microsoft YaHei", 9), justify="left", wraplength=440)
        self.host_hint.pack(anchor="w", pady=(6, 0))
        ttk.Button(f, text="忘了管理员密码？只能在本机重置",
                   command=self._reset_admin).pack(anchor="w", pady=(6, 0))
        self.host_need_setup = False

    def _reset_admin(self):
        """本机才能重置管理员密码（服务端也会再查一次是不是本机请求）。"""
        base = self._host_base()
        name = simpledialog.askstring("重置管理员密码", "本机数据库里的管理员账号名：", parent=self.win)
        if not name:
            return
        pw = simpledialog.askstring("重置管理员密码", "新密码（至少 4 位）：", parent=self.win, show="*")
        if not pw:
            return
        if len(str(pw)) < 4:
            self._set_msg("密码至少 4 位")
            return
        sess, err = kmc.setup(base, str(name).strip(), pw)
        if not sess:
            self._set_msg(err or "重置失败")
            return
        self.session = sess
        self._finish(sess, "", "host", base, str(name).strip())

    def _host_base(self):
        port = int(self.cfg.get("port") or self.default_port)
        return "http://127.0.0.1:%d" % port

    def _check_host(self):
        """启动/复用本机服务，并看是不是要首次设置。"""
        port = None
        try:
            port = int(self.ensure_server() or self.default_port)
        except Exception as e:
            self.host_info.config(text="本机服务启动失败：%s" % str(e)[:120])
            self._set_msg("本机服务启动失败：%s（检查 8790 端口是不是被别的程序占了）" % str(e)[:80])
            return
        self.cfg["port"] = port
        base = self._host_base()

        def work():
            ok, st = kmc.server_state(base)
            uikit.post(self.win, self._apply_host_state, ok, st, base)

        threading.Thread(target=work, daemon=True).start()

    def _apply_host_state(self, ok, st, base):
        if not ok:
            self.host_info.config(text="本机服务没起来：%s" % kmc.human_err(st, base))
            return
        need = bool(st.get("need_setup"))
        self.host_need_setup = need
        if need:
            self.host_info.config(text="本机服务：%s（还没有管理员账号 → 请创建）" % base)
            self.host_pw2_lbl.pack(anchor="w")
            self.host_pw2_ent.pack(fill=tk.X, pady=(2, 8))
            self.login_btn.config(text="创建管理员并登录")
            self.host_hint.config(text="这是本机（主客户端）第一次运行。\n"
                                       "创建的这个账号就是管理员（主账号），它能看到和管理所有子客户端。")
        else:
            self.host_info.config(text="本机服务：%s（已设置管理员）" % base)
            self.host_pw2_lbl.pack_forget()
            self.host_pw2_ent.pack_forget()
            self.login_btn.config(text="登  录")
            users = st.get("users") or []
            who = "、".join(str(u.get("name")) for u in users if u.get("name")) or "（不列给未登录的人）"
            self.host_hint.config(text="本机就是主客户端。\n提示：管理员账号 %s" % who)

    # ---------------- 子客户端 ----------------
    def _build_remote(self, f):
        self.remote_info = tk.Label(
            f, text="填主客户端地址：局域网可以是 192.168.1.5；外网/跨网就走客户那套 "
                    "https://域名:9443（frp 转发到主客户端）",
            fg=BLUE, bg=BG, font=("Microsoft YaHei", 9), wraplength=440, justify="left")
        self.remote_info.pack(anchor="w", pady=(0, 8))

        row = ttk.Frame(f)
        row.pack(fill=tk.X)
        ttk.Label(row, text="主客户端地址").pack(side=tk.LEFT)
        self.remote_addr = tk.StringVar(value=str(self.cfg.get("remote_addr") or ""))
        self.remote_addr_ent = ttk.Entry(row, textvariable=self.remote_addr, font=("Consolas", 11))
        self.remote_addr_ent.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        self.btn_find = ttk.Button(row, text="自动发现", command=self._discover)
        self.btn_find.pack(side=tk.LEFT)

        row2 = ttk.Frame(f)
        row2.pack(fill=tk.X, pady=(4, 8))
        ttk.Label(row2, text="发现结果").pack(side=tk.LEFT)
        self.found_var = tk.StringVar()
        self.found_box = ttk.Combobox(row2, textvariable=self.found_var, state="readonly",
                                      values=[], font=("Microsoft YaHei", 9))
        self.found_box.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        self.found_box.bind("<<ComboboxSelected>>", lambda e: self._pick_found())
        self.btn_test = ttk.Button(row2, text="测试连接", command=self._test_remote)
        self.btn_test.pack(side=tk.LEFT)

        ttk.Label(f, text="账号").pack(anchor="w")
        self.remote_name = tk.StringVar(value=str(self.cfg.get("remote_name") or ""))
        self.remote_name_ent = ttk.Entry(f, textvariable=self.remote_name, font=("Microsoft YaHei", 11))
        self.remote_name_ent.pack(fill=tk.X, pady=(2, 8))
        ttk.Label(f, text="密码").pack(anchor="w")
        self.remote_pw = tk.StringVar()
        self.remote_pw_ent = ttk.Entry(f, textvariable=self.remote_pw, show="*", font=("Microsoft YaHei", 11))
        self.remote_pw_ent.pack(fill=tk.X, pady=(2, 6))
        self.insecure = tk.BooleanVar(value=bool(self.cfg.get("tls_insecure")))
        ttk.Checkbutton(f, text="跳过证书校验（自签证书 / 用 IP 直连 https 时勾）",
                        variable=self.insecure).pack(anchor="w", pady=(0, 6))
        tk.Label(f, text="子客户端只显示主账号给你开的按钮；数据实时来自主客户端。\n"
                         "被主账号踢下线后，这台电脑 10 分钟内不能再登录。",
                 bg=BG, fg="#6e6e73", font=("Microsoft YaHei", 9), justify="left",
                 wraplength=440).pack(anchor="w", pady=(6, 0))

    def _pick_found(self):
        try:
            i = self.found_box.current()
            if 0 <= i < len(self._found):
                it = self._found[i]
                self.remote_addr.set("%s:%d" % (it["host"], it["port"]))
        except Exception:
            pass

    def _discover(self):
        if self._busy:
            return
        self._set_msg("正在局域网里找主客户端…", ok=True)
        self.btn_find.config(state=tk.DISABLED)

        def work():
            try:
                found = kmc.discover()
            except Exception as e:
                found = []
                uikit.post(self.win, self._set_msg, "自动发现失败：%s" % str(e)[:80], False)
            uikit.post(self.win, self._apply_found, found)

        threading.Thread(target=work, daemon=True).start()

    def _apply_found(self, found):
        self._found = list(found or [])
        try:
            self.btn_find.config(state=tk.NORMAL)
        except Exception:
            pass
        vals = []
        for it in self._found:
            tag = "（没设管理员）" if it.get("need_setup") else ("（%s 已登录）" % it["user"] if it.get("logged_in") and it.get("user") else "")
            vals.append("%s%s — %s:%d" % (it["name"], tag, it["host"], it["port"]))
        try:
            self.found_box.configure(values=vals)
        except Exception:
            pass
        if not self._found:
            self._set_msg("没发现主客户端。确认那台电脑开着程序、登录了管理员账号，"
                          "并且和这台在同一个局域网（也可以手动填地址）。")
            return
        if len(self._found) == 1:
            self.found_box.current(0)
            self._pick_found()
        self._set_msg("发现 %d 个主客户端，选一个再点「测试连接」" % len(self._found), ok=True)

    def _test_remote(self):
        base = kmc.norm_base(self.remote_addr.get())
        if not base:
            self._set_msg("先填主客户端地址，例如 192.168.1.5 或 https://域名:9443")
            return
        kmc.set_insecure(bool(self.insecure.get()))
        self._set_msg("正在连接 %s …" % base, ok=True)

        def work():
            ok, st = kmc.server_state(base)
            uikit.post(self.win, self._apply_test, ok, st, base)

        threading.Thread(target=work, daemon=True).start()

    def _apply_test(self, ok, st, base):
        if not ok:
            self._set_msg("连不上：%s" % kmc.human_err(st, base))
            return
        if st.get("need_setup"):
            self._set_msg("连上了 %s，但那台还没设置管理员账号 → 请先在那台电脑上设置" % base)
            return
        user = str(st.get("user") or "")
        who = ("已登录的账号：%s" % user) if user else "还没有人登录"
        self._set_msg("✓ 连上主客户端 %s（%s）。填账号密码登录即可。" % (base, who), ok=True)

    # ---------------- 公共 ----------------
    def _on_tab(self):
        if self._busy:
            return
        if self.nb.index(self.nb.select()) == 0:
            self._check_host()
        else:
            has_saved = bool(self.cfg.get("remote_addr"))
            if not self._found and not has_saved:
                pass

    def _focus_entry(self):
        try:
            ent = self.host_name_ent if self.nb.index(self.nb.select()) == 0 else self.remote_addr_ent
            ent.focus_set()
        except Exception:
            pass

    def _set_msg(self, text, ok=False):
        try:
            self.msg.config(text=text, fg="#1B7F35" if ok else "#d70015")
        except Exception:
            pass

    def _submit(self):
        if self._busy:
            return
        host_mode = self.nb.index(self.nb.select()) == 0
        if host_mode:
            name = self.host_name.get().strip()
            pw = self.host_pw.get()
            pw2 = self.host_pw2.get()
            if self.host_need_setup and pw != pw2:
                self._set_msg("两次输入的密码不一样")
                return
            base = self._host_base()
            mode = "host"
        else:
            name = self.remote_name.get().strip()
            pw = self.remote_pw.get()
            base = kmc.norm_base(self.remote_addr.get())
            mode = "remote"
            if not base:
                self._set_msg("请先填主客户端地址（或点「自动发现」）")
                return
            kmc.set_insecure(bool(self.insecure.get()))
        if not name or not pw:
            self._set_msg("账号和密码都要填")
            return
        self._busy = True
        self.login_btn.config(state=tk.DISABLED)
        self._set_msg("正在登录…", ok=True)

        def work():
            try:
                if mode == "host" and self.host_need_setup:
                    sess, err = kmc.setup(base, name, pw)
                else:
                    sess, err = kmc.login(base, name, pw, mode=mode)
            except Exception as e:
                sess, err = None, str(e)[:150]
            uikit.post(self.win, self._finish, sess, err, mode, base, name)

        threading.Thread(target=work, daemon=True).start()

    def _finish(self, sess, err, mode, base, name):
        self._busy = False
        try:
            self.login_btn.config(state=tk.NORMAL)
        except Exception:
            pass
        if not sess:
            self._set_msg(err or "登录失败")
            return
        sess._port = int(self.cfg.get("port") or self.default_port)
        self.session = sess
        if self.memo.get():
            cfg = {"remember": True, "mode": mode}
            if mode == "host":
                cfg["host_name"] = name
            else:
                cfg["remote_addr"] = self.remote_addr.get().strip()
                cfg["remote_name"] = name
            kmc.save_config(cfg)
        try:
            self.win.grab_release()
        except Exception:
            pass
        self.win.destroy()

    def _cancel(self):
        self.session = None
        try:
            self.win.grab_release()
        except Exception:
            pass
        self.win.destroy()


def ask_login(parent, ensure_server, default_port=kmc.DEFAULT_PORT):
    """弹登录窗（阻塞），返回 Session 或 None（用户退出）。"""
    w = LoginWindow(parent, ensure_server, default_port)
    try:
        parent.wait_window(w.win)
    except Exception:
        pass
    return w.session
