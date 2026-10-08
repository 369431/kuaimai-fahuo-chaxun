# -*- coding: utf-8 -*-
"""发布 v1.64：热修「扫码报 ERP 返回错误：result=1」。"""
import os
import sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INSTALLER = r"C:\Users\Kerwin\Desktop\发布\快麦扫码查询_安装版_v1.64.exe"
NOTES = ("**热修：扫码报「ERP 返回错误：result=1」**（v1.61 ~ v1.63 的问题，抱歉）。\n"
         "\n"
         "**原因**：快麦 ERP 的**正常**返回里 `result=1` 就是**成功码**：\n"
         "`{\"clueId\":\"…\",\"data\":[{…订单…}],\"qTime\":714,\"result\":1}`\n"
         "而 v1.61 为了识别「会话异常」加的那个判断，把「`result` 不是 0/空」**一律当成了错误** → "
         "于是正常的 result=1 也被报成「ERP 返回错误：result=1」，扫码全废。\n"
         "\n"
         "**修法**：判定改成**以 `message` 为主**、`result` 只作辅助：\n"
         "· 正常（`result=1`，有没有数据都算正常）→ 不再报错；\n"
         "· 登录失效（`会话异常，请重新登录` / result=901）→ 仍然明确提示「请在软件里点『登录 ERP』重新登录」；\n"
         "· 其它带 message 且拿不到数据的 → 照旧报错。\n"
         "\n"
         "**已实测**：7 种返回形态全部符合预期（含 result=1 有数据 / result=1 空数据 / result=901 会话异常），"
         "并用真机跑了一次扫码：`max=25 中通1 申通24` 正常返回。\n"
         "\n"
         "装了这一版扫码即恢复。")

assert os.path.isfile(INSTALLER), "安装包不存在：%s" % INSTALLER
sys.path.insert(0, REPO)
os.chdir(REPO)
sys.argv = ["release.py", "--version", "v1.64", "--installer", INSTALLER, "--notes", NOTES]

import release  # noqa: E402

rc = release.main()
print("\nrelease.main() returned", rc)
sys.exit(rc)
