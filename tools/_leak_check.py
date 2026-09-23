# -*- coding: utf-8 -*-
"""提交前凭据泄漏自检（三层）。

L1 工作区改动文件：真实凭据值比对（内存里读，只打印命中数/文件名，不打印值）
L2 全库历史对象：扫描所有 blob 里是否含真实凭据值
L3 高熵疑似密钥扫描：改动文件里形如 token/key/secret 的超长字面量（只报字段名与长度）

真实凭据为空串时（本项目既是如此），L1/L2 的「值比对」天然无命中；
所以补 L3 做结构性扫描，避免自检变成空转。
"""
import io
import json
import os
import re
import subprocess
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
os.chdir(REPO)


def git(*a):
    p = subprocess.run(["git"] + list(a), capture_output=True)
    return p.returncode, p.stdout.decode("utf-8", "replace")


# ---------- 真实凭据值（内存比对） ----------
needles = []
p = os.path.join(REPO, "desktop/kuaimai_scan.py")
txt = io.open(p, encoding="utf-8", errors="replace").read() if os.path.isfile(p) else ""
for k in ("KM_APP_KEY", "KM_APP_SECRET", "KM_REFRESH_TOKEN", "INIT_SESSION_ID"):
    m = re.search(k + r'\s*=\s*"([^"]*)"', txt)
    if m and len(m.group(1)) >= 8:
        needles.append((k, m.group(1)))
print("配置区四项非空值个数（>=8 字符）:", len(needles))
print("  说明：本项目这几项本就留空 → 0 属正常")

# ---------- 变更文件清单（不 strip 状态位） ----------
rc, out = git("status", "--porcelain")
changed = []
for line in out.splitlines():
    if not line.strip():
        continue
    path = line[2:].strip().strip('"')
    if len(path) == 3 and path[0].isalpha():     # 形如 "M ..." 的边界情况
        path = line[3:].strip().strip('"')
    changed.append(path)
print("变更文件:", len(changed))
for c in changed:
    print("   ", c)


def read_any(path):
    fp = os.path.join(REPO, path)
    if not os.path.isfile(fp):
        return ""
    for enc in ("utf-8", "gbk"):
        try:
            return io.open(fp, encoding=enc).read()
        except Exception:
            continue
    return io.open(fp, "rb").read().decode("utf-8", "replace")


# ---------- L1 ----------
l1 = 0
for c in changed:
    body = read_any(c)
    for name, val in needles:
        if val and val in body:
            l1 += 1
            print("  !! L1 HIT:", c, name)
print("L1 工作区值比对:", "CLEAN" if l1 == 0 else "LEAK(%d)" % l1)

# ---------- L2 ----------
rc, out = git("rev-list", "--all")
revs = [x for x in out.split() if x]
rc, out2 = git("rev-list", "--objects", "--all")
objs = [l.split(" ", 1)[0] for l in out2.splitlines() if l.strip()]
print("历史 rev:", len(revs), " 历史对象:", len(objs))
l2 = 0
if needles:
    for o in objs:
        rc, blob = git("cat-file", "-p", o)
        if rc != 0:
            continue
        for name, val in needles:
            if val and val in blob:
                l2 += 1
                print("  !! L2 HIT object", o[:10], name)
print("L2 历史值比对:", "CLEAN" if l2 == 0 else "LEAK(%d)" % l2)

# ---------- L3 结构性扫描 ----------
PAT = re.compile(r'(?i)\b(app_?key|app_?secret|secret|token|passwd|password|api_?key|access_?key)'
                 r'\s*[:=]\s*["\']([^"\']{12,})["\']')
SUSPECT_WORDS = ("your", "xxx", "placeholder", "example", "test", "demo", "none", "null")
l3 = 0
for c in changed:
    body = read_any(c)
    for m in PAT.finditer(body):
        field, val = m.group(1), m.group(2)
        low = val.lower()
        likely_placeholder = (not re.search(r"[A-Za-z]", val)) or any(w in low for w in SUSPECT_WORDS)
        if not likely_placeholder:
            l3 += 1
            print("  ?? L3 疑似密钥: %s  字段=%s 长度=%d" % (c, field, len(val)))
print("L3 结构性扫描:", "CLEAN" if l3 == 0 else "REVIEW(%d)" % l3)

print()
print("SUMMARY L1=%d L2=%d L3=%d" % (l1, l2, l3))
