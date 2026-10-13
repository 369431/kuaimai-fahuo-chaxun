# -*- coding: utf-8 -*-
"""发布 v2.32：修「实发订单数一直显示 …」（后台刷新线程标志永不清空）。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = os.path.join(REPO, "packaging", "out", "快麦扫码查询_安装版_v2.32.exe")
NOTES = (
    "**v2.32：修「实发订单数又看不到了（一直 …）」**\n"
    "\n"
    "**原因（一个"永不清空"的标志位）**\n"
    "· 实发订单数是**后台异步抓**的：点开波次记录时，程序去 ERP 逐个波次回读\n"
    "  每单的打印次数，抓到就缓存。为了防止重复起线程，代码里有个标志：\n"
    "      if _WEB_STATE.get(\"wave_printed_thread\") is not None:\n"
    "          return            # ← 直接返回\n"
    "· 问题是这个标志**线程跑完后从来不清空** → **只有第一次会真抓**，\n"
    "  之后每次调用都直接 return → 缓存永远停在第一批波次上。\n"
    "· 现象就是你看到的：新波次的 key 在缓存里根本不存在 → 整列显示「…」（读取中）。\n"
    "  实测抓到的现场：\n"
    "      recent 波次号  = 208350, 208349, 208348 … 208322\n"
    "      printed 的 key = 208085, 208084, 208083 … 208060\n"
    "      对得上 = 0 / 20        ← 全是过期缓存\n"
    "\n"
    "**这一版修的**\n"
    "· 标志改成「**只在线程还活着时**跳过」（is_alive），跑完用 finally 一定解除，\n"
    "  下一轮刷新就能重新抓。\n"
    "· 顺手清理已经不在列表里的旧波次缓存（超过 1 小时的），避免缓存无限长。\n"
    "\n"
    "**实测（修复后）**\n"
    "  第 1 次读取：printed 对得上 0 / 20（刚开始抓）\n"
    "  第 2 次读取：printed 对得上 **16 / 20** ✓ 数字出来了\n"
    "  电脑端表格实发列（真开窗口渲染）：\n"
    "    208351 | 实发 26 / 312      208349 | 实发 36 / 302\n"
    "    208347 | 实发 117 / 185     208346 | 实发 79 / 191\n"
    "    …254/254、91/147、152/152、411/411、500/500 —— 整列 20 行都有数据\n"
    "\n"
    "**怎么看「…」**\n"
    "  刚打开页面时是正常的「读取中」（后台逐单回读要几秒到几十秒，\n"
    "  波次多、每波几百单时要更久）；点一下「刷新」，或者等页面自动轮询就会变成数字。\n"
    "  如果**一直**是 …（等一分钟都没变），那才是问题 —— 现在已修好。\n"
)

assert os.path.isfile(INSTALLER), "安装包不存在：%s" % INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v2.32", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
