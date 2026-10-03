# -*- coding: utf-8 -*-
"""生成波次（ERP 网页登录态）：扫编码 → 查「最大可生成件数」→ 按打单口径挑单 → 成波 + 回读核对。

口径（与 kuaimai_print 打单一致）：
  1) 已超时（剩余<0）最优先 → 2) 加急（本机库 orders.urgent=1）→ 3) 剩余时间少的先 → 4) sid
  · **只挑「一单一件」的订单**（整单只有一个非赠品/非占位明细且数量=1；赠品不计，
    占位/补偿商品照旧排除：编码首段 1166、名称含 买家秀/圆虹包）。
    多件单/组合单不参与凑数 —— 件数不够时按一单一件的最大值生成。
  · 挑单只挑「该编码在火火火仓库还能成波」的候选订单（来自 /trade/wave/checked/trade/query）；
  · 填的件数 > 最大可生成 → 以最大可生成件数成波（不报错）；
  · 一次成波把全部挑中的 sids 一次传给 /trade/wave/checked/trade/save（一个波次）。

只走 **CDP 页面内 fetch**，不碰开放平台密钥；波次回读（erp.trade.waves.query）由调用方传入
caller（主程序用 api_call_authed），本模块不自带凭据。

对外：
  lookup(code)               某编码最大可生成件数 + 候选订单明细
  plan(items)                干跑（只读）：按 targets 挑单，返回 sids 与每码实际件数，不建波
  create(items)              真正成波：save 一个波次（全部 sids）
  verify_wave(sids, caller)  用开放平台回读核对（只读）
"""
import json
import urllib.parse

import kuaimai_print as KP

WAREHOUSE_ID = 556677                 # 火火火服饰仓库（本次只用这个仓）
CARRIERS = ("中通", "申通")            # 波次按快递拆开：一个波次只含一种快递（名称子串匹配）
QUERY_PATH = "/trade/wave/checked/trade/query"
SAVE_PATH = "/trade/wave/checked/trade/save"
DEFAULT_PAGE_SIZE = 600               # 与服务端 queryWaveTradeByCondition 的 limit 600 对齐


def _ci(code):
    """编码归一化：快麦不区分字母大小写，比较统一转大写。"""
    return str(code or "").strip().upper()


# 占位/补偿商品（与打单口径一致）：编码首段 1166、名称含 买家秀/圆虹包
EXCLUDE_CODE_HEADS = ("1166",)
EXCLUDE_NAME_KEYWORDS = ("买家秀", "圆虹包")


def _is_gift(it):
    """赠品明细（不计入件数/种类）。"""
    return bool(it.get("gift") or it.get("platformGift") or it.get("sysGift"))


def _is_placeholder(it):
    """占位/补偿商品（编码首段 1166 或名称含 买家秀/圆虹包）。"""
    code = _ci(it.get("sysOuterId") or it.get("outerId") or "")
    if code.startswith(EXCLUDE_CODE_HEADS):
        return True
    name = str(it.get("sysTitle") or it.get("title") or "")
    return any(k in name for k in EXCLUDE_NAME_KEYWORDS)


def _real_lines(o):
    """一单里的“有效”明细行（排除赠品与占位/补偿商品）。"""
    rows = o.get("itemInfoList")
    if not isinstance(rows, list) or not rows:
        rows = o.get("orders") if isinstance(o.get("orders"), list) else []
    return [it for it in rows
            if isinstance(it, dict) and not _is_gift(it) and not _is_placeholder(it)]


def _is_one_piece(o):
    """一单一件：整单只有一个非赠品/非占位的明细，且数量=1。

    用户硬约束：波次只挑一单一件的订单（多件单/组合单即便件数不够也不用来凑）。
    """
    lines = _real_lines(o)
    if len(lines) != 1:
        return False
    try:
        return int(lines[0].get("num") or lines[0].get("qty") or 0) == 1
    except Exception:
        return False


def _carrier_of(o):
    """订单的快递公司名（ERP 候选响应里的 logisticsCompanyName）。"""
    return str(o.get("logisticsCompanyName") or "").strip()


def _c_match(name, carrier):
    """快递匹配：按子串（实测值 "中通快递-茉茉店铺" / "申通快递"）。忽略首尾空格。"""
    return bool(carrier) and carrier in str(name or "")


def _post(c, path, body, ctype, timeout=90000):
    """在页面里 POST 一段 body（返回 {status, text}；失败带 err）。"""
    js = """(async function(){
      const ac = new AbortController();
      const to = setTimeout(function(){ ac.abort(); }, %d);
      try {
        const r = await fetch(%s, {method:'POST', credentials:'include',
          headers:{'Content-Type':%s}, body:%s, signal: ac.signal});
        clearTimeout(to);
        const t = await r.text();
        return {status: r.status, text: t};
      } catch(e) { return {status: 0, err: String(e)}; }
    })()""" % (timeout, json.dumps(path), json.dumps(ctype), json.dumps(body))
    return c.js(js) or {}


