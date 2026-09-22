# -*- coding: utf-8 -*-
"""只勾选验证：print_selected(..., check_only=True) —— 不取号、不点打印、不出纸。

用法：python tools/km_verify_checkonly.py [编码] [数量]
断言：① 页面校验通过（停在 /trade/printv2/）
      ② 能扫到的行数 ≥ min(要打, 该编码实际单数)（列表虚拟滚动，DOM 只渲染可见窗口≈17 行，
         所以「行数」看列表总数 + 实际勾到数，不看 DOM 窗口）
      ③ 勾到我们的单 == 挑到的单数（hitChecked）且 ERP「已勾选订单数」一致
      ④ **没有点击打印**
"""
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")


class _Tee(object):
    """同时写控制台与文件（控制台按 GBK 会花屏，报告用文件里的 UTF-8 文本）。"""

    def __init__(self, *streams):
        self.streams = streams

    def write(self, s):
        for st in self.streams:
            try:
                st.write(s)
            except Exception:
                pass

    def flush(self):
        for st in self.streams:
            try:
                st.flush()
            except Exception:
                pass


_OUT = os.environ.get("KM_VERIFY_OUT")
if _OUT:
    sys.stdout = _Tee(sys.stdout, open(_OUT, "w", encoding="utf-8"))

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "desktop"))
import kuaimai_print as K   # noqa: E402

CODE = sys.argv[1] if len(sys.argv) > 1 else "7153-常规黑色XL"
WANT = int(sys.argv[2]) if len(sys.argv) > 2 else 30


def main():
    print("=" * 72)
    print("只勾选验证 check_only | 编码=%s | 要打=%d 单" % (CODE, WANT))
    print("=" * 72)
    picked, skipped, _ = K.do_print(CODE, WANT, dry_run=True)
    print("挑单: 要打 %d 单 / 跳过 %d 单" % (len(picked), len(skipped)))
    if not picked:
        print("！！挑不到单 → 无法验证")
        return 1
    sids = [o["sid"] for o in picked]
    shorts = [o.get("short_id") or "" for o in picked]
    print("前 3 单:", [(o["sid"], o.get("short_id")) for o in picked[:3]])
    print("-" * 72)
    v = {}
    logs = K.print_selected(CODE, sids, shorts, check_only=True, verdict=v)
    for line in logs:
        print(line)
    print("-" * 72)
    print("verdict:", json.dumps(v, ensure_ascii=False))
    # ---- 断言 ----
    txt = "\n".join(str(x) for x in logs)
    n = len(sids)
    page_ok = any("/trade/printv2/" in str(x) for x in logs)
    win_rows = int(v.get("rows_window") or 0)
    total_rows = v.get("rows_total")
    try:
        total_rows = int(total_rows) if total_rows is not None else None
    except Exception:
        total_rows = None
    # 「行数」：列表总数（可扫到）优先；拿不到就退化成 DOM 窗口
    reached = total_rows if total_rows is not None else win_rows
    rows_ge_want = (reached is not None and reached >= WANT)
    rows_note = ""
    if not rows_ge_want and total_rows is not None and total_rows < WANT:
        rows_note = "（该编码实际只有 %d 单 < 要打 %d，已全部扫到，非链路问题）" % (total_rows, WANT)
    checked_ok = v.get("checked") == n
    model_ok = v.get("model_count") == n
    no_click = not v.get("clicked")
    no_fail = not txt.startswith("！！")
    cleared = "清空勾选（验证不留残余）" in txt
    scan_beyond_window = (v.get("checked") or 0) > win_rows if win_rows else False
    print("\n断言:")
    print("  ① 页面校验通过(在 /trade/printv2/): %s" % page_ok)
    print("  ② 可扫到行数 ≥ 要打(取列表总数): %s（列表总数=%s，DOM 渲染窗口=%d 行%s）"
          % (rows_ge_want, total_rows, win_rows, rows_note))
    print("  ③ 勾到我们的单 == 挑到的单数(%d): %s（实测 %s）" % (n, checked_ok, v.get("checked")))
    print("     ERP「已勾选订单数」== %d: %s（实测 %s）" % (n, model_ok, v.get("model_count")))
    print("     勾到数 > DOM 窗口(=%d) → 证明扫过了虚拟滚动窗口: %s" % (win_rows, scan_beyond_window))
    print("  ④ 没有点击打印: %s（clicked=%s）" % (no_click, v.get("clicked")))
    print("  链路无失败行: %s" % no_fail)
    print("  验证后清空勾选: %s" % cleared)
    allok = (page_ok and checked_ok and model_ok and no_click and no_fail and cleared
             and win_rows > 0)
    print("\n==> %s" % ("全部通过" if allok else "有断言未通过"))
    return 0 if allok else 1


if __name__ == "__main__":
    sys.exit(main())
