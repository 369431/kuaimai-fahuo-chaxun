# -*- coding: utf-8 -*-
"""发布 v1.60：波次挑单并发化（提速约 2.4 倍）。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = r"C:\Users\Kerwin\Desktop\发布\快麦扫码查询_安装版_v1.60.exe"
NOTES = ("**生成波次提速约 2.4 倍**（挑单阶段的 ERP 查询改成并发）。\n"
         "\n"
         "**为什么慢**：以前挑单是「**逐个编码串行**」地问 ERP —— 每个编码要发 2 次查询"
         "（一次查候选单、一次查剩余时间），6 个编码就要串行发 12 次，实测每个编码约 **4.4 秒**。\n"
         "\n"
         "**现在**：一次把所有编码**并发**发出去（用浏览器自己的并发，不再一个个排队）。实测：\n"
         "· 候选单查询：6.58s → **2.45s**（2.7×）\n"
         "· 剩余时间查询：13.85s → **6.17s**（2.2×）\n"
         "· 挑单整体：约 20.4s → 约 **8.6s**（约 2.4×）\n"
         "\n"
         "**结果完全一致**：已用真实编码逐个对照，编码数 / 候选单数 / 挑中的 sids 全部相同；"
         "业务口径、挑单规则、排序规则（超时→加急→剩余时间）一律没改，只是把「排队问」改成「一起问」。")

assert os.path.isfile(INSTALLER), "安装包不存在：%s" % INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v1.60", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
