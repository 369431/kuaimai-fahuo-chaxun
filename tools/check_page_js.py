# -*- coding: utf-8 -*-
"""★ 发布前必跑：检查所有网页页面的 JS 语法。

为什么要有这个脚本（血泪教训）：
  kuaimai_webui.py 里的页面是「Python 字符串里嵌 <script>」。
  Python 语法检查**发现不了** JS 里的括号错误 ——
  一旦 JS 有语法错，整个页面脚本不执行，表现是「一直载入中」「按钮点了没反应」，
  而且**不报任何错**（用户只看到转圈）。
  实测踩到：现货可发页多了一个 `)`，页面永远停在「正在载入…」，挂了整整一版。

用法：
    python tools\\check_page_js.py            # 只检查，返回码 0=通过 1=失败
    python tools\\check_page_js.py --quiet    # 只在失败时输出
"""
import io
import os
import re
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(REPO, "desktop"))
os.chdir(os.path.join(REPO, "desktop"))
sys.path.insert(0, os.path.join(REPO, "desktop"))

QUIET = "--quiet" in sys.argv


def find_node():
    """找 node（用于 JS 语法检查）。找不到就跳过（不阻断构建，只提示）。"""
    for p in (r"C:\Program Files\nodejs\node.exe",
              r"C:\Program Files (x86)\nodejs\node.exe",
              os.path.expanduser(r"~\AppData\Roaming\npm\node.exe")):
        if os.path.isfile(p):
            return p
    from shutil import which
    return which("node")


def main():
    try:
        import kuaimai_webui as W
    except Exception as e:
        print("[JS] ★ 导入 kuaimai_webui 失败：%s" % str(e)[:160])
        return 1

    node = find_node()
    pages = sorted((k, v) for k, v in vars(W).items()
                   if k.endswith("_HTML") and isinstance(v, str))
    if not node:
        print("[JS] 没找到 node，跳过 JS 语法检查（建议装 Node.js 以便拦住这类问题）")
        print("[JS] 要检查的页面：%s" % ", ".join(k for k, _ in pages))
        return 0

    tmp = os.path.join(os.environ.get("TEMP", "/tmp"), "_km_jscheck")
    os.makedirs(tmp, exist_ok=True)
    bad = []
    total = 0
    for name, html in pages:
        for i, s in enumerate(re.findall(r"<script>(.*?)</script>", html, re.S)):
            total += 1
            p = os.path.join(tmp, "%s_%d.js" % (name, i))
            io.open(p, "w", encoding="utf-8").write(s)
            r = subprocess.run([node, "--check", p], capture_output=True, text=True)
            if r.returncode != 0:
                bad.append((name, i, (r.stderr or "").strip().splitlines()[:8]))
            elif not QUIET:
                print("[JS] %-18s script %d  ✓（%d 字节）" % (name, i, len(s)))

    print()
    if bad:
        print("[JS] ★★★ 发现 %d 段 JS 语法错误（页面会「一直载入中」或按钮无反应）★★★"
              % len(bad))
        for (name, i, err) in bad:
            print("[JS] --- %s script %d ---" % (name, i))
            for line in err:
                print("[JS]     %s" % line)
        return 1
    print("[JS] ✓ 全部 %d 段 JS 语法正确（%d 个页面）" % (total, len(pages)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
