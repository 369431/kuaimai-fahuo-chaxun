# -*- coding: utf-8 -*-
"""发布 v1.42：调用 release.py 的 main()，中文说明走 UTF-8 字面量（不过控制台代码页）。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = r"C:\Users\Kerwin\Desktop\发布\快麦扫码查询_安装版_v1.42.exe"
NOTES = ("新增「**一键拣完**」：生成波次后可以把波次推成**等待验货**（和 200913 同口径）。\n"
         "· 位置：波次页「一键拣完（对已生成的波次）」+ 成波成功后直接给入口，"
         "「波次记录」页每行也有一个。\n"
         "· **两段式**：先点一次 = **只读预览**（分拣明细：位置号 / 编码 / 件数），"
         "**不写任何东西**；再确认才真的提交。\n"
         "· 提交只做 **拣选完成**（`erp.trade.wave.pick.hand`）→ 网页显示 **等待验货**，"
         "订单数不变、件数按**已拣**。**不做播种回传**（那是更靠后一步，会把状态推过头）。\n"
         "· 状态口径实测钉准：`未完成`（没拣）/ **`等待验货`（已拣）** / `已完成` / `已取消`，"
         "记录页同时显示订单数、件数、拣货完成时间。\n"
         "· 该操作写 ERP、**不可撤销**，所以必须你手动确认。")

assert os.path.isfile(INSTALLER), INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v1.42", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
