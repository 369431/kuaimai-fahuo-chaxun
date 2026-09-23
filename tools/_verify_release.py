# -*- coding: utf-8 -*-
"""发版后核验：jsDelivr / raw / Release 资产 / 端到端「检查更新」+ 真下载校验。"""
import hashlib
import io
import json
import os
import sys
import urllib.request

DESKTOP = r"C:\Users\Kerwin\Desktop\kuaimai发货查询\desktop"
sys.path.insert(0, DESKTOP)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

GH = "369431/kuaimai-fahuo-chaxun"
OP = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def get(url, timeout=30):
    return OP.open(url, timeout=timeout).read()


print("== 1. jsDelivr（客户端默认清单源）==")
try:
    d = json.loads(get("https://cdn.jsdelivr.net/gh/%s@main/version.json" % GH).decode("utf-8"))
    print("   version=%s size=%s" % (d.get("version"), d.get("size")))
    print("   sha256=%s" % d.get("sha256"))
    jd = d
except Exception as e:
    print("   FAIL:", e)
    jd = {}

print("== 2. raw.githubusercontent（备用源）==")
try:
    d2 = json.loads(get("https://raw.githubusercontent.com/%s/main/version.json" % GH).decode("utf-8"))
    print("   version=%s size=%s" % (d2.get("version"), d2.get("size")))
except Exception as e:
    print("   (raw 不可达，不影响：", str(e)[:80], ")")
    d2 = {}

print("== 3. Release 资产状态（gh api）==")
import subprocess
p = subprocess.run(["gh", "api", "repos/%s/releases/tags/v1.30" % GH],
                   capture_output=True, text=True, encoding="utf-8", errors="replace")
if p.returncode == 0:
    rel = json.loads(p.stdout)
    print("   draft=%s tag=%s" % (rel.get("draft"), rel.get("tag_name")))
    for a in rel.get("assets") or []:
        print("   asset=%s state=%s size=%s" % (a.get("name"), a.get("state"), a.get("size")))
else:
    print("   gh api 失败:", (p.stderr or "")[:200])

print("== 4. version.json 本地/远端一致 ==")
loc = json.loads(io.open(os.path.join(os.path.dirname(DESKTOP), "version.json"),
                         encoding="utf-8").read())
print("   本地 version=%s size=%s" % (loc.get("version"), loc.get("size")))
same = (loc.get("version") == jd.get("version") == "v1.30" and loc.get("sha256") == jd.get("sha256"))
print("   本地/jsDelivr 一致:", same)

print("== 5. 端到端「检查更新」==")
try:
    import kuaimai_update as ku
    r1 = ku.check("v1.29")
    print("   check('v1.29') ->", {k: r1.get(k) for k in ("has_update", "latest")})
    r2 = ku.check("v1.30")
    print("   check('v1.30') ->", {k: r2.get(k) for k in ("has_update", "latest")})
except Exception as e:
    print("   FAIL:", str(e)[:200])

print("== 6. 真下载（别的电脑走的链路）+ sha256 校验 ==")
try:
    import kuaimai_update as ku
    info = ku.check("v1.29")          # 用客户端自己拉到的清单（带 setup_url/sha256）
    print("   setup_url:", info.get("setup_url"))
    pth, err = ku.download_setup(info)
    if err:
        print("   FAIL:", err)
    else:
        n = os.path.getsize(pth)
        h = hashlib.sha256(io.open(pth, "rb").read()).hexdigest()
        print("   downloaded=%d bytes sha256=%s" % (n, h))
        print("   清单 sha256 一致:", h == (info.get("sha256") or "").lower(),
              " size 一致:", n == loc.get("size"))
except Exception as e:
    print("   FAIL:", str(e)[:200])
