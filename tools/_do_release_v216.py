# -*- coding: utf-8 -*-
"""发布 v2.16：成波一律以 ERP 实时为准（去掉本地快照拦截 + 陈旧提示）。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = os.path.join(REPO, "packaging", "out", "快麦扫码查询_安装版_v2.16.exe")
NOTES = (
    "**v2.16：生成波次一律以 ERP 实时为准**\n"
    "\n"
    "**起因**：9699-加绒黑色S 点「生成波次」说没有可成波订单，但它旁边所有规格都有。\n"
    "查证结论：那一刻 ERP 里确实没有它的可成波订单（我拉了 ERP 生成波次页的完整 SKU 清单，\n"
    "1361 个 SKU 里没有它，而同款 M / 2XL / 常规黑色S 都在）。**ERP 侧是对的**。\n"
    "\n"
    "**但暴露了程序里两个真问题（本次都修了）**\n"
    "\n"
    "① **本地快照把实时查询拦住了**\n"
    "   点「生成波次」时，如果**本地**那一行的「可发」是 0，代码直接 return、\n"
    "   压根不去问 ERP —— 于是 ERP 明明有订单也点不出来。已删除这个拦截。\n"
    "   现在**任何时候点都会实时查 ERP**。\n"
    "\n"
    "② **本地快照数与 ERP 实时数被混用**\n"
    "   以前可成波上限写成 min(本地可发, ERP 实时)，两个不同来源取最小值，\n"
    "   结果既可能少给、又让人看不懂数字怎么来的。现在**上限只用 ERP 实时值**。\n"
    "\n"
    "**新增提示（避免再被旧数据误导）**\n"
    "· ERP 查不到候选、但本地快照却显示有大量订单时，会明确提示：\n"
    "  「ERP 实时查不到可成波订单　★ 本地快照还显示 N 单 —— 这份数据是旧的，请先全量重拉」\n"
    "· ERP 查到的明显少于本地显示（不足一半）时也会提示本地数据偏旧。\n"
    "\n"
    "**为什么会有这个差异**\n"
    "· 「现货可发」表用的是**本地索引**（上次全量/增量拉取时的快照），\n"
    "  订单进了波次/打了单之后，本地还留着旧数字，ERP 那边已经不认了。\n"
    "· 想对齐就点一次「全量重拉」，本地索引刷新后就一致了。\n"
)

assert os.path.isfile(INSTALLER), "安装包不存在：%s" % INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v2.16", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
