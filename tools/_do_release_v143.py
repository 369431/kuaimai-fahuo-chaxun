# -*- coding: utf-8 -*-
"""发布 v1.43：调用 release.py 的 main()，中文说明走 UTF-8 字面量（不过控制台代码页）。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = r"C:\Users\Kerwin\Desktop\发布\快麦扫码查询_安装版_v1.43.exe"
NOTES = ("修复两个问题：\n"
         "· **网页状态不显示「等待验货」**（全显示未完成）：状态换算漏传了拣货完成时间，"
         "且把 ERP 的占位时间戳（0 / 946656000000）误当成「已拣」。现在口径为："
         "`未完成`（没拣）/ **`等待验货`（已拣，有真实拣货时间）** / `已完成` / `已取消`。\n"
         "· **生成的波次不用人工输入波次号**：成波后回读波次号自动重试（最多 3 次），"
         "回读不到时按钮用波次号兜底；生成结果里的入口改为「**一键拣完（不用输入）**」；"
         "万一回读未确认，按提示到「波次记录」页点一下就行（也不用输入）。\n"
         "· 「一键拣完」仍然：先只读预览 → 再确认才写；只做拣选完成，不做播种回传。")

assert os.path.isfile(INSTALLER), INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v1.43", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
