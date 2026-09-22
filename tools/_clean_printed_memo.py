# -*- coding: utf-8 -*-
"""清掉 %LOCALAPPDATA%\\KuaimaiScan\\printed_memory.json 里**近 30 分钟**的误记条目。

用法：python tools/_clean_printed_memo.py [分钟=30] [--apply]
不加 --apply 只预览（不写）。
"""
import io
import json
import os
import sys
import time

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

MIN = float(sys.argv[1]) if len(sys.argv) > 1 else 30.0
APPLY = "--apply" in sys.argv
P = os.path.join(os.environ.get("LOCALAPPDATA", ""), "KuaimaiScan", "printed_memory.json")


def main():
    with open(P, encoding="utf-8") as f:
        mem = json.load(f)
    now = time.time()
    keep, drop = {}, {}
    for k, v in mem.items():
        ts = float((v or {}).get("ts") or 0)
        (drop if (now - ts) <= MIN * 60 else keep)[k] = v
    print("文件:", P)
    print("清理前条数: %d" % len(mem))
    print("近 %.0f 分钟内(要删)条数: %d" % (MIN, len(drop)))
    print("保留条数: %d" % len(keep))
    if drop:
        ages = sorted(round((now - float(v.get('ts') or 0)) / 60, 1) for v in drop.values())
        print("  待删条目 age(min): %s" % (ages[:3] + ["..."] + ages[-3:] if len(ages) > 6 else ages))
        print("  待删 sid:", sorted(drop.keys()))
    if APPLY:
        with open(P, "w", encoding="utf-8") as f:
            json.dump(keep, f, ensure_ascii=False)
        with open(P, encoding="utf-8") as f:
            after = json.load(f)
        print("已写回。清理后条数: %d（校验读到 %d）" % (len(keep), len(after)))
    else:
        print("（预览模式，未写文件；加 --apply 才写）")
    return 0


if __name__ == "__main__":
    sys.exit(main())
