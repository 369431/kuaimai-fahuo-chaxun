# -*- coding: utf-8 -*-
"""发布 v2.29：修「现货可发一直载入中」+ 新增页面自检脚本。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = os.path.join(REPO, "packaging", "out", "快麦扫码查询_安装版_v2.29.exe")
NOTES = (
    "**v2.29：修「现货可发一直载入中，没法用」**\n"
    "\n"
    "**原因（非常隐蔽）**\n"
    "· 现货可发页的 JS 里多了**一个多余的括号/catch 块** → 整段脚本有语法错误 →\n"
    "  **整页 JS 一行都不执行** → 列表永远停在「正在载入…」。\n"
    "· 最坑的是：**页面不报任何错**，用户只看到一直转圈；\n"
    "  而 Python 语法检查也发现不了（页面是「Python 字符串里嵌 JS」）。\n"
    "· 注意：**后端一直是好的** —— /api/stock 实测 2 秒返回 7242 行数据，\n"
    "  纯前端的问题。\n"
    "\n"
    "**这一版修的**\n"
    "· 删掉多余的括号/catch 块，STOCK_HTML 的 JS 语法恢复正常。\n"
    "· 用**真实浏览器**做了端到端验证（真开页面读内容），确认不再是「正在载入…」：\n"
    "    修复前：#sum 文本 = 「正在载入…」（脚本没跑）\n"
    "    修复后：#sum 文本 = 「共 1482 个　可发合计 17941 件　加急 16924 件\n"
    "                       加急有货 658　可成波数据：ERP 实时刷新实时」\n"
    "    JS 异常 0 条 ✓\n"
    "\n"
    "**新增两个自检脚本（以后不会再犯这种错）**\n"
    "· `tools\\check_page_js.py`    —— 用 node 检查**所有页面**的 JS 语法，\n"
    "  有语法错就退出码 1（拦在发布前）。实测 9 个页面 9 段 JS 全部通过。\n"
    "· `tools\\check_pages_live.py` —— 用**真实浏览器**打开页面，\n"
    "  读关键元素 + 抓 JS 异常，验证「页面到底能不能用」。\n"
    "  实测：/stock、/wave、/order、/pick、/wave-records 全部 ✓ 正常\n"
    "  （按页面特性配判据：自动加载的必须出内容，要输入才出结果的只要求无报错+控件在）\n"
)

assert os.path.isfile(INSTALLER), "安装包不存在：%s" % INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v2.29", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
