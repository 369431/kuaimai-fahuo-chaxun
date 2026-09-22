# -*- coding: utf-8 -*-
"""把一个订单的所有时间类字段换算出来，找出「剩余时间」到底看哪个字段。

用法：python tools/erp_order_fields.py 6929692477353262420
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
from erp_probe import CDP, page_ws  # noqa

KEY = sys.argv[1] if len(sys.argv) > 1 else "6929692477353262420"
OUT = os.path.join(os.environ.get("TEMP", "."), "fields.txt")
t = page_ws()
c = CDP(t["webSocketDebuggerUrl"])


def fetch(form):
    js = """(async function(){
      const r = await fetch('/trade/search', {method:'POST', credentials:'include',
        headers:{'Content-Type':'application/x-www-form-urlencoded'}, body:%s});
      return await r.text(); })()""" % json.dumps(form)
    return c.js(js) or ""


base = ("api_name=trade_search&queryId=77&pageSize=5&field=pay_time&needOrder=1"
        "&useCompress=0&minutesAfterPaidOrderAreNotDisplayed=0")
raw = fetch(base + "&tid=" + KEY)
arr = []
try:
    arr = (json.loads(raw).get("data") or {}).get("list") or []
except Exception as e:
    print("解析失败", str(e)[:60], "len", len(raw))
if not arr:
    raw = fetch(base + "&sid=" + KEY)
    try:
        arr = (json.loads(raw).get("data") or {}).get("list") or []
    except Exception:
        arr = []
L = ["查: %s  命中 %d 单" % (KEY, len(arr)), ""]
now_ms = time.time() * 1000
if arr:
    o = arr[0]
    L.append("sid=%s tid=%s shortId=%s" % (o.get("sid"), o.get("tid"), o.get("shortId")))
    L.append("快递=%s 已打=%s itemCount=%s" % (o.get("expressName"), o.get("printCount"), o.get("itemCount")))
    L.append("payTime=%s" % time.strftime("%Y-%m-%d %H:%M", time.localtime(float(o.get("payTime") or 0) / 1000)))
    L.append("")
    L.append("== 所有像时间戳的字段（值 > 1e12）==")
    for k, v in sorted(o.items()):
        try:
            f = float(v)
        except Exception:
            continue
        if f > 1e12:
            ts = f / 1000.0
            try:
                shown = time.strftime("%Y-%m-%d %H:%M", time.localtime(ts))
                gap = "(距今 %.1f 小时)" % ((ts - now_ms / 1000) / 3600)
            except Exception:
                shown, gap = "?", "(换算失败)"
            L.append("  %-24s %s   %s" % (k, shown, gap))
    L.append("")
    L.append("== 小整数/状态类字段（可能是时限小时数或标记）==")
    for k, v in sorted(o.items()):
        s = str(v)
        if len(s) <= 4 and (s.isdigit() or s in ("true", "false", "None")):
            L.append("  %-24s %s" % (k, s))
c.close()
io.open(OUT, "w", encoding="utf-8").write("\n".join(L))
print("OK", len(arr))
