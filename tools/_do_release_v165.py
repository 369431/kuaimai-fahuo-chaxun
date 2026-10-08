# -*- coding: utf-8 -*-
"""发布 v1.65：更新改静默一键。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = r"C:\Users\Kerwin\Desktop\发布\快麦扫码查询_安装版_v1.65.exe"
NOTES = ("**更新改成「静默一键」，不再弹安装向导。**\n"
         "\n"
         "以前点「检查更新 → 下载并安装」会弹出 Inno 安装向导，要一路点下一步、装完还得自己开程序。\n"
         "现在改成：\n"
         "· 下载完直接**静默安装**（只显示一个进度条，不问任何问题）\n"
         "· 安装器自动关掉正在运行的主程序和 9443 中转，装完**自动重新打开**，就是新版\n"
         "\n"
         "你只需要点两下：**检查更新 → 下载并安装**，然后等它自己重启。\n"
         "\n"
         "> 注意：**这一次（装到 v1.65）还得走一遍向导**，因为「静默」这个行为本身写在程序里，"
         "老版本装的还是老逻辑。**从 v1.65 往后就都是静默一键了。**")

assert os.path.isfile(INSTALLER), "安装包不存在：%s" % INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v1.65", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
