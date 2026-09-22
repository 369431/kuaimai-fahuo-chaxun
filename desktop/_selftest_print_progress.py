# -*- coding: utf-8 -*-
"""「打单进度」面板 + 进度上报 的自检（**不出纸**、不连 CDP、不打真库）。

用法：python desktop/_selftest_print_progress.py
覆盖：
  A. 桩对象建面板：假 stats() + 假 print_progress.json → 断言正在打印行/排队条数/失败原因/日志尾部
  B. 真文件路径：手动写一次 print_progress.json（扫描勾选 已勾 12/30）→ 断言面板显示 12/30
  C. 真库：用 scan_log.db 跑一遍 stats() → 断言面板渲染出的排队条数 == live.queue 条数
  D. 布局：解析 kuaimai_scan.py 的 _ops_list → 断言按钮不叠格、原有按钮一个不少
"""
import os
import re
import sys
import io
import json
import time
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import tkinter as tk

OK = []
BAD = []
# 同时写一份 UTF-8 日志（控制台是 GBK，中文会乱码；报告里直接读这个文件）
_LOG = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                    "_selftest_print_progress.out.txt")
try:
    _LOG_FH = io.open(_LOG, "w", encoding="utf-8")
except Exception:
    _LOG_FH = None


def out(s):
    print(s, flush=True)
    try:
        if _LOG_FH is not None:
            _LOG_FH.write(s + "\n")
            _LOG_FH.flush()
    except Exception:
        pass


def check(name, good, info=""):
    (OK if good else BAD).append(name)
    out("%s %s  (%s)" % ("OK  " if good else "FAIL", name, info))


class StubApp(object):
    """桩 App：只要 root + status_text（真 App 也就是这两个被用到）。"""

    def __init__(self, root):
        self.root = root
        self.status_text = tk.StringVar(master=root, value="")


FAKE = {
    "ok": True, "err": "",
    "progress": {"ts": 1758500000.0, "code": "7153-常规黑色XL", "want": 30, "picked": 30,
                 "phase": "扫描勾选", "checked": 23, "page": 3,
                 "msg": "逐屏扫描勾选：已勾 23/30（第 3 屏）", "ok": None},
    "live": {"printing": [{"job_id": 9, "code": "7153-常规黑色XL", "qty": 30, "who": "admin",
                           "claimed_by": "pc1", "claim_ts": 0, "elapsed": 130, "tries": 0}],
             "queue": [{"job_id": 11, "code": "7107-黑色M", "qty": 5, "client": "pc2",
                        "retrying": False, "last_msg": ""},
                       {"job_id": 12, "code": "7107-白色L", "qty": 7, "client": "pc1",
                        "retrying": True, "tries": 2, "last_msg": "第 2 次失败，180 秒后重试：打印机离线"}],
             "failed": [{"job_id": 4, "code": "7153-常规黑色XL", "qty": 23, "tries": 3,
                         "last_msg": "重试 3 次仍失败：同 SKU 冷却中（还需 60 秒）",
                         "done_ts": 1758500100}],
             "counts": {"printing": 1, "queue": 2, "failed": 1}},
    "recent": [{"job_id": 12, "code": "7107-白色L", "qty": 7, "status": "pending",
                "claimed_by": "", "target_client": "pc1", "out_sid": "",
                "last_msg": "第 2 次失败，180 秒后重试"},
               {"job_id": 9, "code": "7153-常规黑色XL", "qty": 30, "status": "printing",
                "claimed_by": "pc1", "target_client": "pc1", "out_sid": "", "last_msg": ""},
               {"job_id": 4, "code": "7153-常规黑色XL", "qty": 23, "status": "failed",
                "claimed_by": "pc1", "target_client": "pc1", "out_sid": "",
                "last_msg": "重试 3 次仍失败：同 SKU 冷却中"},
               {"job_id": 1, "code": "7153-常规黑色XL", "qty": 30, "status": "done",
                "claimed_by": "pc1", "target_client": "pc1", "out_sid": "76982400000001",
                "last_msg": "打印成功"}],
    "log": ["09-22 20:49:16  [任务] 认领到任务 #1：7153-常规黑色XL ×30（来源 admin）→ 准备打单",
            "09-22 20:53:24  任务 #3 完成：无可打订单（0 单）",
            "09-22 20:53:31  总开关：已暂停（删掉 auto_print_pause.flag 即恢复）"],
}


def text_of(w):
    try:
        return str(w.cget("text"))
    except Exception:
        return ""


def tree_rows(tree):
    out = []
    for iid in tree.get_children():
        out.append(tuple(str(x) for x in tree.item(iid, "values")))
    return out


