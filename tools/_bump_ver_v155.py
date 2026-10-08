# -*- coding: utf-8 -*-
"""把 APP_VER 从 v1.54 提到 v1.55（精确替换 + 校验）。"""
import io
import os
import sys

ROOT = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
p = os.path.join(ROOT, "desktop", "kuaimai_client.py")
OLD = 'APP_VER = "v1.54"'
NEW = 'APP_VER = "v1.55"'
s = io.open(p, encoding="utf-8").read()
n = s.count(OLD)
if n != 1:
    print("ABORT: %r 出现 %d 次" % (OLD, n))
    sys.exit(1)
io.open(p, "w", encoding="utf-8", newline="").write(s.replace(OLD, NEW))
for i, line in enumerate(io.open(p, encoding="utf-8"), 1):
    if "APP_VER" in line:
        print("%d: %s" % (i, line.rstrip()))
