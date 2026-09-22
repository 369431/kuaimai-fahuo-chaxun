# -*- coding: utf-8 -*-
"""One-off: bump APP_VER v1.23 -> v1.24 in desktop/kuaimai_client.py (exact, verified)."""
import io, os, sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
p = os.path.join(ROOT, "desktop", "kuaimai_client.py")
OLD = 'APP_VER = "v1.23"'
NEW = 'APP_VER = "v1.24"'

s = io.open(p, encoding="utf-8").read()
n = s.count(OLD)
if n != 1:
    print("ABORT: expected exactly 1 occurrence of %r, found %d" % (OLD, n))
    sys.exit(1)
io.open(p, "w", encoding="utf-8", newline="").write(s.replace(OLD, NEW))
print("replaced %d occurrence" % n)
for i, line in enumerate(io.open(p, encoding="utf-8"), 1):
    if "APP_VER" in line:
        print("%d: %s" % (i, line.rstrip()))
