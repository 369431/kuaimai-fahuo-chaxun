# -*- coding: utf-8 -*-
"""发布 v2.55：成波扣减货位可自定义。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = os.path.join(REPO, "packaging", "out", "快麦扫码查询_安装包_v2.55.exe")
INSTALLER = os.path.join(REPO, "packaging", "out", "快麦扫码查询_安装版_v2.55.exe")
NOTES = (
    "**v2.55：成波扣减的货位可以自定义了（不再写死 a-0）**\n"
    "\n"
    "**一、网页上直接改**\n"
    "生成波次页输入框下面多了一行：\n"
    "```\n"
    "成波扣减货位：[ A-0-0-0 ] [保存]\n"
    "填货位编码或区：A-0-0-0 = 只算 a-0；D = 所有 D 区；留空 = 不限制。改完重扫编码生效。\n"
    "```\n"
    "· 保存后立即生效，会自动重扫当前编码\n"
    "· 设置存在 `kuaimai_settings.json` 的 `wave_stock_region`，重启不丢\n"
    "\n"
    "**二、填什么就扣什么**\n"
    "· `A-0-0-0` → 只算 a-0 这个货位\n"
    "· `D` / `C` / `B` → 该区所有货位\n"
    "· 留空 → 不限制（全部货位，等于老行为）\n"
    "· 前缀匹配：填 `A-0` 会匹配 `A-0-0-0`、`A-0-0-1`…\n"
    "\n"
    "**三、实测（同一编码切换货位，数量跟着变）**\n"
    "```\n"
    "9733-燕麦色M（526 个候选订单）\n"
    "  货位=A-0-0-0 → 区域可用   0 → 可生成   0\n"
    "  货位=C       → 区域可用 234 → 可生成 234\n"
    "  货位=B       → 区域可用 222 → 可生成 222\n"
    "  货位=留空    → 区域可用 814 → 可生成 526\n"
    "```\n"
    "可生成 = min(候选订单数, 所选货位可用数)\n"
    "\n"
    "**四、也修了页面上一处多余按钮**\n"
    "· 去掉了「按规则生成波次（地面-A-0）」按钮\n"
    "  （那个会一次性生成所有波次，与扫码流程无关，容易误点）\n"
)

assert os.path.isfile(INSTALLER), "安装包不存在：%s" % INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v2.55", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
