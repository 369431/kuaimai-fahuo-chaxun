# -*- coding: utf-8 -*-
"""Brute-force the exact commit object for fea97ef (tz/message variants) and adopt it."""
import datetime, itertools, json, subprocess, sys

REPO = r"C:\Users\Kerwin\Desktop\kuaimai发货查询"
SHA = "fea97ef85f8a08ba49103cf1fc590281d97d059c"

d = json.loads(subprocess.run(["gh", "api", "repos/369431/kuaimai-fahuo-chaxun/git/commits/" + SHA],
                              capture_output=True).stdout.decode("utf-8"))
print("tree   :", d["tree"]["sha"])
print("parents:", [p["sha"] for p in d.get("parents", [])])
print("author :", d["author"])
print("committer:", d["committer"])
print("message:", repr(d["message"]))

def ts(x):
    return int(datetime.datetime.strptime(x["date"], "%Y-%m-%dT%H:%M:%SZ")
               .replace(tzinfo=datetime.timezone.utc).timestamp())

base = ["tree " + d["tree"]["sha"]] + ["parent " + p["sha"] for p in d.get("parents", [])]
msgs = [d["message"], d["message"].rstrip("\n"), d["message"] + "\n"]
tzs = ["+0000", "+0800", "-0000"]

found = None
for atz, ctz, m in itertools.product(tzs, tzs, msgs):
    a = "%s <%s> %d %s" % (d["author"]["name"], d["author"]["email"], ts(d["author"]), atz)
    c = "%s <%s> %d %s" % (d["committer"]["name"], d["committer"]["email"], ts(d["committer"]), ctz)
    body = ("\n".join(base + ["author " + a, "committer " + c, ""]) + "\n" + m).encode("utf-8")
    h = subprocess.run(["git", "hash-object", "-t", "commit", "-w", "--stdin"], input=body,
                       capture_output=True, cwd=REPO).stdout.decode().strip()
    if h == SHA:
        found = (atz, ctz, repr(m)); print("MATCH -> atz=%s ctz=%s msg=%s" % (atz, ctz, repr(m)))
        break

if not found:
    print("no variant matched; refs left untouched"); sys.exit(3)
for ref in ("refs/heads/main", "refs/remotes/origin/main"):
    u = subprocess.run(["git", "update-ref", ref, SHA], capture_output=True, cwd=REPO)
    print("update-ref %s rc=%d %s" % (ref, u.returncode, u.stderr.decode("utf-8", "replace").strip()))
