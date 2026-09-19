# -*- coding: utf-8 -*-
"""桌面端「登录 / 主-子客户端」支撑：本机配置、局域网自动发现、会话与远程接口。

主客户端 = 跑服务、持有数据和快麦凭据的那台电脑（登录管理员账号的那台）
子客户端 = 局域网里的其它电脑：连主客户端取数、按账号权限显示功能，本机不存快麦凭据

约定：
  · 所有请求都带 X-KM-Token 头（服务端 _token() 认它，不必用 Cookie）
  · 服务端 401 且带 login=True → 会话失效/被踢下线，Session 会回调 on_kicked
  · 子客户端每 30 秒 POST /api/client/info 一次心跳（主客户端用它显示「在线设备」）
"""
import hashlib
import io
import json
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

APP = "kuaimai-fahuo-chaxun"
APP_VER = "v1.12"              # 版本号（登录窗/主窗口都显示它，一眼能看出是不是新版）
DISCOVER_PORT = 8791
DISCOVER_REQ = b"KUIMAI-SCAN-DISCOVER/1"
DEFAULT_PORT = 8790
HEARTBEAT_SEC = 30


def base_dir():
    """配置文件跟 exe / 程序同目录（打包后 __file__ 在临时解包目录，不能用）。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


CONFIG_FILE = os.path.join(base_dir(), "kuaimai_client.json")


def load_config():
    try:
        with io.open(CONFIG_FILE, encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


def save_config(values):
    try:
        d = load_config()
        d.update(values or {})
        with io.open(CONFIG_FILE, "w", encoding="utf-8") as f:
            f.write(json.dumps(d, ensure_ascii=False, indent=2))
        return True
    except Exception:
        return False


def pc_name():
    try:
        return socket.gethostname()
    except Exception:
        return ""


def win_user():
    for k in ("USERNAME", "USER", "LOGNAME"):
        v = (os.environ.get(k) or "").strip()
        if v:
            return v
    try:
        import getpass
        return getpass.getuser()
    except Exception:
        return ""


def device_id():
    """本机稳定标识：服务端「踢下线后 10 分钟不能再登录」按它来。"""
    d = load_config()
    did = str(d.get("dev_id") or "").strip()
    if did:
        return did
    raw = "%s|%s|%s" % (pc_name(), win_user(), os.environ.get("COMPUTERNAME") or "")
    did = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]
    save_config({"dev_id": did})
    return did


def client_label():
    parts = [p for p in (pc_name(), win_user()) if p]
    return " · ".join(parts) or "本机"


def local_ip():
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("223.5.5.5", 80))
            return s.getsockname()[0]
        finally:
            s.close()
    except Exception:
        return "127.0.0.1"


def _broadcast_addrs():
    out = []
    try:
        ip = local_ip()
        if ip and not ip.startswith("127."):
            out.append(ip.rsplit(".", 1)[0] + ".255")
    except Exception:
        pass
    out.append("255.255.255.255")
    return out


def discover(timeout=1.5):
    """UDP 广播找主客户端 → [{'name','host','port','need_setup','logged_in','user'}]（去重）。"""
    found = {}
    s = None
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        s.settimeout(0.25)
        for addr in _broadcast_addrs():
            try:
                s.sendto(DISCOVER_REQ, (addr, DISCOVER_PORT))
            except Exception:
                pass
        t0 = time.time()
        while time.time() - t0 < max(0.3, float(timeout or 1.5)):
            try:
                data, peer = s.recvfrom(4096)
            except socket.timeout:
                continue
            except Exception:
                break
            try:
                info = json.loads(data.decode("utf-8", "replace"))
            except Exception:
                continue
            if not isinstance(info, dict) or info.get("app") != APP:
                continue
            host = str(info.get("ip") or (peer[0] if peer else "") or "")
            try:
                port = int(info.get("port") or DEFAULT_PORT)
            except Exception:
                port = DEFAULT_PORT
            if not host:
                continue
            host = host.strip()
            if host in ("127.0.0.1", "::1") or host.startswith("169.254."):
                continue
            found[(host, port)] = {"name": str(info.get("name") or host),
                                   "host": host, "port": port,
                                   "need_setup": bool(info.get("need_setup")),
                                   "logged_in": bool(info.get("logged_in")),
                                   "user": str(info.get("user") or "")}
        try:
            s.close()
        except Exception:
            pass
    except Exception:
        if s is not None:
            try:
                s.close()
            except Exception:
                pass
    return sorted(found.values(), key=lambda x: (x["host"], x["port"]))


def norm_base(addr, default_port=None):
    """把用户填的地址统一成 URL。支持：

      192.168.1.5                     → http://192.168.1.5:8790
      192.168.1.5:8790                → http://192.168.1.5:8790
      kmcx.cc:9443                    → https://kmcx.cc:9443   （9443/443 默认当成 https）
      https://kmcx.cc:9443/           → https://kmcx.cc:9443
      https://kmcx.cc                 → https://kmcx.cc:443
      [2408:8207::1]:8790             → http://[2408:8207::1]:8790
      2408:8207:883a::1               → http://[2408:8207:883a::1]:8790   （裸 IPv6 自动加括号）
    """
    a = str(addr or "").strip().rstrip("/")
    if not a:
        return ""
    scheme = ""
    low = a.lower()
    if low.startswith("http://"):
        scheme, a = "http", a[7:]
    elif low.startswith("https://"):
        scheme, a = "https", a[8:]
    a = a.split("/")[0].split("?")[0].strip()      # 去掉路径/查询串
    host, port = "", ""
    if a.startswith("["):                            # [IPv6]:port
        end = a.find("]")
        if end > 0:
            host = a[1:end]
            rest = a[end + 1:]
            if rest.startswith(":"):
                port = rest[1:]
    elif a.count(":") == 1:                          # host:port
        host, port = a.rsplit(":", 1)
    else:                                             # 没端口（含裸 IPv6）
        host = a.strip("[]")
    host = host.strip()
    if not host:
        return ""
    if not scheme:
        scheme = "https" if port in ("443", "9443") else "http"
    try:
        port_n = int(port) if port else (443 if scheme == "https" else int(default_port or DEFAULT_PORT))
    except Exception:
        port_n = int(default_port or DEFAULT_PORT)
    if ":" in host:                                  # IPv6 字面量要方括号
        host = "[%s]" % host.strip("[]")
    return "%s://%s:%d" % (scheme, host, port_n)


# 不认系统代理：主客户端在局域网里，走代理会直接把请求拐跑（有些电脑装了代理/安全软件）
_OPENER_PLAIN = urllib.request.build_opener(urllib.request.ProxyHandler({}))
_OPENER_INSECURE = None          # 跳过证书校验时才用（自签证书 / 用 IP 访问）
_INSECURE_TLS = bool(load_config().get("tls_insecure"))


def set_insecure(flag):
    """https 证书校验开关（只影响桌面端子客户端连主端）。"""
    global _INSECURE_TLS, _OPENER_INSECURE
    _INSECURE_TLS = bool(flag)
    _OPENER_INSECURE = None
    try:
        save_config({"tls_insecure": _INSECURE_TLS})
    except Exception:
        pass
    return _INSECURE_TLS


def insecure():
    return bool(_INSECURE_TLS)


def _opener():
    global _OPENER_INSECURE
    if not _INSECURE_TLS:
        return _OPENER_PLAIN
    if _OPENER_INSECURE is None:
        try:
            import ssl
            ctx = ssl.create_default_context()
            ctx.check_hostname = False
            ctx.verify_mode = ssl.CERT_NONE
            _OPENER_INSECURE = urllib.request.build_opener(
                urllib.request.ProxyHandler({}), urllib.request.HTTPSHandler(context=ctx))
        except Exception:
            _OPENER_INSECURE = _OPENER_PLAIN
    return _OPENER_INSECURE


def http_json(base, path, method="GET", params=None, body=None, token="", timeout=20):
    """返回 (ok, obj)。obj 是 dict（JSON）或 bytes（文件）；出错时 obj = {'error':..., '_status':...}。"""
    base = str(base or "").rstrip("/")
    url = base + path
    if params:
        url += ("&" if "?" in url else "?") + urllib.parse.urlencode(params)
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body, ensure_ascii=False).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if token:
        headers["X-KM-Token"] = str(token)
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with _opener().open(req, timeout=float(timeout or 20)) as r:
            raw = r.read()
            ctype = (r.headers.get("Content-Type") or "").lower()
            if "json" in ctype:
                try:
                    return True, json.loads(raw.decode("utf-8", "replace"))
                except Exception:
                    return True, {"raw": raw}
            return True, raw
    except urllib.error.HTTPError as e:
        raw = b""
        try:
            raw = e.read()
        except Exception:
            pass
        obj = None
        try:
            obj = json.loads(raw.decode("utf-8", "replace"))
        except Exception:
            obj = None
        if not isinstance(obj, dict):
            obj = {"error": "HTTP %d" % int(getattr(e, "code", 0) or 0)}
        obj["_status"] = int(getattr(e, "code", 0) or 0)
        return False, obj
    except Exception as e:
        return False, {"error": str(e)[:200], "_net": True}


def human_err(obj, base=""):
    """把接口/网络错误变成一句人看得懂的话。"""
    if isinstance(obj, dict):
        if obj.get("_net"):
            return "连不上主客户端（%s）：%s" % (base or "地址没填？", str(obj.get("error") or "")[:80])
        return str(obj.get("error") or "").strip() or "未知错误"
    return "未知错误"


class Session:
    """一次登录会话：本机主客户端（mode=host）或子客户端（mode=remote）。"""

    def __init__(self, mode="host", base="", token="", name="", role="user",
                 perms=None, server_name="", user_agent="", owner=False,
                 allow_multi_device=False):
        self.mode = mode
        self.base = str(base or "").rstrip("/")
        self.token = token or ""
        self.name = name or ""
        self.role = role or "user"
        self.owner = bool(owner)                    # 主账号（本机主客户端只能用主账号登录）
        self.allow_multi_device = bool(allow_multi_device)
        self.perms = dict(perms or {})
        self.server_name = server_name or ""
        self.user_agent = user_agent or ""
        self.kicked = False
        self.on_kicked = None
        self._hb_stop = threading.Event()
        self._hb_thread = None

    # ---------- 基本属性 ----------
    @property
    def is_admin(self):
        return str(self.role) == "admin"

    @property
    def is_remote(self):
        return self.mode == "remote"

    def can(self, key):
        if self.is_admin:
            return True
        return bool(self.perms.get(key))

    def label(self):
        if self.mode == "host":
            return "主客户端（本机）"
        host = self.base.replace("http://", "").replace("https://", "")
        return "子客户端 @ %s" % host

    def title_suffix(self):
        return "%s · %s（%s）" % (self.name, "管理员" if self.is_admin else "子账号", self.label())

    # ---------- 接口 ----------
    def api(self, path, method="GET", params=None, body=None, timeout=25):
        if self.mode == "host":
            base = "http://127.0.0.1:%d" % int(load_config().get("port") or DEFAULT_PORT)
            if getattr(self, "_port", 0):
                base = "http://127.0.0.1:%d" % int(self._port)
        else:
            base = self.base
        ok, obj = http_json(base, path, method=method, params=params, body=body,
                            token=self.token, timeout=timeout)
        if (not ok) and isinstance(obj, dict) and obj.get("_status") in (401,):
            self._mark_kicked()
        return ok, obj

    def _mark_kicked(self):
        if self.kicked:
            return
        self.kicked = True
        try:
            if callable(self.on_kicked):
                self.on_kicked()
        except Exception:
            pass

    def logout(self):
        try:
            self.api("/api/auth/logout", "POST", body={}, timeout=6)
        except Exception:
            pass
        self.token = ""

    # ---------- 心跳（在线设备列表用） ----------
    def start_heartbeat(self, interval=HEARTBEAT_SEC):
        if self._hb_thread or not self.base and self.mode == "remote":
            return
        self._hb_stop.clear()

        def loop():
            while not self._hb_stop.wait(max(10, int(interval))):
                self.ping_server()

        self._hb_thread = threading.Thread(target=loop, daemon=True)
        self._hb_thread.start()

    def stop_heartbeat(self):
        try:
            self._hb_stop.set()
        except Exception:
            pass

    def ping_server(self):
        if not self.token:
            return False
        ok, obj = self.api("/api/client/info", "POST", body={
            "mode": self.mode, "pc": pc_name(), "win_user": win_user(),
            "dev_id": device_id(), "addr": local_ip()}, timeout=8)
        return bool(ok and isinstance(obj, dict) and obj.get("ok"))


def _after_login(mode, base, res, server_name=""):
    """登录成功后的统一收尾：取权限表 + 建 Session。"""
    name = str(res.get("name") or "")
    role = str(res.get("role") or "user")
    token = str(res.get("token") or "")
    perms = res.get("perms") if isinstance(res.get("perms"), dict) else None
    a = res.get("perms") if isinstance(res.get("perms"), dict) else None
    owner = bool(res.get("owner"))
    multi = bool(res.get("allow_multi_device"))
    if a is None:
        ok, st = http_json(base, "/api/auth/state", token=token, timeout=10)
        if ok and isinstance(st, dict):
            a = st.get("perms") or {}
            name = name or str(st.get("user") or "")
            role = str(st.get("role") or role)
            owner = bool(st.get("owner"))
            multi = bool(st.get("allow_multi_device"))
    s = Session(mode=mode, base=base, token=token, name=name, role=role,
                perms=a or {}, server_name=server_name, owner=owner,
                allow_multi_device=multi)
    return s, ""


def login(base, name, pw, mode="remote", server_name=""):
    """登录 → (Session, '') 或 (None, 原因)。mode='host' 时 base 一般是 http://127.0.0.1:port。"""
    base = norm_base(base)
    if not base:
        return None, "请先填主客户端地址（例如 192.168.1.5）"
    if not str(name or "").strip() or not pw:
        return None, "账号和密码都要填"
    ok, st = http_json(base, "/api/auth/state", timeout=8)
    if not ok:
        return None, human_err(st, base)
    if isinstance(st, dict) and st.get("need_setup"):
        if mode == "host":
            return None, "还没设置管理员账号，请在「首次设置」里创建"
        return None, "主客户端还没设置管理员账号，请先在那台电脑上设置"
    ok, res = http_json(base, "/api/auth/login", "POST", body={
        "name": str(name).strip(), "pw": pw, "dev_id": device_id(),
        "model": "Windows 桌面版", "pc": pc_name(), "win_user": win_user(),
        "kind": "desktop", "mode": mode}, timeout=15)
    if not ok or not isinstance(res, dict) or not res.get("ok"):
        return None, human_err(res, base)
    return _after_login(mode, base, res, server_name)


def setup(base, name, pw):
    """首次设置管理员（只在主机本机允许）→ (Session, '') 或 (None, 原因)。"""
    base = norm_base(base)
    if not base:
        return None, "本机服务地址不对"
    if not str(name or "").strip() or not pw:
        return None, "账号和密码都要填"
    if len(str(pw)) < 4:
        return None, "密码至少 4 位"
    ok, res = http_json(base, "/api/auth/setup", "POST", body={
        "name": str(name).strip(), "pw": pw, "dev_id": device_id(),
        "model": "Windows 桌面版", "pc": pc_name(), "win_user": win_user(),
        "kind": "desktop"}, timeout=15)
    if not ok or not isinstance(res, dict) or not res.get("ok"):
        return None, human_err(res, base)
    return _after_login("host", base, res)


def server_state(base):
    """探一下这个地址上是不是主客户端 → (ok, {'need_setup','logged_in','user','name'...})。"""
    base = norm_base(base)
    if not base:
        return False, {"error": "地址没填"}
    ok, st = http_json(base, "/api/auth/state", timeout=6)
    if not ok:
        return False, st
    return True, st if isinstance(st, dict) else {}
