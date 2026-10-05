# -*- coding: utf-8 -*-
"""发布 v1.49：波次页改版（删添加按钮/删提示/显示在架+货位+多件预留/记录页排版）。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = r"C:\Users\Kerwin\Desktop\发布\快麦扫码查询_安装版_v1.49.exe"
NOTES = ("生成波次页改版\n"
         "· **删掉「添加」按钮**：手动输入**回车即添加**；摄像头「扫码添加」保留。\n"
         "· **删掉那句提示文案**（手动输入…最大可生成件数）。\n"
         "· **扫码后新增显示**：**在架数量 + 货位**（在架 0 也照样显示货位；没有货位记录才写无货位）、"
         "以及**建议多件预留 N 件**（= 该编码「一单多件/组合单」的件数合计；现货可发 = "
         "min(在架,待发) − 一单多件件数，波次只吃一单一件，多件的留着）。\n"
         "· **波次记录页排版优化**：窄屏/手机更清楚（表格可横向滑动、状态更醒目、数字等宽、"
         "时间与波次号不再挤成两行），「一键拣完」与刷新照旧。\n"
         "· 既有功能不动：波次号回读（波次管理接口）、未建成如实提示、货位库存预检、成波排队锁。\n"
         "· 说明：在架/货位取**本机货位索引**（缓存快照）。要「每次扫码都现场重拉」可以再加开关。")

assert os.path.isfile(INSTALLER), INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v1.49", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
