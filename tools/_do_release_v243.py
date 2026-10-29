# -*- coding: utf-8 -*-
"""发布 v2.43：生成波次按库区锁定 + 严格逐单校验（含赠品）。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = os.path.join(REPO, "packaging", "out", "快麦扫码查询_安装版_v2.43.exe")
NOTES = (
    "**v2.43：生成波次只锁 A/B/C/D 库区 —— 并做到「每件货都在这几区」**\n"
    "\n"
    "**一、你要的效果（等价于 ERP 的「绑定货位 = ABC 库区」）**\n"
    "· 生成波次挑单时，每个编码的上限 = **min（你要的件数，ERP 可成波单数，"
    "该编码在 A/B/C/D 的可用数）**\n"
    "· 可用数来自 **ERP 仓储 → 货位库存**，**已扣掉「已配数」**（被别人配走的量）\n"
    "· 超出 A~D 可用数的部分不会锁定成波\n"
    "\n"
    "**二、严格逐单校验（新增）**\n"
    "· 选中的每一单，检查它**所有明细**（含**赠品**）里的每一个编码\n"
    "· 任一条件在 A~D 可用量不足 → **整单剔除**，并在结果里说明剔了几单\n"
    "· 以前只看「真实商品行」，赠品被漏掉 —— 现在赠品也会校验\n"
    "\n"
    "**三、为什么不用 ERP 那个「绑定货位」输入框**\n"
    "· 它对应的参数是 `bindGoodsSectionCode`（从 ERP 前端 JS 挖出）\n"
    "· 但实测：传单货位和传空值结果完全一样（不生效），传多个直接 0 条\n"
    "· 所以改成「按货位库存算可用数 + 严格校验」，效果等价而且更准\n"
    "\n"
    "**四、实测数据（你店里）**\n"
    "```\n"
    "7158-加绒咖色S    D-1-2-1  已配 19  可用 25   → A~D 可锁 25\n"
    "9711-常规燕麦色M  A-8-6-2  已配 23  可用 1864 → A~D 可锁 1864\n"
    "6625-卡其L        只在 F 区（93 件）          → A~D 0，不能成波\n"
    "9687-燕麦色L      45 个货位全在 G/F 区        → A~D 0，不能成波\n"
    "```\n"
    "· 全库 2,486 个编码里，1,319 个（53%）只在 F/G/XT 区有货 → 不能成波（已确认符合预期）\n"
    "\n"
    "**五、分区可以自己改**\n"
    "· 现货可发页 → 顶部「分区 A/B/C/D ▾」→ 勾选要算的区 → 保存立刻生效\n"
    "· 生成波次、在架数、可发件数 一起跟着变\n"
)

assert os.path.isfile(INSTALLER), "安装包不存在：%s" % INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v2.43", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
