# -*- coding: utf-8 -*-
"""对外访问设置（域名 / frp 隧道 / HTTPS 证书 / 一键启动）—— 逻辑层，无界面。

把原来「安装向导里填的 frp 服务器 + token + 证书两个文件」搬进软件：
  · 配置存在程序目录的 kuaimai_gateway.json
  · 保存时按同一套模板生成 frp\\frpc.toml（和安装包生成的一模一样）
  · 证书：选 .crt / .key 两个文件 → 校验是不是一对 → 放成
    kuaimai_https\\lego\\certificates\\<域名>.crt / .key
  · 启动/重启：frpc（有开机自启计划任务就走任务，否则直接起进程）+ HTTPS 中转（km_https）
  · 开机自启：建/删计划任务「KuaimaiScan 启动」「KuaimaiFrpc」

主客户端那台才需要这些；子客户端不用管。
"""
import io
import json
import os
import re
import socket
import ssl
import subprocess
import sys
import time
from datetime import datetime

DEFAULT_SERVER = "106.52.122.158"
DEFAULT_SERVER_PORT = 7000
DEFAULT_HTTPS_PORT = 9443
DEFAULT_WEB_PORT = 8790
TASK_START = "KuaimaiScan 启动"
TASK_FRPC = "KuaimaiFrpc"

BASE = ""          # 程序目录（测试里可以改）


def _default_base():
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


BASE = _default_base()


def set_base(path):
    global BASE
    BASE = str(path or "")
    return BASE


def base():
    return BASE


def paths():
    return {
        "cfg": os.path.join(BASE, "kuaimai_gateway.json"),
        "frp_dir": os.path.join(BASE, "frp"),
        "frpc": os.path.join(BASE, "frp", "frpc.exe"),
        "frpc_toml": os.path.join(BASE, "frp", "frpc.toml"),
        "https_dir": os.path.join(BASE, "kuaimai_https"),
        "relay_exe": os.path.join(BASE, "kuaimai_https", "km_https.exe"),
        "relay_py": os.path.join(BASE, "kuaimai_https", "km_https.py"),
        "cert_dir": os.path.join(BASE, "kuaimai_https", "lego", "certificates"),
        "autostart_ps1": os.path.join(BASE, "装开机自启.ps1"),
    }


# ---------------------------------------------------------------- 配置
def load_config():
    p = paths()["cfg"]
    d = {}
    try:
        with io.open(p, encoding="utf-8") as f:
            d = json.load(f)
    except Exception:
        d = {}
    if not isinstance(d, dict):
        d = {}
    out = {"domain": str(d.get("domain") or "").strip(),
           "server_addr": str(d.get("server_addr") or DEFAULT_SERVER).strip(),
           "server_port": int(d.get("server_port") or DEFAULT_SERVER_PORT),
           "token": str(d.get("token") or ""),
           "https_port": int(d.get("https_port") or DEFAULT_HTTPS_PORT),
           "web_port": int(d.get("web_port") or DEFAULT_WEB_PORT),
           "expose_443": bool(d.get("expose_443", True))}
    return out


def save_config(cfg):
    try:
        with io.open(paths()["cfg"], "w", encoding="utf-8") as f:
            f.write(json.dumps(cfg, ensure_ascii=False, indent=2))
        return True, ""
    except Exception as e:
        return False, str(e)[:150]


