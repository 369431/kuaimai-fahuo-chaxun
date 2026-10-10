# -*- coding: utf-8 -*-
"""发布 v2.20：修「采购收货」页不显示已收（状态码写错导致部分到货被漏掉）。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = os.path.join(REPO, "packaging", "out", "快麦扫码查询_安装版_v2.20.exe")
NOTES = (
    "**v2.20：修「采购收货」页不显示已收**\n"
    "\n"
    "**原因（我上一版写错了状态码）**\n"
    "· 「部分到货」的状态值，接口实际用的是 **GOODS_PART_ARRIVED**，\n"
    "  我写成了 PART_ARRIVED → 接口返回 **0 条** → 所有部分收货过的采购单**全被漏掉**，\n"
    "  于是页面上「已收」永远是 0。\n"
    "· 「已收」字段本身是对的：收货过的单 receiveQuantity / actualReceiveNum 都有值。\n"
    "\n"
    "**这一版修的**\n"
    "· 状态查询改成 GOODS_NOT_ARRIVED + GOODS_PART_ARRIVED（旧值也兼容，并去重）。\n"
    "· 表格增加一列「**待收**」= 数量 − 已收；\n"
    "  部分到货的行把「已收 / 待收」标红，一眼能看出哪些还没收完。\n"
    "· 状态中文补上「部分到货」。\n"
    "\n"
    "**实测（修好后）**\n"
    "  列出了大量历史部分收货单，例如：\n"
    "    CG6047517019452124  数量 2998  已收 2997  待收 1\n"
    "    CG6046132996438237  数量 2173  已收 1688  待收 485\n"
    "    CG6046104125470770  数量 3776  已收 3778  待收 0（收多了）\n"
    "    CG6046085692240885  数量 5856  已收 5945  待收 0（收多了）\n"
    "  注：「已收 > 数量」是 ERP 里的实际数据（多收/补收），程序照实显示，不做修改。\n"
    "\n"
    "**页面仍然只读**：只查询展示，不改动任何数据。\n"
)

assert os.path.isfile(INSTALLER), "安装包不存在：%s" % INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v2.20", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
