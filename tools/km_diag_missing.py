# -*- coding: utf-8 -*-
"""诊断：为什么 11 个 shortId 在打单页列表里找不到？（页面 vs 接口 / 队列漂移）"""
import json
import os
import sys
import time
import urllib.parse

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "desktop"))
import kuaimai_print as K   # noqa: E402

SCAN_ALL = r"""
(async function(keys){
  var hit = {};
  var cont = document.querySelector('.J_TradeList_Body');
  function rows(){ return Array.from(document.querySelectorAll('div.module-list-item-inpage')); }
  function scan(){
    rows().forEach(function(r){
      var t = r.innerText || '';
      for (var i=0;i<keys.length;i++){
        var k = keys[i];
        if (k && t.indexOf(k) >= 0) hit[k] = 1;
      }
    });
  }
  scan();
  var maxTop = cont ? Math.max(0, cont.scrollHeight - cont.clientHeight) : 0;
  var step = cont ? Math.max(150, Math.round(cont.clientHeight * 0.8)) : 600;
  var top = 0, guard = 0;
  while (top < maxTop && guard++ < 200){
    top = Math.min(maxTop, top + step);
    if (cont) { cont.scrollTop = top; cont.dispatchEvent(new Event('scroll', {bubbles:true})); }
    await new Promise(function(r){ setTimeout(r, 250); });
    scan();
  }
  return JSON.stringify({hit: Object.keys(hit), maxTop: maxTop, scrolled: top});
})(%s)
"""


def main():
    code = "7153-常规黑色L"
    picked = json.load(open("tools/_picked60.json", encoding="utf-8"))
    sids = picked["sids"]
    shorts = picked["shorts"]
    print("dry_run 挑单: %d 单" % len(sids))

    # ① 现在的接口（未打印队列 queryId=77）：我们这 60 个 sid 还在不在
    cur, n, err = K.fetch_unprinted_sids(code, page_size=500)
    print("接口「快递单未打印」队列: %d 条 (err=%s)" % (n, err or "-"))
    inq = [s for s in sids if s in cur]
    outq = [s for s in sids if s not in cur]
    print("  我们的单仍在队列: %d / 已离开(大概已打): %d" % (len(inq), len(outq)))
    print("  已离开的 sid:", outq[:12])

    # ② 去重记忆里有没有它们（本机打过）
    memo = K.load_printed_memory()
    print("  已离开的单在本机去重记忆里:",
          sum(1 for s in outq if str(s) in memo))

    # ③ 页面扫描：哪些 shortId 在页面列表里
    c = K.open_cdp_page()
    try:
        c.call("Page.navigate", {"url": K.PRINT_PAGE_TPL % urllib.parse.quote(code)})
        time.sleep(9)
        href = str(c.js("location.href") or "")
        if "/trade/printv2/" not in href:
            tail = (K.PRINT_PAGE_TPL % urllib.parse.quote(code)).split("superboss.cc", 1)[-1]
            c.call("Page.navigate", {"url": href.split("/index.html", 1)[0] + tail})
            time.sleep(8)
            href = str(c.js("location.href") or "")
        print("\n页面 URL:", href[:130])
        print("每页显示:", K.set_page_size_max(c, []))
        time.sleep(2)
        print("列表共 %s 条 / 渲染窗口 %d 行" % (K.read_total(c), K._rows(c)))
        res = json.loads(c.js(SCAN_ALL % json.dumps(shorts)) or "{}")
        found = set(res.get("hit") or [])
        missing = [s for s in shorts if s not in found]
        print("页面里找到 %d/%d 个 shortId；缺 %d 个: %s" % (len(found), len(shorts), len(missing), missing))
        # 缺的是不是「已离开队列」的那批？
        sid_of = dict(zip(shorts, sids))
        miss_sids = [sid_of.get(s) for s in missing]
        print("  缺失对应 sid:", miss_sids)
        print("  其中已离开未打印队列的:", [s for s in miss_sids if s in set(outq)])
        print("  其中仍在未打印队列的(=页面过滤口径差异):", [s for s in miss_sids if s in cur])
        # 全页文本里有没有这些 shortId
        for s in missing[:6]:
            has = c.js("(function(k){return (document.body.innerText||'').indexOf(String(k))>=0;})()" % json.dumps(str(s)))
            print("   全页文本含 %s: %s" % (s, has))
    finally:
        c.close()


if __name__ == "__main__":
    main()
