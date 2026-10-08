# -*- coding: utf-8 -*-
"""发布 v1.33：调用 release.py 的 main()，中文说明走 UTF-8 字面量（不过控制台代码页）。

本机网络：已探明 **直连 github.com 可用**，本地代理端口全关
→ **不设 HTTPS_PROXY**，让 git / gh 直连（与 v1.32 那轮一致）。
"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = r"C:\Users\Kerwin\Desktop\发布\快麦扫码查询_安装版_v1.33.exe"
NOTES = ("新增「上架后自动智能审核」（默认关，在界面上勾选开）：上架成功后自动把"
         "这批编码的待审核单智能审掉，不用再回 ERP 手点。\n"
         "· **只走智能审核**（等于平时手点那一下），绝不碰缺货审核 / 强制审核 / 其他审核类。\n"
         "· 按规则筛选：**缺货异常单跳过**，**有留言/备注且未人工处理的跳过**，其余才送审。\n"
         "· 审核走 ERP 自己的审单规则，不放行异常单；审核失败只记日志，不影响上架。\n"
         "· 该功能只在主客户端生效。\n"
         "新增「自动上架 / 智能审核日志」：在「打单进度」面板底部，直接看得到"
         "自动上架和智能审核的实时日志（auto_putaway.log + auto_audit.log 尾部合并），"
         "不用再去翻数据目录找文件。")

assert os.path.isfile(INSTALLER), INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v1.33", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
