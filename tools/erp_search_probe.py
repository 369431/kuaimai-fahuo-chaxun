# -*- coding: utf-8 -*-
"""探测打单页实时查单：/trade/search 的「商家编码」过滤参数名（pageSize=1，大切片不截断）。

用法：python tools/erp_search_probe.py "7107-黑色M"
"""
import io
import json
import os
import sys
import time
import urllib.parse

try:                      # pythonw 下没有控制台，sys.stdout 可能是 None
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from erp_probe import CDP, page_ws  # noqa

CODE = sys.argv[1] if len(sys.argv) > 1 else "7107-黑色M"
OUT = os.path.join(os.environ.get("TEMP", "."), "erp_search.txt")
BASE = ("api_name=trade_search&queryId=77&pageSize=1&field=pay_time&needOrder=1"
        "&useCompress=0&minutesAfterPaidOrderAreNotDisplayed=0")
CANDS = ["outerId", "outerIds", "sysOuterId", "sysOuterIds", "mainOuterId",
         "platOuterId", "searchOuterId", "code", "skuOuterId", "itemOuterId", ""]
t = page_ws()
c = CDP(t["webSocketDebuggerUrl"])


def fetch(path, form):
    js = """(async function(){
      const r = await fetch(%s, {method:'POST', credentials:'include',
        headers:{'Content-Type':'application/x-www-form-urlencoded'}, body:%s});
      const t = await r.text();
      return t.length + '||' + t.slice(0, 90000);
    })()""" % (json.dumps(path), json.dumps(form))
    return c.js(js) or ""


L = ["探测编码: %s  （queryId=77 = 快递单未打印）" % CODE, ""]
for p in CANDS:
    body = BASE + ("" if not p else "&%s=%s" % (p, urllib.parse.quote(CODE)))
    raw = fetch("/trade/search", body)
    note, n, hit = "", -1, None
    try:
        payload = raw.split("||", 1)[1] if "||" in raw else raw
        j = json.loads(payload)
        d = j.get("data") or {}
        arr = None
        for k in ("list", "trades", "orders", "rows", "dataList"):
            if isinstance(d.get(k), list):
                arr = d[k]
                break
        if arr is None and isinstance(d, list):
            arr = d
        n = len(arr) if arr is not None else -1
        payload_has_code = CODE in payload
        hit = payload_has_code
        if n > 0:
            o = arr[0]
            note = "sid=%s item_count=%s urgent=%s" % (
                o.get("sid") or o.get("id"), o.get("itemCount") or o.get("item_count"),
                o.get("urgent") or o.get("priority"))
            # 找剩余时间类字段
            cand = [k for k in o.keys() if any(x in k.lower() for x in
                                               ("remain", "deadline", "timeout", "expire", "send", "deliver"))]
            note += " | 时间类字段=%s" % ",".join(cand[:6])
    except Exception as e:
        note = "解析失败(%s) len=%s" % (str(e)[:40], raw.split("||")[0] if "||" in raw else "?")
    L.append("%-14s 单数=%-3s 含该编码=%-5s %s" % (p or "(不过滤)", n, hit, note))
    time.sleep(0.3)
c.close()
io.open(OUT, "w", encoding="utf-8").write("\n".join(L))
print("OK")
