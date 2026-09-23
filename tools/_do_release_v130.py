# -*- coding: utf-8 -*-
"""发布 v1.30：调用 release.py 的 main()，中文说明走 UTF-8 字面量（不过控制台代码页）。

注意：release.py 内部用 subprocess 跑 gh / git，会继承本进程环境变量 ——
所以运行本脚本前先设好 HTTPS_PROXY（本机 git 直连 github.com 不通，要走 65532 代理）。
"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = r"C:\Users\Kerwin\Desktop\发布\快麦扫码查询_安装版_v1.30.exe"
NOTES = ("修「同一编码重复提交 → 多打一遍」：网页/手机点「可发」时，若该编码短时间内被提交多次，"
         "以前每次都各建一个任务、各去打一遍（实测 9681-燕麦色S ×5 提交 3 次打了 15 张）。\n"
         "现在：同一编码已有未完成任务（排队/正在打），或 60 秒内刚打完 → 不再建第二个任务，"
         "网页会提示「本次未新建打单任务（避免重复出纸）」，日志同步留痕。\n"
         "扫码记录照写（只是不建任务）；确需追加打印时可用 force 参数绕过。\n"
         "注：与 v1.29 修的「任务重试多打」不同根因，那条已修。")

assert os.path.isfile(INSTALLER), INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v1.30", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
