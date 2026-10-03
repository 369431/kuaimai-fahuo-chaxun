# -*- coding: utf-8 -*-
"""发布 v1.38：调用 release.py 的 main()，中文说明走 UTF-8 字面量（不过控制台代码页）。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = r"C:\Users\Kerwin\Desktop\发布\快麦扫码查询_安装版_v1.38.exe"
NOTES = ("网页「生成波次」扫码体验修复：**扫出来是 0 时不再一头雾水**。\n"
         "· 原因：波次按快递拆（中通/申通各一个波次），页面默认停在「中通」；"
         "扫到全是申通的货就会显示 0 —— 其实货是有的。\n"
         "· 现在：当前快递没货、另一种有货时，直接提示「**XX 有 N 件**」并给一个"
         "「**切到 XX 并添加**」按钮，一键换快递加上；\n"
         "· 两种快递都没有时，明确写明原因：该编码没有「待发货 + 未成波 + 一单一件」的订单"
         "（可能已生成波次 / 已打印 / 是多件单），并且**不再往清单里塞 0 件的行**。")

assert os.path.isfile(INSTALLER), INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v1.38", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
