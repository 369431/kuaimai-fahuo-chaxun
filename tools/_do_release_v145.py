# -*- coding: utf-8 -*-
"""发布 v1.45：调用 release.py 的 main()，中文说明走 UTF-8 字面量（不过控制台代码页）。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = r"C:\Users\Kerwin\Desktop\发布\快麦扫码查询_安装版_v1.45.exe"
NOTES = ("PDA 扫码枪直接扫到输入框（网页端）：\n"
         "· 之前页面只认「回车」，而多数 PDA 扫码枪默认**不带回车后缀** —— 字打进去了但没人提交，"
         "看起来「没反应」。\n"
         "· 现在加了扫码枪模式：① **一串快速输入停下（~150ms）就自动提交**（≥6 字符才算，"
         "人手慢打不会误触发）② 输入框**没聚焦也在页面层接住**（打字落到页面上也认）"
         "③ 点页面空白处**自动把焦点放回编码框**（PDA 浏览器常丢焦点）。\n"
         "· 带回车后缀的枪照旧只提交一次；首页与波次页都生效。\n"
         "· 提示：PDA 的扫码设置里如果能把「后缀/结束符」设成 Enter，体验最稳（两条都兜住了）。")

assert os.path.isfile(INSTALLER), INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v1.45", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
