# -*- coding: utf-8 -*-
"""1) 那个最急单的明细与剩余时间  2) 试 field=timeoutActionTime 排序是否就是「剩余时间」序。"""
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

OUT = os.path.join(os.environ.get("TEMP", "."), "chk.txt")
t = page_ws()
c = CDP(t["webSocketDebuggerUrl"])


def q(form):
    js = """(async function(){
      const r = await fetch('/trade/search', {method:'POST', credentials:'include',
        headers:{'Content-Type':'application/x-www-form-urlencoded'}, body:%s});
      return await r.text(); })()""" % json.dumps(form)
    raw = c.js(js) or ""
    try:
        return (json.loads(raw).get("data") or {}).get("list") or []
    except Exception as e:
        return [{"__err": str(e)[:50], "__len": len(raw)}]


BASE = ("api_name=trade_search&queryId=77&field=%s&needOrder=1&useCompress=0"
        "&minutesAfterPaidOrderAreNotDisplayed=0&pageSize=%d")
now = time.time()


def remain(o):
    try:
        v = float(o.get("timeoutActionTime") or 0)
        return (v / 1000.0 - now) / 3600.0 if v > 1e12 else None
    except Exception:
        return None


L = []
# 1) 用户指出的最急单
L.append("=== 1. tid=6929692477353262420 明细 ===")
for o in q(BASE % ("pay_time", 5) + "&tid=6929692477353262420"):
    L.append("sid=%s 剩余=%.1fh itemCount=%s" % (o.get("sid"), remain(o) or -999, o.get("itemCount")))
    for it in (o.get("orders") or []):
        L.append("   商品 %s ×%s%s" % (it.get("outerId"), it.get("num"),
                                     "（赠品）" if (it.get("giftNum") or it.get("platformGift")) else ""))

# 2) 排序字段试验：按 timeoutActionTime 取前 5 单（编码固定）
for code in ("7107-黑色M",):
    for field in ("pay_time", "timeoutActionTime", "promiseDeliveryTime"):
        L.append("")
        L.append("=== 2. 编码 %s 按 field=%s 取前 5（看剩余时间是否递增） ===" % (code, field))
        for o in q(BASE % (field, 5) + "&outerId=" + code):
            if "__err" in o:
                L.append("  解析失败 %s len=%s" % (o["__err"], o["__len"]))
                continue
            r = remain(o)
            L.append("  sid=%s 剩余=%s 付款=%s" % (
                o.get("sid"), ("%.1fh" % r) if r is not None else "?",
                time.strftime("%m-%d %H:%M", time.localtime(float(o.get("payTime") or 0) / 1000))))
c.close()
io.open(OUT, "w", encoding="utf-8").write("\n".join(L))
print("OK")
