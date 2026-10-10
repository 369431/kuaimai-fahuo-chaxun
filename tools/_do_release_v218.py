# -*- coding: utf-8 -*-
"""发布 v2.18：生成波次页输入编码 → 实时查 ERP，并把「实时」显示出来。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = os.path.join(REPO, "packaging", "out", "快麦扫码查询_安装版_v2.18.exe")
NOTES = (
    "**v2.18：你输入编码 → 实时查 ERP，并且让「实时」看得见**\n"
    "\n"
    "**先说明：那个框本来就在实时查**\n"
    "· 生成波次页输入编码后，走的是 /api/wave/lookup，**每次都真去 ERP 查**\n"
    "  （代码注释原文：「先**实时查快麦订单**…实时查 ERP，不是本地缓存」）。\n"
    "· 只是界面上**没有把「这是刚查的」显示出来**，所以你没法判断它到底查没查。\n"
    "\n"
    "**这一版做的**\n"
    "① 查完明确显示一行：\n"
    "     ✓ 已实时查 ERP　37 个候选订单　可成波合计 37 件　查询时间 16:42:18\n"
    "   查询中也会显示「正在实时查 ERP：xxx …」，不会让你以为没反应。\n"
    "② ERP 查到 0 单时，把真实原因说清楚：\n"
    "     · 若本地库快照还有单 → ★ 本地快照还有 N 单，但 ERP 实时已查不到，\n"
    "       说明这些单已离开待发货池（进波次/已打单），点「全量重拉」可对齐\n"
    "     · 若本地也没有 → 本地库里也没有待发货单，数据一致 ✓\n"
    "③ 服务端在 /api/wave/lookup 响应里带上 live / 查询时间 / 本地索引对照数。\n"
    "\n"
    "**所以你点 9699-加绒黑色S 会看到什么**\n"
    "   ✓ 已实时查 ERP　0 个候选订单　查询时间 xx:xx:xx\n"
    "   9699-加绒黑色S：没有可成波订单\n"
    "   ★ 本地库快照里还有 586 单 —— 但 ERP 实时已经查不到了。……\n"
    "   → 一眼就能分清「是我没查到」还是「ERP 里确实没有」。\n"
)

assert os.path.isfile(INSTALLER), "安装包不存在：%s" % INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v2.18", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
