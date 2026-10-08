# -*- coding: utf-8 -*-
"""发布 v1.69：更新弹窗可最小化。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = r"C:\Users\Kerwin\Desktop\发布\快麦扫码查询_安装版_v1.69.exe"
NOTES = ("**修：发现新版本的窗口不能最小化、一直摆在桌面上很烦。**\n"
         "\n"
         "**原因**：那个窗口用了 `transient(主窗口)`，在 Windows 上会变成「**被主窗口拥有**」的窗口 ——"
         "任务栏里**没有它的按钮**，所以一旦最小化就找不回来了（等于不能最小化），"
         "只能一直摆在桌面上。\n"
         "\n"
         "**改法**：\n"
         "· 改成**普通窗口**：任务栏里有它自己的按钮，最小化 / 还原都正常（构造时手动提到最前面一次）；\n"
         "· 按钮区新增「**最小化**」；\n"
         "· **下载结束（成功或失败）会自动把窗口弄回前台** —— 你下载时把它最小化了，也不会错过结果。\n"
         "\n"
         "另外窗口最小尺寸放宽到 480×320，小屏也不憋屈。")

assert os.path.isfile(INSTALLER), "安装包不存在：%s" % INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v1.69", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
