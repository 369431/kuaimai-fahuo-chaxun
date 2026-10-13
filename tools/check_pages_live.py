# -*- coding: utf-8 -*-
"""★ 网页页面端到端自检（真浏览器，走 CDP）。

为什么要有它：
  纯 JS 语法检查能拦住「脚本不执行」，但拦不住「脚本执行了但接口拿不到数据」。
  这个脚本用 ERP 自动化浏览器（CDP 9222）真的打开页面，读关键元素 + 抓 JS 异常，
  是"页面到底能不能用"的最终判据。

用法：
    python tools\\check_pages_live.py                 # 检查 现货可发 页
    python tools\\check_pages_live.py /stock /wave    # 检查指定页面

注意：需要快麦程序在跑（127.0.0.1:8790）且自动化浏览器在跑（9222）。
"""
import io
import json
import sys
import time
import urllib.request

sys.stdout.reconfigure(encoding="utf-8")

USERS = r"C:\Users\Kerwin\AppData\Local\KuaimaiScan\kuaimai_users.json"
CDP = "http://127.0.0.1:9222"
BASE = "http://127.0.0.1:8790"

# 每个页面的自检判据：
#   mode="auto" ：打开页面就会自动加载 → 必须出现内容，且不能停在"载入中"
#   mode="ready"：需要用户输入/选择才会出结果 → 不要求有内容，
#                只要「JS 没报错」+「关键控件/容器存在」就算正常
# 判据要按页面实际行为配，别拿"自动加载"的标准去要求"要输入才出结果"的页面。
PAGES = {
    "/stock": dict(elem="sum", mode="auto", loading=("正在载入", "载入中"),
                   required="list"),
    "/pick": dict(elem="pinfo", mode="ready", loading=("正在载入", "载入中"),
                  required="plist"),
    "/wave": dict(elem="hint", mode="ready", loading=("正在载入",),
                  required="code"),
    "/order": dict(elem="out", mode="ready", loading=("正在载入",),
                   required="no"),
    "/wave-records": dict(elem="hdrTitle", mode="ready", loading=("正在载入",),
                          required="upd"),
}


def evaluate(ws, send, expr):
    res = send("Runtime.evaluate", {"expression": expr, "returnByValue": True})
    return (((res or {}).get("result") or {}).get("result") or {}).get("value")


def token():
    try:
        d = json.loads(io.open(USERS, encoding="utf-8").read())
        return str((d["users"]["admin"].get("tokens") or {}).get("desktop") or "")
    except Exception:
        return ""


def main():
    paths = [a for a in sys.argv[1:] if a.startswith("/")] or ["/stock"]
    tok = token()
    if not tok:
        print("[L] ★ 取不到登录 token，跳过")
        return 1
    try:
        import websocket
    except Exception as e:
        print("[L] ★ 没有 websocket 库，跳过端到端检查：%s" % str(e)[:80])
        return 0

    try:
        urllib.request.urlopen(
            urllib.request.Request(CDP + "/json/version", headers={"User-Agent": "km"}),
            timeout=10)
    except Exception as e:
        print("[L] ★ 自动化浏览器(9222)没在跑，跳过端到端检查：%s" % str(e)[:80])
        return 0

    rc = 0
    for path in paths:
        cfg = PAGES.get(path, dict(elem="out", mode="ready", loading=("正在载入",),
                                   required=None))
        elem = cfg["elem"]
        loading_words = cfg["loading"]
        mode = cfg["mode"]
        required = cfg.get("required")
        try:
            r = urllib.request.Request(CDP + "/json/new?about:blank", method="PUT")
            with urllib.request.urlopen(r, timeout=20) as x:
                tab = json.loads(x.read().decode("utf-8", "replace"))
            ws = websocket.create_connection(tab["webSocketDebuggerUrl"], timeout=30,
                                             suppress_origin=True)
        except Exception as e:
            print("[L] %-8s ★ 开标签失败：%s" % (path, str(e)[:90]))
            rc = 1
            continue

        n = [0]

        def send(method, params=None):
            n[0] += 1
            ws.send(json.dumps({"id": n[0], "method": method, "params": params or {}}))
            t0 = time.time()
            while time.time() - t0 < 30:
                m = json.loads(ws.recv())
                if m.get("id") == n[0]:
                    return m
            return None

        send("Page.enable")
        send("Runtime.enable")
        send("Network.enable")
        send("Page.navigate", {"url": BASE + path})
        time.sleep(2.5)
        send("Network.setCookie", {"name": "kmsid", "value": tok,
                                   "domain": "127.0.0.1", "path": "/"})
        send("Page.reload", {"ignoreCache": True})

        errs, text = [], ""
        t0 = time.time()
        while time.time() - t0 < 30:
            try:
                msg = json.loads(ws.recv())
            except Exception:
                break
            if msg.get("method") == "Runtime.exceptionThrown":
                d = (msg.get("params") or {}).get("exceptionDetails") or {}
                errs.append(str((d.get("exception") or {}).get("description")
                                or d.get("text") or "")[:200])
            if time.time() - t0 > 8:
                text = evaluate(ws, send,
                                "document.getElementById('%s')"
                                "?document.getElementById('%s').textContent:''"
                                % (elem, elem)) or ""
                # auto 模式：等它真正出内容；ready 模式：等 8 秒看有没有 JS 报错就够
                if mode == "auto":
                    if text and not any(w in text for w in loading_words):
                        break
                else:
                    break
            time.sleep(0.5)

        # ★ 先确认"读到的确实是目标页面" —— 浏览器可能把内容给了别的标签，
        #   不校验的话会出现「读到别的页面的文字」这种假结果（踩过）。
        where = evaluate(ws, send, "String(location.pathname)") or ""
        on_page = (where == path) or where.rstrip("/") == path.rstrip("/")

        # 关键控件是否存在（有的话说明页面脚本确实跑到了建控件的部分）
        has_req = True
        if required:
            has_req = bool(evaluate(ws, send,
                                    "!!document.getElementById('%s')" % required))

        if mode == "auto":
            bad = ((not text) or any(w in text for w in loading_words)
                   or bool(errs) or not has_req)
        else:
            # 需要输入才出结果的页面：只要求「没 JS 报错」+「关键控件在」
            bad = bool(errs) or not has_req
        if not on_page:
            bad = True
            print("[L] %-14s ★ 页面没切过去（当前路径=%r，期望=%r）"
                  % (path, where, path), flush=True)
        print("[L] %-14s %s  #%s=%r%s"
              % (path, "★ 有问题" if bad else "✓ 正常", elem, text[:80],
                 ("" if has_req else "  缺少 #%s" % required)))
        for e in errs[:3]:
            print("[L]     JS 异常：%s" % e)
        if bad:
            rc = 1
        try:
            ws.close()
        except Exception:
            pass

    print()
    print("[L] %s" % ("✓ 全部页面正常" if rc == 0 else "★★★ 有页面不正常，别发布"))
    return rc


if __name__ == "__main__":
    sys.exit(main())
