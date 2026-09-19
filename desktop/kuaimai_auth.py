# -*- coding: utf-8 -*-
"""网页登录账号：本地 JSON 存储，密码加盐 SHA-256；每个账号同时只允许一个登录会话。

账号文件：程序目录下 kuaimai_users.json（不进 Git，已加到 .gitignore）
"""
import glob
import hashlib
import io
import json
import math
import os
import re
import secrets
import shutil
import sys
import time
from datetime import datetime


def _default_base_dir():
    """账号文件必须跟数据文件同目录（打包后在 exe 旁边）。

    注意：打包成 exe 后 __file__ 指向 PyInstaller 的临时解包目录（_MEIxxxx），
    那里每次启动都是新的、退出还会被删 —— 账号会"每次打开都要求重新设置"。
    """
    if getattr(sys, "frozen", False):
        d = os.path.dirname(os.path.abspath(sys.executable))
        try:
            probe = os.path.join(d, ".km_auth_write_test")
            with io.open(probe, "w", encoding="utf-8") as f:
                f.write("ok")
            os.remove(probe)
            return d
        except Exception:
            pass
        alt = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "KuaimaiScan")
        try:
            os.makedirs(alt, exist_ok=True)
        except Exception:
            pass
        return alt
    return os.path.dirname(os.path.abspath(__file__))


BASE_DIR = _default_base_dir()
USERS_FILE = os.path.join(BASE_DIR, "kuaimai_users.json")


def _adopt_legacy_file():
    """老版本把账号文件写进了临时解包目录：第一次跑新版时把它接过来，免得用户再设一遍。"""
    if not getattr(sys, "frozen", False) or os.path.exists(USERS_FILE):
        return
    try:
        cands = [p for p in glob.glob(os.path.join(os.environ.get("TEMP") or "", "_MEI*", "kuaimai_users.json"))
                 if os.path.getsize(p) > 2]
        if cands:
            shutil.copy2(max(cands, key=os.path.getmtime), USERS_FILE)
    except Exception:
        pass


_adopt_legacy_file()


def _now():
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def _hash(pw, salt):
    return hashlib.sha256((str(salt) + str(pw)).encode("utf-8")).hexdigest()


def device_label(ua="", model=""):
    """把 User-Agent 变成一句人看得懂的话（机型 · 系统 · 浏览器）。

    机型优先用客户端上报的（Chrome/Edge 的 Client Hints 高熵值：Pixel 8 这种），
    拿不到就从 UA 里抠（Android 的 "SM-S9110 Build/..."）；iPhone 只能给出 iPhone。
    """
    ua = str(ua or "")
    model = str(model or "").strip()
    if not ua and not model:
        return ""
    low = ua.lower()
    if "iphone" in low:
        os_name = "iPhone"
    elif "ipad" in low:
        os_name = "iPad"
    elif "android" in low:
        os_name = "Android"
    elif "windows" in low:
        os_name = "Windows 电脑"
    elif "macintosh" in low or "mac os x" in low:
        os_name = "Mac"
    elif "linux" in low:
        os_name = "Linux"
    else:
        os_name = ""
    if "micromessenger" in low:
        app = "微信"
    elif "qqbrowser" in low:
        app = "QQ浏览器"
    elif "edg" in low:
        app = "Edge"
    elif "chrome" in low or "crios" in low:
        app = "Chrome"
    elif "firefox" in low or "fxios" in low:
        app = "Firefox"
    elif "safari" in low:
        app = "Safari"
    else:
        app = ""
    if not model:
        m = re.search(r"Android[^;]*;\s*([^;)]+?)(?:\s+Build[/)]|\s*\))", ua)
        if m and "wv" not in m.group(1).lower():
            model = m.group(1).strip()
    parts = [p for p in (model[:24], os_name, app) if p]
    return " · ".join(parts)[:48]


def _load():
    try:
        with io.open(USERS_FILE, encoding="utf-8") as f:
            d = json.load(f)
        d = d if isinstance(d, dict) else {"users": {}}
    except Exception:
        d = {"users": {}}
    now = time.time()
    b = d.get("blocked") or {}
    d["blocked"] = {k: v for k, v in b.items() if float(v or 0) > now}
    us = d.get("users") or {}
    if us:
        for _n, _u in us.items():
            if not isinstance(_u, dict):
                continue
            _u.setdefault("owner", False)
            _u.setdefault("allow_multi_device", False)
        # 迁移：一个主账号都没有时，把最早建的管理员当主账号
        if not any(u.get("owner") for u in us.values() if isinstance(u, dict)):
            adm = sorted([(u.get("created") or "", n) for n, u in us.items()
                          if isinstance(u, dict) and (u.get("role") or "") == "admin"])
            if adm:
                us[adm[0][1]]["owner"] = True
    return d


