# -*- coding: utf-8 -*-
"""发布 v2.13：修「生成波次后最大可生成数不变」。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = os.path.join(REPO, "packaging", "out", "快麦扫码查询_安装版_v2.13.exe")
NOTES = (
    "**v2.13：修「生成波次后 最大可生成 数字不变」**\n"
    "\n"
    "**你反馈的现象**\n"
    "· 9699-常规燕麦色M 生成之前显示能生成 600 件；\n"
    "  生成 210 件的 205223 波次之后，再看这个编码**还是 600 件**（应该 490 左右）。\n"
    "· 205225 生成时也显示 600 件。\n"
    "\n"
    "**查证过程（先确认 ERP 到底有没有实时扣减）**\n"
    "· 实测：查该编码 = 524 件 → 真的建一个 1 件的波次（205231，已建）→ **立刻变 523 件**，\n"
    "  0 秒/3 秒/8 秒/20 秒都是 523 → **ERP 侧完全实时、数据没问题**。\n"
    "· 所以问题在界面：`it.max`（最大可生成 N 件）是**加入清单那一刻**存下的旧值，\n"
    "  成波成功后从不重算 → 一直显示成波前的数字。\n"
    "\n"
    "**修法**\n"
    "· 新增 `refreshMaxForCodes()`：成波成功后，对涉及的编码\n"
    "    ① 先按**本次实际成波件数**本地立刻扣减（数字马上变小，不用等网络）\n"
    "    ② 再调 `/api/wave/lookup` 拿 ERP **实时值**覆盖（权威）\n"
    "    ③ 若数量超过剩余可生成数，把输入框也收窄到剩余量\n"
    "· 已接到**三处成波路径**：\n"
    "    · 扫描面板：单个编码直接成波\n"
    "    · 扫描面板：两个快递都生成\n"
    "    · 生成波次页：清单合并成一个波次\n"
    "\n"
    "**说明**\n"
    "· 这是**网页版界面**的修复，网页版是打包进客户端的，所以要升级才生效。\n"
    "· 测试波次 205231（1 件）是我为了定位问题真建的，照常拣货/验货即可，不影响数据。\n"
)

assert os.path.isfile(INSTALLER), "安装包不存在：%s" % INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v2.13", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
