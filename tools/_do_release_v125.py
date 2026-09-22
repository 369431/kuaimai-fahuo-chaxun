# -*- coding: utf-8 -*-
"""发布 v1.25：调用 release.py 的 main()，中文说明走 UTF-8 字面量（不过控制台代码页）。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = r"C:\Users\Kerwin\Desktop\发布\快麦扫码查询_安装版_v1.25.exe"
NOTES = ("修复自动打单偶发「找不到打印按钮」导致不出纸：ERP 的打印入口已改名为「多平台极速打印」，"
         "且会按订单状态在两种按钮间切换 → 改为按 data-name + 文案多候选识别并全页兜底；"
         "弹窗确认键兼容「继续打印」；"
         "修正批量勾选的目标定位（原先会提前停止：实测 60 单只定位到 10 单就回退慢扫）")

assert os.path.isfile(INSTALLER), INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v1.25", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