def _tokens(u):
    """一个账号当前的会话表 {kind: token}（老数据只有单个 token 也能读）。"""
    if not isinstance(u, dict):
        return {}
    t = u.get("tokens")
    if isinstance(t, dict) and t:
        return {str(k or "desktop"): str(v) for k, v in t.items() if v}
    if u.get("token"):
        return {str(u.get("kind") or "desktop"): str(u["token"])}
    return {}


def _set_tokens(u, toks):
    toks = {str(k or "desktop"): str(v) for k, v in (toks or {}).items() if v}
    u["tokens"] = toks
    u["token"] = list(toks.values())[-1] if toks else ""     # 兼容旧字段
    return toks


def _save(d):
    try:
        with io.open(USERS_FILE, "w", encoding="utf-8") as f:
            f.write(json.dumps(d, ensure_ascii=False, indent=2))
        return True
    except Exception:
        return False


def users():
    return _load().get("users") or {}


def blocked_left(dev_id):
    """这台设备还有几分钟不能登录（0 = 没被踢过 / 已经到期）。"""
    dev_id = str(dev_id or "").strip()
    if not dev_id:
        return 0
    until = float((_load().get("blocked") or {}).get(dev_id) or 0)
    left = until - time.time()
    return int(math.ceil(left / 60.0)) if left > 0 else 0


def need_setup():
    """还没有任何管理员 → 需要首次设置。"""
    us = users()
    return not any((u.get("role") == "admin") for u in us.values())


def owner_names():
    """主账号（这台电脑的主客户端只能用它登录）。"""
    return [n for n, u in users().items() if isinstance(u, dict) and u.get("owner")]


def is_owner(name):
    u = users().get(str(name or ""))
    return bool(isinstance(u, dict) and u.get("owner"))


def set_multi_device(name, flag):
    """是否允许同一账号电脑端 + 网页端同时在线。"""
    d = _load()
    u = (d.get("users") or {}).get(str(name or ""))
    if not u:
        return "账号不存在"
    u["allow_multi_device"] = bool(flag)
    if not flag:
        _set_tokens(u, {})            # 关掉后只留一个：下次登录会踢掉其它
    _save(d)
    return ""


def list_users():
    out = []
    now = time.time()
    for name, u in users().items():
        seen = float(u.get("seen_ts") or 0)
        out.append({"name": name, "role": u.get("role") or "user",
                    "owner": bool(u.get("owner")),
                    "allow_multi_device": bool(u.get("allow_multi_device")),
                    "kinds": sorted(_tokens(u).keys()),
                    "created": u.get("created") or "", "last_login": u.get("last_login") or "",
                    "online": bool(_tokens(u)), "device": u.get("device") or "",
                    "kicked_at": u.get("kicked_at") or "",
                    "pc": u.get("pc") or "", "win_user": u.get("win_user") or "",
                    "ip": u.get("ip") or "", "kind": u.get("kind") or "",
                    "seen_at": u.get("seen_at") or "",
                    "alive": (bool(_tokens(u)) and (now - seen) < 180) if seen else False})
    return sorted(out, key=lambda x: (not x["owner"], x["role"] != "admin", x["name"]))


def touch(name, ip="", pc="", win_user="", kind=""):
    """子客户端心跳：只刷新「最后活跃」和设备信息，不动会话 token。"""
    d = _load()
    u = (d.get("users") or {}).get(str(name or ""))
    if not u or not _tokens(u):
        return False
    u["seen_ts"] = time.time()
    u["seen_at"] = _now()
    if ip:
        u["ip"] = str(ip)[:45]
    if pc:
        u["pc"] = str(pc)[:64]
    if win_user:
        u["win_user"] = str(win_user)[:64]
    if kind:
        u["kind"] = str(kind)[:16]
    _save(d)
    return True


def user_perms_raw(name):
    """账号里存的原始权限表（可能是 None / 缺字段 —— 老数据）。

    只有真正保存过权限的账号才有这个字段；算成完整权限表由 kuaimai_perms.effective 负责。
    """
    u = users().get(str(name or ""))
    if not u:
        return None
    p = u.get("perms")
    return p if isinstance(p, dict) else None


def set_user_perms(name, values):
    """保存某账号的按钮权限（只写 perms 字段，不动口令/会话）。"""
    d = _load()
    us = d.setdefault("users", {})
    u = us.get(str(name or ""))
    if not u:
        return "账号不存在"
    u["perms"] = dict(values or {})
    _save(d)
    return ""


