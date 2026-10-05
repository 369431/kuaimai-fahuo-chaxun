# -*- coding: utf-8 -*-
"""发布 v1.51：修「自动化浏览器选错页面 → ERP 调用 30s 超时」。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = r"C:\Users\Kerwin\Desktop\发布\快麦扫码查询_安装版_v1.51.exe"
NOTES = ("修「查询失败：Connection timed out」/「货位库存状态读取失败」\n"
         "\n"
         "· **根因**：ERP 域名由 `erpb.superboss.cc` 迁到租户域名 `viperp.superboss.cc` 后，"
         "自动化浏览器里**按老域名找打单页**匹配不上了 —— 旧代码匹配不上就「取第一个页面」，"
         "结果挑到无关的插件页（Tampermonkey）→ 所有 ERP 调用**卡满 30 秒超时**（波次查询、"
         "货位库存状态全挂）。\n"
         "· **修复**：\n"
         "  - 优先挑**任意 ERP 租户页**（`*.superboss.cc`），并**排除**插件/浏览器内部页"
         "（`chrome-extension://`、`edge://`、`tampermonkey` 等）；带 `/index.html#` 的应用页优先。\n"
         "  - **不再「拿第一个页面凑数」**：确实没有 ERP 页 → 明确报错并提示「请先打开打单浏览器并登录 ERP」，"
         "不让调用白等 30 秒。\n"
         "· 实测：修复后挑中的是 `viperp.superboss.cc/index.html#/trade/genwave/`，"
         "一次 ERP 调用 **0.3 秒**（修复前 30 秒超时）。\n"
         "· 影响面：所有走自动化浏览器的功能（波次查询/成波/货位库存/打单页操作）都会受益。")

assert os.path.isfile(INSTALLER), INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v1.51", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
