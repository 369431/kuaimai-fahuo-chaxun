# -*- coding: utf-8 -*-
"""通过 CDP 操作那个自动化 Edge 窗口：读页面标题/按钮，供打单对接用。

用法：
  python erp_probe.py                 # 列出页面 + 打印页面里的按钮文字
  python erp_probe.py eval "<js>"     # 在页面里执行一段 JS 并打印结果
"""
import json
import sys
import urllib.request

try:                      # pythonw 下没有控制台，sys.stdout 可能是 None
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
import websocket  # websocket-client

OP = urllib.request.build_opener(urllib.request.ProxyHandler({}))
BASE = "http://127.0.0.1:9222"


def targets():
    return json.loads(OP.open(BASE + "/json/list", timeout=5).read().decode("utf-8"))


def page_ws(url_part="erpb.superboss.cc"):
    for t in targets():
        if t.get("type") == "page" and url_part in (t.get("url") or ""):
            return t
    for t in targets():
        if t.get("type") == "page":
            return t
    raise SystemExit("没找到页面")


class CDP(object):
    def __init__(self, ws_url):
        # Edge/Chrome 会拒绝带 Origin 的 CDP 连接 → suppress_origin
        self.ws = websocket.create_connection(ws_url, timeout=30, suppress_origin=True)
        self.i = 0

    def call(self, method, params=None):
        self.i += 1
        self.ws.send(json.dumps({"id": self.i, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.i:
                return msg

    def js(self, expr):
        r = self.call("Runtime.evaluate", {"expression": expr, "returnByValue": True,
                                           "awaitPromise": True})
        res = (r.get("result") or {}).get("result") or {}
        if r.get("result", {}).get("exceptionDetails"):
            return "JS异常: " + str(r["result"]["exceptionDetails"])[:200]
        return res.get("value")

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


if __name__ == "__main__":
    t = page_ws()
    print("页面:", (t.get("title") or "")[:60], "|", (t.get("url") or "")[:90])
    c = CDP(t["webSocketDebuggerUrl"])
    if len(sys.argv) > 2 and sys.argv[1] == "eval":
        print(c.js(sys.argv[2]))
    else:
        print("登录状态判定:", c.js("(function(){var b=document.body?document.body.innerText:'';"
                                   "return b.indexOf('登录')>=0||b.indexOf('密码')>=0?'看起来是登录页':'可能已登录';})()"))
        print("按钮文字:", c.js("Array.from(document.querySelectorAll('button')).map(function(b){"
                                "return (b.innerText||'').trim();}).filter(Boolean).slice(0,40)"))
        print("输入框数:", c.js("document.querySelectorAll('input').length"))
    c.close()
