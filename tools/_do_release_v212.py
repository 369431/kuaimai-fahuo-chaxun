# -*- coding: utf-8 -*-
"""发布 v2.12：所有对话框确保显示在主窗口上面（修「检查更新窗被压住」）。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = os.path.join(REPO, "packaging", "out", "快麦扫码查询_安装版_v2.12.exe")
NOTES = (
    "**v2.12：所有弹窗都确保显示在主窗口上面**\n"
    "\n"
    "**修了什么**\n"
    "· 「检查更新」窗口以前偶尔会被主窗口压住（你反馈的：不在主页面上面）。\n"
    "· 根因：主窗口是无边框自绘标题栏的，Windows 有时不给新弹出的子窗前台焦点。\n"
    "\n"
    "**改法（统一处理，不是只修一个窗）**\n"
    "· 新增公共函数 `show_dialog_on_top()`，每个对话框打开时：\n"
    "    ① 应用级模态（必须处理完才回到主窗）\n"
    "    ② 加置顶标志（窗口关掉就失效，不是永久置顶）\n"
    "    ③ 先 show() 一次再进模态循环 —— 保证拿到前台焦点\n"
    "    ④ raise_ + activateWindow 明确拉到最前\n"
    "· 已接到**全部 10 个弹窗**：检查更新、API 设置、对外访问设置、子客户端管理、\n"
    "  打印分工、现货可发、批次查询、盘点、每日发货量、重新登录。\n"
    "\n"
    "**实测（真实 Win32 窗口层级）**\n"
    "  前台窗口 = 对话框 ✓\n"
    "  Z 序：主窗=11，对话框=6 → 对话框在主窗前面 ✓\n"
    "  对话框带 WS_EX_TOPMOST = True（主窗 False）✓\n"
)

assert os.path.isfile(INSTALLER), "安装包不存在：%s" % INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v2.12", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
