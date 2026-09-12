#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
快麦扫码查待发货 + 可售库存（增强版）
==================================================
功能：
  1. 扫商家编码 → 显示【待发货件数 + 当前可售库存】一行对比
  2. 声光提示：待发货 > 0 绿色；待发货 = 0 红色
  3. 一键导出全部扫码日志 Excel
  4. 待发货数量本地缓存，扫码秒查
  5. 商品数量筛选：订单商品数量 > / < / = N，只加载符合条件的待发货订单

底层逻辑：
  启动/刷新时用 erp.trade.list.query（status=WAIT_SEND_GOODS）分页拉取全部
  待发货订单，读取每单商品件数 itemNum，按设置的件数条件过滤后，把每单内
  商品的商家编码(sysOuterId)汇总成“编码 → 待发货件数”的本地索引并缓存。
  扫码时直接查缓存（秒查），可售库存用 stock.api.status.query 实时查询。

接口依据：快麦开放平台 open.kuaimai.com（V2 网关 https://gw.superboss.cc/router）
"""
import os
import sys
import json
import hmac
import time
import queue
import hashlib
import sqlite3
import threading
import concurrent.futures
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

try:
    from kuaimai_webui import WEB_INDEX_HTML
except Exception:
    WEB_INDEX_HTML = "<h1>缺少 kuaimai_webui.py</h1>"
import kuaimai_db              # 订单缓存 SQLite 存储层（kuaimai_db.py）
import traceback
import collections
import re
import socket
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone, timedelta
import tkinter as tk
from tkinter import ttk, messagebox

try:
    import winsound  # Windows 声光提示
except Exception:  # pragma: no cover
    winsound = None

# ====================== 【配置区域，修改这里】======================
# ⚠️ 下面四项是本地的私有凭据，开源仓库里一律用占位符。
#    真要运行，请把你的真实值填在这里（不要提交到任何公开仓库）。
KM_APP_KEY = "YOUR_KM_APP_KEY"
KM_APP_SECRET = "YOUR_KM_APP_SECRET"
KM_REFRESH_TOKEN = "YOUR_KM_REFRESH_TOKEN"
# 【重要】初始可用 sessionId（accessToken）
INIT_SESSION_ID = "YOUR_INIT_SESSION_ID"
KM_SIGN_METHOD = "hmac-sha256"
KM_SIGN_UPPER = False
GATEWAY = "https://gw.superboss.cc/router"
# ==================================================================

def _pick_base_dir(preferred):
    """数据目录：优先放在 exe 旁边（便携）；若不可写（如装在 Program Files）则用用户目录。"""
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


# 打包成 exe 后，数据文件（缓存/日志）跟随 exe 所在目录，而不是临时解包目录
if getattr(sys, "frozen", False):
    BASE_DIR = _pick_base_dir(os.path.dirname(os.path.abspath(sys.executable)))
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_FILE = os.path.join(BASE_DIR, "kuaimai_token_cache.json")
PENDING_CACHE_FILE = os.path.join(BASE_DIR, "kuaimai_pending_cache.json")
STOCK_CACHE_FILE = os.path.join(BASE_DIR, "kuaimai_stock_cache.json")
SHELF_CACHE_FILE = os.path.join(BASE_DIR, "kuaimai_shelf_cache.json")
LOCK_CACHE_FILE = os.path.join(BASE_DIR, "kuaimai_lock_cache.json")
SETTINGS_FILE = os.path.join(BASE_DIR, "kuaimai_settings.json")
PULL_PROGRESS_FILE = os.path.join(BASE_DIR, "kuaimai_pull_progress.json")
DB_FILE = os.path.join(BASE_DIR, "scan_log.db")
ORDERS_DB_FILE = os.path.join(BASE_DIR, "kuaimai_data.db")   # 订单缓存（SQLite，替代 kuaimai_pending_cache.json）

PENDING_CACHE_MAX_AGE = 30 * 60      # 待发货缓存视为“新鲜”的秒数
STOCK_CACHE_TTL = 120                # 可售库存缓存有效期（秒）
SHELF_CACHE_TTL = 300                # 货架(货位)在架数缓存有效期（秒）
PAGE_SIZE = 500                      # erp.trade.list.query 文档写最大200，实测 500 可用（1000 报错）
MAX_PAGES = 600                      # 安全上限，避免异常死循环
SHELF_PAGE_SIZE = 500                # asso.goods.section.sku.query 实际单页上限 500
MAX_SHELF_PAGES = 200
LOCK_PAGE_SIZE = 100                 # stock.api.status.query 单页最大 100
LOCK_REFRESH_MIN = 10                # 锁定数自动刷新间隔（分钟）

# 待发货口径（用户定义）：待发货 + 待审核 + 待打印快递单 三个系统状态合并统计。
# 注：合并后结果集很大，普通分页会报 20027“数量过多”，必须用 useCursor 游标翻页。
PENDING_STATUSES = "WAIT_SEND_GOODS,WAIT_AUDIT,WAIT_EXPRESS_PRINT"
STATUS_LABEL = {
    "WAIT_SEND_GOODS": "待发货",
    "WAIT_AUDIT": "待审核",
    "WAIT_EXPRESS_PRINT": "待打印快递单",
}

SHIP_NOTE = "已剔除系统状态=已发货的订单"
# 已发货只看「系统状态」(sysStatus)：
#   待发货/待审核/待打印快递单 一律当未发货（哪怕平台状态已是卖家已发货，也不剔除）
SHIPPED_SYS_STATUS = {"SELLER_SEND_GOODS", "FINISHED", "CLOSED"}

FILTER_OPTIONS = ("不限", "大于", "小于", "等于")

# 不计入商品件数的占位/补偿类商品（编码首段或名称关键字命中即排除）
EXCLUDE_CODE_HEADS = ("1166",)
EXCLUDE_NAME_KEYWORDS = ("买家秀", "圆虹包")
EXCLUDE_NOTE = "已排除占位/补偿商品：编码 %s、名称含 %s" % (
    "/".join(EXCLUDE_CODE_HEADS), "、".join(EXCLUDE_NAME_KEYWORDS))

# 待发货口径的三个系统状态（集合形式，便于增量同步判断）
PENDING_STATUS_SET = {"WAIT_SEND_GOODS", "WAIT_AUDIT", "WAIT_EXPRESS_PRINT"}
AUTO_REFRESH_MIN = 5        # 增量刷新间隔（分钟）
FULL_REFRESH_MIN = 30       # 全量重拉间隔（分钟）
INCR_OVERLAP_SEC = 120      # 增量查询向前重叠秒数，避免边界漏单
TOTAL_LOOKBACK_DAYS = 3     # 估算总数时「待审核」向前回溯天数（更早的量极小）

# 全量拉取并发参数（实测 6 线程吞吐约为单线程的 3.7 倍）
PARALLEL_WORKERS = 4        # 并发线程数（过高容易触发 429 限流）
CHUNK_HOURS = 6             # 时间窗大小（小时）
MAX_LOOKBACK_DAYS = 90      # 最多回溯天数
EMPTY_STOP = 4              # 连续 N 个空窗口即停止回溯


# ============================ 基础工具 ============================
def now_gmt8():
    tz = timezone(timedelta(hours=8))
    return datetime.now(tz).strftime("%Y-%m-%d %H:%M:%S")


def sign(params, secret, sign_method="hmac-sha256", upper=False):
    """签名：去掉 sign 与空值，按参数名 ASCII 升序拼接 k+v（不含 secret）。"""
    data = {k: v for k, v in params.items() if v not in (None, "") and k != "sign"}
    src = "".join("%s%s" % (k, data[k]) for k in sorted(data.keys()))
    if sign_method == "md5":
        raw = hashlib.md5((secret + src + secret).encode("utf-8")).hexdigest()
    elif sign_method == "hmac":
        raw = hmac.new(secret.encode("utf-8"), src.encode("utf-8"), hashlib.md5).hexdigest()
    elif sign_method == "hmac-sha256":
        raw = hmac.new(secret.encode("utf-8"), src.encode("utf-8"), hashlib.sha256).hexdigest()
    else:
        raise ValueError("不支持的 sign_method: %s" % sign_method)
    return raw.upper() if upper else raw


def api_call(method, business, session, timeout=40):
    """通用调用：公共参数 + 业务参数 → POST 表单。"""
    params = {
        "method": method,
        "appKey": KM_APP_KEY,
        "timestamp": now_gmt8(),
        "format": "json",
        "version": "1.0",
        "sign_method": KM_SIGN_METHOD,
        "session": session,
    }
    params.update({k: v for k, v in business.items() if v not in (None, "")})
    params["sign"] = sign(params, KM_APP_SECRET, KM_SIGN_METHOD, KM_SIGN_UPPER)
    body = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(
        GATEWAY,
        data=body,
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded; charset=utf-8"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def load_json(path, default=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return default


def save_json(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


def load_settings():
    return load_json(SETTINGS_FILE, {}) or {}


def save_settings(data):
    try:
        save_json(SETTINGS_FILE, data)
    except Exception:
        pass


# ============================ Token 续期 ============================
def load_token_cache():
    return load_json(CACHE_FILE, {"sessionId": INIT_SESSION_ID, "last_refresh_ts": 0})


def save_token_cache(session_id, last_refresh_ts):
    save_json(CACHE_FILE, {"sessionId": session_id, "last_refresh_ts": last_refresh_ts})


def refresh_access_token(old_session):
    """open.token.refresh（续期）：成功返回的 sessionId 不变，仅有效期 +30 天。限流 1 次/小时。"""
    res = api_call("open.token.refresh", {"refreshToken": KM_REFRESH_TOKEN}, old_session)
    if isinstance(res, dict) and res.get("success"):
        data = res.get("data") or {}
        new_session = data.get("sessionId") or old_session
        save_token_cache(new_session, datetime.now().timestamp())
        return new_session
    code = res.get("code") if isinstance(res, dict) else "?"
    msg = res.get("msg") if isinstance(res, dict) else str(res)[:100]
    raise RuntimeError("刷新会话失败 code=%s msg=%s" % (code, msg))


def current_session():
    """当前会话：优先本地缓存，否则用初始 sessionId。不主动联网刷新（刷新接口限流 1 次/小时）。"""
    return load_token_cache().get("sessionId") or INIT_SESSION_ID


_AUTH_HINTS = ("token", "session", "授权", "登录", "过期", "无效", "appkey", "app key", "签名")


def _is_auth_failure(res):
    if not isinstance(res, dict) or res.get("success") is not False:
        return False
    text = ("%s %s" % (res.get("code", ""), res.get("msg", ""))).lower()
    return any(h in text for h in _AUTH_HINTS)


def get_session_id(force_refresh=False):
    """默认返回当前会话；仅 force_refresh 时才续期。"""
    if force_refresh:
        return refresh_access_token(current_session())
    return current_session()


def api_call_authed(method, business, timeout=40, retries=5):
    """业务调用：429/网络错误自动退避重试；会话失效时自动续期并重试一次。"""
    import urllib.error
    session = current_session()
    attempt = 0
    while True:
        try:
            res = api_call(method, business, session, timeout)
            break
        except urllib.error.HTTPError as e:
            if (e.code == 429 or 500 <= e.code < 600) and attempt < retries:
                attempt += 1
                time.sleep(min(60, 4 * (2 ** attempt)))     # 8/16/32/60/60 秒
                continue
            raise
        except Exception:
            if attempt < retries:
                attempt += 1
                time.sleep(min(20, 2 * (2 ** attempt)))
                continue
            raise
    if not _is_auth_failure(res):
        return res
    last = load_token_cache().get("last_refresh_ts", 0) or 0
    if time.time() - last < 3600:
        return res  # 刚续期过仍失败，直接返回，避免触发 refresh_frequently
    try:
        session = refresh_access_token(session)
    except Exception:
        return res
    return api_call(method, business, session, timeout)


# ============================ 数据库（扫码日志） ============================
def get_conn():
    conn = sqlite3.connect(DB_FILE)
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """CREATE TABLE IF NOT EXISTS scan_record
           (id INTEGER PRIMARY KEY AUTOINCREMENT,
            scan_time TEXT,
            barcode TEXT,
            order_no TEXT,
            goods_name TEXT,
            status TEXT)"""
    )
    # 兼容旧库：补齐增强字段
    cols = [d[1] for d in cur.execute("PRAGMA table_info(scan_record)")]
    for name, ddl in (
        ("pending_qty", "INTEGER DEFAULT 0"),
        ("stock_qty", "INTEGER DEFAULT 0"),
        ("shelf_qty", "INTEGER DEFAULT 0"),
        ("orders_count", "INTEGER DEFAULT 0"),
    ):
        if name not in cols:
            cur.execute("ALTER TABLE scan_record ADD COLUMN %s %s" % (name, ddl))
    conn.commit()
    conn.close()


def insert_scan(barcode, pending_qty, shelf_qty, orders_count, light):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO scan_record(scan_time,barcode,order_no,goods_name,status,pending_qty,shelf_qty,orders_count)"
        " VALUES (?,?,?,?,?,?,?,?)",
        (now_gmt8(), barcode, "", "", light, int(pending_qty), int(shelf_qty), int(orders_count)),
    )
    conn.commit()
    conn.close()


def fetch_all_scans():
    conn = get_conn()
    cur = conn.cursor()
    rows = cur.execute(
        "SELECT id,scan_time,barcode,pending_qty,shelf_qty,orders_count,status"
        " FROM scan_record ORDER BY id ASC"
    ).fetchall()
    conn.close()
    return rows


# ==================== 订单缓存数据库（SQLite，替代 pending_cache.json） ====================
# 单连接 + 串行锁：网页服务/后台拉取/主线程共用；WAL 模式下读写不会互相阻塞。
_ODB_CONN = None
_ODB_LOCK = threading.RLock()


def orders_db():
    """订单库连接（首次调用时建库建表）。"""
    global _ODB_CONN
    with _ODB_LOCK:
        if _ODB_CONN is None:
            _ODB_CONN = kuaimai_db.connect(ORDERS_DB_FILE, check_same_thread=False)
        return _ODB_CONN


def db_call(fn):
    """锁内执行一次库操作；出错回滚（保留旧数据）后抛出。"""
    conn = orders_db()
    with _ODB_LOCK:
        try:
            return fn(conn)
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
            raise


def import_orders_from_json():
    """首次启动：库为空且 JSON 缓存还在 → 导入一次（JSON 保留不删）。返回提示文字。"""
    def _do(conn):
        if kuaimai_db.orders_total(conn) > 0:
            return None
        cache = load_pending_cache()
        store = (cache or {}).get("store") or {}
        if not store:
            return None
        n_o, _n_i = kuaimai_db.import_store(conn, store, loaded_at=(cache.get("loaded_at") or ""))
        kuaimai_db.set_meta(conn, {
            "loaded_at": cache.get("loaded_at") or "",
            "last_sync_ts": cache.get("last_sync_ts") or 0,
            "last_full_ts": cache.get("last_full_ts") or 0,
            "total_estimate": cache.get("total_estimate") or 0,
            "source": "import:kuaimai_pending_cache.json",
        })
        return n_o, _n_i

    r = db_call(_do)
    if not r:
        return ""
    return "已从 JSON 缓存导入 %d 单 / %d 条商品明细" % r


def import_shelf_lock_from_json():
    """货位/锁定数：库为空时从旧 JSON 缓存迁移一次（之后以库为准）。"""
    def _do(conn):
        msg = []
        if kuaimai_db.shelf_total(conn) == 0:
            c = load_json(SHELF_CACHE_FILE, None) or {}
            if c.get("map"):
                kuaimai_db.save_shelf(conn, c["map"])
                kuaimai_db.set_meta(conn, {
                    "shelf_at": c.get("loaded_at") or "",
                    "shelf_ts": c.get("loaded_ts") or 0,
                    "shelf_stat": json.dumps(c.get("stat") or {}, ensure_ascii=False)})
                msg.append("货位 %d 个" % len(c["map"]))
        if kuaimai_db.lock_total(conn) == 0:
            c = load_json(LOCK_CACHE_FILE, None) or {}
            if c.get("map"):
                kuaimai_db.save_lock(conn, c["map"])
                kuaimai_db.set_meta(conn, {"lock_at": c.get("loaded_at") or "",
                                           "lock_ts": c.get("loaded_ts") or 0})
                msg.append("锁定数 %d 个" % len(c["map"]))
        return msg

    return db_call(_do) or []


def db_orders_total():
    return db_call(kuaimai_db.orders_total)


def replace_orders_db(store, loaded_at=""):
    """全量拉取结果 → 事务内整体替换订单库（空结果拒绝写入，绝不覆盖）。"""
    return db_call(lambda conn: kuaimai_db.import_store(conn, store, loaded_at=loaded_at, replace=True))


def upsert_orders_db(records, delete_sids=()):
    """增量结果 → 按 sid UPSERT（orders 一行 + order_items 若干行）。"""
    return db_call(lambda conn: kuaimai_db.upsert_records(conn, records, delete_sids))


def build_index_db(relation="不限", n=0):
    """SQL 聚合建索引（不再把所有订单读进内存）。"""
    return db_call(lambda conn: kuaimai_db.rebuild_index_db(conn, relation, n))


def save_shelf_db(shelf_map, stat, loaded_at):
    def _do(conn):
        n = kuaimai_db.save_shelf(conn, shelf_map)
        kuaimai_db.set_meta(conn, {"shelf_at": loaded_at, "shelf_ts": time.time(),
                                   "shelf_stat": json.dumps(stat or {}, ensure_ascii=False)})
        return n

    return db_call(_do)


def save_lock_db(lock_map, loaded_at):
    def _do(conn):
        n = kuaimai_db.save_lock(conn, lock_map)
        kuaimai_db.set_meta(conn, {"lock_at": loaded_at, "lock_ts": time.time()})
        return n

    return db_call(_do)


def save_orders_meta(**kv):
    return db_call(lambda conn: kuaimai_db.set_meta(conn, kv))


def load_orders_meta(keys):
    return db_call(lambda conn: {k: kuaimai_db.get_meta(conn, k, "") for k in keys})


# ============================ 待发货订单加载 ============================
def item_code(item):
    """取商品条目上的商家编码（SKU 优先）。"""
    for key in ("sysOuterId", "outerSkuId", "outer_sku_id", "sysOuterOuterId", "outerId"):
        v = item.get(key)
        if v not in (None, ""):
            return str(v).strip()
    return ""


def item_main_code(item):
    for key in ("sysItemOuterId", "sysOuterId"):
        v = item.get(key)
        if v not in (None, ""):
            return str(v).strip()
        # sysOuterId 可能是 SKU 编码，主编码在 sysItemOuterId
    return ""


def item_num(item):
    for key in ("num", "quantity"):
        try:
            n = int(item.get(key))
            if n > 0:
                return n
        except Exception:
            pass
    return 1


def _is_excluded_item(item):
    """占位/补偿类商品（如 1166、买家秀客服2圆虹包）不计入商品件数。"""
    code = item_code(item)
    if code:
        head = re.split(r"[-\s（()）/,]", code)[0]
        if head in EXCLUDE_CODE_HEADS:
            return True
    name = str(item.get("title") or item.get("sysTitle") or item.get("shortTitle") or "")
    return any(k and k in name for k in EXCLUDE_NAME_KEYWORDS)


def _trade_item_count(trade):
    """订单商品件数：只统计有效商品（排除占位/补偿类）；无明细时回退 itemNum。"""
    items = trade.get("orders") or []
    if not items:
        try:
            return int(trade.get("itemNum"))
        except Exception:
            return 0
    total = 0
    for item in items:
        if not _is_excluded_item(item):
            total += item_num(item)
    return total


def _is_shipped(trade):
    """是否已发货：**只看系统状态**（sysStatus）。

    系统状态为 待发货/待审核/待打印快递单 的，一律当作未发货，不剔除；
    平台状态（unifiedStatus）可能已经显示卖家已发货，但以系统状态为准。
    """
    return str(trade.get("sysStatus") or "").strip().upper() in SHIPPED_SYS_STATUS


def _rec_shipped(rec):
    """store 记录是否已发货（本地判断，改规则无需重拉）。"""
    return str(rec.get("status") or "").strip().upper() in SHIPPED_SYS_STATUS


def _store_record(trade):
    """生成 store 记录（全量保留，含平台状态；剔除动作放到本地建索引时做）。"""
    count, pairs = _order_contribution(trade)
    return {"status": trade.get("sysStatus"),
            "us": trade.get("unifiedStatus"),
            "count": count, "pairs": pairs}


def _add_trade_to_store(store, trade):
    """写入订单记录。"""
    sid = trade.get("sid")
    if sid is None:
        return
    store[str(sid)] = _store_record(trade)


def _match_quantity(total_items, relation, n):
    if relation == "大于":
        return total_items > n
    if relation == "小于":
        return total_items < n
    if relation == "等于":
        return total_items == n
    return True


def _order_contribution(trade):
    """计算一个订单对编码索引的贡献：返回 (有效件数, [[编码, 数量], ...])。

    排除占位/补偿类商品；同时计入主商家编码，便于扫主编码也能命中。
    """
    items = trade.get("orders") or []
    count = 0
    pairs = []
    for item in items:
        if _is_excluded_item(item):
            continue
        qty = item_num(item)
        count += qty
        code = item_code(item)
        main = item_main_code(item)
        if code:
            pairs.append([code, qty])
        if main and main != code:
            pairs.append([main, qty])
    if not items:
        try:
            count = int(trade.get("itemNum"))
        except Exception:
            count = 0
    return count, pairs


def _fetch_pending_batches(progress=None, max_pages=None):
    """游标分页，逐页 yield 一批订单。

    三个状态合并后结果集很大，普通 pageNo 分页会报 20027（数量过多），
    必须用 useCursor=true 游标翻页；按 sid 去重。
    """
    limit = MAX_PAGES if max_pages is None else max_pages
    seen = set()
    cursor = None
    page = 0
    pulled = 0
    while page < limit:
        page += 1
        biz = {
            "status": PENDING_STATUSES,
            "pageNo": str(page),
            "pageSize": str(PAGE_SIZE),
            "useCursor": "true",
        }
        if cursor:
            biz["cursor"] = cursor
        try:
            res = api_call_authed("erp.trade.list.query", biz)
        except Exception:
            if pulled:      # 中途超时：保留已取部分
                return
            raise
        if not isinstance(res, dict) or not res.get("success"):
            if pulled:
                return
            code = res.get("code") if isinstance(res, dict) else "?"
            msg = res.get("msg") if isinstance(res, dict) else str(res)[:120]
            raise RuntimeError("查询待发货订单失败 code=%s msg=%s" % (code, msg))
        batch = []
        for trade in (res.get("list") or []):
            sid = trade.get("sid")
            if sid is not None:
                if sid in seen:
                    continue
                seen.add(sid)
            batch.append(trade)
        pulled += len(batch)
        if progress:
            progress(pulled, page)
        yield batch
        cursor = res.get("cursor")
        if not res.get("hasNext") or not batch:
            return


def fetch_pending_orders(progress=None, max_pages=None):
    """一次性返回订单列表（仅小样本/自检用）。"""
    orders = []
    for batch in _fetch_pending_batches(progress=progress, max_pages=max_pages):
        orders.extend(batch)
    return orders


def full_pull_store(progress=None, max_pages=None):
    """全量拉取待发货口径订单，建立订单级 store：sid → {"status","count","pairs"}。

    保留订单级明细，是为了增量同步时能把「已发货/已关闭」的单从索引里扣减掉。
    """
    store = {}
    for batch in _fetch_pending_batches(progress=progress, max_pages=max_pages):
        for trade in batch:
            _add_trade_to_store(store, trade)
    return store


def _fetch_window_status(status, start, end, depth=0, retry=1):
    """拉取某状态在某时间窗内的全部订单。

    返回 (orders, ok)：**ok=False 表示查询出错**（跟“确实查到 0 条”要区分开，
    否则刚唤醒/断网时会把失败当成空窗口，导致全量拉取结果为空）。
    窗口过大（20027）时二分拆分。
    """
    fmt = "%Y-%m-%d %H:%M:%S"
    orders = []
    page = 1
    total = None
    while page <= 60:
        biz = {"status": status, "timeType": "created",
               "startTime": start.strftime(fmt), "endTime": end.strftime(fmt),
               "pageNo": str(page), "pageSize": str(PAGE_SIZE)}
        try:
            res = api_call_authed("erp.trade.list.query", biz)
        except Exception:
            if retry > 0 and not orders:
                time.sleep(2)
                return _fetch_window_status(status, start, end, depth, retry - 1)
            return orders, False
        if not isinstance(res, dict) or not res.get("success"):
            if page == 1 and depth < 4 and (end - start).total_seconds() > 600:
                mid = start + (end - start) / 2
                a, ok1 = _fetch_window_status(status, start, mid, depth + 1, retry)
                b, ok2 = _fetch_window_status(status, mid, end, depth + 1, retry)
                return a + b, (ok1 and ok2)
            if retry > 0 and not orders:
                time.sleep(2)
                return _fetch_window_status(status, start, end, depth, retry - 1)
            return orders, False
        batch = res.get("list") or []
        if total is None:
            try:
                total = int(res.get("total"))
            except Exception:
                total = None
        orders.extend(batch)
        if not batch or (total is not None and len(orders) >= total):
            break
        page += 1
    return orders, True


def full_pull_store_parallel(progress=None, workers=PARALLEL_WORKERS,
                             chunk_hours=CHUNK_HOURS, max_days=MAX_LOOKBACK_DAYS,
                             empty_stop=EMPTY_STOP, stats=None):
    """多线程分片全量拉取：时间窗切片 + 线程池并发。

    窗口由新到旧分发；连续 empty_stop 个空窗口则停止回溯。
    已发货订单会在此处被剔除，不计入待发货。
    progress(pulled, window_no) 用于刷新进度。
    """
    now = datetime.now()
    windows = []
    t = now
    while (now - t).days < max_days:
        windows.append((t - timedelta(hours=chunk_hours), t))
        t = t - timedelta(hours=chunk_hours)

    lock = threading.Lock()
    store = {}
    st = {"idx": 0, "empty": 0, "stop": False, "pulled": 0, "errors": 0}

    def worker():
        while True:
            with lock:
                if st["stop"] or st["idx"] >= len(windows):
                    return
                i = st["idx"]
                st["idx"] += 1
                ws, we = windows[i]
            got = 0
            errs = 0
            recs = {}
            for status in ("WAIT_AUDIT", "WAIT_EXPRESS_PRINT", "WAIT_SEND_GOODS"):
                orders, ok = _fetch_window_status(status, ws, we)
                if not ok:
                    errs += 1
                got += len(orders)
                for trade in orders:
                    _add_trade_to_store(recs, trade)
            with lock:
                store.update(recs)
                st["pulled"] += got
                st["errors"] += errs
                if got or errs:
                    st["empty"] = 0      # 出错不算“空窗口”，避免提前停止
                else:
                    st["empty"] += 1
                    if st["empty"] >= empty_stop:
                        st["stop"] = True
                if progress:
                    progress(st["pulled"], i + 1)

    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as ex:
        concurrent.futures.wait([ex.submit(worker) for _ in range(workers)])
    if stats is not None:
        stats.update({"pulled": st["pulled"], "windows": min(st["idx"], len(windows)),
                      "errors": st["errors"]})
    # 安全阀：一单没拉到就报错，绝不返回空结果去覆盖已有数据
    if st["pulled"] == 0:
        if st["errors"]:
            raise RuntimeError("全量拉取失败：%d 个请求出错（可能刚唤醒/断网），已保留原有数据" % st["errors"])
        raise RuntimeError("全量拉取返回 0 单，疑似异常，已保留原有数据")
    return store


def incremental_sync(store, since_ts, progress=None):
    """按修改时间增量同步（不带状态过滤）。

    既把新增/变更的待发货订单写进 store，也能看到「已发货/已关闭」的单并把它移除，
    索引里的件数才能随发货实时减少。返回 (处理单数, 本次同步起始时间戳)。
    """
    sync_started = time.time()
    if not since_ts:
        since_ts = sync_started - 3600
    start = datetime.fromtimestamp(max(0, since_ts - INCR_OVERLAP_SEC))
    end = datetime.now()
    fmt = "%Y-%m-%d %H:%M:%S"
    cursor = None
    page = 0
    processed = 0
    while page < MAX_PAGES:
        page += 1
        biz = {
            "timeType": "upd_time",
            "startTime": start.strftime(fmt),
            "endTime": end.strftime(fmt),
            "pageNo": str(page),
            "pageSize": str(PAGE_SIZE),
            "useCursor": "true",
        }
        if cursor:
            biz["cursor"] = cursor
        try:
            res = api_call_authed("erp.trade.list.query", biz)
        except Exception:
            break
        if not isinstance(res, dict) or not res.get("success"):
            break
        batch = res.get("list") or []
        for trade in batch:
            sid = trade.get("sid")
            if sid is None:
                continue
            key = str(sid)
            status = trade.get("sysStatus")
            if status in PENDING_STATUS_SET:
                store[key] = _store_record(trade)
            else:
                store.pop(key, None)      # 已离开待发货口径 → 扣减（是否已发货由本地索引阶段判定）
            processed += 1
        if progress:
            progress(processed)
        cursor = res.get("cursor")
        if not res.get("hasNext") or not batch:
            break
    return processed, sync_started


def incremental_sync_db(since_ts, progress=None):
    """增量同步（写库版）：按修改时间拉变更，逐页 UPSERT 到订单库。

    口径与 JSON 版完全一致：仍属待发货三状态 → 写入；已离开口径 → 删除该 sid。
    请求失败即停，已应用的那些页保留（不整份重写、也不清空）。
    返回 (处理单数, 本次同步起始时间戳, 是否至少成功拉过一页)。
    """
    sync_started = time.time()
    if not since_ts:
        since_ts = sync_started - 3600
    start = datetime.fromtimestamp(max(0, since_ts - INCR_OVERLAP_SEC))
    end = datetime.now()
    fmt = "%Y-%m-%d %H:%M:%S"
    cursor = None
    page = 0
    processed = 0
    pages_ok = 0
    while page < MAX_PAGES:
        page += 1
        biz = {
            "timeType": "upd_time",
            "startTime": start.strftime(fmt),
            "endTime": end.strftime(fmt),
            "pageNo": str(page),
            "pageSize": str(PAGE_SIZE),
            "useCursor": "true",
        }
        if cursor:
            biz["cursor"] = cursor
        try:
            res = api_call_authed("erp.trade.list.query", biz)
        except Exception:
            break
        if not isinstance(res, dict) or not res.get("success"):
            break
        pages_ok += 1
        batch = res.get("list") or []
        ups, dels = {}, []
        for trade in batch:
            sid = trade.get("sid")
            if sid is None:
                continue
            key = str(sid)
            if trade.get("sysStatus") in PENDING_STATUS_SET:
                ups[key] = _store_record(trade)
            else:
                ups.pop(key, None)
                dels.append(key)
            processed += 1
        if ups or dels:
            upsert_orders_db(list(ups.items()), dels)
        if progress:
            progress(processed)
        cursor = res.get("cursor")
        if not res.get("hasNext") or not batch:
            break
    # 一页都没成功（断网/限流）→ 不推进同步水位，下次从原处重来，避免漏单
    return processed, (sync_started if pages_ok else since_ts), bool(pages_ok)


def rebuild_index(store, relation="不限", n=0):
    """【内存版参考实现，仅 --selftest / 对拍用】由订单级 store 重建编码索引。

    程序运行已改走 kuaimai_db.rebuild_index_db（SQL 聚合，不把订单读进内存）。
    已发货（平台状态=卖家已发货/已完结）的订单在这里被剔除，不计入待发货。
    """
    index = {}
    breakdown = collections.Counter()
    included = 0
    shipped = 0
    for rec in store.values():
        if _rec_shipped(rec):
            shipped += 1
            continue
        breakdown[rec.get("status")] += 1
        if not _match_quantity(rec.get("count", 0), relation, n):
            continue
        included += 1
        for pair in (rec.get("pairs") or []):
            code = pair[0]
            try:
                qty = int(pair[1])
            except Exception:
                qty = 0
            e = index.setdefault(code, {"qty": 0, "orders": 0, "ones": 0, "main": False})
            e["qty"] += qty
            e["orders"] += 1
            if int(rec.get("count") or 0) == 1:
                e["ones"] += 1
    live = len(store) - shipped
    stat = {"total_orders": live, "store_orders": len(store),
            "shipped_excluded": shipped, "included_orders": included,
            "breakdown": dict(breakdown)}
    return index, stat


# ============================ 总数估算（进度条分母） ============================
def _status_total(status, start=None, end=None, timeout=60):
    """取某状态订单总数；超上限（20027）等情况返回 None。"""
    biz = {"status": status, "pageNo": "1", "pageSize": "20"}
    if start is not None and end is not None:
        biz.update({"timeType": "created",
                    "startTime": start.strftime("%Y-%m-%d %H:%M:%S"),
                    "endTime": end.strftime("%Y-%m-%d %H:%M:%S")})
    try:
        res = api_call_authed("erp.trade.list.query", biz, timeout)
    except Exception:
        return None
    if not isinstance(res, dict) or not res.get("success"):
        return None
    try:
        return int(res.get("total"))
    except Exception:
        return None


def _range_total(status, start, end, min_hours=1.0):
    """区间总数；若整段超限则二分细分求和，直到 min_hours。"""
    v = _status_total(status, start, end)
    if v is not None:
        return v
    hours = (end - start).total_seconds() / 3600.0
    if hours <= min_hours:
        return 0
    mid = start + (end - start) / 2
    return (_range_total(status, start, mid, min_hours)
            + _range_total(status, mid, end, min_hours))


def estimate_pending_total(lookback_days=TOTAL_LOOKBACK_DAYS):
    """估算待发货口径总单数（进度条分母）。

    待发货/待打印直接取 total；待审核量太大（20027）时按时间二分求和。
    """
    end = datetime.now()
    total = 0
    for st in ("WAIT_SEND_GOODS", "WAIT_EXPRESS_PRINT"):
        v = _status_total(st)
        total += v or 0
    total += _range_total("WAIT_AUDIT", end - timedelta(days=lookback_days), end, 1.0)
    return total


# ============================ 可售库存查询 ============================
def query_stock(code):
    """按商家编码查询可售库存（skuOuterId 优先，其次 mainOuterId）。返回 (sellable, rows)。"""
    for field in ("skuOuterId", "mainOuterId"):
        res = api_call_authed(
            "stock.api.status.query",
            {"pageNo": "1", "pageSize": "100", field: code},
        )
        rows = (res.get("stockStatusVoList") if isinstance(res, dict) else None) or []
        if rows:
            total = 0
            for r in rows:
                try:
                    total += int(r.get("sellableNum") or 0)
                except Exception:
                    pass
            return total, rows
    return 0, []


def load_stock_cache():
    return load_json(STOCK_CACHE_FILE, {}) or {}


def stock_from_cache(cache, code):
    e = cache.get(code)
    if not e:
        return None
    if time.time() - e.get("ts", 0) > STOCK_CACHE_TTL:
        return None
    return e.get("sellable")


def put_stock_cache(cache, code, sellable):
    cache[code] = {"sellable": sellable, "ts": time.time()}
    save_json(STOCK_CACHE_FILE, cache)


# ============================ 货架(货位)在架数 ============================
def fetch_shelf_stock(progress=None):
    """拉取全部货位库存（asso.goods.section.sku.query），按商家编码汇总在架数。

    返回 (shelf_map, stat)：
      shelf_map[编码] = {"shelf": 拣货区合计, "all": 全部库区合计, "bins": [[货位, 数量], ...]}
    库区类型：1拣货区 2备货区 3次品区 —— 货架在架数取拣货区。
    """
    shelf_map = {}
    region_counter = collections.Counter()
    total_rows = 0
    total_expected = None
    page = 1
    while page <= MAX_SHELF_PAGES:
        biz = {"pageNo": str(page), "pageSize": str(SHELF_PAGE_SIZE)}
        if page > 1:
            biz["noNeedTotal"] = "true"      # 后续页不算总数，接口更快
        res = api_call_authed("asso.goods.section.sku.query", biz)
        if not isinstance(res, dict) or not res.get("success"):
            if total_rows:
                break
            code = res.get("code") if isinstance(res, dict) else "?"
            msg = res.get("msg") if isinstance(res, dict) else str(res)[:120]
            raise RuntimeError("查询货位库存失败 code=%s msg=%s" % (code, msg))
        if page == 1:
            try:
                total_expected = int(res.get("total"))
            except Exception:
                total_expected = None
        batch = res.get("list") or []
        for row in batch:
            outer = str(row.get("outerId") or "").strip()
            if not outer:
                continue
            try:
                qty = int(row.get("totalNum") or 0)
            except Exception:
                qty = 0
            region = row.get("stockRegionType")
            region_counter[region] += 1
            e = shelf_map.setdefault(outer, {"shelf": 0, "all": 0, "bins": []})
            e["all"] += qty
            if region == 1:          # 1 = 拣货区（货架）
                e["shelf"] += qty
            if qty:
                e["bins"].append([row.get("goodsSectionCode") or "", qty])
        total_rows += len(batch)
        if progress:
            progress(total_rows)
        if not batch:
            break
        # 服务端可能不受 pageSize 控制，用首页返回的 total 作为结束条件
        if total_expected is not None:
            if total_rows >= total_expected:
                break
        elif len(batch) < SHELF_PAGE_SIZE:
            break
        page += 1
    # 安全阀：没拉全（中途失败）就报错，不拿残缺数据覆盖旧缓存
    if total_expected is not None and total_rows < total_expected:
        raise RuntimeError("货位库存只拉到 %d/%d 条（中途失败），保留原有数据" % (total_rows, total_expected))
    # 若账号没有拣货区货位，则把全部库区合计当作在架数，避免全部为 0
    if "1" not in {str(k) for k in region_counter}:
        for e in shelf_map.values():
            e["shelf"] = e["all"]
    stat = {"rows": total_rows, "codes": len(shelf_map),
            "regions": {str(k): v for k, v in region_counter.items()}}
    return shelf_map, stat


def load_shelf_cache():
    """旧 JSON 货位缓存：仅用于首次迁移进数据库，不再写入。"""
    return load_json(SHELF_CACHE_FILE, None)


# ============================ 库存锁定数 ============================
def fetch_lock_stock(progress=None):
    """拉取全部 SKU 的库存口径（锁定数/可售/实际可用），按编码汇总。

    lock_map[编码] = {"lock": 锁定数, "sellable": 可售数, "avail": 实际可用}
    同时按主商家编码汇总，便于扫主编码也能命中。
    """
    lock_map = {}
    rows_total = 0
    page = 1
    total = None
    while page <= 300:
        biz = {"pageNo": str(page), "pageSize": str(LOCK_PAGE_SIZE)}
        if page > 1:
            biz["noNeedTotal"] = "true"
        try:
            res = api_call_authed("stock.api.status.query", biz)
        except Exception:
            if rows_total:
                break
            raise
        if not isinstance(res, dict) or not res.get("success"):
            if rows_total:
                break
            code = res.get("code") if isinstance(res, dict) else "?"
            msg = res.get("msg") if isinstance(res, dict) else str(res)[:120]
            raise RuntimeError("查询库存锁定数失败 code=%s msg=%s" % (code, msg))
        if page == 1:
            try:
                total = int(res.get("total"))
            except Exception:
                total = None
        batch = res.get("stockStatusVoList") or []
        for row in batch:
            sku = str(row.get("skuOuterId") or "").strip()
            main = str(row.get("mainOuterId") or "").strip()
            def _n(k):
                try:
                    return int(row.get(k) or 0)
                except Exception:
                    return 0
            lock, sell, avail = _n("totalLockStock"), _n("sellableNum"), _n("totalAvailableStock")
            for key, is_main in ((sku, False), (main, True)):
                if not key:
                    continue
                e = lock_map.setdefault(key, {"lock": 0, "sellable": 0, "avail": 0, "main": is_main})
                e["lock"] += lock
                e["sellable"] += sell
                e["avail"] += avail
        rows_total += len(batch)
        if progress:
            progress(rows_total)
        if not batch:
            break
        if total is not None and rows_total >= total:
            break
        page += 1
        time.sleep(0.5)      # 轻微限速，避开 429 限流
    # 安全阀：没拉全（中途失败）就报错，不拿残缺数据覆盖旧缓存
    if total is not None and rows_total < total:
        raise RuntimeError("库存锁定数只拉到 %d/%d 条（中途失败），保留原有数据" % (rows_total, total))
    stat = {"rows": rows_total, "codes": len(lock_map), "total": total}
    return lock_map, stat


def load_lock_cache():
    """旧 JSON 锁定数缓存：仅用于首次迁移进数据库，不再写入。"""
    return load_json(LOCK_CACHE_FILE, None)


# ============================ 待发货缓存文件（旧 JSON，只读迁移用） ============================
def load_pending_cache():
    """旧 JSON 订单缓存：仅用于首次迁移进数据库，不再写入。"""
    return load_json(PENDING_CACHE_FILE, None)


# ============================ Excel 导出（纯标准库 xlsx） ============================
def _xml_escape(value):
    return (str(value).replace("&", "&amp;").replace("<", "&lt;")
            .replace(">", "&gt;").replace('"', "&quot;"))


def _col_letter(n):
    s = ""
    while n > 0:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def write_xlsx(path, headers, rows):
    """用标准库生成最小可用的 .xlsx（inlineStr，数字按数值存储）。"""
    def cell(ref, val):
        if isinstance(val, bool) or val is None:
            val = "" if val is None else str(val)
        if isinstance(val, (int, float)):
            return '<c r="%s"><v>%s</v></c>' % (ref, val)
        return '<c r="%s" t="inlineStr"><is><t xml:space="preserve">%s</t></is></c>' % (ref, _xml_escape(val))

    body = []
    for ri, row in enumerate([headers] + list(rows), 1):
        cells = "".join(cell("%s%d" % (_col_letter(ci), ri), v) for ci, v in enumerate(row, 1))
        body.append('<row r="%d">%s</row>' % (ri, cells))

    sheet = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
             '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
             '<sheetData>%s</sheetData></worksheet>' % "".join(body))
    content_types = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                     '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
                     '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
                     '<Default Extension="xml" ContentType="application/xml"/>'
                     '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
                     '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
                     '</Types>')
    rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
            '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
            '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
            '</Relationships>')
    workbook = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
                'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
                '<sheets><sheet name="扫码日志" sheetId="1" r:id="rId1"/></sheets></workbook>')
    wb_rels = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
               '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
               '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/>'
               '</Relationships>')
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("[Content_Types].xml", content_types)
        z.writestr("_rels/.rels", rels)
        z.writestr("xl/workbook.xml", workbook)
        z.writestr("xl/_rels/workbook.xml.rels", wb_rels)
        z.writestr("xl/worksheets/sheet1.xml", sheet)


def export_scans_to_excel(path=None):
    rows = fetch_all_scans()
    if path is None:
        path = os.path.join(BASE_DIR, "扫码日志_%s.xlsx" % datetime.now().strftime("%Y%m%d_%H%M%S"))
    headers = ["序号", "扫码时间", "商家编码", "待发货订单数", "货架在架数", "件数", "提示"]
    data = [[i + 1, r[1], r[2], r[3] or 0, r[4] or 0, r[5] or 0, r[6]] for i, r in enumerate(rows)]
    write_xlsx(path, headers, data)
    return path, len(data)


# ============================ 声音提示 ============================
def play_ok_sound():
    if winsound is None:
        return
    try:
        winsound.Beep(880, 110)
        winsound.Beep(1250, 140)
    except Exception:
        pass


def play_alert_sound():
    if winsound is None:
        return
    try:
        winsound.Beep(500, 220)
        winsound.Beep(500, 220)
        winsound.Beep(500, 260)
    except Exception:
        pass


# ============================ 内置手机网页服务 ============================
WEB_PORT = 8790


def lan_ips():
    """本机局域网 IP，供手机访问。"""
    ips = []
    try:
        import socket
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect(("8.8.8.8", 80))
            ips.append(s.getsockname()[0])
        finally:
            s.close()
    except Exception:
        pass
    try:
        import socket
        for info in socket.getaddrinfo(socket.gethostname(), None, socket.AF_INET):
            ip = info[4][0]
            if ip and not ip.startswith("127.") and ip not in ips:
                ips.append(ip)
    except Exception:
        pass
    return ips


class _WebHandler(BaseHTTPRequestHandler):
    app = None

    def log_message(self, fmt, *args):
        pass

    def _send(self, body, ctype, code=200):
        try:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception:
            pass

    def _json(self, obj, code=200):
        body = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        try:
            self.send_response(code)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception:
            pass

    def do_GET(self):
        app = self.app
        try:
            parsed = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(parsed.query)
            key = (qs.get("k") or [""])[0]
            required = (getattr(app, "web_key", "") or "") if getattr(app, "require_key", True) else ""
            if required and key != required:
                body = ("<!doctype html><meta charset='utf-8'><meta name='viewport' content='width=device-width'>"
                        "<h3 style='font-family:sans-serif'>需要访问口令</h3>"
                        "<p style='font-family:sans-serif'>请用带 ?k=口令 的完整地址打开本页。</p>").encode("utf-8")
                return self._send(body, "text/html; charset=utf-8", code=401)
            if parsed.path in ("/", "/index.html"):
                return self._send(WEB_INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
            if parsed.path == "/api/status":
                return self._json(app.web_status())
            if parsed.path == "/api/index":
                return self._json(app.web_index_payload())
            if parsed.path == "/api/lookup":
                code = (qs.get("code") or [""])[0].strip()
                rel = (qs.get("rel") or ["any"])[0] or "any"
                try:
                    n = int((qs.get("n") or ["0"])[0] or 0)
                except Exception:
                    n = 0
                if not code:
                    return self._json({"error": "缺少 code"}, 400)
                return self._json(app.web_lookup(code, rel, n))
            return self._json({"error": "not found"}, 404)
        except Exception as e:
            return self._json({"error": str(e)[:200]}, 500)


class _V6Server(ThreadingHTTPServer):
    address_family = socket.AF_INET6


def start_web_server(app):
    """启动内置手机网页服务（同时监听 IPv4 和 IPv6，端口被占用就顺延）。"""
    _WebHandler.app = app
    for port in range(WEB_PORT, WEB_PORT + 10):
        servers = []
        try:
            servers.append(ThreadingHTTPServer(("0.0.0.0", port), _WebHandler))
        except OSError:
            pass
        try:
            servers.append(_V6Server(("::", port), _WebHandler))
        except OSError:
            pass
        if servers:
            for s in servers:
                threading.Thread(target=s.serve_forever, daemon=True).start()
            return servers, port
    return None, 0


# ============================ 界面 ============================
class ScanApp:
    GREEN = "#1e9e4a"
    GREEN_BG = "#d6f5df"
    RED = "#c62828"
    RED_BG = "#fde0e0"
    GREY = "#555555"
    GREY_BG = "#eeeeee"

    def __init__(self, root):
        self.root = root
        self.root.title("快麦扫码查待发货 + 货架在架数")
        self.root.geometry("980x680")

        self.session = None
        self.index = {}                 # 编码 → {"qty","orders","main"}
        self.stat = {"total_orders": 0, "included_orders": 0}
        self.loaded_at = "未加载"
        self.shelf_map = {}             # 编码 → {"shelf","all","bins"}
        self.shelf_stat = {}
        self.shelf_at = "未加载"
        self.lock_map = {}              # 编码 → {"lock","sellable","avail"}
        self.lock_at = "未加载"
        self.lock_at_ts = 0
        self._scan_after = None         # 输入停顿自动提交定时器
        self._scanning = False
        self.store_orders = 0           # 订单库里的订单总数（不再把全部订单读进内存）
        self.db_note = ""               # 首次从 JSON 导入的提示
        self.last_sync_ts = 0
        self.last_full_ts = 0
        self._syncing = False
        self.total_est = 0              # 进度条分母（总单数估算）
        self._pull_count = 0
        self._pull_page = 0
        self._pull_t0 = 0
        self.filter_relation = tk.StringVar(value="不限")
        self.filter_n = tk.StringVar(value="1")
        self.scan_text = tk.StringVar()
        self.status_text = tk.StringVar(value="就绪")
        self.sound_on = tk.BooleanVar(value=True)
        self.q = queue.Queue()

        settings = load_settings()
        self.auto_refresh_min = int(settings.get("auto_refresh_min") or AUTO_REFRESH_MIN)
        self.full_refresh_min = int(settings.get("full_refresh_min") or FULL_REFRESH_MIN)
        self.lock_refresh_min = int(settings.get("lock_refresh_min") or LOCK_REFRESH_MIN)
        self.auto_min_var = tk.StringVar(value=str(self.auto_refresh_min))
        self.full_min_var = tk.StringVar(value=str(self.full_refresh_min))
        self.lock_min_var = tk.StringVar(value=str(self.lock_refresh_min))
        self._key_saved = bool(settings.get("require_key", True))
        self.require_key = self._key_saved
        self.key_on = tk.BooleanVar(value=self.require_key)

        self._build_ui()
        init_db()
        self._init_orders_db()
        self.reload_records()
        self._restore_pending_cache()
        self._restore_shelf_cache()
        self._restore_lock_cache()
        self._start_web()          # 数据恢复完再对外服务，避免手机端拿到半成品
        self.root.after(100, self._drain_queue)
        self.root.after(300, lambda: self.sync_pending(background=True))
        self.root.after(600, lambda: self.reload_shelf(background=True))
        self.root.after(900, lambda: self.reload_lock(background=True))
        self.root.after(1000 * 60 * self.auto_refresh_min, self._auto_tick)

    def _init_orders_db(self):
        """建订单库；库为空而 JSON 缓存还在就先导入一次（JSON 保留不删）。"""
        note = import_orders_from_json()
        extra = import_shelf_lock_from_json()
        if extra:
            note = (note + "；" if note else "") + "迁移 " + "、".join(extra)
        self.db_note = note

    def _start_web(self):
        """启动内置手机网页服务并把访问地址显示在界面上。"""
        if not hasattr(self, "_web_cache"):
            self._web_cache = {}
            self._store_version = 0
        settings = load_settings()
        self.web_key = (settings.get("web_key") or "").strip()
        if not self.web_key:
            import random
            self.web_key = "".join(random.choice("ABCDEFGHJKLMNPQRSTUVWXYZ23456789") for _ in range(6))
            settings["web_key"] = self.web_key
            save_settings(settings)
        self.require_key = self._key_saved
        try:
            _servers, port = start_web_server(self)
        except Exception as e:
            self.web_label.config(text="手机网页服务启动失败：%s" % str(e)[:60])
            return
        if not port:
            self.web_label.config(text="手机网页服务启动失败（端口被占用）")
            return
        self.web_port = port
        self._show_web_urls()

    def _show_web_urls(self):
        port = getattr(self, "web_port", 0)
        if not port:
            return
        qs = ("?k=" + self.web_key) if self.require_key else ""
        host = (load_settings().get("public_host") or "").strip()
        urls = []
        if host:
            urls.append("http://%s:%d/%s" % (host, port, qs))
        for ip in lan_ips():
            urls.append("http://%s:%d/%s" % (ip, port, qs))
        if not urls:
            urls.append("http://127.0.0.1:%d/%s" % (port, qs))
        self.web_label.config(text="手机扫码地址：" + "    ".join(urls))

    def on_key_toggle(self):
        """勾选/取消「手机访问需口令」；值没变就直接返回（防止启动时误触发）。"""
        val = bool(self.key_on.get())
        if val == getattr(self, "_key_saved", None):
            return
        self._key_saved = val
        self.require_key = val
        s = load_settings()
        s["require_key"] = val
        save_settings(s)
        self._show_web_urls()
        self.status_text.set("手机访问口令：%s" % ("已开启" if val else "已关闭（任何人知道地址都能看）"))

    def _web_index(self, rel, n):
        """给手机网页用的索引（按筛选条件缓存，store 换代后自动失效）。"""
        if not hasattr(self, "_web_cache"):
            self._web_cache = {}
            self._store_version = 0
        key = (self._store_version, rel, n)
        hit = self._web_cache.get(key)
        if hit is not None:
            return hit
        relation = {"gt": "大于", "lt": "小于", "eq": "等于"}.get(rel, "不限")
        idx, stat = build_index_db(relation, n)
        self._web_cache = {key: (idx, stat)}
        return idx, stat

    def web_status(self):
        idx, stat = self._web_index("any", 0)
        return {
            "live_orders": stat.get("total_orders", 0),
            "shipped_excluded": stat.get("shipped_excluded", 0),
            "included_orders": stat.get("included_orders", 0),
            "codes": len(idx),
            "loaded_at": self.loaded_at,
            "shelf_at": self.shelf_at,
            "lock_at": self.lock_at,
            "breakdown": stat.get("breakdown", {}),
        }

    def web_index_payload(self):
        """给手机端同步的「精简索引」：编码 -> 订单数/件数/一件订单/在架/锁定。

        只包含编码+数字，体积小（几百 KB），手机拉一次就能本地秒查。
        """
        ver = (getattr(self, "_store_version", 0), getattr(self, "_shelf_version", 0),
               getattr(self, "_lock_version", 0))
        cache = getattr(self, "_web_idx_cache", None)
        if cache and cache[0] == ver:
            return cache[1]
        idx, stat = self._web_index("any", 0)
        shelf = self.shelf_map or {}
        lock = self.lock_map or {}
        items = {}
        for code in set(idx.keys()) | set(shelf.keys()) | set(lock.keys()):
            e = idx.get(code) or {}
            sh = shelf.get(code) or {}
            lk = lock.get(code) or {}
            items[code] = {
                "o": int(e.get("orders", 0) or 0),
                "p": int(e.get("qty", 0) or 0),
                "n": int(e.get("ones", 0) or 0),
                "s": int(sh.get("shelf", 0) or 0),
                "l": int(lk.get("lock", 0) or 0),
            }
        payload = {
            "loaded_at": self.loaded_at,
            "shelf_at": self.shelf_at,
            "lock_at": self.lock_at,
            "live_orders": int(stat.get("total_orders", 0) or 0),
            "codes": len(items),
            "items": items,
        }
        self._web_idx_cache = (ver, payload)
        return payload

    def web_lookup(self, code, rel, n):
        idx, _stat = self._web_index(rel, n)
        e = idx.get(code) or {}
        sh = self.shelf_map.get(code) or {}
        lk = self.lock_map.get(code) or {}
        return {
            "code": code,
            "orders": int(e.get("orders", 0) or 0),
            "pieces": int(e.get("qty", 0) or 0),
            "ones": int(e.get("ones", 0) or 0),
            "shelf": int(sh.get("shelf", 0) or 0),
            "bins": (sh.get("bins") or [])[:6],
            "lock": int(lk.get("lock", 0) or 0),
            "sellable": int(lk.get("sellable", 0) or 0),
            "avail": int(lk.get("avail", 0) or 0),
            "shelf_at": self.shelf_at,
            "lock_at": self.lock_at,
        }

    # ---------- UI ----------
    def _build_ui(self):
        main = ttk.Frame(self.root, padding=10)
        main.pack(fill=tk.BOTH, expand=True)
        main.columnconfigure(0, weight=1)

        # 扫码区
        scan_box = ttk.LabelFrame(main, text="扫码查询（扫商家编码，回车提交）")
        scan_box.grid(row=0, column=0, sticky="ew")
        scan_box.columnconfigure(1, weight=1)
        ttk.Label(scan_box, text="商家编码：").grid(row=0, column=0, padx=6, pady=8, sticky="w")
        self.scan_entry = ttk.Entry(scan_box, textvariable=self.scan_text, font=("Consolas", 14))
        self.scan_entry.grid(row=0, column=1, padx=6, pady=8, sticky="ew")
        self.scan_entry.bind("<Return>", lambda e: self.on_scan())
        self.scan_entry.bind("<KeyRelease>", self._on_scan_key)   # 扫码枪不回车时按停顿自动查
        ttk.Button(scan_box, text="查询", command=self.on_scan).grid(row=0, column=2, padx=6, pady=8)
        ttk.Checkbutton(scan_box, text="声音提示", variable=self.sound_on).grid(row=0, column=3, padx=6)
        self.web_label = ttk.Label(scan_box, text="", foreground="#0b5394")
        self.web_label.grid(row=1, column=0, columnspan=4, sticky="w", padx=6, pady=(0, 6))
        ttk.Checkbutton(scan_box, text="手机访问需口令", variable=self.key_on,
                        command=self.on_key_toggle).grid(row=2, column=0, columnspan=4, sticky="w", padx=6, pady=(0, 6))

        # 结果面板（对比一行）
        self.result = tk.Label(
            main, text="待发货订单数  —    货架在架数  —",
            font=("Microsoft YaHei", 22, "bold"),
            bg=self.GREY_BG, fg=self.GREY, height=2, anchor="center",
        )
        self.result.grid(row=1, column=0, sticky="ew", pady=8)
        self.result_detail = tk.Label(main, text="", font=("Microsoft YaHei", 10), fg="#333")
        self.result_detail.grid(row=2, column=0, sticky="w")

        # 商品数量筛选
        flt = ttk.LabelFrame(main, text="商品数量筛选（按订单商品件数加载待发货订单）")
        flt.grid(row=3, column=0, sticky="ew", pady=8)
        ttk.Label(flt, text="订单商品数量").grid(row=0, column=0, padx=6, pady=6)
        ttk.Combobox(flt, textvariable=self.filter_relation, values=FILTER_OPTIONS,
                     width=6, state="readonly").grid(row=0, column=1, padx=4)
        ttk.Entry(flt, textvariable=self.filter_n, width=6).grid(row=0, column=2, padx=4)
        ttk.Label(flt, text="件").grid(row=0, column=3)
        ttk.Button(flt, text="按条件筛选(本地)", command=self.apply_filter).grid(row=0, column=4, padx=10)

        # 操作按钮
        ops = ttk.Frame(main)
        ops.grid(row=4, column=0, sticky="ew", pady=4)
        ttk.Button(ops, text="一键导出全部扫码日志 Excel", command=self.on_export).pack(side=tk.LEFT, padx=4)
        ttk.Button(ops, text="增量刷新", command=lambda: self.sync_pending(background=True)).pack(side=tk.LEFT, padx=4)
        ttk.Button(ops, text="全量重拉", command=lambda: self.full_reload(background=True)).pack(side=tk.LEFT, padx=4)
        ttk.Button(ops, text="刷新货位库存", command=lambda: self.reload_shelf(background=True)).pack(side=tk.LEFT, padx=4)
        ttk.Button(ops, text="刷新锁定数", command=lambda: self.reload_lock(background=True)).pack(side=tk.LEFT, padx=4)
        ttk.Button(ops, text="清空日志", command=self.on_clear_logs).pack(side=tk.LEFT, padx=4)

        # 刷新周期
        itv = ttk.LabelFrame(main, text="刷新周期（分钟）")
        itv.grid(row=5, column=0, sticky="ew", pady=4)
        ttk.Label(itv, text="增量刷新").grid(row=0, column=0, padx=6, pady=6)
        ttk.Spinbox(itv, from_=1, to=180, width=5, textvariable=self.auto_min_var).grid(row=0, column=1)
        ttk.Label(itv, text="全量重拉").grid(row=0, column=2, padx=6)
        ttk.Spinbox(itv, from_=5, to=600, width=5, textvariable=self.full_min_var).grid(row=0, column=3)
        ttk.Label(itv, text="锁定数").grid(row=0, column=4, padx=6)
        ttk.Spinbox(itv, from_=1, to=600, width=5, textvariable=self.lock_min_var).grid(row=0, column=5)
        ttk.Button(itv, text="应用", command=self.apply_intervals).grid(row=0, column=6, padx=10)

        status_row = ttk.Frame(main)
        status_row.grid(row=6, column=0, sticky="ew", pady=4)
        status_row.columnconfigure(0, weight=1)
        self.status_label = ttk.Label(status_row, textvariable=self.status_text, foreground="#0b5394")
        self.status_label.grid(row=0, column=0, sticky="w")
        self.progress = ttk.Progressbar(status_row, mode="indeterminate", length=200)
        self.progress.grid(row=0, column=1, sticky="e", padx=8)
        self.progress.grid_remove()

        # 扫码记录
        log = ttk.LabelFrame(main, text="扫码记录")
        log.grid(row=7, column=0, sticky="nsew")
        main.rowconfigure(7, weight=1)
        cols = ("time", "barcode", "pending", "shelf", "orders", "light")
        self.tree = ttk.Treeview(log, columns=cols, show="headings", height=10)
        for c, t, w in (("time", "扫码时间", 170), ("barcode", "商家编码", 240),
                        ("pending", "待发货订单数", 110), ("shelf", "货架在架数", 100),
                        ("orders", "件数", 70), ("light", "提示", 110)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="center")
        self.tree.pack(fill=tk.BOTH, expand=True)
        self.tree.tag_configure("ok", background=self.GREEN_BG)
        self.tree.tag_configure("alert", background=self.RED_BG)

        self.scan_entry.focus()

    # ---------- 后台线程 / 队列 ----------
    def _run_bg(self, fn, *args):
        t = threading.Thread(target=fn, args=args, daemon=True)
        t.start()

    def _drain_queue(self):
        try:
            while True:
                fn = self.q.get_nowait()
                try:
                    fn()
                except Exception as e:  # UI 回调异常不致命
                    self.status_text.set("界面异常：%s" % e)
        except queue.Empty:
            pass
        self.root.after(100, self._drain_queue)

    # ---------- 待发货加载 ----------
    def _restore_pending_cache(self):
        """启动时读订单库（JSON 导入已先做完）并建索引（立即可扫，之后后台增量刷新）。"""
        if db_orders_total() <= 0:
            self.status_text.set("订单库为空，等待首次全量拉取…")
            return
        meta = load_orders_meta(("loaded_at", "last_sync_ts", "last_full_ts", "total_estimate"))
        self.last_sync_ts = float(meta.get("last_sync_ts") or 0)
        self.last_full_ts = float(meta.get("last_full_ts") or 0)
        try:
            self.total_est = int(float(meta.get("total_estimate") or 0))
        except Exception:
            self.total_est = 0
        self.loaded_at = meta.get("loaded_at") or "未知"
        self.rebuild_local()
        self._show_load_status(from_cache=True)

    def _show_load_status(self, prefix="", from_cache=False):
        tag = "（缓存）" if from_cache else ""
        bd = self.stat.get("breakdown") or {}
        bd_txt = "，".join("%s %d" % (STATUS_LABEL.get(k, k), v) for k, v in bd.items()) if bd else ""
        last = datetime.fromtimestamp(self.last_sync_ts).strftime("%H:%M:%S") if self.last_sync_ts else "—"
        lastfull = datetime.fromtimestamp(self.last_full_ts).strftime("%H:%M") if self.last_full_ts else "—"
        self.status_text.set(
            "%s待发货口径(待发货+待审核+待打印)：%d 单%s%s，剔除已发货 %d 单，按件数条件加载 %d 单；索引 %d 个编码；数据时间 %s；上次增量 %s；上次全量 %s；%s"
            % (prefix, self.stat.get("total_orders", 0), ("（" + bd_txt + "）") if bd_txt else "",
               tag, self.stat.get("shipped_excluded", 0), self.stat.get("included_orders", 0),
               len(self.index), self.loaded_at, last, lastfull,
               EXCLUDE_NOTE + "，" + SHIP_NOTE + (("，" + self.db_note) if getattr(self, "db_note", "") else ""))
        )

    # ---------- 货架在架数加载 ----------
    def _restore_shelf_cache(self):
        """启动时读货位表（首次已从 JSON 缓存迁移过）。"""
        self.shelf_map = db_call(kuaimai_db.load_shelf)
        if not self.shelf_map:
            return
        meta = load_orders_meta(("shelf_at", "shelf_stat"))
        self.shelf_at = meta.get("shelf_at") or "未知"
        self._shelf_version = getattr(self, "_shelf_version", 0) + 1
        try:
            self.shelf_stat = json.loads(meta.get("shelf_stat") or "{}")
        except Exception:
            self.shelf_stat = {}

    def reload_shelf(self, background=True):
        if background:
            self.status_text.set("正在拉取货位库存…")
            self._run_bg(self._worker_shelf)
        else:
            self._worker_shelf()

    def _worker_shelf(self):
        try:
            def prog(count):
                self.q.put(lambda: self.status_text.set("正在拉取货位库存…已拉取 %d 条" % count))
            shelf_map, stat = fetch_shelf_stock(progress=prog)
            loaded_at = now_gmt8()
            save_shelf_db(shelf_map, stat, loaded_at)
            self.q.put(lambda: self._apply_shelf(shelf_map, stat, loaded_at))
        except Exception as e:
            msg = str(e)[:200]
            self.q.put(lambda: self.status_text.set("加载货位库存失败：%s" % msg))

    def _apply_shelf(self, shelf_map, stat, loaded_at):
        self.shelf_map = shelf_map
        self.shelf_stat = stat
        self.shelf_at = loaded_at
        self._shelf_version = getattr(self, "_shelf_version", 0) + 1

    # ---------- 库存锁定数加载 ----------
    def _restore_lock_cache(self):
        """启动时读锁定数表（首次已从 JSON 缓存迁移过）。"""
        self.lock_map = db_call(kuaimai_db.load_lock)
        if not self.lock_map:
            return
        meta = load_orders_meta(("lock_at", "lock_ts"))
        self.lock_at = meta.get("lock_at") or "未知"
        try:
            self.lock_at_ts = float(meta.get("lock_ts") or 0)
        except Exception:
            self.lock_at_ts = 0
        self._lock_version = getattr(self, "_lock_version", 0) + 1

    def reload_lock(self, background=True):
        if background:
            self._run_bg(self._worker_lock)
        else:
            self._worker_lock()

    def _worker_lock(self):
        try:
            def prog(count):
                self.q.put(lambda: self.status_text.set("正在拉取库存锁定数…已拉取 %d 个 SKU" % count))
            lock_map, stat = fetch_lock_stock(progress=prog)
            loaded_at = now_gmt8()
            save_lock_db(lock_map, loaded_at)
            self.q.put(lambda: self._apply_lock(lock_map, loaded_at))
        except Exception as e:
            msg = str(e)[:200]
            self.q.put(lambda: self.status_text.set("加载锁定数失败：%s" % msg))

    def _apply_lock(self, lock_map, loaded_at):
        self.lock_map = lock_map
        self.lock_at = loaded_at
        self.lock_at_ts = time.time()
        self._lock_version = getattr(self, "_lock_version", 0) + 1

    # ---------- 进度显示 ----------
    def _start_progress(self, text):
        self.status_text.set(text)
        try:
            self.progress.stop()
            self.progress.config(mode="indeterminate")
            self.progress.grid()
            self.progress.start(80)
        except Exception:
            pass

    def _stop_progress(self):
        try:
            self.progress.stop()
            self.progress.grid_remove()
        except Exception:
            pass
        self.root.title("快麦扫码查待发货 + 货架在架数")

    def _show_pull_progress(self, count, page, t0):
        self._pull_count, self._pull_page, self._pull_t0 = count, page, t0
        self._render_pull_progress()

    def _render_pull_progress(self):
        count, page, t0 = self._pull_count, self._pull_page, self._pull_t0
        el = max(0.0, time.time() - t0)
        rate = count / el if el > 0 else 0
        if self.total_est > 0:
            try:
                self.progress.stop()
                self.progress.config(mode="determinate", maximum=self.total_est, value=count)
                self.progress.grid()
            except Exception:
                pass
            pct = min(100.0, count * 100.0 / self.total_est)
            body = "共约 %d 单，已拉取 %d 单（%.1f%%，已处理 %d 个分片，用时 %d:%02d，约 %.0f 单/秒）" % (
                self.total_est, count, pct, page, int(el) // 60, int(el) % 60, rate)
        else:
            body = "已拉取 %d 单（已处理 %d 个分片，用时 %d:%02d，约 %.0f 单/秒）；总数统计中…" % (
                count, page, int(el) // 60, int(el) % 60, rate)
        self.status_text.set("正在全量拉取待发货订单…" + body)
        self.root.title("快麦扫码查询 — 拉取 %d / %s 单" % (count, self.total_est or "统计中"))
        try:      # 同步写进度文件，窗口外也能看
            save_json(PULL_PROGRESS_FILE, {
                "mode": "full", "pulled": count, "page": page,
                "total_estimate": self.total_est,
                "percent": round(min(100.0, count * 100.0 / self.total_est), 1) if self.total_est else None,
                "elapsed_sec": int(el), "rate_per_sec": round(rate, 1),
                "updated_at": now_gmt8(),
            })
        except Exception:
            pass

    def _worker_total_estimate(self):
        """与拉取并行：估算总单数，用于把进度条变成确定值。"""
        try:
            total = estimate_pending_total()
            if total > 0:
                self.q.put(lambda: self._apply_total_estimate(total))
        except Exception:
            pass

    def _apply_total_estimate(self, total):
        self.total_est = total
        if self._syncing and self._pull_count:
            self._render_pull_progress()
        elif self._syncing:
            self.status_text.set("正在全量拉取待发货订单…共约 %d 单，已拉取 %d 单" % (total, self._pull_count))

    def _filter_values(self):
        relation = self.filter_relation.get()
        try:
            n = int(self.filter_n.get().strip() or "0")
        except Exception:
            n = 0
        return relation, n

    def rebuild_local(self):
        """本地重建索引：走 SQLite 聚合，不再把全部订单读进内存。"""
        relation, n = self._filter_values()
        self.index, self.stat = build_index_db(relation, n)
        self.store_orders = int(self.stat.get("store_orders", 0) or 0)

    def apply_filter(self):
        """改件数筛选：纯本地重建索引，不联网。"""
        if db_orders_total() <= 0:
            self.status_text.set("订单库还没有数据，先点「全量重拉」")
            return
        self.rebuild_local()
        self._show_load_status(prefix="已按条件筛选：")

    def apply_intervals(self):
        """应用界面上的三个刷新周期（分钟），并持久化。"""
        def _iv(var, lo, hi, default):
            try:
                v = int(float(var.get()))
            except Exception:
                v = default
            return max(lo, min(hi, v))
        self.auto_refresh_min = _iv(self.auto_min_var, 1, 180, AUTO_REFRESH_MIN)
        self.full_refresh_min = _iv(self.full_min_var, 5, 600, FULL_REFRESH_MIN)
        self.lock_refresh_min = _iv(self.lock_min_var, 1, 600, LOCK_REFRESH_MIN)
        self.auto_min_var.set(str(self.auto_refresh_min))
        self.full_min_var.set(str(self.full_refresh_min))
        self.lock_min_var.set(str(self.lock_refresh_min))
        save_settings({"auto_refresh_min": self.auto_refresh_min,
                       "full_refresh_min": self.full_refresh_min,
                       "lock_refresh_min": self.lock_refresh_min})
        self.status_text.set("周期已应用：增量 %d 分钟 / 全量 %d 分钟 / 锁定数 %d 分钟"
                             % (self.auto_refresh_min, self.full_refresh_min, self.lock_refresh_min))

    def _save_orders_meta(self):
        """把订单库元信息（数据时间/同步水位/总数估算）落库，重启后可恢复。"""
        save_orders_meta(loaded_at=self.loaded_at, last_sync_ts=self.last_sync_ts,
                         last_full_ts=self.last_full_ts, total_estimate=self.total_est)

    def sync_pending(self, background=True):
        """增量刷新（按修改时间）。"""
        if self._syncing:
            return
        self._syncing = True
        if background:
            self._start_progress("增量刷新中…")
            self._run_bg(self._worker_sync)
        else:
            self._worker_sync()

    def full_reload(self, background=True):
        """全量重拉（首次或需要重建时用，耗时约 20 分钟）。"""
        if self._syncing:
            return
        self._syncing = True
        if background:
            self._start_progress("正在全量拉取待发货订单…总数统计中…")
            self._run_bg(self._worker_full)
        else:
            self._worker_full()

    def _worker_sync(self):
        try:
            if db_orders_total() <= 0:
                self._worker_full()          # 库里没数据 → 直接走全量
                return
            def prog(c):
                self.q.put(lambda: self.status_text.set("增量刷新中…已处理 %d 单" % c))
            processed, sync_started, ok = incremental_sync_db(self.last_sync_ts, progress=prog)
            self.q.put(lambda: self._apply_sync(processed, sync_started, ok))
        except Exception as e:
            msg = str(e)[:200]
            self.q.put(lambda: self._finish_sync("增量刷新失败：%s" % msg))

    def _worker_full(self):
        t0 = time.time()
        try:
            if not self.total_est:      # 与拉取并行估算总数（首次或没有缓存时）
                self._run_bg(self._worker_total_estimate)
            def prog(count, page):
                self.q.put(lambda: self._show_pull_progress(count, page, t0))
            stats = {}
            store = full_pull_store_parallel(progress=prog, stats=stats)
            # 安全阀：拉取结果为空则保留原有数据，写库前先拦一次
            if not store:
                self.q.put(lambda: self._finish_sync("全量拉取结果为空，已保留原有数据（未覆盖数据库）"))
                return
            self.q.put(lambda: self.status_text.set("正在写入订单库（事务内整体替换）…"))
            n_o, n_i = replace_orders_db(store, loaded_at=now_gmt8())
            self.q.put(lambda: self._apply_full(n_o, n_i, time.time(), stats))
        except Exception as e:
            msg = str(e)[:200]
            self.q.put(lambda: self._finish_sync("全量拉取失败：%s" % msg))

    def _apply_sync(self, processed, sync_started, ok=True):
        if not ok:
            self._finish_sync("增量刷新失败（接口无响应/限流），已保留原有数据，同步水位未推进")
            return
        self.last_sync_ts = sync_started
        self.loaded_at = now_gmt8()
        self._store_version = getattr(self, "_store_version", 0) + 1
        self.rebuild_local()
        self._save_orders_meta()
        self._syncing = False
        self._stop_progress()
        self._show_load_status(prefix="增量刷新完成(处理 %d 单变更)：" % processed)

    def _apply_full(self, n_orders, n_items, sync_started, stats=None):
        self.last_sync_ts = sync_started
        self.last_full_ts = time.time()
        self._store_version = getattr(self, "_store_version", 0) + 1
        self.loaded_at = now_gmt8()
        self.rebuild_local()
        self._save_orders_meta()
        self._syncing = False
        self._stop_progress()
        extra = ""
        if stats:
            extra = "扫描 %s 单，" % stats.get("pulled", 0)
        self._show_load_status(prefix="全量拉取完成(%s写库 %d 单 / %d 明细)：" % (extra, n_orders, n_items))
        try:
            save_json(PULL_PROGRESS_FILE, {
                "mode": "done", "pulled": n_orders, "updated_at": now_gmt8(),
            })
        except Exception:
            pass

    def _finish_sync(self, status=None):
        self._syncing = False
        self._stop_progress()
        if status:
            self.status_text.set(status)

    def _auto_tick(self):
        """定时：到点跑全量（每 full_refresh_min 分钟），其余时候跑增量；并定期刷新锁定数。"""
        if not self._syncing:
            if (time.time() - self.last_full_ts) >= self.full_refresh_min * 60:
                self.full_reload(background=True)
            else:
                self.sync_pending(background=True)
        if time.time() - self.lock_at_ts > self.lock_refresh_min * 60:
            self.reload_lock(background=True)
        self.root.after(1000 * 60 * self.auto_refresh_min, self._auto_tick)

    # ---------- 扫码 ----------
    def _on_scan_key(self, event):
        """扫码枪多数以回车结尾（Return 已绑定）；部分不回车，这里按输入停顿自动查询。"""
        if event.keysym in ("Return", "KP_Enter", "Tab", "Escape"):
            return
        if self._scan_after:
            try:
                self.root.after_cancel(self._scan_after)
            except Exception:
                pass
            self._scan_after = None
        if len(self.scan_text.get().strip()) >= 3:
            self._scan_after = self.root.after(350, self._auto_scan)

    def _auto_scan(self):
        self._scan_after = None
        if self.scan_text.get().strip() and not self._scanning:
            self.on_scan()

    def _finish_scan(self, status=None):
        self._scanning = False
        if status:
            self.status_text.set(status)

    def on_scan(self):
        if self._scan_after:
            try:
                self.root.after_cancel(self._scan_after)
            except Exception:
                pass
            self._scan_after = None
        code = self.scan_text.get().strip()
        if not code:
            self.status_text.set("请输入/扫入商家编码")
            return
        if self._scanning:
            return
        self._scanning = True
        self.status_text.set("查询中：%s …" % code)
        self._run_bg(self._worker_scan, code)

    def _worker_scan(self, code):
        try:
            entry = self.index.get(code) or {"qty": 0, "orders": 0, "ones": 0, "main": False}
            pending = int(entry.get("qty", 0))
            orders_count = int(entry.get("orders", 0))
            ones = int(entry.get("ones", 0))

            # 货架在架数：直接取本地货位缓存（秒查，不联网）
            shelf_entry = self.shelf_map.get(code) or {}
            shelf = int(shelf_entry.get("shelf", 0) or 0)
            bins = shelf_entry.get("bins") or []
            shelf_note = "货位缓存 %s" % self.shelf_at if self.shelf_map else "货位缓存未加载"

            # 库存锁定数：本地缓存
            lock_entry = self.lock_map.get(code) or {}
            lock_n = int(lock_entry.get("lock", 0) or 0)
            sell_n = int(lock_entry.get("sellable", 0) or 0)
            avail_n = int(lock_entry.get("avail", 0) or 0)

            light = "绿" if orders_count > 0 else "红"
            insert_scan(code, orders_count, shelf, pending, light)
            self.q.put(lambda: self._apply_scan(code, orders_count, pending, ones, shelf, shelf_note,
                                               bins, lock_n, sell_n, avail_n))
        except Exception as e:
            msg = str(e)[:200]
            self.q.put(lambda: self._finish_scan("扫码查询失败：%s" % msg))

    def _apply_scan(self, code, orders_count, pending, ones, shelf, shelf_note, bins,
                    lock_n=0, sell_n=0, avail_n=0):
        self._scanning = False
        ok = orders_count > 0
        if ok and pending > shelf:
            hint = "件数 %d > 在架 %d ⚠ 需补货" % (pending, shelf)
        elif ok:
            hint = "有待发货订单 ✔ 可以拣货"
        else:
            hint = "没有待发货订单"
        self.result.config(
            text="%s\n待发货订单数  %d 单    货架在架数  %d" % (code, orders_count, shelf),
            bg=self.GREEN_BG if ok else self.RED_BG,
            fg=self.GREEN if ok else self.RED,
        )
        bin_txt = "、".join("%s×%d" % (b[0], b[1]) for b in bins[:5]) if bins else "无在架货位"
        self.result_detail.config(
            text="件数 %d；其中“一件订单” %d 单；锁定数 %d（可售 %d / 可用 %d）\n货位来源：%s；货位：%s；%s"
            % (pending, ones, lock_n, sell_n, avail_n, shelf_note, bin_txt, hint),
        )
        self.tree.insert("", 0, values=(now_gmt8(), code, orders_count, shelf, pending,
                                        "绿(有货)" if ok else "红(无待发)"),
                         tags=("ok",) if ok else ("alert",))
        self.status_text.set("查询完成：%s（待发货 %d 单 / 件数 %d / 在架 %d）" % (
            code, orders_count, pending, shelf))
        self.scan_text.set("")
        self.scan_entry.focus()
        if self.sound_on.get():
            self._run_bg(play_ok_sound if ok else play_alert_sound)

    # ---------- 导出 / 清理 ----------
    def on_export(self):
        try:
            path, n = export_scans_to_excel()
            self.status_text.set("已导出 %d 条扫码日志：%s" % (n, path))
            messagebox.showinfo("导出成功", "已导出 %d 条扫码日志到：\n%s" % (n, path))
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    def on_clear_logs(self):
        if not messagebox.askyesno("确认", "确定清空全部扫码日志吗？此操作不可撤销。"):
            return
        conn = get_conn()
        conn.execute("DELETE FROM scan_record")
        conn.commit()
        conn.close()
        self.reload_records()
        self.status_text.set("已清空扫码日志")

    def reload_records(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for r in reversed(fetch_all_scans()):
            pid, st, bc, pq, sh, oc, light = r
            ok = (light == "绿")
            self.tree.insert("", 0, values=(st, bc, pq or 0, sh or 0, oc or 0,
                                            "绿(有货)" if ok else "红(无待发)"),
                             tags=("ok",) if ok else ("alert",))


def run_selftest():
    """无界面自检：拉取待发货、建索引、查库存。"""
    print("[selftest] session ok:", bool(current_session()))
    store = full_pull_store(max_pages=2)   # 自检只取少量页，避免拉全量
    print("[selftest] 样本订单数:", len(store))
    index, stat = rebuild_index(store, "不限", 0)
    print("[selftest] 索引编码数:", len(index), "stat:", stat)
    sample = next(iter(index.items()), None)
    if sample:
        code, e = sample
        print("[selftest] 示例编码 %s → 待发货 %d 件 / %d 单" % (code, e["qty"], e["orders"]))
        smap, sstat = fetch_shelf_stock()
        print("[selftest] 货位库存:", sstat)
        se = smap.get(code) or {}
        print("[selftest] 该编码货架在架数:", se.get("shelf"), "货位:", se.get("bins"))
    # 件数筛选示例与增量同步演示
    for rel, n in (("大于", 1), ("等于", 1)):
        _i, s = rebuild_index(store, rel, n)
        print("[selftest] 筛选 %s %d → 加载 %d/%d 单" % (rel, n, s["included_orders"], s["total_orders"]))
    work = dict(store)
    processed, started = incremental_sync(work, time.time() - 600)
    print("[selftest] 增量同步: 处理 %d 单，store 由 %d → %d 单" % (processed, len(store), len(work)))


def main():
    if "--selftest" in sys.argv:
        run_selftest()
        return
    try:
        init_db()
        root = tk.Tk()
        ScanApp(root)
        root.mainloop()
    except Exception:
        detail = traceback.format_exc()
        try:
            sys.stderr.write(detail)
        except Exception:
            pass
        try:
            messagebox.showerror("启动失败", detail)
        except Exception:
            pass
        raise


if __name__ == "__main__":
    main()
