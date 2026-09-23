# -*- coding: utf-8 -*-
"""发布 v1.31：调用 release.py 的 main()，中文说明走 UTF-8 字面量（不过控制台代码页）。

本机网络：直连 github.com 可用、本地代理 65532 已挂 → **不设 HTTPS_PROXY**，
让 git / gh 直连（与 v1.30 那轮正好相反，故每轮都现探一次）。
"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = r"C:\Users\Kerwin\Desktop\发布\快麦扫码查询_安装版_v1.31.exe"
NOTES = ("新增「后置打印（包装验货）」打单方式，可与「订单打印V2」切换（界面下拉，默认仍是 V2）：\n"
         "换到后置打印后，出纸走「拣选号 -11 → 编码 → 数量」，拣选号固定 -11、"
         "编码与数量只取自本次「可发」那条，不再取号、不再滚屏勾选。\n"
         "沿用旧口径的防重复打印（宁可漏打、绝不错重打）。\n\n"
         "撤回「可发」时，把该编码还没开打的打单任务一并取消（正在打/已打完/失败的一律不动）；"
         "取消后电脑端不会再认领，撤回就真的不出纸；撤回后同一编码可以重新提交。\n"
         "撤回提示会显示「已取消 N 个未开打的打单任务」。")

assert os.path.isfile(INSTALLER), INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v1.31", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
