# -*- coding: utf-8 -*-
"""Publish v1.24 by calling release.py's main() with explicit args.

Driving release.py in-process sidesteps any console/ANSI-passing mangling of the
Chinese --notes text (paths + notes live here as UTF-8 literals instead).
"""
import io, os, sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = r"C:\Users\Kerwin\Desktop\发布\快麦扫码查询_安装版_v1.24.exe"
NOTES = ("新增「打单」全链路（网页提交→按账号派单→多台认领→自动打单）；"
         "修复打印按钮改名导致的不出纸（ERP 已把「多平台极速打印」改为「多平台打印快递单」，"
         "且确认键「打 印」带空格）；新增「打单进度」面板与「打印记录」网页页；"
         "新增打印分工设置；修复误标「已打」与误写去重记忆；队列失败自动退避重试")

assert os.path.isfile(INSTALLER), INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v1.24", "--installer", INSTALLER, "--notes", NOTES]

import release
rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
