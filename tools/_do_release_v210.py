# -*- coding: utf-8 -*-
"""发布 v2.10：最小化后不再露出旧界面（旧 Tk 根窗彻底隐藏）。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = os.path.join(REPO, "packaging", "out", "快麦扫码查询_安装版_v2.10.exe")
NOTES = (
    "**v2.10：修「最小化后露出旧版界面」**\n"
    "\n"
    "**原因**\n"
    "· 电脑版为了不显示旧界面，把后台那个 Tk 根窗设成了「全透明」。\n"
    "· 但全透明在 Windows 看来**仍然是「可见窗口」**（实测 IsWindowVisible=True），\n"
    "  所以你把电脑版窗口最小化后，这层透明的旧界面就露出来了 —— 看起来像旧版。\n"
    "· 之前不敢用「彻底隐藏」是因为：彻底隐藏后，那些设了 transient(主窗口) 的设置窗\n"
    "  会**建出来但不显示**（点 API 设置没反应的老问题）。\n"
    "\n"
    "**改法**\n"
    "· 之前已经把 transient 换成了「父窗隐藏时跳过」的安全版本，\n"
    "  所以现在可以放心把根窗**彻底隐藏**：实测旧根窗 IsWindowVisible=False，\n"
    "  同时 8 个设置窗（API 设置 / 对外访问 / 子客户端管理 / 打印分工 / 现货可发 /\n"
    "  批次查询 / 改库存日志 / 打单进度）**全部照常弹出**。\n"
    "\n"
    "**实测**\n"
    "  旧 Tk 根窗：可见=False（真正隐藏）✓\n"
    "  设置窗：8 个全部能弹 ✓\n"
)

assert os.path.isfile(INSTALLER), "安装包不存在：%s" % INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v2.10", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
