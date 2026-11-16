# -*- coding: utf-8 -*-
"""发布 v2.63：成波成功卡片显示「拣货区域 X区」。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = os.path.join(REPO, "packaging", "out", "快麦扫码查询_安装版_v2.63.exe")
NOTES = (
    "**v2.63：成波成功后直接显示「拣货区域 X区」**\n"
    "\n"
    "**一、成波成功卡片新增标签**\n"
    "```\n"
    "波次号：231623\n"
    "状态 未拣  |  已建出 41 件  |  订单数 41  |  拣货区域 z区\n"
    "```\n"
    "· 绿色加粗标签，直接显示 ERP 波次的真实拣货库区\n"
    "· 多库区时显示 `A/C/B区`\n"
    "· 数据来自 ERP 波次列表的 `sectionAreas`，不是本地估算\n"
    "\n"
    "**二、回读加了重试**\n"
    "新波次可能延迟几秒才出现在 ERP 列表里，现在会重试 4 次（最多约 9 秒），\n"
    "避免「刚成波却读不到库区」显示空白。\n"
    "\n"
    "**三、实测结果（重要）**\n"
    "```\n"
    "波次 231623   41 件   拣货库区 = z    ← 用普通「生成波次」按钮成的，没走规则\n"
    "```\n"
    "说明：ERP 按「绑定货位」优先分配库存。7127-黑加绒M 绑定在 z-0-0-0-0、\n"
    "货也主要在 z，所以直接就用 z 扣了 —— **不需要规则也能做到只扣 z**。\n"
    "\n"
    "**四、两条路都可用**\n"
    "```\n"
    "生成波次（默认）        → 快，一步到位，库区看绑定/库存分布（可能已是 z）\n"
    "准备规则并等待生成      → 强制区域，需要你在 ERP 点一次生成\n"
    "```\n"
)

assert os.path.isfile(INSTALLER), "安装包不存在：%s" % INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v2.63", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
