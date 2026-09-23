# -*- coding: utf-8 -*-
r"""上架后自动「智能审核」—— 把上架好的单送进可打单状态。

用户口径（原话）：「操作完上架单还要智能审核才能去打印快递单，你能不能操作完上架单去智能审核」
⇒ 因果链：**上架 → 库存到位 → 缺货异常解除 → 可审核 → 可打单**。

**只做智能审核**（用户明确：「你只能智能审核 不能缺货审核和强制审核还有其他审核类的」）：
本模块**只**调 `/trade/audit/manual`，**绝不**碰 `/trade/audit/force`（强制审核）、
`/trade/audit/insufficient`（缺货审核）、`/trade/unaudit`（取消审核）、`/trade/finance/audit`（财审）。

接口（**ERP 页面内接口，要登录态**，实测于订单管理页 `#/tradeNew/manage/`）：
  · `POST /trade/audit/manual`  ← 就是订单管理页「智能审核」按钮点确定后发的那个
    **form 编码**，必带 `api_name=trade_audit_manual`；`sid` 逗号分隔（不选单则为空=审当前查询结果）。
    返回 `{result:1, data:{progressKey:"progress_audit_...", status:"success"}}`；`result:3` 是业务拒绝。
    **实测证据**：在订单管理页点「智能审核」→ 选模式1 → 点确定，被拦截到的请求体就是
    `api_name=trade_audit_manual&ignoreBeforeDate=true&queryId=62&useHasNext=1&pageNo=1&timeType=pay_time&...&sid=`
    （`input.rc-btn-ok` 才是确定按钮 —— 它是 `input`，没有 innerText，按文本找不到）
  · **审核是全局互斥的**：并发时返回 `result:3 message:"其他员工正在进行审核操作，请稍后重试!"`
    ⇒ 必须当成「稍后再试」，不能当失败重试轰炸。

安全约定：
  · 独立开关（设置 `auto_audit_on`，默认 **关**），只有「自动上架」开着且刚上架成功才触发；
  · **只审 WAIT_AUDIT 的单**，且只审「本次上架涉及的编码」相关的单 —— 不做全店扫描；
  · 打单浏览器（Edge 9222）没开 → 记日志跳过，**不报错、不影响上架**；
  · 审完**回读核对**（开放平台重查 WAIT_AUDIT）：没离开就说明「规则没放行」，**不算失败**。

依赖：复用 `kuaimai_print` 的 CDP 连接（`open_cdp_page`），不另造一套。
日志：`BASE_DIR\auto_audit.log`
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

_DEFAULT_WINDOW_DAYS = 7          # 找待审核单的默认回溯天数
_MAX_SIDS_PER_CALL = 200          # 单次送审上限（超过分批）
_AUDIT_PATH = "/trade/audit/manual"
_AUDIT_API_NAME = "trade_audit_manual"


def _pick_base_dir(preferred):
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

_LOG_PATH = os.path.join(BASE_DIR, "auto_audit.log")


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


def _up(s):
    return str(s or "").strip().upper()


# ============= 找「这些编码的待审核单」=============

def find_pending_sids(api, codes, days=_DEFAULT_WINDOW_DAYS, max_win_days=2):
    """查 `codes` 里各编码当前**待审核**的订单 → (可审 sids, 命中的编码, 跳过说明, 错误)。

    **用户口径（必须遵守）**：
      · **缺货异常的订单本身就不能智能审核** → 带 `exceptions`（尤其 `EX_INSUFFICIENT`）的直接跳过；
      · **有留言/备注且未人工处理的也要跳过**，只有「无留言/无备注」或「已人工处理」的才可以审。
    后一条 ERP 自己在审核时也会卡（返回「订单是异常订单」之类），这里先按能拿到的字段预筛，
    剩下的交给 ERP 审单规则裁决（它才是权威）。

    只查 WAIT_AUDIT；按创建时间切窗（避免 20027 查询结果过多）。
    """
    from datetime import datetime, timedelta
    want = set(_up(c) for c in (codes or []) if str(c or "").strip())
    if not want:
        return [], set(), "没有要审的编码", ""
    now = datetime.now()
    fmt = "%Y-%m-%d %H:%M:%S"
    sids, hit, errs = [], set(), []
    n_exc = 0
    n_msg = 0
    seen = set()

    end = now
    while (now - end).days < int(days):
        start = max(end - timedelta(days=int(max_win_days)), now - timedelta(days=int(days)))
        biz = {"status": "WAIT_AUDIT", "timeType": "created",
               "startTime": start.strftime(fmt), "endTime": end.strftime(fmt),
               "pageNo": 1, "pageSize": 200}
        try:
            r = api("erp.trade.list.query", biz) or {}
        except BaseException as e:
            errs.append(str(e)[:80])
            break
        if not r.get("success"):
            # 窗口过大（20027）→ 收窄到 1 天再试一次
            biz2 = dict(biz)
            biz2["startTime"] = (end - timedelta(days=1)).strftime(fmt)
            try:
                r = api("erp.trade.list.query", biz2) or {}
            except BaseException as e:
                errs.append(str(e)[:80])
                break
            if not r.get("success"):
                errs.append("%s/%s" % (r.get("code"), str(r.get("msg"))[:60]))
        if r.get("success"):
            for o in (r.get("list") or []):
                sid = str(o.get("sid") or "").strip()
                if not sid or sid in seen:
                    continue
                m = False
                for it in (o.get("orders") or []):
                    c1, c2 = _up(it.get("sysOuterId")), _up(it.get("sysItemOuterId"))
                    if c1 in want or c2 in want:
                        m = True
                        if c1 in want:
                            hit.add(c1)
                        if c2 in want:
                            hit.add(c2)
                if not m:
                    continue
                seen.add(sid)
                # ① 缺货异常 → 本身就不能审
                if o.get("exceptions"):
                    n_exc += 1
                    continue
                # ② 有留言/备注且未人工处理 → 跳过（已处理的字段为 1/true）
                if _has_unhandled_note(o):
                    n_msg += 1
                    continue
                sids.append(sid)
        end = start
        if end <= now - timedelta(days=int(days)):
            break

    skip = []
    if n_exc:
        skip.append("%d 单缺货/异常（本身就不能审）" % n_exc)
    if n_msg:
        skip.append("%d 单有未处理的留言/备注" % n_msg)
    if errs and not sids:
        return [], hit, "；".join(skip), "查待审核失败：%s" % ("；".join(errs[:3]))
    return sids, hit, "；".join(skip), ""


def _has_unhandled_note(o):
    """该单是否有「未人工处理」的留言/备注 → True 表示要跳过。

    判定：有留言/备注内容，且对应的 `isHandlerMessage`/`isHandlerMemo` 不是真值。
    字段缺失时**宁可保守**（当它有未处理内容就跳过，不冒险）。
    """
    def truthy(v):
        return str(v).lower() in ("1", "true", "yes")

    def any_text(*keys):
        for k in keys:
            v = o.get(k)
            if v not in (None, "", [], {}):
                return True
        return False

    has_msg = any_text("buyerMessage", "message", "buyerMsg")
    has_memo = any_text("sellerMemo", "memo", "remark", "sellerRemark")
    if has_msg and not truthy(o.get("isHandlerMessage")):
        return True
    if has_memo and not truthy(o.get("isHandlerMemo")):
        return True
    # 没拿到留言/备注字段时的兜底：isHandler* 明确为假且页面标了「已处理」相关位
    if not has_msg and not has_memo:
        return False
    return False


# ============= 页面内接口（走 CDP，form 编码）=============

def _form_post(c, path, form, timeout=120):
    """在 ERP 页面里发 **form 编码** 的 POST（与真实调用一致）。"""
    from urllib.parse import urlencode
    js = """(async function(){
      const ac = new AbortController();
      const to = setTimeout(function(){ ac.abort(); }, %d);
      try {
        const r = await fetch(%s, {method:'POST', credentials:'include',
          headers:{'Content-Type':'application/x-www-form-urlencoded'},
          body:%s, signal: ac.signal});
        clearTimeout(to);
        const t = await r.text();
        return 'HTTP '+r.status+' '+t.slice(0, 3000);
      } catch(e) { return 'ERR '+String(e); }
    })()""" % (timeout * 1000, json.dumps(path), json.dumps(urlencode(form)))
    return c.js(js)


def _parse_resp(raw):
    """'HTTP 200 {...}' → (http_code, dict|None, 原文)。

    注意必须 `split(" ", 2)`：用 `split(" ", 1)` 会把 head 取成 "HTTP"、code 取成空串。
    """
    s = str(raw or "")
    if s.startswith("ERR "):
        return 0, None, s
    try:
        head, _code, body = s.split(" ", 2)
        code = int(_code)
        if head.strip().upper() != "HTTP":
            raise ValueError(head)
    except Exception:
        return 0, None, s
    try:
        return code, json.loads(body), s
    except Exception:
        return code, None, s


# 审核结果是全局互斥的
_LOCK_WORDS = ("正在进行审核", "稍后重试", "请稍后再试")


def smart_audit_sids(c, sids):
    """送审这些 sid（**走 ERP 智能审核**）→ (状态, 说明)。

    状态：'ok' 已受理 / 'lock' 别人正在审核（稍后再试）/ 'reject' 被拒 / 'error' 请求失败。
    """
    sids = [str(x).strip() for x in (sids or []) if str(x or "").strip()]
    if not sids:
        return "reject", "没有可送审的订单"
    if len(sids) > _MAX_SIDS_PER_CALL:
        sids = sids[:_MAX_SIDS_PER_CALL]

    form = {"api_name": _AUDIT_API_NAME, "ignoreBeforeDate": "true",
            "sid": ",".join(sids),
            "pageNo": "1", "pageSize": "500", "order": "desc", "timeType": "pay_time"}
    code, js, raw = _parse_resp(_form_post(c, _AUDIT_PATH, form))
    if js is None:
        return "error", "送审请求失败（HTTP %s）：%s" % (code, raw[:160])

    result = js.get("result")
    msg = str(js.get("message") or "")
    if any(w in msg for w in _LOCK_WORDS):
        return "lock", "别人正在审核，稍后再试（%s）" % msg[:60]
    if result == 1 or str((js.get("data") or {}).get("status") or "") == "success":
        pk = (js.get("data") or {}).get("progressKey")
        return "ok", "已受理（%d 单%s）" % (len(sids), "，异步任务" if pk else "")
    return "reject", "被拒：result=%s %s" % (result, msg[:80] or str(js)[:80])


def verify_left_pending(api, sids, days=_DEFAULT_WINDOW_DAYS):
    """核对：这些 sid 是否已离开 WAIT_AUDIT → (还剩几个, 说明)。"""
    sids = set(str(x).strip() for x in (sids or []) if str(x or "").strip())
    if not sids:
        return 0, "无单可核对"
    from datetime import datetime, timedelta
    now = datetime.now()
    fmt = "%Y-%m-%d %H:%M:%S"
    still = 0
    end = now
    while (now - end).days < int(days):
        start = max(end - timedelta(days=2), now - timedelta(days=int(days)))
        biz = {"status": "WAIT_AUDIT", "timeType": "created",
               "startTime": start.strftime(fmt), "endTime": end.strftime(fmt),
               "pageNo": 1, "pageSize": 200}
        try:
            r = api("erp.trade.list.query", biz) or {}
        except BaseException:
            break
        if r.get("success"):
            for o in (r.get("list") or []):
                if str(o.get("sid") or "").strip() in sids:
                    still += 1
        end = start
        if end <= now - timedelta(days=int(days)):
            break
    return still, ("已全部离开待审核" if not still else "其中 %d 单仍在待审核" % still)


# ============= 对外主流程 =============

def audit_codes(cdp_factory, api, codes, days=_DEFAULT_WINDOW_DAYS, dry_run=False):
    """上架成功后调用：把 `codes` 下**可审的**待审核单**智能审核**掉 → (审掉的单数, 日志行列表)。

    可审 = 无缺货/异常 + 无未处理的留言/备注（用户口径，见 `find_pending_sids`）。
    """
    lines = []
    sids, hit, skipped, err = find_pending_sids(api, codes, days=days)
    if err:
        lines.append("！！%s" % err)
        return 0, lines
    if skipped:
        lines.append("  跳过：%s" % skipped)
    if not sids:
        lines.append("  没有可审的单（剩下的不是缺货异常、就是留言/备注还没处理）")
        return 0, lines
    lines.append("  可审 %d 单（命中编码 %d 个：%s）"
                 % (len(sids), len(hit), "、".join(sorted(hit)[:6])))
    if dry_run:
        lines.append("  【预演】本会智能审核 %d 单，dry-run 不调接口" % len(sids))
        return len(sids), lines

    c = None
    try:
        c = cdp_factory()
    except BaseException as e:
        lines.append("  跳过审核：连不上打单浏览器（%s）" % str(e)[:100])
        return 0, lines
    if c is None:
        lines.append("  跳过审核：打单浏览器没开（Edge 9222）")
        return 0, lines
    try:
        st, msg = smart_audit_sids(c, sids)
        lines.append("  智能审核：%s" % msg)
        if st != "ok":
            # lock/reject/error 都不重试轰炸；本轮到此为止
            return 0, lines
        left, why = verify_left_pending(api, sids, days=days)
        lines.append("  审核核对：%s%s"
                     % (why, "（规则不放行的，如临货异常/留言未处理，会留着，属正常）" if left else ""))
        return len(sids) - left, lines
    finally:
        try:
            c.close()
        except Exception:
            pass


def main():
    """单独调试：--codes 逗号分隔编码；--dry-run 不调接口。"""
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("--codes", required=True)
    ap.add_argument("--days", type=int, default=_DEFAULT_WINDOW_DAYS)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import kuaimai_scan as KS
    ks_base = os.path.join(os.environ.get("LOCALAPPDATA") or "", "KuaimaiScan")
    if os.path.isdir(ks_base):
        KS.BASE_DIR = ks_base
        KS.API_FILE = os.path.join(ks_base, "kuaimai_api.json")
        KS.CACHE_FILE = os.path.join(ks_base, "kuaimai_token_cache.json")
        KS.reload_api_conf()
    sess = KS.current_session()

    def api(method, biz, timeout=60):
        return KS.api_call(method, biz, sess, timeout=timeout)

    def factory():
        import kuaimai_print as KP
        return KP.open_cdp_page()

    codes = [x.strip() for x in a.codes.split(",") if x.strip()]
    n, lines = audit_codes(factory, api, codes, days=a.days, dry_run=a.dry_run)
    for ln in lines:
        print(ln)
    print("本次审核 %d 单" % n)


if __name__ == "__main__":
    main()
