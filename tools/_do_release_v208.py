# -*- coding: utf-8 -*-
"""发布 v2.08：底部那行状态文字换成彩色进度条（所有刷新类型都显示）。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = os.path.join(REPO, "packaging", "out", "快麦扫码查询_安装版_v2.08.exe")
NOTES = (
    "**v2.08：底部状态那行 → 换成彩色进度条**\n"
    "\n"
    "**改了什么**\n"
    "· 以前刷新时底部只显示一行文字（例如「⏳ 正在拉取库存锁定数…已拉取 3100 个 SKU」），\n"
    "  现在**同样位置换成彩色进度条**：文字那一行自动隐藏，进度条顶上来，\n"
    "  跑完停在 100% 一秒半再收回去、文字恢复。\n"
    "· 进度条样式：1%→100% 的**彩虹色**，整条颜色缓慢流动；\n"
    "  中间大字百分比，右侧「正在拉取锁定数 · 已拉 3100 · 共约 9000 · 850/秒」。\n"
    "\n"
    "**关键修复：以前只有「全量拉订单」才有进度**\n"
    "· 进度文件以前只有全量拉订单会写，所以刷新**锁定数 / 货位 / 增量**时界面拿不到任何进度，\n"
    "  进度条根本不出现 —— 这就是你说「看不到彩色进度条」的原因。\n"
    "· 现在四种刷新（订单全量 / 增量 / 锁定数 / 货位）**统一都写进度**，\n"
    "  而且**带上了总数**（锁定数和货位的总数接口本来就返回，只是一直没往上传）。\n"
    "\n"
    "**实测（四种刷新逐个触发，进度条都出现且有真实百分比）**\n"
    "  锁定数：39.2% → 42.1% → 43.6%\n"
    "  货位  ：56.3% → 100.0%\n"
    "  增量  ：63.9%\n"
    "  全量  ：72.6%\n"
)

assert os.path.isfile(INSTALLER), "安装包不存在：%s" % INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v2.08", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
