# -*- coding: utf-8 -*-
"""桌面端「登录 + 主/子客户端」自检（无界面）：临时目录 + 临时端口 + 桩 app。

覆盖：
  · /api/ping（免登录）、首次设置管理员、登录、心跳
  · 子账号默认权限、管理员改权限后立即生效
  · 服务端真的拦住了没权限的动作（不是只返回 403 —— 还要确认动作没执行）
  · 扫码 / 扫码记录 / 标记已打 / 导出 / 批次 / 现货可发 / 已发 / 清空已发 / 设备列表
  · 踢下线：旧 token 立即失效 + 那台设备 10 分钟内不能再登录
  · 权限矩阵接口（/api/perms）只给管理员
  · 自动发现（UDP 广播）
  · 桌面登录窗 / 子客户端管理面板能不能建起来（建完就销毁）

跑法：python desktop/_selftest_login.py
"""
import hashlib
import io
import json
import os
import shutil
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, HERE)
LOG_PATH = os.path.join(HERE, "_selftest_login.log")
_logf = io.open(LOG_PATH, "w", encoding="utf-8", buffering=1)


class _Tee:
    """同时写到控制台（可能被控制台 GBK 弄成乱码）和 UTF-8 日志文件。"""

    def write(self, s):
        try:
            sys.__stdout__.write(s)
        except Exception:
            pass
        try:
            _logf.write(s)
        except Exception:
            pass

    def flush(self):
        try:
            _logf.flush()
        except Exception:
            pass


sys.stdout = _Tee()

TMP = tempfile.mkdtemp(prefix="km_selftest_")
REAL_USERS = []          # 跑之前/之后都比对哈希：真账号文件一个也不能被动
for _p in (os.path.join(HERE, "kuaimai_users.json"),
           os.path.join(os.path.dirname(HERE), "kuaimai_users.json"),
           os.path.join(os.path.expanduser("~"), "Desktop", "kuaimai_users.json")):
    if os.path.exists(_p):
        REAL_USERS.append(_p)
FAILS = []
STEPS = []


def ok(name, cond, extra=""):
    STEPS.append((name, bool(cond), extra))
    print(("  [OK]   " if cond else "  [FAIL] ") + name + (("  → " + str(extra)) if extra else ""))
    if not cond:
        FAILS.append(name)


class StubApp:
    """桩 app：只实现网页/桌面接口真正用到的那几个方法，并记录调用次数。"""

    def __init__(self):
        self.web_key = ""
        self.require_key = False
        self.loaded_at = "2026-09-20 00:00:00"
        self.shelf_at = "2026-09-20 00:00:00"
        self.lock_at = "2026-09-20 00:00:00"
        self.calls = {"lookup": 0, "export": 0, "batch": 0, "sent": 0, "clear": 0,
                      "printed": 0, "adjust": 0, "record": 0}
        self.scan_rows = [{"id": 1, "time": "2026-09-20 00:10:00", "code": "9681-黑色S",
                           "pending": 3, "shelf": 5, "orders": 3, "ok": True,
                           "who": "u1", "print_num": "", "printed": 0}]

    def web_status(self):
        return {"live_orders": 11, "codes": 7, "loaded_at": self.loaded_at,
                "shelf_at": self.shelf_at, "lock_at": self.lock_at}

    def web_index_payload(self):
        return {"items": {}}

    def web_lookup(self, code, rel, n):
        self.calls["lookup"] += 1
        return {"code": code, "orders": 3, "pieces": 4, "ones": 2, "shelf": 5,
                "bins": [["A-1", 5]], "lock": 0, "sellable": 5, "avail": 1,
                "shelf_at": self.shelf_at, "lock_at": self.lock_at}

    def record_web_scan(self, out, who=""):
        self.calls["record"] += 1
        self.last_who = who

    def web_scans(self, limit=300, who="", kw=""):
        rows = list(self.scan_rows)
        return {"rows": rows[:limit] if limit else rows, "count": len(rows),
                "who": ["u1"], "loaded_at": self.loaded_at, "shelf_at": self.shelf_at}

    def scans_xlsx(self, limit=0, who="", kw=""):
        self.calls["export"] += 1
        return b"PK\x03\x04fake-xlsx"

    def web_batch(self, batch, days=3):
        self.calls["batch"] += 1
        return {"orders": [{"seq": 1, "sid": "S1", "short_id": "", "express": "E1",
                            "urgent": False, "sys_status": "WAIT_SEND_GOODS"}],
                "rows": [{"i": 0, "code": "9681-黑色S", "num": 2, "shelf": 5, "bins": "A-1"}],
                "batch": batch}

    def web_stock(self, kw="", only="all", sort="free"):
        return {"rows": [{"c": "9681-黑色S", "b": "A-1", "s": 5, "p": 4, "o": 3, "n": 2,
                          "m": 1, "mp": 2, "uo": 0, "up": 0, "p1": 0, "sent": 0, "f": 3}],
                "total": 1, "loaded_at": self.loaded_at, "shelf_at": self.shelf_at}

    def stock_bins_of(self, code):
        return {"code": code, "found": True, "shelf": 5, "bins": [["A-1", 5]]}

    def stock_xlsx(self, kw="", only="all", sort="free"):
        return b"PK\x03\x04fake"

    def mark_sent(self, codes, undo=False):
        self.calls["sent"] += 1
        return [str(c) for c in (codes or [])]

    def clear_sent(self):
        self.calls["clear"] += 1
        return []

    def stock_adjust(self, code, bin_code, qty, who=""):
        self.calls["adjust"] += 1
        return {"ok": True, "msg": "", "code": code, "bin": bin_code, "qty": qty}

    def adjust_logs(self, limit=30):
        return [{"ts": "2026-09-20 00:20:00", "who": "u1", "code": "9681", "bin": "A-1",
                 "old": "5", "new": "6", "ok": True, "msg": ""}]


