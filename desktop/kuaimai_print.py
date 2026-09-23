# -*- coding: utf-8 -*-
"""打单核心：选单规则（一单一件/加急/剩余时间优先）+ 取号 + 结果留痕。

规则（用户口径，见 docs/打单对接.md）：
 1) 已超时（剩余<0）绝对最优先；其次加急；再按剩余时间少优先
 2) 只打「一单一件」：订单里只有一个非赠品编码（7107-黑色M ✅ / 7107-黑色M,1166 ✅ / 7107-黑色M,7107-白色M ❌）
 3) 一次最多 500 单；取号分批（每批 ≤20 个 sids）
 4) 打印完成后**不自动标「已打」**，等人工确认

排除口径与 kuaimai_scan._is_excluded_item 一致：编码头 1166、名称含 买家秀/圆虹包。

自测：python desktop/kuaimai_print.py selftest
取号：python desktop/kuaimai_print.py getcode 6029578498234808
"""
import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request

try:                      # pythonw 下没有控制台，sys.stdout 可能是 None
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


# ============= 内联 CDP（打包后不依赖 tools/ 目录与子进程）=============
# 源码版原先从 tools/erp_probe.py 取 CDP/page_ws、从 tools/erp_api.py 取 fetch 封装；
# 冻结后 sys.executable 变成 exe 本身、tools/ 也不随包发出去 → 这里内联等价实现，
# 源码版与打包版共用同一份（tools/ 里的脚本仍保留给开发/抓包用）。
try:
    import websocket                       # websocket-client
except Exception:                          # pragma: no cover
    websocket = None

# ============= 分段计时埋点（只记时间，不改行为）=============
# 目的：把「提交可发 → 出纸」之间的黑盒段量出来（取号 / 拉单 / 勾选 / 等弹窗 / 核对各多少秒），
# 用数据决定该优化哪一段。结果以「耗时分解: …」写进打单日志（auto_print.log）与任务日志。
# 说明：纯累加字典，不参与任何判断分支；异常时也只是数字不准，不会影响打单。
_TM = {"t0": time.time(), "tick": time.time(), "stages": {}, "counts": {}, "marks": []}


def _tm_reset():
    """每次 do_print 开头清零（一次任务一份分解）。"""
    _TM["t0"] = time.time()
    _TM["tick"] = _TM["t0"]
    _TM["stages"] = {}
    _TM["counts"] = {}
    _TM["marks"] = []


def _tm(name):
    """距上一次计时点到现在，累加到 name（推进计时链）。"""
    now = time.time()
    _TM["stages"][name] = _TM["stages"].get(name, 0.0) + (now - _TM["tick"])
    _TM["tick"] = now
    return now


def _tm_add(name, secs):
    """显式加一段时间（用于函数内部局部测量，不动计时链）。"""
    try:
        _TM["stages"][name] = _TM["stages"].get(name, 0.0) + float(secs)
    except Exception:
        pass


def _tm_count(name):
    """计数（CDP 建页次数、队列读取次数等）——量化「反复建页」这类开销。"""
    _TM["counts"][name] = _TM["counts"].get(name, 0) + 1


def _tm_mark(label, secs):
    """记一个独立的时刻点（如弹窗到底等了多久）。"""
    try:
        _TM["marks"].append((str(label), float(secs)))
    except Exception:
        pass


def _tm_line():
    """拼成一行：总时长 + 各阶段耗时（降序）+ 计数 + 时刻点。"""
    tot = time.time() - _TM["t0"]
    parts = ["%s=%.1f" % (k, v)
             for k, v in sorted(_TM["stages"].items(), key=lambda kv: -kv[1])]
    if _TM["marks"]:
        parts.append("(" + " ".join("%s=%.1f" % m for m in _TM["marks"]) + ")")
    if _TM["counts"]:
        parts.append("{" + " ".join("%s=%d" % kv for kv in sorted(_TM["counts"].items())) + "}")
    return "耗时分解(总 %.1fs): %s" % (tot, " ".join(parts) or "（无分段）")


CDP_BASE = "http://127.0.0.1:9222"
_CDP_OP = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def erp_targets():
    """CDP 目标列表（本机自动化 Edge，9222）。"""
    return json.loads(_CDP_OP.open(CDP_BASE + "/json/list", timeout=5).read().decode("utf-8"))


def erp_page_ws(url_part="erpb.superboss.cc"):
    """取打单页的 CDP 目标；找不到页面时抛 SystemExit（与旧 page_ws 行为一致）。"""
    ts = erp_targets()
    for t in ts:
        if t.get("type") == "page" and url_part in (t.get("url") or ""):
            return t
    for t in ts:
        if t.get("type") == "page":
            return t
    raise SystemExit("没找到页面（自动化 Edge 没开？CDP 9222 不通？）")


class CDP(object):
    """极简 CDP 客户端：Runtime.evaluate + Page.navigate（等价 tools/erp_probe.CDP）。"""

    def __init__(self, ws_url):
        if websocket is None:
            raise RuntimeError("缺少 websocket-client，无法连 CDP（pip install websocket-client）")
        # Edge/Chrome 会拒绝带 Origin 的 CDP 连接 → suppress_origin
        self.ws = websocket.create_connection(ws_url, timeout=30, suppress_origin=True)
        self.i = 0

    def call(self, method, params=None):
        self.i += 1
        self.ws.send(json.dumps({"id": self.i, "method": method, "params": params or {}}))
        while True:
            msg = json.loads(self.ws.recv())
            if msg.get("id") == self.i:
                return msg

    def js(self, expr):
        r = self.call("Runtime.evaluate", {"expression": expr, "returnByValue": True,
                                           "awaitPromise": True})
        res = (r.get("result") or {}).get("result") or {}
        if r.get("result", {}).get("exceptionDetails"):
            return "JS异常: " + str(r["result"]["exceptionDetails"])[:200]
        return res.get("value")

    def close(self):
        try:
            self.ws.close()
        except Exception:
            pass


def open_cdp_page():
    """连上打单页（找不到页面抛 SystemExit，由调用方给友好提示）。"""
    _t_cdp = time.time()
    t = erp_page_ws()
    c = CDP(t["webSocketDebuggerUrl"])
    _tm_add("CDP建页", time.time() - _t_cdp)
    _tm_count("CDP建页次数")
    return c


def page_api(c, path, form, timeout=90000):
    """在页面里 fetch 调接口（等价 tools/erp_api.api）。"""
    js = """(async function(){
      const ac = new AbortController();
      const to = setTimeout(function(){ ac.abort(); }, %d);
      try {
        const r = await fetch(%s, {method:'POST', credentials:'include',
          headers:{'Content-Type':'application/x-www-form-urlencoded'},
          body:%s, signal: ac.signal});
        clearTimeout(to);
        const t = await r.text();
        return 'HTTP '+r.status+' '+t.slice(0, 6000);
      } catch(e) { return 'ERR '+String(e); }
    })()""" % (timeout, json.dumps(path), json.dumps(form))
    return c.js(js)


# ============= 数据目录（冻结时与主程序同一处）=============
def _pick_base_dir(preferred):
    """数据目录：冻结时优先 exe 旁（便携）；不可写则回落 %LOCALAPPDATA%\\KuaimaiScan。

    **必须与主程序 kuaimai_scan._pick_base_dir 同规则**：PRINT_MEMO（本机去重记忆）与
    EDGE_PROFILE（打单浏览器登录态）跟主程序数据文件放一起，两台机上才不会分裂。
    """
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

DB_CANDIDATES = [
    os.path.join(BASE_DIR, "kuaimai_data.db"),                # 主程序库：与主程序数据目录同处
    os.path.join(os.environ.get("LOCALAPPDATA", ""), "KuaimaiScan", "kuaimai_data.db"),
    os.path.join(os.path.expanduser("~"), "Desktop", "kuaimai_data.db"),
]
PRINT_MEMO = os.path.join(BASE_DIR, "printed_memory.json")
EDGE_PROFILE = os.path.join(BASE_DIR, "edge-automation")

# ============= 打单进度上报（只写文件，不改打印/勾选逻辑）=============
# 打单链路的关键节点把「正在打什么 / 勾到几成 / 第几屏 / 成功或失败」写进 print_progress.json，
# 电脑端「打单进度」面板读它 + scan_log.db 的 print_jobs 任务表 + auto_print.log 尾部。
# 生产环境 BASE_DIR = %LOCALAPPDATA%\KuaimaiScan，文件就在那里；源码调试时另镜像一份过去。
PROGRESS_NAME = "print_progress.json"
PROGRESS_FILE = os.path.join(BASE_DIR, PROGRESS_NAME)
_PROG = {}                          # 累积快照：每次只覆盖传入的字段


def _progress_paths():
    r"""进度文件落地路径（BASE_DIR 为主 + %LOCALAPPDATA%\KuaimaiScan 镜像一份）。"""
    out = [PROGRESS_FILE]
    try:
        alt = os.path.join(os.environ.get("LOCALAPPDATA") or "", "KuaimaiScan", PROGRESS_NAME)
        if os.path.dirname(alt) and os.path.abspath(alt) != os.path.abspath(PROGRESS_FILE):
            out.append(alt)
    except Exception:
        pass
    return out


def _write_json_atomic(path, obj):
    """原子写：先写临时文件再 os.replace（读者永远看到完整 JSON）；失败返回 False。"""
    try:
        tmp = "%s.tmp%d" % (path, os.getpid())
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False)
        os.replace(tmp, path)
        return True
    except Exception:
        return False


def report_progress(reset=False, **fields):
    """【进度上报】把打单链路的关键节点写进 print_progress.json。

    字段：ts(时间戳) / code(编码) / want(要打数量) / picked(挑到数量) /
          phase(开始|挑单|取号|设每页|扫描勾选|点打印|核对|完成|失败) /
          checked(已勾数) / page(第几屏) / msg(人类可读一句) / ok(True/False/None=进行中)

    纯加法：不影响打印逻辑、不改任何函数的签名与返回值；任何异常都吞掉
    （进度写不进去也不耽误打单）。
    """
    try:
        if reset:
            _PROG.clear()
        for k, v in (fields or {}).items():
            _PROG[k] = v
        _PROG["ts"] = time.time()
        snap = dict(_PROG)
    except Exception:
        return
    for p in _progress_paths():
        _write_json_atomic(p, snap)

MAX_BATCH = 500                     # 快麦单次上限
CODE_BATCH = 20                     # 每次取号调用最多带多少个 sids
EXCLUDE_CODE_HEADS = ("1166",)      # 与 kuaimai_scan 保持一致
EXCLUDE_NAME_KEYWORDS = ("买家秀", "圆虹包")
# 页面文本样式：'编码 编码 数量'（编码重复两次）→ 用它取 item
ITEM_RE = re.compile(r"(\S+)\s+\1\s+(\d+)")


def is_excluded_item(code, name=""):
    """占位/补偿类商品：编码头命中 或 名称含关键字 → 不计入件数。"""
    c = str(code or "")
    if c:
        head = re.split(r"[-\s（()）/,]", c)[0]
        if head in EXCLUDE_CODE_HEADS:
            return True
    n = str(name or "")
    return any(k in n for k in EXCLUDE_NAME_KEYWORDS)


def parse_items(text):
    """把订单行「商品明细」文本解析成 [{code, qty, gift}]（兜底用；优先用接口 JSON）。"""
    s = str(text or "").split("明细")[0]
    items = []
    for m in ITEM_RE.finditer(s):
        code, qty = m.group(1), int(m.group(2))
        items.append({"code": code, "qty": qty, "gift": is_excluded_item(code)})
    merged = {}
    for it in items:                        # 同编码合并（页面会重复渲染）
        k = it["code"]
        if k in merged:
            merged[k]["qty"] = max(merged[k]["qty"], it["qty"])
        else:
            merged[k] = dict(it)
    return list(merged.values())


def norm_items(raw):
    """把接口给的结构化明细统一成 [{code, qty, gift}]。

    接受：[{code/outerId/sysOuterId, num/qty, title/sysTitle}] 或已规范化后的列表
    """
    out = []
    for it in raw or []:
        if not isinstance(it, dict):
            continue
        code = str(it.get("code") or it.get("outerId") or it.get("sysOuterId") or "").strip()
        try:
            qty = int(it.get("qty") or it.get("num") or 1)
        except Exception:
            qty = 1
        name = str(it.get("title") or it.get("sysTitle") or it.get("shortTitle") or "")
        gift = bool(it.get("gift")) or (not code) or is_excluded_item(code, name)
        out.append({"code": code, "qty": qty, "gift": gift})
    return out


def is_single_item(items):
    """一单一件：只有一个非赠品编码，且数量为 1。返回 (是否可打, 编码或原因)。"""
    real = [i for i in (items or []) if not i.get("gift")]
    if not real:
        return False, "只有赠品/占位商品"
    if len(real) > 1:
        return False, "一单多件（%d 个编码：%s）" % (len(real), ",".join(i["code"] for i in real))
    if int(real[0].get("qty") or 1) != 1:
        return False, "单编码但数量 %s（非一单一件）" % real[0].get("qty")
    return True, real[0]["code"]


def parse_remain_hours(v):
    """剩余小时数：支持数值（接口 timeoutActionTime 算出）或文本 '48.0小时'/'-3.5小时'；负数=超时。"""
    if isinstance(v, (int, float)):
        return float(v)
    m = re.search(r"(-?\d+(?:\.\d+)?)\s*小时", str(v or ""))
    return float(m.group(1)) if m else 99999.0


def sort_key(order):
    """排序键：已超时(剩余<0)绝对最前 → 加急 → 剩余时间升序 → sid。

    负数剩余 = 已超时（平台可能处罚/自动取消），比加急更硬，故排在加急之前。
    实测 2026-09-23：288 个候选里 79 个负剩余单全部带加急，两规则暂不冲突；
    但加急标记来自本地库（可能滞后），负数剩余是接口实时算出，更可靠。
    """
    h = parse_remain_hours(order.get("remain"))
    return (0 if h < 0 else 1,                 # 已超时绝对最优先
            0 if order.get("urgent") else 1,   # 其次加急
            h,                                 # 再按剩余时间升序
            str(order.get("sid") or ""))


def pick_orders(orders, want, code=None, max_n=MAX_BATCH):
    """按规则挑单：返回 (要打的列表, 跳过的[(sid, 原因)])。

    want = 该编码要打的单数；code = 网页扫到的商家编码 —— **只打这个编码的单**
    （不是同一个编码的一律不打，即「一单一件且非赠品编码 == 扫到的编码」）。
    code 传空则不按编码过滤（仅自测/调试用）。
    """
    ok, skip = [], []
    limit = min(int(want or 0), max_n)
    for o in sorted(orders or [], key=sort_key):
        if len(ok) >= limit:
            break
        if str(o.get("sid")) in _printed_set():     # 本机打过 → 绝不再打（即便 ERP 次数为 0）
            skip.append((o.get("sid"), "本机已打过（去重记忆）"))
            continue
        if int(o.get("print_count") or 0) > 0:      # 已打印过 → 跳过
            skip.append((o.get("sid"), "已打印 %s 次" % o.get("print_count")))
            continue
        can, why = is_single_item(o.get("items") or [])
        if not can:
            skip.append((o.get("sid"), why))
            continue
        if code and str(why) != str(code):          # 不是同一个编码 → 不能打
            skip.append((o.get("sid"), "编码不符(%s)" % why))
            continue
        ok.append(o)
    return ok, skip


