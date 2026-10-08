# -*- coding: utf-8 -*-
"""发布 v1.62：成波/拣完日志留痕排队时长。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = r"C:\Users\Kerwin\Desktop\发布\快麦扫码查询_安装版_v1.62.exe"
NOTES = ("**成波日志补上「排队时长」留痕**（配合 v1.61 的排队可见）。\n"
         "\n"
         "日志文件：数据目录下的 `auto_print.log`（主界面「打单进度」窗口底部能看到尾部）。\n"
         "\n"
         "· 排队过（等了超过 1 秒）才加后缀，没排队时不加，保持日志干净：\n"
         "  `生成波次：快递=中通 sids=9 save=True 波次=202801 created=True 排队等待=12.3s`\n"
         "· 排满 3 分钟没轮到的，单独记一条：\n"
         "  `生成波次：排队超时（等了 180.2s 仍没轮到），已让用户重试`\n"
         "· 「一键拣完」同样留痕（它也占用 ERP 浏览器，会和成波排队）：\n"
         "  `一键拣完：波次=202801 写入=True ok=True 状态=等待验货 排队等待=8.4s`\n"
         "\n"
         "另外：「一键拣完」也接入了排队闸门 —— 以前它在跑的时候，波次页的排队提示会显示不准"
         "（明明在忙却显示空闲），现在三个写 ERP 的操作（成波 / 拣完 / 取消）共用同一个闸门，状态一致。")

assert os.path.isfile(INSTALLER), "安装包不存在：%s" % INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v1.62", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
