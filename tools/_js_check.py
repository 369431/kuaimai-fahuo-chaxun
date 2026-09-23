# -*- coding: utf-8 -*-
"""JS 语法闸门：把 kuaimai_webui.py 里各 <script> 段抠出来跑 node --check。"""
import io, json, os, re, subprocess, sys, tempfile

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询\desktop"
OUT = r"C:\Users\Kerwin\Desktop\kuaimai发货查询\tools\_boot_out.txt"
sys.path.insert(0, REPO)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import kuaimai_webui as w   # noqa: E402

buf = []
pages = {}
for name in ("WEB_INDEX_HTML", "STOCK_HTML", "PICK_HTML", "ORDER_HTML", "STOCKTAKE_HTML",
             "PERMS_HTML", "PRINTS_HTML"):
    v = getattr(w, name, None)
    if isinstance(v, str) and v.strip():
        pages[name] = v

tmp = tempfile.mkdtemp(prefix="km_js_")
total_bad = 0
for pname, html in pages.items():
    segs = re.findall(r"<script>(.*?)</script>", html, re.S)
    buf.append("== %s: %d script segs, %d chars" % (pname, len(segs), len(html)))
    for i, s in enumerate(segs):
        p = os.path.join(tmp, "%s_%d.js" % (pname, i))
        io.open(p, "w", encoding="utf-8", newline="\n").write(s)
        r = subprocess.run(["node", "--check", p], capture_output=True, text=True,
                           encoding="utf-8", errors="replace")
        ok = (r.returncode == 0)
        if not ok:
            total_bad += 1
        buf.append("   seg %d: %s%s" % (i, "OK" if ok else "SYNTAX ERROR",
                                        "" if ok else ("\n" + (r.stderr or "")[:600])))

buf.append("=" * 30)
buf.append("bad segments: %d" % total_bad)

# 断言新文案真的进了页面
html = pages.get("STOCK_HTML", "")
buf.append("STOCK_HTML 含 dup 提示: %s" % ("本次未新建打单任务" in html))
buf.append("STOCK_HTML 含 dup_msg 用法: %s" % ("j.dup_msg" in html))
idx = pages.get("WEB_INDEX_HTML", "")
buf.append("WEB_INDEX_HTML 含 dup 提示: %s" % ("本次未新建打单任务" in idx))
buf.append("WEB_INDEX_HTML 含 j.dup: %s" % ("j.dup" in idx))

io.open(OUT, "w", encoding="utf-8", newline="\n").write("\n".join(buf))
print("wrote; bad=%d; tmp=%s" % (total_bad, tmp))
