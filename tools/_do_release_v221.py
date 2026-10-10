# -*- coding: utf-8 -*-
"""发布 v2.21：采购收货页点「已收 / 待收」弹商品明细。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = os.path.join(REPO, "packaging", "out", "快麦扫码查询_安装版_v2.21.exe")
NOTES = (
    "**v2.21：点「已收 / 待收」看商品明细**\n"
    "\n"
    "**新增**\n"
    "· 「采购收货」页里**点任意一行**（或点「已收」「待收」那两格），\n"
    "  弹出这张采购单的**商品明细**，两个页签：\n"
    "    ① **商品明细**：每个编码的 采购数量 / 已收 / 待收 / 正品 / 次品\n"
    "       （待收 > 0 标红，收完了标绿）\n"
    "    ② **收货记录**：这张采购单下的每张收货单（含 已上架 / 待上架 / 正次品）\n"
    "· 底部合计：采购 N 件 / 已收 N 件 / 待收 N 件 / 收货单几张。\n"
    "· 仍然**只读**，不改任何数据。\n"
    "\n"
    "**实测**（采购单 CG6056070037723603）\n"
    "  商品明细 8 行，例如：\n"
    "    9687-燕麦色M   采购 1176  已收 1176  待收 0  正品 1176  次品 0\n"
    "    9693-咖色S     采购   70  已收   70  待收 0  正品   70  次品 0\n"
    "  收货记录 6 张，例如：\n"
    "    RK6055924384903710_5  已上架  收货 350   已上架 350  正品 350\n"
    "    RK6055924384903710    未完成  收货 2318  已上架   0  正品 1608\n"
    "  合计：采购 3916 件 / 已收 3916 件 / 待收 0 件 / 收货单 6 张\n"
    "\n"
    "**数据来源**（都是只读接口）\n"
    "· purchase.order.get            采购明细\n"
    "· warehouse.entry.list.query    这张采购单下的所有收货单（可能拆单）\n"
    "· warehouse.entry.list.get      每张收货单的商品明细（count / goodNum / badNum）\n"
    "\n"
    "**上一版（v2.20）修的**\n"
    "· 「已收」不显示的问题：状态码写错（应为 GOODS_PART_ARRIVED），\n"
    "  导致部分收货的采购单被漏掉；已修好并新增「待收」列。\n"
)

assert os.path.isfile(INSTALLER), "安装包不存在：%s" % INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v2.21", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
