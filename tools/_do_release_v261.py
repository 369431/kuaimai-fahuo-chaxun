# -*- coding: utf-8 -*-
"""发布 v2.61：修好波次列表读取（能看到今天的波次/库区/规则）。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = os.path.join(REPO, "packaging", "out", "快麦扫码查询_安装版_v2.61.exe")
NOTES = (
    "**v2.61：修好「读不到新波次」——现在能看到今天所有波次和它们的拣货库区**\n"
    "\n"
    "**一、修了一个隐藏很深的大 bug**\n"
    "· 波次列表接口 `/trade/wave/manager/list` **必须表单编码 + api_name + 时间范围**\n"
    "· 以前程序发 JSON（只有 pageNo/pageSize/warehouseId），服务端把参数全忽略了，\n"
    "  永远返回同一批老波次（首条一直是 231082）\n"
    "· 后果：刚生成的波次看不到 → 误判「生成 0 个」；「波次记录」页也一直是老数据\n"
    "· 现在带 `startTime/endTime`（今天）→ 一次就能看到今天的 **786 个波次**\n"
    "\n"
    "**二、波次数据现在带「拣货库区」和「生成规则」**\n"
    "```\n"
    "231550  40 件   库区=C    规则=16369「测试1」\n"
    "231519 200 件   库区=z    规则=16364「地面波Z」\n"
    "231510 200 件   库区=D    规则=15901「地面D-1」\n"
    "```\n"
    "· `wave_areas()` 改成翻页查今天的波次，能精确找到任意波次号\n"
    "· 成波回读、实际库区显示都跟着修好了\n"
    "\n"
    "**三、重要实测结论：规则限制库区是有效的**\n"
    "```\n"
    "「地面波Z」(16364)  区域=z    → 今天 36 个波次，库区全是 z  ✓\n"
    "「地面D-1」(15901)  区域=D    → 今天 88 个波次，库区全是 D  ✓\n"
    "「地面-A-0」(15940) 区域=A-0-0 → 无效区域码，不生效\n"
    "```\n"
    "· 区域码必须是**真实库区名**（`z` / `M` / `A` / `D`），`A-0-0` 这种不存在\n"
    "· `z-0-0-0-0` 属于 Z 库区，而 Z 库区只有这一个货位 → 区域 z ≈ 只扣这个货位 ✓\n"
    "\n"
    "**四、当前分工（程序触发不了 ERP 生成）**\n"
    "· 程序调 `/trade/wave/save`、页面点击、真实鼠标事件都试过：\n"
    "  ERP 返回「success」，但**不产出波次**\n"
    "· 所以：**你在 ERP 点「生成波次」，程序负责读取并显示结果**（已完全打通）\n"
    "  - 用「地面波Z」规则生成 → 库区 z\n"
    "  - 程序能立刻查到波次号、件数、库区\n"
)

assert os.path.isfile(INSTALLER), "安装包不存在：%s" % INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v2.61", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
