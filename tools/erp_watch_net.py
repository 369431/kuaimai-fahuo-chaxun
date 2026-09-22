# -*- coding: utf-8 -*-
"""只监听不操作：把页面期间发出的关键请求（URL/方法/入参/状态/返回片段）写到 %TEMP%\erp_watch.txt。

用法：python tools/erp_watch_net.py [秒数]
"""
import io
import json
import os
import sys
import time

try:                      # pythonw 下没有控制台，sys.stdout 可能是 None
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import websocket  # noqa
from erp_probe import page_ws  # noqa

SECS = int(sys.argv[1]) if len(sys.argv) > 1 else 180
OUT = os.path.join(os.environ.get("TEMP", "."), "erp_watch.txt")
SKIP = (".js", ".css", ".png", ".jpg", ".gif", ".svg", ".woff", ".ttf", ".ico", ".map", ".webp")

t = page_ws()
ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=30, suppress_origin=True)
ID = [0]


def send(m, p=None):
    ID[0] += 1
    ws.send(json.dumps({"id": ID[0], "method": m, "params": p or {}}))
    return ID[0]


send("Network.enable", {"maxTotalBufferSize": 40000000, "maxResourceBufferSize": 8000000})
send("Runtime.enable")
reqs = {}
start = time.time()
while time.time() - start < SECS:
    try:
        ws.settimeout(2)
        msg = json.loads(ws.recv())
    except Exception:
        continue
    m = msg.get("method")
    if m == "Network.requestWillBeSent":
        p = msg["params"]
        u = p["request"]["url"]
        if u.lower().split("?")[0].endswith(SKIP):
            continue
        reqs[p["requestId"]] = {"u": u, "m": p["request"]["method"],
                                "post": (p["request"].get("postData") or "")[:500],
                                "s": "-", "type": p.get("type", "")}
    elif m == "Network.responseReceived":
        p = msg["params"]
        if p["requestId"] in reqs:
            reqs[p["requestId"]]["s"] = p["response"]["status"]

KW = ("waybill", "express", "print", "trade", "audit", "bill", "order", "get", "api", "batch")
L = ["监听 %ds，共 %d 条请求" % (SECS, len(reqs)), ""]
for rid, r in reqs.items():
    hit = any(k.lower() in r["u"].lower() for k in KW)
    if not hit:
        continue
    L.append("%s %s [%s] %s" % (r["m"], r["u"][:200], r["s"], r["type"]))
    if r["post"]:
        L.append("   入参: " + r["post"][:500])
    if r["s"] == 200:
        try:
            ID[0] += 1
            ws.send(json.dumps({"id": ID[0], "method": "Network.getResponseBody",
                                "params": {"requestId": rid}}))
            while True:
                mm = json.loads(ws.recv())
                if mm.get("id") == ID[0]:
                    body = (mm.get("result") or {}).get("body") or ""
                    if body:
                        L.append("   返回: " + body.replace("\n", " ")[:400])
                    break
                if mm.get("method") == "Network.requestWillBeSent":
                    p = mm["params"]
                    reqs[p["requestId"]] = {"u": p["request"]["url"], "m": p["request"]["method"],
                                            "post": (p["request"].get("postData") or "")[:500],
                                            "s": "-", "type": p.get("type", "")}
        except Exception as e:
            L.append("   (返回体取不到: %s)" % str(e)[:60])
io.open(OUT, "w", encoding="utf-8").write("\n".join(L))
print("watch done", len(reqs))
