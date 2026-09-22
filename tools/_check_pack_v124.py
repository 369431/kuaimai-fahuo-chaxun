# -*- coding: utf-8 -*-
"""Assert the built exe bundles the runtime-only modules. Pure read; no app launch."""
import sys
EXE = sys.argv[1] if len(sys.argv) > 1 else r"C:\Users\Kerwin\Desktop\发布\_build_v124\dist\快麦扫码查询.exe"
CORE = ["kuaimai_print", "kuaimai_print_ui", "kuaimai_print_jobs", "auto_print_watcher"]
EXTRA = ["kuaimai_webui", "kuaimai_client", "kuaimai_scan", "kuaimai_db", "kuaimai_login_window"]

from PyInstaller.archive.readers import CArchiveReader
ca = CArchiveReader(EXE)
top = set(str(t) for t in ca.toc)
print("CArchive TOC entries:", len(top))
print("sample:", sorted(top)[:6])

# modules live inside the embedded PYZ archive
pyz_entry = next((n for n in top if n.lower().endswith(".pyz")), None)
print("embedded PYZ entry:", pyz_entry)
za = ca.open_embedded_archive(pyz_entry)
znames = set(str(k) for k in za.toc.keys())
print("PYZ modules:", len(znames))
names = top | znames

def find(mod):
    hits = [n for n in names if n == mod or n == mod + ".pyc" or n.endswith("/" + mod + ".pyc")
            or n.split(".")[0] == mod or n.startswith(mod + ".")]
    return sorted(hits)[:4]

print("\n-- CORE (must all be present) --")
missing = []
for m in CORE:
    h = find(m)
    print("  %-22s %s" % (m, ("FOUND %s" % h) if h else "MISSING"))
    if not h:
        missing.append(m)

print("\n-- related modules (informational) --")
for m in EXTRA:
    h = find(m)
    print("  %-22s %s" % (m, h if h else "missing"))

print("\nRESULT: core missing =", missing if missing else "NONE - all 4 bundled")
sys.exit(1 if missing else 0)
