# -*- coding: utf-8 -*-
"""发布 v1.41：调用 release.py 的 main()，中文说明走 UTF-8 字面量（不过控制台代码页）。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = r"C:\Users\Kerwin\Desktop\发布\快麦扫码查询_安装版_v1.41.exe"
NOTES = ("波次功能补齐（都在网页端）：\n"
         "· **成波后直接显示波次号**（成波即回读，不用再回 ERP 找）。\n"
         "· **配货明细逐行显示**：`7107-燕麦色S　38 件` 一个 SKU 一行，多个 SKU 自动换行，照着配货。\n"
         "· **新增「生成波次记录」页**：列出你生成过的波次号 + 状态 + 件数/时间。\n"
         "· **波次状态**中文化显示（未完成 / 已完成 / 已取消；认不出的状态原样显示，不瞎猜）。\n"
         "· 数据**实时取 ERP**：记录页每次打开都实时回读，不走本地缓存；本机只记"
         "「你自己生成过哪些波次号」。")

assert os.path.isfile(INSTALLER), INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v1.41", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
