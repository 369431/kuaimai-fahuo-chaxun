# -*- coding: utf-8 -*-
"""只读探测：打单页订单列表的滚动容器与行号信息（写问题 A 的「行号区间」前先看实况）。

用法：python tools/km_probe_rows.py
不点任何东西、不出纸（只 c.js 读 DOM）。
"""
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "desktop"))
import kuaimai_print as K   # noqa: E402

PROBE_JS = r"""
(function(){
  var out = {};
  var b = document.querySelector('.J_TradeList_Body');
  out.has_body = !!b;
  if (b) out.body_geo = {st:b.scrollTop, sh:b.scrollHeight, ch:b.clientHeight,
                         top:b.offsetTop, cls:String(b.className||'').slice(0,80)};
  var divs = [];
  document.querySelectorAll('div').forEach(function(d){
    if (d.scrollHeight > d.clientHeight + 20 && d.clientHeight > 100)
      divs.push({cls:String(d.className||'').slice(0,70), st:d.scrollTop,
                 sh:d.scrollHeight, ch:d.clientHeight});
  });
  out.scrollers = divs;
  var rows = Array.from(document.querySelectorAll('div.module-list-item-inpage'));
  out.n_rows = rows.length;
  out.rows = rows.map(function(r){
    return {di: r.getAttribute('data-index'), top: r.offsetTop, h: r.offsetHeight,
            pt: (r.offsetParent? r.offsetParent.offsetTop : null),
            pcls: String((r.parentElement||{}).className||'').slice(0,60),
            txt: (r.innerText||'').replace(/\s+/g,' ').slice(0,50)};
  });
  var m = (document.body.innerText||'').match(/共\s*(\d+)\s*条记录/);
  out.total = m ? m[1] : null;
  var se = document.scrollingElement || document.documentElement;
  out.page_scroll = {st: se.scrollTop, sh: se.scrollHeight, ch: se.clientHeight};
  out.other_list_cls = [];
  document.querySelectorAll('[class*=tradeList],[class*=TradeList],[class*=module-list]').forEach(function(e){
    out.other_list_cls.push(String(e.className||'').slice(0,70) + ' | sh=' + e.scrollHeight + ' ch=' + e.clientHeight + ' st=' + e.scrollTop);
  });
  return JSON.stringify(out);
})()
"""


def main():
    c = K.open_cdp_page()
    try:
        print("URL:", c.js("location.href"))
        raw = c.js(PROBE_JS)
        d = json.loads(raw or "{}")
        print(json.dumps(d, ensure_ascii=False, indent=1))
        # 再看一次：把容器滚到 0 后前 5 行的 offsetTop 与行高
        c.js(K.SCROLL_TOP_JS)
        import time
        time.sleep(0.5)
        d2 = json.loads(c.js(PROBE_JS) or "{}")
        print("\n--- 滚到顶后 ---")
        print("body_geo:", json.dumps(d2.get("body_geo"), ensure_ascii=False))
        print("n_rows:", d2.get("n_rows"), "total:", d2.get("total"))
        for r in (d2.get("rows") or [])[:5]:
            print("  row:", json.dumps(r, ensure_ascii=False))
    finally:
        try:
            c.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