def frpc_toml(cfg):
    """和安装包生成的内容保持同一套模板（多了就照抄，别改格式）。"""
    crlf = "\r\n"
    toml = ('serverAddr = "%s"' % str(cfg.get("server_addr") or DEFAULT_SERVER).strip() + crlf +
            "serverPort = %d" % int(cfg.get("server_port") or DEFAULT_SERVER_PORT) + crlf +
            'auth.method = "token"' + crlf +
            'auth.token = "%s"' % str(cfg.get("token") or "") + crlf +
            'log.to = "%s"' % (paths()["frp_dir"].replace("\\", "/") + "/frpc.log") + crlf +
            'log.level = "info"' + crlf + crlf +
            "[[proxies]]" + crlf +
            'name = "kuaimai-https-9443"' + crlf +
            'type = "tcp"' + crlf +
            'localIP = "127.0.0.1"' + crlf +
            "localPort = %d" % int(cfg.get("https_port") or DEFAULT_HTTPS_PORT) + crlf +
            "remotePort = %d" % int(cfg.get("https_port") or DEFAULT_HTTPS_PORT))
    if cfg.get("expose_443", True):
        toml += (crlf + crlf + "[[proxies]]" + crlf +
                 'name = "kuaimai-https-443"' + crlf +
                 'type = "tcp"' + crlf +
                 'localIP = "127.0.0.1"' + crlf +
                 "localPort = %d" % int(cfg.get("https_port") or DEFAULT_HTTPS_PORT) + crlf +
                 "remotePort = 443")
    return toml + crlf


def write_frpc_toml(cfg):
    p = paths()["frpc_toml"]
    try:
        try:
            os.makedirs(os.path.dirname(p), exist_ok=True)
        except Exception:
            pass
        with io.open(p, "w", encoding="utf-8", newline="") as f:
            f.write(frpc_toml(cfg))
        return True, ""
    except Exception as e:
        return False, str(e)[:150]


def public_url(cfg=None):
    cfg = cfg or load_config()
    dom = str(cfg.get("domain") or "").strip()
    if not dom:
        return ""
    return "https://%s:%d/" % (dom, int(cfg.get("https_port") or DEFAULT_HTTPS_PORT))


# ---------------------------------------------------------------- 证书
def _parse_cert(path):
    """读 pem 证书 → {domains, not_after}；失败返回 {}。"""
    out = {}
    try:
        info = ssl._ssl._test_decode_cert(path)     # 只读文件，不联网
    except Exception:
        return out
    names = []
    try:
        for _k, v in (info.get("subject") or ()):        # CN
            if _k == "commonName" and v:
                names.append(str(v))
    except Exception:
        pass
    try:
        for _k, v in (info.get("subjectAltName") or ()):  # SAN
            if _k.lower() == "dns" and v:
                names.append(str(v))
            elif _k.lower() in ("ip address", "ip") and v:
                names.append(str(v))
    except Exception:
        pass
    seen = []
    for n in names:
        if n not in seen:
            seen.append(n)
    out["names"] = seen
    out["domain"] = seen[0] if seen else ""
    na = str(info.get("notAfter") or "")
    out["not_after_raw"] = na
    try:
        parts = na.split()
        if len(parts) >= 4:
            t = datetime.strptime(" ".join(parts[:4]), "%b %d %H:%M:%S %Y")
            out["not_after"] = t.strftime("%Y-%m-%d")
            out["days_left"] = (t - datetime.now()).days
    except Exception:
        pass
    return out


def check_pair(crt, key):
    """校验 .crt 和 .key 是不是一对（用 ssl 真加载一次）。→ (ok, 说明)"""
    for f in (crt, key):
        if not f or not os.path.exists(f):
            return False, "文件不存在：%s" % f
    try:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(certfile=crt, keyfile=key)
    except Exception as e:
        return False, "证书和私钥不匹配（或格式不对）：%s" % str(e)[:120]
    return True, ""


def cert_pairs():
    """现有证书清单：[{domain, crt, key, not_after, days_left, ok}]（新的排前面）。"""
    d = paths()["cert_dir"]
    out = []
    try:
        names = os.listdir(d)
    except Exception:
        return out
    for n in sorted(set([os.path.splitext(x)[0] for x in names])):
        crt = os.path.join(d, n + ".crt")
        key = os.path.join(d, n + ".key")
        if not os.path.exists(crt):
            continue
        info = _parse_cert(crt)
        out.append({"name": n, "crt": crt, "key": key,
                    "has_key": os.path.exists(key),
                    "domain": info.get("domain") or n,
                    "names": info.get("names") or [],
                    "not_after": info.get("not_after") or "",
                    "days_left": info.get("days_left"),
                    "mtime": os.path.getmtime(crt)})
    out.sort(key=lambda x: -x["mtime"])
    return out


