# -*- coding: utf-8 -*-
"""抓「多平台获取单号」点击后的网络请求（URL/参数/状态/返回片段）。

用法：python tools/erp_trace_net.py [按钮关键字] [监听秒数]
默认：多平台获取单号 25 秒
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

BTN = sys.argv[1] if len(sys.argv) > 1 else "多平台获取单号"
SECS = int(sys.argv[2]) if len(sys.argv) > 2 else 25
OUT = os.path.join(os.environ.get("TEMP", "."), "erp_net.txt")

t = page_ws()
ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=30, suppress_origin=True)
_id = [0]


def send(method, params=None):
    _id[0] += 1
    ws.send(json.dumps({"id": _id[0], "method": method, "params": params or {}}))
    return _id[0]


send("Network.enable", {"maxTotalBufferSize": 30000000, "maxResourceBufferSize": 8000000})
send("Runtime.enable")
CLICK = """
(function(){
 var bar=document.querySelector('div.trade-toolbar_list');
 if(!bar) return 'no-toolbar';
 var items=Array.from(bar.querySelectorAll('a.toolbar-menu_item'));
 for(var k=0;k<items.length;k++){var s=(items[k].innerText||'').trim();
   if(s.indexOf(%s)>=0){ items[k].click(); return 'clicked:'+s; }}
 return 'not-found';
})()
""" % json.dumps(BTN)
send("Runtime.evaluate", {"expression": CLICK, "returnByValue": True})

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
        reqs[p["requestId"]] = {"url": p["request"]["url"], "method": p["request"]["method"],
                                "post": (p["request"].get("postData") or "")[:400], "status": "-"}
    elif m == "Network.responseReceived":
        p = msg["params"]
        if p["requestId"] in reqs:
            reqs[p["requestId"]]["status"] = p["response"]["status"]

KW = ("waybill", "express", "print", "trade", "audit", "getWayBill", "getExpress", "bill")
L = []
L.append("按钮: %s  监听 %ds  抓到 %d 条请求" % (BTN, SECS, len(reqs)))
for r in reqs.values():
    u = r["url"]
    if any(k.lower() in u.lower() for k in KW):
        L.append("----")
        L.append("%s %s [%s]" % (r["method"], u[:220], r["status"]))
        if r["post"]:
            L.append("  入参: " + r["post"][:400])
io.open(OUT, "w", encoding="utf-8").write("\n".join(L) if len(L) > 1 else (L[0] + "\n（没有相关请求）"))
print("OK", OUT, "共", len(reqs), "条")
