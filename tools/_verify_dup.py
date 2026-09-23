# -*- coding: utf-8 -*-
"""针对性验证：重复提交去重（全部走临时库/桩；绝不真实出纸；绝不碰暂停开关）。

覆盖：
 A. dup_reason / add_job_checked 纯库断言（窗口边界、force、失败态）
 A2. 并发：同一编码 8 线程同时提交 → 只建 1 条
 B. /api/stock/canprint 真 HTTP handler（桩 auth/perms）：首建 / 重复不建 / force / done 窗口
 C. /api/print/jobs_add 重复 → 409
 D. 无权限 → 403 且无副作用
 E. 真库与暂停开关前后只读快照一致
"""
import hashlib
import io
import json
import os
import shutil
import sqlite3
import sys
import tempfile
import threading
import time

DESKTOP = r"C:\Users\Kerwin\Desktop\kuaimai发货查询\desktop"
sys.path.insert(0, DESKTOP)
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

LOCAL = os.path.join(os.environ.get("LOCALAPPDATA") or "", "KuaimaiScan")
PAUSE = os.path.join(LOCAL, "auto_print_pause.flag")
REAL_DB = os.path.join(LOCAL, "scan_log.db")

RES = []


def check(name, cond, detail=""):
    RES.append((bool(cond), name, detail))
    print("%s  %s%s" % ("PASS" if cond else "FAIL", name,
                        ("  | " + str(detail)) if detail else ""), flush=True)


def snap(path):
    if not os.path.exists(path):
        return "ABSENT"
    st = os.stat(path)
    return "%d|%.0f|%s" % (st.st_size, st.st_mtime,
                           hashlib.sha256(io.open(path, "rb").read()).hexdigest()[:16])


def snap_dir(d, names):
    return {n: snap(os.path.join(d, n)) for n in names}


WATCH_RUN = ["scan_log.db", "printed_memory.json", "print_progress.json", "print_clients.json",
             "print_client.json", "auto_print.log", "kuaimai_users.json", "kuaimai_settings.json"]
WATCH_REPO = ["scan_log.db", "kuaimai_data.db"]

TMP = tempfile.mkdtemp(prefix="km_dup_verify_")
before_run = snap_dir(LOCAL, WATCH_RUN)
before_repo = snap_dir(DESKTOP, WATCH_REPO)
before_pause = snap(PAUSE)

import kuaimai_print_jobs as pj            # noqa: E402
import kuaimai_scan as ks                  # noqa: E402

# ---- 主程序模块全部指到临时目录（绝不碰真库/真设置/真日志）----
ks.BASE_DIR = TMP
ks.DB_FILE = os.path.join(TMP, "scan_log.db")
ks.SETTINGS_FILE = os.path.join(TMP, "kuaimai_settings.json")
ks.PRINT_CLIENTS_FILE = os.path.join(TMP, "print_clients.json")
ks.PRINT_CLIENT_FILE = os.path.join(TMP, "print_client.json")
io.open(ks.PRINT_CLIENTS_FILE, "w", encoding="utf-8").write(
    json.dumps({"admin": "pc1", "default": "pc1"}, ensure_ascii=False))

DB = ks.DB_FILE
TDB = os.path.join(TMP, "jobs_only.db")
ks.init_db()                      # 临时目录建 scan_record 等表

print("### A. dup_reason / add_job_checked（临时库）")
c = pj.connect(TDB)
check("A1 全新编码不判重复", pj.dup_reason(c, "7107-黑色M") == "")
jid, why = pj.add_job_checked(c, "7107-黑色M", 3, who="admin", target_client="pc1")
check("A2 首次建任务成功", jid > 0 and why == "", "jid=%s why=%r" % (jid, why))
check("A3 已有 pending → 判重复", "未完成" in pj.dup_reason(c, "7107-黑色M"),
      pj.dup_reason(c, "7107-黑色M"))
jid2, why2 = pj.add_job_checked(c, "7107-黑色M", 3, who="admin", target_client="pc1")
check("A4 重复提交不建任务", jid2 == 0 and why2, "jid2=%s why=%r" % (jid2, why2))
check("A5 库里仍只有 1 条",
      c.execute("SELECT COUNT(*) FROM print_jobs WHERE code='7107-黑色M'").fetchone()[0] == 1)
jid3, why3 = pj.add_job_checked(c, "7107-黑色M", 3, who="admin", target_client="pc1", force=True)
check("A6 force=True 可绕过（追加）", jid3 > 0, "jid3=%s" % jid3)
check("A7 force 后共 2 条",
      c.execute("SELECT COUNT(*) FROM print_jobs WHERE code='7107-黑色M'").fetchone()[0] == 2)
c.execute("UPDATE print_jobs SET status='claimed', claimed_by='pc1', claim_ts=? WHERE job_id=?",
          (int(time.time()), jid3))
