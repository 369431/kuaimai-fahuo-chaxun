# -*- coding: utf-8 -*-
"""按账号分工的打单任务队列（主端权威）。

用途：多台电脑（主端 + 若干子端）同时自动打单时，保证**一个任务只被一台电脑打**。

表 print_jobs:
    job_id / code / qty / who(来源账号) / target_client(派给谁) /
    status(pending|claimed|printing|done|failed|cancelled) / claimed_by / claim_ts /
    done_ts / tries / out_sid / last_msg / created_at

三道防重复闸：
  1) claim() 原子认领（BEGIN IMMEDIATE + rowcount 判定）——并发下只有一台成功
  2) reclaim() 超时回收（认领后 5 分钟没回写 → 回 pending；重试超 3 次 → failed）
  3) 客户端侧另有"本机去重记忆" + ERP 打印次数核对（kuaimai_print.py）

cancelled = 「可发」被撤回时取消掉的 pending 任务（cancel_pending_by_code）：
  只取消**还没开打**的（pending）；正在打/已打完/失败的一律不动（不打断出纸、不涉重打）。
  取消后 pc 端不再认领 → 撤回的那条不会出纸。

账号映射：print_clients.json  {"admin": "pc1", "账号B": "pc2", "default": "pc1"}

★ 语义边界（用户口径）：本模块**只**写 print_jobs（任务队列），
  **绝不**碰 scan_record.printed —— 「已打」是人工确认出纸的标记，
  建任务 / 认领 / 回写结果都不许改它（见 kuaimai_scan.set_printed 的约束）。
"""
import json
import os
import re
import sqlite3
import threading
import time
from datetime import datetime

CLAIM_TIMEOUT = 300        # 认领后多久没回写算超时（秒）
MAX_TRIES = 3
DUP_WINDOW = 60            # 同编码去重窗口（秒）：队列里已有未完成、或窗口内刚打完 → 不再建新任务

DDL = """
CREATE TABLE IF NOT EXISTS print_jobs(
  job_id INTEGER PRIMARY KEY AUTOINCREMENT,
  code TEXT NOT NULL,
  qty INTEGER NOT NULL DEFAULT 0,
  who TEXT DEFAULT '',
  target_client TEXT DEFAULT '',
  status TEXT NOT NULL DEFAULT 'pending',
  claimed_by TEXT DEFAULT '',
  claim_ts INTEGER DEFAULT 0,
  done_ts INTEGER DEFAULT 0,
  tries INTEGER DEFAULT 0,
  next_try_ts INTEGER DEFAULT 0,
  out_sid TEXT DEFAULT '',
  last_msg TEXT DEFAULT '',
  created_at TEXT DEFAULT '',
  picked_sids TEXT DEFAULT ''
);
CREATE INDEX IF NOT EXISTS idx_print_jobs_state ON print_jobs(status, target_client);
-- 跨机共享的「已打订单」（防两台电脑把同一单各打一遍，2026-09-23）
CREATE TABLE IF NOT EXISTS printed_sids(
  sid TEXT PRIMARY KEY,
  out_sid TEXT DEFAULT '',
  client TEXT DEFAULT '',
  ts INTEGER DEFAULT 0
);
"""


def connect(path):
    c = sqlite3.connect(path, timeout=30, check_same_thread=False)
    c.row_factory = sqlite3.Row
    init(c)
    return c


def init(conn):
    conn.executescript(DDL)
    try:                                    # 老库迁移：补 retry 相关列
        conn.execute("ALTER TABLE print_jobs ADD COLUMN next_try_ts INTEGER DEFAULT 0")
    except Exception:
        pass
    for _col, _ddl in (("picked_sids", "TEXT DEFAULT ''"),):   # 本轮任务首次挑中的 sid（防重试另挑新单）
        try:
            have = [r[1] for r in conn.execute("PRAGMA table_info(print_jobs)")]
            if _col not in have:
                conn.execute("ALTER TABLE print_jobs ADD COLUMN %s %s" % (_col, _ddl))
        except Exception:
            pass
    conn.commit()


