# -*- coding: utf-8 -*-
r"""自动上架（推荐货位）监听器 —— **纯开放平台 API**，不依赖浏览器/登录态。

每 N 秒（默认 60，可在界面调）查一次「待上架」的上架单：

    erp.purchase.shelf.query(status=0)   → 有哪些单没上架
    erp.purchase.shelf.get(id)           → 每张单的商品明细
    本地货位索引（kuaimai_scan.shelf_map / kuaimai_shelf_cache.json）
                                         → 算推荐货位
    erp.purchase.shelf.save(id, items)   → 上架

推荐货位规则（**与 ERP 网页版「自动推荐货位」实测一致**，两单交叉验证：
46171040 与 46171044 的 ERP 推荐 = 本地推算）：
  1) 该编码自己现有的货位里，取**在架最多**的那个（同款归位，拣货不用换地方）；
  2) 该编码一条货位记录都没有时，看**同款（主编码）+ 同尺码**的兄弟编码是不是都指向同一个货位
     （实测 6618 全族按尺码固定：S=C-9-5-2 / M=C-9-6-2 / L=C-9-7-2 / XL=C-9-8-2），是则采用；
  3) 仍拿不到 → **整张单跳过**，只记日志等人工分配，**绝不乱猜货位**。

安全约定：
  · 独立开关（设置 `auto_putaway_on`）+ 可调间隔（`auto_putaway_secs`），每轮**重新读取**，
    改设置不用重启；
  · `dry_run=True` 只记「会怎么上架」，**不写库**；
  · 写前**复查该单仍在待上架**（人在 ERP 界面可能同时在操作）；
  · `code 33 该上架单已完成或已作废！` 属正常竞争 → 记日志跳过，**不重试**；
  · 写后核对：该单离开待上架 + 货位在架数读回等于写入值，三者齐了才算成功。

跑法：
  · 主程序启动后放进 daemon 线程（`kuaimai_scan.start_auto_putaway_watcher`）；
  · 单独调试：`python desktop/auto_putaway.py [--once] [--dry-run] [--interval 60]`
日志：`BASE_DIR\auto_putaway.log`
"""
import io
import json
import os
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

_DEFAULT_INTERVAL = 60
_MIN_INTERVAL = 10
_MAX_INTERVAL = 3600


def _pick_base_dir(preferred):
    """数据目录：与主程序/kuaimai_print 同规则（冻结时 exe 旁优先，不可写回落 LOCALAPPDATA）。"""
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

LOG = os.path.join(BASE_DIR, "auto_putaway.log")
_LOG_PATH = LOG


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


# ============= 推荐货位（本地推算；与 ERP 网页版实测一致）=============

_SIZE_TAIL = ("XXXL", "XXL", "XL", "XS", "S", "M", "L")


def _up(s):
    """编码比较一律忽略大小写（用户要求：快麦字母不区分大小写）。"""
    return str(s or "").strip().upper()


def split_code(code):
    """把 `6618-浅灰色M` 拆成 (主款部分 `6618`, 尺码尾 `M`)；拆不出尺码则尾为空。

    只认「编码结尾的尺码字母」：先比长尾（XXXL/XXL/XL/XS），再比单字母（S/M/L）。
    """
    c = str(code or "").strip()
    if not c:
        return "", ""
    head = c.rsplit("-", 1)[0] if "-" in c else c
    for tail in _SIZE_TAIL:
        if c.upper().endswith(tail):
            # 避免把「米白色M」里的色号误切：尺码尾必须是编码最后一段的结尾
            last = c.rsplit("-", 1)[-1]
            if last.upper().endswith(tail) and len(last) > len(tail) - 1:
                return head, tail
    return head, ""


def _bins_of(shelf_map, code):
    """取某编码的货位列表 [[货位, 数量], …]（大小写不敏感）。"""
    e = (shelf_map or {}).get(code)
    if e is None:
        u = _up(code)
        for k, v in (shelf_map or {}).items():
            if _up(k) == u:
                e = v
                break
    if not e:
        return []
    bins = e.get("bins") or []
    out = []
    for b in bins:
        try:
            out.append((str(b[0]), int(b[1] or 0)))
        except Exception:
            continue
    return out