def selftest():
    cases = [
        ("7123-咖色L 7123-咖色L 1明细", True),                                   # 单件单
        ("7107-黑色M 7107-黑色M 1 1166 1166 1明细", True),                        # 主商品 + 1166 赠品
        ("7107-黑色M 7107-黑色M 1 7107-白色M 7107-白色M 1明细", False),            # 一单多件
        ("1166 1166 1明细", False),                                              # 只有赠品
        ("7107-黑色M 7107-黑色M 2明细", False),                                   # 数量 2
    ]
    bad = 0
    for text, want in cases:
        got, why = is_single_item(parse_items(text))
        if got != want:
            bad += 1
        print("%s %-46s -> %s (%s)" % ("OK " if got == want else "FAIL", text[:44], got, why))
    os_ = [{"sid": "B", "remain": "3小时", "items": parse_items("7107-黑色M 7107-黑色M 1明细")},
           {"sid": "A", "remain": "-2小时", "items": parse_items("7107-黑色M 7107-黑色M 1明细")},
           {"sid": "C", "remain": "50小时", "urgent": True, "items": parse_items("7107-黑色M 7107-黑色M 1明细")},
           {"sid": "D", "remain": "48小时", "print_count": 1, "items": parse_items("7107-黑色M 7107-黑色M 1明细")},
           {"sid": "F", "remain": "5小时", "outSid": "7703", "print_count": 0,
            "items": parse_items("7107-黑色M 7107-黑色M 1明细")}]
    order = [o["sid"] for o in sorted(os_, key=sort_key)]
    print("排序(期望 A,C,B,F,D):", order)   # A=-2h 已超时 → 排 C(加急) 之前
    if order != ["A", "C", "B", "F", "D"]:
        bad += 1
    ok3, skip3 = pick_orders(os_, 3)
    print("挑 3 单 → 要打:", [o["sid"] for o in ok3], " 跳过:", skip3)
    if [o["sid"] for o in ok3] != ["A", "C", "B"]:
        bad += 1
    ok4, skip4 = pick_orders(os_, 4)          # 优先取 A(超时),C(加急),B,F（D 已打印过，排最后）
    print("挑 4 单 → 要打:", [o["sid"] for o in ok4], " 跳过:", skip4)
    if [o["sid"] for o in ok4] != ["A", "C", "B", "F"]:
        bad += 1
    ok5, skip5 = pick_orders(os_, 5)      # 预发货：有运单号但没打印过 → 应该照打
    print("挑 5 单 → 要打:", [o["sid"] for o in ok5], " 跳过:", skip5)
    if "F" not in [o["sid"] for o in ok5]:
        bad += 1
    # 「不是同一个编码也不能打」：候选里混入别的编码，只应打出扫到的那个
    mix = [{"sid": "E1", "remain": "5小时", "items": parse_items("7107-黑色M 7107-黑色M 1明细")},
           {"sid": "E2", "remain": "1小时", "items": parse_items("7107-白色M 7107-白色M 1明细")},
           {"sid": "E3", "remain": "2小时", "items": parse_items("7123-咖色L 7123-咖色L 1明细")}]
    okc, skipc = pick_orders(mix, 5, code="7107-黑色M")
    print("按编码 7107-黑色M 挑 → 要打:", [o["sid"] for o in okc], " 跳过:", skipc)
    if [o["sid"] for o in okc] != ["E1"] or len(skipc) != 2:
        bad += 1
    print("自测结果:", "全部通过" if bad == 0 else ("%d 项失败" % bad))
    return bad


def getcode(sids):
    """在 ERP 页面里 fetch 取号（需自动化 Edge 窗口开着且已登录 ERP）。"""
    c = open_cdp_page()
    out = []
    for i in range(0, len(sids), CODE_BATCH):
        out.append(page_api(c, "/pt/waybill/code/get",
                            "sids=%s&api_name=pt_waybill_code_get" % ",".join(sids[i:i + CODE_BATCH])))
        time.sleep(0.4)
    c.close()
    return out


_CACHE = {}      # 轻量缓存：{(key): (ts, value)} —— 缩短重复点击的等待


ORDERS_TTL = 120      # 查单缓存时长（秒）：预取与重复点击共用


def _cache_get(key, ttl):
    hit = _CACHE.get(key)
    if hit and (time.time() - hit[0]) < ttl:
        return hit[1]
    return None


def _cache_put(key, val):
    _CACHE[key] = (time.time(), val)
    return val


# DB_CANDIDATES / PRINT_MEMO / EDGE_PROFILE 已在文件顶部定义：
# 与主程序同一规则（冻结时 exe 旁优先，不可写则 %LOCALAPPDATA%\KuaimaiScan）。


def load_printed_memory():
    """本机已打过的订单：{sid: {ts, outSid}}。ERP 打印次数滞后时靠它防重复出纸。"""
    try:
        with open(PRINT_MEMO, encoding="utf-8") as f:
            return json.load(f) or {}
    except Exception:
        return {}


def remember_printed(sids, outSids=None, keep_days=30):
    """记录「已打过」的订单（默认保留 30 天），并刷新缓存。"""
    mem = load_printed_memory()
    now = time.time()
    for s in sids:
        mem[str(s)] = {"ts": now, "outSid": str((outSids or {}).get(str(s)) or "")}
    cut = now - keep_days * 86400
    mem = {k: v for k, v in mem.items() if float((v or {}).get("ts") or 0) >= cut}
    try:
        os.makedirs(os.path.dirname(PRINT_MEMO), exist_ok=True)
        with open(PRINT_MEMO, "w", encoding="utf-8") as f:
            json.dump(mem, f, ensure_ascii=False)
    except Exception:
        pass
    _CACHE.pop("printed", None)
    return mem


def _printed_set():
    s = _cache_get("printed", 30)          # 本机打印记忆（30 秒缓存）
    if s is None:
        s = set(str(k) for k in load_printed_memory().keys())
        _cache_put("printed", s)
    return s


def load_urgent_sids():
    s = _cache_get("urgent", 60)          # 加急 sid 缓存 60 秒
    if s is not None:
        return s
    return _cache_put("urgent", _load_urgent_raw())


def _load_urgent_raw():
    """本地库里的加急订单 sid 集合（isUrgent 由主程序从开放 API 同步进 orders.urgent）。

    打单页的数据里**没有**加急标记，所以加急只能从本地库补（混合取数）。
    """
    import sqlite3
    for p in DB_CANDIDATES:
        if os.path.isfile(p):
            try:
                c = sqlite3.connect(p)
                rows = c.execute("select sid from orders where urgent=1").fetchall()
                c.close()
                return set(str(r[0]) for r in rows)
            except Exception:
                continue
    return set()


def fetch_orders_live(code, page_size=500):
    key = ("orders", str(code), int(page_size))
    hit = _cache_get(key, ORDERS_TTL)      # 预取 / 重复点击都复用
    if hit is not None:
        _tm_count("订单列表-命中缓存")
        return list(hit)
    # 按编码复用：同一次点击里「预览」用默认 page_size=500 查过，真打时 do_print 会按
    # want×3 换成更小的 page_size（10 张→60），键不同 → 原来会把刚查的结果白白丢掉再查一遍。
    # 更大的 page_size 结果天然覆盖更小的需求（都是同一编码的结果集），可直接复用。
    try:
        prev = _cache_get(("orders_by_code", str(code)), ORDERS_TTL)
        if prev and int(prev.get("page_size") or 0) >= int(page_size):
            rows = list(prev.get("rows") or [])
            _cache_put(key, rows)          # 顺手补上精确键
            return rows
    except Exception:
        pass
    """从打单页**实时**查该商家编码的订单（/trade/search + outerId，queryId=77）。

    返回 [{sid, items[{code,qty,gift}], remain(小时,可负), print_count, express, urgent}]
    """
    _t_ord = time.time()
    c = open_cdp_page()
    form = ("api_name=trade_search&queryId=77&pageSize=%d&field=timeoutActionTime&needOrder=1"
            "&useCompress=0&minutesAfterPaidOrderAreNotDisplayed=0&outerId=%s"
            % (page_size, urllib.parse.quote(code)))
    js = """(async function(){
      const r = await fetch('/trade/search', {method:'POST', credentials:'include',
        headers:{'Content-Type':'application/x-www-form-urlencoded'}, body:%s});
      return await r.text();
    })()""" % json.dumps(form)
    raw = c.js(js) or ""
    c.close()
    _tm_add("拉订单列表", time.time() - _t_ord)
    _tm_count("订单列表-网络拉取")
    try:
        arr = (json.loads(raw).get("data") or {}).get("list") or []
    except Exception as e:
        print("  (实时查单返回解析失败: %s，长度 %d)" % (str(e)[:60], len(raw)))
        return []
    now = time.time()
    urgent_set = load_urgent_sids()
    out = []
    for o in arr:
        items = []
        for it in (o.get("orders") or []):
            cd = str(it.get("outerId") or "")
            try:
                num = int(it.get("num") or 1)
            except Exception:
                num = 1
            gift = bool(it.get("giftNum")) or bool(it.get("platformGift")) or is_excluded_item(cd)
            items.append({"code": cd, "qty": num, "gift": gift})
        remain = None
        try:
            to = float(o.get("timeoutActionTime") or 0)
            if to > 1e12:
                remain = (to / 1000.0 - now) / 3600.0
        except Exception:
            remain = None
        out.append({"sid": str(o.get("sid") or ""), "short_id": str(o.get("shortId") or ""),
                    "items": items, "remain": remain,
                    "print_count": o.get("printCount"), "express": o.get("expressName"),
                    "urgent": str(o.get("sid") or "") in urgent_set})
    _cache_put(key, list(out))
    _cache_put(("orders_by_code", str(code)), {"page_size": int(page_size), "rows": list(out)})
    return out


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def prefetch(code):
    """后台预取某编码的待打单（扫码记录里出现就提前拉），点「打单」时秒开。"""
    try:
        return len(fetch_orders_live(code))
    except BaseException:
        return None


def do_print(code, want, dry_run=True, page_size=None, check_only=False, verdict=None):
    """一条龙：实时查单 → 挑单 →（预演 / 只勾选核对 / 真打：取号 → 页面勾选 → 打印 → 核对队列）。

    dry_run=True   只列单，不取号不出纸（给人工核对）
    check_only=True 不取号、**不点打印**，只走页面「设页数/对齐条件/勾选/核对」→ 验证链路用
    返回 (picked, skipped, logs) —— 保持 3 元组（3 个调用方按 3 元组解包，别改签名）。
    真打时：**只有核对通过才记去重记忆**；失败时 logs 首行是「！！打印失败：…」，调用方据此判失败。
    注意：**不自动标「已打」**，由人工确认出纸后自己标。
    """
    if page_size is None:
        # 拉**全量候选**（500 = ERP 单次上限）。原先按 want×3 缩短（50 张→150 单），
        # 但接口返回顺序**不是**剩余时间序（field/order 排序参数实测无效），负数/超时单
        # 散落在 150 名之后 → 没进候选池，后面按剩余时间排序也救不回来
        # （实测 2026-09-23：288 单里 79 个负剩余全是加急；截断到前 150 时挑出 50 单含 0 个负数）。
        # 一次请求即可（pageSize=500），不比 pageSize=150 多花时间；且与预览共用同一 page_size 缓存。
        page_size = MAX_BATCH
    _tm_reset()
    report_progress(reset=True, code=str(code), want=int(want or 0), picked=0, phase="开始",
                    checked=0, page=0, ok=None,
                    msg="开始打单：%s ×%s" % (code, want))
    orders = fetch_orders_live(code, page_size=page_size)
    _tm("拉订单列表(do_print)")
    picked, skipped = pick_orders(orders, want, code=code)
    _tm("挑单")
    logs = []
    report_progress(phase="挑单", picked=len(picked or []),
                    msg="挑到 %d 单（跳过 %d）" % (len(picked or []), len(skipped or [])))
    if picked:                              # 选单自证：一眼看出是否真按「超时优先、剩余时间升序」
        _rm = [parse_remain_hours(o.get("remain")) for o in picked]
        logs.append("挑单明细: %d 单，剩余时间 %.2f ~ %.2f 小时（升序）；其中已超时(负数) %d 单"
                    % (len(picked), min(_rm), max(_rm), len([x for x in _rm if x < 0])))
    if not picked:
        report_progress(phase="完成", ok=True, msg="没有可打的单（挑到 0 单）")
        return picked, skipped, logs
    sids = [o["sid"] for o in picked]
    shorts_all = [o.get("short_id") or "" for o in picked]
    if check_only:                          # 只勾选核对：不取号、不点打印
        v = verdict if isinstance(verdict, dict) else {}
        logs.append("只勾选验证（check_only）：不取号、不点打印")
        try:
            logs.extend(print_selected(code, sids, shorts_all, check_only=True, verdict=v))
        except BaseException as e:
            logs.append("！！只勾选验证失败：%s" % str(e)[:200])
        _cok = not any(str(x).startswith("！！") for x in logs)
        report_progress(phase="完成" if _cok else "失败", ok=bool(_cok),
                        checked=int(v.get("checked") or 0),
                        msg="只勾选验证%s：已勾 %s/%s" % ("完成" if _cok else "失败",
                                                     v.get("checked"), len(sids)))
        return picked, skipped, logs
    if dry_run:
        return picked, skipped, logs
    report_progress(phase="取号", checked=0, page=0,
                    msg="取号中：共 %d 单要取号" % len(sids))
    _tm("取号前")
    gc = getcode_stable(sids)
    _tm("取号")
    fresh = [s for s in sids if s in (gc.get("ok") or {})]
    fails = gc.get("fail") or {}
    # 预发货单：早就取了号（但还没打印）→ 不算失败，**直接进打印**
    have = [s for s in sids if s in fails and
            ("已有快递单号" in str(fails[s]) or "已有运单号" in str(fails[s]))]
    real_fail = {s: m for s, m in fails.items() if s not in have}
    ok_sids = fresh + have
    logs.append("取号: 新取 %d / 已有单号(预发货,直接打) %d / 失败 %d"
                % (len(fresh), len(have), len(real_fail)))
    report_progress(phase="取号", picked=len(fresh) + len(have),
                    msg="取号：新取 %d / 已有单号 %d / 失败 %d"
                        % (len(fresh), len(have), len(real_fail)))
    for s, msg in real_fail.items():
        logs.append("  未取到号 %s: %s" % (s, msg))
    for e in (gc.get("errors") or [])[:3]:
        logs.append("  批次错误: %s" % e)
    if not ok_sids:
        logs.append("没有可用运单号 → 不打印")
        report_progress(phase="失败", ok=False, msg="没有可用运单号 → 不打印")
        return picked, skipped, logs
    shorts = [o.get("short_id") or "" for o in picked if o["sid"] in ok_sids]
    # 页面勾选 + 点打印：**进程内执行**（不再 subprocess 调 tools/erp_print_run2.py，冻结后不可用）
    v = verdict if isinstance(verdict, dict) else {}
    try:
        _tm("打单页前")
        plog = print_selected(code, ok_sids, shorts, verdict=v)
        _tm("打单页(勾选+打印+核对)")
    except BaseException as e:
        logs.insert(0, "！！打印失败：打印链路异常 %s" % str(e)[:200])
        v.update({"clicked": False, "verified": False, "reason": "exception:%s" % str(e)[:120]})
        report_progress(phase="失败", ok=False, msg="打印链路异常：%s" % str(e)[:150])
        return picked, skipped, logs
    logs.append("打印链路: " + (" | ".join(str(x) for x in plog)[-400:] or "（无输出）"))
    for line in plog:
        logs.append("    " + str(line)[:200])
    # 成败判定：必须「点到了打印」**且**「核对确认离开未打印队列」才算成功
    # 只有「真的点了打印」**且**「打印后核对确认离开未打印队列」才算成功 → 才写去重记忆。
    # check_only（只勾选验证）与任何失败路径**都不写**（旧版 exe 无条件写 → 会把没打印的单误记）。
    printed_ok = ((not check_only) and bool(v.get("clicked"))
                  and (v.get("verified") is True) and (int(v.get("gone") or 0) > 0))
    if printed_ok:
        logs.append("打印结果: 成功（已离开未打印队列 %s/%s）" % (v.get("gone"), v.get("checked")))
        report_progress(phase="完成", ok=True, checked=int(v.get("checked") or 0),
                        msg="打单成功：已离开未打印队列 %s/%s" % (v.get("gone"), v.get("checked")))
        try:                               # 记入本机去重记忆（下次不再选中）
            remember_printed(ok_sids, gc.get("ok") or {})
            logs.append("已记入本机去重记忆：%d 单" % len(ok_sids))
        except Exception as e:
            logs.append("去重记忆写入失败：%s" % str(e)[:80])
    else:
        why = v.get("reason") or ("没点到打印" if not v.get("clicked") else "队列未变化")
        report_progress(phase="失败", ok=False, checked=int(v.get("checked") or 0),
                        msg="打单失败：%s" % str(why)[:150])
        logs.append("打印结果: 失败（%s）→ **未记去重记忆**，下次还会选中这些单" % str(why)[:80])
        if not any(str(x).startswith("！！打印失败") for x in logs):
            logs.insert(0, "！！打印失败：%s" % str(why)[:120])
    logs.append(_tm_line())
    return picked, skipped, logs


