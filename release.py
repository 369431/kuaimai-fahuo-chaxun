# -*- coding: utf-8 -*-
"""一键发版：把安装包传到 GitHub Release，并更新 version.json（客户端「检查更新」就看它）。

用法（在仓库目录里跑，需要本机已登录 gh）：

    python release.py --version v1.12 --installer "C:\\Users\\Kerwin\\Desktop\\发布\\快麦扫码查询_安装版_v1.12.exe" --notes "修了 XXX；新增 YYY"

它会：
  1) 把安装包复制成 ASCII 名：kuaimai-scan-setup-v1.12.exe（GitHub 资源名别用中文，URL 容易出问题）
  2) 算 sha256（客户端下载完会校验）
  3) gh release create v1.12 <安装包>（已存在就 gh release upload --clobber）
  4) 写 version.json（version / notes / setup_url / sha256 / published_at）
  5) git add version.json && git commit && git push

之后客户端点「检查更新」就能看到新版、一键下载安装。
"""
import argparse
import hashlib
import io
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
REPO = os.path.dirname(os.path.abspath(__file__))
GH_REPO = "369431/kuaimai-fahuo-chaxun"
ASSET_TPL = "kuaimai-scan-setup-%s.exe"


def sha256(path):
    h = hashlib.sha256()
    with io.open(path, "rb") as f:
        for blk in iter(lambda: f.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def run(cmd, cwd=None):
    p = subprocess.run(cmd, cwd=cwd or REPO, capture_output=True)
    out = (p.stdout or b"").decode("utf-8", "replace") + (p.stderr or b"").decode("gbk", "replace")
    return p.returncode, out.strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--version", required=True, help="例 v1.12")
    ap.add_argument("--installer", required=True, help="安装包路径（.exe）")
    ap.add_argument("--notes", default="", help="更新说明（客户端弹窗里显示）")
    ap.add_argument("--no-push", action="store_true", help="只写 version.json，不 git 提交推送")
    a = ap.parse_args()

    ver = a.version.strip()
    if not re.match(r"^v?\d", ver):
        print("版本号看着不对：%s" % ver)
        return 2
    ver = ver if ver.startswith("v") else ("v" + ver)
    inst = os.path.abspath(a.installer)
    if not os.path.exists(inst):
        print("找不到安装包：%s" % inst)
        return 2

    # 1) 复制成 ASCII 资源名
    asset_name = ASSET_TPL % ver
    asset = os.path.join(os.path.dirname(inst), asset_name)
    if os.path.abspath(asset) != inst:
        shutil.copy2(inst, asset)
    digest = sha256(asset)
    size = os.path.getsize(asset)
    print("资源：%s（%.1f MB）\nsha256：%s" % (asset, size / 1048576.0, digest))

    # 2) 发布 Release（已存在就覆盖那个资源）
    rc, out = run(["gh", "release", "view", ver, "--repo", GH_REPO])
    if rc == 0:
        rc2, out2 = run(["gh", "release", "upload", ver, asset, "--repo", GH_REPO, "--clobber"])
        print("已存在 %s，上传/覆盖资源：%s" % (ver, "ok" if rc2 == 0 else out2))
    else:
        notes = a.notes or ("快麦扫码查询 %s" % ver)
        nf = os.path.join(os.environ.get("TEMP", "."), "km_release_notes.md")
        io.open(nf, "w", encoding="utf-8").write("%s\n\n%s\n" % (ver, notes))
        rc2, out2 = run(["gh", "release", "create", ver, asset, "--repo", GH_REPO,
                         "--title", ver, "--notes-file", nf])
        print("建 Release：%s" % ("ok" if rc2 == 0 else out2))
    if rc2 != 0:
        print("！！Release 没发成，先别更新 version.json")
        return 3

    # 3) 写 version.json
    vj = os.path.join(REPO, "version.json")
    data = {}
    try:
        data = json.loads(io.open(vj, encoding="utf-8").read()) or {}
    except Exception:
        data = {}
    data.update({
        "version": ver,
        "notes": a.notes or data.get("notes") or "",
        "page_url": "https://github.com/%s/releases/latest" % GH_REPO,
        "setup_url": "https://github.com/%s/releases/download/%s/%s" % (GH_REPO, ver, asset_name),
        "sha256": digest,
        "mandatory": bool(data.get("mandatory", False)),
        "published_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    })
    io.open(vj, "w", encoding="utf-8").write(json.dumps(data, ensure_ascii=False, indent=2) + "\n")
    print("version.json 已更新：%s" % data["setup_url"])

    # 4) 提交推送（只动 version.json）
    if not a.no_push:
        run(["git", "add", "version.json"])
        rc3, out3 = run(["git", "commit", "-m", "发布 %s（更新 version.json）" % ver])
        rc4, out4 = run(["git", "push", "origin", "main"])
        print("提交推送：%s" % ("ok" if rc4 == 0 else (out4 or out3)))
    print("\n完成。客户端点「检查更新」就能看到 %s。" % ver)
    return 0


if __name__ == "__main__":
    sys.exit(main())
