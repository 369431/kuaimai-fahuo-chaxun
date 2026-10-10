# -*- coding: utf-8 -*-
"""电脑版（Qt）用的本机接口客户端。

**为什么能这么干**：主程序本身就是个 HTTP 服务器（127.0.0.1:8790），手机端用的那套接口
全是现成的；而服务器里**本来就给桌面端留了凭证通道** ——
    kuaimai_scan.py  _token():  "会话 token：查询串 sid / 请求头 X-KM-Token（桌面端用）/ Cookie"
所以桌面版只要带 `X-KM-Token` 头就行，**主程序一行都不用改**。

登录：POST /api/auth/login {name, pw, kind:"desktop"} → {token, perms, role}
"""
import json
import socket
import urllib.error
import urllib.request

UA = "kuaimai-desktop-qt/1"


class ApiError(Exception):
    pass


class Api(object):
    def __init__(self, base="http://127.0.0.1:8790", timeout=20):
        self.base = str(base or "").rstrip("/")
        self.token = ""
        self.name = ""
        self.role = ""
        self.perms = []
        self.ver = ""
        self.timeout = timeout

    # ---------- 底层 ----------
    def _open(self, path, method="GET", body=None, timeout=None):
        url = self.base + path
        hdrs = {"User-Agent": UA, "Cache-Control": "no-store"}
        if self.token:
            hdrs["X-KM-Token"] = self.token
        data = None
        if body is not None:
            data = json.dumps(body, ensure_ascii=False).encode("utf-8")
            hdrs["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
        try:
            with urllib.request.urlopen(req, timeout=float(timeout or self.timeout)) as r:
                raw = r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            raw = ""
            try:
                raw = e.read().decode("utf-8", "replace")
            except Exception:
                pass
            try:
                j = json.loads(raw)
            except Exception:
                j = {"error": "HTTP %s" % e.code}
            if e.code == 401:
                j.setdefault("login", True)
            return j
        except Exception as e:
            return {"error": "本机服务未响应（%s）" % str(e)[:90], "offline": True}
        try:
            return json.loads(raw)
        except Exception:
            return {"raw": raw}

    def get(self, path, timeout=None):
        return self._open(path, "GET", timeout=timeout)

    def post(self, path, body=None, timeout=None):
        return self._open(path, "POST", body=body if body is not None else {}, timeout=timeout)

    # ---------- 业务快捷方法 ----------
    def ping(self):
        return self.get("/api/ping", timeout=4)

    def login(self, name, pw, dev="电脑版", dev_id="", model=""):
        j = self.post("/api/auth/login", {
            "name": str(name or "").strip(), "pw": str(pw or ""),
            "kind": "desktop", "mode": "web",
            "dev": dev, "dev_id": dev_id, "model": model,
            "pc": socket.gethostname(), "win_user": "",
        }, timeout=12)
        if j.get("error"):
            return False, str(j.get("error"))
        self.token = str(j.get("token") or "")
        self.name = str(j.get("name") or name)
        self.role = str(j.get("role") or "")
        self.perms = j.get("perms") or []
        self.ver = str(j.get("ver") or "")
        return bool(self.token), ("" if self.token else "登录没返回 token")

    def logout(self):
        try:
            self.post("/api/auth/logout", timeout=6)
        except Exception:
            pass
        self.token = ""

    def status(self):
        return self.get("/api/status", timeout=6)

    def lookup(self, code):
        import urllib.parse
        return self.get("/api/lookup?code=" + urllib.parse.quote(str(code or "")), timeout=25)

    def scans(self, limit=300):
        return self.get("/api/scans?limit=%d" % int(limit or 300), timeout=12)

    def wave_records(self):
        return self.get("/api/wave/records", timeout=40)

    def purchase_pending(self, days=90):
        """采购待收货/待上架（**只读**）。服务端有 120 秒缓存，所以可以放心轮询。"""
        return self.get("/api/purchase/pending?days=%d" % int(days or 90), timeout=60)

    def purchase_detail(self, pid):
        """某张采购单的商品收发明细（**只读**）。"""
        return self.get("/api/purchase/detail?id=%s" % str(pid), timeout=90)

    # ---------- 电脑版专用（v1.70 新增的三个接口）----------
    def desktop_refresh(self, what):
        """触发数据刷新：what = inc 增量 / full 全量 / shelf 货位 / lock 锁定数。"""
        return self.post("/api/desktop/refresh", {"what": str(what)}, timeout=20)

    def desktop_clearlog(self):
        return self.post("/api/desktop/clearlog", timeout=30)

    def desktop_state(self):
        return self.get("/api/desktop/state", timeout=6)

    def desktop_action(self, name):
        """执行主程序侧动作（打开设置窗 / 触发操作）。白名单在服务器端。"""
        return self.post("/api/desktop/action", {"name": str(name)}, timeout=20)

    def desktop_opt(self, name, value=None):
        """开关类设置：带 value=设成该值，不带=切换。"""
        body = {"name": str(name)}
        if value is not None:
            body["value"] = value
        return self.post("/api/desktop/opt", body, timeout=20)

    def desktop_log(self, tail=120):
        return self.get("/api/desktop/log?tail=%d" % int(tail), timeout=10)

    def api_conf(self):
        """读 API 参数（电脑版「API 设置」用）。"""
        return self.get("/api/desktop/api_conf", timeout=15)

    def save_api_conf(self, conf):
        return self.post("/api/desktop/api_conf", {"conf": dict(conf or {})}, timeout=25)

    def print_progress(self):
        """打单进度的原始数据（主程序那边直接给 print_progress_payload()）。"""
        return self.get("/api/desktop/print_progress", timeout=15)

    def desktop_table(self, name):
        """通用表格数据：{title, columns, rows, count, note}。"""
        import urllib.parse
        return self.get("/api/desktop/table?" + urllib.parse.urlencode({"name": str(name)}),
                        timeout=90)

    # ---------- 设置窗（打印分工 / 对外访问设置 / 子客户端管理）----------
    # ---------- 现货可发（带筛选/排序/标记/改库存/导出）----------
    def stock(self, kw="", only="all", sort="free", hide_sent=True):
        """现货可发表格（真数据来自主程序本地索引）。"""
        import urllib.parse
        q = urllib.parse.urlencode({"name": "stock", "kw": str(kw), "only": str(only),
                                    "sort": str(sort),
                                    "hide_sent": "1" if hide_sent else "0"})
        return self.get("/api/desktop/table?" + q, timeout=120)

    def stock_act(self, action, **kw):
        """现货可发动作：mark / undo / clear_sent / adjust / bins / export。"""
        body = {"action": str(action)}
        body.update(kw)
        return self.post("/api/desktop/stock_act", body, timeout=180)

    def print_clients(self):
        """打印分工：账号→电脑 映射 + 本机身份 + 可选电脑编号。"""
        return self.get("/api/desktop/print_clients", timeout=20)

    def save_print_clients(self, m, local=""):
        body = {"map": dict(m or {})}
        if local:
            body["local"] = str(local)
        return self.post("/api/desktop/print_clients", body, timeout=30)

    def gateway(self):
        """对外访问设置：配置 + 隧道状态 + 证书文件列表（不含内容）。"""
        return self.get("/api/desktop/gateway", timeout=30)

    def gateway_action(self, action, **kw):
        body = {"action": str(action)}
        body.update(kw)
        return self.post("/api/desktop/gateway", body, timeout=60)

    def devices(self):
        """子客户端管理：本机信息 + 账号设备列表。"""
        return self.get("/api/devices", timeout=25)

    def users_action(self, action, name=None, pw=None, **kw):
        body = {"action": str(action)}
        if name:
            body["name"] = str(name)
        if pw:
            body["pw"] = str(pw)
        body.update(kw)
        return self.post("/api/users", body, timeout=30)

    def set_multi_device(self, name, on):
        """允许该账号「电脑端和网页端同时在线」。

        ★ 注意接口收的字段名是 flag（不是 on），传错会被当成关闭。
        """
        return self.users_action("set_multi", name=name, flag=bool(on))

    def perms_payload(self):
        """权限清单 + 各账号权限（/api/perms）。

        ★ 名字不能叫 perms：Api 上已有 self.perms（本登录账号的权限列表），
          同名方法会被实例属性盖住 → 调 api.perms() 直接 TypeError。
        """
        return self.get("/api/perms", timeout=25)

    def save_perms(self, name, values):
        return self.post("/api/perms", {"name": str(name), "perms": dict(values or {})},
                         timeout=30)

    def print_action(self, name, ids=None):
        body = {"name": str(name)}
        if ids:
            body["ids"] = list(ids)
        return self.post("/api/desktop/print_action", body, timeout=30)

    def download(self, path, dest):
        """下载文件（导出 Excel 用）。返回 (ok, 错误)。"""
        req = urllib.request.Request(self.base + path, headers={
            "User-Agent": UA, "X-KM-Token": self.token})
        try:
            with urllib.request.urlopen(req, timeout=90) as r:
                data = r.read()
            with open(dest, "wb") as f:
                f.write(data)
            return True, ""
        except urllib.error.HTTPError as e:
            try:
                j = json.loads(e.read().decode("utf-8", "replace"))
                return False, str(j.get("error") or ("HTTP %s" % e.code))
            except Exception:
                return False, "HTTP %s" % e.code
        except Exception as e:
            return False, str(e)[:140]