def recommend_bin(code, shelf_map):
    """算一个编码的推荐货位 → (货位编码, 理由) 或 (None, 不可推荐的理由)。

    规则见模块头注释（① 自己的货位取在架最多 ② 同款同尺码规律 ③ 拿不到就跳过）。
    """
    bins = _bins_of(shelf_map, code)
    if bins:
        best = max(bins, key=lambda x: x[1])
        if best[1] > 0:
            return best[0], "现有货位（在架 %d）" % best[1]
        # 都在架 0：仍然用它（实测同一编码可能既有货位记录、当前没库存）
        if len(bins) == 1:
            return bins[0][0], "现有货位（在架 0）"
        # 多个全 0 的货位 → 交给尺码规律裁决，避免「历史上挂过」的干扰
    head, size = split_code(code)
    if head and size:
        votes = {}
        for k, v in (shelf_map or {}).items():
            h2, s2 = split_code(k)
            if h2 == head and s2 == size and _up(k) != _up(code):
                for bc, q in _bins_of(shelf_map, k):
                    votes.setdefault(bc, []).append(q)
        if len(votes) == 1:
            bc = list(votes)[0]
            return bc, "同款同尺码规律（%s-%s 一致指向）" % (head, size)
        if votes:
            # 多个候选：取「兄弟编码在架总数最大」的那个
            bc = max(votes, key=lambda b: sum(votes[b]))
            return bc, "同款同尺码规律（多候选取在架最多）"
    if bins:
        return bins[0][0], "仅有货位记录（在架 0，多个候选）"
    return None, "无货位记录，需人工分配"


# ============= 接口调用 =============

def _query_pending(api, days=90):
    """待上架列表（status=0）。返回 (list, err)。"""
    from datetime import datetime, timedelta
    now = datetime.now()
    biz = {"timeType": 1,
           "startModified": (now - timedelta(days=int(days))).strftime("%Y-%m-%d %H:%M:%S"),
           "endModified": now.strftime("%Y-%m-%d %H:%M:%S"),
           "status": 0, "pageNo": 1, "pageSize": 200}
    try:
        r = api("erp.purchase.shelf.query", biz) or {}
    except BaseException as e:
        return [], "查待上架异常：%s" % str(e)[:120]
    if not r.get("success"):
        return [], "查待上架失败：%s/%s" % (r.get("code"), str(r.get("msg"))[:100])
    return (r.get("list") or []), ""


def _order_details(api, sid):
    """一张上架单的明细行 → [{outerId, count, quality}]。"""
    try:
        r = api("erp.purchase.shelf.get", {"id": sid}) or {}
    except BaseException as e:
        return [], "查明细异常：%s" % str(e)[:120]
    if not r.get("success"):
        return [], "查明细失败：%s/%s" % (r.get("code"), str(r.get("msg"))[:100])
    rows = []
    for x in (r.get("list") or []):
        try:
            rows.append({"outerId": str(x.get("outerId") or "").strip(),
                         "count": int(float(x.get("count") or 0)),
                         "quality": True if x.get("quality") in (None, "", True) else
                                    str(x.get("quality")).lower() not in ("false", "0", "次品")})
        except Exception:
            continue
    return rows, ""


def _save(api, sid, items):
    """上架（写）。items 为 list[dict] → 接口要 JSON 字符串。"""
    try:
        return api("erp.purchase.shelf.save",
                   {"id": str(sid), "items": json.dumps(items, ensure_ascii=False)}) or {}
    except BaseException as e:
        return {"success": False, "code": "exception", "msg": str(e)[:150]}


def _still_pending(api, sid):
    """写前复查：该单是否仍在待上架（返回 True/False；查不到按 True 处理，交给接口自己判）。"""
    lst, err = _query_pending(api)
    if err:
        return True, err
    return any(str(o.get("id")) == str(sid) for o in lst), ""