def getcode_parallel(sids, batch=CODE_BATCH, workers=5):
    """并发取号：在页面里用 Promise.all 开 workers 个协程跑分批请求（浏览器侧并发）。

    不用 Python 多线程是为了避开「多线程共用一条 CDP 连接会串消息」的坑。
    返回原始文本（'条数||结果1@@结果2...'）。
    """
    c = open_cdp_page()
    chunks = [list(sids[i:i + batch]) for i in range(0, len(sids), batch)] or [[]]
    js = """(async function(){
      const chunks = %s;
      const out = [];
      let idx = 0;
      async function worker(){
        while (idx < chunks.length){
          const my = chunks[idx++];
          try {
            const r = await fetch('/pt/waybill/code/get', {method:'POST', credentials:'include',
              headers:{'Content-Type':'application/x-www-form-urlencoded'},
              body:'sids=' + my.join(',') + '&api_name=pt_waybill_code_get'});
            out.push(await r.text());
          } catch(e){ out.push('ERR ' + String(e)); }
        }
      }
      await Promise.all(Array.from({length: Math.min(%d, chunks.length)}, worker));
      return out.length + '||' + out.join('\\n@@\\n');
    })()""" % (json.dumps(chunks), int(workers))
    raw = c.js(js) or ""
    c.close()
    return raw


def getcode_stable(sids, batch=CODE_BATCH, workers=3, retries=2):
    """稳定取号（推荐方案）。

    稳定性要点：
      1) Python 侧不开线程（共用一条 CDP 连接会串消息）；并发放在浏览器里
      2) 并发上限小（默认 3）、分批 ≤20 个 sids
      3) 每个请求带超时（45s）+ 失败批次指数退避重试（默认 2 次）
      4) 返回逐单结果，取不到号的单**不打印**，并如实报错（不静默）
    返回 {"ok": {sid: outSid}, "fail": {sid: 原因}, "errors": [批级错误]}
    """
    c = open_cdp_page()
    chunks = [list(sids[i:i + batch]) for i in range(0, len(sids), batch)] or [[]]
    js = """(async function(){
      const chunks = %s, RETRIES = %d, WORKERS = %d, TIMEOUT = 45000;
      const results = [];
      async function once(my){
        const ac = new AbortController();
        const to = setTimeout(function(){ ac.abort(); }, TIMEOUT);
        try {
          const r = await fetch('/pt/waybill/code/get', {method:'POST', credentials:'include',
            headers:{'Content-Type':'application/x-www-form-urlencoded'},
            body:'sids=' + my.join(',') + '&api_name=pt_waybill_code_get', signal: ac.signal});
          clearTimeout(to);
          const t = await r.text();
          if (r.status !== 200) throw new Error('HTTP ' + r.status);
          return {ok:true, text:t};
        } catch(e){ clearTimeout(to); return {ok:false, err:String(e)}; }
      }
      let idx = 0;
      async function worker(){
        while (idx < chunks.length){
          const my = chunks[idx++];
          let last = {ok:false, err:'未执行'};
          for (let i = 0; i <= RETRIES; i++){
            last = await once(my);
            if (last.ok) break;
            await new Promise(function(res){ setTimeout(res, 700 * (i + 1)); });
          }
          results.push({sids: my, ok: last.ok, text: last.text || '', err: last.err || ''});
        }
      }
      await Promise.all(Array.from({length: Math.min(WORKERS, chunks.length)}, worker));
      return JSON.stringify(results);
    })()""" % (json.dumps(chunks), int(retries), int(workers))
    raw = c.js(js) or ""
    c.close()
    ok, fail, errors = {}, {}, []
    try:
        arr = json.loads(raw)
    except Exception:
        return {"ok": ok, "fail": fail, "errors": ["返回非 JSON，长度 %d" % len(raw)]}
    for item in arr:
        if not item.get("ok"):
            errors.append("批次 %s 失败: %s" % (",".join(item.get("sids") or [])[:50], item.get("err")))
            continue
        try:
            d = (json.loads(item.get("text") or "{}").get("data") or {})
        except Exception:
            errors.append("批次返回解析失败")
            continue
        for x in d.get("successList") or []:
            ok[str(x.get("sid"))] = x.get("outSid")
        for x in d.get("failList") or []:
            fail[str(x.get("sid"))] = x.get("message") or "取号失败"
        for x in d.get("expressForwardFailList") or []:
            fail.setdefault(str(x.get("sid") or ""), str(x.get("message") or "转单失败"))
    return {"ok": ok, "fail": fail, "errors": errors}


PRINT_PAGE_TPL = ("https://erpb.superboss.cc/index.html#/trade/printv2/?queryId=77&module=printv2"
                  "&warehouseId=556677&order=asc&pageNo=1&pageSize=300&timeType=pay_time&expressStatus=0"
                  "&orderIdTypeSelect=mixKey&key=mainOuterId&queryType=1&skuOuterId=%s")
ROWS_JS = "document.querySelectorAll('div.module-list-item-inpage').length"
UNCHECK_JS = """
(function(){
 var n=0;
 document.querySelectorAll('div.module-list-item-inpage').forEach(function(r){
   var cb=r.querySelector('input[type=checkbox]');
   if(cb && cb.checked){ cb.click(); n++; }});
 return 'unchecked='+n+' 剩余勾选='+document.querySelectorAll('input[type=checkbox]:checked').length;
})()
"""
CHECK_JS = """
(function(keys){
  var rows = Array.from(document.querySelectorAll('div.module-list-item-inpage'));
  var found = [], n = 0;
  rows.forEach(function(r){
    var txt = r.innerText || '';
    var hit = keys.find(function(k){ return k && txt.indexOf(k) >= 0; });
    if (hit) {
      found.push(hit);
      var cb = r.querySelector('input[type=checkbox]');
      if (cb && !cb.checked) { cb.click(); n = n + 1; }
    }
  });
  var checkedRows = document.querySelectorAll('div.module-list-item-inpage input[type=checkbox]:checked').length;
  return 'clicked=' + n + '|found=' + found.join(',') + '|checkedRows=' + checkedRows;
})(%s)
"""
SAFETY_JS = """
(function(keys){
  var rows = Array.from(document.querySelectorAll('div.module-list-item-inpage'));
  var hitRows = 0;
  rows.forEach(function(r){
    var txt = r.innerText || '';
    if (keys.find(function(k){ return k && txt.indexOf(k) >= 0; })) {
      var cb = r.querySelector('input[type=checkbox]');
      if (cb && cb.checked) hitRows = hitRows + 1;
    }
  });
  return 'hitChecked=' + hitRows;
})(%s)
"""
# 旧选择器（div.trade-toolbar_list > a.toolbar-menu_item）实测已匹配不到 → 保留供对照，
# 真正用的是下面 click_print_button()：多策略找 + 真实鼠标点击 + 失败自证。
CLICK_PRINT_JS = """
(function(){
 var bar=document.querySelector('div.trade-toolbar_list');
 if(!bar) return 'no-toolbar';
 var items=Array.from(bar.querySelectorAll('a.toolbar-menu_item'));
 for(var k=0;k<items.length;k++){var s=(items[k].innerText||'').trim();
   if(s.indexOf('多平台极速打印')>=0){ items[k].click(); return 'clicked:'+s; }}
 return 'not-found';
})()
"""

# ---- 打印按钮定位（v1.23 原样遍历：div.trade-toolbar_list > a.toolbar-menu_item + 子串匹配）----
# 匹配文案顺序：多平台打印快递单（现名，v1.23 包里叫「多平台极速打印」已不再渲染）→ 多平台极速打印（旧名）→ 打印快递单；
# 只认**可见且未禁用**（offsetParent/尺寸/computedStyle/disabled/aria-disabled/class 里 is-disabled）。
# 命中后给它打标记 data-km-printbtn=1，后续按标记点击（避免再找一次又变了）。
PRINT_BTN_FIND_JS = r"""
(function(){
  function vis(e){
    if(!e) return false;
    if(e.disabled) return false;
    if(e.getAttribute && e.getAttribute('aria-disabled')==='true') return false;
    var cn=String(e.className||'')+' '+String((e.parentElement&&e.parentElement.className)||'');
    if(/\bdisabled\b|is-disabled/i.test(cn)) return false;
    var r=e.getBoundingClientRect();
    if(!(r.width>2 && r.height>2)) return false;
    var st=window.getComputedStyle(e);
    if(st && (st.display==='none'||st.visibility==='hidden'||parseFloat(st.opacity||'1')<0.05)) return false;
    return true;
  }
  // v1.23 原样：工具条内 a.toolbar-menu_item + innerText 子串匹配 + click()
  // （只把匹配文案补成现在的值——v1.23 包里写的是「多平台极速打印」，该文案现在工具条里已不存在）
  // 候选按优先级收集（工具条优先，全页兜底）：ERP 的打印入口文案/位置变过多次
  //   print_express_plus「多平台打印快递单」→ speed_print_btn「多平台极速打印▼」→ 可能还有「继续打印」✗
  // 不能只认一个名字，否则改名即 not-found
  var best=null;
  function consider(e, sc, how){
    if(!vis(e)) return;
    var r=e.getBoundingClientRect(), area=r.width*r.height;
    if(!best || sc>best.sc || (sc===best.sc && area<best.area)) best={sc:sc, how:how, area:area, el:e};
  }
  var bar=document.querySelector('div.trade-toolbar_list');
  var scope = bar || document;
  Array.from(scope.querySelectorAll('a.toolbar-menu_item,a[data-name]')).forEach(function(e){
    var t=String(e.innerText||'').replace(/\s+/g,'').trim();
    var dn=String((e.getAttribute&&e.getAttribute('data-name'))||'');
    if(!t || t.length>40) return;
    if(dn==='print_express_plus' || t.indexOf('多平台打印快递单')>=0) return consider(e, 60, '多平台打印快递单');
    if(dn==='speed_print_btn' || t.indexOf('多平台极速打印')>=0) return consider(e, 58, '多平台极速打印');
    if(t.indexOf('多平台继续打印')>=0) return consider(e, 56, '多平台继续打印');
    if(t.indexOf('继续打印')>=0) return consider(e, 54, '继续打印');
    if(t.indexOf('打印快递单')>=0) return consider(e, 50, '打印快递单');
  });
  var out={found:false};
  if(best){
    Array.from(document.querySelectorAll('[data-km-printbtn]')).forEach(function(x){x.removeAttribute('data-km-printbtn');});
    best.el.setAttribute('data-km-printbtn','1');
    var r=best.el.getBoundingClientRect();
    out.found=true; out.how=best.how; out.score=best.sc;
    out.tag=best.el.tagName;
    out.text=String(best.el.innerText||'').replace(/\s+/g,' ').trim().slice(0,30);
    out.dn=String((best.el.getAttribute&&best.el.getAttribute('data-name'))||'');
    out.cls=String(best.el.className||'').slice(0,60);
    out.x=Math.round(r.left+r.width/2); out.y=Math.round(r.top+r.height/2);
    out.w=Math.round(r.width); out.h=Math.round(r.height);
    out.vw=window.innerWidth; out.vh=window.innerHeight;
  }
  return JSON.stringify(out);
})()
"""

# 真实鼠标点击前先武装监听：事件若真的落到标记控件上，__km_print_clicked>0。
# 用来判「真实鼠标有没有被隐形浮层挡住」→ 没落到才退回 element.click()（**避免重复点两次打印**）。
PRINT_BTN_ARM_JS = r"""
(function(){
  window.__km_print_clicked=0;
  if(!window.__km_arm){
    window.__km_arm=1;
    document.addEventListener('click', function(e){
      var t=e.target;
      if(t && t.closest && t.closest('[data-km-printbtn]')) window.__km_print_clicked=(window.__km_print_clicked||0)+1;
    }, true);
  }
  return 'armed';
})()
"""

PRINT_BTN_JSCLICK_JS = r"""
(function(){
  var e=document.querySelector('[data-km-printbtn]');
  if(!e) return 'gone';
  var t=String(e.innerText||'').replace(/\s+/g,' ').trim().slice(0,30);
  e.click();
  return 'clicked:'+t;
})()
"""

# ③ 目标可能在下拉菜单里：点开可见的「打印 / 批量打印 / 打印面单」触发项（取最靠后那个）。
PRINT_MENU_OPEN_JS = r"""
(function(){
  function vis(e){
    var r=e.getBoundingClientRect();
    if(!(r.width>2 && r.height>2)) return false;
    var st=window.getComputedStyle(e);
    return !(st.display==='none'||st.visibility==='hidden');
  }
  var SEL='button,a,div,span,li,[role=button]';
  var cands=Array.from(document.querySelectorAll(SEL)).filter(function(e){
    if(!vis(e)||e.disabled) return false;
    var t=String(e.innerText||'').replace(/\s+/g,'').trim();
    if(!t||t.length>20) return false;
    return t==='\u6253\u5370'||t.indexOf('\u6279\u91cf\u6253\u5370')>=0||t.indexOf('\u6253\u5370\u9762\u5355')>=0;
  });
  if(!cands.length) return 'no-trigger';
  var el=cands[cands.length-1];
  el.click();
  return 'opened:'+String(el.innerText||'').replace(/\s+/g,' ').trim().slice(0,20);
})()
"""

