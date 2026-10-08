# -*- coding: utf-8 -*-
"""发布 v2.04：把「点了没反应」的异常写进日志（便于以后排查）。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = os.path.join(REPO, "packaging", "out", "快麦扫码查询_安装版_v2.04.exe")
NOTES = (
    "**v2.04：设置窗全部正常 + 加排查日志**\n"
    "\n"
    "**实测结果（9 个设置窗全部 0.0 秒弹出）**\n"
    "· API 设置 / 对外访问设置 / 子客户端管理 / 打印分工 / 现货可发 /\n"
    "  批次查询 / 改库存日志 / 打单进度 —— 全部正常。\n"
    "· 库存盘点按设计只在网页版有（电脑版不提供入口）。\n"
    "\n"
    "**这一版修的根因（v2.03 里已修，这版继续加固）**\n"
    "· 电脑版为了不显示旧界面，把后台的 Tk 根窗隐藏了；而 Tk 的规则是\n"
    "  **transient(隐藏的父窗) 会让子窗自己也被隐藏**（窗口建出来了但看不见）——\n"
    "  这就是「点 API 设置/对外访问/现货可发没反应」的真正原因。已把 transient\n"
    "  换成安全版本。\n"
    "· 登录会话没交接给业务核心：登录窗把会话文件删了 → 启动器读不到 →\n"
    "  业务核心从没启动 → 界面每个请求都被回「请先登录」。已修。\n"
    "· 启动器现在**采纳登录窗的 token** 作为权威，并写回权威会话文件，\n"
    "  界面 token 不被接受时会自动读它自愈。\n"
    "\n"
    "**新增排查日志**\n"
    "· 如果以后还有点按钮没反应，程序会把异常写进 `%TEMP%\\km_action.log`\n"
    "  （以前这类异常被队列静默吞掉，完全查不到原因）。\n"
)

assert os.path.isfile(INSTALLER), "安装包不存在：%s" % INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v2.04", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
