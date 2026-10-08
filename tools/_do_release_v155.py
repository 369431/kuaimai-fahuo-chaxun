# -*- coding: utf-8 -*-
"""发布 v1.55：现货可发「生成波次可填件数 + 生成后隐藏(全量拉取后恢复)」；撤掉取消波次按钮。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = r"C:\Users\Kerwin\Desktop\发布\快麦扫码查询_安装版_v1.55.exe"
NOTES = ("现货可发：生成波次可填件数；生成过的 SKU 先隐藏（**全量拉取后恢复**）；撤掉「取消波次」按钮\n"
         "\n"
         "**现货可发页**\n"
         "· 点「生成波次」后，中通/申通 按钮旁多了**件数输入框**：默认是本次最多可生成的件数，"
         "**你填几件就生成几件**（超出上限会自动收敛到上限）；「两个都生成」也各按你填的数走。\n"
         "· **生成波次成功后，该编码立即从列表隐藏**（避免刚生成又被重复拣货）。\n"
         "· 隐藏**只持续到下一次「全量拉取数据」**：全量重拉（或到点的自动全量）完成后，标记自动清空、"
         "又能查到（那时数据已更新）。每 5 分钟的增量刷新**不会**提前放出来。\n"
         "\n"
         "**波次页**\n"
         "· 「待成波清单」防丢加固：页头直接显示「中通 N 条 · 申通 M 条」；每份清单**单独备份**，"
         "若某一份被意外清空会**自动按备份恢复**；清单变动写本地日志（`_baglog.txt`，诊断用）。\n"
         "· 成波仍然**只清对应快递**那份清单（中通成波不动申通，反之亦然）。\n"
         "\n"
         "**波次记录页**\n"
         "· 按需求**移除「取消波次」按钮**（ERP 的取消必须先在「波次管理」页勾选波次才生效，"
         "程序侧无法稳定模拟勾选，故不做；需要取消请仍在该页面手动操作）。\n"
         "\n"
         "**质量**\n"
         "· 打包前用 `node --check` 校验三个页面内联 JS（本次全部通过）。")

assert os.path.isfile(INSTALLER), "安装包不存在：%s" % INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v1.55", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
