# -*- coding: utf-8 -*-
r"""网页提交 → 自动打单 监听器。

网页/手机点「可发」并输入数量 → 写一条扫码记录（print_num = 输入的数量）
→ 本监听发现**新记录**就自动按该数量打单（走已验证的打单链路 + 本机去重记忆）。

两种跑法：
  · **推荐**：主程序启动后自动用 daemon 线程跑 `watch(...)`（读同一个库与开关文件，不再单独开进程）
  · 开发/单独调试：`python desktop/auto_print_watcher.py [--from <id>] [--cooldown 60]`

去重规则：
  1) 本机去重记忆：打过的**订单**永不重复打（防 ERP 打印次数滞后）
  2) ERP printCount：已打印过的跳过（见 kuaimai_print.pick_orders）
  3) 记录标了「已打」的跳过；电脑端自己扫的（who 以「桌面版」开头）不自动打
  4) **[仅本地模式 watch()]** 同一 SKU 冷却期内（默认 60 秒）只打一次。
     **认领模式 watch_claims() 不冷却**：队列里每个 job 都是用户明确提交的一次任务，
     互相不该冷却；失败只由同一个 job 的 tries 退避（60/180/600 秒，3 次后 failed）。
  5) **0 单绝不判 done**：查单失败 → report(ok=False,"查单失败：…")；确实挑不到 →
     report(ok=False,"挑不到可打单（可能已打完）")；两者都回队列退避重试。

停止：主程序退出即停（daemon）；单独跑时结束进程。
日志：`BASE_DIR\auto_print.log`（安装版 = %LOCALAPPDATA%\KuaimaiScan\auto_print.log）
"""
import io
import os
import sqlite3
import sys
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
import kuaimai_print as K  # noqa


def _pick_base_dir(preferred):
    """数据目录：与主程序/kuaimai_print 同一规则（冻结时 exe 旁优先，不可写回落 LOCALAPPDATA）。"""
    try:
        os.makedirs(preferred, exist_ok=True)
        probe = os.path.join(preferred, ".km_write_test")
        with open(probe, "w", encoding="utf-8") as f:
            f.write("ok")
        os.remove(probe)
        return preferred
    except Exception:
        alt = os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"), "KuaimaiScan")
        try:
            os.makedirs(alt, exist_ok=True)
        except Exception:
            pass
        return alt


if getattr(sys, "frozen", False):
    BASE_DIR = _pick_base_dir(os.path.dirname(os.path.abspath(sys.executable)))
else:
    BASE_DIR = _pick_base_dir(os.path.dirname(os.path.abspath(__file__)))

_LOCAL = os.path.join(os.environ.get("LOCALAPPDATA", ""), "KuaimaiScan")


def default_db():
    """扫码库：就是 `BASE_DIR\\scan_log.db`（与主程序 DB_FILE 同一处）。

    冻结时**无条件**用 BASE_DIR（exe 旁 / 安装目录），不做「谁存在用谁」的挑选——
    否则便携场景下会误用旧安装遗留的 %LOCALAPPDATA%\\KuaimaiScan 库。
    源码调试时本目录没有、而 %LOCALAPPDATA%\\KuaimaiScan 有，才用后者（方便单跑）。
    """
    p = os.path.join(BASE_DIR, "scan_log.db")
    if getattr(sys, "frozen", False) or os.path.isfile(p):
        return p
    alt = os.path.join(_LOCAL, "scan_log.db")
    return alt if os.path.isfile(alt) else p


DB = default_db()
LOG = os.path.join(BASE_DIR, "auto_print.log")
PAUSE = os.path.join(_LOCAL, "auto_print_pause.flag")  # 存在=暂停（与主程序勾选框同源）
POLL = 3.0
_DB_PATH = DB          # 当前监听的库（主程序内嵌时由 watch() 覆盖）
_LOG_PATH = LOG         # 当前日志文件（同上）


