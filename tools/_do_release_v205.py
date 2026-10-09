# -*- coding: utf-8 -*-
"""发布 v2.05：API 设置换成 Qt 窗（不再弹旧界面）+ 补测试连接/保存接口。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = os.path.join(REPO, "packaging", "out", "快麦扫码查询_安装版_v2.05.exe")
NOTES = (
    "**v2.05：API 设置也换成电脑版自己的界面（不再弹旧窗口）**\n"
    "\n"
    "**① API 设置 → 电脑版自己的窗口**\n"
    "· 以前点「API 设置」弹的是旧版窗口；现在跟「对外访问设置 / 子客户端管理 / 打印分工」\n"
    "  一样，用电脑版统一的界面。\n"
    "· 字段一致：网关地址、API 版本、appKey、appSecret、refreshToken、sessionId、\n"
    "  签名方式、签名结果大写（敏感字段可点「显示」核对）。\n"
    "· 实测：读取 8 个字段正常；点「保存并应用」→「已保存并生效」；\n"
    "  「测试连接」→「接口可用」（真调一次快麦开放平台）。\n"
    "\n"
    "**② 补上电脑版侧的两个接口**\n"
    "· `POST /api/desktop/api_conf`：保存 API 参数（写 kuaimai_api.json 并立即生效）\n"
    "· `POST /api/desktop/api_test`：测试连接\n"
    "  这两个接口以前主程序里根本没有，所以电脑版那个窗的「保存」点了会报错。\n"
    "\n"
    "**③ 顺带修掉的**\n"
    "· 电脑版里同一个「API 设置」窗定义了两份（后一份把前一份覆盖），已去掉重复。\n"
    "· 从别的线程操作界面会统一回到主线程执行（避免偶发「点了没反应」）。\n"
    "\n"
    "**目前电脑版已全部用新界面（不再弹旧窗口）的按钮**\n"
    "  API 设置 / 对外访问设置 / 子客户端管理 / 打印分工 / 现货可发 / 按条件筛选 /\n"
    "  改库存日志 / 盘点 / 批次查询 / 每日发货量 / 检查更新 / 打单进度 / 各设置开关\n"
)

assert os.path.isfile(INSTALLER), "安装包不存在：%s" % INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v2.05", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
