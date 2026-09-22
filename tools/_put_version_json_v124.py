# -*- coding: utf-8 -*-
"""Fallback for the failed `git push`: update version.json on GitHub via the Contents API.

Used because git-over-HTTPS to github.com is unreachable from this host, while
api.github.com (gh) works. Updates only version.json, exactly like release.py does.
"""
import base64, io, json, os, subprocess, sys

GH_REPO = "369431/kuaimai-fahuo-chaxun"
P = "repos/%s/contents/version.json" % GH_REPO
ROOT = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"

def gh(*args, inp=None):
    r = subprocess.run(["gh"] + list(args), capture_output=True, input=inp)
    return r.returncode, r.stdout.decode("utf-8", "replace"), r.stderr.decode("utf-8", "replace")

local = io.open(os.path.join(ROOT, "version.json"), encoding="utf-8").read()
local_ver = json.loads(local).get("version")

rc, out, err = gh("api", P, "--jq", ".sha")
if rc != 0:
    print("cannot read remote sha:", err); sys.exit(2)
remote_sha = out.strip()

rc, out, err = gh("api", P, "--jq", ".content")
if rc != 0:
    print("cannot read remote content:", err); sys.exit(2)
remote_now = base64.b64decode(out.strip()).decode("utf-8")
print("remote version BEFORE:", json.loads(remote_now).get("version"), "| local:", local_ver)

body = {
    "message": "发布 v1.24（更新 version.json）",
    "content": base64.b64encode(local.encode("utf-8")).decode("ascii"),
    "sha": remote_sha,
    "branch": "main",
}
bf = os.path.join(os.environ.get("TEMP", "."), "km_vj_body.json")
io.open(bf, "w", encoding="utf-8").write(json.dumps(body, ensure_ascii=False))

rc, out, err = gh("api", "--method", "PUT", P, "--input", bf)
print("PUT rc:", rc)
if rc != 0:
    print("stderr:", err[:800]); sys.exit(3)
res = json.loads(out)
print("commit:", res.get("commit", {}).get("sha"))
print("new remote content sha:", res.get("content", {}).get("sha"))
