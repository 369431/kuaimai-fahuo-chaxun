# -*- coding: utf-8 -*-
"""检查更新：拉 GitHub 上的 version.json，比版本号，能一键下载安装包。

清单地址（默认仓库根目录的 version.json，可改）：
  https://raw.githubusercontent.com/369431/kuaimai-fahuo-chaxun/main/version.json

发新版时要做的事（仓库是 Public，客户端免密钥就能拉）：
  1) 把新安装包传到 GitHub Release（文件名用 ASCII，例：kuaimai-scan-setup-v1.12.exe）
  2) 更新仓库根的 version.json：version / notes / setup_url / sha256
  3) 客户端点「检查更新」就能看到、能一键下载安装
"""
import hashlib
import io
import json
import os
import re
import sys
import urllib.error
import urllib.request

DEFAULT_MANIFEST = ("https://cdn.jsdelivr.net/gh/369431/kuaimai-fahuo-chaxun@main/version.json")
# 备用源：jsDelivr 不可达时再试 raw（国内 jsDelivr 通常能通，raw.githubusercontent 经常被阻）
FALLBACK_MANIFEST = ("https://raw.githubusercontent.com/369431/kuaimai-fahuo-chaxun/main/version.json")
RELEASES_PAGE = "https://github.com/369431/kuaimai-fahuo-chaxun/releases/latest"

# 走系统/环境代理：ProxyHandler({}) 是写死“不用代理”，客户机挂了梯子/系统代理反而更下不来
import ssl as _ssl


def _ssl_contexts():
    """依次试：certifi 证书包 → 系统证书库 → 不校验（兜底；安装包本身还有 sha256 校验）。"""
    ctxs = []
    try:
        import certifi
        ctxs.append(_ssl.create_default_context(cafile=certifi.where()))
    except Exception:
        pass
    try:
        _c = _ssl.create_default_context()
        _c.load_default_certs()
        ctxs.append(_c)
    except Exception:
        pass
    try:
        ctxs.append(_ssl._create_unverified_context())
    except Exception:
        pass
    return ctxs or [None]


_OPENERS = [urllib.request.build_opener(urllib.request.ProxyHandler(urllib.request.getproxies()),
                                        *([urllib.request.HTTPSHandler(context=c)] if c else []))
            for c in _ssl_contexts()]
_OPENER = _OPENERS[0]


def _open(req, timeout=10):
    """证书报错就换下一套上下文重试（客户机上常见“unable to get local issuer certificate”）。"""
    last = None
    for _op in _OPENERS:
        try:
            return _op.open(req, timeout=float(timeout or 10))
        except urllib.error.HTTPError:
            raise
        except Exception as e:
            low = str(e).lower()
            if ("certificate" in low) or ("ssl" in low):
                last = e
                continue
            raise
    raise last


def manifest_url():
    """清单地址：默认上面那个；kuaimai_client.json 里配了 update_url 就用它。"""
    try:
        import kuaimai_client as kmc
        u = str((kmc.load_config() or {}).get("update_url") or "").strip()
        if u:
            return u
    except Exception:
        pass
    return DEFAULT_MANIFEST


def manifest_urls(url=None):
    """要问的清单源（去重保序）：配置里的 update_url → jsDelivr → raw。"""
    cand = []
    if url:
        cand.append(str(url))
    else:
        try:
            import kuaimai_client as kmc
            u = str((kmc.load_config() or {}).get("update_url") or "").strip()
            if u:
                cand.append(u)
        except Exception:
            pass
        cand.append(DEFAULT_MANIFEST)
        cand.append(FALLBACK_MANIFEST)
    seen, out = set(), []
    for u in cand:
        if u and u not in seen:
            seen.add(u)
            out.append(u)
    return out


def parse_ver(v):
    """'v1.11' / '1.11.2' / 'v1.12-beta' → (1, 11) / (1, 11, 2) / (1, 12)。"""
    s = str(v or "").strip().lower().lstrip("v")
    nums = re.findall(r"\d+", s)
    if not nums:
        return (0,)
    return tuple(int(x) for x in nums[:4])


def newer(latest, current):
    a, b = parse_ver(latest), parse_ver(current)
    n = max(len(a), len(b))
    a = a + (0,) * (n - len(a))
    b = b + (0,) * (n - len(b))
    return a > b


def _fetch(url, timeout=10, binary=False):
    req = urllib.request.Request(url, headers={"User-Agent": "kuaimai-update/1"})
    with _open(req, timeout=float(timeout or 10)) as r:
        data = r.read()
    return data if binary else data.decode("utf-8", "replace")


