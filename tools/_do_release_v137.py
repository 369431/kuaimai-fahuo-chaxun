# -*- coding: utf-8 -*-
"""发布 v1.37：调用 release.py 的 main()，中文说明走 UTF-8 字面量（不过控制台代码页）。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = r"C:\Users\Kerwin\Desktop\发布\快麦扫码查询_安装版_v1.37.exe"
NOTES = ("网页「生成波次」体验调整：\n"
         "· 首页按钮**改回「生成波次」**（点它进入操作页）。\n"
         "· 商家编码框支持两种方式：**手动输入回车即添加**；或点「**扫码添加**」"
         "**调用摄像头扫码**（带 ZXing 兜底，微信/部分国产浏览器也能扫）。\n"
         "· 波次仍按快递拆开（中通 / 申通不混）、只挑「一单一件」、"
         "件数超上限按最大可生成成波，生成后可回读波次号核对。")

assert os.path.isfile(INSTALLER), INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v1.37", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