def log(s):
    line = "%s  %s" % (time.strftime("%m-%d %H:%M:%S"), s)
    try:
        print(line, flush=True)
    except Exception:
        pass
    try:
        with io.open(_LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def _conn(db=None):
    c = sqlite3.connect(db or _DB_PATH, timeout=20)
    c.row_factory = sqlite3.Row
    return c


def max_id(db=None):
    try:
        c = _conn(db)
        r = c.execute("select max(id) from scan_record").fetchone()
        c.close()
        return int(r[0] or 0)
    except Exception:
        return 0


def new_rows(after_id, db=None):
    try:
        c = _conn(db)
        rs = c.execute("select id, scan_time, barcode, print_num, printed, who from scan_record "
                       "where id > ? order by id", (after_id,)).fetchall()
        c.close()
        return [dict(r) for r in rs]
    except Exception as e:
        log("读库失败: %s" % str(e)[:80])
        return []


def watch(stop_event=None, db=None, log_path=None, pause_path=None, poll=POLL,
          cooldown=60.0, start=0, quiet=False):
    """自动打单监听循环（可被主程序放进 daemon 线程，也可由 main() 单独跑）。

    stop_event 置位即退出（主程序关窗时用）；db / log_path / pause_path 由主程序传入，
    保证与主程序读的是**同一个库、同一个开关文件**（"网页提交后自动打单"勾选框同源）。
    """
    global _DB_PATH, _LOG_PATH
    if db:
        _DB_PATH = db
    if log_path:
        _LOG_PATH = log_path
    pause = pause_path or PAUSE
    last = int(start or 0) or max_id(_DB_PATH)
    recent = {}          # sku → 上次自动打单时间（冷却用）
    paused = False
    if not quiet:
        log("=== 自动打单监听启动（库 %s，从 id %d 起，%.0f 秒轮一次，同 SKU 冷却 %.0f 秒）==="
            % (_DB_PATH, last, poll, cooldown))
    while not (stop_event is not None and stop_event.is_set()):
        for r in new_rows(last, _DB_PATH):
            last = max(last, int(r["id"]))
            if os.path.isfile(pause):                  # 总开关：暂停文件存在则只消费不打印
                if not paused:
                    paused = True
                    log("总开关：已暂停（删掉 %s 即恢复）" % os.path.basename(pause))
                continue
            if paused:
                paused = False
                log("总开关：已恢复自动打单")
            who = str(r.get("who") or "")
            code = str(r.get("barcode") or "").strip()
            try:
                qty = int(float(r.get("print_num") or 0))
            except Exception:
                qty = 0
            if who.startswith("桌面版"):
                continue                                  # 电脑端自己扫的：不自动打
            if int(r.get("printed") or 0) == 1:
                log("跳过 id=%s %s：已标「已打」" % (r["id"], code))
                continue
            if not code or qty <= 0:
                continue
            gap = time.time() - recent.get(code, 0)
            if gap < cooldown:
                log("跳过 %s ×%s：同 SKU 冷却中（距上次 %.0f 秒 < %.0f 秒）"
                    % (code, qty, gap, cooldown))
                continue
            log("收到网页提交：%s ×%s（id=%s，%s）→ 自动打单" % (code, qty, r["id"], who))
            try:
                st, msg = K.ensure_browser()
                if st != "ok":
                    log("  浏览器未就绪：%s" % msg)
                    continue
                picked, skipped, logs = K.do_print(code, qty, dry_run=False)
                recent[code] = time.time()             # 记冷却时间
                log("  结果：%d 单；%s" % (len(picked or []),
                                          " | ".join(str(x)[:140] for x in (logs or []))))
            except BaseException as e:
                log("  打单异常：%s" % str(e)[:150])
        if stop_event is None:
            time.sleep(poll)
        else:
            stop_event.wait(poll)                      # 可中断等待：停服务时最多 0.2 秒退出
    log("=== 自动打单监听已停止 ===")


def _err_text(obj):
    """把接口错误变成一句短话（认领/回写失败时写日志用）。"""
    if isinstance(obj, dict):
        return str(obj.get("error") or obj.get("msg") or obj)[:200]
    return str(obj)[:200]


def _extract_out_sid(picked):
    """打过之后回读运单号：本机去重记忆里存了 sid → outSid（remember_printed）。"""
    try:
        mem = K.load_printed_memory()
    except Exception:
        return ""
    for o in (picked or []):
        try:
            sid = str((o or {}).get("sid") or "")
            s = str(((mem.get(sid) or {}).get("outSid")) or "").strip()
            if s:
                return s
        except Exception:
            continue
    return ""


def _job_verdict(picked, logs):
    """这次打单算不算成功 → (成功?, 说明)。失败的话主端会把任务退回队列退避重试。

    · picked 空 = **还不能判定**（返回 None）→ 交给 _classify_no_pick 再区分为
      「查单失败」还是「确实挑不到」；**绝不允许"没打却标 done"**；
    · logs 首行以「！！」开头 = 失败（do_print 的约定）；
    · 要打却没拿到任何运单号 / 打印结果: 失败 = 也算失败（不静默丢单）。
    """
    if not picked:
        return None, "本次没挑到单，待分类"
    first = str(logs[0]) if logs else ""
    if first.startswith("！！"):
        return False, (first[:200] or "打印失败")
    if any("没有可用运单号" in str(x) for x in (logs or [])):
        return False, "没取到运单号，未打印"
    for x in (logs or []):
        if str(x).startswith("打印结果: 失败"):
            return False, str(x)[:200]
    return True, "打印成功"


def _classify_no_pick(code):
    """0 单时分类：**查单失败** 还是 **确实挑不到** → 两种都判失败。

    两种都 report(ok=False) → 主端回队列退避重试，3 次后 failed（看板里能看到，不静默）。
    用 ERP 的**实时未打印队列**区分（do_print 在 0 单时无法自证是「查不到」还是「真没单」）：
      · 读队列报错        → 「查单失败：…」
      · 队列 0 条         → 「挑不到可打单（可能已打完）」
      · 队列有单却挑不到   → 被去重记忆/规则挡住，消息里带上条数（方便一眼看出"误记挡住"）
    """
    try:
        sids, n, err, complete, q_total = K.fetch_unprinted_sids(code)
    except BaseException as e:
        return False, "查单失败：%s" % str(e)[:120]
    if err:
        return False, "查单失败：%s" % str(err)[:120]
    # 队列条数用 ERP 的 total（翻页已读全时 n 与之相等；拿不到 total 才退而用 n）
    qcount = int(q_total if q_total is not None else (n or 0))
    if qcount <= 0:
        return False, "挑不到可打单（可能已打完）"
    try:
        pset = K._printed_set()
        blocked = sum(1 for s in (sids or set()) if str(s) in pset)
    except Exception:
        blocked = 0
    if blocked and blocked >= qcount:
        return False, "挑不到可打单（队列 %d 单全被本机去重记忆挡住）" % qcount
    return False, "挑不到可打单（队列 %d 单，均不符合「一单一件/同编码」）" % qcount


def _sync_shared_memory(api):
    """打单前把主端权威库的「已打订单」同步下来，合并进本机去重记忆（跨机防重）。

    跨机场景：两台电脑身份相同（或旧版空派单）时，同一单可能被两台各打一遍。
    同步后本机 pick_orders 的 _printed_set() 会跳过别台打过的单。
    """
    try:
        ok, res = api("/api/print/memory", "GET", timeout=20)
        if not ok or not isinstance(res, dict) or res.get("error"):
            return 0
        n = K.merge_printed_memory(res.get("sids") or {})
        if n:
            log("  跨机去重：同步了 %d 单（别台已打，本次不再打）" % n)
        return n
    except BaseException as e:
        log("  跨机去重同步失败（不影响打单）：%s" % str(e)[:120])
        return 0


def _report_printed(api, client, sids, out_sids=None):
    """把本次**确证已出纸**的 sid 报给主端权威库（供别的电脑同步，跨机防重）。"""
    sids = [s for s in (sids or []) if s]
    if not sids:
        return 0
    try:
        ok, res = api("/api/print/memory", "POST",
                      body={"client": client, "sids": sids, "out_sids": out_sids or {}}, timeout=20)
        if ok and isinstance(res, dict) and not res.get("error"):
            log("  跨机去重：已上报 %s 单（别台不会再打）" % (res.get("marked") or len(sids)))
            return int(res.get("marked") or 0)
        log("  跨机去重上报失败：%s" % _err_text(res))
    except BaseException as e:
        log("  跨机去重上报异常：%s" % str(e)[:120])
    return 0


class _Heartbeat(object):
    """打单期间每 60s 上报一次心跳（刷新 claim_ts），防止长任务被 reclaim() 超时回收
    → 被别的电脑重新认领后重打（2026-09-23）。"""

    def __init__(self, api, client, job_id, every=60.0):
        self.api, self.client, self.jid = api, client, job_id
        self.every = float(every)
        self._stop = threading.Event()
        self._t = None

    def __enter__(self):
        def loop():
            while not self._stop.wait(self.every):
                try:
                    self.api("/api/print/heartbeat", "POST",
                             body={"job_id": int(self.jid), "client": self.client}, timeout=15)
                except BaseException:
                    pass
        self._t = threading.Thread(target=loop, daemon=True)
        self._t.start()
        return self

    def __exit__(self, *a):
        self._stop.set()
        return False


def _report(api, client, job_id, ok, msg="", out_sid="", picked_sids=None):
    """回写结果；回写本身失败就写日志（任务在主端会超时回收，不会丢）。

    picked_sids：本次挑中的 sid → 主端存进任务，**重试只补这批**（防另挑新单重打）。
    """
    try:
        ok2, res = api("/api/print/report", "POST",
                       body={"job_id": int(job_id), "client": client, "ok": bool(ok),
                             "msg": str(msg)[:200], "out_sid": str(out_sid or ""),
                             "picked_sids": [str(s) for s in (picked_sids or []) if s]}, timeout=25)
        if not ok2 or (isinstance(res, dict) and res.get("error")):
            log("  回写失败（任务 #%s）：%s（主端超时回收后会重试）" % (job_id, _err_text(res)))
    except BaseException as e:
        log("  回写异常（任务 #%s）：%s（主端超时回收后会重试）" % (job_id, str(e)[:150]))


def _do_claim_one(api, client, job):
    """打一个已认领的任务：拿浏览器 → do_print → 成功/失败都回写。

    **认领模式不做「同 SKU 冷却」**：队列里的每个 job 都是用户**明确提交**的一次任务，
    互相不该冷却。去重只靠 ①订单级去重记忆(sid) ②ERP printCount ③同一 job 的 tries 退避。
    （老的「本地模式」watch() 仍保留同 SKU 冷却，见上面。）

    ★ 本函数**不**写 scan_record.printed：认领 / 打印 / 回写只影响 print_jobs 与
      去重记忆；「已打」是人工确认出纸后在扫码记录里自己点的（走 /api/scans/printed）。
    """
    jid = job.get("job_id")
    code = str(job.get("code") or "").strip()
    who = str(job.get("who") or "")
    try:
        qty = int(job.get("qty") or 0)
    except Exception:
        qty = 0
    if not code or qty <= 0:
        log("任务 #%s 参数不对（code=%r qty=%s）→ 判失败回队列" % (jid, code, qty))
        _report(api, client, jid, False, "任务参数不合法（code/qty）")
        return
    log("认领到任务 #%s：%s ×%s（来源 %s）→ 准备打单" % (jid, code, qty, who or "-"))
    try:
        st, msg = K.ensure_browser()
        if st != "ok":
            log("  浏览器未就绪：%s" % msg)
            _report(api, client, jid, False, "浏览器未就绪：%s" % str(msg)[:160])
            return
        verdict = {}
        _sync_shared_memory(api)               # 先同步别台已打的单（跨机防重）
        # ★ 重试只用「本任务上次挑中的那批单」，绝不另挑新单（防重试重打用户没要的单）
        only = [str(s) for s in (job.get("picked_sids") or []) if s]
        if only:
            log("  本任务已锁定 %d 单（重试只补这批，不另挑新单）" % len(only))
        _t_job = time.time()
        with _Heartbeat(api, client, jid):     # 打单期间心跳，防超时回收被别台重领
            picked, skipped, logs = K.do_print(code, qty, dry_run=False, verdict=verdict,
                                              only_sids=(only or None))
        _job_secs = time.time() - _t_job
        _picked_now = [str(o.get("sid")) for o in (picked or []) if o.get("sid")]
        _all_picked = list(dict.fromkeys(only + _picked_now))
        good, why = _job_verdict(picked, logs)
        if good is None and _all_picked:
            # ★ 锁定批次的单若已全部进本机去重记忆 → 确实都打完了，判完成（不再重试）：
            #   重试时已打的会被去重记忆挡住 → 挑到 0 单是「补打完成」，不是失败。
            try:
                if set(_all_picked) <= set(str(s) for s in K._printed_set()):
                    good, why = True, "本任务的单已全部打完（补打完成，无新单可挑）"
            except Exception:
                pass
        if good is None:                       # 0 单：必须分类，**绝不判 done**
            good, why = _classify_no_pick(code)
        _tmline = [x for x in (logs or []) if "耗时分解" in str(x)]
        log("  打单结果：%d 单（do_print 耗时 %.1fs）；%s" % (len(picked or []), _job_secs,
                                      " | ".join(str(x)[:140] for x in (logs or []) if x not in _tmline)))
        for _t in _tmline:          # 耗时分解单独整行：别被上面的 140 字截断（实测被砍掉尾巴）
            log("  " + str(_t))
        # 把「确证已出纸」的 sid 报给主端权威库（跨机防重，成功/部分成功都报）
        _printed = [s for s in (verdict.get("printed_sids") or []) if s]
        if _printed:
            _report_printed(api, client, _printed, {})
        if good:
            sid = _extract_out_sid(picked)
            log("  任务 #%s 完成：%s%s" % (jid, why, ("（运单号 %s）" % sid) if sid else ""))
            _report(api, client, jid, True, why, out_sid=sid, picked_sids=_all_picked)
        else:
            log("  任务 #%s 失败：%s → 回队列退避重试（下次只补这批 %d 单）"
                % (jid, why, len(_all_picked)))
            _report(api, client, jid, False, why, picked_sids=_all_picked)
    except BaseException as e:
        log("  任务 #%s 打单异常：%s → 回队列退避重试" % (jid, str(e)[:180]))
        _report(api, client, jid, False, "异常：%s" % str(e)[:160])


def watch_claims(api, client, stop_event=None, log_path=None, pause_path=None,
                 poll=3.0, cooldown=0.0, limit=2, quiet=False):
    """认领模式：向主端轮询属于本机（client）的打单任务 → 打单 → 回写结果。

    api(path, method=, params=, body=, timeout=) → (ok, obj)：复用主端会话机制
    （kuaimai_client.Session.api：主端走 127.0.0.1:本机端口，子端走 session.base）。

    任何一步失败都会写日志；打单失败会 report(ok=False) → 主端把任务退回队列并退避重试，
    所以**不会静默丢任务**。总开关 auto_print_pause.flag 与原来一致。
    """
    global _LOG_PATH
    if log_path:
        _LOG_PATH = log_path
    pause = pause_path or PAUSE
    client = str(client or "").strip()
    if not client:
        log("认领模式：没有本机身份，不认领")
        return
    paused = False
    fails = 0
    if not quiet:
        log("=== 认领模式启动（本机身份 %s，每 %.0f 秒向主端认领一次；队列任务之间**不冷却**，"
            "每个 job 都是用户明确提交的一次任务）===" % (client, poll))
    while not (stop_event is not None and stop_event.is_set()):
        if os.path.isfile(pause):
            if not paused:
                paused = True
                log("总开关：已暂停（删掉 %s 即恢复）" % os.path.basename(pause))
            if stop_event is None:
                time.sleep(poll)
            else:
                stop_event.wait(poll)
            continue
        if paused:
            paused = False
            log("总开关：已恢复自动打单")
        try:
            ok, res = api("/api/print/claim", "POST",
                          body={"client": client, "limit": int(limit)}, timeout=25)
        except BaseException as e:
            ok, res = False, {"error": "认领异常：%s" % str(e)[:150]}
        jobs = (res.get("jobs") if isinstance(res, dict) else None) or []
        if (not ok) or (not isinstance(res, dict)) or res.get("error"):
            fails += 1
            if fails <= 3 or fails % 20 == 0:
                log("认领失败（第 %d 次）：%s" % (fails, _err_text(res)))
        else:
            if fails:
                log("认领已恢复（之前连续失败 %d 次）" % fails)
            fails = 0
        for job in jobs:
            if stop_event is not None and stop_event.is_set():
                break
            _do_claim_one(api, client, job)
        if stop_event is None:
            time.sleep(poll)
        else:
            stop_event.wait(poll)
    log("=== 认领监听已停止 ===")


def main():
    start = 0
    cooldown = 60.0
    if "--from" in sys.argv:
        try:
            start = int(sys.argv[sys.argv.index("--from") + 1])
        except Exception:
            start = 0
    if "--cooldown" in sys.argv:
        try:
            cooldown = float(sys.argv[sys.argv.index("--cooldown") + 1])
        except Exception:
            cooldown = 60.0
    watch(start=start, cooldown=cooldown)


if __name__ == "__main__":
    main()
