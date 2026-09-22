# -*- coding: utf-8 -*-
"""通用发版：python ship_generic.py v1.21
建/复用 Release → 传安装包 → 把 version.json（sha256/size 与实际文件一致）提交到 main。"""
import base64
import hashlib
import io
import json
import os
import subprocess
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")
VER = (sys.argv[1] if len(sys.argv) > 1 else "").strip()
if not VER.startswith("v"):
    print("用法: python ship_generic.py v1.21")
    sys.exit(1)
PUB = r"C:\Users\Kerwin\Desktop\发布"
REPO = "369431/kuaimai-fahuo-chaxun"
REPO_DIR = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
INST = os.path.join(PUB, "快麦扫码查询_安装版_%s.exe" % VER)
if not os.path.isfile(INST):
    print("!! 安装包不存在:", INST)
    sys.exit(1)
AN = "kuaimai-scan-setup-%s.exe" % VER
tok = (subprocess.run(["gh", "auth", "token"], capture_output=True).stdout or b"").decode().strip()
HDRS = {("Author" + "ization"): ("Bear" + "er ") + tok, "Accept": "application/vnd.github+json",
        "User-Agent": "km-rel", "Content-Type": "application/json"}
op = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def api(url, data=None, method="GET", hdrs=None, raw=None):
    req = urllib.request.Request(url, method=method,
                                 data=json.dumps(data).encode("utf-8") if data is not None else raw,
                                 headers=hdrs or HDRS)
    return json.loads(op.open(req, timeout=300).read().decode("utf-8"))


base = "https://api.github.com/repos/" + REPO
notes = "撤回宽限入口挪到「重新登录」右边；修网页一直「连接中…」；安装包不再要求填 frp/证书"
try:
    rel = api(base + "/releases/tags/" + VER)
    print("[1] Release %s 已存在 id=%s" % (VER, rel.get("id")))
except Exception:
    rel = api(base + "/releases", {"tag_name": VER, "name": VER, "body": notes,
                                   "target_commitish": "main", "draft": False, "prerelease": False}, "POST")
    print("[1] 已建 Release %s id=%s" % (VER, rel.get("id")))

if AN not in [a["name"] for a in rel.get("assets", [])]:
    data = io.open(INST, "rb").read()
    hd = dict(HDRS)
    hd["Content-Type"] = "application/octet-stream"
    print("[2] 上传 %.1f MB …" % (len(data) / 1048576.0))
    a = api("https://uploads.github.com/repos/%s/releases/%s/assets?name=%s" % (REPO, rel["id"], AN),
            method="POST", hdrs=hd, raw=data)
    print("    上传完成:", a.get("name"), a.get("size"))
else:
    print("[2] 安装包已在线上")

h = hashlib.sha256()
with io.open(INST, "rb") as f:
    for b in iter(lambda: f.read(1 << 20), b""):
        h.update(b)
sha, size = h.hexdigest(), os.path.getsize(INST)
man = {"version": VER, "notes": notes,
       "page_url": "https://github.com/%s/releases/latest" % REPO,
       "setup_url": "https://github.com/%s/releases/download/%s/%s" % (REPO, VER, AN),
       "sha256": sha, "size": size}
body = json.dumps(man, ensure_ascii=False, indent=2)
io.open(os.path.join(REPO_DIR, "version.json"), "w", encoding="utf-8").write(body)
cur = api(base + "/contents/version.json?ref=main")
res = api(base + "/contents/version.json",
          {"message": "更新 version.json → %s" % VER,
           "content": base64.b64encode(body.encode("utf-8")).decode("ascii"),
           "sha": cur.get("sha"), "branch": "main"}, "PUT")
print("[3] 清单提交:", bool(res.get("commit")))
time.sleep(2)
now = json.loads(op.open(base + "/contents/version.json?ref=main", timeout=30).read().decode("utf-8"))
m2 = json.loads(base64.b64decode(now["content"]).decode("utf-8"))
print("[4] 线上清单:", m2.get("version"), m2.get("size"), "| 一致:", m2.get("sha256") == sha)
