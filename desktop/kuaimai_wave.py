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

只走 **CDP 页面内 fetch**，不碰开放平台密钥。

**波次号回读（v1.46）**：save 返回 success ≠ ERP 真的建出波次，且开放平台 erp.trade.waves.query
**只返回已拣选波次**（新波次永远读不到）。所以改走 ERP 网页「波次管理」接口
/trade/wave/manager/list（登录态、含未拣选波次）回读。
verify_wave（开放平台）保留导出，别处可能引用，但 create() 不再调它。

对外：
  lookup(code)               某编码最大可生成件数 + 候选订单明细
  plan(items)                干跑（只读）：按 targets 挑单，返回 sids 与每码实际件数，不建波
  manager_waves(...)         ERP 网页「波次管理」列表（只读，含未拣选波次）
  readback_new_wave(...)     在网页列表里回读本次新建的波次（只读）
  create(items)              真正成波：save 一个波次（全部 sids）+ 网页列表回读波次号
  verify_wave(sids, caller)  用开放平台回读核对（只读；只返回已拣选波次，保留导出）
"""
import json
import os
import time
import urllib.parse

import kuaimai_print as KP

WAREHOUSE_ID = 556677                 # 火火火服饰仓库（本次只用这个仓）

# 波次状态中文。官方 erp.trade.waves.query 只给 1/3/4；但实测「等待验货」也回 status=1，
# 区别在 pickEndTime：status=1 且无 pickEndTime = 待拣货/未完成；status=1 且有 pickEndTime = 等待验货（已拣）。
WAVE_STATUS_CN = {1: "未完成", 3: "已完成", 4: "已取消"}
PICKED_CN = "等待验货"      # 有 pickEndTime 的未完成波次：已拣、等待验货


def wave_state(status, pick_end_time=None):
    """按 (status, pickEndTime) 算网页状态口径。

    · status=3 → 已完成；status=4 → 已取消；
    · status=1 且无 pickEndTime → 待拣货（未完成）；
    · status=1 且有 pickEndTime → 等待验货（已拣）。
    返回 {status, status_cn, picked, pick_end_time}。
    """
    raw = status
    if raw is None or raw == "":
        return {"status": raw, "status_cn": "", "picked": False, "pick_end_time": pick_end_time}
    try:
        iv = int(raw)
    except Exception:
        return {"status": raw, "status_cn": str(raw), "picked": bool(pick_end_time),
                "pick_end_time": pick_end_time}
    pet = pick_end_time
    try:
        pet_ms = int(pet or 0)
    except Exception:
        pet_ms = 0
    # ERP 用 0 / 946656000000（2000-01-01）当「没有时间」的占位；真实毫秒时间戳远大于 1e12。
    # 所以只能按数值判断，不能用“非空字符串”——否则 0 会被当成已拣（v1.42 踩过）。
    has_pet = pet_ms > 1000000000000
    if iv == 3:
        cn, picked = "已完成", True
    elif iv == 4:
        cn, picked = "已取消", False
    elif iv == 1:
        cn, picked = (PICKED_CN if has_pet else "未完成"), has_pet
    else:
        cn, picked = str(raw), has_pet
    return {"status": raw, "status_cn": cn, "picked": picked, "pick_end_time": pet}


def status_cn(s, pick_end_time=None):
    """波次状态 → 中文；未知值返回原始字符串（绝不瞎猜）。传入 pickEndTime 才能区分「等待验货」。"""
    return wave_state(s, pick_end_time).get("status_cn") or ""
CARRIERS = ("中通", "申通")            # 波次按快递拆开：一个波次只含一种快递（名称子串匹配）
QUERY_PATH = "/trade/wave/checked/trade/query"
SAVE_PATH = "/trade/wave/checked/trade/save"
MANAGER_PATH = "/trade/wave/manager/list"   # ERP 网页「波次管理」列表（登录态，含未拣选波次）
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


def _post_many(c, path, forms, ctype="application/x-www-form-urlencoded", timeout=90000):
    """一次 c.js 调用里**并发** POST 多份 body，返回 [{status,text,err}, ...]（顺序与 forms 对齐）。

    波次挑单是「一个编码一次查询」：逐个串行发时 N 个编码要 N 次往返（实测每个 1.3~3s）。
    放进一个 Promise.all 让**浏览器自己并发**（同源通常 6 并发），总耗时 ≈ 最慢的那一个。
    """
    forms = list(forms or [])
    if not forms:
        return []
    js = """(async function(){
      const tmo = %d;
      const one = function(body){
        const ac = new AbortController();
        const to = setTimeout(function(){ ac.abort(); }, tmo);
        return fetch(%s, {method:'POST', credentials:'include',
            headers:{'Content-Type':%s}, body:body, signal:ac.signal})
          .then(function(r){ return r.text().then(function(t){
              clearTimeout(to); return {status:r.status, text:t}; }); })
          .catch(function(e){ clearTimeout(to); return {status:0, err:String(e)}; });
      };
      try { return await Promise.all(%s.map(one)); } catch(e){ return []; }
    })()""" % (timeout, json.dumps(path), json.dumps(ctype), json.dumps(forms))
    res = c.js(js)
    return res if isinstance(res, list) else []


def _erp_err(text):
    """识别 ERP 的「会话异常 / 未登录」等错误响应，返回给用户看的原因；正常返回 ''。

    ERP 错误响应形如：{"clueId":"null","data":{},"message":"会话异常，请重新登录","result":901}
    —— 正常业务响应**没有 result 字段**（data 才是列表）。以前这里不检查，会把错误当成
    「0 个候选订单」，界面上显示成「没有可成波订单」，让人误判成真没单。
    """
    try:
        j = json.loads(text or "")
    except Exception:
        return ""
    if not isinstance(j, dict):
        return ""
    res = j.get("result")
    msg = str(j.get("message") or "").strip()
    low = msg.lower()
    login_issue = any(k in msg for k in ("会话异常", "重新登录", "未登录", "登录超时", "登录失效")) \
        or ("session" in low) or ("login" in low)
    is_err = login_issue or (res not in (None, 0, "0", ""))
    if not is_err:
        return ""
    why = msg or ("result=%s" % res)
    if login_issue:
        return "ERP 登录已失效（%s）—— 请在软件里点「登录 ERP」重新登录后再试" % why
    return "ERP 返回错误：%s" % why


def _split_raw(res, code):
    """解析 query 响应 → {"one": [一单一件候选], "multi_qty": 多件预留件数, ["error": 原因]}。

    `one`：只含「一单一件」的候选单（波次只挑这些，用户硬约束）。
    `multi_qty`：该编码在**非一单一件**（一单多件/组合单）候选里的件数合计 ——
      波次不挑它们，但现货要先留出来，所以单独统计给 UI 显示「建议多件预留」。
    """
    text = (res or {}).get("text") or ""
    _err = _erp_err(text)          # v1.61：ERP 报错（会话失效等）不再被当成「0 单」
    if _err:
        return {"one": [], "multi_qty": 0, "error": _err}
    try:
        j = json.loads(text)
    except Exception:
        return {"one": [], "multi_qty": 0}
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
        return {"one": [], "multi_qty": 0}
    k0 = _ci(code)
    one, multi_qty = [], 0
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
        if _is_one_piece(o):
            one.append({"sid": sid, "qty": qty, "carrier": _carrier_of(o)})
        else:
            # 一单多件：不参与成波，但该编码的件数要预留
            multi_qty += qty.get(k0, 0)
    return {"one": one, "multi_qty": multi_qty}


def _query_form(code):
    """波次候选单查询的表单体（对齐 ERP 生成波次页的 queryWaveTradeByCondition）。"""
    return urllib.parse.urlencode({
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


def _query_raw(c, code):
    """按商家编码查该编码在火火火仓库的候选订单（可成波的一单一件 + 多件预留统计）。"""
    return _split_raw(_post(c, QUERY_PATH, _query_form(code),
                            "application/x-www-form-urlencoded"), code)


def _shelf_map():
    """本机货位索引：优先内存里的界面实例（kuaimai_scan 全局），否则从订单库现读。

    只读；拿不到就返回空字典（UI 会显示「货位索引为空」）。
    """
    try:
        import kuaimai_scan as KS
    except Exception:
        return {}
    try:
        app = (getattr(KS, "_WEB_STATE", None) or {}).get("app")
        m = getattr(app, "shelf_map", None) if app is not None else None
        if m:
            return m
    except Exception:
        pass
    try:
        return KS._load_shelf_map_now() or {}
    except Exception:
        return {}


def _shelf_info(code):
    """某编码本机货位 → {shelf_qty, bins, bins_text, shelf_index_empty}。

    在架 0 也保留货位（用户口径：只要有货位记录就显示出来）。
    """
    m = _shelf_map()
    if not m:
        return {"shelf_qty": 0, "bins": [], "bins_text": "", "shelf_index_empty": True}
    e = None
    try:
        import kuaimai_scan as KS
        e, _k = KS.dict_get_ci(m, code)
    except Exception:
        e = m.get(code)
    e = e or {}
    bins = []
    for b in (e.get("bins") or []):
        try:
            bins.append((str(b[0]), int(b[1] or 0)))
        except Exception:
            continue
    try:
        qty = int(e.get("shelf", 0) or 0)
    except Exception:
        qty = 0
    text = " / ".join("%s(%d)" % (b[0], b[1]) for b in bins)
    return {"shelf_qty": qty, "bins": bins, "bins_text": text, "shelf_index_empty": False}


def lookup(code):
    """某编码最大可生成件数（按快递分组）+ 候选订单明细 + 本机在架/货位 + 多件预留。

    只统计「一单一件」的候选单（`carriers` 是 {中通: n, 申通: m}，其他快递归入 other）；
    `multi_qty` 是被过滤掉的一单多件/组合单中该编码的件数合计（现货要先预留，不被波次吃掉）；
    `shelf_qty`/`bins`/`bins_text`/`shelf_index_empty` 是本机货位索引（在架 0 也保留货位）。
    """
    code = str(code or "").strip()
    if not code:
        return {"error": "缺少编码"}
    c = KP.open_cdp_page()
    try:
        raw = _query_raw(c, code)
    finally:
        c.close()
    if isinstance(raw, dict) and raw.get("error"):
        return {"error": raw["error"]}          # v1.61：ERP 报错直接告诉用户，别装成「0 单」
    orders = raw.get("one") or []
    multi_qty = int(raw.get("multi_qty") or 0)
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
    info = _shelf_info(code)
    return {"ok": True, "code": code, "max": total, "carriers": per, "other": other,
            "orders": len(orders), "det": det, "warehouseId": WAREHOUSE_ID,
            "multi_qty": multi_qty, "shelf_qty": info["shelf_qty"], "bins": info["bins"],
            "bins_text": info["bins_text"], "shelf_index_empty": info["shelf_index_empty"]}


SEARCH_PATH = "/trade/search"           # 打单页的订单搜索接口（「剩余时间」在这）
SEARCH_PAGE_SIZE = 500                  # 与 KP.fetch_orders_live 的默认 page_size 对齐


def _search_form(code):
    """打单页 /trade/search 的表单体（与 KP.fetch_orders_live 同源同参数）。"""
    return ("api_name=trade_search&queryId=77&pageSize=%d&field=timeoutActionTime&needOrder=1"
            "&useCompress=0&minutesAfterPaidOrderAreNotDisplayed=0&outerId=%s"
            % (SEARCH_PAGE_SIZE, urllib.parse.quote(code)))


def _priority(codes):
    """剩余时间（小时，可负）来源：打单页 /trade/search（与打单口径同源）。{sid: remain}

    并发查：所有编码一次全发出去（不再逐个串行），只取 sid + timeoutActionTime。
    """
    codes = [str(c) for c in (codes or []) if c]
    if not codes:
        return {}
    c = KP.open_cdp_page()
    try:
        resps = _post_many(c, SEARCH_PATH, [_search_form(cd) for cd in codes])
    finally:
        try:
            c.close()
        except Exception:
            pass
    now = time.time()
    rem = {}
    for resp in (resps or []):
        try:
            arr = (json.loads((resp or {}).get("text") or "").get("data") or {}).get("list") or []
        except Exception:
            arr = []
        for o in arr:
            if not isinstance(o, dict):
                continue
            s = str(o.get("sid") or "")
            if not s:
                continue
            r = None
            try:
                to = float(o.get("timeoutActionTime") or 0)
                if to > 1e12:
                    r = (to / 1000.0 - now) / 3600.0
            except Exception:
                r = None
            rem[s] = r
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
        # 并发查：所有编码一次全发出去（浏览器自己并发），不再逐个串行
        _ts = list(targets)
        _codes = [orig.get(t, t) for t in _ts]
        _resps = _post_many(c, QUERY_PATH, [_query_form(cd) for cd in _codes])
        for _i, t in enumerate(_ts):
            # 契约：_split_raw 返回 {"one": [一单一件候选], "multi_qty": 多件预留件数}
            # —— 这里必须取 "one"，不能再把整个返回值当列表遍历，
            # 否则遍历到字典的键（字符串）→ 'str' object has no attribute 'get'。
            _resp = _resps[_i] if _i < len(_resps) else {}
            _q = _split_raw(_resp, _codes[_i]) or {}
            if isinstance(_q, dict) and _q.get("error"):
                return {"error": _q["error"]}   # v1.61：会话失效等错误直接抛给用户
            _one = _q.get("one") if isinstance(_q, dict) else _q
            rows = [o for o in (_one or [])
                    if isinstance(o, dict) and _c_match(o.get("carrier"), carrier)]
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
        urg = KP.load_urgent_sids(fresh=True)
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


def manager_waves(page_no=1, page_size=20, c=None, warehouse_id=None):
    """ERP 网页「波次管理」列表（只读）：含未拣选波次，替代开放平台 verify_wave 回读。

    POST /trade/wave/manager/list（页面内 fetch，登录态）。
    c 传入则复用（**不要关它**），否则自己开 CDP 页并在结束时关闭。
    返回规范化 [{code,id,status,item_count,plan_num,picked_num,created_ms,express,tags}]；
    解析不出列表时返回 []。最新创建的排最前（服务端顺序，原样保留）。
    """
    own = c is None
    if own:
        c = KP.open_cdp_page()
    try:
        body = json.dumps({"pageNo": page_no, "pageSize": page_size,
                           "warehouseId": warehouse_id or WAREHOUSE_ID})
        res = _post(c, MANAGER_PATH, body, "application/json")
    finally:
        if own:
            try:
                c.close()
            except Exception:
                pass
    try:
        j = json.loads((res or {}).get("text") or "")
    except Exception:
        return []
    data = j.get("data")
    arr = None
    if isinstance(data, dict):
        for k in ("list", "rows", "records"):
            if isinstance(data.get(k), list):
                arr = data[k]
                break
    elif isinstance(data, list):
        arr = data
    if not isinstance(arr, list):
        return []
    out = []
    for w in arr:
        if not isinstance(w, dict):
            continue
        tags = w.get("tagNames")
        if isinstance(tags, str):
            tags = [t for t in tags.replace("，", ",").split(",") if t]
        out.append({
            "code": str(w.get("code") or ""),
            "id": w.get("id"),
            "status": w.get("status"),
            "item_count": _int(w.get("itemCount")),
            "plan_num": _int(w.get("planPickNum")),
            "picked_num": _int(w.get("pickedNum")),
            "created_ms": _int(w.get("created")),
            "express": w.get("expressName") or "",
            "tags": tags or [],
        })
    return out


def readback_new_wave(since_ms, item_count=None, page_no=1, page_size=20, c=None):
    """在「波次管理」列表里回读本次新建的波次（只读）。

    找 created_ms >= since_ms - 5000 的波次（created 是毫秒时间戳）；item_count 给了就再按它
    过滤；取第一条（列表最新创建排最前）。返回 {ok, wave_code, wave_id, item_count, created_ms}；
    找不到返回 {ok:False, error:"..."}。c 传入则复用（不关它）。
    """
    try:
        since = int(since_ms) - 5000
    except Exception:
        since = 0
    try:
        rows = manager_waves(page_no=page_no, page_size=page_size, c=c)
    except Exception as e:
        return {"ok": False, "error": "回读波次列表失败：%s" % str(e)[:150]}
    for w in rows:
        if _int(w.get("created_ms")) < since:
            continue
        if item_count is not None and _int(w.get("item_count")) != _int(item_count):
            continue
        return {"ok": True, "wave_code": w.get("code") or "", "wave_id": w.get("id"),
                "item_count": w.get("item_count"), "created_ms": w.get("created_ms")}
    return {"ok": False, "error": "波次列表里未找到本次新建的波次（created>=%s）" % since}


def create(items, carrier=""):
    """真正成波：先算挑单，再把全部 sids 一次 save（一个波次，只含选定的那一种快递）。

    save 后用**同一个 CDP 页**在「波次管理」列表回读新波次号（最多 3 次，等 2s/3s）；
    不回读开放平台 erp.trade.waves.query（只返回已拣选波次，新波次永远读不到）。
    """
    p = plan(items, carrier)
    if p.get("error"):
        return p
    sids = p.get("sids") or []
    if not sids:
        return {"error": "没有可成波的订单（可能已全部成波 / 已打印 / 该编码无可生成订单）"}
    c = KP.open_cdp_page()
    try:
        # v1.53e 货位库存：拣货位在架不足时**不直接挡**，改成「能拣多少先成多少」——
        # 按在架数收窄该编码件数并重新挑单；只有全部编码在架都是 0 时才报错。
        try:
            _need = {}
            for _c2 in (p.get("codes") or []):
                _k2 = str(_c2.get("code") or "")
                if _k2:
                    _need[_k2] = int(_c2.get("actual") or _c2.get("max") or 0)
            if _need:
                _st = pick_stock(c, list(_need.keys()))
                _capped = [(k3, _st.get(k3), n3) for k3, n3 in _need.items()
                           if _st.get(k3) is not None and _st.get(k3) < n3]
                if _capped:
                    _capq = {k3: max(0, int(_s3 or 0)) for k3, _s3, _n3 in _capped}
                    if all(v <= 0 for v in _capq.values()):
                        _o = dict(p)
                        _o["save_ok"] = False
                        _o["created"] = False
                        _o["stock_short"] = _capped
                        _o["error"] = "货位库存不足（拣货位 0 件，需先上架/补货）：" + "；".join(
                            "%s 在架 %s 件、需 %s 件" % (a2, b2, c2) for a2, b2, c2 in _capped)
                        return _o
                    _items2 = []
                    for _c4 in (p.get("codes") or []):
                        _k4 = str(_c4.get("code") or "")
                        _q4 = _capq.get(_k4, int(_c4.get("actual") or _c4.get("max") or 0))
                        if _k4 and _q4 > 0:
                            _items2.append({"code": _k4, "qty": _q4})
                    if _items2:
                        p2 = plan(_items2, str(p.get("carrier") or ""))
                        if (not p2.get("error")) and p2.get("sids"):
                            p2["capped"] = [{"code": k5, "was": w5, "now": _capq.get(k5, 0)}
                                            for k5, _s5, w5 in _capped]
                            p2["capped_note"] = "；".join(
                                "%s 按拣货位在架 %s 件成波（原 %s 件）" % (k5, _capq.get(k5, 0), w5)
                                for k5, _s5, w5 in _capped)
                            p = p2
                            sids = p.get("sids") or []
        except Exception:
            pass
        t0 = time.time() * 1000                  # save 前记时点：只认这之后新建的波次
        body = json.dumps({"warehouseId": WAREHOUSE_ID, "ruleId": "", "sids": sids,
                           "hasFilter": False})
        res = _post(c, SAVE_PATH, body, "application/json")
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
        # save 返回 success ≠ ERP 真的建出波次 → 必须在「波次管理」列表回读核对（最多 3 次）
        rb = {}
        for _wait in (0, 2, 3):
            if _wait:
                try:
                    time.sleep(_wait)
                except Exception:
                    pass
            try:
                rb = readback_new_wave(t0, len(sids), c=c)
            except Exception as e:
                rb = {"ok": False, "error": str(e)[:150]}
            if rb.get("ok"):
                break
        out["verify"] = rb
        if rb.get("ok"):
            out["wave_code"] = rb.get("wave_code")
            out["wave_id"] = rb.get("wave_id")
            out["created"] = True
        else:
            out["created"] = False
            out["verify_error"] = "ERP 未建出波次（可能权限/订单状态）"
        return out
    finally:
        c.close()


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
            "status": w.get("status"), "status_cn": status_cn(w.get("status"), w.get("pickEndTime")),
            "tradesCount": w.get("tradesCount"),
            "itemCount": w.get("itemCount"), "matched": inter,
            "missing": sorted(want - ws), "extra": len(ws - want)}


def _biz_window(minutes):
    from datetime import datetime, timedelta, timezone
    tz = timezone(timedelta(hours=8))
    now = datetime.now(tz)
    return {"pageNo": 1, "pageSize": 100,
            "start": (now - timedelta(minutes=minutes)).strftime("%Y-%m-%d %H:%M:%S"),
            "end": (now + timedelta(minutes=2)).strftime("%Y-%m-%d %H:%M:%S")}


def waves_list(caller, minutes=1440, page_size=50):
    """实时回读最近波次（开放平台 erp.trade.waves.query，只读）。

    caller(method, biz) 由主程序传入（api_call_authed）。只回波次级字段，不返回订单/客户信息。

    ⚠ 这个接口的返回体里**带每个波次的订单明细**：24h 窗口 × pageSize=100 时返回体会超过网关
    8MB 上限（实测 ~10.2MB），网关直接回 success=false / "Data length too large"。所以这里：
      1) **识别 success=false** —— 以前只判断"是不是 dict"，会把错误响应当成"成功但 0 个波次"，
         于是页面只显示「实时回读失败」却给不出任何原因；
      2) **响应过大就自动降 pageSize 重试**（100 → 50 → 25 → 12 → 10），绕开 8MB 上限。
    """
    # 依次尝试的 pageSize：从传入值开始每次减半，最小 10
    sizes, ps = [], int(page_size or 50)
    while ps >= 10:
        sizes.append(ps)
        ps //= 2
    if not sizes:
        sizes = [10]

    last_err = ""
    for ps in sizes:
        biz = _biz_window(minutes)
        biz["pageSize"] = ps
        try:
            res = caller("erp.trade.waves.query", biz)
        except Exception as e:
            return {"ok": False, "error": "回读失败：%s" % str(e)[:150]}
        if not isinstance(res, dict):
            return {"ok": False, "error": "回读返回异常"}
        if res.get("success") is False:
            msg = ("%s %s" % (res.get("code") or "", res.get("msg") or "")).strip()
            last_err = "回读失败：%s" % (msg[:180] or "接口返回 success=false")
            low = msg.lower()
            # 返回体超过网关上限 → 减小 pageSize 再试（pageSize 越小 → 返回体越小）
            if ("too large" in low) or ("data length" in low) or ("payload" in low):
                continue
            return {"ok": False, "error": last_err}
        out = []
        for w in (res.get("list") or []):
            out.append({
                "wave_code": w.get("code"), "wave_id": w.get("id"),
                "status": w.get("status"), "status_cn": status_cn(w.get("status"), w.get("pickEndTime")),
                "tradesCount": w.get("tradesCount"), "itemCount": w.get("itemCount"),
                "pickEndTime": w.get("pickEndTime"),
                "sids": [x.get("sid") for x in (w.get("list") or [])],
            })
        return {"ok": True, "waves": out, "total": res.get("total"), "pageSize": ps}
    return {"ok": False, "error": last_err or "回读失败：响应过大，已自动降档仍失败"}


# ---------- 一键拣完（v1.42）：分拣明细(只读) → 拣选完成(写) → 播种完成(写) → 回读状态 ----------
# 接口（本账号已验证有权限）：erp.trade.wave.sorting.query（读）/ erp.trade.wave.pick.hand（写）
#   / erp.trade.wave.seed（写）/ erp.trade.waves.query（读，复用上面的 waves_list）。
# 字段名一律以官方文档为准，不猜。写操作只在 do_write=True 时发生，默认只读。
def _int(v, d=0):
    """宽松取整（接口字段可能是 str/None），取不到返回默认值。"""
    try:
        return int(v)
    except Exception:
        try:
            return int(float(v))
        except Exception:
            return d


def _wm_id(wave_id):
    """波次ID 尽量转长整型（接口 waveId 是 long）；转不了就原样传。"""
    try:
        return int(wave_id)
    except Exception:
        return wave_id


def sorting(caller, wave_id):
    """erp.trade.wave.sorting.query（只读）：按波次查分拣明细并规范化。

    官方字段：list[].positionNo / list[].details[].{outerId,title,propertiesName,
    itemNum,pickedNum,matchedNum,multiCodes}，顶层 total。
    caller(method, biz) 由主程序传入（api_call_authed）；本函数绝不写任何东西。
    """
    try:
        res = caller("erp.trade.wave.sorting.query", {"waveId": _wm_id(wave_id)})
    except Exception as e:
        return {"ok": False, "error": "分拣明细查询失败：%s" % str(e)[:150]}
    if not isinstance(res, dict):
        return {"ok": False, "error": "分拣明细返回异常"}
    if res.get("success") is False:
        return {"ok": False,
                "error": str(res.get("msg") or res.get("error") or "分拣明细查询失败"),
                "code": res.get("code")}
    arr = res.get("list")
    if not isinstance(arr, list):
        d = res.get("data")
        if isinstance(d, dict) and isinstance(d.get("list"), list):
            arr = d.get("list")
    if not isinstance(arr, list):
        # 实测：该波次没有分拣明细时，success=true 且 total=0，响**省略 list 字段**。
        # 只有 success=false 才是错误；success 非 False 时把缺 list 当空结果（不报错）。
        if res.get("success") is not False:
            arr = []
        else:
            return {"ok": False, "error": "分拣明细查询失败",
                    "keys": sorted([str(k) for k in res.keys()])[:12]}
    positions, line_count = [], 0
    for p in arr:
        if not isinstance(p, dict):
            continue
        dets = []
        for it in (p.get("details") or []):
            if not isinstance(it, dict):
                continue
            dets.append({
                "outerId": str(it.get("outerId") or ""),
                "title": it.get("title") or "",
                "propertiesName": it.get("propertiesName") or "",
                "itemNum": _int(it.get("itemNum")),
                "pickedNum": _int(it.get("pickedNum")),
                "matchedNum": _int(it.get("matchedNum")),
                "multiCodes": it.get("multiCodes") or [],
            })
        line_count += len(dets)
        positions.append({"positionNo": p.get("positionNo"), "details": dets})
    tot = res.get("total")
    return {"ok": True, "wave_id": wave_id,
            "total": (len(positions) if tot is None else _int(tot, len(positions))),
            "positions": positions, "position_count": len(positions),
            "line_count": line_count,
            "field_names": ["positionNo", "details.outerId", "details.title",
                            "details.propertiesName", "details.itemNum",
                            "details.pickedNum", "details.matchedNum", "details.multiCodes"]}


def _seed_list(positions):
    """由 sorting 明细拼 seed 的 list（**仅供 seed() 封装或特殊场景；一键拣完默认不调 seed**）。

    应播种数量 = itemNum（应拣/应播）− matchedNum（已播种），负数按 0；
    同一位置同一 outerId 合并。返回 (list, 明细行数, 总件数, 未拣完行, 无待播种的位置, 合并次数)。
    """
    out, lines, total, not_picked, empty_pos, dup = [], 0, 0, [], [], 0
    for p in (positions or []):
        if not isinstance(p, dict):
            continue
        pos = p.get("positionNo")
        merged, order = {}, []
        for d in (p.get("details") or []):
            if not isinstance(d, dict):
                continue
            oid = str(d.get("outerId") or "")
            if not oid:
                continue
            need = _int(d.get("itemNum")) - _int(d.get("matchedNum"))
            if need < 0:
                need = 0
            if _int(d.get("pickedNum")) < _int(d.get("itemNum")):
                not_picked.append({"positionNo": pos, "outerId": oid,
                                   "pickedNum": _int(d.get("pickedNum")),
                                   "itemNum": _int(d.get("itemNum"))})
            if need <= 0:
                continue
            if oid in merged:
                merged[oid] += need
                dup += 1
            else:
                merged[oid] = need
                order.append(oid)
        dets = [{"outerId": o, "matchedNum": merged[o]} for o in order]
        if dets:
            out.append({"positionNo": pos, "details": dets})
            lines += len(dets)
            total += sum(x["matchedNum"] for x in dets)
        else:
            empty_pos.append(pos)
    return out, lines, total, not_picked, empty_pos, dup


def pick_hand(caller, wave_id):
    """erp.trade.wave.pick.hand（写）：波次标记「拣选完成」（订单随即进入等待验货）。

    ids=波次ID（可多个逗号拼接 ≤100）。这是「一键拣完」**唯一**会调用的写接口。
    返回 successIds / failedIds / failedMessages，原样不吞。
    """
    try:
        res = caller("erp.trade.wave.pick.hand", {"ids": str(wave_id)})
    except Exception as e:
        return {"ok": False, "error": "拣选完成（pick.hand）调用失败：%s" % str(e)[:150]}
    if not isinstance(res, dict):
        return {"ok": False, "error": "拣选完成返回异常"}
    succ = res.get("successIds") or []
    fail = res.get("failedIds") or []
    msgs = res.get("failedMessages") or res.get("failedMsg") or []
    ok = (res.get("success") is not False) and not fail and bool(succ)
    return {"ok": bool(ok), "successIds": succ, "failedIds": fail, "failedMessages": msgs,
            "code": res.get("code"), "msg": res.get("msg")}


def seed(caller, wave_id, list_obj):
    """erp.trade.wave.seed（写）：waveId(long) + list(JSON 字符串，内部双引号自动转义)。

    **一键拣完默认流程不调此接口**（播种回传是更靠后一步，会把状态推过头），仅作封装保留。
    list_obj 形如 [{"positionNo":1,"details":[{"outerId":"MN-milk","matchedNum":5}]}]。
    返回 success / errorList，原样不吞。
    """
    try:
        payload = json.dumps(list_obj or [], ensure_ascii=False)
    except Exception as e:
        return {"ok": False, "error": "list 序列化失败：%s" % str(e)[:150]}
    try:
        res = caller("erp.trade.wave.seed", {"waveId": _wm_id(wave_id), "list": payload})
    except Exception as e:
        return {"ok": False, "error": "播种完成（seed）调用失败：%s" % str(e)[:150]}
    if not isinstance(res, dict):
        return {"ok": False, "error": "播种完成返回异常"}
    errs = res.get("errorList") or res.get("errorlist") or []
    return {"ok": bool(res.get("success")) and not errs, "success": bool(res.get("success")),
            "errorList": errs, "code": res.get("code"), "msg": res.get("msg")}


def _read_wave(caller, wave_id, minutes=1440):
    """按波次ID回读当前状态（只读，复用 waves_list）。"""
    try:
        r = waves_list(caller, minutes=minutes, page_size=50)
    except Exception as e:
        return {"ok": False, "error": "状态回读失败：%s" % str(e)[:150]}
    if not r.get("ok"):
        return r
    for w in (r.get("waves") or []):
        if str(w.get("wave_id")) == str(wave_id):
            return {"ok": True, "wave": w}
    return {"ok": False, "error": "回读未找到该波次（近 %d 分钟）" % minutes,
            "waves": len(r.get("waves") or [])}


def finish_pick(caller, wave_id, do_write=False):
    """一键拣完：把波次在 ERP 里推成「拣选完成」（网页显示「等待验货」）。

    **只调 erp.trade.wave.pick.hand（ids=波次ID）；绝不调 erp.trade.wave.seed。**
    口径（实测波次 200913）：网页「等待验货」= 开放平台 status=1 且 pickEndTime 有值。

    do_write=False（默认）：只读回读波次，返回 波次号/订单数/件数/是否已拣/拣货完成时间
      以及「将执行：手动拣选(ids=波次号)」，明确不写。
    do_write=True：调 pick.hand → 回读 erp.trade.waves.query，把 pickEndTime 与状态一起返回
      （成功应看到「等待验货」）。
    任何失败/部分失败（failedIds / failedMessages / success=false）如实返回，绝不吞。
    """
    if wave_id in (None, "", 0):
        return {"ok": False, "error": "缺少波次ID（wave_id）"}

    # 只读回读当前波次（用于波次号/订单数/件数/是否已拣），不写
    st0 = _read_wave(caller, wave_id)
    w0 = (st0.get("wave") or {}) if st0.get("ok") else {}
    stt = wave_state(w0.get("status"), w0.get("pickEndTime"))
    plan = "手动拣选(ids=%s)" % wave_id

    if not do_write:
        out = {"ok": True, "preview": True, "write": False, "wave_id": wave_id,
               "wave_code": w0.get("wave_code"),
               "tradesCount": w0.get("tradesCount"), "itemCount": w0.get("itemCount"),
               "status": w0.get("status"), "status_cn": stt.get("status_cn"),
               "picked": stt.get("picked"), "pickEndTime": stt.get("pick_end_time"),
               "will_execute": plan,
               "note": "预览：以上为只读回读结果；确认后只会调 erp.trade.wave.pick.hand（%s），"
                       "把该波次标记为已拣（订单进入等待验货）。不调 seed，不可撤销。" % plan}
        if not st0.get("ok"):
            out["warning"] = "状态回读失败：%s" % st0.get("error")
        return out

    hand = pick_hand(caller, wave_id)
    out = {"ok": bool(hand.get("ok")), "preview": False, "write": True, "wave_id": wave_id,
           "will_execute": plan, "pick_hand": hand}
    if not hand.get("ok"):
        out["step"] = "pick.hand"
        out["error"] = ("拣选（pick.hand）未成功："
                        + str(hand.get("failedMessages") or hand.get("msg")
                              or hand.get("error") or "未知失败"))

    st = _read_wave(caller, wave_id)
    out["verify"] = st
    if st.get("ok"):
        w = st.get("wave") or {}
        s2 = wave_state(w.get("status"), w.get("pickEndTime"))
        out["wave_code"] = w.get("wave_code")
        out["tradesCount"] = w.get("tradesCount")
        out["itemCount"] = w.get("itemCount")
        out["status"] = w.get("status")
        out["status_cn"] = s2.get("status_cn")
        out["picked"] = s2.get("picked")
        out["pickEndTime"] = s2.get("pick_end_time")
    else:
        out["warning"] = "状态回读失败：%s" % st.get("error")
    return out


# ---------- 本机自有记录（只记「我自己生成过哪些波次号」，仅供记录页兜底） ----------
def records_path():
    base = getattr(KP, "BASE_DIR", "") or os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base, "wave_records.json")


def load_records():
    """读本机波次记录（没有/损坏时返回空表）。"""
    try:
        with open(records_path(), "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, list) else []
    except Exception:
        return []


def append_record(rec):
    """追加一条本机记录（按波次号去重，保留最近 200 条）。状态/内容一律实时回读，这里只是兜底索引。"""
    if not isinstance(rec, dict) or not rec.get("wave_code"):
        return
    try:
        rows = load_records()
        code = str(rec.get("wave_code"))
        rows = [r for r in rows if str((r or {}).get("wave_code") or "") != code]
        rows.append(rec)
        rows = rows[-200:]
        p = records_path()
        tmp = p + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(rows, f, ensure_ascii=False, indent=2)
        os.replace(tmp, p)
    except Exception:
        pass


# ---------- v1.46b 货位库存预检 ----------
SKU_LIST_PATH = "/trade/wave/checked/sku/list"


def pick_stock(c, codes):
    """各编码在**拣货位**的在架数（ERP「按商品生成」清单的 pickStock）。

    只返回查到的编码；查不到（不在清单里）就不出现该键，调用方按"不拦"处理。
    查库位失败时返回 {}（绝不让预检本身把成波搞挂）。
    """
    need = set(str(x) for x in (codes or []) if str(x or "").strip())
    if not need:
        return {}
    body = {"warehouseId": WAREHOUSE_ID, "conditionId": "", "itemNumUp": "", "itemNumDown": "",
            "sysSkuRemark": "", "sysItemRemark": "", "bindGoodsSectionCode": "",
            "titles": "", "skuPropertiesNames": "", "outerIdStr": "", "mainOuterId": "",
            "isAccurate": 0, "specifyShipperIds": "", "pageSize": 2000}
    try:
        res = _post(c, SKU_LIST_PATH, json.dumps(body), "application/json")
        rows = json.loads((res or {}).get("text") or "{}").get("data") or []
    except Exception:
        return {}
    out = {}
    for r in rows:
        oid = str(r.get("outerId") or "")
        if oid in need:
            try:
                out[oid] = int(r.get("pickStock") or 0)
            except Exception:
                pass
    return out