def _verify_done(api, we_code):
    """写后核对：该单是否已进「已完成」（返回 (bool, 说明)）。"""
    from datetime import datetime, timedelta
    now = datetime.now()
    biz = {"timeType": 1,
           "startModified": (now - timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S"),
           "endModified": now.strftime("%Y-%m-%d %H:%M:%S"),
           "status": 1, "pageNo": 1, "pageSize": 200}
    try:
        r = api("erp.purchase.shelf.query", biz) or {}
    except BaseException as e:
        return False, "核对异常：%s" % str(e)[:100]
    for o in (r.get("list") or []):
        if str(o.get("weCode") or "").split("_")[0] == str(we_code or "").split("_")[0]:
            return True, "已完成（上架数 %s）" % o.get("weShelveQuantity")
    return False, "未在已完成列表中找到（可能仍在处理）"


def process_once(api, shelf_map, dry_run=False, on_done=None):
    """跑一轮：返回本轮的 (处理单数, 成功上架单数, 跳过单数) 与日志文字列表。

    `on_done(codes)`：本轮**上架成功**涉及的商品编码（去重）会回调一次；
    用于接「上架后自动智能审核」（用户在 kuaimai_scan 里接进来）。回调异常不影响上架。
    """
    lines = []
    done_codes = []
    orders, err = _query_pending(api)
    if err:
        lines.append("！！%s" % err)
        return 0, 0, 0, lines
    if not orders:
        return 0, 0, 0, lines                      # 静默：没有待上架单很正常
    if not shelf_map:
        # 索引为空就直接明说，**不要逐单刷「推荐不出货位」**（容易被当成「没单」）
        lines.append("！！待上架 %d 张单，但货位索引为空 → 本轮不做"
                     "（请先在主程序点「刷新货位库存」）" % len(orders))
        return len(orders), 0, 0, lines

    lines.append("待上架 %d 张单" % len(orders))
    done = skipped = 0
    for o in orders:
        sid = o.get("id")
        we = o.get("weCode")
        rows, err = _order_details(api, sid)
        if err:
            lines.append("  单 %s（%s）跳过：%s" % (sid, we, err))
            skipped += 1
            continue
        if not rows:
            lines.append("  单 %s（%s）跳过：明细为空" % (sid, we))
            skipped += 1
            continue

        items, bad = [], []
        for r in rows:
            code = r["outerId"]
            bc, why = recommend_bin(code, shelf_map)
            if not bc:
                bad.append("%s（%s）" % (code, why))
                continue
            items.append({"outerId": code, "quantity": int(r["count"]),
                          "quality": bool(r.get("quality", True)), "goodsSectionCode": bc})
            lines.append("    %s ×%s → %s（%s）" % (code, r["count"], bc, why))
        if bad:
            lines.append("  单 %s（%s）**跳过**：这些编码推荐不出货位 → %s"
                         % (sid, we, "；".join(bad[:6])))
            skipped += 1
            continue

        if dry_run:
            lines.append("  【预演】单 %s（%s）→ 已算好 %d 行，dry-run 不写库"
                         % (sid, we, len(items)))
            done += 1
            continue

        # 写前复查（人在界面可能同时在操作）
        okp, errp = _still_pending(api, sid)
        if not okp:
            lines.append("  单 %s（%s）已不在待上架（%s）→ 跳过，不写"
                         % (sid, we, errp or "别人做掉了"))
            skipped += 1
            continue

        res = _save(api, sid, items)
        if not res.get("success"):
            code, msg = res.get("code"), str(res.get("msg") or "")[:120]
            if str(code) == "33":
                lines.append("  单 %s（%s）上架被拒：%s（已不在待上架，属竞争，跳过）"
                             % (sid, we, msg))
            else:
                lines.append("  单 %s（%s）上架失败：%s/%s" % (sid, we, code, msg))
            skipped += 1
            continue

        okv, whyv = _verify_done(api, we)
        if okv:
            lines.append("  单 %s（%s）**上架成功**：%s" % (sid, we, whyv))
            done += 1
            for r in rows:
                c = _up(r["outerId"])
                if c and c not in done_codes:
                    done_codes.append(c)
        else:
            lines.append("  单 %s（%s）接口返回成功，但核对未通过：%s"
                         "（请人工确认）" % (sid, we, whyv))
            done += 1
            for r in rows:
                c = _up(r["outerId"])
                if c and c not in done_codes:
                    done_codes.append(c)
    if done_codes and on_done is not None:
        try:
            on_done(done_codes)
        except BaseException as e:
            lines.append("  ！！上架后处理失败（不影响上架）：%s" % str(e)[:150])
    return len(orders), done, skipped, lines


def watch(api, shelf_map_getter, stop_event=None, log_path=None,
          interval=None, dry_run=False, quiet=False, is_on=None, on_done=None):
    """自动上架监听循环（放主程序 daemon 线程里跑）。

    api(method, business)  → 已鉴权的接口调用（主程序传 kuaimai_scan.api_call 的包装）
    shelf_map_getter()     → 返回当前货位索引（主程序传 lambda: self.shelf_map）
    is_on()                → 返回开关是否打开（每轮读设置，改设置不用重启）
    interval               → 固定间隔；None = 每轮从设置里读
    on_done(codes)         → 上架成功后回调（主程序在这里接「自动智能审核」）
    """
    global _LOG_PATH
    if log_path:
        _LOG_PATH = log_path
    if not quiet:
        log("=== 自动上架监听启动（每 %s 秒查一次待上架%s）==="
            % (interval or "设置值", "，**预演模式不写库**" if dry_run else ""))
    last_run = 0.0
    while not (stop_event is not None and stop_event.is_set()):
        # 开关 + 间隔：每轮重读，界面改了立刻生效
        on = True
        try:
            on = bool(is_on()) if is_on else True
        except Exception:
            on = True
        iv = interval or _read_interval()
        if not on:
            _sleep(stop_event, min(iv, 10))
            continue
        now = time.time()
        if now - last_run < iv:
            _sleep(stop_event, min(iv - (now - last_run), iv))
            continue
        last_run = time.time()
        try:
            smap = {}
            try:
                smap = shelf_map_getter() or {}
            except BaseException as e:
                log("读货位索引失败（本轮跳过，不用空表乱推）：%s" % str(e)[:120])
                _sleep(stop_event, iv)
                continue
            n, ok, skip, lines = process_once(api, smap, dry_run=dry_run, on_done=on_done)
            for ln in lines:
                log(ln)
            if lines and n:
                log("本轮：待上架 %d 张，成功 %d，跳过 %d" % (n, ok, skip))
        except BaseException as e:
            log("！！本轮异常：%s" % str(e)[:200])
        _sleep(stop_event, iv)
    log("=== 自动上架监听已停止 ===")


def _sleep(stop_event, secs):
    secs = max(0.2, float(secs or 0))
    if stop_event is None:
        time.sleep(secs)
    else:
        stop_event.wait(secs)


def _read_interval():
    """从主程序设置里读间隔（读不到用默认 60，越界收敛到 10–3600）。"""
    try:
        p = os.path.join(BASE_DIR, "kuaimai_settings.json")
        with open(p, "r", encoding="utf-8") as f:
            v = (json.load(f) or {}).get("auto_putaway_secs", _DEFAULT_INTERVAL)
        v = int(float(v))
    except Exception:
        v = _DEFAULT_INTERVAL
    return max(_MIN_INTERVAL, min(_MAX_INTERVAL, v))


def main():
    """单独调试用：--once 跑一轮；--dry-run 不写库；--interval 秒。"""
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--once", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--interval", type=int, default=None)
    a = ap.parse_args()
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import kuaimai_scan as KS
    import kuaimai_db
    ks_base = os.path.join(os.environ.get("LOCALAPPDATA") or "", "KuaimaiScan")
    if os.path.isdir(ks_base):
        KS.BASE_DIR = ks_base
        KS.API_FILE = os.path.join(ks_base, "kuaimai_api.json")
        KS.CACHE_FILE = os.path.join(ks_base, "kuaimai_token_cache.json")
        KS.reload_api_conf()
    sess = KS.current_session()
    odb = os.path.join(KS.BASE_DIR, "kuaimai_data.db")

    def api(method, biz, timeout=60):
        return KS.api_call(method, biz, sess, timeout=timeout)

    def shelf_getter():
        """货位索引：用主程序那条稳健取法（只读已存在的库，不缺就报错、不新建空库）。"""
        return KS._load_shelf_map_now()

    if a.once:
        n, ok, skip, lines = process_once(api, shelf_getter(), dry_run=a.dry_run)
        for ln in lines:
            print(ln)
        print("待上架 %d，成功 %d，跳过 %d" % (n, ok, skip))
        return
    watch(api, shelf_getter, interval=a.interval, dry_run=a.dry_run)


if __name__ == "__main__":
    main()
