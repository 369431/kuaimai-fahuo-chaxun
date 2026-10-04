# -*- coding: utf-8 -*-
"""发布 v1.47：多账号并发成波改成排队依次执行。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = r"C:\Users\Kerwin\Desktop\发布\快麦扫码查询_安装版_v1.47.exe"
NOTES = ("多账号一起生成波次：**改成排队依次执行**（不再互相挡掉）\n"
         "\n"
         "· 背景：成波都走**同一个 ERP 自动化浏览器**（同一个 ERP 登录），必须串行；"
         "之前是「抢不到锁就报错让你重试」，两个账号同时点会有一个白点。\n"
         "· 现在：**后来者自动排队等待**（最多 3 分钟），轮到就自动生成 → 两个账号都能成，"
         "不用反复手动重试；只有真的排太久（>3 分钟）才提示「前面还有波次在生成，请稍后再试」。\n"
         "· 「一键拣完」的写入也纳入**同一把锁**（它也走同一个 ERP 浏览器），"
         "避免「一个在生成、一个在拣完」互相插队。\n"
         "· 排队等过的请求会在结果里带上等了多久（`waited_s`）。\n"
         "· 上一版（v1.46）已含：波次号回读（波次管理接口）、未建成如实提示、货位库存预检。")

assert os.path.isfile(INSTALLER), INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v1.47", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
