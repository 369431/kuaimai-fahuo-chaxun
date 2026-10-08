# -*- coding: utf-8 -*-
"""发布 v1.68：波次记录页改版（生成账号列）。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = r"C:\Users\Kerwin\Desktop\发布\快麦扫码查询_安装版_v1.68.exe"
NOTES = ("**波次记录页改版。**\n"
         "\n"
         "· **去掉「我生成的波次」那张表** —— 不再单独列「本机生成过哪些波次」。\n"
         "· **「最近 ERP 波次」新增「生成账号」列** —— 一眼看出每个波次是**本系统哪个账号**"
         "（比如 admin）点成波的。\n"
         "· 「一键拣完」按钮**搬到新表里**（原来它挂在「我生成的波次」那张表上）。\n"
         "\n"
         "**为什么「生成账号」要取自本机记录**：快麦 ERP 那边只有同一个登录账号，"
         "它在 ERP 里看到的操作人永远是它自己，分不出是**本系统**的哪个账号点的成波。"
         "所以这一列从本机记录（只存「波次号 → 账号」）里取。三种显示：\n"
         "· `admin` —— 有记录，就是它生成的；\n"
         "· `（旧记录无账号）` —— 这版之前生成的（那时还没记账号）；\n"
         "· `（非本系统）` —— 不在本机记录里（别人直接在 ERP 里建的波次）。")

assert os.path.isfile(INSTALLER), "安装包不存在：%s" % INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v1.68", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
