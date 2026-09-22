# -*- coding: utf-8 -*-
"""Prove APP_VER inside the frozen PYZ is v1.24 (static; no launch)."""
import marshal, sys, types
EXE = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\Kerwin\Desktop\发布\_build_v124\dist\快麦扫码查询.exe"
from PyInstaller.archive.readers import CArchiveReader
ca = CArchiveReader(EXE)
za = ca.open_embedded_archive("PYZ.pyz")
raw = za.extract("kuaimai_client")
if isinstance(raw, types.CodeType):
    code = raw
elif isinstance(raw, tuple):
    code = raw[1] if isinstance(raw[1], types.CodeType) else marshal.loads(raw[1])
else:
    code = marshal.loads(raw)

found = []
def walk(co, path="<mod>"):
    if isinstance(co, types.CodeType):
        for c in co.co_consts:
            if isinstance(c, str) and c.startswith("v1."):
                found.append((path, c))
            elif isinstance(c, types.CodeType):
                walk(c, path + "." + co.co_name)
walk(code)
print("version-like string constants in bundled kuaimai_client:", found)
has124 = any(v == "v1.24" for _, v in found)
has123 = any(v == "v1.23" for _, v in found)
print("contains v1.24:", has124, "| contains v1.23:", has123)
sys.exit(0 if (has124 and not has123) else 1)