def sha(path):
    try:
        with io.open(path, "rb") as f:
            return hashlib.sha256(f.read()).hexdigest()
    except Exception:
        return ""


def free_port(start=21000, end=31000):
    """挑一个真的空闲的端口（别用 8790/8791：真程序很可能正跑着）。"""
    import random
    import socket as _sock
    for _ in range(60):
        p = random.randint(start, end)
        s = _sock.socket()
        try:
            s.bind(("127.0.0.1", p))
            return p
        except Exception:
            pass
        finally:
            try:
                s.close()
            except Exception:
                pass
    return 29999


def main():
    real_before = {p: sha(p) for p in REAL_USERS}
    print("临时目录：%s" % TMP)
    print("真实账号文件（跑完要逐一比对哈希）：%s" % (REAL_USERS or "（无）"))

    import kuaimai_scan as km
    import kuaimai_client as kmc
    import kuaimai_perms as perms
    import kuaimai_auth as auth

    # ---- 关键：import 之后再改路径，否则会往真的账号文件里写测试账号 ----
    km.auth.USERS_FILE = os.path.join(TMP, "kuaimai_users.json")
    km.auth.BASE_DIR = TMP
    kmc.CONFIG_FILE = os.path.join(TMP, "kuaimai_client.json")
    if os.path.abspath(km.auth.USERS_FILE) in [os.path.abspath(p) for p in REAL_USERS]:
        print("！！临时账号文件挂载失败，中止")
        return 2
    print("已把账号文件挂到临时目录：%s" % km.auth.USERS_FILE)

    app = StubApp()
    TEST_PORT = free_port()   # 不能用 8790：真程序很可能正跑着（Windows 上 SO_REUSEADDR 会“抢”同一个端口）
    servers, port = km.start_web_server(app, port=TEST_PORT, host="127.0.0.1")
    if not port:
        print("！！端口起不来，中止")
        return 2
    base = "http://127.0.0.1:%d" % port
    kmc.save_config({"port": port})      # 本机模式的 Session 默认走这个端口
    print("测试服务：%s" % base)
    km._WEB_STATE["servers"] = servers
    km._WEB_STATE["port"] = port
    km._WEB_STATE["app"] = app
    time.sleep(0.3)

    try:
        # 1) 免登录的 /api/ping
        okk, ping = kmc.http_json(base, "/api/ping", timeout=5)
        ok("/api/ping 免登录可访问", okk and ping.get("app") == "kuaimai-fahuo-chaxun", ping.get("error"))
        # 地址解析：局域网 IP / 带端口 / https 域名:9443 / 裸 IPv6 都要认
        cases = (("192.168.1.5", "http://192.168.1.5:8790"),
                 ("192.168.1.5:8790", "http://192.168.1.5:8790"),
                 ("kmcx.cc:9443", "https://kmcx.cc:9443"),
                 ("https://kmcx.cc:9443/", "https://kmcx.cc:9443"),
                 ("https://kmcx.cc", "https://kmcx.cc:443"),
                 ("http://kmcx.cc/", "http://kmcx.cc:8790"),
                 ("[2408:8207::1]:8790", "http://[2408:8207::1]:8790"),
                 ("2408:8207:883a::1", "http://[2408:8207:883a::1]:8790"))
        bad = [(a, kmc.norm_base(a), want) for a, want in cases if kmc.norm_base(a) != want]
        ok("地址解析：局域网 IP / 端口 / https 域名:9443 / 裸 IPv6 都能认", not bad, bad)
        ok("证书校验开关能存能读", kmc.set_insecure(True) is True and kmc.insecure() is True)
        kmc.set_insecure(False)
        ok("/api/ping 带 need_setup", isinstance(ping.get("need_setup"), bool), ping)

        # 2) 没登录时 /api/scans 要 401
        okk, res = kmc.http_json(base, "/api/scans")
        ok("未登录访问 /api/scans → 401", (not okk) and res.get("_status") == 401, res)

        # 3) 首次设置管理员（本机 127.0.0.1 = 本机请求）
        admin, err = kmc.setup(base, "boss", "abcd1234")
        ok("首次设置管理员并登录", admin is not None, err)
        ok("管理员权限全开", bool(admin and admin.is_admin and admin.can("export.excel")), "")
        if admin is not None:
            admin._port = port

        # 4) 管理员建一个子账号
        okk, res = admin.api("/api/users", "POST", body={"action": "add", "name": "u1",
                                                        "pw": "u1pass", "role": "user"})
        ok("管理员新增子账号 u1", okk and res.get("ok"), res.get("error"))

        # 5) 子客户端登录（模拟局域网另一台机器）
        sub, err = kmc.login(base, "u1", "u1pass", mode="remote")
        ok("子账号登录（子客户端模式）", sub is not None, err)
        if sub is None:
            print("！！子账号登录失败，后续检查无意义")
            return 3
        ok("子账号默认：扫码记录=开", bool(sub and sub.can("scan.record")))
        ok("子账号默认：导出 Excel=关", bool(sub and not sub.can("export.excel")))
        ok("子账号默认：清空已发=关", bool(sub and not sub.can("stock.sent.clear")))
        ok("子账号默认：子客户端管理=关", bool(sub and not sub.can("desktop.admin")))

        # 6) 有权 / 无权的接口（重点：无权限时动作真的不该执行）
        before = app.calls["export"]
        okk, res = sub.api("/api/scans")
        ok("子账号能看扫码记录", okk and len(res.get("rows") or []) == 1, res)
        okk, res = sub.api("/api/scans/export", timeout=20)
        ok("子账号导出被 403 拦住", (not okk) and res.get("_status") == 403 and res.get("denied"), res)
        ok("被拒的导出确实没执行（动作计数没涨）", app.calls["export"] == before,
           "before=%s after=%s" % (before, app.calls["export"]))
        okk, res = sub.api("/api/stock/sent", "POST", body={"clear": True})
        ok("子账号清空已发被拦住", (not okk) and res.get("_status") == 403, res)
        ok("被拒的清空已发没有执行", app.calls["clear"] == 0, app.calls["clear"])

        # 7) 有权限的查询/动作：扫码、批次、标记已打、已发
        okk, res = sub.api("/api/lookup", params={"code": "9681-黑色S", "rel": "any", "n": 0})
        ok("子账号扫码查询成功", okk and res.get("code") == "9681-黑色S", res)
        ok("扫码记录里记的是登录账号", app.calls["record"] == 1 and getattr(app, "last_who", "") == "u1",
           getattr(app, "last_who", ""))
        okk, res = sub.api("/api/batch", params={"batch": "3014728", "days": 3}, timeout=30)
        ok("子账号批次查询成功", okk and len(res.get("rows") or []) == 1, res)
        okk, res = sub.api("/api/scans/printed", "POST", body={"id": 1, "flag": 1})
        ok("子账号标记已打（默认开，接口放行）", okk and res.get("printed") == 1, res)
        okk, res = sub.api("/api/stock", params={"kw": "", "only": "all", "sort": "free"})
        ok("子账号现货可发（查看）", okk and len(res.get("rows") or []) == 1, res)
        okk, res = sub.api("/api/stock/sent", "POST", body={"codes": ["9681-黑色S"]})
        ok("子账号标记已发需要 stock.canprint → 默认被拦", (not okk) and res.get("_status") == 403, res)
        okk, res = sub.api("/api/stock/bins", params={"code": "9681-黑色S"})
        ok("子账号改库存（无权限）被拦", (not okk) and res.get("_status") == 403, res)

        # 8) 子账号不能管账号 / 看设备 / 拿权限矩阵
        okk, res = sub.api("/api/users", "POST", body={"action": "list"})
        ok("子账号不能列账号", (not okk) and res.get("_status") == 403, res)
        okk, res = sub.api("/api/devices")
        ok("子账号不能看在线设备", (not okk) and res.get("_status") == 403, res)
        okk, res = sub.api("/api/perms")
        ok("子账号拿不到权限矩阵", (not okk) and res.get("_status") == 403, res)

        # 9) 管理员：给 u1 开权限（导出 + 已发 + 清空 + 改库存 + 子客户端管理不行）
        okk, res = admin.api("/api/perms")
        keys = [c.get("key") for c in (res.get("catalog") or [])]
        ok("权限清单里有新的桌面权限点",
           all(k in keys for k in ("scan.record", "batch.query", "data.refresh",
                                   "export.excel", "api.settings", "desktop.admin")), keys[:5])
        okk, res = admin.api("/api/perms", "POST", body={"name": "u1", "perms": {
            "export.excel": True, "stock.canprint": True, "stock.sent.clear": True,
            "stock.edit": True, "desktop.admin": True, "垃圾键": True}})
        ok("管理员保存 u1 权限", okk and res.get("ok"), res.get("error"))
        ok("管理员权限不能被写（desktop.admin 不进子账号）", not bool((res.get("perms") or {}).get("desktop.admin")),
           res.get("perms"))
        sub2, err = kmc.login(base, "u1", "u1pass", mode="remote")
        ok("重新登录拿到新权限", bool(sub2 and sub2.can("export.excel") and sub2.can("stock.sent.clear")), err)
        before = app.calls["export"]
        okk, data = sub2.api("/api/scans/export", timeout=20)
        ok("开权限后能导出（拿到 xlsx 字节）", okk and isinstance(data, (bytes, bytearray)) and app.calls["export"] == before + 1)
        okk, res = sub2.api("/api/stock/sent", "POST", body={"clear": True})
        ok("开权限后能清空已发", okk and res.get("ok") and app.calls["clear"] == 1, res)
        okk, res = sub.api("/api/scans/export")   # 旧的 sub 会话已被 sub2 顶下线
        ok("同账号新登录把旧会话顶下线", (not okk) and res.get("_status") == 401, res)
        ok("旧会话被顶 → Session.kicked 置位", sub.kicked is True, sub.kicked)

        # 10) 心跳 / 在线设备
        okk, res = sub2.api("/api/client/info", "POST", body={"mode": "remote", "pc": "PC-B",
                                                             "win_user": "kerwin", "kind": "desktop"})
        ok("子客户端心跳成功", okk and res.get("ok"), res)
        okk, res = admin.api("/api/devices")
        devs = res.get("devices") or []
        u1 = [d for d in devs if d.get("name") == "u1"]
        ok("在线设备列表带电脑名/Windows 用户",
           bool(u1 and u1[0].get("pc") == "PC-B" and u1[0].get("win_user") == "kerwin"), u1)
        ok("在线设备列表带本机（主机）信息", bool((res.get("host") or {}).get("pc")), res.get("host"))

        # 11) 踢下线：token 立刻失效 + 那台设备 10 分钟不能再登录
        okk, res = admin.api("/api/users", "POST", body={"action": "kick", "name": "u1"})
        ok("管理员踢下线 u1", okk and res.get("ok"), res)
        okk, res = sub2.api("/api/scans")
        ok("被踢后旧 token 立刻失效（401）", (not okk) and res.get("_status") == 401, res)
        bad, err = kmc.login(base, "u1", "u1pass", mode="remote")
        ok("被踢的设备 10 分钟内不能再登录", bad is None and "分钟" in (err or ""), err)

        # 12) 自动发现（UDP 广播）
        km.start_discovery_responder()
        time.sleep(0.3)
        found = kmc.discover(timeout=1.5)
        ok("自动发现能广播找到主客户端（找不到不算致命，看网络）",
           any(int(f.get("port") or 0) == int(port) for f in found), found)

        # 13) 权限点的默认值/兼容
        eff = perms.effective(None, "user")
        ok("老账号（没存 perms）按默认算：查询类开、动作类关",
           eff.get("scan.query") is True and eff.get("export.excel") is False, eff)
        eff2 = perms.effective({"scan.query": False}, "user")
        ok("显式关闭能被尊重", eff2.get("scan.query") is False)

        # 13.5) 加急按快递拆开（中通/申通）：内存索引 + SQL 索引两条路都要对
        store = {
            "S1": {"status": "WAIT_SEND_GOODS", "us": "", "urgent": True, "ex": "中通快递",
                   "count": 1, "pairs": [("9681-黑色S", 1)]},
            "S2": {"status": "WAIT_SEND_GOODS", "us": "", "urgent": True, "ex": "申通",
                   "count": 1, "pairs": [("9681-黑色S", 1)]},
            "S3": {"status": "WAIT_SEND_GOODS", "us": "", "urgent": True, "ex": "中通",
                   "count": 2, "pairs": [("9681-黑色S", 2)]},
            "S4": {"status": "WAIT_SEND_GOODS", "us": "", "urgent": False, "ex": "中通",
                   "count": 1, "pairs": [("9681-黑色S", 1)]},
            "S5": {"status": "WAIT_SEND_GOODS", "us": "", "urgent": True, "ex": "ZTO",
                   "count": 1, "pairs": [("9682-白色M", 1)]},
        }
        idx, _stat = km.rebuild_index(store)
        ok("加急按快递拆开（内存索引）：一单一件+加急才计",
           (idx.get("9681-黑色S") or {}).get("ue") == {"中通": 1, "申通": 1},
           (idx.get("9681-黑色S") or {}).get("ue"))
        ok("英文快递代码也认（ZTO → 中通）",
           (idx.get("9682-白色M") or {}).get("ue") == {"中通": 1},
           (idx.get("9682-白色M") or {}).get("ue"))
        try:
            conn = km.kuaimai_db.connect(os.path.join(TMP, "ue_test.db"))
            km.kuaimai_db.import_store(conn, store, loaded_at="t")
            idx2, _s2 = km.kuaimai_db.rebuild_index_db(conn, "不限", 0)
            conn.close()
            ok("加急按快递拆开（SQL 索引）也对",
               (idx2.get("9681-黑色S") or {}).get("ue") == {"中通": 1, "申通": 1},
               (idx2.get("9681-黑色S") or {}).get("ue"))
        except Exception as e:
            ok("加急按快递拆开（SQL 索引）也对", False, repr(e)[:200])

        # 14) 桌面窗口能不能建起来（建完就销毁，不弹给用户看）
        try:
            import tkinter as tk
            import kuaimai_login_window as kmlw
            import kuaimai_admin_panel as kmap
            root = tk.Tk()
            root.withdraw()
            lw = kmlw.LoginWindow(root, lambda: port, default_port=port)
            lw.win.withdraw()
            ok("桌面登录窗能建起来", True)
            fake_app = type("A", (), {})()
            fake_app.root = root
            fake_app.session = admin
            kmap.open_admin_panel(fake_app)
            win = getattr(fake_app, "_admin_win", None)
            ok("子客户端管理面板能建起来（在线设备/账号/权限都拉到了）", win is not None)
            try:
                win.withdraw()
                win.destroy()
            except Exception:
                pass
            try:
                lw.win.destroy()
            except Exception:
                pass
            root.destroy()

            # 16) 子客户端模式：整个桌面主界面能建起来，并按权限置灰/收起
            d = auth._load()
            d["blocked"] = {}                 # 清掉前面“踢下线”给本机留的封禁，换个账号继续测
            auth._save(d)
            okk, res = admin.api("/api/users", "POST", body={"action": "add", "name": "u2",
                                                            "pw": "u2pass", "role": "user"})
            ok("再建一个子账号 u2", okk and res.get("ok"), res.get("error"))
            s2, err2 = kmc.login(base, "u2", "u2pass", mode="remote")
            ok("u2 子客户端登录", s2 is not None, err2)
            if s2 is not None:
                root2 = tk.Tk()
                root2.withdraw()
                app2 = km.ScanApp(root2, s2)

                def dis(key):
                    items = (app2.gated or {}).get(key) or []
                    if not items:
                        return None
                    w, mode = items[0]
                    if mode == "disable":
                        return "disabled" in w.state()
                    return not bool(w.grid_info())      # grid_remove 后 grid_info() 为空

                ok("子客户端模式：桌面主界面能建起来", True)
                ok("子客户端模式：查询按钮可用", dis("scan.query") is False, dis("scan.query"))
                ok("子客户端模式：导出 Excel 置灰", dis("export.excel") is True, dis("export.excel"))
                ok("子客户端模式：API 设置置灰", dis("api.settings") is True, dis("api.settings"))
                ok("子客户端模式：刷新周期整块收起", dis("data.refresh") is True, dis("data.refresh"))
                ok("子客户端模式：扫码记录表按权限显示", dis("scan.record") is False, dis("scan.record"))
                ok("子客户端模式：顶栏写清数据来自主客户端",
                   "子客户端" in str(app2.web_label.cget("text")), app2.web_label.cget("text"))
                ok("子客户端模式：身份行显示账号/角色",
                   "u2" in str(app2.id_label.cget("text")), app2.id_label.cget("text"))
                try:
                    app2.root.destroy()
                except Exception:
                    pass
        except Exception as e:
            ok("桌面窗口能建起来", False, repr(e)[:200])

        # 17) 登录阶段（回环）→ 主客户端模式（对外）的切换（放最后：会把测试服务停掉）
        for s in servers:
            try:
                s.shutdown()
            except Exception:
                pass
            try:
                s.server_close()
            except Exception:
                pass
        km.stop_web_server()
        time.sleep(0.3)
        SW = free_port()
        p1 = km.ensure_web_server(None, lan=False, port=SW)
        okk, png = kmc.http_json("http://127.0.0.1:%d" % SW, "/api/ping", timeout=5)
        ok("登录阶段：只在回环上起服务（/api/ping 可用）",
           p1 == SW and okk and png.get("app") == "kuaimai-fahuo-chaxun", png.get("error"))
        km._note_login("boss", "admin", "host")          # 主程序登录后会做这件事
        p2 = km.ensure_web_server(app, lan=True, port=SW)
        okk, png2 = kmc.http_json("http://127.0.0.1:%d" % SW, "/api/ping", timeout=5)
        ok("切主客户端模式：同端口重起，服务已换成主程序且保住登录",
           p2 == SW and okk and png2.get("logged_in") is True and bool(png2.get("pc")), png2)
        okk, res = kmc.http_json("http://127.0.0.1:%d" % SW, "/api/status", token=admin.token, timeout=5)
        ok("主客户端模式：带 token 能拿到主程序状态", okk and res.get("live_orders") == 11, res)
        okk, res = kmc.http_json("http://127.0.0.1:%d" % SW, "/api/scans")
        ok("主客户端模式：没 token 依旧 401", (not okk) and res.get("_status") == 401, res)
        found3 = kmc.discover(timeout=1.5)
        ok("主客户端模式：广播报的端口就是对外端口",
           any(int(f.get("port") or 0) == SW for f in found3), found3)
        km.stop_web_server()

        # 18) 主机模式：真的按“管理员本机登录”把桌面主界面建起来（数据文件全指到临时目录）
        HOSTDIR = os.path.join(TMP, "host")
        try:
            os.makedirs(HOSTDIR, exist_ok=True)
        except Exception:
            pass
        for _nm in ("CACHE_FILE", "PENDING_CACHE_FILE", "STOCK_CACHE_FILE", "SHELF_CACHE_FILE",
                    "LOCK_CACHE_FILE", "SETTINGS_FILE", "PULL_PROGRESS_FILE", "DB_FILE",
                    "ORDERS_DB_FILE", "API_FILE"):
            try:
                setattr(km, _nm, os.path.join(HOSTDIR, os.path.basename(getattr(km, _nm))))
            except Exception:
                pass
        km.WEB_PORT = free_port()
        km.DISCOVER_PORT = free_port()
        km.auth.USERS_FILE = os.path.join(HOSTDIR, "kuaimai_users.json")
        hp = km.ensure_web_server(None, lan=False, port=free_port())
        hbase = "http://127.0.0.1:%d" % hp
        kmc.save_config({"port": hp})
        hs, herr = kmc.setup(hbase, "boss", "abcd1234")      # 本机首次设置管理员（回环）
        ok("主机模式：本机首次设置管理员", hs is not None, herr)
        if hs is not None:
            hs._port = hp
            host_root = tk.Tk()
            host_root.withdraw()
            apph = km.ScanApp(host_root, hs)
            ok("主机模式：桌面主界面能建起来（管理员）", True)
            ok("主机模式：管理员所有按钮都可用（没有一个被灰）",
               all(not (m == "disable" and "disabled" in w.state())
                   for _k, items in (apph.gated or {}).items() for w, m in items), "")
            ok("主机模式：手机网页服务在跑（对外监听）",
               int(getattr(apph, "web_port", 0)) == int(km.WEB_PORT), getattr(apph, "web_port", None))
            hbase2 = "http://127.0.0.1:%d" % int(getattr(apph, "web_port", 0) or hp)
            okk, res = kmc.http_json(hbase2, "/api/ping", timeout=5)
            ok("主机模式：/api/ping 报“已登录（管理员）”", okk and res.get("logged_in") is True, res)
            okk, res = kmc.http_json(hbase2, "/api/scans", token=hs.token, timeout=5)
            ok("主机模式：管理员 token 能读扫码记录", okk and ("rows" in res), res)
            okk, res = kmc.http_json(hbase2, "/api/users", "POST", body={"action": "list"},
                                     token=hs.token, timeout=5)
            ok("主机模式：管理员能管账号", okk and res.get("ok"), res)
            try:
                host_root.destroy()
            except Exception:
                pass
            km.stop_web_server()

        # 19) 对外访问设置（域名 / frp / 证书）的逻辑：配置 + frpc.toml + 证书安装校验
        gwdir = os.path.join(TMP, "gw")
        try:
            os.makedirs(os.path.join(gwdir, "frp"), exist_ok=True)
        except Exception:
            pass
        import kuaimai_gateway as gw
        gw.set_base(gwdir)
        gcfg = {"domain": "shsp.pw", "server_addr": "106.52.122.158", "server_port": 7000,
                "token": "tok-123", "https_port": 9443, "web_port": 8790, "expose_443": True}
        okw, gerr = gw.save_config(gcfg)
        ok("对外访问设置：配置能存", okw, gerr)
        okw, gerr = gw.write_frpc_toml(gcfg)
        toml = ""
        try:
            toml = io.open(gw.paths()["frpc_toml"], encoding="utf-8").read()
        except Exception:
            pass
        ok("对外访问设置：frpc.toml 写对了（服务器/token/9443/443）",
           okw and 'serverAddr = "106.52.122.158"' in toml and 'auth.token = "tok-123"' in toml
           and "remotePort = 9443" in toml and "remotePort = 443" in toml, toml[:80].replace("\r", ""))
        ok("对外访问设置：外网地址拼得对", gw.public_url(gcfg) == "https://shsp.pw:9443/", gw.public_url(gcfg))
        ok("对外访问设置：配置读回一致", (gw.load_config().get("token") == "tok-123"
                                     and gw.load_config().get("domain") == "shsp.pw"))
        # 真证书（本机现成的 shsp.pw 一对）→ 装进临时目录
        fx_crt = r"C:\Users\Kerwin\Desktop\kuaimai_https\lego\certificates\shsp.pw.crt"
        fx_key = r"C:\Users\Kerwin\Desktop\kuaimai_https\lego\certificates\shsp.pw.key"
        if os.path.exists(fx_crt) and os.path.exists(fx_key):
            okp, pmsg = gw.check_pair(fx_crt, fx_key)
            ok("证书：一对的 .crt/.key 能通过校验", okp, pmsg)
            oki, imsg, dom = gw.install_cert(fx_crt, fx_key, "")
            ok("证书：能装进证书目录并识别域名", oki and dom == "shsp.pw", "%s / %s" % (imsg, dom))
            ok("证书：装完能在清单里看到（带到期日）",
               any(c.get("domain") == "shsp.pw" and c.get("not_after") for c in gw.cert_pairs()),
               [c.get("domain") for c in gw.cert_pairs()])
            oki2, imsg2, dom2 = gw.install_cert(fx_crt, fx_key, "../坏域名")
            ok("证书：手填的怪域名会被拌掉（用证书里的真域名）",
               oki2 and dom2 == "shsp.pw"
               and all(os.path.dirname(c["crt"]) == gw.paths()["cert_dir"] for c in gw.cert_pairs()),
               "%s / %s" % (imsg2, dom2))
            bad_ok, bad_msg = gw.check_pair(fx_crt, os.path.join(gw.paths()["cert_dir"], "shsp.pw.key") + ".nope")
            ok("证书：错的私钥会被拦住", (not bad_ok), bad_msg)
        else:
            ok("证书：本机没有 shsp.pw 证书做样本（跳过）", True, "跳过")
        ok("对外访问设置：status() 能跑出来",
           isinstance(gw.status(), dict) and "frpc" in gw.status())

        # 20) 「对外访问设置」窗口能不能建起来（建完就销毁）
        try:
            import kuaimai_gateway_ui as gwui
            groot = tk.Tk()
            groot.withdraw()
            gapp = type("A", (), {})()
            gapp.root = groot
            gwui.open_gateway_dialog(gapp)
            gwin = getattr(gapp, "_gw_win", None)
            ok("对外访问设置窗口能建起来", gwin is not None)
            try:
                gwin.withdraw()
                gwin.destroy()
            except Exception:
                pass
            groot.destroy()
        except Exception as e:
            ok("对外访问设置窗口能建起来", False, repr(e)[:200])
    finally:
        for s in servers:
            try:
                s.shutdown()
            except Exception:
                pass
            try:
                s.server_close()
            except Exception:
                pass

    real_after = {p: sha(p) for p in REAL_USERS}
    ok("真实账号文件一个也没被碰过", real_before == real_after,
       {k: (v[:10], real_after.get(k, "")[:10]) for k, v in real_before.items() if v != real_after.get(k)})
    n_fail = len(FAILS)
    print("\n==== %d 项检查，%d 项失败 ====" % (len(STEPS), n_fail))
    for name, _c, extra in STEPS:
        if name in FAILS:
            print("  FAIL: %s → %s" % (name, extra))
    print("UTF-8 日志：%s" % LOG_PATH)
    report = os.path.join(TMP, "selftest_report.txt")
    try:
        with io.open(report, "w", encoding="utf-8") as f:
            f.write("\n".join("%s\t%s\t%s" % (("OK" if c else "FAIL"), n, e) for n, c, e in STEPS))
        print("报告：%s" % report)
    except Exception:
        pass
    try:
        shutil.rmtree(TMP, ignore_errors=True)
    except Exception:
        pass
    return 1 if n_fail else 0


if __name__ == "__main__":
    sys.exit(main())
