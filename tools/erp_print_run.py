# -*- coding: utf-8 -*-
"""真打测试：按商家编码筛选 → 勾选指定 sids → 点「多平台极速打印」→ 处理确认框。"""
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

CODE = sys.argv[1] if len(sys.argv) > 1 else "7107-黑色M"
SIDS = (sys.argv[2] if len(sys.argv) > 2 else "").split(",")
OUT = os.path.join(os.environ.get("TEMP", "."), "print_run.txt")
L = []
t = page_ws()
c = CDP(t["webSocketDebuggerUrl"])
c.call("Page.bringToFront")
L.append("页面: " + str(c.js("location.href")))


def js(e):
    return c.js(e)


# 1) 填商家编码搜索 + 触发查询
L.append("填搜索框: " + str(js("""
(function(){
 var i=Array.from(document.querySelectorAll('input')).filter(function(x){
   return (x.placeholder||'').indexOf('商家编码搜索')>=0;})[0];
 if(!i) return 'no-input';
 i.focus(); i.value=%s;
 i.dispatchEvent(new Event('input',{bubbles:true}));
 i.dispatchEvent(new Event('change',{bubbles:true}));
 i.dispatchEvent(new KeyboardEvent('keydown',{key:'Enter',keyCode:13,bubbles:true}));
 i.dispatchEvent(new KeyboardEvent('keyup',{key:'Enter',keyCode:13,bubbles:true}));
 return 'filled';
})()
""" % json.dumps(CODE))))
time.sleep(1)
L.append("点查询按钮: " + str(js("""
(function(){
 var bs=Array.from(document.querySelectorAll('button,a,span,div')).filter(function(b){
   var s=(b.innerText||'').trim(); return (s==='查询'||s==='查 询') && b.children.length<=1;});
 if(!bs.length) return 'no-btn';
 bs[0].click(); return 'clicked';
})()
""")))
time.sleep(6)
L.append("行数: " + str(js("document.querySelectorAll('div.module-list-item-inpage').length")))

# 2) 勾选我们的 sids
L.append("勾选结果: " + str(js("""
(function(sids){
 var n=0, found=[];
 var rows=document.querySelectorAll('div.module-list-item-inpage');
 for(var i=0;i<rows.length;i++){
   var txt=rows[i].innerText||'';
   for(var k=0;k<sids.length;k++){
     if(sids[k] && txt.indexOf(sids[k])>=0){
       var cb=rows[i].querySelector('input[type=checkbox]');
       if(cb && !cb.checked){ cb.click(); n++; }
       found.push(sids[k]);
     }
   }
 }
 return 'clicked='+n+' found='+found.join(',')+' checked='+document.querySelectorAll('input[type=checkbox]:checked').length;
})(%s)
""" % json.dumps(SIDS))))

# 3) 点打印按钮 —— 注意：下面 JS 仍按**旧名**「多平台极速打印」匹配（现已失效，见文件头 ⚠️）
#    现名「多平台打印快递单」/ `data-name=print_express_plus`
L.append("点打印: " + str(js("""
(function(){
 var bar=document.querySelector('div.trade-toolbar_list');
 if(!bar) return 'no-toolbar';
 var items=Array.from(bar.querySelectorAll('a.toolbar-menu_item'));
 for(var k=0;k<items.length;k++){
   var s=(items[k].innerText||'').trim();
   if(s.indexOf('多平台极速打印')>=0){ items[k].click(); return 'clicked:'+s; }}
 return 'not-found';
})()
""")))
for i in range(10):
    time.sleep(1.5)
    d = js("""
    (function(){var o=[];Array.from(document.querySelectorAll('.el-dialog,.el-message-box,.ui-dialog,.layui-layer,.el-message'))
     .filter(function(x){return x.offsetParent!==null})
     .forEach(function(x){o.push((x.innerText||'').replace(/\\s+/g,' ').slice(0,120))});
     return o.length?o.join(' || '):'none';})()
    """)
    if d != "none":
        L.append(" +%.1fs 弹窗: %s" % ((i + 1) * 1.5, d))
        # 确认打印
        r = js("""
        (function(){var ds=Array.from(document.querySelectorAll('.el-dialog,.el-message-box,.ui-dialog,.layui-layer')).filter(function(x){return x.offsetParent!==null});
         for(var i=0;i<ds.length;i++){var bs=Array.from(ds[i].querySelectorAll('button,a,span'));
          for(var j=0;j<bs.length;j++){var s=(bs[j].innerText||'').trim();
           if(s==='确定'||s==='确 定'||s==='打印'||s==='确认'||s==='是'){bs[j].click(); return 'ok:'+s;}}}
         return 'no-btn';})()
        """)
        L.append("   点了: " + str(r))
c.close()
io.open(OUT, "w", encoding="utf-8").write("\n".join(L))
print("OK")
