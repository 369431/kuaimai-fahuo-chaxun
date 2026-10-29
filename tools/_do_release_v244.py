# -*- coding: utf-8 -*-
"""发布 v2.44：严格模式 —— 保证波次里只有所选分区（A/B/C/D）的货位。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = os.path.join(REPO, "packaging", "out", "快麦扫码查询_安装版_v2.44.exe")
NOTES = (
    "**v2.44：严格模式 —— 保证「生成波次后只有 A/B/C/D 货位」**\n"
    "\n"
    "**一、为什么之前的版本还不够**\n"
    "· 之前只保证「A~D 有足够的可用量」，但某编码如果在区外（G/F/XT）**也有库存**，\n"
    "  ERP 有可能把这一单绑到区外货位 → 波次里就混进了非 A~D 货位\n"
    "\n"
    "**二、新增「严格模式」（默认开启）**\n"
    "· 规则：**只让「库存全部在所选分区」的编码成波**\n"
    "· 某编码在区外还有可用库存 → 直接不参与成波，并说明原因\n"
    "· 这样 ERP 无论怎么分配货位，都只能从 A~D 拣 → **波次里只有 A~D 货位**\n"
    "\n"
    "**三、对你的实际影响（本地货位库 2,500 个编码）**\n"
    "```\n"
    "① 库存全在 A~D（可成波，100% 保证）        654 个\n"
    "② A~D 有货但区外也有（严格模式会被排除）   378 个\n"
    "③ A~D 没货（本来就不能成波）             1,468 个\n"
    "```\n"
    "· 也就是：可成波的编码从 1,032 个变成 654 个\n"
    "· 被排除的 378 个是「A~D 有一部分、其它区也有一部分」的 —— 这类没法保证只从 A~D 拣\n"
    "\n"
    "**四、想放宽的话**\n"
    "· 现货可发页 → 顶部「分区 A/B/C/D ▾」→ 弹窗里**取消勾选「严格模式」**→ 保存\n"
    "· 取消后：只要 A~D 有货就允许成波（但 ERP 可能绑到区外货位，不保证波次只含 A~D）\n"
    "\n"
    "**五、怎么看到被排除了什么**\n"
    "· 成波结果里会返回 `zone_blocked`：列出因「区外还有库存」被排除的编码，\n"
    "  以及它「区内多少件 / 区外多少件」\n"
    "· 日志里也会有说明\n"
    "\n"
    "**六、顺带查清的事实**\n"
    "· ERP「选择订单生成波次」里的「绑定货位」= 查询参数 `bindGoodsSectionCode`\n"
    "  （从 ERP 前端 JS 挖出），但它**在接口层实测不生效**（传值与传空结果一样）\n"
    "· 生成波次的提交接口 `/trade/wave/checked/trade/save` 只收\n"
    "  `{warehouseId, ruleId, sids, tradeNumUp, hasFilter}`，**没有货位参数**\n"
    "  → 所以货位分配完全由 ERP 决定，只能在「挑哪些编码」这一侧做保证\n"
)

assert os.path.isfile(INSTALLER), "安装包不存在：%s" % INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v2.44", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