def add_job(conn, code, qty, who="", target_client="", msg=""):
    """提交一个打印任务（主端收到网页提交时调用）。

    只写 print_jobs；**不**碰 scan_record.printed（建任务 ≠ 已打）。
    """
    init(conn)
    cur = conn.execute(
        "INSERT INTO print_jobs(code,qty,who,target_client,status,last_msg,created_at) "
        "VALUES(?,?,?,?,'pending',?,?)",
        (str(code), int(qty), str(who), str(target_client), str(msg)[:200],
         datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    conn.commit()
    return cur.lastrowid


def dup_reason(conn, code, window_secs=None):
    """这条提交该不该被当作「重复」挡下；算重复就返回给人看的说明，否则返回 ''。

    用户口径（2026-09-23）：**同一编码短时间内被提交多次**会各建一个任务、各打一遍
    （实测 9681-燕麦色S ×5 提交 3 次 → #16/#17/#18 各打 5 张 = 15 张）。判定两条：
      1) 同编码**已有未完成任务**（pending/claimed/printing）→ 队列里还没打完，别再加一个；
      2) 同编码**窗口内刚打完**（done 且 done_ts 在窗口内）→ 大概率是误触/重试，别又打一遍。
    窗口内的追加打印需求会被挡（用户已知并选择这个取舍）；确要追加用 force=True 绕过。

    调用方必须先 init(conn)；本函数不做 DDL（要在事务里跑）。
    """
    c = str(code or "").strip()
    if not c:
        return ""
    w = DUP_WINDOW if window_secs is None else int(window_secs)
    now = int(time.time())
    r = conn.execute("SELECT job_id,status FROM print_jobs "
                     "WHERE code=? AND status IN ('pending','claimed','printing') "
                     "ORDER BY job_id LIMIT 1", (c,)).fetchone()
    if r:
        return "该编码已有未完成任务 #%s（%s）" % (r["job_id"], r["status"])
    r = conn.execute("SELECT job_id,done_ts FROM print_jobs "
                     "WHERE code=? AND status='done' AND done_ts>=? "
                     "ORDER BY done_ts DESC LIMIT 1", (c, now - w)).fetchone()
    if r:
        return "该编码 %d 秒内刚打完（任务 #%s）" % (now - int(r["done_ts"] or now), r["job_id"])
    return ""


def add_job_checked(conn, code, qty, who="", target_client="", msg="",
                    window_secs=None, force=False):
    """建任务 + 去重（查与插在同一把 BEGIN IMMEDIATE 里，防并发双建）。

    返回 (job_id, reason)：reason == '' 表示**已建**（job_id > 0）；
    否则 job_id == 0、reason 是「为什么没建」（直接显示给网页/写日志）。
    force=True 时跳过去重（人工确认要追加时用）。
    """
    init(conn)
    c = str(code or "").strip()
    old_level = conn.isolation_level
    conn.isolation_level = None                      # 手动事务
    try:
        conn.execute("BEGIN IMMEDIATE")
        why = "" if force else dup_reason(conn, c, window_secs)
        if why:
            conn.execute("COMMIT")
            return 0, why
        cur = conn.execute(
            "INSERT INTO print_jobs(code,qty,who,target_client,status,last_msg,created_at) "
            "VALUES(?,?,?,?,'pending',?,?)",
            (c, int(qty), str(who), str(target_client), str(msg)[:200],
             datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.execute("COMMIT")
        return cur.lastrowid, ""
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        conn.isolation_level = old_level


def _parse_sids(raw):
    """把任务里存的 picked_sids（JSON 数组文本）解析成 list；坏值当空。"""
    try:
        v = json.loads(raw or "[]")
        return [str(s) for s in v if s] if isinstance(v, list) else []
    except Exception:
        return []


def claim(conn, client, limit=1):
    """原子认领：属于该客户端（或未指派）的 pending 任务。返回 [{'job_id','code','qty','who'}]。

    只改 print_jobs.status；**不**碰 scan_record.printed（认领 ≠ 已打）。
    """
    init(conn)
    now = int(time.time())
    old_level = conn.isolation_level
    conn.isolation_level = None                      # 手动事务
    try:
        conn.execute("BEGIN IMMEDIATE")
        rows = conn.execute(
            # 只认「明确派给本机」的任务：空串 = 不自动打（旧实现把空串当「任意」→
            # 用户设了不自动打仍被打单，见 client_for 的语义说明）
            "SELECT job_id, code, qty, who, picked_sids FROM print_jobs "
            "WHERE status='pending' AND next_try_ts<=? AND target_client=? "
            "ORDER BY job_id LIMIT ?", (now, str(client), int(limit))).fetchall()
        got = []
        for r in rows:
            cur = conn.execute(
                "UPDATE print_jobs SET status='claimed', claimed_by=?, claim_ts=? "
                "WHERE job_id=? AND status='pending'", (str(client), now, r["job_id"]))
            if cur.rowcount == 1:                    # 只有真抢到才算
                got.append({"job_id": r["job_id"], "code": r["code"],
                            "qty": r["qty"], "who": r["who"],
                            "picked_sids": _parse_sids(r["picked_sids"])})
        conn.execute("COMMIT")
        return got
    except Exception:
        try:
            conn.execute("ROLLBACK")
        except Exception:
            pass
        raise
    finally:
        conn.isolation_level = old_level


BACKOFF = (60, 180, 600)          # 失败重试退避（秒）：第 1/2/3 次


def report(conn, job_id, client, ok, msg="", out_sid="", picked_sids=None):
    """回写结果：成功→done；失败→**回 pending 并退避重试**（tries 超限才判 failed）。

    picked_sids：本次挑中的 sid（与任务里已存的一起并入）——
    **重试只补这批**，绝不再另挑新单（防重试把用户没要的单也打了，2026-09-23）。

    只改 print_jobs；**不**碰 scan_record.printed（回写任务 ≠ 已打；已打由人工点）。
    """
    init(conn)
    now = int(time.time())
    row = conn.execute("SELECT picked_sids FROM print_jobs WHERE job_id=?",
                       (int(job_id),)).fetchone()
    old = _parse_sids(row["picked_sids"]) if row else []
    merged = list(dict.fromkeys(old + [str(s) for s in (picked_sids or []) if s]))
    if ok:
        conn.execute("UPDATE print_jobs SET status='done', done_ts=?, out_sid=?, last_msg=?, "
                     "picked_sids=? WHERE job_id=? AND claimed_by=?",
                     (now, str(out_sid), str(msg)[:300], json.dumps(merged),
                      int(job_id), str(client)))
        conn.commit()
        return "done"
    r = conn.execute("SELECT tries FROM print_jobs WHERE job_id=?", (int(job_id),)).fetchone()
    tries = int((r["tries"] if r else 0) or 0) + 1
    if tries >= MAX_TRIES:
        conn.execute("UPDATE print_jobs SET status='failed', tries=?, done_ts=?, last_msg=?, "
                     "picked_sids=? WHERE job_id=? AND claimed_by=?",
                     (tries, now, ("重试 %d 次仍失败：%s" % (tries, str(msg)[:200])),
                      json.dumps(merged), int(job_id), str(client)))
        conn.commit()
        return "failed"
    wait = BACKOFF[min(tries, len(BACKOFF)) - 1]
    conn.execute("UPDATE print_jobs SET status='pending', claimed_by='', claim_ts=0, tries=?, "
                 "next_try_ts=?, last_msg=?, picked_sids=? WHERE job_id=?",
                 (tries, now + wait,
                  ("第 %d 次失败，%d 秒后重试：%s" % (tries, wait, str(msg)[:160])),
                  json.dumps(merged), int(job_id)))
    conn.commit()
    return "pending"


def cancel_pending_by_code(conn, code, who=""):
    """撤回「可发」时调用：把该编码**还没开打**的 pending 任务取消掉。返回取消条数。

    只动 pending：
      · claimed / printing（正在打）**不动** —— 不打断正在出的纸；
      · done（已打完）**不动** —— 已出纸的更不碰，也就不涉重复打印；
      · failed 不动。
    取消后 status='cancelled' → 不在 claim() 的 `status='pending'` 里 → pc 端不再认领
    → 撤回的那条真的不会出纸。也不入 dup_reason 的去重窗口（撤回后可重新提交）。
    """
    init(conn)
    c = str(code or "").strip()
    if not c:
        return 0
    msg = "已取消（可发撤回）" + (("，操作人 %s" % str(who)) if who else "")
    n = conn.execute("UPDATE print_jobs SET status='cancelled', last_msg=? "
                     "WHERE code=? AND status='pending'", (msg[:200], c)).rowcount
    conn.commit()
    return int(n or 0)


def delete_job(conn, job_id):
    """删掉一条打单任务（主端权威库）。返回受影响行数（0=没这条）。"""
    init(conn)
    try:
        jid = int(job_id)
    except Exception:
        return 0
    cur = conn.execute("DELETE FROM print_jobs WHERE job_id=?", (jid,))
    conn.commit()
    return cur.rowcount


def delete_jobs(conn, ids=None, status=None):
    """批量删任务：按 id 列表 或 按状态（如清空 failed）。返回删除条数。

    两个都没给 → 返回 0（绝不整表清空，防手滑）；给了就按给了的删，可以同时用。
    """
    init(conn)
    clean = []
    for x in (ids or []):
        try:
            clean.append(int(x))
        except Exception:
            pass
    st = str(status or "").strip()
    if not clean and not st:
        return 0
    n = 0
    if clean:
        marks = ",".join("?" * len(clean))
        n += conn.execute("DELETE FROM print_jobs WHERE job_id IN (%s)" % marks,
                          tuple(clean)).rowcount
    if st:
        n += conn.execute("DELETE FROM print_jobs WHERE status=?", (st,)).rowcount
    conn.commit()
    return n


def reclaim(conn, timeout=CLAIM_TIMEOUT, max_tries=MAX_TRIES):
    """超时未回写的认领 → 回 pending（tries+1）；重试超限 → failed。返回 (回收数, 判死数)。"""
    init(conn)
    cut = int(time.time()) - int(timeout)
    n1 = conn.execute(
        "UPDATE print_jobs SET status='pending', claimed_by='', claim_ts=0, tries=tries+1 "
        "WHERE status IN ('claimed','printing') AND claim_ts>0 AND claim_ts<? AND tries<?",
        (cut, int(max_tries))).rowcount
    n2 = conn.execute(
        "UPDATE print_jobs SET status='failed', last_msg='认领超时重试过多' "
        "WHERE status IN ('claimed','printing') AND claim_ts>0 AND claim_ts<? AND tries>=?",
        (cut, int(max_tries))).rowcount
    conn.commit()
    return n1, n2


def heartbeat(conn, job_id, client):
    """打单期间的心跳：刷新 claim_ts，防止长任务被 reclaim() 超时回收 → 被别的电脑重领重打。

    只对「本机正在打的那条」生效（WHERE claimed_by=?），不影响别人。
    """
    init(conn)
    try:
        cur = conn.execute(
            "UPDATE print_jobs SET claim_ts=? WHERE job_id=? AND claimed_by=? "
            "AND status IN ('claimed','printing')",
            (int(time.time()), int(job_id), str(client)))
        conn.commit()
        return cur.rowcount
    except Exception:
        return 0


def mark_printed(conn, sids, out_sids=None, client="", keep_days=30):
    """把「已出纸的订单」记进**主端权威**共享表（跨机防重）。返回写入条数。

    与 scan_record.printed 无关：那是人工确认标记，这是自动链路自己的去重账本。
    """
    init(conn)
    now = int(time.time())
    n = 0
    for s in (sids or []):
        s = str(s or "").strip()
        if not s:
            continue
        out = str((out_sids or {}).get(s) or "")
        conn.execute("INSERT OR REPLACE INTO printed_sids(sid,out_sid,client,ts) VALUES(?,?,?,?)",
                     (s, out, str(client), now))
        n += 1
    if n:
        cut = now - int(keep_days) * 86400
        conn.execute("DELETE FROM printed_sids WHERE ts < ?", (cut,))
    conn.commit()
    return n


def printed_sids(conn, keep_days=30):
    """主端权威的「已打订单」表：{sid: {outSid}}（供各端打单前同步，跨机防重）。"""
    init(conn)
    cut = int(time.time()) - int(keep_days) * 86400
    out = {}
    for r in conn.execute("SELECT sid, out_sid FROM printed_sids WHERE ts >= ?", (cut,)):
        out[str(r["sid"])] = {"outSid": str(r["out_sid"] or "")}
    return out


def live_view(conn):
    """看板用直白视图：正在打印 / 排队中（**只含未完成**）/ 打印完成 / 最近失败。

    ★ 分区口径（用户要求）：`queue` **只含 pending**（未完成），打完的进 `done`；
      不再让「已打印」混在排队里（面板/网页都按这个分区渲染）。
    """
    init(conn)
    now = int(time.time())
    printing = []
    for r in conn.execute(
            "SELECT job_id, code, qty, who, claimed_by, claim_ts, tries FROM print_jobs "
            "WHERE status IN ('claimed','printing') ORDER BY claim_ts"):
        d = dict(r)
        d["elapsed"] = max(0, now - int(d.get("claim_ts") or 0))
        d["who"] = d.get("who") or "-"
        printing.append(d)
    queue = []
    for r in conn.execute(
            "SELECT job_id, code, qty, who, target_client, tries, next_try_ts, created_at, last_msg "
            "FROM print_jobs WHERE status='pending' ORDER BY next_try_ts, job_id"):
        d = dict(r)
        d["client"] = d.get("target_client") or "未指派(不自动打)"
        d["retrying"] = bool(d.get("tries"))
        try:
            d["wait"] = max(0, now - int(time.mktime(time.strptime(str(d.get("created_at") or ""),
                                                                 "%Y-%m-%d %H:%M:%S"))))
        except Exception:
            d["wait"] = 0
        queue.append(d)
    done = []
    for r in conn.execute(
            "SELECT job_id, code, qty, who, claimed_by, done_ts, out_sid, last_msg "
            "FROM print_jobs WHERE status='done' ORDER BY done_ts DESC, job_id DESC LIMIT 50"):
        d = dict(r)
        d["client"] = d.get("claimed_by") or "-"
        done.append(d)
    failed = []
    for r in conn.execute(
            "SELECT job_id, code, qty, who, tries, last_msg, done_ts FROM print_jobs "
            "WHERE status='failed' ORDER BY job_id DESC LIMIT 10"):
        failed.append(dict(r))
    return {"printing": printing, "queue": queue, "done": done, "failed": failed,
            "counts": {"printing": len(printing), "queue": len(queue),
                       "done": len(done), "failed": len(failed)}}


def stats(conn):
    init(conn)
    out = {}
    for r in conn.execute("SELECT status, COUNT(*) AS n FROM print_jobs GROUP BY status"):
        out[r["status"]] = r["n"]
    per = {}
    for r in conn.execute("SELECT claimed_by, status, COUNT(*) AS n FROM print_jobs "
                          "WHERE claimed_by<>'' GROUP BY claimed_by, status"):
        per.setdefault(r["claimed_by"], {})[r["status"]] = r["n"]
    out["by_client"] = per
    recent = []
    for r in conn.execute(
            "SELECT job_id, code, qty, who, target_client, status, claimed_by, tries, "
            "out_sid, last_msg, created_at FROM print_jobs ORDER BY job_id DESC LIMIT 20"):
        recent.append(dict(r))
    out["recent"] = recent
    out["live"] = live_view(conn)
    return out


def load_client_map(path):
    """账号 → 客户端 映射；{"admin":"pc1","账号B":"pc2","default":"pc1"}"""
    try:
        with open(path, encoding="utf-8") as f:
            d = json.load(f) or {}
        return d if isinstance(d, dict) else {}
    except Exception:
        return {}


CLIENT_ID_RE = re.compile(r"^pc\d+$")      # 有效电脑名：pc1 / pc2 / pc3 …


def valid_client(v):
    """只认**有效电脑名**；其余（含「不自动打」/空/垃圾）一律当 '' = 不自动打。"""
    v = str(v or "").strip()
    return v if CLIENT_ID_RE.match(v) else ""


def client_for(mapd, who):
    """按映射决定这个来源账号该派给哪个客户端。

    ★ 返回 '' = **不自动打**：不派发 → 网页点「可发」也**不推送**、不建任务、
      任何电脑都不会认领（claim 只认明确派给本机的任务）。

    判定顺序（2026-09-23 修正）：
      1) 该账号**明确列出**（含宽松匹配）→ 用它；值不是有效电脑名（「不自动打」/空）
         **直接 = 不自动打，不再落回 default** —— 用户要求：设了不自动打就绝不推送。
      2) 都没命中 → default；default 无效/缺失 = 不自动打。

    旧实现的两处漏洞（用户报「设了不自动打还是打单出来」）：
      · '' 被当「谁都能领」→ 全设不自动打时文件是空表 → 空串任务被任意电脑认领并打单；
      · 「不自动打」的账号没写进文件 → 取用时落回 default 那台电脑 → 照样推送。
    """
    mapd = mapd or {}
    w = str(who or "").strip()
    if w and w in mapd:
        return valid_client(mapd[w])
    for k, v in mapd.items():                        # 宽松匹配（网页账号常带前缀/后缀）
        if k and k != "default" and (k in w or (w and w in k)):
            return valid_client(v)
    return valid_client(mapd.get("default"))


def selftest():
    """并发抢单 + 超时回收 + 回写 + 映射 自测（临时库，不碰真实数据）。"""
    import tempfile
    ok = []
    path = os.path.join(tempfile.gettempdir(), "km_jobs_test.db")
    if os.path.exists(path):
        os.remove(path)
    conn = connect(path)
    jid = add_job(conn, "7107-黑色M", 3, who="admin", target_client="pc1")
    res = {}

    def worker(name):
        c = sqlite3.connect(path, timeout=30, check_same_thread=False)
        c.row_factory = sqlite3.Row
        res[name] = claim(c, name, limit=1)
        c.close()

    ts = [threading.Thread(target=worker, args=(n,)) for n in ("pc1", "pc2")]
    [t.start() for t in ts]
    [t.join() for t in ts]
    winners = [n for n, r in res.items() if r]
    ok.append(("并发抢单只成功一台", len(winners) == 1, "抢到的是 %s" % winners))
    win = winners[0] if winners else ""
    if win:
        report(conn, jid, win, True, "打印成功", out_sid="76982400000001")
        st = conn.execute("SELECT status, out_sid FROM print_jobs WHERE job_id=?", (jid,)).fetchone()
        ok.append(("回写成功状态", st["status"] == "done" and bool(st["out_sid"]), str(dict(st))))

    j2 = add_job(conn, "7107-黑色S", 2, who="账号B", target_client="pc2")
    conn.execute("UPDATE print_jobs SET status='claimed', claimed_by='pc2', claim_ts=? WHERE job_id=?",
                 (int(time.time()) - 999, j2))
    conn.commit()
    n1, n2 = reclaim(conn, timeout=300)
    st2 = conn.execute("SELECT status, tries FROM print_jobs WHERE job_id=?", (j2,)).fetchone()
    ok.append(("超时回收回 pending", st2["status"] == "pending" and st2["tries"] == 1,
               "回收=%d 判死=%d 现在=%s" % (n1, n2, dict(st2))))
    got2 = claim(conn, "pc2", limit=1)
    ok.append(("回收后能再被领到", len(got2) == 1, str(got2)))

    # 失败重试 + 退避
    j3 = add_job(conn, "7107-白色L", 1, who="admin", target_client="pc1")
    c3 = sqlite3.connect(path, timeout=30, check_same_thread=False)
    c3.row_factory = sqlite3.Row
    got3 = claim(c3, "pc1", limit=5)
    ok.append(("能领到新任务", any(g["job_id"] == j3 for g in got3), str(got3)))
    r = report(conn, j3, "pc1", False, "打印机离线")
    row = conn.execute("SELECT status, tries, next_try_ts FROM print_jobs WHERE job_id=?", (j3,)).fetchone()
    ok.append(("失败→回 pending 并退避", r == "pending" and row["status"] == "pending"
               and row["tries"] == 1 and row["next_try_ts"] > int(time.time()), str(dict(row))))
    got4 = claim(c3, "pc1", limit=5)
    ok.append(("退避期内不会被立刻重领", all(g["job_id"] != j3 for g in got4), str(got4)))
    conn.execute("UPDATE print_jobs SET next_try_ts=0 WHERE job_id=?", (j3,))
    conn.commit()
    for _ in range(2):                      # 第 2、3 次：等退避到期 → 重新认领 → 再失败
        claim(c3, "pc1", limit=5)
        report(conn, j3, "pc1", False, "再次失败")
        conn.execute("UPDATE print_jobs SET next_try_ts=0 WHERE job_id=?", (j3,))
        conn.commit()
    row2 = conn.execute("SELECT status, tries FROM print_jobs WHERE job_id=?", (j3,)).fetchone()
    ok.append(("重试超限→failed", row2["status"] == "failed" and row2["tries"] >= 3, str(dict(row2))))
    st = stats(conn)
    ok.append(("看板含队列明细", bool(st.get("recent")) and "by_client" in st,
               "pending=%s done=%s failed=%s recent=%d" % (st.get("pending"), st.get("done"),
                                                           st.get("failed"), len(st.get("recent") or []))))
    c3.close()

    # 队列分区：queue 只含 pending；done 只含 done；counts 对得上
    lv = live_view(conn)
    qst = set(str(x.get("status") or "pending") for x in lv["queue"])
    ok.append(("live_view.queue 只含 pending", qst <= {"pending"},
               "queue 里的状态=%s" % sorted(qst)))
    n_db_done = conn.execute("SELECT COUNT(*) AS n FROM print_jobs "
                             "WHERE status='done'").fetchone()["n"]
    ok.append(("live_view.done 条数 == 库里 done 条数",
               len(lv["done"]) == min(50, n_db_done) and len(lv["done"]) > 0,
               "库里 done=%d，done 列表=%d" % (n_db_done, len(lv["done"]))))
    ok.append(("live_view.done 含 job_id/code/qty/who/claimed_by/done_ts/out_sid/last_msg",
               all((k in (lv["done"][0] if lv["done"] else {})) for k in
                   ("job_id", "code", "qty", "who", "claimed_by", "done_ts", "out_sid", "last_msg")),
               str(sorted((lv["done"][0] if lv["done"] else {}).keys()))))
    ok.append(("live_view.done 按 done_ts 倒序（最新在前）",
               [d["done_ts"] for d in lv["done"]] == sorted([d["done_ts"] for d in lv["done"]],
                                                             reverse=True),
               str([d["done_ts"] for d in lv["done"]])))
    ok.append(("counts 含 queue/done/failed 且与列表长度一致",
               lv["counts"].get("queue") == len(lv["queue"])
               and lv["counts"].get("done") == len(lv["done"])
               and lv["counts"].get("failed") == len(lv["failed"]),
               str(lv["counts"])))
    # 未完成（claimed）绝不出现在 queue 或 done 里
    jc = add_job(conn, "7107-分区CLAIMED", 1, who="admin", target_client="pc1")
    conn.execute("UPDATE print_jobs SET status='claimed', claimed_by='pc1', claim_ts=? "
                 "WHERE job_id=?", (int(time.time()), jc))
    conn.commit()
    lv2 = live_view(conn)
    ok.append(("claimed 既不在 queue 也不在 done",
               all(x.get("job_id") != jc for x in lv2["queue"])
               and all(x.get("job_id") != jc for x in lv2["done"])
               and any(x.get("job_id") == jc for x in lv2["printing"]),
               "printing=%s queue=%s done=%s" % ([x.get("job_id") for x in lv2["printing"]],
                                                 [x.get("job_id") for x in lv2["queue"]],
                                                 [x.get("job_id") for x in lv2["done"]])))

    # 删除任务：临时库造 3 条（1 pending / 1 failed / 1 claimed）
    jd1 = add_job(conn, "7107-删除A", 1, who="admin", target_client="pc1")
    jd2 = add_job(conn, "7107-删除B", 2, who="admin", target_client="pc1")
    jd3 = add_job(conn, "7107-删除C", 3, who="admin", target_client="pc1")
    conn.execute("UPDATE print_jobs SET status='failed' WHERE job_id=?", (jd2,))
    conn.execute("UPDATE print_jobs SET status='claimed', claimed_by='pc1', claim_ts=? "
                 "WHERE job_id=?", (int(time.time()), jd3))
    conn.commit()
    n_jd = delete_job(conn, jd1)
    n_failed_before = conn.execute("SELECT COUNT(*) AS n FROM print_jobs "
                                   "WHERE status='failed'").fetchone()["n"]
    n_st = delete_jobs(conn, status="failed")
    left = [r["job_id"] for r in conn.execute(
        "SELECT job_id FROM print_jobs WHERE job_id IN (?,?,?) ORDER BY job_id", (jd1, jd2, jd3))]
    n_failed_after = conn.execute("SELECT COUNT(*) AS n FROM print_jobs "
                                  "WHERE status='failed'").fetchone()["n"]
    ok.append(("delete_job 删掉指定那条", n_jd == 1, "rowcount=%d" % n_jd))
    ok.append(("delete_jobs(status=failed) 把 failed 清空",
               n_st == n_failed_before and n_failed_after == 0,
               "删除前 failed=%d，deleted=%d，删除后 failed=%d"
               % (n_failed_before, n_st, n_failed_after)))
    ok.append(("剩 1 条（claimed 那条不动）", left == [jd3], "left=%s 期望=[%s]" % (left, jd3)))
    ok.append(("什么都不给时删 0 条", delete_jobs(conn) == 0, "防整表清空"))

    # 撤回「可发」取消 pending 任务：只动 pending，其它状态一律不动
    jx1 = add_job(conn, "7107-撤回A", 3, who="admin", target_client="pc1")
    jx2 = add_job(conn, "7107-撤回A", 5, who="admin", target_client="pc1")
    jx3 = add_job(conn, "7107-撤回A", 1, who="admin", target_client="pc1")
    jx_other = add_job(conn, "7107-撤回B", 2, who="admin", target_client="pc1")
    conn.execute("UPDATE print_jobs SET status='done', done_ts=? WHERE job_id=?",
                 (int(time.time()), jx3))
    conn.commit()
    n_cx = cancel_pending_by_code(conn, "7107-撤回A", who="admin")

    def _st(j):
        return str(conn.execute("SELECT status FROM print_jobs WHERE job_id=?",
                                (j,)).fetchone()["status"])

    ok.append(("cancel_pending_by_code 只取消该编码的 pending", n_cx == 2,
               "返回 %d 期望 2" % n_cx))
    ok.append(("取消后 pending→cancelled、done 不动、别的编码不动",
               _st(jx1) == "cancelled" and _st(jx2) == "cancelled"
               and _st(jx3) == "done" and _st(jx_other) == "pending",
               "A1=%s A2=%s done=%s B=%s" % (_st(jx1), _st(jx2), _st(jx3), _st(jx_other))))
    ok.append(("被取消的任务不再被 claim 认领",
               all(g["job_id"] not in (jx1, jx2) for g in claim(conn, "pc1", limit=20)),
               "claim 未取到已取消的任务"))
    # 干净编码：取消后可重新提交（不进 dup 窗口）
    jx_clean = add_job(conn, "7107-撤回C", 4, who="admin", target_client="pc1")
    cancel_pending_by_code(conn, "7107-撤回C", who="admin")
    ok.append(("撤回后可重新提交同一编码", dup_reason(conn, "7107-撤回C") == "",
               "dup=%r" % dup_reason(conn, "7107-撤回C")))
    ok.append(("cancelled 不出现在看板 queue",
               all(x.get("job_id") != jx1 for x in live_view(conn)["queue"]),
               "queue 无已取消任务"))

    mp = {"admin": "pc1", "账号B": "pc2", "default": "pc1"}
    ok.append(("账号映射", client_for(mp, "admin") == "pc1" and client_for(mp, "账号B") == "pc2"
               and client_for(mp, "其他") == "pc1",
               "%s / %s / %s" % (client_for(mp, "admin"), client_for(mp, "账号B"), client_for(mp, "其他"))))
    conn.close()
    bad = [x for x in ok if not x[1]]
    for name, good, info in ok:
        print("%s %s  (%s)" % ("OK  " if good else "FAIL", name, info))
    print("RESULT:", "ALL OK" if not bad else "%d PROBLEM(S)" % len(bad))
    return 0 if not bad else 1


if __name__ == "__main__":
    import sys
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
    raise SystemExit(selftest())
