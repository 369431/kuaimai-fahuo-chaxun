# -*- coding: utf-8 -*-
"""发布 v2.01：修实发订单数不显示 + 登录页检查更新 + 成波提速。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = os.path.join(REPO, "packaging", "out", "快麦扫码查询_安装版_v2.01.exe")
NOTES = (
    "**v2.01：修 3 个反馈问题**\n"
    "\n"
    "**① 波次记录「实发订单数」终于显示数字了**\n"
    "· 之前那一列永远是「…」或「—」：表格渲染还在用旧的「当日发货日志」逻辑，\n"
    "  没接上新的读取方式。现在改成走 ERP「波次管理 → 点波次号」那个接口读 `printTimes`。\n"
    "· 显示成 **「已打印 / 订单总数」**（例如 `227 / 227`、`218 / 220`），\n"
    "  已完成波次也能读。列宽也加宽了，不会再被截断成「…」。\n"
    "\n"
    "**② 登录页新增「检查更新」按钮**\n"
    "· 以前只有登录之后才能检查更新。现在登录窗上就能点（更新跟登录没关系）。\n"
    "· 有新版本时可以直接「下载并安装」，也能「打开下载页」。\n"
    "\n"
    "**③ 页签顺序调换**\n"
    "· **波次记录** 排在 **扫码记录** 前面。\n"
    "\n"
    "**④ 生成波次提速**\n"
    "· 挑单只查**候选订单**的剩余时间（原来按编码把该编码全部待发货单都拉一遍）。\n"
    "  单个编码实测 1.35 秒；成波整体更快。\n"
)

assert os.path.isfile(INSTALLER), "安装包不存在：%s" % INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v2.01", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
