# -*- coding: utf-8 -*-
"""发布 v1.57：波次页单快递刷新保留 + 待成波合计件数（上限 500）+ 补 baglog 接口。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = r"C:\Users\Kerwin\Desktop\发布\快麦扫码查询_安装版_v1.57.exe"
NOTES = ("波次页三处改进。\n"
         "\n"
         "**「待成波清单」新增合计件数（吸顶常驻）**\n"
         "· 清单上方常驻一条大字横幅：把清单里所有编码的数量相加，直接显示「合计 / 500」。\n"
         "· 未超上限=绿色「还可加 N 件」；**超过 500 变红色 + 红框 + 数字放大**，并提示「已超上限 N 件，请减少后再成波」。\n"
         "· 手动改某个编码的数量时，合计实时跟着变；往下滚清单时横幅吸顶不掉。\n"
         "\n"
         "**单快递模式也能刷新保留了**\n"
         "· 原来「单快递模式（旧）」刷新会丢清单，现在也会保存并在刷新后恢复；"
         "切换快递仍会清空当前清单（语义不变）。\n"
         "\n"
         "**补上 baglog 接口**\n"
         "· 波次页「待成波清单变动日志」（`_baglog.txt`）的后端接口补齐，网页与后端一致。")

assert os.path.isfile(INSTALLER), "安装包不存在：%s" % INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v1.57", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
