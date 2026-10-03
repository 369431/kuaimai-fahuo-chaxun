# -*- coding: utf-8 -*-
"""发布 v1.36：调用 release.py 的 main()，中文说明走 UTF-8 字面量（不过控制台代码页）。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = r"C:\Users\Kerwin\Desktop\发布\快麦扫码查询_安装版_v1.36.exe"
NOTES = ("修复：电脑端「**登录 ERP**」按钮被「自动上架推荐货位」那一组控件压住、看不见的问题"
         "（操作区改成一行 6 个按钮，不再挤位）。\n"
         "· 登录 ERP 按钮在主界面「操作」区，一键打开/聚焦打单浏览器并定位到 ERP 登录页；"
         "窗口被关掉后点它就能重开。\n"
         "· 打单、生成波次都依赖这个浏览器窗口，请保持开着并登录。")

assert os.path.isfile(INSTALLER), INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v1.36", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