# 失败自证①：工具条逐项列出（文本 + data-name + 位置；hidden 标注）——一眼看出按钮是不是改了名/被藏了
PRINT_BTN_TOOLBAR_JS = r"""
(function(){
  var bar=document.querySelector('div.trade-toolbar_list');
  if(!bar) return 'no-toolbar';
  var out=[];
  Array.from(bar.querySelectorAll('a.toolbar-menu_item')).forEach(function(e){
    var t=String(e.innerText||'').replace(/\s+/g,' ').trim();
    var dn=String(e.getAttribute('data-name')||'');
    var r=e.getBoundingClientRect();
    out.push(t+'{'+dn+'}'+((r.width>2&&r.height>2)?'':'(hidden)'));
  });
  return out.join(' ; ');
})()
"""

# 失败自证②：页面前 40 个有文字的可见可点元素 → tagName|前20字 innerText|className 前30字
PRINT_BTN_DUMP_JS = r"""
(function(){
  var SEL='button,a,div,span,li,[role=button],input';
  var n=0, out=[];
  Array.from(document.querySelectorAll(SEL)).forEach(function(e){
    if(n>=40) return;
    var r=e.getBoundingClientRect();
    if(!(r.width>2 && r.height>2)) return;
    var st=window.getComputedStyle(e);
    if(st && (st.display==='none'||st.visibility==='hidden')) return;
    var t=String(e.innerText||e.value||'').replace(/\s+/g,' ').trim().slice(0,20);
    if(!t) return;
    n++;
    out.push(e.tagName+'|'+t+'|'+String(e.className||'').slice(0,30));
  });
  return out.join(' ;; ');
})()
"""
DIALOG_JS = """
(function(){var o=[];Array.from(document.querySelectorAll('.el-dialog,.el-message-box,.ui-dialog,.layui-layer,.el-message'))
 .filter(function(x){return x.offsetParent!==null})
 .forEach(function(x){var bs=Array.from(x.querySelectorAll('button,a,input[type=button],.ui-dialog-btn,.ui-dialog-autofocus')).map(function(b){return (b.innerText||b.value||'').replace(/\\s+/g,'').trim()}).filter(Boolean).slice(0,8);
   o.push((x.innerText||'').replace(/\\s+/g,' ').slice(0,150)+' <<'+bs.join('/')+'>')});
 return o.length?o.join(' || '):'none';})()
"""
# 实测（2026-09-22）：点「多平台打印快递单」会先弹【打印设置】前置弹窗，
# 确认按钮文案是「打 印」（**中间带空格**）且是 <a> 不是 <button> → 必须去空格 + 放宽选择器，
# 否则永远 no-btn（旧版就卡在这，表现为“点了没反应/没出纸”）。
CONFIRM_JS = """
(function(){
  var SEL='.el-dialog,.el-message-box,.ui-dialog,.layui-layer';
  var ds=Array.from(document.querySelectorAll(SEL)).filter(function(x){return x.offsetParent!==null});
  var want=['打印','确认打印','开始打印','立即打印','继续打印','多平台继续打印','继续',
            '确定','确认','是'];
  for(var i=0;i<ds.length;i++){
    var bs=Array.from(ds[i].querySelectorAll('button,a,input[type=button],.ui-dialog-btn,.ui-dialog-autofocus'));
    for(var j=0;j<bs.length;j++){
      var s=String(bs[j].innerText||bs[j].value||'').replace(/\\s+/g,'').trim();
      if(!s) continue;
      for(var k=0;k<want.length;k++){
        if(s===want[k]){ bs[j].click(); return 'ok:'+s; }
      }
    }
  }
  return 'no-btn';
})()
"""


# ---------- 打单页控件读写（每页显示 / 过滤条件 / ERP 已勾选计数）----------
# 实测（viperp.superboss.cc）：
#   「每页显示」= element-ui 的 .trade-pageSizeInput，选项 50/100/200/300/500（点选项即重查）
#   「快递单打印状态」= 老式 .ui-select-expressStatus 外壳 + **隐藏的原生 select[name=expressStatus]**（0=未打印 1=已打印）
#   页脚「已勾选：订单数：N」= ERP 自己的模型计数（= 点打印真正会打的单数），比 DOM 计数更权威
MODEL_COUNT_JS = r"""
(function(){
  var el=document.querySelector('.module-trade-footer-container')||document.body;
  var m=(el.innerText||'').match(/订单数：\s*(\d+)/);
  return m?m[1]:'?';
})()
"""
PAGESIZE_OPEN_JS = r"""
(function(){
  var e=document.querySelector('.trade-pageSizeInput');
  if(!e) return 'no-control';
  var inp=e.querySelector('input')||e;
  var cur=String(inp.value||'');
  inp.click();
  return 'opened|cur='+cur;
})()
"""
PAGESIZE_FIND_JS = r"""
(function(){
  // 先按 element-ui 的 .trade-pageSizeInput 定位；找不到再按「每页显示」标签就近找 el-select。
  var e=document.querySelector('.trade-pageSizeInput'), how='class';
  if(!e){
    var labs=Array.from(document.querySelectorAll('span,label,b,div')).filter(function(n){
      return n.children.length===0 && ((n.innerText||'').replace(/\s+/g,'')==='每页显示');});
    for(var i=0;i<labs.length && !e;i++){
      var p=labs[i].parentElement;
      for(var d=0; p && d<3; d++, p=p.parentElement){
        var c=p.querySelector('.el-select,input,[class*=pageSize]');
        if(c){ e=(c.closest&&c.closest('.el-select'))||c; how='label'; break; }
      }
    }
  }
  if(!e) return 'no-control';
  var inp=e.querySelector('input')||e;
  return JSON.stringify({how:how, cur:String(inp.value||''), cls:String(e.className||'').slice(0,80)});
})()
"""
PAGESIZE_OPEN_ANY_JS = r"""
(function(){
  var e=document.querySelector('.trade-pageSizeInput');
  if(!e){
    var labs=Array.from(document.querySelectorAll('span,label,b,div')).filter(function(n){
      return n.children.length===0 && ((n.innerText||'').replace(/\s+/g,'')==='每页显示');});
    for(var i=0;i<labs.length && !e;i++){
      var p=labs[i].parentElement;
      for(var d=0; p && d<3; d++, p=p.parentElement){
        var c=p.querySelector('.el-select,input,[class*=pageSize]');
        if(c){ e=(c.closest&&c.closest('.el-select'))||c; break; }
      }
    }
  }
  if(!e) return 'no-control';
  var inp=e.querySelector('input')||e;
  inp.click();
  return 'opened|cur='+String(inp.value||'');
})()
"""
PAGESIZE_CUR_JS = ("(function(){var e=document.querySelector('.trade-pageSizeInput input');"
                   "return e?String(e.value||''):'';})()")
EL_DROPDOWN_ITEMS_JS = r"""
(function(){
  var ds=Array.from(document.querySelectorAll('.el-select-dropdown')).filter(function(x){
    var s=getComputedStyle(x); return s.display!=='none' && s.visibility!=='hidden';});
  if(!ds.length) return 'none';
  var d=ds[ds.length-1];
  return JSON.stringify(Array.from(d.querySelectorAll('.el-select-dropdown__item')).map(function(li){
    return (li.innerText||'').replace(/\s+/g,' ').trim();}));
})()
"""
EL_DROPDOWN_PICK_JS = r"""
(function(val){
  var ds=Array.from(document.querySelectorAll('.el-select-dropdown')).filter(function(x){
    var s=getComputedStyle(x); return s.display!=='none' && s.visibility!=='hidden';});
  if(!ds.length) return 'no-dropdown';
  var d=ds[ds.length-1];
  var items=Array.from(d.querySelectorAll('.el-select-dropdown__item'));
  for(var i=0;i<items.length;i++){
    if((items[i].innerText||'').trim()===String(val)){ items[i].click(); return 'clicked:'+val; }
  }
  return 'not-found:'+val;
})(%s)
"""
BODY_CLICK_JS = "(function(){document.body.click();return 'x';})()"
EXPRESS_READ_JS = r"""
(function(){
  var s=document.querySelector('select[name="expressStatus"]');
  var t=document.querySelector('.ui-select-expressStatus .ui-select-txt');
  if(!s) return JSON.stringify({found:false});
  return JSON.stringify({found:true, cur:String(s.value||''), shown:t?t.innerText:'',
                         dataVal:t?String(t.getAttribute('data-value')||''):'',
                         opts:Array.from(s.options).map(function(o){
                           return {v:String(o.value),t:(o.innerText||'').trim()};})});
})()
"""
EXPRESS_SET_JS = r"""
(function(want){
  var s=document.querySelector('select[name="expressStatus"]');
  if(!s) return 'no-select';
  s.value=String(want);
  s.dispatchEvent(new Event('change', {bubbles:true}));
  s.dispatchEvent(new Event('input', {bubbles:true}));
  return 'set:'+String(s.value);
})(%s)
"""
ONEPIECE_JS = r"""
(function(kw){
  var sels=Array.from(document.querySelectorAll('select'));
  for(var i=0;i<sels.length;i++){
    var s=sels[i];
    var hit=Array.from(s.options).filter(function(o){return (o.innerText||'').indexOf(kw)>=0;});
    if(hit.length){
      s.value=hit[0].value;
      s.dispatchEvent(new Event('change',{bubbles:true}));
      return 'set-native:'+String(s.name)+'='+(hit[0].innerText||'').trim();
    }
  }
  var wraps=Array.from(document.querySelectorAll('.el-select,.ui-select')).filter(function(e){
    return e.offsetParent!==null && (e.innerText||'').indexOf(kw)>=0;});
  if(wraps.length){
    var w=wraps[0];
    var hd=w.querySelector('.ui-select-hd')||w.querySelector('input')||w;
    hd.click();
    return 'found-widget:'+String(w.className).slice(0,50);
  }
  return 'none';
})(%s)
"""

PRINT_VERIFY_SECS = 60.0      # 打印后核对「是否离开未打印队列」的总等待（秒）

# 打单页的订单列表**只渲染可见窗口**（实测窗口高 675px → 只有 17 行 DOM，容器 scrollHeight 9511），
# 往下滚动时行会被回收/换出 → 不能只看一屏就判「勾够没」。这几个脚本都「边滚边扫」，
# 并用页面自己的「已勾选：订单数」做权威计数（= 点打印时真正会打的单数）。
TOTAL_JS = r"""
(function(){
  var m=(document.body.innerText||'').match(/共\s*(\d+)\s*条记录/);
  return m?m[1]:'?';
})()
"""
# 打单页「就绪」探针：页脚「共 N 条记录」已渲染 + 列表容器在 + 已在打单页。
# 原来靠固定 sleep(9)/sleep(8) 等加载；现在轮询这个，就绪即走（上限仍是原来的秒数）。
PAGE_READY_JS = r"""
(function(){
  var rows=document.querySelectorAll('div.module-list-item-inpage').length;
  var body=(document.body&&document.body.innerText)||'';
  var m=body.match(/共\s*(\d+)\s*条记录/);
  return JSON.stringify({rows:rows, total:(m?m[1]:'?'),
                         cont:!!document.querySelector('.J_TradeList_Body'),
                         href:(location.href||'')});
})()
"""
SCROLL_TOP_JS = ("(function(){var b=document.querySelector('.J_TradeList_Body');if(b)b.scrollTop=0;"
                 "(document.scrollingElement||document.documentElement).scrollTop=0;return 'top';})()")
SCROLL_SET_JS = r"""
(function(top){
  var cont = document.querySelector('.J_TradeList_Body');
  if (cont){
    cont.scrollTop = top;
    cont.dispatchEvent(new Event('scroll', {bubbles:true}));
    return JSON.stringify({st: cont.scrollTop, sh: cont.scrollHeight, ch: cont.clientHeight});
  }
  var w = document.scrollingElement || document.documentElement;
  w.scrollTop = top;
  return JSON.stringify({st: w.scrollTop, sh: w.scrollHeight, ch: w.clientHeight});
})(%d)
"""
ROWS_MAP_JS = r"""
(function(){
  var rows=Array.from(document.querySelectorAll('div.module-list-item-inpage'));
  return JSON.stringify(rows.map(function(r){
    var cb=r.querySelector('input[type=checkbox]');
    var b=cb?cb.getBoundingClientRect():null;
    return {sid:String(r.getAttribute('sid')||''),
            idx:parseInt(r.getAttribute('data-index')||'-1',10),
            checked:cb?!!cb.checked:null,
            x:b?Math.round(b.left+b.width/2):-1,
            y:b?Math.round(b.top+b.height/2):-1};
  }));
})()
"""


def _rows_now(c):
    """读当前渲染窗口的行：[{sid, idx, checked, x, y}]（拿不到给空）。"""
    try:
        return json.loads(str(c.js(ROWS_MAP_JS) or "[]")) or []
    except Exception:
        return []


def _row_by_idx(c, idx, tries=3):
    """滚到位后按 data-index 找行（拿不到返回 None）。"""
    for _ in range(max(1, int(tries))):
        for r in _rows_now(c):
            if int(r.get("idx", -1)) == int(idx) and int(r.get("x", -1)) > 0:
                return r
        time.sleep(0.12)
    return None


def _visible_row(c, idx):
    """按 data-index 找行，且 x/y 都在视口内（避开粘性表头/列）。找不到返回 None。"""
    try:
        vh = int(c.js("window.innerHeight||1000") or 1000)
    except Exception:
        vh = 1000
    for r in _rows_now(c):
        if int(r.get("idx", -1)) == int(idx):
            x, y = int(r.get("x", -1)), int(r.get("y", -1))
            if x > 0 and 12 < y < (vh - 12):
                return r
    return None


def _click_row_checkbox(c, idx, top, modifiers=0, logs=None):
    """滚到 top → **等目标行渲染出来** → 快速点击（不发 mouseMoved）→ 轮询自证已勾上。

    实测坑：扫完全表后滚回顶部，虚拟列表要一会儿才重新渲染出顶部行（固定等 0.12s 会找不到行）
    → 这里改为轮询等行出现；点击丢包/状态滞后还能重试；重复点 = 取消，所以每次都先看当前状态。
    拿不到行/始终没勾上都返回 False，由调用方清空回退（宁慢勿错）。
    """
    for _att in range(3):
        try:
            c.js(SCROLL_SET_JS % int(top))
        except Exception:
            pass
        r = None
        for _w in range(14):                 # 最多等 ~2s 让虚拟滚动渲染出该行
            time.sleep(0.15)
            r = _visible_row(c, idx)
            if r:
                break
        if not r:
            if logs is not None:
                logs.append("    第 %d 次：滚到 top=%s 后等 2s 仍看不到第 %d 行" % (_att + 1, top, idx))
            continue
        if r.get("checked"):                  # 已经勾上了（前一次其实成功）
            return True
        _real_mouse_click(c, r["x"], r["y"], modifiers=modifiers, move=False)
        for _w in range(9):                   # 轮询等状态落定（ERP 重渲染有延迟）
            time.sleep(0.12)
            cur = None
            for rr in _rows_now(c):
                if int(rr.get("idx", -1)) == int(idx):
                    cur = rr.get("checked")
                    break
            if cur:
                return True
        if logs is not None:
            logs.append("    第 %d 次：点了 (%d,%d) mod=%d 但没勾上" % (_att + 1, r["x"], r["y"], modifiers))
    return False


