# -*- coding: utf-8 -*-
"""发布 v1.50：确认并保证包含「货位在架/货位 后台自动刷新」（方案 A）。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = r"C:\Users\Kerwin\Desktop\发布\快麦扫码查询_安装版_v1.50.exe"
NOTES = ("货位在架/货位：**后台自动刷新**（方案 A）\n"
         "\n"
         "· 波次页显示的在架/货位，会在**后台自动保持新鲜**：进页面、每次扫码后、以及停留时每 30 秒"
         "校一次新鲜度；**超过 5 分钟**（或索引为空）→ 服务端**起后台线程刷一次**，"
         "**不阻塞扫码**（扫码请求永远不等全量拉取）。\n"
         "· 页面标注数据时间：**「货位库存：更新于 HH:MM:SS」**；刷新中显示「更新中…」，"
         "刷完数字与时间自动更新。\n"
         "· 失败有 60 秒冷却，不狂拉；子端（没有开放平台 API）不触发，交由主端。\n"
         "· 刷新间隔可在设置里改（`shelf_refresh_min`，默认 5 分钟）。\n"
         "· 说明：ERP 那个货位接口**不能按编码过滤**（实测 9 个参数名都不吃）、单页上限 500 条，"
         "全量 ~4314 行要 9 次请求，所以「每次扫码现场拉」会卡 4~5 秒 —— 故采用后台刷新。")

assert os.path.isfile(INSTALLER), INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v1.50", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
