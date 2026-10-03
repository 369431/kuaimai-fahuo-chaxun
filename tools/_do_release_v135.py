# -*- coding: utf-8 -*-
"""发布 v1.35：调用 release.py 的 main()，中文说明走 UTF-8 字面量（不过控制台代码页）。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = r"C:\Users\Kerwin\Desktop\发布\快麦扫码查询_安装版_v1.35.exe"
NOTES = ("网页端：首页「生成波次」入口改名为「**扫码添加**」，页内按钮同样改成「扫码添加」"
         "（先选快递 → 扫码/输入编码 → 填件数 → 预览 → 生成，一个波次只含一种快递）。\n"
         "电脑端新增「**登录 ERP**」按钮：一键打开/聚焦打单浏览器（独立配置目录，"
         "CDP 9222）并定位到 ERP 登录页，不用再去命令行或翻目录找浏览器。\n"
         "· 打单与生成波次都依赖这个浏览器窗口，**请保持开着并登录**；"
         "窗口被关掉后，点一下「登录 ERP」就能重新打开。\n"
         "· 启动时自动带上 9222 调试端口与专用配置目录，不影响你日常用的浏览器。")

assert os.path.isfile(INSTALLER), INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v1.35", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
