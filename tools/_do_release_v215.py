# -*- coding: utf-8 -*-
"""发布 v2.15：修「扫描面板直接成波后，可生成数不变」的真正原因（跨页面函数调用失败）。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = os.path.join(REPO, "packaging", "out", "快麦扫码查询_安装版_v2.15.exe")
NOTES = (
    "**v2.15：修「扫描面板直接成波」后数字不变（上次没修对）**\n"
    "\n"
    "**上次（v2.13）为什么没生效**\n"
    "· v2.13 我把刷新用的 `refreshMaxForCodes` 函数定义在了**波次页**的脚本里，\n"
    "  但在**扫描面板/现货可发页**里去调它。\n"
    "· 这两页是各自独立的 HTML + 独立 `<script>`，**函数不互通** → 调用直接报\n"
    "  `ReferenceError` → 而我又写成了 `try{...}catch(e){}`（静默吞异常）→ 完全没生效。\n"
    "· 所以你说的「扫描面板直接成波」，v2.13/v2.14 都没有真正修到。\n"
    "\n"
    "**这一版改成每页自包含（各自定义，不再跨页面调用）**\n"
    "· 扫描面板/现货可发页：新增自己的 `refreshStockRowAfterWave()` 和 `refreshAllStockMaxQuiet()`\n"
    "· 波次页：保留自己的 `refreshMaxForCodes()` 和 `refreshAllMaxQuiet()`\n"
    "· 两页都有：成波成功立刻按实际件数扣减 + 拉 ERP 实时值覆盖；进页面重算；停留时每 60 秒校一次\n"
    "\n"
    "**顺带修正一个概念混淆**\n"
    "· 「可发」（min(在架,待发) − 多件预留）和 ERP 的「最大可生成」是**两个不同的量**，\n"
    "  不能再互相覆盖。现在只更新各自该更新的那个。\n"
    "\n"
    "**底层数据一直是正确的（已实测）**\n"
    "· ERP 实时：524 → 建 1 件波次 → 立刻 523。\n"
    "· 订单不会重复进波次：候选 523 → 建波 1 件 → 522，且该 sid 已不在候选里。\n"
)

assert os.path.isfile(INSTALLER), "安装包不存在：%s" % INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v2.15", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
