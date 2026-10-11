# -*- coding: utf-8 -*-
"""发布 v2.24：修「HTTPS 能访问、HTTP 不行」。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = os.path.join(REPO, "packaging", "out", "快麦扫码查询_安装版_v2.24.exe")
NOTES = (
    "**v2.24：修「https 能访问、http 不行」**\n"
    "\n"
    "**原因**\n"
    "· frpc 的配置模板里**只写了两个映射，都是指到 HTTPS 端口**：\n"
    "    kuaimai-https-9443 → 本机 9443\n"
    "    kuaimai-https-443  → 本机 9443\n"
    "  **完全没有 80 端口（HTTP）的映射** → 所以 http://域名 没有任何隧道在转发，必然打不开。\n"
    "· 本机其实同时开着两个服务：**9443（HTTPS）** 和 **8790（HTTP 明文）**，\n"
    "  只是 8790 从来没被 frp 接出去。\n"
    "\n"
    "**这一版做的**\n"
    "① frpc 配置模板新增 80 端口映射（默认开）：\n"
    "     kuaimai-http-80 → 本机 8790（明文服务）\n"
    "② 本机的明文服务会把 HTTP 请求**自动 302 跳到 HTTPS**，规则：\n"
    "     · 用域名访问 + 明文进来 → 跳 https://域名:9443（保留原路径和参数）\n"
    "     · 已经是从 HTTPS 转来的（X-Forwarded-Proto: https）→ **不跳**（防死循环）\n"
    "     · localhost / 127.0.0.1 / 内网 IP → **不跳**（办公室内网直连更方便）\n"
    "   这样证书和登录状态仍然只走 HTTPS，HTTP 只是「入口 + 跳转」。\n"
    "③ 「对外访问设置」窗新增两个开关：\n"
    "     ☑ 开放 HTTP 端口 80（自动跳 HTTPS）\n"
    "     ☑ 开放 HTTPS 端口 443\n"
    "\n"
    "**实测**\n"
    "· 生成的 frpc.toml 现在包含：name=kuaimai-http-80 / localPort=8790 / remotePort=80\n"
    "· 跳转逻辑 6 种情况全部正确：\n"
    "    域名+明文 → 跳；域名已带 https → 不跳；localhost / 内网 IP → 不跳；无 Host → 不跳\n"
    "· 跳转后地址形如 https://kmcx.cc:9443/scan?x=1（保留路径与参数）\n"
    "\n"
    "**注意**\n"
    "· 80 端口能否用，取决于你 frp 服务器上 80 有没有被别的程序占用；\n"
    "  启动隧道后如果报「port already used」，就是服务器那边 80 被占了（要换端口或腾出来）。\n"
    "· 如果只想让 HTTPS 能访问、不想要 80，可以在窗口里把「开放 HTTP 端口 80」取消勾选。\n"
)

assert os.path.isfile(INSTALLER), "安装包不存在：%s" % INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v2.24", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
