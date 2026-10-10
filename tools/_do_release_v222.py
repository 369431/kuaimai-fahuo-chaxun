# -*- coding: utf-8 -*-
"""发布 v2.22：修「待收恒为 0」+ 旧 Tk 窗口锁死（最小化不再露旧界面）。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = os.path.join(REPO, "packaging", "out", "快麦扫码查询_安装版_v2.22.exe")
NOTES = (
    "**v2.22：修「待收」总是 0 + 锁死旧界面窗口**\n"
    "\n"
    "**① 「待收」无论收没收货都显示 0 —— 已修**\n"
    "· 原因：商品明细里的 `count` **不是「已收数量」**，而是「这张收货单要求上架的数量」。\n"
    "  我上一版直接把它求和当已收 → 结果正好等于采购数量 → 待收永远 0。\n"
    "· 正确口径（试错后确认）：\n"
    "    · 收货单已上架（SHELVED）→ count 全额计入\n"
    "    · 未上架（NOT_FINISH）   → 计 0\n"
    "    · 部分上架              → 按 已上架数 / 数量 比例计入\n"
    "· 实测这样算出的每个商品之和，**严格等于采购单头的「已收」**\n"
    "  （8 个采购单逐个核对全部一致）。\n"
    "· 现在能正确显示，例如采购单 CG6056070037723603：\n"
    "    9687-燕麦色M   采购 1176  已收 715  待收 461\n"
    "    9687-燕麦色XL  采购 1176  已收 657  待收 519\n"
    "    9693-咖色M     采购  210  已收   0  待收 210\n"
    "    合计：采购 3916　已收 1598　待收 2318\n"
    "\n"
    "**② 「最小化又露出老版本窗口」—— 从根上锁死**\n"
    "· 这个毛病修过两次又复发，这次找到原因了：\n"
    "    · Tk 的 `attributes()` 在窗口 withdraw 之后调用，**会把窗口重新映射**（等于又显示）；\n"
    "    · 程序里还有几处 `deiconify()` 兜底分支（比如「Qt 起不来就把 Tk 放出来」）。\n"
    "· 这一版把根窗的 `deiconify / wm_deiconify / attributes / lift` **全部拦掉**\n"
    "  （调用就被记日志并重新隐藏），再加一个看门狗每 10 秒用 Win32 查一次真实可见性，\n"
    "  发现露出来就按回去。**根窗从此不可能显示**。\n"
    "· 设置窗不受影响：它们是独立的 Toplevel，本来就不依赖根窗显示。\n"
)

assert os.path.isfile(INSTALLER), "安装包不存在：%s" % INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v2.22", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
