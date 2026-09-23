# -*- coding: utf-8 -*-
"""核验打包产物内含新代码（改进版）。

- PYZ 里的自建模块：extract → 遍历 co_consts **与 co_names**（函数名/全局名不在 consts 里）
- 入口脚本 kuaimai_scan 在 CArchive 里（不在 PYZ）→ 取字节 → marshal.loads
"""
import marshal
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

EXE = r"C:\Users\Kerwin\Desktop\kuaimai发货查询\packaging\staging\快麦扫码查询.exe"
from PyInstaller.archive.readers import CArchiveReader   # noqa: E402

ca = CArchiveReader(EXE)
names = [str(n) for n in ca.toc]
pyz_name = [n for n in names if n.endswith(".pyz")][0]
z = ca.open_embedded_archive(pyz_name)

allok = True


def collect(code, out):
    for c in code.co_consts:
        if isinstance(c, str):
            out.add(c)
        elif hasattr(c, "co_consts"):
            collect(c, out)
        elif isinstance(c, (tuple, frozenset, list)):
            for x in c:
                if isinstance(x, str):
                    out.add(x)
                elif hasattr(x, "co_consts"):
                    collect(x, out)
    for n in getattr(code, "co_names", ()) or ():
        if isinstance(n, str):
            out.add(n)


def check(label, code, needles):
    global allok
    found = set()
    collect(code, found)
    for nd in needles:
        hit = any(nd in s for s in found)
        print("   %-46s %s" % ("%s :: %s" % (label, nd), "FOUND" if hit else "MISSING"))
        if not hit:
            allok = False


print("== PYZ 模块 ==")
WANT = {
    "kuaimai_print_jobs": ["dup_reason", "add_job_checked", "DUP_WINDOW"],
    "kuaimai_webui": ["本次未新建打单任务", "j.dup_msg"],
    "kuaimai_client": ["v1.30"],
    "auto_print_watcher": ["watch_claims"],
}
for mod, needles in WANT.items():
    try:
        check(mod, z.extract(mod), needles)
    except Exception as e:
        print("!! extract %s failed: %s" % (mod, e))
        allok = False

print("== 入口脚本（CArchive）==")
try:
    raw = ca.extract("kuaimai_scan")
    code = marshal.loads(raw)
    check("kuaimai_scan", code, ["add_job_checked", "dup_msg", "/api/print/jobs_add"])
except Exception as e:
    print("!! entry extract failed: %s" % e)
    allok = False

# 反向断言：旧行为标记不该再出现
print("== 反向断言 ==")
found_scan = set()
try:
    collect(marshal.loads(ca.extract("kuaimai_scan")), found_scan)
except Exception:
    pass
print("   入口脚本仍含旧直接调用 add_job( ？", any(s == "add_job" for s in found_scan))

print()
print("VERIFY:", "ALL FOUND" if allok else "SOME MISSING")
print("exe size:", os.path.getsize(EXE))
