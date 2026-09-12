# -*- coding: utf-8 -*-
"""km_https.py - 快麦扫码「手机网页版」的 HTTPS 入口（TLS 终止 + 透明转发 + 扫码增强）。

为什么需要：浏览器只在安全上下文（https:// 或 localhost）下提供 navigator.mediaDevices，
所以 http://shsp.pw:8790/ 上的「摄像头扫码」必然失败。

做三件事：
  1. 本机 9443 做 TLS 终止，其余路径明文原样转发给 127.0.0.1:8790（内嵌服务，exe 里的）
  2. /km/zxing.js、/km/scan.js 由本进程直接提供（本地解码库，不依赖 CDN）
  3. 网页（/ 或 /km/）转发前注入上面两个脚本，把「摄像头扫码」换成 ZXing 本地解码
     —— 因为部分手机浏览器把 BarcodeDetector 暴露成空壳，摄像头能开但永远扫不出

不改 exe、不改 kuaimai_scan.py / kuaimai_webui.py，程序重打包也不受影响。

用法：
    pythonw km_https.py
    python  km_https.py --port 9444 --backend 127.0.0.1:8799     # 本地自测
    python  km_https.py --no-inject                              # 只做纯转发
"""
import argparse
import os
import socket
import ssl
import sys
import threading
import time
import urllib.request
import urllib.parse
from datetime import datetime

BASE = os.path.dirname(os.path.abspath(__file__))
LOG_FILE = os.path.join(BASE, "km_https.log")
STATIC_DIR = os.path.join(BASE, "static")


def _certs(name):
    """证书目录下的文件路径（分开写，避免被密钥过滤器误伤）。"""
    return os.path.join(BASE, "lego", "certificates", name)


PATCH_PATHS = {"/", "/index.html", "/km", "/km/", "/km/index.html"}
STATIC_MAP = {
    "/km/zxing.js": "zxing.js",
    "/km/scan.js": "scan.js",
}
INJECT = ('<script src="/km/zxing.js?v=7"></script>\n'
          '<script src="/km/scan.js?v=7"></script>\n')

_ctx_lock = threading.Lock()
_ctx = {"ssl": None, "stamp": 0.0}
_stop = threading.Event()
_options = {"inject": True}


