# -*- coding: utf-8 -*-
"""发布 v1.66：检查更新改多源取最高版本。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = r"C:\Users\Kerwin\Desktop\发布\快麦扫码查询_安装版_v1.66.exe"
NOTES = ("**修：点「检查更新」说「已是最新版」，其实有新版本。**\n"
         "\n"
         "**原因**：清单只问了一个源 —— jsDelivr 的 CDN。它的 `@main` 缓存是 `s-maxage=43200`"
         "（**12 小时**），而且 purge（强制刷新）经常报告完成却**不真的失效**。"
         "结果新版本发布后，客户端最长 12 小时都拿到旧清单 → 拿旧版本号跟自己比 → 「已是最新版」。\n"
         "\n"
         "**修法**：改成**同时问多个源、取版本号最高**的那个：\n"
         "· jsDelivr（国内通常能通，但会缓存）\n"
         "· raw.githubusercontent（GitHub 自己的源，基本实时）\n"
         "· 有配置 `update_url` 时也一起问\n"
         "任一源给出更新的版本号就算有更新，并采用它那份的下载地址和 sha256。\n"
         "\n"
         "**实测**（当前 jsDelivr 还停在 v1.63、raw 已是 v1.65）：\n"
         "· 拿 v1.63 去查 → 正确发现 v1.65（采用 raw）；\n"
         "· 拿 v1.65 去查 → 正确地报「没有更新」；\n"
         "· 拿 v1.10 去查 → 正确发现 v1.65。\n"
         "\n"
         "> 提醒：本次要更新到 v1.66，**如果你当前跑的还是 v1.63 及更早，它的检查逻辑是旧的**，"
         "受 jsDelivr 缓存影响可能仍提示「已是最新版」（要等缓存过期，最多 12 小时）。"
         "这种情况直接跑一次安装包即可；**装到 v1.66 之后，检查更新就准了。**")

assert os.path.isfile(INSTALLER), "安装包不存在：%s" % INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v1.66", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
