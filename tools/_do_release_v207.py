# -*- coding: utf-8 -*-
"""发布 v2.07：拉取数据时显示 RGB 流动进度条（1% → 100%）。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = os.path.join(REPO, "packaging", "out", "快麦扫码查询_安装版_v2.07.exe")
NOTES = (
    "**v2.07：拉取数据时显示彩色进度条（1% → 100%）**\n"
    "\n"
    "**新增：RGB 流动进度条**\n"
    "· 拉取订单 / 增量刷新 / 刷新货位时，界面上会出现一条**彩虹色进度条**：\n"
    "  颜色从红→橙→黄→绿→青→蓝→紫**缓慢流动**，看着就是"活的"。\n"
    "· 中间大字显示百分比（1% → 100%）；右侧同步显示「已拉 xx 单 · xx 单/秒 · 共约 xx 单」。\n"
    "· 总数还没统计出来时，先显示「读取中…」+ 来回扫的流光，一知道总数就切成确定百分比。\n"
    "· 拉完会把进度条推到 **100%**，停留 1 秒多再自动收起（让你确认"跑完了"）。\n"
    "\n"
    "**怎么拿到的**\n"
    "· 拉取线程本来就每处理一片就写一次 `kuaimai_pull_progress.json`（已拉单数/百分比/速率），\n"
    "  现在把这个数据接到 `/api/desktop/state`，电脑版界面直接画出来 —— 没改拉取逻辑。\n"
    "\n"
    "**实测（真拉了一次全量）**\n"
    "  60.7% → 62.2% → 93.2% → 98.5% → 99.7% → 100.0% → 完成\n"
    "  一共 152938 单，约 1 分钟拉完（2786 单/秒）\n"
)

assert os.path.isfile(INSTALLER), "安装包不存在：%s" % INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v2.07", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
