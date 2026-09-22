# -*- coding: utf-8 -*-
"""验证打印后核对（verify_printed）的判失败/判成功两条路径 + do_print(check_only=True)。

不打印、不出纸：
  ① 拿**仍在未打印队列**的单去核对 → 必须判失败，且原因 = "ERP 队列未变化"
  ② 拿**不在队列**的假 sid 去核对   → 必须判成功（离开队列 2/2）——证明成功路径可通
"""
import io
import json
import os
import sys

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "desktop"))
import kuaimai_print as K   # noqa: E402

CODE = "7153-常规黑色L"


def main():
    cur, n, err = K.fetch_unprinted_sids(CODE, page_size=500)
    print("接口未打印队列: %d 条 (err=%s)" % (n, err or "-"))
    still = sorted(cur)[:5]
    print("拿 5 个仍在队列的 sid 核对:", still)

    print("\n① 判失败路径（队列没变 → 必须 ok=False）")
    logs = []
    r = K.verify_printed(CODE, still, logs=logs, max_secs=6.0, interval=3.0)
    for x in logs:
        print("   ", x)
    print("   结果:", json.dumps(r, ensure_ascii=False))
    ok1 = (r.get("ok") is False) and r.get("why") == "ERP 队列未变化"
    print("   ==> 判失败且原因=「ERP 队列未变化」: %s" % ok1)

    print("\n② 判成功路径（这批单确实不在队列里 → ok=True）")
    logs2 = []
    fake = ["9999999999999901", "9999999999999902"]
    r2 = K.verify_printed(CODE, fake, logs=logs2, max_secs=6.0, interval=3.0)
    for x in logs2:
        print("   ", x)
    print("   结果:", json.dumps(r2, ensure_ascii=False))
    ok2 = (r2.get("ok") is True) and r2.get("gone") == 2
    print("   ==> 判成功且 gone=2: %s" % ok2)

    print("\n③ do_print(check_only=True) 走通（小批量 3 单，不点打印）")
    picked, skipped, logs3 = K.do_print(CODE, 3, check_only=True)
    for x in logs3:
        print("   ", x)
    ok3 = any("check_only" in str(x) for x in logs3) and not any("点打印: clicked" in str(x) for x in logs3)
    print("   ==> check_only 生效且没点打印: %s" % ok3)

    print("\n==> %s" % ("全部通过" if (ok1 and ok2 and ok3) else "有未通过项"))
    return 0 if (ok1 and ok2 and ok3) else 1


if __name__ == "__main__":
    sys.exit(main())