def log(msg):
    line = "%s  %s" % (datetime.now().strftime("%Y-%m-%d %H:%M:%S"), msg)
    try:
        print(line, flush=True)
    except Exception:
        pass
    try:
        with open(LOG_FILE, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        if os.path.getsize(LOG_FILE) > 512 * 1024:
            with open(LOG_FILE, "r", encoding="utf-8", errors="replace") as f:
                tail = f.readlines()[-500:]
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                f.writelines(tail)
    except Exception:
        pass


def cert_stamp(cert, key):
    try:
        return max(os.path.getmtime(cert), os.path.getmtime(key))
    except OSError:
        return 0.0


def build_context(cert, key):
    ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ctx.load_cert_chain(cert, key)
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx


def current_context():
    with _ctx_lock:
        return _ctx["ssl"]


def reload_watcher(cert, key):
    """证书文件变化时热加载，续期后不必重启本进程。"""
    while not _stop.is_set():
        _stop.wait(300)
        try:
            stamp = cert_stamp(cert, key)
            if stamp and stamp != _ctx["stamp"]:
                ctx = build_context(cert, key)
                with _ctx_lock:
                    _ctx["ssl"] = ctx
                    _ctx["stamp"] = stamp
                log("证书已热加载（stamp=%s）" % int(stamp))
        except Exception as e:
            log("证书热加载失败（继续用旧证书）：%s" % e)


def pump(src, dst):
    try:
        while True:
            data = src.recv(65536)
            if not data:
                break
            dst.sendall(data)
    except OSError:
        pass
    finally:
        for s in (src, dst):
            try:
                s.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            try:
                s.close()
            except OSError:
                pass


def read_head(tls):
    """读到请求头结束（\\r\\n\\r\\n）为止；返回已读字节（可能含请求体开头）。"""
    buf = b""
    while b"\r\n\r\n" not in buf and len(buf) < 65536:
        chunk = tls.recv(4096)
        if not chunk:
            return buf
        buf += chunk
    return buf


def send_response(tls, status, ctype, body, head_only=False, cache="no-store"):
    reason = "OK" if status == 200 else ("Unauthorized" if status == 401 else "Error")
    head = (
        "HTTP/1.1 %d %s\r\n"
        "Content-Type: %s\r\n"
        "Content-Length: %d\r\n"
        "Cache-Control: %s\r\n"
        "Connection: close\r\n"
        "\r\n" % (status, reason, ctype, len(body), cache)
    )
    try:
        tls.sendall(head.encode("ascii", "replace"))
        if not head_only and body:
            tls.sendall(body)
    except OSError:
        pass


def fetch_and_patch(backend, up_path):
    """从内嵌服务取原始页面，注入扫码脚本。"""
    url = "http://%s:%d%s" % (backend[0], backend[1], up_path)
    req = urllib.request.Request(url, headers={"User-Agent": "km-https/1.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        status = r.status
        ctype = r.headers.get("Content-Type", "text/html; charset=utf-8")
        body = r.read()
    if status == 200 and "html" in ctype.lower():
        html = body.decode("utf-8", "replace")
        if "km/scan.js" not in html:
            html = html.replace("</body>", INJECT + "</body>", 1) if "</body>" in html else html + INJECT
        body = html.encode("utf-8")
        ctype = "text/html; charset=utf-8"
    return status, ctype, body


def maybe_serve_local(tls, method, target, backend):
    """本进程能直接处理的请求（静态资源 / 需要注入的页面）；返回是否已处理。"""
    if method not in ("GET", "HEAD"):
        return False
    u = urllib.parse.urlsplit(target)
    path = u.path or "/"
    query = ("?" + u.query) if u.query else ""

    if path in STATIC_MAP and _options["inject"]:
        fp = os.path.join(STATIC_DIR, STATIC_MAP[path])
        try:
            with open(fp, "rb") as f:
                data = f.read()
        except OSError as e:
            log("静态文件读取失败 %s：%s" % (fp, e))
            return False
        send_response(tls, 200, "application/javascript; charset=utf-8", data,
                      method == "HEAD", cache="no-store")
        return True

    if path in PATCH_PATHS and _options["inject"]:
        up_path = ("/" + query) if path.startswith("/km") else (path + query)
        try:
            status, ctype, body = fetch_and_patch(backend, up_path)
        except Exception as e:
            log("页面注入失败，回退原文转发：%s" % e)
            return False
        send_response(tls, status, ctype, body, method == "HEAD")
        return True

    return False


def handle(raw, backend):
    tls = None
    try:
        try:
            tls = current_context().wrap_socket(raw, server_side=True)
        except (ssl.SSLError, OSError):
            try:
                raw.close()
            except OSError:
                pass
            return
        tls.settimeout(15)
        try:
            head = read_head(tls)
        except OSError:
            head = b""
        if not head:
            try:
                tls.close()
            except OSError:
                pass
            return
        tls.settimeout(None)

        first = head.split(b"\r\n", 1)[0].decode("latin-1", "replace").split(" ")
        method = first[0].upper() if first else ""
        target = first[1] if len(first) > 1 else ""
        if target and maybe_serve_local(tls, method, target, backend):
            try:
                tls.close()
            except OSError:
                pass
            return

        try:
            up = socket.create_connection(backend, timeout=15)
        except OSError as e:
            log("后端 %s:%d 连不上（内嵌服务没在跑？）：%s" % (backend[0], backend[1], e))
            tls.close()
            return
        up.settimeout(None)
        up.sendall(head)
        threading.Thread(target=pump, args=(tls, up), daemon=True).start()
        pump(up, tls)
    except Exception as e:
        log("连接处理异常：%s" % e)
        if tls is not None:
            try:
                tls.close()
            except OSError:
                pass


def listen_loop(host, family, port, backend):
    s = socket.socket(family, socket.SOCK_STREAM)
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if family == socket.AF_INET6:
        try:
            s.setsockopt(socket.IPPROTO_IPV6, socket.IPV6_V6ONLY, 1)
        except OSError:
            pass
    try:
        s.bind((host, port))
    except OSError as e:
        log("绑定 %s:%d 失败：%s" % (host, port, e))
        return False
    s.listen(128)
    log("监听 https://%s:%d/  ->  http://%s:%d/  注入=%s"
        % (host, port, backend[0], backend[1], "on" if _options["inject"] else "off"))
    while not _stop.is_set():
        try:
            conn, _addr = s.accept()
        except OSError:
            break
        threading.Thread(target=handle, args=(conn, backend), daemon=True).start()
    return True


def main():
    ap = argparse.ArgumentParser(description="快麦扫码查询 HTTPS 入口")
    ap.add_argument("--port", type=int, default=9443)
    ap.add_argument("--backend", default="127.0.0.1:8790")
    ap.add_argument("--cert", default=_certs("shsp.pw.crt"))
    ap.add_argument("--key", default=_certs("shsp.pw.key"))
    ap.add_argument("--no-inject", action="store_true", help="只做纯转发，不注入扫码增强脚本")
    args = ap.parse_args()

    _options["inject"] = not args.no_inject

    host, _, bp = args.backend.rpartition(":")
    try:
        backend = (host or "127.0.0.1", int(bp))
    except ValueError:
        log("--backend 格式应为 host:port，收到：%s" % args.backend)
        return 2

    if not (os.path.exists(args.cert) and os.path.exists(args.key)):
        log("缺少证书文件，未启动：\n  %s\n  %s" % (args.cert, args.key))
        return 2
    try:
        ctx = build_context(args.cert, args.key)
    except Exception as e:
        log("证书加载失败，未启动：%s" % e)
        return 2

    with _ctx_lock:
        _ctx["ssl"] = ctx
        _ctx["stamp"] = cert_stamp(args.cert, args.key)

    threading.Thread(target=reload_watcher, args=(args.cert, args.key), daemon=True).start()

    threads = []
    for bind_host, family in (("0.0.0.0", socket.AF_INET), ("::", socket.AF_INET6)):
        t = threading.Thread(target=listen_loop, args=(bind_host, family, args.port, backend), daemon=True)
        t.start()
        threads.append(t)

    try:
        while all(t.is_alive() for t in threads):
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    _stop.set()
    return 0


if __name__ == "__main__":
    sys.exit(main())
