# -*- coding: utf-8 -*-
"""Adopt the remote version.json commit locally so local main == origin/main.

git-over-HTTPS to github.com is unreachable, so we cannot `git fetch`. But the
remote commit's tree is byte-identical to the local commit's tree (verified), so
recreating that commit object from GitHub's metadata yields the exact same SHA and
local main can fast-forward. Metadata/ref-only: no file content changes.
"""
import datetime, json, os, subprocess, sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
SHA = "fea97ef85f8a08ba49103cf1fc590281d97d059c"

r = subprocess.run(["gh", "api", "repos/369431/kuaimai-fahuo-chaxun/git/commits/" + SHA],
                   capture_output=True)
if r.returncode != 0:
    print("gh api failed:", r.stderr.decode("utf-8", "replace")); sys.exit(2)
d = json.loads(r.stdout.decode("utf-8"))

def ident(x):
    dt = datetime.datetime.strptime(x["date"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc)
    return "%s <%s> %d +0000" % (x["name"], x["email"], int(dt.timestamp()))

lines = ["tree " + d["tree"]["sha"]]
lines += ["parent " + p["sha"] for p in d.get("parents", [])]
lines += ["author " + ident(d["author"]), "committer " + ident(d["committer"]), ""]
payload = ("\n".join(lines) + "\n" + d["message"])

for attempt, body in enumerate([payload, payload.rstrip("\n"), payload + "\n"]):
    h = subprocess.run(["git", "hash-object", "-t", "commit", "-w", "--stdin"],
                       input=body.encode("utf-8"), capture_output=True, cwd=REPO)
    got = h.stdout.decode().strip()
    print("attempt %d -> %s (want %s) match=%s" % (attempt, got, SHA, got == SHA))
    if got == SHA:
        for ref in ("refs/heads/main", "refs/remotes/origin/main"):
            u = subprocess.run(["git", "update-ref", ref, SHA], capture_output=True, cwd=REPO)
            print("  update-ref %s rc=%d %s" % (ref, u.returncode, u.stderr.decode("utf-8", "replace").strip()))
        sys.exit(0)
print("could not reproduce the exact commit object; leaving refs untouched")
sys.exit(3)