def _orders_from(res):
    """从 query 响应里取候选订单列表（[{sid, qty:{大写编码: 件数}}]）。"""
    text = (res or {}).get("text") or ""
    try:
        j = json.loads(text)
    except Exception:
        return []
    data = j.get("data")
    arr = None
    if isinstance(data, list):
        arr = data
    elif isinstance(data, dict):
        for k in ("list", "rows", "data"):
            if isinstance(data.get(k), list):
                arr = data[k]
                break
    if not isinstance(arr, list):
        return []
    out = []
    for o in arr:
        if not isinstance(o, dict):
            continue
        sid = str(o.get("sid") or "")
        if not sid:
            continue
        qty = {}
        for it in _real_lines(o):
            cd = it.get("sysOuterId") or it.get("outerId") or ""
            try:
                n = int(it.get("num") or it.get("qty") or 0)
            except Exception:
                n = 0
            if cd and n > 0:
                k = _ci(cd)
                qty[k] = qty.get(k, 0) + n
        if not _is_one_piece(o):
            continue                      # 只收「一单一件」（用户硬约束）
        out.append({"sid": sid, "qty": qty, "carrier": _carrier_of(o)})
    return out


def _query_raw(c, code):
    """按商家编码查该编码在火火火仓库的候选（可成波）订单。"""
    form = urllib.parse.urlencode({
        "warehouseId": WAREHOUSE_ID,
        "conditionId": "",
        "sids": "",
        "itemNumUp": "",
        "itemNumDown": "",
        "sysSkuRemark": "",
        "sysItemRemark": "",
        "bindGoodsSectionCode": "",
        "titles": "",
        "skuPropertiesNames": "",
        "outerIdStr": code,
        "mainOuterId": "",
        "isAccurate": "1",
        "specifyShipperIds": "",
        "pageSize": DEFAULT_PAGE_SIZE,
    })
    return _orders_from(_post(c, QUERY_PATH, form, "application/x-www-form-urlencoded"))


def lookup(code):
    """某编码最大可生成件数（按快递分组）+ 候选订单明细。

    只统计「一单一件」的候选单；`carriers` 是 {中通: n, 申通: m}（其他快递归入 other）。
    """
    code = str(code or "").strip()
    if not code:
        return {"error": "缺少编码"}
    c = KP.open_cdp_page()
    try:
        orders = _query_raw(c, code)
    finally:
        c.close()
    k = _ci(code)
    per, other = {c2: 0 for c2 in CARRIERS}, {}
    det = []
    for o in orders:
        n = o["qty"].get(k, 0)
        if n <= 0:
            continue
        det.append({"sid": o["sid"], "qty": n, "carrier": o.get("carrier") or ""})
        name = o.get("carrier") or ""
        for c2 in CARRIERS:
            if c2 in name:
                per[c2] += n
                break
        else:
            other[name or "(空)"] = other.get(name or "(空)", 0) + n
    total = sum(o["qty"].get(k, 0) for o in orders)
    return {"ok": True, "code": code, "max": total, "carriers": per, "other": other,
            "orders": len(orders), "det": det, "warehouseId": WAREHOUSE_ID}


def _priority(codes):
    """剩余时间（小时，可负）来源：打单页 /trade/search（与打单口径同源）。{sid: remain}"""
    rem = {}
    for code in codes:
        try:
            rows = KP.fetch_orders_live(code)
        except BaseException:
            continue
        for o in rows or []:
            s = str(o.get("sid") or "")
            if s:
                rem[s] = o.get("remain")
    return rem


def _remain_h(v):
    if v is None:
        return 99999.0
    try:
        return float(v)
    except Exception:
        return 99999.0


def _pkey(sid, rem, urg):
    """排序键：已超时(<0)最前 → 加急 → 剩余时间升序 → sid（与打单口径一致）。"""
    h = _remain_h(rem.get(sid))
    return (0 if h < 0 else 1, 0 if sid in urg else 1, h, str(sid))


