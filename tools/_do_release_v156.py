# -*- coding: utf-8 -*-
"""发布 v1.56：网页端新拟物风格。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = r"C:\Users\Kerwin\Desktop\发布\快麦扫码查询_安装版_v1.56.exe"
NOTES = ("网页端全部页面换成**新拟物（软拟物）**风格：柔和灰底、卡片双阴影凸起、输入框内凹、按钮按压内凹；"
         "浅色/深色跟随系统自动切换。\n\n"
         "覆盖首页 / 登录 / 拣货 / 现货可发 / 盘点 / 打印记录 / 波次 / 波次记录 / 权限 共 9 个页面。")

assert os.path.isfile(INSTALLER), "安装包不存在：%s" % INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v1.56", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
