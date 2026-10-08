# -*- coding: utf-8 -*-
"""发布 v1.58：波次记录「实时回读失败」修复。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = r"C:\Users\Kerwin\Desktop\发布\快麦扫码查询_安装版_v1.58.exe"
NOTES = ("波次记录「实时回读失败」修复。\n"
         "\n"
         "**根因**：`erp.trade.waves.query` 在 24 小时窗口下返回体约 **10.2 MB**，"
         "**超过网关 8 MB 上限**被拒（网关原话：`Data length too large`）。\n"
         "\n"
         "**修复**\n"
         "· 回读遇到「响应过大」**自动把 pageSize 减半重试**（100 → 50 → 25 → …），绕开 8 MB 上限，实测已恢复正常。\n"
         "· 以前只判断「返回是不是字典」，会把**错误响应当成「成功但 0 个波次」**，"
         "所以页面只显示「实时回读失败」却给不出原因 —— 现在会**识别 success=false**，"
         "把接口的 code/msg 直接显示出来，不再装死。\n"
         "· 波次记录页、以及「一键拣完」的只读预览都一并恢复正常。")

assert os.path.isfile(INSTALLER), "安装包不存在：%s" % INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v1.58", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
