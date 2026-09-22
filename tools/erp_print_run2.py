# -*- coding: utf-8 -*-
"""真打（修正版）：用 URL 参数 skuOuterId 筛单 → 清空已勾选 → 勾我们的单 → 点打印。

用法：python tools/erp_print_run2.py <商家编码> <sid1,sid2,...> <shortId1,shortId2,...>
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
SIDS = [s for s in (sys.argv[2] if len(sys.argv) > 2 else "").split(",") if s]
SHORT = [s for s in (sys.argv[3] if len(sys.argv) > 3 else "").split(",") if s]
OUT = os.path.join(os.environ.get("TEMP", "."), "print_run2.txt")
L = []
t = page_ws()
c = CDP(t["webSocketDebuggerUrl"])
# 注意：不要用 Page.bringToFront —— 会把自动化浏览器弹到前台，用户要求全程后台静默
# c.call("Page.bringToFront")

URL = ("https://erpb.superboss.cc/index.html#/trade/printv2/?queryId=77&module=printv2"
       "&warehouseId=556677&order=asc&pageNo=1&pageSize=300&timeType=pay_time&expressStatus=0"
       "&orderIdTypeSelect=mixKey&key=mainOuterId&queryType=1&skuOuterId=%s"
       % urllib.parse.quote(CODE))
c.call("Page.navigate", {"url": URL})
time.sleep(9)
L.append("筛单后 URL: " + str(c.js("location.href"))[:150])
L.append("行数: " + str(c.js("document.querySelectorAll('div.module-list-item-inpage').length")))

# 1) 清空已有勾选
L.append("清空勾选: " + str(c.js("""
(function(){
 var n=0;
 document.querySelectorAll('div.module-list-item-inpage').forEach(function(r){
   var cb=r.querySelector('input[type=checkbox]');
   if(cb && cb.checked){ cb.click(); n++; }});
 return 'unchecked='+n+' 剩余勾选='+document.querySelectorAll('input[type=checkbox]:checked').length;
})()
""")))

# 2) 勾我们的单（按 sid 或短号匹配）
L.append("勾选我们的单: " + str(c.js("""
(function(keys){
  var rows = Array.from(document.querySelectorAll('div.module-list-item-inpage'));
  var found = [], n = 0;
  rows.forEach(function(r){
    var txt = r.innerText || '';
    var hit = keys.find(function(k){ return k && txt.indexOf(k) >= 0; });
    if (hit) {
      found.push(hit);
      var cb = r.querySelector('input[type=checkbox]');
      if (cb && !cb.checked) { cb.click(); n = n + 1; }
    }
  });
  var checkedRows = document.querySelectorAll('div.module-list-item-inpage input[type=checkbox]:checked').length;
  return 'clicked=' + n + '|found=' + found.join(',') + '|checkedRows=' + checkedRows;
})(%s)
""" % json.dumps(SIDS + SHORT))))

# 2.5) 保险：没勾齐我们的单就不许点打印
STATE = str(c.js("""
(function(keys){
  var rows = Array.from(document.querySelectorAll('div.module-list-item-inpage'));
  var hitRows = 0;
  rows.forEach(function(r){
    var txt = r.innerText || '';
    if (keys.find(function(k){ return k && txt.indexOf(k) >= 0; })) {
      var cb = r.querySelector('input[type=checkbox]');
      if (cb && cb.checked) hitRows = hitRows + 1;
    }
  });
  return 'hitChecked=' + hitRows;
})(%s)
""" % json.dumps(SIDS + SHORT)))
L.append("保险检查: " + STATE)

# 3) 点打印按钮（只有勾到我们的单才点）—— 注意：下面 JS 仍按**旧名**「多平台极速打印」
#    匹配（现已失效，见文件头 ⚠️）；现名「多平台打印快递单」/ `data-name=print_express_plus`
import re as _re  # noqa
_n = int((_re.search(r"hitChecked=(\d+)", STATE) or [None, "0"])[1] or 0)
if _n <= 0:
    L.append("未勾到我们的单 → 跳过打印（保险生效）")
else:
    L.append("点打印: " + str(c.js("""
    (function(){
     var bar=document.querySelector('div.trade-toolbar_list');
     if(!bar) return 'no-toolbar';
     var items=Array.from(bar.querySelectorAll('a.toolbar-menu_item'));
     for(var k=0;k<items.length;k++){var s=(items[k].innerText||'').trim();
       if(s.indexOf('多平台极速打印')>=0){ items[k].click(); return 'clicked:'+s; }}
     return 'not-found';
    })()
    """)))
D = """
(function(){var o=[];Array.from(document.querySelectorAll('.el-dialog,.el-message-box,.ui-dialog,.layui-layer,.el-message'))
 .filter(function(x){return x.offsetParent!==null})
 .forEach(function(x){var bs=Array.from(x.querySelectorAll('button')).map(function(b){return (b.innerText||'').trim()}).filter(Boolean).slice(0,4);
   o.push((x.innerText||'').replace(/\\s+/g,' ').slice(0,150)+' <<'+bs.join('/')+'>')});
 return o.length?o.join(' || '):'none';})()
"""
for i in range(12):
    time.sleep(1.5)
    d = c.js(D)
    if d != "none":
        L.append(" +%.1fs: %s" % ((i + 1) * 1.5, d))
        r = c.js("""
        (function(){var ds=Array.from(document.querySelectorAll('.el-dialog,.el-message-box,.ui-dialog,.layui-layer')).filter(function(x){return x.offsetParent!==null});
         for(var i=0;i<ds.length;i++){var bs=Array.from(ds[i].querySelectorAll('button'));
          for(var j=0;j<bs.length;j++){var s=(bs[j].innerText||'').trim();
           if(s==='确定'||s==='确 定'||s==='打印'||s==='确认打印'||s==='是'){bs[j].click(); return 'ok:'+s;}}}
         return 'no-btn';})()
        """)
        L.append("   点了: " + str(r))
        time.sleep(2)
c.close()
io.open(OUT, "w", encoding="utf-8").write("\n".join(L))
print("OK")
