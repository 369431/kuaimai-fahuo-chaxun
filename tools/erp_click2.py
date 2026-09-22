# -*- coding: utf-8 -*-
"""绕过遮住工具条的浮层：ESC 收起下拉 → 临时给覆盖元素设 pointer-events:none → 真鼠标点 → 抓网络。"""
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
SECS = int(sys.argv[2]) if len(sys.argv) > 2 else 18
OUT = os.path.join(os.environ.get("TEMP", "."), "erp_click2.txt")
L = []
t = page_ws()
ws = websocket.create_connection(t["webSocketDebuggerUrl"], timeout=30, suppress_origin=True)
ID = [0]


def send(m, p=None):
    ID[0] += 1
    ws.send(json.dumps({"id": ID[0], "method": m, "params": p or {}}))
    return ID[0]


def call(m, p=None):
    want = send(m, p)
    while True:
        msg = json.loads(ws.recv())
        if msg.get("id") == want:
            return msg


def js(e):
    r = call("Runtime.evaluate", {"expression": e, "returnByValue": True, "awaitPromise": True})
    return ((r.get("result") or {}).get("result") or {}).get("value")


send("Network.enable", {"maxTotalBufferSize": 30000000})
send("Runtime.enable")
# 1) 收起可能开着的下拉
send("Input.dispatchKeyEvent", {"type": "keyDown", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27})
send("Input.dispatchKeyEvent", {"type": "keyUp", "key": "Escape", "code": "Escape", "windowsVirtualKeyCode": 27})
time.sleep(1.0)
# 2) 找按钮中心 & 遮挡元素
info = js("""
(function(){
 var bar=document.querySelector('div.trade-toolbar_list');
 if(!bar) return 'no-toolbar';
 var items=Array.from(bar.querySelectorAll('a.toolbar-menu_item'));
 for(var k=0;k<items.length;k++){var s=(items[k].innerText||'').trim();
  if(s.indexOf(%s)>=0){
    var r=items[k].getBoundingClientRect();
    var x=Math.round(r.left+r.width/2), y=Math.round(r.top+r.height/2);
    var top=document.elementFromPoint(x,y);
    if(top && top!==items[k] && !items[k].contains(top)){ top.style.pointerEvents='none'; top.setAttribute('data-km-blocked','1'); }
    var t2=document.elementFromPoint(x,y);
    return JSON.stringify({x:x,y:y,s:s,blocker:(top?String(top.className).slice(0,40):''),now:(t2?String(t2.className).slice(0,40):'')});
  }}
 return 'not-found';
})()
""" % json.dumps(BTN))
L.append("定位: %s" % info)
if isinstance(info, str) and info.startswith("{"):
    d = json.loads(info)
    x, y = d["x"], d["y"]
    for m, extra in (("mouseMoved", {}), ("mousePressed", {"button": "left", "clickCount": 1}),
                     ("mouseReleased", {"button": "left", "clickCount": 1})):
        send("Input.dispatchMouseEvent", dict({"type": m, "x": x, "y": y}, **extra))
        time.sleep(0.15)
    L.append("已点击 @(%d,%d)" % (x, y))
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
        reqs[p["requestId"]] = {"u": p["request"]["url"], "m": p["request"]["method"],
                                "post": (p["request"].get("postData") or "")[:300], "s": "-"}
    elif m == "Network.responseReceived":
        p = msg["params"]
        if p["requestId"] in reqs:
            reqs[p["requestId"]]["s"] = p["response"]["status"]
KW = ("waybill", "express", "print", "trade", "audit", "bill", "get", "api")
L.append("请求数: %d" % len(reqs))
for r in reqs.values():
    if any(k.lower() in r["u"].lower() for k in KW):
        L.append("%s %s [%s]" % (r["m"], r["u"][:180], r["s"]))
        if r["post"]:
            L.append("   入参: " + r["post"][:260])
L.append("弹窗: " + str(js("""
(function(){var o=[];Array.from(document.querySelectorAll('.el-dialog,.el-message-box,.ui-dialog,.layui-layer,.el-message'))
 .filter(function(d){return d.offsetParent!==null}).forEach(function(d){o.push((d.innerText||'').replace(/\\s+/g,' ').slice(0,120))});
 return o.length?o.join(' || '):'none';})()
""")))
# 还原被我改过的元素
js("(function(){var n=document.querySelectorAll('[data-km-blocked]');for(var i=0;i<n.length;i++){n[i].style.pointerEvents='auto';n[i].removeAttribute('data-km-blocked');}return n.length;})()")
io.open(OUT, "w", encoding="utf-8").write("\n".join(L))
print("OK", len(reqs))