def add_user(name, pw, role="user"):
    name = str(name or "").strip()
    if not name or not pw:
        return "账号和密码不能为空"
    if len(str(pw)) < 4:
        return "密码至少 4 位"
    d = _load()
    us = d.setdefault("users", {})
    if name in us:
        return "账号已存在"
    salt = secrets.token_hex(8)
    us[name] = {"salt": salt, "hash": _hash(pw, salt), "role": role, "created": _now(),
                "token": "", "tokens": {}, "owner": False, "allow_multi_device": False,
                "last_login": "", "device": ""}
    _save(d)
    return ""


def del_user(name):
    d = _load()
    us = d.setdefault("users", {})
    u = us.get(name)
    if not u:
        return "账号不存在"
    if u.get("role") == "admin":
        admins = [n for n, x in us.items() if x.get("role") == "admin"]
        if len(admins) <= 1:
            return "至少要保留一个管理员账号"
    us.pop(name, None)
    _save(d)
    return ""


def kick(name, minutes=10):
    """把账号的当前登录踢下线，并让那台设备 minutes 分钟内不能再登录。"""
    d = _load()
    us = d.setdefault("users", {})
    u = us.get(str(name))
    if not u:
        return "账号不存在"
    dev = str(u.get("dev") or "").strip()
    _set_tokens(u, {})               # 旧会话全部立即失效
    u["kicked_at"] = _now()
    if dev:
        d.setdefault("blocked", {})[dev] = time.time() + max(1, int(minutes)) * 60
    _save(d)
    return ""


def set_password(name, pw, block_minutes=10):
    if len(str(pw or "")) < 4:
        return "密码至少 4 位"
    d = _load()
    us = d.setdefault("users", {})
    u = us.get(str(name))
    if not u:
        return "账号不存在"
    u["salt"] = secrets.token_hex(8)
    u["hash"] = _hash(pw, u["salt"])
    _set_tokens(u, {})               # 改密码后旧登录全部失效
    dev = str(u.get("dev") or "").strip()
    if block_minutes and dev:            # 管理员改别人的密码：那台设备 10 分钟内不能再登录
        d.setdefault("blocked", {})[dev] = time.time() + max(1, int(block_minutes)) * 60
    _save(d)
    return ""


def login(name, pw, device="", dev_id="", model="", pc="", win_user="", ip="", kind=""):
    """成功 → (token, '')；失败 → (None, 原因)。

    会话规则：默认一个账号只有一个会话（新登录把旧的踢掉）；
    allow_multi_device=True 时允许「电脑端 + 网页端」各一个（同端再登录会顶掉同端的旧会话）。
    """
    name = str(name or "").strip()
    dev_id = str(dev_id or "").strip()
    left = blocked_left(dev_id)
    if left:
        return None, "这台设备被踢下线了，%d 分钟后才能再登录" % left
    d = _load()
    us = d.setdefault("users", {})
    u = us.get(name)
    if not u or _hash(pw, u.get("salt") or "") != u.get("hash"):
        return None, "账号或密码不对"
    tok = secrets.token_urlsafe(24)
    k = str(kind or "desktop")[:16]
    toks = _tokens(u)
    if not u.get("allow_multi_device"):
        toks = {}                       # 只保留最新一个会话
    else:
        toks.pop(k, None)                # 同一端只留最新，另一端保持在线
    toks[k] = tok
    _set_tokens(u, toks)
    u["last_login"] = _now()
    u["device"] = device_label(device, model)
    u["ua"] = str(device or "")[:160]
    u["pc"] = str(pc or "")[:64]
    u["win_user"] = str(win_user or "")[:64]
    u["ip"] = str(ip or "")[:45]
    u["kind"] = str(kind or "")[:16]
    u["seen_ts"] = time.time()
    u["seen_at"] = _now()
    if dev_id:
        u["dev"] = dev_id
        (d.get("blocked") or {}).pop(dev_id, None)
    _save(d)
    return tok, ""


def check(token):
    """校验会话 token → {'name','role','owner','kind','allow_multi_device'} 或 None。"""
    token = str(token or "").strip()
    if not token:
        return None
    for name, u in users().items():
        if not isinstance(u, dict):
            continue
        for _k, t in _tokens(u).items():
            if t == token:
                return {"name": name, "role": u.get("role") or "user",
                        "owner": bool(u.get("owner")),
                        "kind": _k,
                        "allow_multi_device": bool(u.get("allow_multi_device"))}
    return None


def logout(token):
    d = _load()
    changed = False
    for _name, u in (d.get("users") or {}).items():
        if not isinstance(u, dict):
            continue
        toks = _tokens(u)
        hit = [k for k, t in toks.items() if t == str(token or "")]
        if hit:
            for k in hit:
                toks.pop(k, None)
            _set_tokens(u, toks)
            changed = True
    if changed:
        _save(d)
    return changed
