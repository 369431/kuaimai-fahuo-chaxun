# -*- coding: utf-8 -*-
"""主账号的「子客户端管理」面板：在线设备 / 账号 / 权限。

主客户端上直接管本机；子客户端上用它管主端的账号（接口和网页端 /perms、/api/users 同一套）。
只有管理员（role=admin）能打开。
"""
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog

BG = "#f2f2f7"
BLUE = "#0b5394"

ROLE_TXT = {"admin": "管理员（主账号）", "user": "子账号"}


def open_admin_panel(app):
    """app 需要有 .root 和 .session（kuaimai_client.Session）。"""
    try:
        old = getattr(app, "_admin_win", None)
        if old is not None and old.winfo_exists():
            old.lift()
            old.focus_force()
            return old
    except Exception:
        pass
    w = AdminPanel(app)
    app._admin_win = w.win
    return w.win


class AdminPanel:
    def __init__(self, app):
        self.app = app
        self.s = app.session
        self.win = tk.Toplevel(app.root)
        self.win.title("子客户端管理")
        self.win.geometry("1000x640")
        try:
            self.win.configure(bg=BG)
        except Exception:
            pass
        head = tk.Frame(self.win, bg=BG)
        head.pack(fill=tk.X, padx=12, pady=(10, 2))
        tk.Label(head, text="子客户端管理", bg=BG, fg="#1d1d1f",
                 font=("Microsoft YaHei", 15, "bold")).pack(anchor="w")
        tk.Label(head, text="登录身份：%s　·　%s" % (self.s.name, self.s.label()),
                 bg=BG, fg="#6e6e73", font=("Microsoft YaHei", 9)).pack(anchor="w")
        self.nb = ttk.Notebook(self.win)
        self.nb.pack(fill=tk.BOTH, expand=True, padx=12, pady=8)
        self.tab_dev = ttk.Frame(self.nb, padding=10)
        self.tab_acc = ttk.Frame(self.nb, padding=10)
        self.tab_perm = ttk.Frame(self.nb, padding=10)
        self.nb.add(self.tab_dev, text="  在线设备  ")
        self.nb.add(self.tab_acc, text="  账号  ")
        self.nb.add(self.tab_perm, text="  权限  ")
        self._build_devices()
        self._build_accounts()
        self._build_perms()
        bar = ttk.Frame(self.win, padding=(12, 0, 12, 10))
        bar.pack(fill=tk.X)
        self.msg = tk.Label(bar, text="", bg=BG, fg="#6e6e73", font=("Microsoft YaHei", 9))
        self.msg.pack(side=tk.LEFT)
        ttk.Button(bar, text="关闭", command=self.win.destroy).pack(side=tk.RIGHT)
        self.refresh_devices()
        self.refresh_accounts()
        self.refresh_perms()

    # ---------------- 通用 ----------------
    def _say(self, text, ok=True):
        try:
            self.msg.config(text=text, fg="#1B7F35" if ok else "#d70015")
        except Exception:
            pass

    def _ask(self, path, method="GET", body=None, params=None):
        ok, res = self.s.api(path, method, body=body, params=params, timeout=25)
        if not ok:
            err = (res or {}).get("error") if isinstance(res, dict) else ""
            if getattr(self.s, "kicked", False):
                self._say("已被主账号踢下线，请重新登录", ok=False)
            else:
                self._say(str(err or "请求失败")[:120], ok=False)
            return None
        return res

    # ---------------- 在线设备 ----------------
    def _build_devices(self):
        t = self.tab_dev
        bar = ttk.Frame(t)
        bar.pack(fill=tk.X, pady=(0, 6))
        ttk.Button(bar, text="刷新", command=self.refresh_devices).pack(side=tk.LEFT)
        ttk.Button(bar, text="踢下线", command=self._kick_selected_device).pack(side=tk.LEFT, padx=6)
        self.dev_info = tk.Label(bar, text="", bg=BG, fg=BLUE, font=("Microsoft YaHei", 9))
        self.dev_info.pack(side=tk.LEFT, padx=8)
        cols = ("name", "role", "pc", "win_user", "ip", "kind", "login", "seen", "alive")
        heads = (("name", "账号", 110), ("role", "角色", 110), ("pc", "电脑名", 150),
                 ("win_user", "Windows 用户", 110), ("ip", "来源 IP", 115),
                 ("kind", "客户端", 80), ("login", "登录时间", 150), ("seen", "最后活跃", 150),
                 ("alive", "状态", 70))
        self.dev_tree = ttk.Treeview(t, columns=cols, show="headings", height=16)
        for c, txt, w in heads:
            self.dev_tree.heading(c, text=txt)
            self.dev_tree.column(c, width=w, anchor="center")
        self.dev_tree.tag_configure("on", background="#d7f5e0")
        self.dev_tree.pack(fill=tk.BOTH, expand=True)
        tk.Label(t, text="「状态」按 3 分钟内有心跳算在线。踢下线后那台设备 10 分钟内不能再登录。",
                 bg=BG, fg="#6e6e73", font=("Microsoft YaHei", 9)).pack(anchor="w", pady=(4, 0))

    def refresh_devices(self):
        res = self._ask("/api/devices")
        if res is None:
            return
        try:
            self.dev_tree.delete(*self.dev_tree.get_children())
        except Exception:
            return
        host = res.get("host") or {}
        rows = res.get("devices") or []
        if host:
            self.dev_tree.insert("", tk.END, values=(
                host.get("name") or "本机", "主机（本机）", host.get("pc") or "-",
                host.get("win_user") or "-", "127.0.0.1", "主客户端",
                host.get("login") or "-", "正在用", "在线"), tags=("on",))
        for d in rows:
            self.dev_tree.insert("", tk.END, values=(
                d.get("name"), ROLE_TXT.get(d.get("role"), d.get("role")),
                d.get("pc") or "-", d.get("win_user") or "-", d.get("ip") or "-",
                "桌面端" if d.get("kind") == "desktop" else (d.get("kind") or "网页"),
                d.get("last_login") or "-", d.get("seen_at") or "-",
                "在线" if d.get("alive") else ("已登录" if d.get("online") else "离线")),
                tags=("on",) if d.get("alive") else ())
        self.dev_info.config(text="共 %d 条登录记录（含本机）" % (len(rows) + (1 if host else 0)))

    def _kick_selected_device(self):
        sel = self.dev_tree.selection()
        if not sel:
            messagebox.showinfo("提示", "先在列表里选一行", parent=self.win)
            return
        name = str(self.dev_tree.item(sel[0], "values")[0])
        role = str(self.dev_tree.item(sel[0], "values")[1])
        if "主机" in role:
            messagebox.showinfo("提示", "本机就是主客户端，不用踢自己", parent=self.win)
            return
        if not messagebox.askyesno("确认", "把「%s」踢下线？\n那台设备 10 分钟内不能再登录。" % name,
                                   parent=self.win):
            return
        if self._ask("/api/users", "POST", body={"action": "kick", "name": name}) is not None:
            self._say("已踢下线：%s" % name)
            self.refresh_devices()
            self.refresh_accounts()

    # ---------------- 账号 ----------------
    def _build_accounts(self):
        t = self.tab_acc
        bar = ttk.Frame(t)
        bar.pack(fill=tk.X, pady=(0, 6))
        ttk.Button(bar, text="刷新", command=self.refresh_accounts).pack(side=tk.LEFT)
        ttk.Button(bar, text="新增子账号", command=self._add_account).pack(side=tk.LEFT, padx=6)
        ttk.Button(bar, text="改密码", command=self._passwd_account).pack(side=tk.LEFT)
        ttk.Button(bar, text="删除", command=self._del_account).pack(side=tk.LEFT, padx=6)
        ttk.Button(bar, text="踢下线", command=self._kick_account).pack(side=tk.LEFT)
        self.acc_info = tk.Label(bar, text="", bg=BG, fg=BLUE, font=("Microsoft YaHei", 9))
        self.acc_info.pack(side=tk.LEFT, padx=8)
        cols = ("name", "role", "online", "device", "pc", "win_user", "ip", "last", "created")
        heads = (("name", "账号", 110), ("role", "角色", 110), ("online", "在线", 60),
                 ("device", "登录设备", 190), ("pc", "电脑名", 130), ("win_user", "Windows 用户", 100),
                 ("ip", "来源 IP", 110), ("last", "最后登录", 150), ("created", "创建时间", 150))
        self.acc_tree = ttk.Treeview(t, columns=cols, show="headings", height=16)
        for c, txt, w in heads:
            self.acc_tree.heading(c, text=txt)
            self.acc_tree.column(c, width=w, anchor="center")
        self.acc_tree.pack(fill=tk.BOTH, expand=True)
        tk.Label(t, text="同一账号同时只能在一处登录：新登录会把旧设备顶下线。",
                 bg=BG, fg="#6e6e73", font=("Microsoft YaHei", 9)).pack(anchor="w", pady=(4, 0))

    def refresh_accounts(self):
        res = self._ask("/api/users", "POST", body={"action": "list"})
        if res is None:
            return
        try:
            self.acc_tree.delete(*self.acc_tree.get_children())
        except Exception:
            return
        for u in res.get("users") or []:
            self.acc_tree.insert("", tk.END, values=(
                u.get("name"), ROLE_TXT.get(u.get("role"), u.get("role")),
                "是" if u.get("online") else "否", u.get("device") or "-",
                u.get("pc") or "-", u.get("win_user") or "-", u.get("ip") or "-",
                u.get("last_login") or "-", u.get("created") or "-"))
        self.acc_info.config(text="共 %d 个账号（主账号 %d 个）"
                             % (len(res.get("users") or []),
                                sum(1 for u in (res.get("users") or []) if u.get("role") == "admin")))

    def _sel_account(self, need=True):
        sel = self.acc_tree.selection()
        if not sel:
            if need:
                messagebox.showinfo("提示", "先在列表里选一个账号", parent=self.win)
            return None
        return str(self.acc_tree.item(sel[0], "values")[0])

    def _add_account(self):
        name = simpledialog.askstring("新增子账号", "账号名（子账号，权限随后在「权限」页勾选）",
                                      parent=self.win)
        if not name:
            return
        pw = simpledialog.askstring("新增子账号", "密码（至少 4 位）", parent=self.win, show="*")
        if not pw:
            return
        res = self._ask("/api/users", "POST", body={"action": "add", "name": name.strip(),
                                                   "pw": pw, "role": "user"})
        if res is not None:
            self._say("已新增：%s（默认只给查询类权限）" % name.strip())
            self.refresh_accounts()
            self.refresh_perms()

    def _passwd_account(self):
        name = self._sel_account()
        if not name:
            return
        pw = simpledialog.askstring("改密码", "给「%s」设新密码（至少 4 位）" % name,
                                    parent=self.win, show="*")
        if not pw:
            return
        res = self._ask("/api/users", "POST", body={"action": "passwd", "name": name, "pw": pw})
        if res is not None:
            self._say("已改密码：%s（该账号旧登录已失效，那台设备 10 分钟内不能再登录）" % name)
            self.refresh_accounts()

    def _del_account(self):
        name = self._sel_account()
        if not name:
            return
        if not messagebox.askyesno("确认", "删除账号「%s」？" % name, parent=self.win):
            return
        res = self._ask("/api/users", "POST", body={"action": "del", "name": name})
        if res is not None:
            self._say("已删除：%s" % name)
            self.refresh_accounts()
            self.refresh_perms()

    def _kick_account(self):
        name = self._sel_account()
        if not name:
            return
        res = self._ask("/api/users", "POST", body={"action": "kick", "name": name})
        if res is not None:
            self._say("已踢下线：%s" % name)
            self.refresh_accounts()

    # ---------------- 权限 ----------------
    def _build_perms(self):
        t = self.tab_perm
        bar = ttk.Frame(t)
        bar.pack(fill=tk.X, pady=(0, 8))
        ttk.Label(bar, text="子账号").pack(side=tk.LEFT)
        self.perm_user = tk.StringVar()
        self.perm_box = ttk.Combobox(bar, textvariable=self.perm_user, width=20, state="readonly")
        self.perm_box.pack(side=tk.LEFT, padx=6)
        self.perm_box.bind("<<ComboboxSelected>>", lambda e: self._load_user_perms())
        ttk.Button(bar, text="保存权限", command=self._save_perms).pack(side=tk.LEFT, padx=6)
        ttk.Button(bar, text="全不选", command=lambda: self._set_all(False)).pack(side=tk.LEFT)
        ttk.Button(bar, text="全选", command=lambda: self._set_all(True)).pack(side=tk.LEFT, padx=4)
        ttk.Button(bar, text="恢复默认", command=self._restore_defaults).pack(side=tk.LEFT)
        ttk.Button(bar, text="刷新", command=self.refresh_perms).pack(side=tk.LEFT, padx=6)

        self.perm_info = tk.Label(t, text="", bg=BG, fg=BLUE, font=("Microsoft YaHei", 9))
        self.perm_info.pack(anchor="w", pady=(0, 6))

        self.perm_canvas = tk.Canvas(t, highlightthickness=0, bg=BG)
        vsb = ttk.Scrollbar(t, orient="vertical", command=self.perm_canvas.yview)
        self.perm_canvas.configure(yscrollcommand=vsb.set)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)
        self.perm_canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.perm_holder = ttk.Frame(self.perm_canvas)
        self.perm_canvas.create_window((0, 0), window=self.perm_holder, anchor="nw")
        self.perm_holder.bind("<Configure>",
                              lambda e: self.perm_canvas.configure(scrollregion=self.perm_canvas.bbox("all")))
        self.perm_vars = {}          # 键 → BooleanVar
        self.perm_keys = []
        self._perm_users = {}

    def refresh_perms(self):
        res = self._ask("/api/perms")
        if res is None:
            return
        users = res.get("users") or []
        self._perm_users = {u.get("name"): u for u in users if u.get("name")}
        subs = [u.get("name") for u in users if u.get("name") and u.get("role") != "admin"]
        try:
            self.perm_box.configure(values=subs)
        except Exception:
            pass
        cur = self.perm_user.get()
        if cur not in subs:
            self.perm_user.set(subs[0] if subs else "")
        # 勾选矩阵（按分组排）
        for ch in list(self.perm_holder.children.values()):
            ch.destroy()
        self.perm_vars = {}
        self.perm_keys = []
        groups = res.get("groups") or []
        if not groups:
            groups = [{"name": "权限", "keys": [c.get("key") for c in (res.get("catalog") or [])]}]
        labels = {c.get("key"): c.get("label") for c in (res.get("catalog") or [])}
        defaults = {c.get("key"): bool(c.get("default")) for c in (res.get("catalog") or [])}
        self._perm_defaults = defaults
        if not subs:
            ttk.Label(self.perm_holder, text="还没有子账号。先到「账号」页新增一个。",
                      font=("Microsoft YaHei", 10)).grid(row=0, column=0, sticky="w", padx=4, pady=6)
        for r, g in enumerate(groups):
            box = ttk.LabelFrame(self.perm_holder, text=str(g.get("name") or "权限"), padding=8)
            box.grid(row=r, column=0, sticky="ew", padx=4, pady=5)
            for i, key in enumerate(g.get("keys") or []):
                v = tk.BooleanVar(value=False)
                self.perm_vars[key] = v
                self.perm_keys.append(key)
                cb = ttk.Checkbutton(box, text=str(labels.get(key) or key), variable=v)
                cb.grid(row=i // 2, column=i % 2, sticky="w", padx=6, pady=2)
        self.perm_holder.columnconfigure(0, weight=1)
        self.perm_info.config(text="共 %d 个权限点。管理员（主账号）始终全开，不用配。" % len(self.perm_keys))
        self._load_user_perms()

    def _load_user_perms(self):
        name = self.perm_user.get()
        u = self._perm_users.get(name) or {}
        p = u.get("perms") or {}
        for key, var in self.perm_vars.items():
            var.set(bool(p.get(key)))
        if not name:
            return
        on = sum(1 for v in self.perm_vars.values() if v.get())
        self.perm_info.config(text="正在配置「%s」：已开 %d / %d 个权限点（管理员全开，不用配）"
                                   % (name, on, len(self.perm_keys)))

    def _set_all(self, flag):
        for v in self.perm_vars.values():
            v.set(bool(flag))

    def _restore_defaults(self):
        for key, v in self.perm_vars.items():
            v.set(bool(getattr(self, "_perm_defaults", {}).get(key)))

    def _save_perms(self):
        name = self.perm_user.get()
        if not name:
            messagebox.showinfo("提示", "先选一个子账号", parent=self.win)
            return
        values = {k: bool(v.get()) for k, v in self.perm_vars.items()}
        res = self._ask("/api/perms", "POST", body={"name": name, "perms": values})
        if res is not None:
            self._say("已保存「%s」的权限（%d 项开启）" % (name, sum(1 for v in values.values() if v)))
            self.refresh_perms()