c.commit()
check("A8 claimed 也算未完成", "未完成" in pj.dup_reason(c, "7107-黑色M"))
c.execute("UPDATE print_jobs SET status='done', done_ts=? WHERE job_id=?", (int(time.time()), jid))
c.execute("UPDATE print_jobs SET status='done', done_ts=? WHERE job_id=?", (int(time.time()), jid3))
c.commit()
check("A9 done 窗口内判重复", "刚打完" in pj.dup_reason(c, "7107-黑色M"),
      pj.dup_reason(c, "7107-黑色M"))
c.execute("UPDATE print_jobs SET done_ts=? WHERE code='7107-黑色M'", (int(time.time()) - 5,))
c.commit()
check("A10 窗口=1s 且 5 秒前 done → 放行",
      pj.dup_reason(c, "7107-黑色M", window_secs=1) == "",
      repr(pj.dup_reason(c, "7107-黑色M", window_secs=1)))
jid4, why4 = pj.add_job_checked(c, "7107-黑色M", 1, who="admin", target_client="pc1",
                                window_secs=1)
check("A11 窗口外可再建新任务（追加）", jid4 > 0, "jid4=%s why=%r" % (jid4, why4))

cb = "7107-边界60"
c.execute("INSERT INTO print_jobs(code,qty,who,target_client,status,last_msg,created_at,done_ts) "
          "VALUES(?,1,'a','pc1','done','',?,?)",
          (cb, "2026-01-01 00:00:00", int(time.time()) - pj.DUP_WINDOW))
c.commit()
check("A12 恰在窗口边界(60s)仍判重复", pj.dup_reason(c, cb) != "", pj.dup_reason(c, cb))
c.execute("DELETE FROM print_jobs WHERE code=?", (cb,))
c.execute("INSERT INTO print_jobs(code,qty,who,target_client,status,last_msg,created_at,done_ts) "
          "VALUES(?,1,'a','pc1','done','',?,?)",
          (cb, "2026-01-01 00:00:00", int(time.time()) - pj.DUP_WINDOW - 5))
c.commit()
check("A13 超出窗口(65s)放行", pj.dup_reason(c, cb) == "", pj.dup_reason(c, cb))
c.execute("UPDATE print_jobs SET status='failed' WHERE code='7107-黑色M'")
c.commit()
check("A14 failed 不挡重复", pj.dup_reason(c, "7107-黑色M") == "")
c.close()

print()
print("### A2. 并发：同一编码 8 线程同时提交 → 只应建成 1 条")
TDB2 = os.path.join(TMP, "jobs_conc.db")
pj.connect(TDB2).close()
got, lock = [], threading.Lock()


def worker(i):
    cc = pj.connect(TDB2)
    try:
        j, w = pj.add_job_checked(cc, "并发-同编码", 1, who="admin", target_client="pc1")
    finally:
        cc.close()
    with lock:
        got.append((j, w))


ts = [threading.Thread(target=worker, args=(i,)) for i in range(8)]
[t.start() for t in ts]
[t.join() for t in ts]
cc = pj.connect(TDB2)
n = cc.execute("SELECT COUNT(*) FROM print_jobs WHERE code='并发-同编码'").fetchone()[0]
cc.close()
check("A15 8 并发只建成 1 条", n == 1,
      "建成 %d 条；成功线程=%d" % (n, sum(1 for j, _ in got if j)))

print()
print("### B/C/D. 真 HTTP handler（桩 auth/perms，临时库）")


class _Hdrs(dict):
    def get(self, k, d=None):
        for kk, vv in self.items():
            if kk.lower() == str(k).lower():
                return vv
        return d


class _FakeAuth(object):
    def user_perms_raw(self, name):
        return {}


class _FakePerms(object):
    LABELS = {}

    def effective(self, raw, role):
        return {"stock.canprint": True, "scan.printed": True}


class _DenyPerms(object):
    LABELS = {}

    def effective(self, raw, role):
        return {"stock.canprint": False, "scan.printed": False}


_ORIG_AUTH, _ORIG_PERMS = ks.auth, ks.perms


def call(path, body, deny=False):
    ks.auth = _FakeAuth()
    ks.perms = _DenyPerms() if deny else _FakePerms()
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    h = ks._WebHandler.__new__(ks._WebHandler)
    h.command = "POST"
    h.path = path
    h.requestline = "POST %s HTTP/1.1" % path
    h.request_version = "HTTP/1.1"
    h.client_address = ("127.0.0.1", 5555)
    h.headers = _Hdrs({"Content-Length": str(len(raw)),
                       "Content-Type": "application/json"})
    h.rfile = io.BytesIO(raw)
    h.wfile = io.BytesIO()
    h._cookie_out = ""
    h._auth = lambda qs: {"name": "admin", "role": "admin"}
    try:
        h.do_POST()
    except Exception as e:
        return 0, {"error": "runner-exception: %s" % e}
    data = h.wfile.getvalue()
    head, _, payload = data.partition(b"\r\n\r\n")
    try:
        status = int(head.split(b" ")[1])
    except Exception:
        status = 0
    try:
        obj = json.loads(payload.decode("utf-8") or "{}")
    except Exception:
        obj = {"_raw": payload[:200].decode("utf-8", "replace")}
    return status, obj


