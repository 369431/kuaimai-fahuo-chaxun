# -*- coding: utf-8 -*-
"""发布 v1.67：检查更新加 GitHub 官方 API 源。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = r"C:\Users\Kerwin\Desktop\发布\快麦扫码查询_安装版_v1.67.exe"
NOTES = ("**修「检查更新」说已是最新版、其实有新版**（比 v1.66 更彻底）。\n"
         "\n"
         "**问题**：更新的清单只问了 jsDelivr 一个 CDN。它的 `@main` 缓存是 **12 小时**，"
         "purge 还常常报告完成却不真失效 → 新版发布后客户端最长 12 小时都拿到旧清单 → 误报「已是最新版」。\n"
         "\n"
         "**v1.66 的做法**是「多问几个源、取版本号最高的」；实测发现 **raw.githubusercontent 也不稳**"
         "（偶尔超时，而且刚推的版本它也会落后几分钟）。\n"
         "\n"
         "**v1.67 再加一个真正实时的源：GitHub 官方 API**（实测发布后**立刻**可见、0.6 秒返回，"
         "完全不受 CDN 缓存影响）。现在三个源一起问、取最高版本：\n"
         "· GitHub 官方 API —— 最实时（版本以它为准）\n"
         "· raw.githubusercontent —— 基本实时\n"
         "· jsDelivr CDN —— 国内通常能通但会缓存\n"
         "发版时还会把安装包的 `sha256` 写进 Release 说明，这样从 API 拿到的版本**也能校验下载**。\n"
         "\n"
         "**实测**（当时 jsDelivr 停在 v1.63、raw 停在 v1.65、API 已是 v1.66）：\n"
         "拿 v1.63 去查 → 正确发现 v1.66，并给出对应的下载地址与 sha256。")

assert os.path.isfile(INSTALLER), "安装包不存在：%s" % INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v1.67", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