def check(current, url=None, timeout=10):
    """查有没有新版 → dict(ok, has_update, latest, notes, page_url, setup_url, sha256, mandatory, error)。

    ⚠ 会**同时问多个清单源、取版本号最高**的那个：
    jsDelivr 的 `@main` 是 CDN，缓存 `s-maxage=43200`（**12 小时**），而且 purge 常常报告完成却
    不真的失效 —— 刚发的版本它会一直返回旧的。以前只用它一个源，于是新版本发布后点「检查更新」
    会**误报「已是最新版」**（v1.66 修）。raw.githubusercontent 是 GitHub 自己的源，基本实时。
    """
    out = {"ok": False, "has_update": False, "latest": "", "notes": "",
           "page_url": RELEASES_PAGE, "setup_url": "", "sha256": "",
           "mandatory": False, "error": "", "url": "", "sources": []}
    errs, best_u, best_m = [], "", None
    for u in manifest_urls(url):
        try:
            man = json.loads(_fetch(u, timeout))
            if not isinstance(man, dict):
                raise ValueError("清单格式不对")
            v = str(man.get("version") or "").strip()
            if not v:
                raise ValueError("清单里没写 version")
        except urllib.error.HTTPError as e:
            errs.append("%s（HTTP %s）" % (u[-38:], e.code))
            continue
        except Exception as e:
            errs.append("%s（%s）" % (u[-38:], str(e)[:40]))
            continue
        out["sources"].append({"url": u, "version": v})
        if best_m is None or parse_ver(v) > parse_ver(str(best_m.get("version") or "")):
            best_u, best_m = u, man
    if best_m is None:
        out["error"] = "检查更新失败：清单源都拉不到（%s）" % ("；".join(errs)[:170] or "无可用源")
        return out
    out["ok"] = True
    out["url"] = best_u
    latest = str(best_m.get("version") or "").strip()
    out["latest"] = latest
    out["notes"] = str(best_m.get("notes") or "")
    out["page_url"] = str(best_m.get("page_url") or RELEASES_PAGE)
    out["setup_url"] = str(best_m.get("setup_url") or "")
    out["sha256"] = str(best_m.get("sha256") or "").strip().lower()
    out["mandatory"] = bool(best_m.get("mandatory"))
    out["has_update"] = newer(latest, current)
    return out


def download_setup(info, dest_dir=None, progress=None):
    """下载安装包 → 返回 (本地路径, 错误)。progress(已下载, 总字节, 百分比)。"""
    url = str((info or {}).get("setup_url") or "")
    if not url:
        return "", "清单里没给 setup_url（只能去发布页手动下）"
    dest_dir = dest_dir or os.path.join(os.environ.get("TEMP") or ".", "kuaimai_update")
    try:
        os.makedirs(dest_dir, exist_ok=True)
    except Exception:
        pass
    name = os.path.basename(url.split("?")[0]) or "kuaimai-setup.exe"
    dest = os.path.join(dest_dir, name)
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "kuaimai-update/1"})
        with _open(req, timeout=60) as r:
            total = int(r.headers.get("Content-Length") or 0)
            got = 0
            with open(dest, "wb") as f:
                while True:
                    chunk = r.read(262144)
                    if not chunk:
                        break
                    f.write(chunk)
                    got += len(chunk)
                    if progress:
                        try:
                            progress(got, total, int(got * 100 / total) if total else 0)
                        except Exception:
                            pass
    except Exception as e:
        return "", "下载失败：%s" % str(e)[:150]
    want = str((info or {}).get("sha256") or "").strip().lower()
    if want:
        try:
            h = hashlib.sha256()
            with open(dest, "rb") as f:
                for blk in iter(lambda: f.read(1 << 20), b""):
                    h.update(blk)
            if h.hexdigest().lower() != want:
                return "", "下载下来的文件校验不对（可能没下完），已丢弃"
        except Exception as e:
            return "", "校验失败：%s" % str(e)[:100]
    return dest, ""


def run_setup(path, silent=True):
    """启动安装包。**默认静默**：不再弹 Inno 向导，只显示一个进度条，装完自动重启程序。

    silent=True 带这三个参数：
      · /SILENT            不提问（只显示进度条）
      · /CLOSEAPPLICATIONS 让安装器自己关掉正在运行的程序（主程序 + 9443 中转都占着要被替换的文件）
      · /NORESTART         不要重启电脑
    配合安装脚本 `.iss` 里「启动全部」那条 [Run] **去掉了 skipifsilent**，所以静默装完也会自动拉起程序。

    silent=False → 老行为（弹安装向导）。万一静默装失败，可以用它兜底。
    """
    try:
        if not os.path.exists(path):
            return False, "文件不在了：%s" % path
        low = str(path).lower()
        if not low.endswith((".exe", ".msi")):
            os.startfile(os.path.dirname(path))
            return True, "已打开所在文件夹（不是安装包，没自动运行）"
        if silent and low.endswith(".exe"):
            import subprocess
            subprocess.Popen([path, "/SILENT", "/CLOSEAPPLICATIONS", "/NORESTART"],
                             close_fds=True)
            return True, ""
        os.startfile(path)
        return True, ""
    except Exception as e:
        return False, "打不开安装包：%s" % str(e)[:120]
