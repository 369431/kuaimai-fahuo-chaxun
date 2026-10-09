# -*- coding: utf-8 -*-
"""发布 v2.10：最小化不再露旧界面 + 进度条可拖拽改大小。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = os.path.join(REPO, "packaging", "out", "快麦扫码查询_安装版_v2.10.exe")
NOTES = (
    "**v2.10：修「最小化露出旧界面」+ 进度条可以拉着改大小**\n"
    "\n"
    "**① 最小化后不再露出旧版界面**\n"
    "· 原因：电脑版为了不显示旧界面，把后台那个 Tk 根窗设成了「全透明」；\n"
    "  但全透明在 Windows 看来**仍然是「可见窗口」**（实测 IsWindowVisible=True），\n"
    "  所以最小化电脑版窗口后这层透明的旧界面就露出来了。\n"
    "· 改法：既然之前已经把 transient 换成了安全版本（父窗隐藏时跳过），\n"
    "  现在可以放心把根窗**彻底隐藏**。\n"
    "· 实测：旧 Tk 根窗 IsWindowVisible=False（真正隐藏）✓，\n"
    "  同时 8 个设置窗（API 设置 / 对外访问 / 子客户端管理 / 打印分工 / 现货可发 /\n"
    "  批次查询 / 改库存日志 / 打单进度）**全部照常弹出** ✓。\n"
    "\n"
    "**② 进度条可以自己拉大小**\n"
    "· **鼠标放到进度条边缘**就会出现对应的调整光标，按住拖动即可：\n"
    "    左边缘 / 右边缘 → 拉宽 / 拉窄\n"
    "    上边缘 / 下边缘 → 拉高 / 拉矮\n"
    "    四个角         → 同时改宽和高\n"
    "· 拉完的尺寸**会记住**，下次启动还是你拉的大小。\n"
    "· 在进度条上**点右键**有「恢复默认大小」。\n"
    "· 实测：右拉 +200 → 700x30；下拉 +14 → 700x44；左拉 +80 → 780x44；\n"
    "  新建（模拟重启）沿用 780x44；恢复默认 → 280x30。\n"
)

assert os.path.isfile(INSTALLER), "安装包不存在：%s" % INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v2.10", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
