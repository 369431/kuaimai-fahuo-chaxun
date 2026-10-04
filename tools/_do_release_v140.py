# -*- coding: utf-8 -*-
"""发布 v1.40：调用 release.py 的 main()，中文说明走 UTF-8 字面量（不过控制台代码页）。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = r"C:\Users\Kerwin\Desktop\发布\快麦扫码查询_安装版_v1.40.exe"
NOTES = ("修复：波次页「扫码添加」在手机上扫不出来（多台手机都不行）。\n"
         "· 原因：首页能用是因为中转注入了本地 ZXing 的扫码增强层（scan.js，靠 "
         "`btnCam` / `video` / `camBox` 三个元素接管）；波次页元素名不一样、也没引它，"
         "所以走的是浏览器自带识别（部分手机是空壳，扫不出）。\n"
         "· 现在：波次页按钮改名为 `btnCam`（并补 `btnCamStop`），页面自己引 `/km/scan.js`，"
         "扫码增强层直接接管 —— 和首页**同一套解码**；扫到码后回调页面 `window.query` 自动加入清单。\n"
         "· 原来那套（ZXing→原生识别）保留作兜底：经 8790 直连或脚本没加载时仍可用。\n"
         "· 注意：手机浏览器请**刷新页面**再试。")

assert os.path.isfile(INSTALLER), INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v1.40", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