def n_jobs(code):
    cc = pj.connect(DB)
    try:
        return cc.execute("SELECT COUNT(*) FROM print_jobs WHERE code=?", (code,)).fetchone()[0]
    finally:
        cc.close()


def n_scans(code):
    cc = sqlite3.connect(DB)
    try:
        return cc.execute("SELECT COUNT(*) FROM scan_record WHERE barcode=?", (code,)).fetchone()[0]
    finally:
        cc.close()


CODE = "9681-燕麦色S"
st, o = call("/api/stock/canprint", {"code": CODE, "qty": 5, "bins": "", "pending": 0, "shelf": 0})
check("B1 首次提交建任务", st == 200 and o.get("ok") and not o.get("dup"), (st, o))
check("B2 库里 1 条任务", n_jobs(CODE) == 1, "n=%d" % n_jobs(CODE))
check("B3 扫码记录已写（记录仍照写）", n_scans(CODE) == 1, "n=%d" % n_scans(CODE))

st, o = call("/api/stock/canprint", {"code": CODE, "qty": 5, "bins": "", "pending": 0, "shelf": 0})
check("B4 重复提交不建任务（dup=True）", st == 200 and o.get("ok") and o.get("dup"), (st, o))
check("B5 库里仍 1 条任务（没重复建）", n_jobs(CODE) == 1, "n=%d" % n_jobs(CODE))
check("B6 重复时提示文案非空", bool(o.get("dup_msg")), o.get("dup_msg"))
check("B7 重复时扫码记录仍写入（只是不建任务）", n_scans(CODE) == 2, "n=%d" % n_scans(CODE))

st, o = call("/api/stock/canprint", {"code": CODE, "qty": 5, "force": True})
check("B8 force 可追加（2 条）", st == 200 and not o.get("dup") and n_jobs(CODE) == 2,
      (st, n_jobs(CODE)))

cc = pj.connect(DB)
cc.execute("UPDATE print_jobs SET status='done', done_ts=? WHERE code=?", (int(time.time()), CODE))
cc.commit()
cc.close()
st, o = call("/api/stock/canprint", {"code": CODE, "qty": 5})
check("B9 done 窗口内再提交也挡", o.get("dup") and n_jobs(CODE) == 2,
      (o.get("dup_msg"), n_jobs(CODE)))

st, o = call("/api/print/jobs_add", {"code": CODE, "qty": 5})
check("C1 jobs_add 重复 → 409 + dup", st == 409 and o.get("dup"), (st, o))
st, o = call("/api/print/jobs_add", {"code": "新编码-测试1", "qty": 2})
check("C2 jobs_add 新编码 → 200", st == 200 and o.get("job_id"), (st, o))

before_n = n_jobs("无权限-测试")
st, o = call("/api/stock/canprint", {"code": "无权限-测试", "qty": 5}, deny=True)
after_n = n_jobs("无权限-测试")
check("D1 无权限 → 403", st == 403 and o.get("denied"), (st, o))
check("D2 被拒时无副作用（无新任务）", before_n == 0 and after_n == 0,
      "%d -> %d" % (before_n, after_n))
b4 = n_jobs("无权限-测试2")
st2, o2 = call("/api/print/jobs_add", {"code": "无权限-测试2", "qty": 5}, deny=True)
check("D3 jobs_add 无权限 → 403", st2 == 403, (st2, o2))
check("D4 jobs_add 被拒无副作用", b4 == 0 and n_jobs("无权限-测试2") == 0)

ks.auth, ks.perms = _ORIG_AUTH, _ORIG_PERMS

after_run = snap_dir(LOCAL, WATCH_RUN)
after_repo = snap_dir(DESKTOP, WATCH_REPO)
chg = [k for k in WATCH_RUN if before_run[k] != after_run[k]]
check("E1 运行目录关键文件未变", chg == [], chg)
chg2 = [k for k in WATCH_REPO if before_repo[k] != after_repo[k]]
check("E2 仓库目录 DB 未变", chg2 == [], chg2)
check("E3 暂停开关一字未变", before_pause == snap(PAUSE),
      "%s -> %s" % (before_pause, snap(PAUSE)))
check("E4 暂停开关仍不存在（自动打单没被我动）", snap(PAUSE) == "ABSENT", snap(PAUSE))

rc = sqlite3.connect("file:%s?mode=ro" % REAL_DB.replace("\\", "/"), uri=True)
rc.row_factory = sqlite3.Row
rows = rc.execute("SELECT job_id,status FROM print_jobs WHERE code='9681-燕麦色S' "
                  "ORDER BY job_id").fetchall()
rc.close()
check("E5 真库 9681 历史任务未被改动（仍 3 条）", len(rows) == 3,
      [(r["job_id"], r["status"]) for r in rows])

print()
npass = sum(1 for ok, _, _ in RES if ok)
print("RESULT: %d/%d PASS" % (npass, len(RES)))
if npass != len(RES):
    print("FAILED:")
    for ok, name, detail in RES:
        if not ok:
            print("  -", name, detail)
shutil.rmtree(TMP, ignore_errors=True)
print("tmp cleaned:", TMP)
