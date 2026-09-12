# -*- coding: utf-8 -*-
"""_selftest.py - 本地自测 km_https.py：临时自签证书 + 桩后端，验证 TLS 终止与转发。

用法：python _selftest.py   （通过打印 PASS/FAIL，不依赖外网、不需要真证书）
"""
import http.server
import os
import socket
import ssl
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import datetime, timedelta, timezone

BASE = os.path.dirname(os.path.abspath(__file__))
TMP = os.path.join(BASE, "_selftest")
PORT = 9444
BACKEND_PORT = 8799
BODY = b"STUB-OK\n"


def make_cert():
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "shsp.pw")])
    now = datetime.now(timezone.utc)
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now - timedelta(days=1))
        .not_valid_after(now + timedelta(days=30))
        .add_extension(x509.SubjectAlternativeName([x509.DNSName("shsp.pw")]), critical=False)
        .sign(key, hashes.SHA256())
    )
    os.makedirs(TMP, exist_ok=True)
    crt = os.path.join(TMP, "test.crt")
    k = os.path.join(TMP, "test.key")
    with open(crt, "wb") as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    with open(k, "wb") as f:
        f.write(key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        ))
    return crt, k


class Stub(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        payload = ("PATH=%s\n" % self.path).encode() + BODY
        self.send_response(200)
        self.send_header("Content-Type", "text/plain")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *a):
        pass


def fetch(url, timeout=8):
    ctx = ssl.create_default_context()
    ctx.check_hostname = False
    ctx.verify_mode = ssl.CERT_NONE
    with urllib.request.urlopen(url, context=ctx, timeout=timeout) as r:
        return r.status, r.read()


def main():
    crt, key = make_cert()
    print("临时证书:", crt)

    stub = http.server.ThreadingHTTPServer(("127.0.0.1", BACKEND_PORT), Stub)
    threading.Thread(target=stub.serve_forever, daemon=True).start()
    time.sleep(0.3)

    proc = subprocess.Popen(
        [sys.executable, os.path.join(BASE, "km_https.py"),
         "--port", str(PORT), "--backend", "127.0.0.1:%d" % BACKEND_PORT,
         "--cert", crt, "--key", key],
        stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
    )

    failures = []
    try:
        for _ in range(40):
            time.sleep(0.25)
            try:
                with socket.create_connection(("127.0.0.1", PORT), timeout=1):
                    break
            except OSError:
                continue
        else:
            failures.append("中转未在 3 秒内监听 %d" % PORT)

        if not failures:
            status, body = fetch("https://127.0.0.1:%d/api/status?k=ABC123" % PORT)
            print("IPv4  ->", status, body)
            if status != 200 or BODY not in body:
                failures.append("IPv4 转发内容不对")
            if b"/api/status?k=ABC123" not in body:
                failures.append("查询串没有透传")

        # IPv6（本机有 ::1 时才测）
        try:
            with socket.create_connection(("::1", PORT), timeout=2):
                status6, body6 = fetch("https://[::1]:%d/api/status?k=ABC123" % PORT)
                print("IPv6  ->", status6, body6)
            if status6 != 200 or BODY not in body6:
                failures.append("IPv6 转发内容不对")
        except OSError as e:
            print("IPv6 跳过:", e)

        # 明文访问同一端口应当失败（证明确实是 TLS）
        try:
            req = urllib.request.urlopen("http://127.0.0.1:%d/" % PORT, timeout=3)
            req.read()
            failures.append("明文 HTTP 竟然成功了，TLS 没生效")
        except Exception as e:
            print("明文访问被拒（预期）:", type(e).__name__)

    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        stub.shutdown()
        out = proc.stdout.read() if proc.stdout else ""
        if out.strip():
            print("---- 中转日志 ----")
            print(out.strip()[:1500])

    print()
    if failures:
        print("FAIL:", "; ".join(failures))
        return 1
    print("PASS: TLS 终止 + 转发 + 查询串透传 都正常")
    return 0


if __name__ == "__main__":
    sys.exit(main())
