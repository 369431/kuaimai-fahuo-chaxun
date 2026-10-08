# -*- coding: utf-8 -*-
"""发布 v1.59：软件启动即在后台拉起 9443 中转。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = r"C:\Users\Kerwin\Desktop\发布\快麦扫码查询_安装版_v1.59.exe"
NOTES = ("**软件一启动就把 HTTPS 中转（9443）在后台拉起来**，关窗口也照样在监听。\n"
         "\n"
         "· 以前只有点「启动全部」或刚装完那一次才会起中转；直接从桌面图标开软件**不会**起，"
         "所以关掉再开就发现 9443 没了 —— 现在开软件就自动起。\n"
         "· 中转是**独立隐藏进程**，关主窗口不影响它继续监听。\n"
         "· 顺带加了**每 3 分钟巡检**：配了证书但 9443 没在听（中转偶尔会自己退出）就自动重新拉起，"
         "不用再手动去点「只重启 HTTPS 中转」。\n"
         "· 已经在听就跳过，不会重复杀/重启；没装证书的机器静默跳过，不打扰。")

assert os.path.isfile(INSTALLER), "安装包不存在：%s" % INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v1.59", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
