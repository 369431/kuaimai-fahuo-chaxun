# -*- coding: utf-8 -*-
"""发布 v2.25：修「订单查询看不到订单图」。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = os.path.join(REPO, "packaging", "out", "快麦扫码查询_安装版_v2.25.exe")
NOTES = (
    "**v2.25：修「订单查询看不到订单图」**\n"
    "\n"
    "**原因**\n"
    "· 订单图片是程序**代理转发**的（避免把本机变成任意请求转发器），只放行白名单里的图片域名。\n"
    "· 但白名单里**缺了微信小店 / 腾讯系**（`tc.qq.com` 等）和**快手 CDN**（`kwimgs.com`）等域名，\n"
    "  这些平台的订单图片被直接拒掉 → 页面上就是没有图。\n"
    "· 实测复现：\n"
    "    抖音图  p9-aio.ecombdimg.com   → 代理 200 ✓\n"
    "    微信图  wst.wxapp.tc.qq.com    → 代理 **400 拒绝** ✗（白名单没有它）\n"
    "\n"
    "**这一版修的**\n"
    "① 图片域名白名单补全（13 个 → 36 个）：微信小店/腾讯系（tc.qq.com、qq.com、gtimg.com、\n"
    "   qpic.cn…）、快手 CDN（kwimgs.com）、有赞/微店、阿里云 OSS、京东、拼多多等。\n"
    "② Referer 不再写死抖音：按图片域名给对应平台的 Referer，取不到再**去掉 Referer 重试一次**\n"
    "   （实测有些 CDN 反而不接受外来 Referer）。\n"
    "③ 图片取不到时显示「图片取不到/无图」占位块，不再是个破图或空白。\n"
    "④ 顺手修掉一个隐患：白名单原来写成逗号分隔的字符串形式，容易被误改成字符串\n"
    "   （那样会当成「单个超长域名」、所有图全挂），现在明确是**元组**并加了注释。\n"
    "\n"
    "**实测（6 个真实订单图片全部成功）**\n"
    "  6045797692651684  wst.wxapp.tc.qq.com   → ✓ 329610 字节（**之前失败的微信图**）\n"
    "  6044406448699849  p9-aio.ecombdimg.com  → ✓ 372156 字节\n"
    "  6046571777792016  p9-aio.ecombdimg.com  → ✓ 428375 字节\n"
    "  …共 6 个全过；恶意域名 / 非 https 仍然拒绝 ✓\n"
)

assert os.path.isfile(INSTALLER), "安装包不存在：%s" % INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v2.25", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
