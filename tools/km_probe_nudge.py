# -*- coding: utf-8 -*-
"""只读探测 2：找出「让虚拟滚动列表把窗口重渲染到第 1 行」的可靠手法。

用法：python tools/km_probe_nudge.py
只读 DOM + 设 scrollTop（不点勾选、不出纸）。
"""
import io
import json
import os
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "desktop"))
import kuaimai_print as K   # noqa: E402

READ_JS = r"""
(function(){
  var b = document.querySelector('.J_TradeList_Body');
  var rows = Array.from(document.querySelectorAll('div.module-list-item-inpage'));
  var idx = rows.map(function(r){ var v = r.getAttribute('data-index'); return v===null?-1:parseInt(v); });
  var tops = rows.map(function(r){ return r.offsetTop; });
  var minI = idx.length ? Math.min.apply(null, idx) : null;
  var maxI = idx.length ? Math.max.apply(null, idx) : null;
  var minT = tops.length ? Math.min.apply(null, tops) : null;
  return JSON.stringify({
    st: b ? b.scrollTop : null, sh: b ? b.scrollHeight : null, ch: b ? b.clientHeight : null,
    n: rows.length, minI: minI, maxI: maxI, minT: minT,
    kids: b ? Array.from(b.children).slice(0,3).map(function(e){
        return String(e.className||'').slice(0,60) + '|top=' + e.offsetTop + '|sh=' + e.scrollHeight; }) : []});
})()
"""

# 各种「回顶」手法
NUDGES = [
    ("1) scrollTop=0（不派发事件）",
     "(function(){var b=document.querySelector('.J_TradeList_Body');b.scrollTop=0;return 'ok';})()"),
    ("2) scrollTop=0 + scroll 事件",
     "(function(){var b=document.querySelector('.J_TradeList_Body');b.scrollTop=0;"
     "b.dispatchEvent(new Event('scroll',{bubbles:true}));return 'ok';})()"),
    ("3) scrollTo({top:0}) + scroll 事件",
     "(function(){var b=document.querySelector('.J_TradeList_Body');b.scrollTo({top:0});"
     "b.dispatchEvent(new Event('scroll',{bubbles:true}));return 'ok';})()"),
    ("4) 先 300 再 0 + scroll 事件",
     "(function(){var b=document.querySelector('.J_TradeList_Body');b.scrollTop=300;"
     "b.dispatchEvent(new Event('scroll',{bubbles:true}));b.scrollTop=0;"
     "b.dispatchEvent(new Event('scroll',{bubbles:true}));return 'ok';})()"),
    ("5) 先 1 再 0 + scroll 事件",
     "(function(){var b=document.querySelector('.J_TradeList_Body');b.scrollTop=1;"
     "b.dispatchEvent(new Event('scroll',{bubbles:true}));b.scrollTop=0;"
     "b.dispatchEvent(new Event('scroll',{bubbles:true}));return 'ok';})()"),
    ("6) wheel 向上大滚",
     "(function(){var b=document.querySelector('.J_TradeList_Body');"
     "b.dispatchEvent(new WheelEvent('wheel',{deltaY:-5000,bubbles:true,cancelable:true}));return 'ok';})()"),
    ("7) 对容器派发 mouseover+mouseenter",
     "(function(){var b=document.querySelector('.J_TradeList_Body');"
     "['mouseover','mouseenter','mousemove'].forEach(function(t){"
     "b.dispatchEvent(new MouseEvent(t,{bubbles:true,cancelable:true}));});return 'ok';})()"),
    ("8) 先滚到顶再对该容器 click 空白处",
     "(function(){var b=document.querySelector('.J_TradeList_Body');b.scrollTop=0;"
     "b.dispatchEvent(new Event('scroll',{bubbles:true}));"
     "b.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,cancelable:true}));"
     "b.dispatchEvent(new MouseEvent('mouseup',{bubbles:true,cancelable:true}));return 'ok';})()"),
]


def read(c, tag):
    d = json.loads(c.js(READ_JS) or "{}")
    print("  %-34s st=%-6s rows=%-3s data-index %s..%s  minTop=%s"
          % (tag, d.get("st"), d.get("n"), d.get("minI"), d.get("maxI"), d.get("minT")))
    return d


def main():
    c = K.open_cdp_page()
    try:
        print("初始:")
        read(c, "before")
        for name, js in NUDGES:
            c.js(js)
            time.sleep(0.8)
            read(c, name)
        # 最后：再看看 children 结构
        print("\n容器 children:", json.dumps(json.loads(c.js(READ_JS) or "{}").get("kids"), ensure_ascii=False))
    finally:
        try:
            c.close()
        except Exception:
            pass


if __name__ == "__main__":
    main()
