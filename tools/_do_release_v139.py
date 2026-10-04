# -*- coding: utf-8 -*-
"""发布 v1.39：调用 release.py 的 main()，中文说明走 UTF-8 字面量（不过控制台代码页）。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = r"C:\Users\Kerwin\Desktop\发布\快麦扫码查询_安装版_v1.39.exe"
NOTES = ("修复：**小米等手机上波次页「扫码添加」识别不到**（画面能开、就是扫不出来）。\n"
         "· 原因：波次页原来先试浏览器自带的条码识别，而部分国产浏览器这个能力是空壳 —— "
         "能开画面但永远识别不到；首页那套之所以能用，是因为它用的是本地 ZXing 解码。\n"
         "· 现在：波次页的「扫码添加」也**改成优先用 ZXing 解码**（和首页同一套码制："
         "CODE_128/39/93、ITF、EAN/UPC、QR、DataMatrix，并开 TRY_HARDER），"
         "浏览器自带识别只作为兜底。\n"
         "· 桌面 Chrome/Edge 不受影响；打单浏览器与波次功能照旧。")

assert os.path.isfile(INSTALLER), INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v1.39", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
