# -*- coding: utf-8 -*-
"""发布 v1.63：成波后隐藏改为服务端共享。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = r"C:\Users\Kerwin\Desktop\发布\快麦扫码查询_安装版_v1.63.exe"
NOTES = ("**「成波后隐藏」改为服务端共享**（以前只有本浏览器当前会话内才隐藏）。\n"
         "\n"
         "· 生成波次成功后，程序会把这一波用到的编码标记「已生波次」→ 这些编码在**现货可发**页"
         "对**所有账号、所有设备都看不到**（避免刚成波又被重复拣货）。\n"
         "· 隐藏**只持续到下一次「全量拉取数据」**：全量重拉（或到点的自动全量）完成后标记自动清空、"
         "编码重新出现（那时数据已更新）。每 5 分钟的**增量刷新不会**提前放出来。\n"
         "· 网页端早就在按这个字段过滤了，这版把**后端补齐**，两边终于对上（以前字段一直缺，等于没生效）。\n"
         "· 另外：「取消波次」（在波次管理页勾选后再调 ERP 接口那条路）按决定**不做**，"
         "这次把它的残留代码一并清掉了（前端本就没入口，后端接口/实现已移除）。")

assert os.path.isfile(INSTALLER), "安装包不存在：%s" % INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v1.63", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