def _scan_tops(c):
    """扫全表用到的 scrollTop 列表（与 _tops 同口径）。"""
    geo = _cont_geo(c)
    ch = int(geo.get("ch") or 600)
    max_top = max(0, int(geo.get("sh") or 0) - ch)
    step = max(80, int(ch * 0.32))
    tops = list(range(0, max_top + 1, step))
    if max_top not in tops:
        tops.append(max_top)
    return tops


def shift_sweep_check(c, target_sids, expect, logs=None, on_scan=None,
                      max_segments=6):
    """用 ERP 的 shift 区间勾选快速勾中目标 sid（**只勾这些**）。

    实测（2026-09-23，viperp.superboss.cc 打单页）：
      · 普通点首行 + shift 点末行 = 勾中整个区间（连虚拟滚动窗口外的行也勾上）；
      · 区间内单行【普通点击】= 只切换该行，**不清空**已选（可用来取消多余）。
    做法：滚动读回全表 sid→data-index → 把目标切成连续段 → 每段「首行普通点 + 末行 shift 点」。
    返回 (命中 sid 集合, 点击次数)；判定不可用（目标缺失/分段太碎/中途拿不到行）返回 None，
    且返回前保证把已勾的**清干净**，由调用方回退逐屏扫描（宁慢勿错）。
    """
    tgt = [str(s) for s in (target_sids or []) if s]
    if len(tgt) < 2:
        return None
    lg = logs if logs is not None else []
    by_sid, by_idx = {}, {}
    _t0 = time.time()
    _tops = _scan_tops(c)
    _n_calls = 0
    _n_screens = 0
    for t in _tops:
        try:
            c.js(SCROLL_SET_JS % int(t))
        except Exception:
            pass
        time.sleep(0.12)
        _n_screens += 1
        for r in _rows_now(c):
            _n_calls += 1
            sid, idx = r.get("sid"), int(r.get("idx", -1))
            if sid and sid not in by_sid and idx >= 0:
                by_sid[sid] = {"idx": idx, "top": int(t)}
                by_idx.setdefault(idx, {"sid": sid, "top": int(t)})
        # 目标是**全部找到**才停（不是「见过的 sid 数 ≥ 目标数」——那样 60 个目标
        # 只要列表里任意 60 行就提前停，实测只会找到 10 个目标就回退 ✗）
        if all(s in by_sid for s in tgt):
            break
    lg.append("  shift 快速勾选：定位目标读了 %d/%d 屏、%d 行，找到 %d/%d，%.1fs"
              % (_n_screens, len(_tops), _n_calls, sum(1 for s in tgt if s in by_sid), len(tgt),
                 time.time() - _t0))
    miss = [s for s in tgt if s not in by_sid]
    if miss:
        lg.append("  shift 快速勾选：列表里没找到 %d 个目标 sid → 回退逐屏扫描" % len(miss))
        try:
            c.js(SCROLL_TOP_JS)
        except Exception:
            pass
        return None
    idxs = sorted(by_sid[s]["idx"] for s in tgt)
    segs = []
    for i in idxs:
        if segs and i - segs[-1][-1] <= 1:
            segs[-1].append(i)
        else:
            segs.append([i])
    if len(segs) > int(max_segments):
        lg.append("  shift 快速勾选：目标分成 %d 段（>%d）→ 收益不足，回退逐屏扫描"
                  % (len(segs), max_segments))
        try:
            c.js(SCROLL_TOP_JS)
        except Exception:
            pass
        return None
    clicks = 0
    screen = 0
    try:
        for g in segs:
            a, b = g[0], g[-1]
            if not _click_row_checkbox(c, a, by_idx[a]["top"], modifiers=0, logs=lg):
                lg.append("  shift 快速勾选：点第 %d 行没勾上 → 清空回退逐屏扫描" % a)
                sweep_uncheck(c, lg, tag="shift 失败清空")
                try:
                    c.js(SCROLL_TOP_JS)
                except Exception:
                    pass
                return None
            clicks += 1
            if b != a:
                if not _click_row_checkbox(c, b, by_idx[b]["top"], modifiers=8, logs=lg):
                    lg.append("  shift 快速勾选：shift 点第 %d 行没勾上 → 清空回退逐屏扫描" % b)
                    sweep_uncheck(c, lg, tag="shift 失败清空")
                    try:
                        c.js(SCROLL_TOP_JS)
                    except Exception:
                        pass
                    return None
                clicks += 1
            screen += 1
            if on_scan is not None:
                try:
                    on_scan(len(tgt), expect, clicks, screen)
                except Exception:
                    pass
        lg.append("  shift 快速勾选：%d 段一次勾中 %d 单（点击 %d 次，共用 %.1fs）"
                  % (len(segs), len(tgt), clicks, time.time() - _t0))
    except BaseException as e:
        lg.append("  shift 快速勾选异常：%s → 回退" % str(e)[:120])
        try:
            sweep_uncheck(c, lg, tag="shift 异常清空")
            c.js(SCROLL_TOP_JS)
        except Exception:
            pass
        return None
    return set(tgt), clicks


SCAN_KEYS_JS = r"""
(function(keys, done){
  var d = {};
  (done||[]).forEach(function(k){ d[k] = 1; });
  var rows = Array.from(document.querySelectorAll('div.module-list-item-inpage'));
  var hit = [], clicks = 0;
  rows.forEach(function(r){
    var t = r.innerText || '';
    for (var i=0;i<keys.length;i++){
      var k = keys[i];
      if (k && t.indexOf(k) >= 0){
        hit.push(k);
        if (!d[k]){                       // 同一单只点一次（重复点 = 反而取消勾选）
          var cb = r.querySelector('input[type=checkbox]');
          if (cb && !cb.checked){ cb.click(); clicks = clicks + 1; }
        }
        break;
      }
    }
  });
  return JSON.stringify({hit: hit, clicks: clicks});
})(%s, %s)
"""
UNCHECK_WINDOW_JS = r"""
(function(){
  var n = 0;
  Array.from(document.querySelectorAll('div.module-list-item-inpage input[type=checkbox]:checked'))
    .forEach(function(cb){ cb.click(); n = n + 1; });
  return String(n);
})()
"""


def _cont_geo(c):
    """列表容器几何：{st, sh, ch}（拿不到就给空）。"""
    try:
        return json.loads(str(c.js(SCROLL_SET_JS % 0) or "{}"))
    except Exception:
        return {}


def _tops(geo, down=True):
    ch = int(geo.get("ch") or 600)
    max_top = max(0, int(geo.get("sh") or 0) - ch)
    step = max(80, int(ch * 0.32))          # 列表虚拟滚动、DOM 只渲染可见窗口（≈17 行）→ 步长必须 ≪ 一屏，相邻两屏大量重叠才不漏行
    rng = list(range(0, max_top + 1, step)) if down else list(range(max_top, -1, -step))
    return rng or [0]


def _scan_once(c, keylist, found):
    """扫当前渲染窗口一次：返回 (命中列表, 新增命中, 本次点勾数)。"""
    try:
        d = json.loads(str(c.js(SCAN_KEYS_JS % (json.dumps(keylist),
                                                json.dumps(sorted(found)))) or "{}"))
    except Exception:
        d = {}
    hit = [str(x) for x in (d.get("hit") or [])]
    new = [k for k in hit if k not in found]
    return hit, new, int(d.get("clicks") or 0)


def sweep_check(c, keys, expect, logs=None, settle=0.15, rounds=2, on_scan=None,
                settle_max=0.35):
    """边滚边勾：列表只渲染可见窗口（约 17 行），必须逐屏滚动扫描才能勾满。

    向下扫一遍 → 不够再向上扫一遍（每轮方向交替）。
    settle 是**首试**等待：某屏没扫到新命中时，只对**同一屏**加长等待（settle_max）
    再扫一次，而不是整表重扫；第一遍就勾满 → 直接结束，不扫第二遍。
    返回 (命中 shortId 集合, 实际点击次数)。是否干净由调用方用 ERP「已勾选订单数」判。
    on_scan 是**可选**的进度回调：每屏扫完后调 on_scan(已勾数, 要勾数, 累计点击, 第几屏)，
    异常一律吞掉（进度上报失败不影响勾选）。
    """
    keylist = [str(k) for k in (keys or []) if k]
    found, clicks = set(), 0
    screen = 0
    if not keylist:
        return found, 0
    for rnd in range(max(1, int(rounds))):
        geo = _cont_geo(c)
        down = (rnd % 2 == 0)
        for t in _tops(geo, down=down):
            if expect and len(found) >= expect:
                break
            screen += 1
            c.js(SCROLL_SET_JS % t)
            time.sleep(settle)
            tried_long = False
            while True:                      # 同一屏自适应重扫（不等就往下滚 = 漏行）
                hit, new, n_clk = _scan_once(c, keylist, found)
                clicks += n_clk
                found.update(hit)
                if new or (expect and len(found) >= expect):
                    break
                if tried_long or float(settle_max) <= float(settle):
                    break
                tried_long = True
                time.sleep(float(settle_max))
            if on_scan is not None:          # 每屏扫完上报一次（拿不到影响打单）
                try:
                    on_scan(len(found), expect, clicks, screen)
                except Exception:
                    pass
        if logs is not None:
            logs.append("  第 %d 遍%s扫: 命中 %d/%s，累计点勾 %d"
                        % (rnd + 1, "向下" if down else "向上", len(found), expect, clicks))
        if expect and len(found) >= expect:  # 第一遍就全中 → 不再扫第二遍
            if logs is not None and rnd + 1 < max(1, int(rounds)):
                logs.append("  已勾满 → 跳过后续遍扫")
            break
    return found, clicks


def sweep_uncheck(c, logs=None, settle=0.15, tag="清空勾选", rounds=2, settle_max=0.3):
    """清空打单页全部勾选（滚完整列表，含未渲染窗口里的残余）。返回取消个数。

    settle 同 sweep_check 是首试等待：某屏读到 0 时，对**同一屏**加长等待再读一次
    （区分「真没勾选」与「还没渲染」），避免漏取消残余勾选。
    """
    total = 0
    for rnd in range(max(1, int(rounds))):
        geo = _cont_geo(c)
        for t in _tops(geo, down=(rnd % 2 == 0)):
            c.js(SCROLL_SET_JS % t)
            time.sleep(settle)
            tried_long = False
            while True:
                try:
                    n = int(str(c.js(UNCHECK_WINDOW_JS) or "0"))
                except Exception:
                    n = 0
                total += n
                if n or tried_long or float(settle_max) <= float(settle):
                    break
                tried_long = True
                time.sleep(float(settle_max))
    try:
        c.js(SCROLL_TOP_JS)
    except Exception:
        pass
    if logs is not None:
        logs.append("%s: 共取消 %d 个勾选（已滚完整列表）" % (tag, total))
    return total


def read_total(c):
    """页面上的「共 N 条记录」（读不到返回 None）。"""
    try:
        s = str(c.js(TOTAL_JS) or "")
    except Exception:
        return None
    return int(s) if s.isdigit() else None


def _rows(c):
    """当前渲染出来的订单行数（div.module-list-item-inpage）。"""
    try:
        return int(c.js(ROWS_JS) or 0)
    except Exception:
        return 0


def read_model_count(c):
    """ERP 自己的「已勾选：订单数」——点打印时真正会打的单数（读不到返回 None）。"""
    try:
        s = str(c.js(MODEL_COUNT_JS) or "")
    except Exception:
        return None
    return int(s) if s.isdigit() else None


def poll_rows(c, need, budget=20.0, do_scroll=False, interval=0.25):
    """轮询渲染行数，直到 ≥ need（need<=0 时只要 >0）；返回最终行数。"""
    t0 = time.time()
    rows = _rows(c)
    while rows < max(1, int(need or 0)) and (time.time() - t0) < budget:
        time.sleep(min(float(interval), max(0.01, budget - (time.time() - t0))))
        if do_scroll:
            try:
                c.js(SCROLL_ALL_JS)
            except Exception:
                pass
        rows = _rows(c)
    return rows


def _page_ready_ok(v):
    """PAGE_READY_JS 的就绪判据：在打单页 + 列表容器在 + 页脚条数已渲染（0 条也算就绪）。"""
    try:
        d = json.loads(str(v or "{}"))
    except Exception:
        return False
    if "/trade/printv2/" not in str(d.get("href") or ""):
        return False
    if not d.get("cont"):
        return False
    return str(d.get("total") or "?") != "?"


def _btn_found_ok(v):
    """PRINT_BTN_FIND_JS 的就绪判据：已找到可点的打印按钮。"""
    try:
        return bool(json.loads(str(v or "{}")).get("found"))
    except Exception:
        return False


def wait_until(c, probe_js, ok=None, interval=0.2, timeout=9.0, desc="", logs=None):
    """轮询 probe_js 直到「就绪」：ok(val) 为真 → 立即返回 (True, val, 用时)。

    用于把「固定 sleep(N) 等页面/控件就绪」换成「就绪即走」（上限仍是原来的 N 秒，
    超时就返回最后一次探测值，行为与原固定等待一致）。
    """
    def _default_ok(v):
        s = str(v if v is not None else "").strip().lower()
        return s not in ("", "none", "no-control", "not-found", "0", "{}", "[]", "?")
    okf = ok or _default_ok
    t0 = time.time()
    last = None
    while True:
        try:
            last = c.js(probe_js)
        except BaseException:
            last = None
        try:
            good = bool(okf(last))
        except Exception:
            good = False
        if good:
            break
        left = float(timeout) - (time.time() - t0)
        if left <= 0:
            break
        time.sleep(min(float(interval), left))
    dt = time.time() - t0
    try:
        good = bool(okf(last))
    except Exception:
        good = False
    if logs is not None:
        logs.append("  等就绪(%s): %s，用时 %.2fs"
                    % (desc or "页面", "就绪" if good else "超时兜底", dt))
    return good, last, dt


