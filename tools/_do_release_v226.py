# -*- coding: utf-8 -*-
"""发布 v2.26：修「成波请求失败：Failed to fetch」+ 修排队提示从来没显示过。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = os.path.join(REPO, "packaging", "out", "快麦扫码查询_安装版_v2.26.exe")
NOTES = (
    "**v2.26：修「成波请求失败：Failed to fetch」**\n"
    "\n"
    "**这是什么错**\n"
    "· `Failed to fetch` 是浏览器报的**网络层**错误 —— 请求没到达服务器，或中途连接断了。\n"
    "  **不是成波本身失败**（这点很关键：ERP 那边可能已经把波次建出来了）。\n"
    "· 实测后台接口一切正常：ERP 已登录、成波接口正常响应。所以问题在「连接」不在「成波」。\n"
    "· 成波要 **30~180 秒**（含多账号排队），这段时间里网络/中转只要抖一下就会断，\n"
    "  而旧版一断就只给你看一句「Failed to fetch」，你既不知道结果，也没法续看。\n"
    "\n"
    "**这一版做的（断了也不丢结果）**\n"
    "· 成波结果**存在服务端**：每次成波带一个请求号，结果（含波次号）在服务端留底。\n"
    "· 前端遇到网络中断时，**不再直接报错**，而是自动回头去问「刚才那次成波结果出来了吗」，\n"
    "  每 4 秒问一次、最多问 3 分钟；取到了就照常显示波次号和配货明细。\n"
    "· 3 分钟仍取不到 → 明确提示「不要急着重复建波，先到波次记录/ERP 波次管理确认」，\n"
    "  避免网络抖动导致**重复建波**。\n"
    "\n"
    "**顺手修掉一个大 bug：排队提示从来没显示过**\n"
    "· 「前面还有 N 个波次，已等 X 秒」这个提示依赖 `/api/wave/queue`，\n"
    "  但这条路由**只注册在 POST 里**，前端却是用 GET 调的 → 一直 404 →\n"
    "  这个功能从上线起就没工作过（等 3 分钟时看着像卡死）。\n"
    "· 现在 GET / POST 都注册了，实测：\n"
    "    GET /api/wave/queue       → 200 {\"running\": false, \"waiting\": 0} ✓\n"
    "    GET /api/wave/last        → 200 ✓\n"
    "\n"
    "**给用户的话**\n"
    "· 以后再看到「连接中断，正在取回结果…」**请不要急着重新点成波**，等它自动取回来。\n"
    "· 如果提示「没能取回结果」，先去「波次记录」或 ERP「波次管理」看一眼有没有新波次，\n"
    "  确认没有再造，避免一个波次建两遍。\n"
)

assert os.path.isfile(INSTALLER), "安装包不存在：%s" % INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v2.26", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
