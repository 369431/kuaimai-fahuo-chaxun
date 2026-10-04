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
import os
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
    has_pet = bool(str(pet).strip()) if pet is not None else False
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
            "status": w.get("status"), "status_cn": status_cn(w.get("status")),
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


def waves_list(caller, minutes=1440, page_size=100):
    """实时回读最近波次（开放平台 erp.trade.waves.query，只读）。

    caller(method, biz) 由主程序传入（api_call_authed）。只回波次级字段，不返回订单/客户信息。
    """
    biz = _biz_window(minutes)
    biz["pageSize"] = page_size
    try:
        res = caller("erp.trade.waves.query", biz)
    except Exception as e:
        return {"ok": False, "error": "回读失败：%s" % str(e)[:150]}
    if not isinstance(res, dict):
        return {"ok": False, "error": "回读返回异常"}
    out = []
    for w in (res.get("list") or []):
        out.append({
            "wave_code": w.get("code"), "wave_id": w.get("id"),
            "status": w.get("status"), "status_cn": status_cn(w.get("status")),
            "tradesCount": w.get("tradesCount"), "itemCount": w.get("itemCount"),
            "pickEndTime": w.get("pickEndTime"),
            "sids": [x.get("sid") for x in (w.get("list") or [])],
        })
    return {"ok": True, "waves": out, "total": res.get("total")}


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
        r = waves_list(caller, minutes=minutes, page_size=100)
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
