# -*- coding: utf-8 -*-
"""发布 v1.48：扫码枪只认回车提交（去掉快输入自动提交）。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = r"C:\Users\Kerwin\Desktop\发布\快麦扫码查询_安装版_v1.48.exe"
NOTES = ("扫码枪：**只认回车提交**（去掉「快输入自动提交」）\n"
         "\n"
         "· 你的扫码枪**带回车后缀**，所以之前为「不带回车后缀的枪」加的"
         "「一串快输入停下就自动提交」已**移除** —— 避免误触发、行为更可控。\n"
         "· 现在：扫码枪扫完（带回车）→ 提交；手输后按回车 → 提交；"
         "**不按回车就不会提交**（输入框里留着内容，方便你核对）。\n"
         "· 保留：输入框**没聚焦**时页面级也接住回车（打字落到页面上照样认）、"
         "点空白处自动把焦点放回编码框、带回车只提交一次。\n"
         "· 首页 + 波次页都生效；打单链路未动。")

assert os.path.isfile(INSTALLER), INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v1.48", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