def set_page_size_max(c, logs):
    """把「每页显示」设为下拉里**数值最大**的一项（不写死 100/500）。

    返回 {"value": 最终显示值, "max_opt": 下拉最大数值(int|None), "ok": bool, "why": str}。
    先按 .trade-pageSizeInput 定位，找不到再按「每页显示」标签就近找；每一步都写 logs
    （定位方式 → 点开 → 选项 → 选中值），失败写明原因（调用方据此写「！！每页显示设置失败」）。
    """
    res = {"value": "", "max_opt": None, "ok": False, "why": ""}
    found = str(c.js(PAGESIZE_FIND_JS) or "")
    if found == "no-control":
        cur = str(c.js(PAGESIZE_CUR_JS) or "?")
        logs.append("  每页显示: 页面上没这个控件（.trade-pageSizeInput 与「每页显示」标签都没找到）→ 保持 %s" % cur)
        res.update({"value": cur, "ok": False, "why": "no-control"})
        return res
    try:
        info = json.loads(found)
    except Exception:
        info = {"how": "?", "cur": ""}
    logs.append("  每页显示: 定位到控件（方式=%s，当前=%s）" % (info.get("how"), info.get("cur")))
    opened = str(c.js(PAGESIZE_OPEN_ANY_JS) or "")
    logs.append("  每页显示: 点开 → %s" % opened[:60])
    if opened == "no-control":
        res.update({"value": str(c.js(PAGESIZE_CUR_JS) or ""), "ok": False, "why": "open-no-control"})
        logs.append("  每页显示: 打不开下拉 → 保持当前值")
        return res
    # 1.2s 内轮询等下拉选项渲染（就绪即走；超时同样保守地继续往下）
    wait_until(c, EL_DROPDOWN_ITEMS_JS,
               ok=lambda v: (str(v or "none") != "none" and len(json.loads(str(v))) > 0),
               interval=0.12, timeout=1.2, desc="每页显示下拉选项", logs=logs)
    raw = str(c.js(EL_DROPDOWN_ITEMS_JS) or "none")
    nums = []
    try:
        for t in (json.loads(raw) or []):
            t = str(t).strip()
            if t.isdigit():
                nums.append(int(t))
    except Exception:
        nums = []
    cur = str(c.js(PAGESIZE_CUR_JS) or "")
    if not nums:
        logs.append("  每页显示: 读不到选项（raw=%s）→ 保持 %s" % (raw[:60], cur))
        c.js(BODY_CLICK_JS)
        res.update({"value": cur, "ok": False, "why": "no-options"})
        return res
    mx = max(nums)
    logs.append("  每页显示: 选项 %s（最大 %d）" % (nums, mx))
    if cur == str(mx):
        logs.append("  每页显示: 已是最大 %d → 不再点" % mx)
        c.js(BODY_CLICK_JS)
        res.update({"value": cur, "max_opt": mx, "ok": True})
        return res
    logs.append("  每页显示: 当前 %s → 点选项 %d" % (cur, mx))
    c.js(EL_DROPDOWN_PICK_JS % json.dumps(str(mx)))
    wait_until(c, PAGESIZE_CUR_JS, ok=lambda v: str(v).strip() == str(mx),
               interval=0.12, timeout=2.0, desc="每页显示生效", logs=logs)
    now = str(c.js(PAGESIZE_CUR_JS) or "")
    if now != str(mx):                     # 没选中 → 关掉重开再点一次
        logs.append("  每页显示: 第 1 次没选中（现在=%s）→ 关掉重开再点一次" % now)
        c.js(BODY_CLICK_JS)
        time.sleep(0.4)
        c.js(PAGESIZE_OPEN_ANY_JS)
        wait_until(c, EL_DROPDOWN_ITEMS_JS,
                   ok=lambda v: (str(v or "none") != "none" and len(json.loads(str(v))) > 0),
                   interval=0.12, timeout=1.2, desc="每页显示下拉选项", logs=None)
        c.js(EL_DROPDOWN_PICK_JS % json.dumps(str(mx)))
        wait_until(c, PAGESIZE_CUR_JS, ok=lambda v: str(v).strip() == str(mx),
                   interval=0.12, timeout=2.0, desc="每页显示生效", logs=None)
        now = str(c.js(PAGESIZE_CUR_JS) or "")
    ok = (now == str(mx))
    res.update({"value": now, "max_opt": mx, "ok": ok, "why": "" if ok else "set-failed"})
    logs.append("  每页显示: 现在 = %s（%s）" % (now, ("已设为最大 %d" % mx) if ok else "！设置未生效"))
    return res


def align_filters(c, logs):
    """对齐打单页过滤条件：快递单打印状态=未打印；有「一单一件」就选上；其余下拉不动。

    返回 {"ok": bool, "why": str}；ok=False 时调用方**不点打印**
    （防止把「已打印过」的单再打一遍出纸）。
    """
    res = {"ok": True, "why": ""}
    try:
        info = json.loads(str(c.js(EXPRESS_READ_JS) or "{}"))
    except Exception:
        info = {}
    if not info.get("found"):
        logs.append("  快递单打印状态: 没找到控件 → 跳过（URL 已带 expressStatus=0）")
    else:
        want = None
        for o in (info.get("opts") or []):
            if "未打印" in str(o.get("t") or ""):
                want = str(o.get("v") or "")
                break
        if want is None:
            logs.append("  快递单打印状态: 下拉里没有「未打印」选项 → 跳过")
        elif str(info.get("cur")) == want:
            logs.append("  快递单打印状态: 已是「未打印」(v=%s)" % want)
        else:
            logs.append("  快递单打印状态: 现在 v=%s「%s」→ 设为 v=%s「未打印」"
                        % (info.get("cur"), info.get("shown"), want))
            c.js(EXPRESS_SET_JS % json.dumps(want))
            wait_until(c, EXPRESS_READ_JS,
                       ok=lambda v: (str((json.loads(str(v)) if str(v or "").startswith("{") else {})
                                         .get("cur")) == want),
                       interval=0.12, timeout=1.5, desc="快递单打印状态", logs=logs)
            try:
                info2 = json.loads(str(c.js(EXPRESS_READ_JS) or "{}"))
            except Exception:
                info2 = {}
            if str(info2.get("cur")) != want:
                res = {"ok": False, "why": "快递单打印状态设不动（现在 v=%s）" % info2.get("cur")}
            else:
                logs.append("  快递单打印状态: 已设为「未打印」")
    try:
        one = str(c.js(ONEPIECE_JS % json.dumps("一单一件")) or "none")
    except Exception:
        one = "err"
    if one == "none":
        logs.append("  一单一件: 页面没有该筛选控件 → 跳过（真正的把关在本地 pick_orders）")
    else:
        logs.append("  一单一件: %s" % one)
    # 单号类型（ui-select-orderIdTypeSelect）等其他下拉：**保持现状不动**
    return res


def fetch_unprinted_sids(code, page_size=500, max_pages=8):
    """实时拉该编码**仍在**「快递单未打印」(queryId=77) 队列里的 sid 集合（不走缓存）。

    返回 (sids_set, 已读条数, err, complete, total)。

    实测坑（2026-09-23）：队列可能远大于每页上限（实测 total=856 vs pageSize=500）→ 必须按
    ``data.total`` **翻页读全**；否则「不在返回列表」≠「已打印」，会把**打成功判成失败** ✗
    （实测：50 单已出纸、日志每次核对都是「已离开队列 50/50」，却因 n>=pageSize 判失败、
    连去重记忆都没记）。complete=True = 确实读全（拿到 total 且已覆盖）→ 调用方才能用
    「不在集合」判已打印；拿不到 total 一律 complete=False（保守）。
    """
    c = None
    all_sids, total, pages = set(), None, 0
    _t_q = time.time()
    try:
        c = open_cdp_page()
        for pno in range(1, max(1, int(max_pages)) + 1):
            form = ("api_name=trade_search&queryId=77&pageSize=%d&pageNo=%d&field=timeoutActionTime"
                    "&needOrder=1&useCompress=0&minutesAfterPaidOrderAreNotDisplayed=0&outerId=%s"
                    % (page_size, pno, urllib.parse.quote(code)))
            raw = c.js("""(async function(){
              const r = await fetch('/trade/search', {method:'POST', credentials:'include',
                headers:{'Content-Type':'application/x-www-form-urlencoded'}, body:%s});
              return await r.text();
            })()""" % json.dumps(form)) or ""
            try:
                data = (json.loads(raw).get("data") or {})
                arr = data.get("list") or []
            except Exception as e:
                if not pages:
                    return set(), 0, "返回解析失败(%s, 长度 %d)" % (str(e)[:40], len(raw)), False, None
                break
            pages += 1
            try:
                if data.get("total") is not None:
                    total = int(data.get("total"))
            except Exception:
                pass
            for o in arr:
                sid = str(o.get("sid") or "")
                if sid:
                    all_sids.add(sid)
            if len(arr) < int(page_size):        # 最后一页（没满）
                break
            if total is not None and len(all_sids) >= total:
                break
    except BaseException as e:
        _tm_add("读未打印队列", time.time() - _t_q)
        _tm_count("读未打印队列次数")
        return set(), 0, str(e)[:80], False, None
    finally:
        try:
            if c:
                c.close()
        except Exception:
            pass
    _tm_add("读未打印队列", time.time() - _t_q)
    _tm_count("读未打印队列次数")
    complete = bool(pages) and (total is not None) and (len(all_sids) >= total)
    return all_sids, len(all_sids), "", complete, total


def fetch_queue_sids_by_ids(sids, batch=100):
    """按 sid 精确查「快递单未打印」(queryId=77) 队列：只问这几个单**是否还在队列里**。

    返回 (still_set, err, complete, want_n)：still_set = 请求的 sid 里仍在队列的那些。

    实测（2026-09-23，队列 289 条）：
      ``sid=a,b,c`` 支持逗号批量（100 个一次 → 覆盖 100/100，1.04s）；
      不存在的 sid 被干净排除（total=0，不报错）；
      ``sids=`` / ``sidList=`` 是**无效参数**（会被忽略并返回全量，别用）。
      比全量翻页（289 条 3.85s）快约 7 倍，且待核对单越多优势越大 —— 核对本身也更快收敛。
    complete=True 表示每个 sid 都有明确结论（每组 total 与返回条数一致）→ 调用方才能用
    「不在集合」判已打印；任一组请求失败 → err 非空、complete=False（保守）。
    """
    want = [str(s) for s in (sids or []) if s]
    if not want:
        return set(), "", True, 0
    bs = max(1, int(batch))
    c, still, errs = None, set(), None
    _t_q = time.time()
    try:
        c = open_cdp_page()
        for i in range(0, len(want), bs):
            grp = want[i:i + bs]
            form = ("api_name=trade_search&queryId=77&pageSize=%d&pageNo=1&field=timeoutActionTime"
                    "&needOrder=1&useCompress=0&minutesAfterPaidOrderAreNotDisplayed=0&sid=%s"
                    % (max(50, len(grp) + 5), ",".join(grp)))
            raw = c.js("""(async function(){
              const r = await fetch('/trade/search', {method:'POST', credentials:'include',
                headers:{'Content-Type':'application/x-www-form-urlencoded'}, body:%s});
              return await r.text();
            })()""" % json.dumps(form)) or ""
            try:
                data = (json.loads(raw).get("data") or {})
                arr = data.get("list") or []
            except Exception as e:
                errs = "sid 查返回解析失败(%s, 长度 %d)" % (str(e)[:40], len(raw))
                break
            try:
                qtotal = int(data.get("total")) if data.get("total") is not None else None
            except Exception:
                qtotal = None
            got = set(str(o.get("sid") or "") for o in arr)
            got.discard("")
            still |= (got & set(grp))
            if qtotal is None or qtotal != len(got):
                errs = "sid 查结果不完整（total=%s，返回 %d，本组查了 %d）" % (qtotal, len(got), len(grp))
                break
    except BaseException as e:
        errs = str(e)[:80]
    finally:
        try:
            if c:
                c.close()
        except Exception:
            pass
    _tm_add("读未打印队列", time.time() - _t_q)
    _tm_count("读未打印队列次数")
    return still, (errs or ""), (errs is None), len(want)


def verify_printed(code, sids, logs=None, max_secs=PRINT_VERIFY_SECS, page_size=500, interval=2.0):
    """打印后核对：这批单**是否离开「快递单未打印」队列**（= 真出纸了）。

    返回 {"ok", "still", "gone", "total", "why"}。ok=False 时调用方必须判失败：
      - 全部仍在队列 → why="ERP 队列未变化"
      - 队列**没读全**（翻页失败/拿不到 total）→ 「不在列表」不代表已打印 → 也判失败（保守）
    （旧版用「条数 ≥ 每页即截断」判失败，队列 856 > 每页 500 时会把**打成功判成失败**，已改）
    """
    logs = logs if logs is not None else []
    want = set(str(s) for s in (sids or []) if s)
    total = len(want)
    if not total:
        return {"ok": False, "still": 0, "gone": 0, "total": 0, "why": "没有要核对的单"}
    t0 = time.time()
    last = {"ok": False, "still": total, "gone": 0, "total": total, "why": ""}
    while True:
        # 优先「按 sid 精确查」（实测快约 7 倍）；任何异常 → 回退全量翻页（保守，不据此判成功）
        cur, err, complete, n = fetch_queue_sids_by_ids(sorted(want), batch=100)
        mode = "sid精确查"
        if err:
            cur, n, err, complete, q_total = fetch_unprinted_sids(code, page_size=page_size)
            mode = "全量翻页"
        else:
            q_total = len(want)
        if err:
            last = {"ok": False, "still": total, "gone": 0, "total": total,
                    "why": "核对时读队列失败：%s" % err}
            logs.append("  打印后核对(+%.0fs): 读队列失败 %s" % (time.time() - t0, err))
        else:
            still, gone = want & cur, want - cur
            last = {"ok": (not still) and complete, "still": len(still), "gone": len(gone),
                    "total": total, "why": ""}
            logs.append("  打印后核对(+%.0fs)[%s]: 已离开队列 %d/%d，仍在队列 %d%s"
                        % (time.time() - t0, mode, len(gone), total, len(still),
                           "" if complete else "（未读全：队列共 %s 条，读到 %d 条）"
                           % (q_total if q_total is not None else "?", n)))
            if last["ok"]:
                last["why"] = "全部离开未打印队列"
                return last
            if (not still) and (not complete):
                last["why"] = ("队列未读全（共 %s 条，读到 %d 条）→ 无法确认是否出纸"
                                % (q_total if q_total is not None else "?", n))
        if (time.time() - t0) >= float(max_secs):
            if not last.get("why"):
                last["why"] = ("ERP 队列未变化" if last.get("still") == total
                               else "仍有 %d/%d 单在未打印队列" % (last.get("still"), total))
            return last
        time.sleep(float(interval))


# 通用滚动渲染：把可能存在的“懒加载/虚拟滚动”列表滚到底，让所有行都渲染出来
SCROLL_ALL_JS = ("(function(){var n=0;var els=[document.scrollingElement||document.documentElement];"
                 "document.querySelectorAll('div').forEach(function(d){"
                 "if(d.scrollHeight>d.clientHeight+20 && d.clientHeight>200){els.push(d);}});"
                 "els.forEach(function(e){e.scrollTop=e.scrollHeight;n++;});return String(n);})()")


