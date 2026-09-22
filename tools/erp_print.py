# -*- coding: utf-8 -*-
"""快麦 ERP 打单（订单打印V2）——通过 CDP 驱动那个自动化 Edge 窗口。

流程按用户实际习惯：勾选订单 → 「多平台获取单号」 → 「多平台极速打印」
（中通/申通 的多平台打印设置里已各自绑好打印机，会自动选打印机）

⚠️ 已过时（2026-09-22 实测）：ERP 打单页工具条**已不再渲染**「多平台极速打印」
   （`data-name=speed_print_btn` 消失 ✗），现在可点的是**「多平台打印快递单」**
   （`data-name=print_express_plus` ✓）；且点完会先弹【打印设置】弹窗，确认按钮文案是
   「打 印」（**中间带空格**）且是 `<a>` 不是 `<button>` ✗。
   本脚本下面的 `print` / `run` 仍按**旧名**点击 → 会 `not-found`（仅作历史/探针参考）。
   实际打单实现见 `desktop/kuaimai_print.py`：data-name 优先 + 文案兜底 + 真实鼠标点击 + 去空格确认。
   详见 `docs/打单对接.md` 四点七。

用法：
  python tools/erp_print.py list
  python tools/erp_print.py check --codes "7107-黑色M,1166" --qty 3
  python tools/erp_print.py getcode
  python tools/erp_print.py print
  python tools/erp_print.py rows
"""
import argparse
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

PRINT_PAGE = "https://erpb.superboss.cc/index.html#/trade/printv2"

ROWS_JS = r"""
Array.from(document.querySelectorAll('div.module-trade-list-item-row1')).map(function(r, i){
  function cell(cls){ var x=r.querySelector('div.trade-cell.'+cls); return x?(x.innerText||'').replace(/\s+/g,' ').trim():''; }
  var cb=r.querySelector('input[type=checkbox]');
  return {i:i, checked: !!cb && cb.checked, sid: cell('trade-shortId'),
          code: cell('trade-commodityDetailed').slice(0,60), num: cell('trade-num'),
          outSid: cell('trade-outSid'), status: cell('trade-printStatus'),
          count: cell('trade-printCount'), express: cell('trade-expressName')};
})
"""


def conn():
    t = page_ws()
    c = CDP(t["webSocketDebuggerUrl"])
    if "printv2" not in (t.get("url") or ""):
        c.call("Page.navigate", {"url": PRINT_PAGE})
        time.sleep(6)
    return c


def rows(c):
    return c.js(ROWS_JS) or []


def click_toolbar(c, text):
    """点工具条上文本包含 text 的按钮（如 多平台获取单号 / 多平台打印快递单）。

    ⚠️ 只按文本匹配，且不吃 `element.click()` 时无效；打印按钮现名「多平台打印快递单」，
    旧名「多平台极速打印」已失效（见文件头 ⚠️ 说明）。
    """
    js = """
    (function(){
      var bar=document.querySelector('div.trade-toolbar_list');
      if(!bar) return 'no-toolbar';
      var items=Array.from(bar.querySelectorAll('a.toolbar-menu_item'));
      for (var i=0;i<items.length;i++){
        var s=(items[i].innerText||'').trim();
        if (s.indexOf(%s)>=0){ items[i].click(); return 'clicked:'+s; }
      }
      return 'not-found';
    })()
    """ % json.dumps(text)
    return c.js(js)


def click_dialog_ok(c, tries=6):
    """点掉可能出现的确认弹窗（确定/确认/是）。"""
    js = """
    (function(){
      var ds=Array.from(document.querySelectorAll('.el-dialog,.ui-dialog,.el-message-box,.layui-layer'));
      var vis=ds.filter(function(d){return d.offsetParent!==null});
      for (var i=0;i<vis.length;i++){
        var bs=Array.from(vis[i].querySelectorAll('button,a,span'));
        for (var j=0;j<bs.length;j++){
          var s=(bs[j].innerText||'').trim();
          if (s==='确定'||s==='确 定'||s==='确认'||s==='是'){ bs[j].click(); return 'ok:'+s; }
        }
      }
      return 'no-dialog';
    })()
    """
    out = []
    for _ in range(tries):
        r = c.js(js)
        out.append(r)
        if r == "no-dialog":
            time.sleep(1.5)
            if c.js(js) == "no-dialog":
                break
        time.sleep(1.5)
    return out


def check_codes(c, codes, per_code=1):
    """用「商家编码搜索」筛选，再勾选前 per_code 行/编码。codes 逗号/换行分隔。"""
    js = """
    (function(codes, per){
      var inp=Array.from(document.querySelectorAll('input')).filter(function(i){
        return (i.placeholder||'').indexOf('商家编码搜索')>=0;})[0];
      if(!inp) return 'no-input';
      inp.focus(); inp.value=codes;
      inp.dispatchEvent(new Event('input',{bubbles:true}));
      inp.dispatchEvent(new Event('change',{bubbles:true}));
      return 'filled';
    })(%s, %d)
    """ % (json.dumps(codes), per_code)
    return c.js(js)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["list", "rows", "check", "getcode", "print", "run"])
    ap.add_argument("--codes", default="")
    ap.add_argument("--qty", type=int, default=1, help="每个编码勾选几单")
    a = ap.parse_args()
    c = conn()
    if a.cmd in ("list", "rows"):
        rs = rows(c)
        print("订单行数:", len(rs))
        for r in rs:
            print(" #%-2s %-4s 系统单号=%-10s 编码=%-22s 量=%-2s 运单号=%-12s 状态=%-4s 打印次数=%s %s"
                  % (r["i"] + 1, "✔" if r["checked"] else " ", r["sid"], r["code"][:22], r["num"],
                     r["outSid"], r["status"], r["count"], r["express"][:12]))
    elif a.cmd == "check":
        print(c.js("location.href"))
        print("填搜索框:", check_codes(c, a.codes, 1))
        print("（搜索/查询按钮需要确认，或你已在页面上筛好）")
    elif a.cmd == "getcode":
        print("点「多平台获取单号」:", click_toolbar(c, "多平台获取单号"))
        print("弹窗处理:", click_dialog_ok(c))
    elif a.cmd == "print":
        print("点「多平台极速打印」:", click_toolbar(c, "多平台极速打印"))
        print("弹窗处理:", click_dialog_ok(c))
    elif a.cmd == "run":
        if a.codes:
            print("筛选:", check_codes(c, a.codes, a.qty))
            time.sleep(2)
        print("取号:", click_toolbar(c, "多平台获取单号"), click_dialog_ok(c)[-1])
        time.sleep(3)
        print("打印:", click_toolbar(c, "多平台极速打印"), click_dialog_ok(c)[-1])
        time.sleep(3)
        for r in rows(c):
            if r["checked"]:
                print(" 已打:", r["sid"], r["code"][:20], "运单号=", r["outSid"])


if __name__ == "__main__":
    main()