def main():
    import kuaimai_scan as S

    out("BASE_DIR = %s" % S.BASE_DIR)
    out("PROGRESS_FILE = %s" % S.PROGRESS_FILE)
    out("DB_FILE = %s" % S.DB_FILE)

    root = tk.Tk()
    root.withdraw()
    app = StubApp(root)

    # ---------------- A. 桩对象建面板 ----------------
    dlg = S.PrintProgressDialog(app, parent=root, payload_fn=lambda: json.loads(json.dumps(FAKE)))
    dlg.win.withdraw()                      # 别弹到用户脸上
    root.update()

    big = text_of(dlg.lbl_printing)
    check("A1 正在打印行含编码", "7153-常规黑色XL" in big, big)
    check("A2 正在打印行含数量 ×30", "×30" in big, big)
    check("A3 正在打印行含哪台电脑 pc1", "pc1" in big, big)
    check("A4 正在打印行含已用时", "已用时" in big, big)

    phase = text_of(dlg.lbl_phase)
    check("A5 阶段行含「已勾 23/30」", "已勾 23/30" in phase, phase)
    check("A6 阶段行含 phase 名与第几屏", ("扫描勾选" in phase or "逐屏扫描勾选" in phase)
          and "第 3 屏" in phase, phase)

    check("A7 排队条数 = 2", text_of(dlg.lbl_queue_title) == "排队中（2）",
          text_of(dlg.lbl_queue_title))
    qtxt = text_of(dlg.lbl_queue)
    check("A8 排队列出 2 条且含编码×数量→哪台", (qtxt.count("\n") == 1 and "7107-黑色M ×5 → pc2" in qtxt
                                            and "7107-白色L ×7 → pc1" in qtxt), qtxt.replace("\n", " / "))
    check("A9 排队标出重试中", "重试中" in qtxt, qtxt.replace("\n", " / "))

    check("A10 失败条数 = 1", text_of(dlg.lbl_failed_title) == "失败（1）",
          text_of(dlg.lbl_failed_title))
    ftxt = text_of(dlg.lbl_failed)
    check("A11 失败原因显示", "重试 3 次仍失败：同 SKU 冷却中（还需 60 秒）" in ftxt, ftxt)

    rows = tree_rows(dlg.tree)
    check("A12 最近结果行数 = 4", len(rows) == 4, "%d 行" % len(rows))
    check("A13 最近结果含运单号/状态/哪台",
          rows[3][4] == "pc1" and rows[3][5] == "76982400000001" and rows[3][3] == "已完成",
          str(rows[3]))

    ltxt = dlg.log_text.get("1.0", "end")
    check("A14 日志尾部含关键字「认领到任务」", "认领到任务" in ltxt, ltxt.splitlines()[0] if ltxt.strip() else "")
    check("A15 日志尾部含「总开关」", "总开关" in ltxt, "")
    check("A16 底部提示更新时间", "更新于" in text_of(dlg.lbl_updated), text_of(dlg.lbl_updated))

    # 自动刷新：换 payload → _tick 后界面跟着变
    FAKE2 = json.loads(json.dumps(FAKE))
    FAKE2["live"]["queue"] = []
    FAKE2["progress"]["phase"] = "完成"
    FAKE2["progress"]["checked"] = 30
    FAKE2["progress"]["ok"] = True
    dlg.payload_fn = lambda: FAKE2
    dlg._tick()
    root.update()
    check("A17 自动刷新后排队归零", text_of(dlg.lbl_queue_title) == "排队中（0）",
          text_of(dlg.lbl_queue_title))
    check("A18 自动刷新后显示结果：成功", "结果：成功" in text_of(dlg.lbl_phase),
          text_of(dlg.lbl_phase))

    dlg.close()
    root.update()
    check("A19 关窗后停止定时刷新（_after 为空）", dlg._after is None, str(dlg._after))

    # ---------------- B. 真文件路径：写一次 12/30 ----------------
    saved = None
    try:
        if os.path.isfile(S.PROGRESS_FILE):
            with io.open(S.PROGRESS_FILE, encoding="utf-8") as f:
                saved = f.read()
        snap = {"ts": time.time(), "code": "7153-常规黑色XL", "want": 30, "picked": 30,
                "phase": "扫描勾选", "checked": 12, "page": 2, "ok": None,
                "msg": "逐屏扫描勾选：已勾 12/30（第 2 屏）"}
        tmp = S.PROGRESS_FILE + ".selftest"
        with io.open(tmp, "w", encoding="utf-8") as f:
            json.dump(snap, f, ensure_ascii=False)
        os.replace(tmp, S.PROGRESS_FILE)
        got = S.read_print_progress()
        check("B1 真文件读回 checked=12/want=30", got.get("checked") == 12 and got.get("want") == 30,
              json.dumps(got, ensure_ascii=False))
        d2 = S.format_progress({"ok": True, "progress": got, "live": {}, "recent": [], "log": []})
        check("B2 面板文案显示 12/30", "已勾 12/30" in d2["printing_phase"], d2["printing_phase"])
        dlg2 = S.PrintProgressDialog(app, parent=root, payload_fn=S.print_progress_payload)
        dlg2.win.withdraw()
        dlg2.refresh()
        root.update()
        check("B3 真路径面板 lbl_phase 显示 12/30", "已勾 12/30" in text_of(dlg2.lbl_phase),
              text_of(dlg2.lbl_phase))
        # ---------------- C. 真库：live.queue 条数 ----------------
        import kuaimai_print_jobs as pj
        conn = sqlite3.connect(S.DB_FILE, timeout=10)
        try:
            conn.row_factory = sqlite3.Row
            st = pj.stats(conn)
        finally:
            conn.close()
        nq = len(((st.get("live") or {}).get("queue") or []))
        nrows = len(tree_rows(dlg2.tree))
        check("C1 真库 stats() 能跑通且含 live.queue", "live" in st, "真库 queue=%d 条" % nq)
        check("C2 面板渲染的排队标题与真库一致",
              text_of(dlg2.lbl_queue_title) == "排队中（%d）" % nq, text_of(dlg2.lbl_queue_title))
        check("C3 面板最近结果行数 == min(recent,8)", nrows == min(len(st.get("recent") or []), 8),
              "面板 %d 行 / recent %d 条" % (nrows, len(st.get("recent") or [])))
        if nq:
            first = ((st["live"]["queue"])[0])
            check("C4 排队首条编码出现在面板里", str(first.get("code")) in text_of(dlg2.lbl_queue),
                  str(first.get("code")))
        # C5：安装目录那份真库（用户实际在跑的那份）—— 面板能否渲染出真实排队条数
        live_db = os.path.join(os.environ.get("LOCALAPPDATA") or "", "KuaimaiScan", "scan_log.db")
        if os.path.isfile(live_db):
            old_db, old_pf = S.DB_FILE, S.PROGRESS_FILE
            try:
                S.DB_FILE = live_db
                S.PROGRESS_FILE = os.path.join(os.path.dirname(live_db), "print_progress.json")
                pl = S.print_progress_payload()
                nq2 = len(pl["live"]["queue"])
                d3 = S.PrintProgressDialog(app, parent=root, payload_fn=S.print_progress_payload)
                d3.win.withdraw()
                d3.refresh()
                root.update()
                check("C5 安装目录真库：面板排队标题 == 真库 live.queue 条数",
                      text_of(d3.lbl_queue_title) == "排队中（%d）" % nq2,
                      "真库 %s 排队 %d 条 / 面板 %s" % (live_db, nq2, text_of(d3.lbl_queue_title)))
                check("C6 安装目录真库：面板能渲染每次排队明细",
                      all((str(q.get("code")) in text_of(d3.lbl_queue))
                          for q in pl["live"]["queue"]) if nq2 else True,
                      text_of(d3.lbl_queue).replace("\n", " / "))
                out("      真库 live 摘要: %s" % json.dumps(
                    {"queue": [q.get("code") for q in pl["live"]["queue"]],
                     "printing": [p.get("code") for p in pl["live"]["printing"]],
                     "failed": [f.get("code") for f in pl["live"]["failed"]],
                     "recent": len(pl["recent"])}, ensure_ascii=False))
                d3.close()
            finally:
                S.DB_FILE, S.PROGRESS_FILE = old_db, old_pf
        dlg2.close()
    finally:
        try:
            if saved is None:
                os.remove(S.PROGRESS_FILE)
            else:
                with io.open(S.PROGRESS_FILE, "w", encoding="utf-8") as f:
                    f.write(saved)
        except Exception:
            pass

    # ---------------- D. 布局：按钮不叠格、原有按钮一个不少 ----------------
    src = io.open(os.path.join(S.BASE_DIR, "kuaimai_scan.py"), encoding="utf-8").read()
    m = re.search(r"_ops_list = \((.*?)\)\n\s*for i,", src, re.S)
    texts = re.findall(r'\("([^"]+)",\s*(?:lambda|self\.)', m.group(1)) if m else []
    cols = 5
    cells = [(i // cols, i % cols) for i in range(len(texts))]
    check("D1 操作区按钮不叠格", len(set(cells)) == len(cells),
          "%d 个按钮，格子 %s" % (len(texts), cells))
    check("D2 新按钮「打单进度」在列表里", "打单进度" in texts, str(texts[-2:]))
    need = ["增量刷新", "全量重拉", "刷新货位库存", "刷新锁定数", "导出扫码日志 Excel", "清空日志",
            "API 设置", "子客户端管理", "对外访问设置", "检查更新", "重新登录", "打印分工"]
    missing = [t for t in need if t not in texts]
    check("D3 原有 12 个按钮一个不少", not missing, "缺：%s" % missing if missing else "%d 个都在" % len(need))
    # 与既有控件（可发撤回宽限 row2/col4、复选框 row3）不冲突
    check("D4 新按钮未占用「可发撤回宽限」那格(2,4)，也未落到复选框行(3,x)",
          (2, 4) not in cells and max(r for r, _c in cells) <= 2,
          "按钮格子=%s；占用(2,4)的按钮 %d 个" % (cells, len([c for c in cells if c == (2, 4)])))

    try:
        root.destroy()
    except Exception:
        pass

    print("")
    print("RESULT: %s" % ("ALL OK" if not BAD else "%d PROBLEM(S): %s" % (len(BAD), BAD)))
    return 1 if BAD else 0

if __name__ == "__main__":
    raise SystemExit(main())