def _goto_print_page(c, code, logs):
    """导航到打单页（处理 erpb→租户域名跳转丢失 #/ 路由）。返回 True/False。

    页面加载不再固定等 9s/8s，改为轮询就绪（页脚条数已渲染 + 列表容器在）就绪即走，
    上限仍是原来的 9s/8s（超时兜底行为与旧版一致）。
    """
    ok_page = False
    # 提速（实测 2026-09-23）：原来第一跳固定走 erpb.superboss.cc，它必然 302 到租户域名
    # （viperp.superboss.cc）并丢掉 #/ 路由 → 就绪判据永远不满足，白等满 9s 超时才重走。
    # 现在优先用「当前页面已有的租户域名」直连，跳过这一轮死等；失败再回退原逻辑。
    _tail = (PRINT_PAGE_TPL % urllib.parse.quote(code)).split("superboss.cc", 1)[-1]
    _urls = []
    try:
        _cur = str(c.js("location.href") or "")
        if "superboss.cc/index.html" in _cur:
            _base = _cur.split("/index.html", 1)[0]
            if _base.startswith("http") and _tail:
                _urls.append(_base + _tail)
                logs.append("直连当前租户: " + _base)
    except Exception:
        pass
    _urls.append(PRINT_PAGE_TPL % urllib.parse.quote(code))
    for _try in range(3):
        c.call("Page.navigate", {"url": _urls[min(_try, len(_urls) - 1)]})
        wait_until(c, PAGE_READY_JS, ok=_page_ready_ok, interval=0.25, timeout=9.0,
                   desc="加载打单页", logs=logs)
        href = str(c.js("location.href") or "")
        logs.append("筛单后 URL: " + href[:150])
        if "/trade/printv2/" in href:
            ok_page = True
            break
        # 跳域重定向（erpb→租户域名）会丢掉 #/... 路由 → 用当前实际域名重新走一次
        try:
            tail = (PRINT_PAGE_TPL % urllib.parse.quote(code)).split("superboss.cc", 1)[-1]   # 必须是**已填好编码**的版本，否则筛选参数会是字面的 %s
            base = href.split("/index.html", 1)[0]
            if base.startswith("http") and tail:
                c.call("Page.navigate", {"url": base + tail})
                wait_until(c, PAGE_READY_JS, ok=_page_ready_ok, interval=0.25, timeout=8.0,
                           desc="重走路由后加载", logs=logs)
                href2 = str(c.js("location.href") or "")
                logs.append("按当前租户重走路由: " + href2[:150])
                if "/trade/printv2/" in href2:
                    ok_page = True
                    break
        except Exception as e:
            logs.append("重走路由失败: %s" % str(e)[:80])
        logs.append("！页面不在打单页（%s）→ 重新导航（第 %d/3 次）" % (href[:80], _try + 1))
    return ok_page


def _chunk_pairs(sids, shorts, cap):
    """把 sids/shorts 按每批 cap 拆成 [(sids_i, shorts_i), ...]（保持一一对应）。"""
    n = max(1, int(cap or 0))
    out = []
    shorts = list(shorts or [])
    if len(shorts) < len(sids):
        shorts = shorts + [""] * (len(sids) - len(shorts))
    for i in range(0, len(sids), n):
        out.append((list(sids[i:i + n]), list(shorts[i:i + n])))
    return out or [(list(sids), list(shorts))]


def _real_mouse_click(c, x, y, modifiers=0, move=True):
    """CDP 真实鼠标点击（页面视口坐标）：mouseMoved → mousePressed → mouseReleased。

    modifiers: 8=Shift（ERP 打单页支持「首行 + shift 末行」区间勾选，实测 2026-09-23）。
    move=False 时**不发 mouseMoved**：实测本页 mouseMoved 每次卡 ~5s（pressed/released 仅 0.01s），
    而只发 pressed+released 仍然能正常勾选（含 shift 区间、再点取消），故勾选框走这条快路。
    **打印按钮不走快路**（那条路径只有真打才能验证，不冒风险）。
    """
    kinds = ("mouseMoved", "mousePressed", "mouseReleased") if move else ("mousePressed", "mouseReleased")
    for typ in kinds:
        p = {"type": typ, "x": int(x), "y": int(y),
             "button": "left", "clickCount": 1,
             "buttons": 1 if typ == "mousePressed" else 0}
        if modifiers:
            p["modifiers"] = int(modifiers)
        c.call("Input.dispatchMouseEvent", p)
        time.sleep(0.08)


def click_print_button(c, logs=None, attempts=3):
    """找并点「多平台打印快递单」（多策略 + 真实鼠标点击 + 失败自证）。

    每轮顺序：滚到顶 → 找（含可见/未禁用过滤）→ 真实鼠标点中心（mousePressed/mouseReleased，
    页面视口坐标）；坐标无效或事件没落到目标（被隐形浮层挡住）→ 退回 element.click()；
    没找到则尝试展开「打印」下拉再找。同一页面内最多重试 `attempts` 次（间隔 1s），**不重新导航**。
    返回 'clicked:<文本>'；失败返回 'not-found'，并把页面候选控件写进 logs（print-button:candidates=…）。
    """
    logs = logs if logs is not None else []
    last = "not-found"
    for i in range(max(1, int(attempts))):
        try:                                  # d. 先滚到顶（按钮可能需列表回顶才出现/可点）
            c.js(SCROLL_TOP_JS)
        except Exception:
            pass
        wait_until(c, PRINT_BTN_FIND_JS, ok=_btn_found_ok,
                   interval=0.15, timeout=(0.5 if i == 0 else 1.0), desc="找打印按钮", logs=None)
        try:
            info = json.loads(str(c.js(PRINT_BTN_FIND_JS) or "{}"))
        except Exception as e:
            info = {}
            logs.append("  找打印按钮第 %d 次：解析结果失败 %s" % (i + 1, str(e)[:80]))
        if info.get("found"):
            x, y = int(info.get("x") or 0), int(info.get("y") or 0)
            vw, vh = int(info.get("vw") or 0), int(info.get("vh") or 0)
            logs.append("  找到打印按钮（第 %d 次）: <%s> 「%s」[%s] data-name=%s cls=%s rect=(%s,%s %sx%s) 视口=%sx%s"
                        % (i + 1, info.get("tag"), info.get("text"), info.get("how"),
                           info.get("dn"), info.get("cls"), x, y, info.get("w"), info.get("h"), vw, vh))
            try:
                c.js(PRINT_BTN_ARM_JS)
            except Exception:
                pass
            real_ok = False
            if 0 < x < (vw or 10 ** 6) and 0 < y < (vh or 10 ** 6):
                try:
                    _real_mouse_click(c, x, y, move=False)   # 快路：跳过每次卡 ~5s 的 mouseMoved
                    logs.append("  真实鼠标点击 @(%d,%d)（无 mouseMoved 快路）" % (x, y))
                except Exception as e:
                    logs.append("  真实鼠标点击异常：%s" % str(e)[:100])
                wait_until(c, "window.__km_print_clicked||0", ok=lambda v: int(v or 0) > 0,
                           interval=0.1, timeout=1.2, desc="点击是否落到目标", logs=None)
                try:
                    real_ok = int(str(c.js("window.__km_print_clicked||0")) or "0") > 0
                except Exception:
                    real_ok = False
            else:
                logs.append("  坐标无效（x=%d,y=%d）→ 跳过真实鼠标点击" % (x, y))
            if real_ok:
                logs.append("  点击方式: 真实鼠标（事件已落到目标控件）")
                return "clicked:" + str(info.get("text") or "多平台打印快递单")
            try:
                r = str(c.js(PRINT_BTN_JSCLICK_JS))
            except Exception as e:
                r = "js-error:%s" % str(e)[:60]
            logs.append("  点击方式: 退回 element.click()（真实鼠标未落到目标控件）→ %s" % r)
            if r.startswith("clicked:"):
                return r
            last = "not-found"
        else:
            last = "not-found"
            logs.append("  找打印按钮第 %d 次: 未命中（%s）" % (i + 1, info.get("how") or "?"))
        if i < max(1, int(attempts)) - 1:
            try:                              # c. 可能藏在下拉菜单里 → 点开再找
                op = str(c.js(PRINT_MENU_OPEN_JS))
            except Exception as e:
                op = "err:%s" % str(e)[:60]
            logs.append("  第 %d 次没找到 → 尝试展开「打印」下拉: %s" % (i + 1, op))
            if op.startswith("opened:"):
                wait_until(c, PRINT_BTN_FIND_JS, ok=_btn_found_ok,
                           interval=0.15, timeout=0.8, desc="展开下拉后的打印按钮", logs=None)
                try:
                    info2 = json.loads(str(c.js(PRINT_BTN_FIND_JS) or "{}"))
                except Exception:
                    info2 = {}
                if info2.get("found"):
                    x, y = int(info2.get("x") or 0), int(info2.get("y") or 0)
                    vw, vh = int(info2.get("vw") or 0), int(info2.get("vh") or 0)
                    logs.append("  展开后找到: <%s> 「%s」rect=(%s,%s)"
                                % (info2.get("tag"), info2.get("text"), x, y))
                    try:
                        c.js(PRINT_BTN_ARM_JS)
                    except Exception:
                        pass
                    if 0 < x < (vw or 10 ** 6) and 0 < y < (vh or 10 ** 6):
                        try:
                            _real_mouse_click(c, x, y, move=False)   # 快路：同上
                            wait_until(c, "window.__km_print_clicked||0",
                                       ok=lambda v: int(v or 0) > 0, interval=0.1, timeout=1.2,
                                       desc="点击是否落到目标", logs=None)
                            if int(str(c.js("window.__km_print_clicked||0")) or "0") > 0:
                                return "clicked:" + str(info2.get("text") or "多平台打印快递单")
                        except Exception:
                            pass
                    try:
                        r = str(c.js(PRINT_BTN_JSCLICK_JS))
                    except Exception:
                        r = "gone"
                    if r.startswith("clicked:"):
                        return r
            wait_until(c, PRINT_BTN_FIND_JS, ok=_btn_found_ok, interval=0.15, timeout=1.0,
                       desc="重试前等打印按钮", logs=None)
    try:                                      # 2. 失败自证：工具条逐项 + 候选控件写进日志
        tb = str(c.js(PRINT_BTN_TOOLBAR_JS) or "")
    except Exception as e:
        tb = "toolbar-dump失败:%s" % str(e)[:80]
    logs.append("print-button:toolbar=" + tb[:2000])
    try:
        dump = str(c.js(PRINT_BTN_DUMP_JS) or "")
    except Exception as e:
        dump = "dump失败:%s" % str(e)[:80]
    logs.append("print-button:candidates=" + dump[:3000])
    return last


