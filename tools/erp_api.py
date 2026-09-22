# -*- coding: utf-8 -*-
"""在 ERP 页面里用 fetch 调内部接口（自动带登录态，绕开点页面/浮层问题）。

用法：
  python tools/erp_api.py getcode 6029578498234808[,6029578498234809]
  python tools/erp_api.py raw <path> <form-body>
"""
import io
import json
import os
import sys

try:                      # pythonw 下没有控制台，sys.stdout 可能是 None
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from erp_probe import CDP, page_ws  # noqa

OUT = os.path.join(os.environ.get("TEMP", "."), "erp_api.txt")


def api(c, path, form, timeout=90000):
    js = """(async function(){
      const ac = new AbortController();
      const to = setTimeout(function(){ ac.abort(); }, %d);
      try {
        const r = await fetch(%s, {method:'POST', credentials:'include',
          headers:{'Content-Type':'application/x-www-form-urlencoded'},
          body:%s, signal: ac.signal});
        clearTimeout(to);
        const t = await r.text();
        return 'HTTP '+r.status+' '+t.slice(0, 6000);
      } catch(e) { return 'ERR '+String(e); }
    })()""" % (timeout, json.dumps(path), json.dumps(form))
    return c.js(js)


def main():
    if len(sys.argv) < 2:
        print(__doc__)
        return
    t = page_ws()
    c = CDP(t["webSocketDebuggerUrl"])
    cmd = sys.argv[1]
    if cmd == "getcode":
        sids = (sys.argv[2] if len(sys.argv) > 2 else "").replace(" ", "")
        res = api(c, "/pt/waybill/code/get", "sids=%s&api_name=pt_waybill_code_get" % sids)
        try:
            j = json.loads(res.split(" ", 2)[2])
            d = j.get("data") or {}
            for x in d.get("successList") or []:
                print("OK  sid=%s 运单号=%s %s" % (x.get("sid"), x.get("outSid"),
                                                  x.get("logisticsCompanyName")))
            for x in d.get("failList") or []:
                print("失败 sid=%s 原因=%s" % (x.get("sid"), x.get("msg") or x))
        except Exception:
            pass
        io.open(OUT, "w", encoding="utf-8").write(str(res))
        print("（完整返回见 %s）" % OUT)
    elif cmd == "raw":
        res = api(c, sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else "")
        io.open(OUT, "w", encoding="utf-8").write(str(res))
        print(str(res)[:1200])
    c.close()


if __name__ == "__main__":
    main()