def plan(items, carrier=""):
    """干跑：按 {code, qty} 目标挑单。返回每码 target/max/actual + 将成波的 sids + 明细。不建波。

    carrier（必填）：只挑该快递（中通/申通）的候选单 —— 用户要求**一个波次只能是同一种快递**。
    """
    carrier = str(carrier or "").strip()
    if not carrier:
        return {"error": "请先选择快递（中通 / 申通）：一个波次只能同一种快递"}
    req = []
    for it in (items or []):
        if not isinstance(it, dict):
            continue
        cd = str(it.get("code") or "").strip()
        try:
            q = int(float(it.get("qty") or 0))
        except Exception:
            q = 0
        if cd and q > 0:
            req.append({"code": cd, "qty": q})
    if not req:
        return {"error": "没有有效的编码/件数"}

    targets, orig = {}, {}
    for r in req:
        k = _ci(r["code"])
        targets[k] = targets.get(k, 0) + r["qty"]
        orig.setdefault(k, r["code"])

    c = KP.open_cdp_page()
    try:
        cand, raw_by_code = {}, {}
        for t in targets:
            rows = [o for o in _query_raw(c, orig.get(t, t))
                    if _c_match(o.get("carrier"), carrier)]
            raw_by_code[t] = rows
            for o in rows:
                # 同一订单会被多个编码的查询各返回一次（每次都是该单的完整明细），
                # 逐编码取 max 去重，绝不相加（否则 actual 会翻倍）。
                m = cand.setdefault(o["sid"], {})
                for cc, qq in o["qty"].items():
                    m[cc] = max(m.get(cc, 0), qq)
    finally:
        c.close()

    maxs = {t: sum(o["qty"].get(t, 0) for o in raw_by_code.get(t, [])) for t in targets}
    eff = {t: min(targets[t], maxs[t]) for t in targets}

    rem = _priority(list(targets.keys()))
    try:
        urg = KP.load_urgent_sids()
    except BaseException:
        urg = set()

    sids = sorted(cand.keys(), key=lambda s: _pkey(s, rem, urg))
    selected, covered = [], {}
    for sid in sids:
        q = cand[sid]
        if not any(covered.get(cc, 0) < eff.get(cc, 0) for cc in q if cc in eff):
            continue
        selected.append(sid)
        for cc, qq in q.items():
            covered[cc] = covered.get(cc, 0) + qq
        if all(covered.get(t, 0) >= eff[t] for t in eff):
            break

    codes = [{"code": orig.get(t, t), "target": targets[t], "max": maxs[t],
              "actual": covered.get(t, 0)} for t in targets]
    picks = []
    for sid in selected:
        p_rem = rem.get(sid)
        picks.append({"sid": sid, "remain": p_rem, "urgent": bool(sid in urg),
                      "contribute": {k: v for k, v in cand[sid].items() if k in eff}})
    return {"ok": True, "carrier": carrier, "codes": codes, "sids": selected, "picks": picks,
            "candidates": len(cand), "warehouseId": WAREHOUSE_ID}


def create(items, carrier=""):
    """真正成波：先算挑单，再把全部 sids 一次 save（一个波次，只含选定的那一种快递）。"""
    p = plan(items, carrier)
    if p.get("error"):
        return p
    sids = p.get("sids") or []
    if not sids:
        return {"error": "没有可成波的订单（可能已全部成波 / 已打印 / 该编码无可生成订单）"}
    c = KP.open_cdp_page()
    try:
        body = json.dumps({"warehouseId": WAREHOUSE_ID, "ruleId": "", "sids": sids,
                           "hasFilter": False})
        res = _post(c, SAVE_PATH, body, "application/json")
    finally:
        c.close()
    text = (res or {}).get("text") or ""
    ok, status = False, ""
    try:
        j = json.loads(text)
        d = j.get("data") or {}
        status = str(d.get("status") or "")
        ok = (status == "success") or bool(j.get("success"))
    except Exception:
        pass
    out = dict(p)
    out["save_ok"] = ok
    out["save_status"] = status
    out["save_http"] = (res or {}).get("status")
    if not ok:
        out["error"] = "成波接口未返回 success（code/msg 见下）"
        out["save_msg"] = text[:300]
    return out


def verify_wave(sids, caller, minutes=20):
    """用开放平台 erp.trade.waves.query 回读核对（只读）。caller(method, biz) 由主程序传。"""
    from datetime import datetime, timedelta, timezone
    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz)
    biz = {"pageNo": 1, "pageSize": 100,
           "start": (now - timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S"),
           "end": (now + timedelta(minutes=2)).strftime("%Y-%m-%d %H:%M:%S")}
    try:
        res = caller("erp.trade.waves.query", biz)
    except Exception as e:
        return {"ok": False, "error": "回读失败：%s" % str(e)[:150]}
    if not isinstance(res, dict):
        return {"ok": False, "error": "回读返回异常"}
    want = set(str(s) for s in (sids or []))
    best = None
    for w in (res.get("list") or []):
        ws = set(str(x.get("sid")) for x in (w.get("list") or []))
        inter = len(want & ws)
        if inter and (best is None or inter > best[0]):
            best = (inter, w, ws)
    if not best:
        return {"ok": False, "error": "回读未找到含本次 sids 的波次",
                "waves": len(res.get("list") or []), "code": res.get("code"), "msg": res.get("msg")}
    inter, w, ws = best
    return {"ok": True, "wave_id": w.get("id"), "wave_code": w.get("code"),
            "status": w.get("status"), "tradesCount": w.get("tradesCount"),
            "itemCount": w.get("itemCount"), "matched": inter,
            "missing": sorted(want - ws), "extra": len(ws - want)}