def install_cert(crt_src, key_src, domain=""):
    """把选中的两个文件放成 <域名>.crt / <域名>.key。→ (ok, 说明, 域名)"""
    ok, msg = check_pair(crt_src, key_src)
    if not ok:
        return False, msg, ""
    info = _parse_cert(crt_src)
    dom = str(domain or info.get("domain") or "").strip()
    if dom:
        dom = re.sub(r"[^A-Za-z0-9._-]", "", dom).strip(".-_")
        if (not dom) or (".." in dom) or (not re.search(r"[A-Za-z0-9]", dom)):
            dom = ""                                  # 手填的域名不像域名 → 就用证书里的域名
    if not dom:
        dom = str(info.get("domain") or "").strip()
        dom = re.sub(r"[^A-Za-z0-9._-]", "", dom).strip(".-_")
    if (not dom) or (".." in dom) or (not re.search(r"[A-Za-z0-9]", dom)):
        return False, "从证书里读不出域名，请手填域名后再装", ""
    # 去掉 Cloudflare 那种 _bundle 后缀，和安装向导一致
    if dom.lower().endswith("_bundle"):
        dom = dom[:-7]
    if not dom:
        return False, "域名不合法", ""
    d = paths()["cert_dir"]
    try:
        os.makedirs(d, exist_ok=True)
        with io.open(crt_src, "rb") as f:
            data_c = f.read()
        with io.open(key_src, "rb") as f:
            data_k = f.read()
        with io.open(os.path.join(d, dom + ".crt"), "wb") as f:
            f.write(data_c)
        with io.open(os.path.join(d, dom + ".key"), "wb") as f:
            f.write(data_k)
    except Exception as e:
        return False, "写入证书目录失败：%s" % str(e)[:120], ""
    ok2, msg2 = check_pair(os.path.join(d, dom + ".crt"), os.path.join(d, dom + ".key"))
    if not ok2:
        return False, msg2, dom
    cfg = load_config()
    if not cfg.get("domain"):
        cfg["domain"] = dom
        save_config(cfg)
    return True, "%s（%s）" % (dom, (info.get("not_after") or "到期日未知")), dom


# ---------------------------------------------------------------- 端口 / 进程
def port_open(port, host="127.0.0.1", timeout=0.6):
    s = socket.socket()
    s.settimeout(timeout)
    try:
        s.connect((host, int(port)))
        return True
    except Exception:
        return False
    finally:
        try:
            s.close()
        except Exception:
            pass


def _run(cmd, timeout=15, hide=True):
    kw = {}
    if hide and os.name == "nt":
        kw["creationflags"] = 0x08000000        # CREATE_NO_WINDOW
    try:
        p = subprocess.run(cmd, capture_output=True, timeout=timeout, **kw)
        out = (p.stdout or b"").decode("gbk", "replace") + (p.stderr or b"").decode("gbk", "replace")
        return p.returncode, out
    except Exception as e:
        return 1, str(e)[:200]


def proc_running(image):
    """tasklist 查进程（image 例：frpc.exe / km_https.exe）。"""
    rc, out = _run(["tasklist", "/FI", "IMAGENAME eq %s" % image])
    return (image.lower() in (out or "").lower()) and ("no tasks" not in (out or "").lower())


def task_state(name):
    rc, out = _run(["schtasks", "/Query", "/TN", name, "/FO", "LIST"])
    if rc != 0:
        return ""
    for line in (out or "").splitlines():
        if line.lower().startswith(("status", "状态")):
            return line.split(":", 1)[-1].strip()
    return "已注册"


def has_autostart():
    return bool(task_state(TASK_START)) and bool(task_state(TASK_FRPC))


