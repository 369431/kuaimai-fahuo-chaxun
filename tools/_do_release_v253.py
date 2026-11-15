# -*- coding: utf-8 -*-
"""发布 v2.53：修「ERP 明明已登录却提示请登录」的误判。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = os.path.join(REPO, "packaging", "out", "快麦扫码查询_安装版_v2.53.exe")
NOTES = (
    "**v2.53：修「ERP 明明已登录，网页却提示请在打单浏览器里登录 ERP」**\n"
    "\n"
    "**一、问题现象**\n"
    "· 浏览器里 ERP 已经登录（停在首页），网页却红字报错：\n"
    "  `波次查询失败：请在打单浏览器里登录 ERP（只需一次，以后会记住）`\n"
    "· 所有走 ERP 的功能都失败（波次查询、成波、货位库存…）\n"
    "\n"
    "**二、根因**\n"
    "· 程序找 ERP 页面时，默认优先匹配 `erpb.superboss.cc`\n"
    "· 只要浏览器里留着一个 **`erpb` 的 login.html 标签**，就选中了这个登录页\n"
    "  → 判定「未登录」，哪怕另一个 `erpa` 标签早就登录好了\n"
    "\n"
    "**三、修法**\n"
    "· 选页面时**跳过任何登录页**（URL 里带 login 的一律不用）\n"
    "· 优先选已登录的应用页（带 `/index.html#` 且不含 login）\n"
    "· 只有全部标签都是登录页时，才真正提示「需要登录」\n"
    "\n"
    "**四、实测**\n"
    "```\n"
    "修前：erp_page_ws 选中 = https://erpb.superboss.cc/login.html\n"
    "      ensure_browser → need_login（误报）\n"
    "修后：erp_page_ws 选中 = https://erpa.superboss.cc/index.html#/index/\n"
    "      ensure_browser → ok | 已登录 ✓\n"
    "```\n"
    "\n"
    "**五、同时说明（A-0 库存是实时变化的）**\n"
    "· 「即入即出」的货会先进 A-0-0-0，被订单分走后归零\n"
    "· 所以同一编码的可生成数量会随时间变化，这是正常的：\n"
    "  例如 `9733-燕麦色M` 早前 A-0 有 227 件 → 可生成 227；\n"
    "  现在 A-0 已被分完（0 件）→ 可生成 0\n"
    "· 只要 A-0 有货，扫码成波就能成，且波次只扣 A 区（实测波次 231008）\n"
)

assert os.path.isfile(INSTALLER), "安装包不存在：%s" % INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v2.53", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
