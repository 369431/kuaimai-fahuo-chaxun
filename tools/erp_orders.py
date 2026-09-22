# -*- coding: utf-8 -*-
"""实时查单：按商家编码从打单页拉订单（/trade/search + outerId），并 dump 结构。

用法：python tools/erp_orders.py "7107-黑色M"
结果写 %TEMP%\erp_orders.txt
"""
import io
import json
import os
import sys
import urllib.parse

try:                      # pythonw 下没有控制台，sys.stdout 可能是 None
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from erp_probe import CDP, page_ws  # noqa

CODE = sys.argv[1] if len(sys.argv) > 1 else "7107-黑色M"
OUT = os.path.join(os.environ.get("TEMP", "."), "erp_orders.txt")
BASE = ("api_name=trade_search&queryId=77&pageSize=5&field=pay_time&needOrder=1"
        "&useCompress=0&minutesAfterPaidOrderAreNotDisplayed=0")

t = page_ws()
c = CDP(t["webSocketDebuggerUrl"])


def fetch(path, form):
    js = """(async function(){
      const r = await fetch(%s, {method:'POST', credentials:'include',
        headers:{'Content-Type':'application/x-www-form-urlencoded'}, body:%s});
      const t = await r.text();
      return t.length + '||' + t.slice(0, 400000);
    })()""" % (json.dumps(path), json.dumps(form))
    return c.js(js) or ""


raw = fetch("/trade/search", BASE + "&outerId=" + urllib.parse.quote(CODE))
L = ["实时查单: 商家编码=%s" % CODE, "响应长度=%s" % raw.split("||")[0]]
try:
    j = json.loads(raw.split("||", 1)[1])
    d = j.get("data") or {}
    arr = None
    for k in ("list", "trades", "orders", "rows", "dataList"):
        if isinstance(d.get(k), list):
            arr = d[k]
            break
    if arr is None and isinstance(d, list):
        arr = d
    L.append("订单数=%s" % (len(arr) if arr is not None else "?"))
    if arr:
        o = arr[0]
        L.append("首单字段: " + ",".join(sorted(o.keys()))[:1200])
        for tf in ("promiseDeliveryTime", "timeoutActionTime", "deliveryTime", "deliverPrintTime"):
            if tf in o:
                L.append("  %s = %s" % (tf, o.get(tf)))
        for k in ("orders", "items", "orderItems", "tradeOrders"):
            if isinstance(o.get(k), list):
                L.append("明细数组 %s 共 %s 条；第一条字段: %s" % (
                    k, len(o[k]), ",".join(sorted(o[k][0].keys()))[:600] if o[k] else "-"))
                for it in o[k][:4]:
                    L.append("   code=%s num=%s gift=%s title=%s" % (
                        it.get("outerId") or it.get("sysOuterId") or it.get("code"),
                        it.get("num") or it.get("qty"),
                        it.get("giftFlag") or it.get("isGift") or it.get("giftNum"),
                        str(it.get("title") or it.get("sysTitle") or "")[:24]))
                break
except Exception as e:
    L.append("解析失败: %s" % str(e)[:120])
    L.append("原文前 300: " + raw[:300])
c.close()
io.open(OUT, "w", encoding="utf-8").write("\n".join(L))
print("OK")