def set_autostart(on):
    """开：用安装包里那个 装开机自启.ps1；关：删掉两个计划任务。"""
    if on:
        ps1 = paths()["autostart_ps1"]
        if not os.path.exists(ps1):
            return False, "找不到 装开机自启.ps1（在程序目录里）"
        rc, out = _run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", ps1], timeout=60)
        return (rc == 0), (out or "").strip()[-200:]
    for t in (TASK_START, TASK_FRPC):
        _run(["schtasks", "/Delete", "/TN", t, "/F"], timeout=30)
    return True, "已关闭开机自启"


def start_frpc():
    p = paths()
    if not os.path.exists(p["frpc"]):
        return False, "找不到 frp\\frpc.exe"
    if not os.path.exists(p["frpc_toml"]):
        return False, "还没有 frpc.toml：先在设置里保存一次配置"
    stop_frpc()
    if task_state(TASK_FRPC):
        rc, out = _run(["schtasks", "/Run", "/TN", TASK_FRPC], timeout=30)
        time.sleep(1.2)
        return proc_running("frpc.exe"), (out or "").strip()[-150:]
    try:
        kw = {}
        if os.name == "nt":
            kw["creationflags"] = 0x08000000
        subprocess.Popen([p["frpc"], "-c", p["frpc_toml"]], cwd=p["frp_dir"],
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw)
    except Exception as e:
        return False, str(e)[:150]
    time.sleep(1.0)
    return proc_running("frpc.exe"), ""


def stop_frpc():
    _run(["taskkill", "/IM", "frpc.exe", "/F"], timeout=20)
    return True, ""


def start_relay(cfg=None):
    """起 HTTPS 中转（9443 → 127.0.0.1:8790）。"""
    cfg = cfg or load_config()
    p = paths()
    port = int(cfg.get("https_port") or DEFAULT_HTTPS_PORT)
    if not os.path.exists(os.path.join(p["cert_dir"])):
        return False, "还没有证书目录：先把 .crt/.key 装进来"
    if not cert_pairs():
        return False, "证书目录里没有证书：先装证书"
    stop_relay()
    dom = str(cfg.get("domain") or "").strip()
    if os.path.exists(p["relay_exe"]):
        cmd = [p["relay_exe"], "--port", str(port)]
        exe_dir = p["https_dir"]
    elif os.path.exists(p["relay_py"]):
        cmd = [sys.executable.replace("python.exe", "pythonw.exe"), p["relay_py"], "--port", str(port)]
        exe_dir = p["https_dir"]
    else:
        return False, "找不到 kuaimai_https\\km_https.exe（也没有 .py）"
    env = dict(os.environ)
    if dom:
        env["KM_DOMAIN"] = dom
    try:
        kw = {}
        if os.name == "nt":
            kw["creationflags"] = 0x08000000
        subprocess.Popen(cmd, cwd=exe_dir, env=env,
                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **kw)
    except Exception as e:
        return False, str(e)[:150]
    for _ in range(12):
        time.sleep(0.5)
        if port_open(port):
            return True, ""
    return False, "起是起了，但 %d 端口还没在听（看 kuaimai_https\\km_https.log）" % port


def stop_relay():
    _run(["taskkill", "/IM", "km_https.exe", "/F"], timeout=20)
    return True, ""


def status():
    """一眼看现状：外网地址 / 端口 / 进程 / 证书。"""
    cfg = load_config()
    pairs = cert_pairs()
    best = None
    for c in pairs:
        if cfg.get("domain") and cfg["domain"] in (c.get("names") or []):
            best = c
            break
    best = best or (pairs[0] if pairs else None)
    return {
        "cfg": cfg,
        "url": public_url(cfg),
        "web_open": port_open(int(cfg.get("web_port") or DEFAULT_WEB_PORT)),
        "https_open": port_open(int(cfg.get("https_port") or DEFAULT_HTTPS_PORT)),
        "frpc": proc_running("frpc.exe"),
        "relay": proc_running("km_https.exe"),
        "cert": best,
        "cert_count": len(pairs),
        "autostart": has_autostart(),
        "frpc_toml": os.path.exists(paths()["frpc_toml"]),
    }