def _print_one_batch(c, code, sids, shorts, logs, v, wait_rows=12.0, check_only=False):
    """单批：对齐过滤 → 设「每页显示」最大 → 清空勾选 → 边滚边扫勾我们的单（严格核对）
    →（check_only 到此为止）→ 点「多平台打印快递单」→ 处理弹窗 → 核对 ERP 队列是否变化。

    假定页面**已在**打单页。返回 (ok, psinfo)；ok=False 时调用方立即停止（不再往下打）。
    """
    keys = [str(s) for s in (list(sids or []) + list(shorts or [])) if s]
    expect = len([s for s in (sids or []) if s]) or len([s for s in (shorts or []) if s])
    v["clicked"] = False
    v["verified"] = None
    # C. 对齐过滤条件（快递单打印状态=未打印；单号类型等其他下拉不动）
    _t_af = time.time()
    f = align_filters(c, logs)
    _tm_add("对齐过滤", time.time() - _t_af)
    if not f.get("ok"):
        logs.append("！！过滤条件没对上（%s）→ 终止（不出纸）" % f.get("why"))
        v["reason"] = "filter:%s" % f.get("why")
        report_progress(phase="失败", ok=False, msg="过滤条件没对上：%s" % f.get("why"))
        return False, {}
    # D. 「每页显示」设成下拉里数值最大的一项（不写死）；列表只渲染可见窗口，下面边滚边勾
    _t_ps = time.time()
    psinfo = set_page_size_max(c, logs)
    rows = poll_rows(c, 1, 8.0)
    _tm_add("设每页显示", time.time() - _t_ps)
    total = read_total(c)
    if rows <= 0:
        logs.append("！！设完每页显示后页面没有行 → 终止（不出纸）")
        v["reason"] = "no-rows-after-pagesize"
        report_progress(phase="失败", ok=False, msg="设完每页显示后页面没有行 → 终止")
        return False, psinfo
    cap = int(psinfo.get("max_opt") or 0)
    v["page_size"] = psinfo.get("value")
    v["page_size_max"] = cap or None
    v["page_size_ok"] = bool(psinfo.get("ok"))
    v["rows_window"] = rows
    v["rows_total"] = total
    logs.append("行数(渲染窗口): %d（每页显示=%s，选项最大=%s，列表共 %s 条，要打 %d 单）"
                % (rows, psinfo.get("value"), psinfo.get("max_opt"), total, expect))
    report_progress(phase="设每页", checked=0, page=1,
                    msg="每页显示=%s（选项最大=%s）；列表共 %s 条，本批要打 %d 单"
                        % (psinfo.get("value"), psinfo.get("max_opt"), total, expect))
    # 轮询渲染行数到 ≥ 要打数量（最多 ~20s）；上不去一定写清原因，绝不静默
    if expect and rows < expect:
        rows2 = poll_rows(c, expect, 20.0)
        if rows2 > rows:
            logs.append("  每页显示: 等页面重渲染 → 渲染行数 %d" % rows2)
            rows = rows2
            v["rows_window"] = rows
        if rows < expect:
            if cap and cap < expect:
                logs.append("  每页显示: 达到上限 %d < 要打 %d → 将分批（本批最多勾 %d 单）" % (cap, expect, cap))
            elif total is not None and cap and int(total) <= cap:
                logs.append("  每页显示: 列表 %s 条已全部载入本页；DOM 只渲染可见窗口 %d 行（列表是虚拟滚动）"
                            "→ 由「边滚边扫」逐屏勾选，不算失败" % (total, rows))
            elif not psinfo.get("ok"):
                logs.append("  ！！每页显示设置失败（行数仍 %d）" % rows)
            else:
                logs.append("  ！！轮询 20s 后渲染行数仍 %d < 要打 %d（页面渲染异常）" % (rows, expect))
    # E. 清空已有勾选（滚完整列表）→ 边滚边勾我们的单
    # 提速（实测 2026-09-23）：ERP 自己就报「已勾选订单数」。已经是 0 就没有残余要清，
    # 直接跳过整表滚动（一次全表扫描 ~10s）；只有确实有残余时才滚。
    _pre = None
    try:
        _pre = read_model_count(c)
    except Exception:
        _pre = None
    if _pre == 0:
        logs.append("  清空已有勾选: ERP 已勾选订单数=0 → 跳过整表清空（省一次全表滚动）")
    else:
        sweep_uncheck(c, logs, tag="清空已有勾选")
    c.js(SCROLL_TOP_JS)
    # 原固定 0.6s：改为轮询「已回到列表顶部」（上限 0.6s），就绪即走
    wait_until(c, SCROLL_SET_JS % 0, ok=lambda v: int((json.loads(str(v)) if str(v or "").startswith("{")
                                                      else {}).get("st") or 0) == 0,
               interval=0.1, timeout=0.6, desc="回到列表顶部", logs=None)
    report_progress(phase="扫描勾选", checked=0, page=0,
                    msg="逐屏扫描勾选：本批要勾 %d 单" % expect)

    def _on_scan(seen, exp, clicks, screen):     # 每屏扫完上报（进度，不影响勾选）
        report_progress(phase="扫描勾选", checked=int(seen), page=int(screen),
                        msg="逐屏扫描勾选：已勾 %d/%s（第 %d 屏）" % (seen, exp, screen))

    # 提速（实测 2026-09-23）：ERP 支持「首行 + shift 末行」区间勾选 → 目标成段时一次勾满，
    # 比逐屏滚动扫描快一个数量级；但真正勾到什么由 ERP 内部状态决定 → **必须**用
    # ERP「已勾选订单数」严格核对，不等就清空回退逐屏扫描（宁慢勿错）。
    found, n_click = None, 0
    if len(sids) >= 2:
        _t_sh = time.time()
        _sh = shift_sweep_check(c, sids, expect, logs=logs, on_scan=_on_scan)
        _tm_add("shift快速勾选", time.time() - _t_sh)
        if _sh is not None:
            _m = read_model_count(c)
            if _m == len(sids):
                found, n_click = _sh
                v["shift_fast"] = True
            else:
                logs.append("  shift 快速勾选：ERP 已勾 %s ≠ 目标 %d → 清空回退逐屏扫描"
                            % (_m, len(sids)))
                sweep_uncheck(c, logs, tag="shift 不符清空")
                try:
                    c.js(SCROLL_TOP_JS)
                except Exception:
                    pass
    if found is None:
        _t_sw = time.time()
        found, n_click = sweep_check(c, keys, expect, logs=logs, on_scan=_on_scan)
        _tm_add("逐屏勾选", time.time() - _t_sw)
    model = read_model_count(c)
    n_hit = len(found)
    v["checked"] = n_hit
    v["model_count"] = model
    # F. 严格核对：以 ERP 自己的「已勾选订单数」为准（= 点打印真正会打的单数）
    got = model if model is not None else n_hit
    logs.append("核对: 命中我们的单 %d / 要打 %d（点勾 %d）；ERP「已勾选订单数」=%s"
                % (n_hit, expect, n_click, model))
    report_progress(phase="扫描勾选", checked=n_hit,
                    msg="核对: 命中我们的单 %d/%d；ERP「已勾选订单数」=%s" % (n_hit, expect, model))
    if got <= 0:
        logs.append("未勾到我们的单 → 跳过打印（保险生效）")
        sweep_uncheck(c, logs, tag="清空残余勾选")
        v["reason"] = "none-checked"
        report_progress(phase="失败", ok=False, msg="未勾到我们的单 → 跳过打印")
        return False, psinfo
    if expect and got != expect:
        logs.append("！！ERP 已勾选订单数 %s ≠ 要打 %d → 为防多勾/少勾，不点打印" % (got, expect))
        sweep_uncheck(c, logs, tag="清空残余勾选")
        v["reason"] = "mismatch"
        report_progress(phase="失败", ok=False, checked=int(got or 0),
                        msg="ERP 已勾选订单数 %s ≠ 要打 %d → 不点打印" % (got, expect))
        return False, psinfo
    if check_only:
        logs.append("check_only：核对通过，**不点打印**（ERP 已勾 %s 单）" % got)
        sweep_uncheck(c, logs, tag="清空勾选（验证不留残余）")
        v["reason"] = "check-only"
        v["verified"] = None
        report_progress(phase="完成", ok=True, checked=int(got or 0),
                        msg="check_only：核对通过，不点打印（已勾 %s/%s）" % (got, expect))
        return True, psinfo
    # G. 点一次「多平台极速打印」+ 处理弹窗
    report_progress(phase="点打印", checked=int(got or 0),
                    msg="点「多平台打印快递单」（已勾 %s/%s）" % (got, expect))
    _t_cl = time.time()
    clicked = click_print_button(c, logs)
    _tm_add("点打印", time.time() - _t_cl)
    logs.append("点打印: " + clicked)
    v["clicked"] = clicked.startswith("clicked:")
    if not v["clicked"]:
        v["reason"] = "print-button:%s" % clicked
        logs.insert(0, "！！打印失败：没点到「多平台打印快递单」（%s）" % clicked)
        report_progress(phase="失败", ok=False, msg="没点到「多平台打印快递单」：%s" % clicked)
        return False, psinfo
    seen_dialog = False
    t_dlg = time.time()
    # 提速（实测 2026-09-23 任务 #11/#12）：**按按钮名决定要不要等**。
    #   「多平台极速打印」→ 从不弹窗，只做一次 1.5s 首检（实测占了 6.0s）；
    #   「多平台打印快递单」→ 实测 +1.5s 弹窗，上限 5s。
    # 循环按「剩余时间」取 min(1.5, 剩余)，避免进循环尾部多等一轮而超出上限。
    # 兜底不变：真没出纸 → 后面的「核对未打印队列」判失败 → 回队列退避重试。
    _dlg_max = 1.5 if "极速" in str(clicked) else 5.0
    while True:
        _left = _dlg_max - (time.time() - t_dlg)
        if _left <= 0:
            break
        got, d, _dt = wait_until(c, DIALOG_JS, ok=lambda v: str(v or "none") != "none",
                                 interval=0.25, timeout=min(1.5, _left),
                                 desc="等打印弹窗", logs=None)
        if not got:
            continue
        seen_dialog = True
        logs.append(" +%.1fs: %s" % (time.time() - t_dlg, d))
        logs.append("   点了: " + str(c.js(CONFIRM_JS)))
        # 原固定 sleep(2)：改为轮询等弹窗关掉（上限 2s）
        wait_until(c, DIALOG_JS, ok=lambda v: str(v or "none") == "none",
                   interval=0.2, timeout=2.0, desc="等弹窗关闭", logs=None)
    if not seen_dialog:
        logs.append("  （%.1fs 内没看到弹窗——可能直接出纸，也可能没响应）" % _dlg_max)
    _tm_add("等弹窗", time.time() - t_dlg)
    _tm_mark("弹窗等待", time.time() - t_dlg)
    # H. 打印后核对：这批单是否离开「快递单未打印」队列（≠ 离开 = 没真出纸）
    report_progress(phase="核对", checked=int(v.get("checked") or 0),
                    msg="打印后核对：等这批单离开「未打印」队列…")
    _t_vf = time.time()
    r = verify_printed(code, list(sids or []) or [], logs=logs, max_secs=PRINT_VERIFY_SECS,
                       page_size=500)
    _tm_add("核对队列", time.time() - _t_vf)
    v["verified"] = bool(r.get("ok"))
    v["still_unprinted"] = r.get("still")
    v["gone"] = r.get("gone")
    v["reason"] = r.get("why") or ""
    logs.append("打印后核对结论: %s（已离开队列 %s/%s）" % (
        "成功" if r.get("ok") else "失败", r.get("gone"), r.get("total")))
    report_progress(phase="完成" if r.get("ok") else "失败", ok=bool(r.get("ok")),
                    checked=int(v.get("checked") or 0),
                    msg="打印后核对%s：已离开未打印队列 %s/%s"
                        % ("成功" if r.get("ok") else "失败", r.get("gone"), r.get("total")))
    if not r.get("ok"):
        logs.insert(0, "！！打印失败：%s" % (r.get("why") or "ERP 队列未变化"))
        return False, psinfo
    return True, psinfo


def print_selected(code, sids, shorts=None, wait_rows=12.0, check_only=False, verdict=None):
    """在打单页筛单 → 对齐条件 → 设「每页显示」最大 → 清空勾选 → 勾我们的单（严格核对）
    →（check_only 到此为止）→ 点一次「多平台打印快递单」→ 处理弹窗 → 核对 ERP 队列是否变化。

    由 tools/erp_print_run2.py 整段改写而来，**进程内执行**（冻结后不再 subprocess 调它）。
    check_only=True 时**不取号、不点打印**，只做「设页数 + 对齐条件 + 勾选 + 核对」（验证链路用）。
    要打单数 > 页面「每页显示」上限时**自动分批**：每批勾满→核对→点打印→核对队列→重新筛单→下一批，
    每批都核对；任一批失败立即停止（不再往下打，避免误打）。
    verdict 传 dict 时写入结构化结论：{clicked, checked, model_count, verified, still_unprinted,
    gone, page_size, page_size_max, page_size_ok, rows_window, rows_total, batches, reason}。
    返回日志行列表（失败时首行是「！！打印失败：…」）。
    注意：**不要 Page.bringToFront**（全程后台静默，用户要求）。
    """
    v = verdict if isinstance(verdict, dict) else {}
    v.update({"clicked": False, "checked": 0, "model_count": None, "verified": None,
              "still_unprinted": None, "gone": None, "reason": "",
              "page_size": None, "page_size_max": None, "page_size_ok": None,
              "rows_window": 0, "rows_total": None, "batches": 1})
    sids = [s for s in (sids or []) if s]
    shorts = list(shorts or [])
    if len(shorts) < len(sids):
        shorts = shorts + [""] * (len(sids) - len(shorts))
    expect = len(sids) or len([s for s in shorts if s])
    logs = []
    c = open_cdp_page()
    try:
        chunks = [(sids, shorts)]
        clicked_any = False
        all_verified = True
        bi = 0
        while bi < len(chunks):
            csids, cshorts = chunks[bi]
            if bi > 0:
                logs.append("--- 第 %d/%d 批：重新筛单（上一批已离开未打印队列）---" % (bi + 1, len(chunks)))
            _t_goto = time.time()
            _ok_goto = _goto_print_page(c, code, logs)
            _tm_add("进打单页", time.time() - _t_goto)
            if not _ok_goto:
                logs.append("！！无法进入打单页 → 终止（不出纸）")
                v["reason"] = "no-page"
                return logs
            rows = poll_rows(c, 1, min(float(wait_rows or 12.0), 20.0))
            logs.append("行数: %d" % rows)
            if rows <= 0:
                logs.append("！！打单页没有行（筛单失败/页面不对）→ 终止（不出纸）")
                v["reason"] = "no-rows"
                return logs
            if bi == 0 and not check_only:
                # 先探一次「每页显示」上限，判断要不要分批（只设页数，不点打印）
                ps0 = set_page_size_max(c, logs)
                cap0 = int(ps0.get("max_opt") or 0)
                v["page_size"] = ps0.get("value")
                v["page_size_max"] = cap0 or None
                if cap0 > 0 and expect > cap0:
                    chunks = _chunk_pairs(sids, shorts, cap0)
                    logs.append("分批打印：要打 %d 单 > 每页显示上限 %d → 分 %d 批（每批都核对）"
                                % (expect, cap0, len(chunks)))
            ok, _ps = _print_one_batch(c, code, csids, cshorts, logs, v,
                                       wait_rows=wait_rows, check_only=check_only)
            clicked_any = clicked_any or bool(v.get("clicked"))
            if not ok:
                v["clicked"] = clicked_any
                if not check_only:
                    v["verified"] = False
                return logs
            if not check_only and v.get("verified") is not True:
                all_verified = False
            bi += 1
        v["clicked"] = clicked_any
        v["batches"] = len(chunks)
        if check_only:
            v["verified"] = None
        else:
            v["verified"] = bool(all_verified and v.get("verified") is True)
        return logs
    finally:
        try:
            c.close()
        except Exception:
            pass


EDGE_CANDIDATES = [r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
                   r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"]
# EDGE_PROFILE 已在文件顶部定义（= BASE_DIR\edge-automation，与主程序数据目录同处）
PRINT_URL = "https://erpb.superboss.cc/index.html#/trade/printv2"


def ensure_browser(auto_start=True):
    hit = _cache_get("browser_ok", 300)   # 已登录状态缓存 5 分钟
    if hit:
        return "ok", "已登录（缓存）"
    """打单前自检：返回 (状态, 说明)。

    ok         → 浏览器在跑且已登录（静默继续，不打扰用户）
    need_login → 需要用户登录 ERP（界面提示一次）
    no_browser → 没找到 Edge / 启动超时
    没在跑时会用**独立配置目录**自动启动（不碰日常浏览器）。
    """
    import subprocess
    import urllib.request

    def alive():
        try:
            op = urllib.request.build_opener(urllib.request.ProxyHandler({}))
            op.open("http://127.0.0.1:9222/json/version", timeout=3).read()
            return True
        except Exception:
            return False

    if not alive():
        exe = next((p for p in EDGE_CANDIDATES if os.path.isfile(p)), None)
        if not (exe and auto_start):
            return "no_browser", "没找到 Edge（或未允许自动启动），请手动打开打单浏览器"
        try:
            os.makedirs(EDGE_PROFILE, exist_ok=True)
            subprocess.Popen([exe, "--remote-debugging-port=9222",
                              "--user-data-dir=" + EDGE_PROFILE,
                              "--start-minimized",          # 最小化启动（无头模式实测打不出纸，故不用）
                              "--no-first-run", "--no-default-browser-check", PRINT_URL])
        except Exception as e:
            return "no_browser", "启动浏览器失败：%s" % str(e)[:80]
        for _ in range(25):
            time.sleep(1)
            if alive():
                break
        else:
            return "no_browser", "浏览器启动超时"
    href = ""
    last = ""
    for _ in range(3):                     # 页面刚启动时可能还没就绪 → 重试几次
        try:
            c = open_cdp_page()
            href = str(c.js("location.href") or "")
            c.close()
            last = ""
            break
        except BaseException as e:         # SystemExit 也要接住（page_ws 找不到页面时抛它）
            last = str(e)[:80]
            time.sleep(1.5)
    if last:
        return "need_login", "打单浏览器未就绪：%s（已重试 3 次，可再点一次）" % last
    if "login" in href.lower() or not href:
        return "need_login", "请在打单浏览器里登录快麦 ERP（只需一次，以后会记住）"
    _cache_put("browser_ok", True)          # 缓存命中用
    return "ok", "已登录"                  # 注意：必须返回字符串 'ok'（不要把 _cache_put 的返回值直接 return）


def preview(code, want):
    """预演：只列会打哪几单、为什么，不取号不出纸。"""
    orders = fetch_orders_live(code, page_size=MAX_BATCH)   # 全量候选：截断会让「剩余时间优先」失效
    print("编码 %s | 要打 %s 单 | 实时查到 %d 单" % (code, want, len(orders)))
    for o in orders:
        can, why = is_single_item(o.get("items") or [])
        rm = o.get("remain")
        print("  sid=%s 剩余=%s 已打=%s %s -> %s" % (
            o["sid"], ("%.1fh" % rm) if isinstance(rm, float) else "?",
            o.get("print_count"), o.get("express"), ("可打:" + why) if can else ("不可打:" + why)))
    ok, skip = pick_orders(orders, want, code=code)
    print("→ 将打：", [(o["sid"], o.get("remain")) for o in ok])
    print("→ 跳过：", skip)
    return ok, skip


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "selftest":
        sys.exit(1 if selftest() else 0)
    if len(sys.argv) > 2 and sys.argv[1] == "getcode":
        for r in getcode(sys.argv[2].split(",")):
            print(str(r)[:600])
    elif len(sys.argv) > 3 and sys.argv[1] == "preview":
        preview(sys.argv[2], int(sys.argv[3]))
    else:
        print(__doc__)
