# -*- coding: utf-8 -*-
"""发布 v1.32：调用 release.py 的 main()，中文说明走 UTF-8 字面量（不过控制台代码页）。

本机网络：已探明 **直连 github.com 可用**（api.github.com 200 / 0.4s）、本地代理端口全关
→ **不设 HTTPS_PROXY**，让 git / gh 直连（每轮都现探一次，与 v1.31 那轮一致）。
"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = r"C:\Users\Kerwin\Desktop\发布\快麦扫码查询_安装版_v1.32.exe"
NOTES = ("新增「自动上架到推荐货位」：在「打单进度」旁边有**独立开关**和可调刷新间隔"
         "（默认 60 秒，可设 10～3600 秒），打开后每隔设定时间自动查一次待上架的上架单，"
         "有就按推荐货位自动上架，不用再手动去 ERP 点。\n"
         "· 推荐货位取「该编码自己现有的货位（在架最多的那个）」；自己没有货位时，"
         "按同款同尺码的规律（如 6618 的 S/M/L/XL 各自固定货位）推；"
         "**推不出来就整张单跳过、只记日志等人工，绝不乱猜货位。**\n"
         "· 上架前后都会核对（写之前确认单还在待上架、写之后核对已完成的实际上架数），"
         "和人工在 ERP 同时操作也不会打架。\n"
         "· 走开放平台 API，**不需要开打单浏览器**；默认是关的，要用请在界面上勾选。\n"
         "· 该功能只在主客户端生效。")

assert os.path.isfile(INSTALLER), INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v1.32", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
