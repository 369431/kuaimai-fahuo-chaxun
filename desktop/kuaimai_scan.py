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
    from kuaimai_webui import WEB_INDEX_HTML, PICK_HTML, ORDER_HTML, STOCK_HTML, STOCKTAKE_HTML
    from kuaimai_login_ui import LOGIN_HTML
except Exception:
    WEB_INDEX_HTML = "<h1>缺少 kuaimai_webui.py</h1>"
    PICK_HTML = WEB_INDEX_HTML
    ORDER_HTML = WEB_INDEX_HTML
    STOCK_HTML = WEB_INDEX_HTML
    STOCKTAKE_HTML = WEB_INDEX_HTML
    LOGIN_HTML = WEB_INDEX_HTML
try:
    import kuaimai_auth as auth
except Exception:
    auth = None
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
from tkinter import ttk, messagebox, filedialog, simpledialog

try:
    import winsound  # Windows 声光提示
except Exception:  # pragma: no cover
    winsound = None

# ====================== 【配置区域】======================
# 【发布版这里不放任何密钥】首次使用请在程序界面点「API 设置」填写：
#   appKey / appSecret / refreshToken / sessionId(accessToken)
# 填完存在 exe 同目录的 kuaimai_api.json，以后就直接用。
KM_APP_KEY = ""
KM_APP_SECRET = ""
KM_REFRESH_TOKEN = ""
INIT_SESSION_ID = ""
# 非密钥默认值（一般不用改）
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
API_FILE = os.path.join(BASE_DIR, "kuaimai_api.json")         # API 参数（界面可改；没有它就用写死的默认值）
# 账号文件必须和数据文件同目录：打包后如果用模块自身的路径，会写进临时解包目录（每次启动被清掉）
if auth is not None:
    try:
        auth.BASE_DIR = BASE_DIR
        auth.USERS_FILE = os.path.join(BASE_DIR, "kuaimai_users.json")
    except Exception:
        pass
_INSTANCE_MUTEX = None       # 单实例互斥体句柄（进程退出自动释放）

PENDING_CACHE_MAX_AGE = 30 * 60      # 待发货缓存视为“新鲜”的秒数
STOCK_CACHE_TTL = 120                # 可售库存缓存有效期（秒）
SHELF_CACHE_TTL = 300                # 货架(货位)在架数缓存有效期（秒）
PAGE_SIZE = 500                      # erp.trade.list.query 文档写最大200，实测 500 可用（1000 报错）
MAX_PAGES = 600                      # 安全上限，避免异常死循环
SHELF_PAGE_SIZE = 500                # asso.goods.section.sku.query 实际单页上限 500
MAX_SHELF_PAGES = 200
LOCK_PAGE_SIZE = 100                 # stock.api.status.query 单页最大 100
LOCK_REFRESH_MIN = 10                # 锁定数自动刷新间隔（分钟）
SHELF_REFRESH_MIN = 5                # 货位在架数自动刷新间隔（分钟）

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


def ci_key(code):
    """编码归一化：快麦的商家编码不区分字母大小写，比较时统一转大写。"""
    return str(code or "").strip().upper()


def dict_get_ci(d, code):
    """在字典里按编码取值：先精确匹配，再忽略大小写。返回 (值, 实际键)。

    命中后返回库里那个写法（用于显示和记录）；上千个键的线性比对也就毫秒级。
    """
    if not d:
        return None, code
    v = d.get(code)
    if v is not None:
        return v, code
    t = ci_key(code)
    if not t:
        return None, code
    for k, val in d.items():
        if ci_key(k) == t:
            return val, k
    return None, code


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
    """通用调用：公共参数 + 业务参数 → POST 表单（参数来自 API_CONF，界面上可改）。"""
    if not (API_CONF.get("appKey") and API_CONF.get("appSecret")):
        raise RuntimeError("未配置 API 参数：请点界面上的「API 设置」填写 appKey / appSecret / "
                           "refreshToken / sessionId 后保存")
    params = {
        "method": method,
        "appKey": API_CONF["appKey"],
        "timestamp": now_gmt8(),
        "format": "json",
        "version": str(API_CONF.get("version") or "1.0"),
        "sign_method": API_CONF.get("signMethod") or KM_SIGN_METHOD,
        "session": session,
    }
    params.update({k: v for k, v in business.items() if v not in (None, "")})
    params["sign"] = sign(params, API_CONF["appSecret"], params["sign_method"],
                          bool(API_CONF.get("signUpper")))
    body = urllib.parse.urlencode(params).encode("utf-8")
    req = urllib.request.Request(
        API_CONF.get("gateway") or GATEWAY,
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


# ============================ API 参数（界面上可改） ============================
# 写死的值只当「默认值」；exe 同目录的 kuaimai_api.json 里的同名字段会覆盖它。
# 换账号 / 换网关 / 换版本都不用重新打包：界面上「API 设置」改完保存即可。
DEFAULT_API = {
    "gateway": GATEWAY,
    "version": "1.0",
    "signMethod": KM_SIGN_METHOD,
    "signUpper": KM_SIGN_UPPER,
    "appKey": KM_APP_KEY,
    "appSecret": KM_APP_SECRET,
    "refreshToken": KM_REFRESH_TOKEN,
    "sessionId": INIT_SESSION_ID,
}
API_CONF = dict(DEFAULT_API)


def reload_api_conf():
    """读 kuaimai_api.json 覆盖默认值（文件不存在/读不出就用写死的默认值）。"""
    global API_CONF
    conf = dict(DEFAULT_API)
    saved = load_json(API_FILE, None)
    if isinstance(saved, dict):
        for k in DEFAULT_API:
            if k in saved and saved[k] not in (None, ""):
                conf[k] = saved[k]
    API_CONF = conf
    return conf


def save_api_conf(conf):
    """写 kuaimai_api.json 并立即生效；同时清掉旧会话缓存（换了账号旧 session 无效）。"""
    out = {}
    for k in DEFAULT_API:
        v = conf.get(k, DEFAULT_API[k])
        if k == "signUpper":
            v = bool(v)
        elif k == "version":
            v = str(v or "1.0").strip() or "1.0"
        else:
            v = str(v or "").strip()
        out[k] = v
    save_json(API_FILE, out)
    reload_api_conf()
    try:
        if os.path.exists(CACHE_FILE):
            os.remove(CACHE_FILE)
    except Exception:
        pass
    return out


reload_api_conf()


# ============================ Token 续期 ============================
def load_token_cache():
    return load_json(CACHE_FILE, {"sessionId": API_CONF.get("sessionId") or INIT_SESSION_ID,
                                "last_refresh_ts": 0})


def save_token_cache(session_id, last_refresh_ts):
    save_json(CACHE_FILE, {"sessionId": session_id, "last_refresh_ts": last_refresh_ts})


def refresh_access_token(old_session):
    """open.token.refresh（续期）：成功返回的 sessionId 不变，仅有效期 +30 天。限流 1 次/小时。"""
    res = api_call("open.token.refresh",
                   {"refreshToken": API_CONF.get("refreshToken") or KM_REFRESH_TOKEN}, old_session)
    if isinstance(res, dict) and res.get("success"):
        data = res.get("data") or {}
        new_session = data.get("sessionId") or old_session
        save_token_cache(new_session, datetime.now().timestamp())
        return new_session
    code = res.get("code") if isinstance(res, dict) else "?"
    msg = res.get("msg") if isinstance(res, dict) else str(res)[:100]
    raise RuntimeError("刷新会话失败 code=%s msg=%s" % (code, msg))


def current_session():
    """当前会话：优先本地缓存，否则用设置里的 sessionId。不主动联网刷新（刷新接口限流 1 次/小时）。"""
    return load_token_cache().get("sessionId") or API_CONF.get("sessionId") or INIT_SESSION_ID


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
    # 拣货会话（手机端拣货进度持久化：退出页面/关浏览器也能接着拣）
    cur.execute(
        """CREATE TABLE IF NOT EXISTS pick_batch
           (batch TEXT PRIMARY KEY,
            created_at TEXT,
            ended_at TEXT,
            status TEXT,
            days INTEGER,
            groups_json TEXT)"""
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


# ============================ 拣货会话（持久化） ============================
def pick_save(batch, orders, status="running", days=3, created_at=None):
    conn = get_conn()
    payload = json.dumps({"v": 2, "orders": orders or []}, ensure_ascii=False)
    conn.execute(
        "INSERT OR REPLACE INTO pick_batch(batch,created_at,ended_at,status,days,groups_json)"
        " VALUES (?,?,?,?,?,?)",
        (str(batch), created_at or now_gmt8(), "" if status == "running" else now_gmt8(),
         status, int(days or 3), payload))
    conn.commit()
    conn.close()


def _norm_orders(data):
    """兼容旧存档：旧结构是「按编码合并的组」，这里并成「一单（快递单号）一卡、卡内多行商品」。"""
    if isinstance(data, dict):
        return data.get("orders") or []
    out, index = [], {}
    for g in (data or []):
        sids = g.get("sids") or []
        exp = g.get("exp_a") or ""
        # 旧组里同一单的多个商品：同 seq + 同快递单号 → 并到同一张卡
        key = "%s|%s" % (g.get("seq_a"), exp if len(sids) <= 1 else (sids[0] if sids else exp))
        o = index.get(key)
        if o is None:
            o = {"seq": g.get("seq_a"), "seq_b": g.get("seq_b"),
                 "express": exp, "sid": (sids[0] if sids else ""), "lines": []}
            index[key] = o
            out.append(o)
        o["lines"].append({"code": g.get("code"), "qty": g.get("qty"),
                            "bins": g.get("bins"), "shelf": g.get("shelf"),
                            "state": g.get("state") or "pending"})
    return out


def _pick_row(batch, row):
    try:
        data = json.loads(row[5] or "{}")
    except Exception:
        data = {}
    return {"batch": batch if batch is not None else row[0], "created_at": row[1],
            "ended_at": row[2], "status": row[3], "days": row[4],
            "orders": _norm_orders(data)}


def pick_get(batch):
    conn = get_conn()
    row = conn.execute("SELECT batch,created_at,ended_at,status,days,groups_json"
                       " FROM pick_batch WHERE batch=?", (str(batch),)).fetchone()
    conn.close()
    return _pick_row(None, row) if row else None


def pick_running():
    conn = get_conn()
    row = conn.execute("SELECT batch,created_at,ended_at,status,days,groups_json FROM pick_batch"
                       " WHERE status='running' ORDER BY created_at DESC LIMIT 1").fetchone()
    conn.close()
    return _pick_row(None, row) if row else None


def pick_end(batch):
    d = pick_get(batch)
    if not d:
        return None
    pick_save(d["batch"], d.get("orders") or [], "ended", d["days"], d["created_at"])
    return pick_get(batch)


def pick_end_others(keep_batch=None):
    """同时只留一个进行中的批次：把其它 running 的标为已结束。

    keep_batch=None 表示全部结束（清理历史遗留的多个 running）。
    """
    conn = get_conn()
    try:
        if keep_batch:
            rows = conn.execute("SELECT batch FROM pick_batch WHERE status='running' AND batch<>?",
                                (str(keep_batch),)).fetchall()
        else:
            rows = conn.execute("SELECT batch FROM pick_batch WHERE status='running'").fetchall()
    finally:
        conn.close()
    ended = []
    for (b,) in rows:
        pick_end(b)
        ended.append(b)
    return ended


def zone_of(bins):
    """从货位取分区字母（A-3-1-2 → A）。"""
    m = re.match(r"\s*([A-Za-z])", str(bins or ""))
    return m.group(1).upper() if m else ""


def zone_rank(z):
    """A/B/C/D 依次，其它排最后。"""
    return "ABCD".index(z) if z in ("A", "B", "C", "D") else 9


def bin_label(bins):
    """清单里显示用的货位文案：无货位统一写「无货位」。"""
    b = str(bins or "").strip()
    return b if b and b != "无在架货位" else "无货位"


def fmt_order_line(seq, items, express=""):
    """按单显示的一行：第 N 张 [快递单号] 共 X 件  编码×件数→货位；…"""
    parts = []
    for code, num, bins in items:
        parts.append("%s×%s→%s" % (code, num, bins))
    head = "第 %-4s张" % seq
    if express:
        head += "（%s）" % express
    return "%s %d件  %s" % (head, len(items), "；".join(parts))


def _pick_group_excluded(code):
    """拣货组是否应排除（占位/补偿类商品：1166、买家秀、圆虹包…）。"""
    code = str(code or "").strip()
    if not code:
        return False
    head = re.split(r"[-\s（()）/,]", code)[0]
    if head in EXCLUDE_CODE_HEADS:
        return True
    return any(k and k in code for k in EXCLUDE_NAME_KEYWORDS)


def series_matches(idx, code):
    """主编码/前缀查询：输入 9687 → 所有 9687-* 规格（返回 (keys, 是否系列)）。

    精确命中且没有其它以它开头的编码 → 就查这一个（返回单元素列表）。
    """
    code = str(code or "").strip()
    if not code:
        return [], False
    up = code.upper()
    exact_entry, canon = dict_get_ci(idx, code)
    pref = sorted([k for k in idx if k.upper().startswith(up)])
    if len(pref) > 1:
        return pref, True
    if exact_entry:
        return [canon], False
    return pref, False


def build_pick_orders(orders, shelf_lookup):
    """按单建清单：一单一张卡；lines = 该单每个商品（同 SKU 多行合并成一行，只点一次）。"""
    out = []
    for o in orders:
        merged, order_lines = {}, []
        for code, num in (o.get("items") or []):
            key = str(code)
            if key in merged:
                merged[key]["qty"] += int(num or 0)      # 同一 SKU 多行 → 件数累加，只算一行
                continue
            bins, qty = shelf_lookup(code)
            line = {"code": code, "qty": int(num or 0), "bins": bins, "shelf": qty,
                    "state": "pending"}
            merged[key] = line
            order_lines.append(line)
        if not order_lines:
            continue
        seq = o.get("seq") or 0
        out.append({"seq": seq, "seq_b": seq, "express": o.get("express") or "",
                    "sid": o.get("sid") or "", "lines": order_lines})
    return out


def order_state(o):
    """整单状态：还有待拣→pending；无待拣且有缺货→short；全部完成→done。"""
    ls = o.get("lines") or []
    if not ls:
        return "done"
    if any((l.get("state") or "pending") == "pending" for l in ls):
        return "pending"
    if any(l.get("state") == "short" for l in ls):
        return "short"
    return "done"


def build_pick_groups(orders, shelf_lookup):
    """把订单明细合并成「相邻同编码同货位」的拣货组（按打印序号排列）。

    shelf_lookup(code) -> (货位文本, 在架数)
    """
    groups = []
    for o in orders:
        items = o.get("items") or []
        if not items:
            items = [("", 0)]
        for code, num in items:
            bins, qty = shelf_lookup(code)
            seq = o.get("seq") or 0
            if groups and groups[-1]["code"] == code and groups[-1]["bins"] == bins:
                g = groups[-1]
                g["seq_b"] = seq
                g["qty"] += int(num or 0)
                g["rows"] += 1
                if o.get("express"):
                    g["exp_b"] = o.get("express")
                    if not g.get("exp_a"):
                        g["exp_a"] = o.get("express")
                if len(g.get("sids") or []) < 400:
                    g.setdefault("sids", []).append(o.get("sid"))
            else:
                groups.append({"seq_a": seq, "seq_b": seq, "code": code, "qty": int(num or 0),
                               "bins": bins, "shelf": qty, "rows": 1, "state": "pending",
                               "exp_a": o.get("express") or "", "exp_b": o.get("express") or "",
                               "sids": [o.get("sid")]})
    return groups


def insert_scan(barcode, pending_qty, shelf_qty, orders_count, light, who="", print_num=""):
    conn = get_conn()
    cur = conn.cursor()
    for stmt in ("ALTER TABLE scan_record ADD COLUMN who TEXT",
                 "ALTER TABLE scan_record ADD COLUMN print_num TEXT",
                 "ALTER TABLE scan_record ADD COLUMN printed INTEGER DEFAULT 0"):
        try:
            cur.execute(stmt)
        except Exception:
            pass
    cur.execute(
        "INSERT INTO scan_record(scan_time,barcode,order_no,goods_name,status,pending_qty,shelf_qty,orders_count,who,print_num,printed)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,0)",
        (now_gmt8(), barcode, "", "", light, int(pending_qty), int(shelf_qty), int(orders_count),
         str(who or ""), str(print_num or "")),
    )
    conn.commit()
    conn.close()


def insert_canprint(code, qty, who="", bins="", pending_qty=0, shelf_qty=0):
    """网页现货可发点「可发」并输入数量 → 写一条扫码日志，可打单数量 = 输入的数量。"""
    conn = get_conn()
    cur = conn.cursor()
    for stmt in ("ALTER TABLE scan_record ADD COLUMN who TEXT",
                 "ALTER TABLE scan_record ADD COLUMN print_num TEXT",
                 "ALTER TABLE scan_record ADD COLUMN printed INTEGER DEFAULT 0"):
        try:
            cur.execute(stmt)
        except Exception:
            pass
    cur.execute(
        "INSERT INTO scan_record(scan_time,barcode,order_no,goods_name,status,pending_qty,shelf_qty,orders_count,who,print_num,printed)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,0)",
        (now_gmt8(), str(code), "", str(bins or ""), "可", int(pending_qty or 0), int(shelf_qty or 0), 0,
         str(who or ""), str(int(qty)),),
    )
    conn.commit()
    conn.close()


def set_printed(rec_id, flag):
    """把某条扫码日志标成「已打」（1）/ 未打（0）。返回是否写成功。"""
    want = 1 if flag else 0
    for _try in range(4):
        conn = None
        try:
            conn = get_conn()
            try:
                conn.execute("ALTER TABLE scan_record ADD COLUMN printed INTEGER DEFAULT 0")
                conn.commit()
            except Exception:
                pass
            conn.execute("UPDATE scan_record SET printed=? WHERE id=?", (want, int(rec_id)))
            conn.commit()
            got = conn.execute("SELECT COALESCE(printed,0) FROM scan_record WHERE id=?",
                               (int(rec_id),)).fetchone()
            conn.close()
            if got is not None and int(got[0] or 0) == want:
                return True
        except Exception:
            try:
                if conn:
                    conn.close()
            except Exception:
                pass
            time.sleep(0.25)
    return False


def fetch_all_scans():
    conn = get_conn()
    cur = conn.cursor()
    for stmt in ("ALTER TABLE scan_record ADD COLUMN who TEXT",
                 "ALTER TABLE scan_record ADD COLUMN print_num TEXT",
                 "ALTER TABLE scan_record ADD COLUMN printed INTEGER DEFAULT 0"):
        try:
            cur.execute(stmt)
            conn.commit()
        except Exception:
            pass
    rows = cur.execute(
        "SELECT id,scan_time,barcode,pending_qty,shelf_qty,orders_count,status,COALESCE(who,''),"
        "COALESCE(print_num,''),COALESCE(printed,0) FROM scan_record ORDER BY id ASC"
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
            "urgent": bool(trade.get("isUrgent")),
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
            e = index.setdefault(code, {"qty": 0, "orders": 0, "ones": 0, "main": False,
                                        "uo": 0, "up": 0})
            e["qty"] += qty
            e["orders"] += 1
            if int(rec.get("count") or 0) == 1:
                e["ones"] += 1
            if rec.get("urgent"):
                e["uo"] += 1        # 加急订单数
                e["up"] += qty      # 加急件数
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
            sec = str(row.get("goodsSectionCode") or "").strip()
            if sec:
                # 在架为 0 也要留下货位：拣货时要看"实际货位"，没在架不等于没货位
                for b in e["bins"]:
                    if b[0] == sec:
                        b[1] += qty
                        break
                else:
                    e["bins"].append([sec, qty])
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
    headers = ["序号", "扫码时间", "商家编码", "待发货订单数", "货架在架数", "件数", "扫码账号", "提示"]
    data = [[i + 1, r[1], r[2], r[3] or 0, r[4] or 0, r[5] or 0, (r[7] if len(r) > 7 else ""), r[6]]
            for i, r in enumerate(rows)]
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
# ---- 界面配色（macOS 风格扁平浅色）----
UI_BG = "#f5f5f7"          # 窗口底
UI_CARD = "#ffffff"        # 卡片
UI_LINE = "#e3e6ea"        # 分隔线
UI_INK = "#1d1d1f"         # 主文字
UI_SUB = "#6e6e73"         # 次文字
UI_FILL = "#f4f4f5"        # 次级按钮底
UI_FILL_HOVER = "#e9e9eb"
UI_FILL_PRESS = "#dedfe0"
UI_BLUE = "#409EFF"
UI_GREEN = "#67C23A"
UI_RED = "#F56C6C"


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
            ck = getattr(self, "_cookie_out", "")
            if ck:
                self.send_header("Set-Cookie", ck)
                self._cookie_out = ""
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
            ck = getattr(self, "_cookie_out", "")
            if ck:
                self.send_header("Set-Cookie", ck)
                self._cookie_out = ""
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception:
            pass

    def _send_file(self, body, ctype, filename):
        """下载文件（导出 Excel 用）。"""
        try:
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Disposition", 'attachment; filename="%s"' % filename)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except Exception:
            pass

    # ---------- 登录 / 会话 ----------
    def _cookie_token(self):
        for part in (self.headers.get("Cookie") or "").split(";"):
            p = part.strip()
            if p.startswith("kmsid="):
                return p[6:]
        return ""

    def _token(self, qs):
        return ((qs.get("sid") or [""])[0] or "").strip() or self._cookie_token()

    def _auth(self, qs):
        """返回 {'name','role'} 或 None；带旧访问口令 k 视为管理员（兼容老书签）。"""
        key = (qs.get("k") or [""])[0] if qs else ""
        required = (getattr(self.app, "web_key", "") or "") if getattr(self.app, "require_key", True) else ""
        if required and key == required:
            return {"name": "口令登录", "role": "admin"}
        if auth:
            u = auth.check(self._token(qs))
            if u:
                return u
        return None

    def _redirect(self, loc):
        try:
            self.send_response(302)
            self.send_header("Location", loc)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", "0")
            self.end_headers()
        except Exception:
            pass

    def _set_cookie(self, tok):
        self._cookie_out = (("kmsid=%s; Path=/; Max-Age=%d; SameSite=Lax" % (tok, 30 * 86400))
                            if tok else "kmsid=; Path=/; Max-Age=0; SameSite=Lax")

    def _client_is_local(self):
        """是不是"就坐在电脑前"的请求：直连回环地址，并且没经过 HTTPS 中转。

        中转（km_https.py）会给转发的请求加上 X-Forwarded-For，所以带这个头的一律不算本机，
        否则 9443 上任何人都能被当成"本机用户"去设置管理员。
        """
        try:
            peer = (self.client_address or [""])[0]
        except Exception:
            return False
        try:
            hdrs = {str(k).lower(): (v or "") for k, v in self.headers.items()}
        except Exception:
            hdrs = {}
        if hdrs.get("x-forwarded-for") or hdrs.get("x-real-ip") or hdrs.get("x-forwarded-host"):
            return False
        return peer in ("127.0.0.1", "::1", "::ffff:127.0.0.1", "localhost")

    def _auth_state(self, qs):
        u = self._auth(qs)
        return {"need_setup": bool(auth and auth.need_setup()),
                "local": self._client_is_local(),
                "user": (u or {}).get("name"), "role": (u or {}).get("role"),
                "users": (auth.list_users() if (auth and u and u.get("role") == "admin") else []),
                "open": (u is not None)}

    def do_GET(self):
        app = self.app
        try:
            parsed = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(parsed.query)
            path = parsed.path
            if path in ("/login", "/login.html"):
                return self._send(LOGIN_HTML.encode("utf-8"), "text/html; charset=utf-8")
            if path == "/api/auth/state":
                return self._json(self._auth_state(qs))
            me = self._auth(qs)
            if not me:
                if path.startswith("/api/"):
                    return self._json({"error": "请先登录", "login": True}, 401)
                # 没登录时直接返回登录页（不靠 302，中转/任何客户端都能看到）
                return self._send(LOGIN_HTML.encode("utf-8"), "text/html; charset=utf-8")
            if parsed.path in ("/", "/index.html"):
                return self._send(WEB_INDEX_HTML.encode("utf-8"), "text/html; charset=utf-8")
            if parsed.path in ("/pick", "/pick.html"):
                return self._send(PICK_HTML.encode("utf-8"), "text/html; charset=utf-8")
            if parsed.path in ("/stocktake", "/stocktake.html"):
                return self._send(STOCKTAKE_HTML.encode("utf-8"), "text/html; charset=utf-8")
            if parsed.path in ("/order", "/order.html"):
                return self._send(ORDER_HTML.encode("utf-8"), "text/html; charset=utf-8")
            if parsed.path in ("/stock", "/stock.html"):
                return self._send(STOCK_HTML.encode("utf-8"), "text/html; charset=utf-8")
            if parsed.path == "/api/status":
                return self._json(app.web_status())
            if parsed.path == "/api/index":
                return self._json(app.web_index_payload())
            if parsed.path == "/api/pick/list":
                try:
                    pdays = int((qs.get("days") or ["3"])[0] or 3)
                except Exception:
                    pdays = 3
                return self._json(app.web_pick_list((qs.get("batch") or [""])[0], pdays,
                                                    (qs.get("refresh") or ["0"])[0] in ("1", "true")))
            if parsed.path == "/api/pick/current":
                return self._json(app.web_pick_current())
            if parsed.path == "/api/pick/mark":
                try:
                    gidx = int((qs.get("g") or ["-1"])[0])
                except Exception:
                    gidx = -1
                raw_line = (qs.get("line") or [""])[0]
                try:
                    lidx = int(raw_line) if raw_line != "" else None
                except Exception:
                    lidx = None
                return self._json(app.web_pick_mark((qs.get("batch") or [""])[0], gidx,
                                                    (qs.get("state") or ["pending"])[0], lidx))
            if parsed.path == "/api/pick/end":
                return self._json(app.web_pick_end((qs.get("batch") or [""])[0]))
            if parsed.path == "/api/lookup":
                code = (qs.get("code") or [""])[0].strip()
                rel = (qs.get("rel") or ["any"])[0] or "any"
                try:
                    n = int((qs.get("n") or ["0"])[0] or 0)
                except Exception:
                    n = 0
                if not code:
                    return self._json({"error": "缺少 code"}, 400)
                out = app.web_lookup(code, rel, n)
                try:                       # 手机/网页扫一次就写进电脑版扫码记录（带账号）
                    app.record_web_scan(out, str((me or {}).get("name") or ""))
                except Exception:
                    pass
                return self._json(out)
            if parsed.path == "/api/order":
                return self._json(app.web_order((qs.get("no") or [""])[0]))
            if parsed.path == "/api/order/img":
                ctype, data = app.web_order_image((qs.get("u") or [""])[0])
                if not data:
                    return self._json({"error": "图片地址不允许或取不到"}, 400)
                return self._send(data, ctype)
            if parsed.path == "/api/stock":
                return self._json(app.web_stock((qs.get("kw") or [""])[0],
                                                (qs.get("only") or ["all"])[0],
                                                (qs.get("sort") or ["free"])[0]))
            if parsed.path == "/api/stock/export":
                data = app.stock_xlsx((qs.get("kw") or [""])[0],
                                      (qs.get("only") or ["all"])[0],
                                      (qs.get("sort") or ["free"])[0])
                if not data:
                    return self._json({"error": "没有可导出的数据"}, 400)
                return self._send_file(data,
                                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                       "xianhuo_kefa.xlsx")
            return self._json({"error": "not found"}, 404)
        except Exception as e:
            return self._json({"error": str(e)[:200]}, 500)


    def do_POST(self):
        try:
            parsed = urllib.parse.urlparse(self.path)
            qs = urllib.parse.parse_qs(parsed.query)
            n = int(self.headers.get("Content-Length") or 0)
            raw = self.rfile.read(n) if n else b""
            try:
                body = json.loads(raw.decode("utf-8") or "{}")
            except Exception:
                body = {k: v[0] for k, v in urllib.parse.parse_qs(raw.decode("utf-8", "replace")).items()}
            path = parsed.path
            dev = (self.headers.get("User-Agent") or "")[:300]   # 给设备名识别留够长度（浏览器名在 UA 后段）
            if path == "/api/auth/setup":
                if not auth:
                    return self._json({"error": "账号模块不可用"}, 400)
                local = self._client_is_local()
                if not local:
                    # 远端（手机 / 外网）一律不许设置或重置管理员，否则谁先打开谁就能当管理员
                    if auth.need_setup():
                        return self._json({"error": "首次设置只能在这台电脑上做：请在本机打开 http://127.0.0.1:8790/login"}, 403)
                    return self._json({"error": "已经设置过管理员了，请直接登录"}, 403)
                name = str(body.get("name") or "").strip()
                us = auth.users()
                if name in us:
                    if (us[name].get("role") or "user") != "admin":
                        return self._json({"error": "本机设置只能重置管理员账号的密码"}, 403)
                    err = auth.set_password(name, body.get("pw"), 0)
                else:
                    err = auth.add_user(name, body.get("pw"), "admin")
                if err:
                    return self._json({"error": err}, 400)
                tok, err = auth.login(name, body.get("pw"), dev, body.get("dev_id"), body.get("model"))
                if err:
                    return self._json({"error": err}, 400)
                self._set_cookie(tok)
                return self._json({"ok": True, "token": tok, "name": name, "role": "admin"})
            if path == "/api/auth/login":
                if not auth:
                    return self._json({"error": "账号模块不可用"}, 400)
                tok, err = auth.login(body.get("name"), body.get("pw"), dev, body.get("dev_id"), body.get("model"))
                if err:
                    return self._json({"error": err}, 400)
                self._set_cookie(tok)
                role = (auth.users().get(str(body.get("name")).strip()) or {}).get("role") or "user"
                return self._json({"ok": True, "token": tok, "name": body.get("name"), "role": role})
            me = self._auth(qs)
            if not me:
                return self._json({"error": "请先登录", "login": True}, 401)
            if path == "/api/auth/logout":
                if auth:
                    auth.logout(self._token(qs))
                self._set_cookie("")
                return self._json({"ok": True})
            if path == "/api/stock/sent":
                # 现货可发：标记/撤回「已发」（存在程序里，所有账号共用；拉新数据后自动清空）
                app = self.app
                if body.get("clear"):
                    app.clear_sent()
                    return self._json({"ok": True, "sent": 0})
                left = app.mark_sent(body.get("codes") or body.get("code") or [],
                                     undo=bool(body.get("undo")))
                return self._json({"ok": True, "sent": len(left)})
            if path == "/api/stock/canprint":
                # 网页现货可发点「可发」并输入数量 → 写一条扫码日志（可打单数量 = 输入值）
                code = str(body.get("code") or "").strip()
                try:
                    qty = int(body.get("qty"))
                except Exception:
                    return self._json({"error": "数量必须是整数"}, 400)
                if not code:
                    return self._json({"error": "缺少编码"}, 400)
                insert_canprint(code, qty, who=str((me or {}).get("name") or ""),
                                bins=str(body.get("bins") or ""),
                                pending_qty=body.get("pending") or 0,
                                shelf_qty=body.get("shelf") or 0)
                return self._json({"ok": True, "code": code, "qty": qty})
            if path == "/api/stock/adjust":
                # 改库存（盘点接口，按货位）。必须带 confirm 二次确认，改完写操作日志。
                app = self.app
                if not body.get("confirm"):
                    return self._json({"error": "缺少二次确认"}, 400)
                out = app.stock_adjust(body.get("code"), body.get("bin"), body.get("qty"),
                                       who=str((me or {}).get("name") or ""))
                return self._json(out, 200 if out.get("ok") else 400)
            if path == "/api/stock/adjust/log":
                return self._json({"list": self.app.adjust_logs(int(body.get("limit") or 30))})
            if path == "/api/users":
                if not auth:
                    return self._json({"error": "账号模块不可用"}, 400)
                if me.get("role") != "admin":
                    return self._json({"error": "只有管理员能管理账号"}, 403)
                act = str(body.get("action") or "list")
                err = ""
                if act == "add":
                    err = auth.add_user(body.get("name"), body.get("pw"), body.get("role") or "user")
                elif act == "del":
                    err = auth.del_user(body.get("name"))
                elif act == "passwd":
                    # 改自己的密码：不踢自己、不锁自己；改别人的：旧会话失效 + 那台设备 10 分钟不能再登录
                    mine = (str(body.get("name") or "").strip() == str(me.get("name") or ""))
                    err = auth.set_password(body.get("name"), body.get("pw"), 0 if mine else 10)
                elif act == "kick":
                    err = auth.kick(body.get("name"))
                if err:
                    return self._json({"error": err}, 400)
                return self._json({"ok": True, "users": auth.list_users()})
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


# ============================ 全局扫码监听（程序不在前台也能扫） ============================
class ScanKeyHook:
    """系统级键盘监听：用 WH_KEYBOARD_LL 抓「扫码枪」的输入。

    · 只认「像扫码枪」的输入：字符间隔 < 80ms、长度 ≥ 3、以回车结束；
    · 不拦截、不修改任何按键（照样传给当前窗口），也不保存其它任何输入；
    · 支持中文/Unicode（扫码枪以 VK_PACKET 注字符时直接取该字符）。
    """

    VK_RETURN = 0x0D
    VK_SHIFT = (0x10, 0xA0, 0xA1)
    VK_CAPITAL = 0x14
    VK_PACKET = 0xE7
    GAP = 0.08          # 相邻字符最大间隔（秒）—— 人手打字达不到
    MIN_LEN = 3
    MAX_SEC = 1.2       # 整串最长耗时
    MAX_BUF = 96

    def __init__(self, on_code):
        self.on_code = on_code
        self.ok = False
        self.err = ""
        self._buf = ""
        self._t0 = 0.0
        self._last = 0.0
        self._shift = False
        self._caps = False
        self._stop = threading.Event()
        self._tid = 0
        self._thread = None
        self._proc = None

    def alive(self):
        return bool(self._thread and self._thread.is_alive())

    def start(self):
        if self.alive():
            return True
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True, name="km-scan-hook")
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()
        try:
            if self._tid:
                ctypes.windll.user32.PostThreadMessageW(self._tid, 0x0012, 0, 0)   # WM_QUIT
        except Exception:
            pass

    def _run(self):
        import ctypes
        from ctypes import wintypes
        try:
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

            class KBDLLHOOKSTRUCT(ctypes.Structure):
                _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                            ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                            ("dwExtraInfo", ctypes.c_void_p)]

            LRESULT = ctypes.c_ssize_t
            HOOKPROC = ctypes.WINFUNCTYPE(LRESULT, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)

            # 必须声明参数/返回类型：否则 64 位下句柄会被当成 32 位整数截断（曾报 err=126）
            user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOKPROC, wintypes.HANDLE, wintypes.DWORD]
            user32.SetWindowsHookExW.restype = wintypes.HANDLE
            user32.UnhookWindowsHookEx.argtypes = [wintypes.HANDLE]
            user32.CallNextHookEx.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
            user32.CallNextHookEx.restype = LRESULT
            user32.GetMessageW.argtypes = [ctypes.POINTER(wintypes.MSG), wintypes.HWND, wintypes.UINT, wintypes.UINT]
            user32.GetMessageW.restype = ctypes.c_int
            user32.TranslateMessage.argtypes = [ctypes.POINTER(wintypes.MSG)]
            user32.DispatchMessageW.argtypes = [ctypes.POINTER(wintypes.MSG)]
            user32.ToUnicodeEx.restype = ctypes.c_int
            user32.GetKeyboardLayout.restype = wintypes.HANDLE
            user32.GetForegroundWindow.restype = wintypes.HWND
            kernel32.GetModuleHandleW.restype = wintypes.HANDLE
            kernel32.GetCurrentThreadId.restype = wintypes.DWORD
            user32.PostThreadMessageW.argtypes = [wintypes.DWORD, wintypes.UINT,
                                                  wintypes.WPARAM, wintypes.LPARAM]

            def translate(vk, scan):
                st = (ctypes.c_ubyte * 256)()
                if self._shift:
                    st[0x10] = 0x80
                if self._caps:
                    st[0x14] = 0x01
                buf = ctypes.create_unicode_buffer(8)
                n = user32.ToUnicodeEx(vk, scan, st, buf, 8, 0, user32.GetKeyboardLayout(0))
                return buf.value if n > 0 else ""

            def proc(nCode, wParam, lParam):
                try:
                    if nCode == 0:
                        kb = ctypes.cast(lParam, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                        vk = kb.vkCode
                        if wParam in (0x0100, 0x0104):          # KEYDOWN / SYSKEYDOWN
                            if vk in self.VK_SHIFT:
                                self._shift = True
                            elif vk == self.VK_CAPITAL:
                                self._caps = not self._caps
                            elif vk == self.VK_RETURN:
                                code = self._buf
                                fast = (len(code) >= self.MIN_LEN) and \
                                       ((time.time() - self._t0) <= self.MAX_SEC)
                                self._buf, self._t0, self._last = "", 0.0, 0.0
                                if fast:
                                    try:
                                        self.on_code(code)
                                    except Exception:
                                        pass
                            else:
                                ch = (chr(kb.scanCode & 0xFFFF) if vk == self.VK_PACKET
                                      else translate(vk, kb.scanCode))
                                if ch and ch.isprintable():
                                    now = time.time()
                                    if self._buf and (now - self._last) > self.GAP:
                                        self._buf, self._t0 = "", 0.0
                                    if not self._t0:
                                        self._t0 = now
                                    self._buf = (self._buf + ch)[-self.MAX_BUF:]
                                    self._last = now
                        elif wParam in (0x0101, 0x0105):        # KEYUP / SYSKEYUP
                            if vk in self.VK_SHIFT:
                                self._shift = False
                except Exception:
                    pass
                return user32.CallNextHookEx(None, nCode, wParam, lParam)

            self._proc = HOOKPROC(proc)          # 必须保引用，否则回调会被回收
            self._tid = kernel32.GetCurrentThreadId()
            hook = user32.SetWindowsHookExW(13, self._proc, kernel32.GetModuleHandleW(None), 0)
            if not hook:
                self._err1 = ctypes.get_last_error()
                hook = user32.SetWindowsHookExW(13, self._proc, None, 0)
            if not hook:
                self.err = "SetWindowsHookEx 失败 err=%s/%s" % (getattr(self, "_err1", ""),
                                                              ctypes.get_last_error())
                return
            self.ok = True
            msg = wintypes.MSG()
            while not self._stop.is_set():
                r = user32.GetMessageW(ctypes.byref(msg), None, 0, 0)
                if r in (0, -1):
                    break
                user32.TranslateMessage(ctypes.byref(msg))
                user32.DispatchMessageW(ctypes.byref(msg))
            user32.UnhookWindowsHookEx(hook)
            self.ok = False
        except Exception as e:
            self.err = str(e)[:120]
            self.ok = False


# ============================ 批次查询（按打印批次号反查） ============================
# 快麦开放平台没有「打印批次」接口，但订单操作日志（erp.trade.trace.list）里
# 「打印快递单」动作的 content 自带：打印批次号 / 打印序号 / 第几次打印 / 快递单号。
_B_RE_SEQ = re.compile(r"打印序号[：:]\s*(\d+)")
_B_RE_TIMES = re.compile(r"第(\d+)次打印")
_B_RE_EXP = re.compile(r"快递单号[：:]\s*([A-Za-z0-9]+)")
_B_RE_CO = re.compile(r"快递公司[：:]\s*([^；;]+)")


def fetch_print_batch(batch, days=3, progress=None, max_pages=30):
    """按打印批次号反查：先查订单操作日志拿 sid，再批量取订单明细（商品编码/件数）。

    返回 (orders, err)。orders = [{sid, seq, printed, express, carrier, operator,
                                 items: [(编码, 件数)], sys_status, short_id}]，按打印序号排序。
    """
    batch = str(batch or "").strip()
    if not batch:
        return [], "请输入打印批次号"
    end = datetime.now()
    start = end - timedelta(days=max(1, int(days or 3)))
    to_ms = lambda d: str(int(d.timestamp() * 1000))
    seen = {}
    page = 1
    while page <= max_pages:
        biz = {"action": "打印快递单", "content": batch,
               "operateTimeStart": to_ms(start), "operateTimeEnd": to_ms(end),
               "pageNo": str(page), "pageSize": "200"}
        try:
            res = api_call_authed("erp.trade.trace.list", biz, timeout=40)
        except Exception as e:
            if seen:
                break
            return [], "查询打印记录失败：%s" % str(e)[:120]
        if not isinstance(res, dict) or not res.get("success"):
            if seen:
                break
            code = res.get("code") if isinstance(res, dict) else "?"
            msg = res.get("msg") if isinstance(res, dict) else str(res)[:80]
            return [], "查询打印记录失败 code=%s msg=%s" % (code, msg)
        lst = res.get("list") or []
        for x in lst:
            content = str(x.get("content") or "")
            if batch not in content:
                continue
            sid = str(x.get("sid") or "")
            if not sid:
                continue
            m_seq, m_t, m_e, m_c = (_B_RE_SEQ.search(content), _B_RE_TIMES.search(content),
                                    _B_RE_EXP.search(content), _B_RE_CO.search(content))
            cur = {"sid": sid,
                   "seq": int(m_seq.group(1)) if m_seq else 0,
                   "printed": int(m_t.group(1)) if m_t else 1,
                   "express": m_e.group(1) if m_e else "",
                   "carrier": m_c.group(1).strip() if m_c else "",
                   "operator": str(x.get("operator") or ""),
                   "op_time": x.get("operateTime")}
            old = seen.get(sid)
            if old is None or (cur["printed"] or 0) >= (old["printed"] or 0):
                seen[sid] = cur
        if progress:
            progress(len(seen), page, len(lst))
        if len(lst) < 200:
            break
        page += 1
    if not seen:
        return [], ("最近 %s 天没找到批次 %s 的打印记录；如果更早打印的，把天数改大再试"
                    % (int(days or 3), batch))
    orders = sorted(seen.values(), key=lambda r: (r.get("seq") or 0))
    # 批量取订单明细（实测：sid 逗号拼接、每次 50 个可用）
    sids = [o["sid"] for o in orders]
    detail = {}
    for i in range(0, len(sids), 50):
        chunk = sids[i:i + 50]
        try:
            res = api_call_authed("erp.trade.list.query",
                                  {"sid": ",".join(chunk), "pageSize": "100"}, timeout=60)
        except Exception:
            continue
        if isinstance(res, dict) and res.get("success"):
            for t in (res.get("list") or []):
                detail[str(t.get("sid"))] = t
        if progress:
            progress(len(seen), i // 50 + 1, len(chunk))
    picked = []
    for o in orders:
        t = detail.get(o["sid"]) or {}
        items, ignored = [], 0
        for it in (t.get("orders") or []):
            if _is_excluded_item(it):      # 1166 / 买家秀 / 圆虹包 等占位、平台赠品：不算、不拣
                ignored += 1
                continue
            code = item_code(it)
            if code:
                items.append((code, item_num(it)))
        o["items"] = items
        o["ignored"] = ignored
        o["sys_status"] = t.get("sysStatus") or ""
        o["urgent"] = bool(t.get("isUrgent"))
        o["short_id"] = t.get("shortId") or ""
        o["found"] = bool(t)
        if items:                          # 只有赠品/占位商品的单，不进拣货清单
            picked.append(o)
    return picked, ""


# ============================ 读导出的批次文件（CSV / xlsx） ============================
def _pick_col(headers, keys):
    for i, h in enumerate(headers):
        t = str(h or "").strip().lower().replace(" ", "")
        for k in keys:
            if k in t:
                return i
    return -1


def read_table_file(path):
    """读 CSV / xlsx，返回 (headers, rows)。xlsx 直接解 zip+XML，不依赖第三方库。"""
    lower = str(path).lower()
    if lower.endswith(".xlsx"):
        import zipfile
        import xml.etree.ElementTree as ET
        NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
        z = zipfile.ZipFile(path)
        names = z.namelist()
        shared = []
        if "xl/sharedStrings.xml" in names:
            root = ET.fromstring(z.read("xl/sharedStrings.xml"))
            for si in root.findall(NS + "si"):
                shared.append("".join(t.text or "" for t in si.iter(NS + "t")))
        sheet = sorted(n for n in names if n.startswith("xl/worksheets/sheet"))[0]
        root = ET.fromstring(z.read(sheet))
        table = []
        for row in root.iter(NS + "row"):
            cells = {}
            for c in row.findall(NS + "c"):
                ref = c.get("r") or ""
                col = "".join(ch for ch in ref if ch.isalpha())
                t = c.get("t")
                v = c.find(NS + "v")
                isel = c.find(NS + "is")
                if t == "s" and v is not None and v.text is not None:
                    idx = int(v.text)
                    txt = shared[idx] if 0 <= idx < len(shared) else ""
                elif isel is not None:
                    txt = "".join(x.text or "" for x in isel.iter(NS + "t"))
                else:
                    txt = (v.text if v is not None else "") or ""
                cells[col] = txt
            table.append(cells)
        if not table:
            return [], []
        cols = sorted({c for r in table for c in r}, key=lambda s: (len(s), s))
        headers = [table[0].get(c, "") for c in cols]
        rows = [[r.get(c, "") for c in cols] for r in table[1:]]
        return headers, rows
    # CSV / 文本
    import csv
    import io
    for enc in ("utf-8-sig", "gbk", "utf-8"):
        try:
            with io.open(path, encoding=enc, newline="") as f:
                table = list(csv.reader(f))
            break
        except Exception:
            table = None
    if not table:
        raise RuntimeError("读不了这个文件（编码/格式不支持）")
    table = [r for r in table if any(str(x).strip() for x in r)]
    if not table:
        return [], []
    return table[0], table[1:]


# ============================ 界面 ============================
class ScanApp:
    GREEN = "#1e9e4a"
    GREEN_BG = "#d7f5e0"
    RED = "#d70015"
    RED_BG = "#ffe5e5"
    GREY = "#555555"
    GREY_BG = "#f2f2f7"

    def __init__(self, root):
        self.root = root
        self.root.title("快麦扫码查询")
        self.root.geometry("1080x760")
        self.root.minsize(920, 620)
        try:
            self.root.configure(bg=UI_BG)
        except Exception:
            pass

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
        self.shelf_at_ts = 0            # 货位在架数最后刷新时间（批次拣货要看新鲜货位）
        self._scan_after = None         # 输入停顿自动提交定时器
        self._scanning = False
        self._hook = None               # 后台扫码监听
        self._last_hook_code, self._last_hook_at = "", 0.0
        self._float = None              # 扫码浮窗
        self._float_after = None
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
        self.shelf_refresh_min = int(settings.get("shelf_refresh_min") or SHELF_REFRESH_MIN)
        self.auto_min_var = tk.StringVar(value=str(self.auto_refresh_min))
        self.full_min_var = tk.StringVar(value=str(self.full_refresh_min))
        self.lock_min_var = tk.StringVar(value=str(self.lock_refresh_min))
        self._key_saved = bool(settings.get("require_key", True))
        self.require_key = self._key_saved
        self.key_on = tk.BooleanVar(value=self.require_key)
        self.hook_on = tk.BooleanVar(value=bool(settings.get("bg_scan_hook", True)))
        # 手动输入不再自动查（与网页一致）：回车/点「查询」才查；只有勾选此项才按输入停顿自动查
        self.autosubmit_on = tk.BooleanVar(value=bool(settings.get("auto_submit", False)))

        self._build_ui()
        init_db()
        self._init_orders_db()
        self.reload_records()
        self._restore_pending_cache()
        self._restore_shelf_cache()
        self._restore_lock_cache()
        self._start_web()          # 数据恢复完再对外服务，避免手机端拿到半成品
        self.root.after(100, self._drain_queue)
        self.root.after(1200, self._first_run_api_hint)    # 新电脑首次装：提示填 API
        self.root.after(1500, self._init_scan_hook)      # 后台扫码监听（最小化也能扫）
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
                "uo": int(e.get("uo", 0) or 0),
                "up": int(e.get("up", 0) or 0),
                "b": "、".join(str(b[0]) for b in (sh.get("bins") or [])[:6]),
                "bl": [[str(b[0]), int(b[1] or 0)] for b in (sh.get("bins") or [])],
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

    # ---------- 手机端拣货 ----------
    def _shelf_lookup(self, code):
        """给拣货组用：返回（货位文本, 在架数）——忽略大小写。"""
        sh, _k = dict_get_ci(self.shelf_map, code)
        sh = sh or {}
        bins = "、".join(b[0] for b in (sh.get("bins") or [])) or "无在架货位"
        return bins, int(sh.get("shelf", 0) or 0)

    def _pick_payload(self, s):
        os_ = s.get("orders") or []
        lines = [l for o in os_ for l in (o.get("lines") or [])]
        done = sum(1 for l in lines if l.get("state") == "done")
        short = sum(1 for l in lines if l.get("state") == "short")
        st = {"pending": 0, "done": 0, "short": 0}
        for o in os_:
            k = order_state(o)
            st[k] = st.get(k, 0) + 1
        return {"batch": s.get("batch"), "created_at": s.get("created_at"),
                "ended_at": s.get("ended_at"), "status": s.get("status"), "days": s.get("days"),
                "orders": os_,
                "progress": {"orders": len(os_), "orders_done": st["done"],
                             "orders_short": st["short"], "orders_pending": st["pending"],
                             "lines": len(lines), "done": done, "short": short,
                             "pending": len(lines) - done - short,
                             "qty": sum(int(l.get("qty") or 0) for l in lines),
                             "qty_done": sum(int(l.get("qty") or 0) for l in lines
                                             if l.get("state") == "done")}}

    def _pick_clean(self, s):
        """续上的旧存档里清掉应排除的商品行（历史遗留的 1166/赠品），其他进度保留。"""
        out, changed = [], False
        for o in (s.get("orders") or []):
            ls = [l for l in (o.get("lines") or []) if not _pick_group_excluded(l.get("code"))]
            if not ls:
                changed = True
                continue
            if len(ls) != len(o.get("lines") or []):
                changed = True
                o = dict(o, lines=ls)
            out.append(o)
        if changed:
            pick_save(s["batch"], out, s.get("status") or "running",
                      s.get("days") or 3, s.get("created_at"))
        return dict(s, orders=out)

    def web_pick_list(self, batch, days=3, refresh=False):
        """开一个拣货会话：已有存档（未结束）就直接续上，否则现拉。"""
        batch = str(batch or "").strip()
        if not batch:
            return {"error": "缺少批次号"}
        saved = pick_get(batch)
        if saved and saved.get("status") == "running" and not refresh:
            pick_end_others(batch)      # 同时只保留一个进行中批次
            return self._pick_payload(self._pick_clean(saved))
        orders, err = fetch_print_batch(batch, days=days)
        if err:
            return {"error": err}
        built = build_pick_orders(orders, self._shelf_lookup)
        pick_save(batch, built, "running", days)
        pick_end_others(batch)          # 开了新批次，旧的自动结束
        return self._pick_payload(pick_get(batch))

    def web_pick_current(self):
        """有未结束的拣货批次就返回（手机页面一打开就能接着拣）。"""
        s = pick_running()
        if not s:
            return {"running": False}
        p = self._pick_payload(self._pick_clean(s))
        return {"running": True, "batch": p["batch"], "created_at": p["created_at"],
                "progress": p["progress"], "orders": p["orders"], "days": p["days"]}

    def web_pick_mark(self, batch, idx, state, line=None):
        """标记：g=第几单（0 起），line=单内第几个商品（不传=整单）。"""
        if state not in ("done", "short", "pending"):
            return {"error": "state 不合法"}
        d = pick_get(batch)
        if not d:
            return {"error": "找不到该批次的拣货记录"}
        os_ = d.get("orders") or []
        if not (0 <= idx < len(os_)):
            return {"error": "序号越界"}
        ls = os_[idx].get("lines") or []
        if line is None:
            targets = list(range(len(ls)))
        elif 0 <= line < len(ls):
            targets = [line]
        else:
            return {"error": "行号越界"}
        for i in targets:
            ls[i]["state"] = state
            ls[i]["marked_at"] = now_gmt8()
        pick_save(d["batch"], os_, d.get("status") or "running", d.get("days") or 3, d.get("created_at"))
        return self._pick_payload(pick_get(batch))

    def web_pick_end(self, batch):
        pick_end(batch)
        return {"ok": True}

    # ---------- 网页端：订单查询（订单号 / 快递单号 → 图文 + 退款状态） ----------
    ORDER_IMG_HOSTS = ("ecombdimg.com", "ecombd.com", "pstatp.com", "ttcdn.com", "byteimg.com",
                       "tbcdn.cn", "alicdn.com", "360buyimg.com", "yangkeduo.com", "pddpic.com",
                       "kwaishop.com", "kuaishou.com", "douyinpic.com")
    OD_STATUS_CN = {"WAIT_SEND_GOODS": "待发货", "WAIT_AUDIT": "待审核", "WAIT_EXPRESS_PRINT": "待打印快递单",
                    "FINISHED_AUDIT": "审核完成", "SELLER_SEND_GOODS": "已发货", "CLOSED": "已关闭",
                    "FINISHED": "交易成功", "TRADE_SUCCESS": "交易成功"}
    OD_UNI_CN = {"SELLER_SEND_GOODS": "已发货", "WAIT_SELLER_SEND_GOODS": "待发货",
                 "TRADE_CLOSED": "交易关闭", "FINISHED": "交易成功"}
    AF_TYPE_CN = {0: "其他", 1: "已发货仅退款", 2: "退货", 3: "补发", 4: "换货", 5: "未发货仅退款",
                  7: "拒收退货", 8: "档口退货", 9: "维修"}
    AF_STATUS_CN = {2: "未解决（处理中）", 9: "已解决（退款完成）", 10: "已作废", 11: "已合并", 12: "解决中"}
    AF_GOOD_CN = {1: "买家未收到货", 2: "买家已收到货", 3: "买家已退货", 4: "卖家已收到退货"}
    EX_CN = {"EX_INSUFFICIENT": "库存不足", "EX_HALT": "已挂起", "EX_REFUND": "退款中",
             "EX_PRESELL": "预售", "EX_ADDRESS": "地址异常", "EX_TIMEOUT": "超时"}
    OD_KEYS = (("tid", "平台单号"), ("sid", "系统单号"), ("outSids", "快递单号"))

    @staticmethod
    def _od_time(v):
        try:
            n = int(v)
        except Exception:
            return str(v or "")[:20]
        if n < 100000000000 or n == 946656000000:
            return ""
        return datetime.fromtimestamp(n / 1000.0).strftime("%Y-%m-%d %H:%M")

    def _wo_json(self, w):
        """一张售后工单 → 页面用的结构（不输出买家姓名/手机）。"""
        t = self._od_time
        kv = [
            ["系统实退金额", ("¥%s" % w.get("refundMoney")) if w.get("refundMoney") is not None else ""],
            ["平台实退金额", ("¥%s" % w.get("rawRefundMoney")) if w.get("rawRefundMoney") is not None else ""],
            ["应退运费", w.get("refundPostFee") or ""],
            ["退款状态", w.get("advanceStatusText") or ""],
            ["货物状态", self.AF_GOOD_CN.get(w.get("goodStatus"), w.get("goodStatus")) or ""],
            ["售后原因", w.get("reason") or w.get("textReason") or ""],
            ["申请时间", t(w.get("applyDate"))],
            ["完成时间", t(w.get("finished"))],
            ["平台售后单号", w.get("platformId") or ""],
            ["退货仓库", w.get("refundWarehouseName") or ""],
            ["退回快递", w.get("refundExpressCompany") or ""],
            ["退回单号", w.get("refundExpressId") or ""],
            ["备注", w.get("remark") or ""],
        ]
        items = []
        for it in (w.get("items") or [])[:6]:
            items.append({"title": it.get("title") or "", "spec": it.get("propertiesName") or "",
                          "code": it.get("outerId") or "", "count": it.get("receivableCount"),
                          "realQty": it.get("itemRealQty"), "price": it.get("price"),
                          "pic": it.get("picPath") or ""})
        return {"id": str(w.get("id") or ""), "status": w.get("status"),
                "statusText": self.AF_STATUS_CN.get(w.get("status"), "工单状态 %s" % w.get("status")),
                "typeText": self.AF_TYPE_CN.get(w.get("afterSaleType"), "售后 %s" % w.get("afterSaleType")),
                "shopName": w.get("shopName") or "", "kv": kv, "items": items}

    def web_order(self, no):
        """输入订单号（19 位平台单号 / 16 位系统单号）或快递单号都能查。

        按单号长度先猜一种，查不到再退其它两种（快递单号长度不固定）。
        """
        no = str(no or "").strip()
        if not no:
            return {"error": "请输入订单号或快递单号"}
        n = len(no)
        if n == 19:
            order_keys = [("tid", "平台单号"), ("outSids", "快递单号"), ("sid", "系统单号")]
        elif n == 16:
            order_keys = [("sid", "系统单号"), ("outSids", "快递单号"), ("tid", "平台单号")]
        else:
            order_keys = [("outSids", "快递单号"), ("tid", "平台单号"), ("sid", "系统单号")]

        order, err, matched = None, "", ""
        for key, label in order_keys:
            try:
                res = api_call_authed("erp.trade.list.query",
                                      {key: no, "pageNo": 1, "pageSize": 20, "useHasNext": "true"}, timeout=40)
                lst = (res or {}).get("list") or []
            except Exception as e:
                err = err or str(e)[:150]
                continue
            if lst:
                order, matched = lst[0], label
                break
        tid = str((order or {}).get("tid") or (no if matched == "平台单号" else ""))
        sid = str((order or {}).get("sid") or (no if matched == "系统单号" else ""))

        after = []
        if tid or sid:
            try:
                q = ({"tid": tid, "pageNo": "1", "pageSize": "20"} if tid
                     else {"sid": sid, "pageNo": "1", "pageSize": "20"})
                a = api_call_authed("erp.aftersale.list.query", q, timeout=40)
                for w in ((a or {}).get("list") or []):
                    if ((tid and str(w.get("tid") or "") == tid)
                            or (sid and str(w.get("sid") or "") == sid)):
                        after.append(self._wo_json(w))
            except Exception as e:
                err = err or str(e)[:150]

        head, items, item_num, line_refund = [], [], "", []
        if order:
            t = self._od_time
            # 加急 / 平台标签 / 异常明细
            tag_names = []
            for tg in (order.get("tradeTags") or []):
                if isinstance(tg, dict) and tg.get("tagName"):
                    tag_names.append(str(tg.get("tagName")))
            exc_codes = []
            for ex in (order.get("exceptions") or []):
                code = str(ex)
                exc_codes.append(self.EX_CN.get(code, code))
            if order.get("isExcep") and not exc_codes:
                exc_codes.append("有异常")
            if order.get("isHalt"):
                exc_codes.append("已挂起")
            memos = order.get("messageMemos")
            memo_txt = []
            if isinstance(memos, list):
                for m in memos:
                    if isinstance(m, dict):
                        s = m.get("memo") or m.get("content") or m.get("remark") or m.get("message")
                        if s:
                            memo_txt.append(str(s))
            head = [
                ["店铺名称", order.get("shopName")],
                ["平台单号", order.get("tid")],
                ["系统单号", order.get("sid")],
                ["付款时间", t(order.get("payTime"))],
                ["发货仓库", order.get("warehouseName")],
                ["快递公司", order.get("expressCompanyName") or order.get("logisticsCompanyName")],
                ["快递模板", order.get("templateName")],
                ["快递单号", order.get("outSid") or "（还没出单）"],
                ["异常状态", "；".join(exc_codes) or "无"],
                ["卖家备注", "；".join(memo_txt[:3])],
                ["系统备注", ""],
                ["加急", "是" if order.get("isUrgent") else "否"],
                ["收货地", " ".join(str(order.get(k) or "") for k in
                                     ("receiverState", "receiverCity", "receiverDistrict", "receiverStreet"))],
                ["查询方式", matched or ""],
            ]
            item_num = order.get("itemNum")
            for it in (order.get("orders") or []):
                code = str(it.get("sysOuterId") or it.get("outerSkuId") or "")
                sh, _k = dict_get_ci(self.shelf_map, code)
                bins = "、".join(str(b[0]) for b in ((sh or {}).get("bins") or []) if b) or "无货位"
                spec = "；".join(x for x in [str(it.get("sysSkuPropertiesName") or ""),
                                             ("(" + str(it.get("sysSkuRemark")) + ")") if it.get("sysSkuRemark") else ""] if x)
                tags = []
                if it.get("stockStatus") == "INSUFFICIENT":
                    tags.append("库存不足")
                if it.get("refundStatus") and it.get("refundStatus") != "NO_REFUND":
                    tags.append(str(it.get("refundStatus")))
                line_refund.append(str(it.get("refundStatus") or ""))
                plat = str(it.get("skuPropertiesName") or "")
                remark = str(it.get("sysSkuRemark") or "")
                amt = it.get("payment")
                if amt in (None, ""):
                    amt = it.get("payAmount")
                items.append({"code": code, "qty": int(it.get("num") or 0),
                              "title": it.get("title") or it.get("sysTitle") or "", "spec": spec,
                              "platSpec": plat, "remark": remark, "amount": amt,
                              "price": it.get("price"), "bin": bins,
                              "pic": it.get("picPath") or it.get("sysPicPath") or "", "tags": tags})
            if order.get("isRefund") not in (0, None, "0"):
                line_refund.append("订单有退款标记")

        line_refund = sorted({x for x in line_refund if x and x != "NO_REFUND"})
        out = {"order": bool(order), "head": head, "items": items, "itemNum": item_num,
               "itemKind": (order or {}).get("itemKindNum"),
               "urgent": bool((order or {}).get("isUrgent")),
               "tags": tag_names if order else [],
               "excs": exc_codes if order else [],
               "statusText": self.OD_STATUS_CN.get((order or {}).get("sysStatus"), (order or {}).get("sysStatus")),
               "uniText": self.OD_UNI_CN.get((order or {}).get("unifiedStatus"), (order or {}).get("unifiedStatus")),
               "lineRefund": line_refund, "after": after, "matched": matched}
        if not order and not after:
            out["error"] = err or "没查到：订单号 / 快递单号是否正确？（归档老单只能从售后查到）"
        return out

    def web_order_image(self, url):
        """订单/售后图片代理：只允许平台图片域名（避免变成本机任意请求转发）。"""
        u = str(url or "").strip()
        try:
            parts = urllib.parse.urlsplit(u)
        except Exception:
            return None, None
        host = (parts.hostname or "").lower()
        if parts.scheme != "https" or not any(host == d or host.endswith("." + d)
                                              for d in self.ORDER_IMG_HOSTS):
            return None, None
        try:
            req = urllib.request.Request(u, headers={"User-Agent": "Mozilla/5.0",
                                                     "Referer": "https://www.douyin.com/"})
            with urllib.request.urlopen(req, timeout=20) as r:
                ctype = (r.headers.get("Content-Type") or "image/jpeg").split(";")[0]
                data = r.read(4 * 1024 * 1024)
        except Exception:
            return None, None
        if len(data) < 100:
            return None, None
        return ctype, data

    # ---------- 网页端：现货可发（在架 / 待发货 / 可发数量） ----------
    def _sent_set(self):
        """「已发」标记（本地先隐藏，避免重复拣）；拉了新数据（数据时间变了）才自动清空。

        注意：重拉过程中 loaded_at 会变空/变化，不能拿它当真·新数据，否则刚打的标记会被误清。
        """
        cur = self.loaded_at
        old = getattr(self, "_sent_ver", None)
        if old is not None and cur and cur != old:
            self._sent = set()          # 真的拉到新数据了 → 清空标记
        if not hasattr(self, "_sent"):
            self._sent = set()
        if cur:
            self._sent_ver = cur
        return self._sent

    def mark_sent(self, codes, undo=False):
        s = self._sent_set()
        if isinstance(codes, str):
            codes = [codes]
        for c in (codes or []):
            c = str(c).strip()
            if not c:
                continue
            if undo:
                s.discard(c)
            else:
                s.add(c)
        return sorted(s)

    def clear_sent(self):
        self._sent_set().clear()
        return []

    # ---------- 改库存（盘点接口，按货位改数量） ----------
    def _adjust_conn(self):
        conn = get_conn()
        conn.execute("""CREATE TABLE IF NOT EXISTS stock_adjust_log(
            id INTEGER PRIMARY KEY AUTOINCREMENT, ts TEXT, who TEXT, code TEXT, bin TEXT,
            old_num TEXT, new_num TEXT, ok INTEGER, msg TEXT, trace TEXT)""")
        conn.commit()
        return conn

    def adjust_logs(self, limit=30):
        try:
            conn = self._adjust_conn()
            rows = conn.execute("SELECT ts,who,code,bin,old_num,new_num,ok,msg FROM stock_adjust_log"
                                " ORDER BY id DESC LIMIT ?", (int(limit),)).fetchall()
            conn.close()
        except Exception:
            return []
        return [{"ts": r[0], "who": r[1], "code": r[2], "bin": r[3], "old": r[4],
                 "new": r[5], "ok": bool(r[6]), "msg": r[7]} for r in rows]

    def stock_bins_of(self, code):
        """该编码本地（程序维护的）各货位数量，用于二次确认与对照。"""
        sh, key = dict_get_ci(self.shelf_map or {}, code)
        if not sh:
            return {"code": code, "found": False, "shelf": 0, "bins": []}
        bins = []
        for b in (sh.get("bins") or []):
            try:
                bins.append([str(b[0]), int(b[1] or 0)])
            except Exception:
                pass
        return {"code": key, "found": True, "shelf": int(sh.get("shelf") or 0),
                "bins": bins, "shelf_at": self.shelf_at}

    def _warehouse_id(self, code):
        """取仓库 id：设置里指定 → 否则按编码问接口（erp.item.warehouse.list.get）。"""
        try:
            wid = str((load_settings() or {}).get("warehouse_id") or "").strip()
        except Exception:
            wid = ""
        if wid:
            return wid, "设置"
        try:
            r = api_call("erp.item.warehouse.list.get",
                         {"skuOuterId": code, "pageNo": "1", "pageSize": "20"},
                         current_session(), timeout=40)
            for sk in (r.get("skus") or []):
                for wh in (sk.get("mainWareHousesStock") or []):
                    if wh.get("id"):
                        return str(wh.get("id")), "接口"
        except Exception as e:
            return "", "错误:%s" % str(e)[:60]
        return "", "未找到"

    def stock_adjust(self, code, bin_code, qty, who=""):
        """把某编码在某货位的数量改成 qty（盘点接口，绝对值）。返回结果字典。"""
        code = str(code or "").strip()
        bin_code = str(bin_code or "").strip()
        try:
            qty = int(qty)
        except Exception:
            return {"ok": False, "msg": "数量必须是整数"}
        if not code or not bin_code:
            return {"ok": False, "msg": "编码和货位都不能为空"}
        if qty < 0:
            return {"ok": False, "msg": "数量不能为负数"}
        before = self.stock_bins_of(code)
        old = None
        for b in (before.get("bins") or []):
            if str(b[0]).upper() == bin_code.upper():
                old = b[1]
        wid, how = self._warehouse_id(code)
        if not wid:
            return {"ok": False, "msg": "拿不到仓库 id（%s），请在 API 设置里填仓库 id" % how,
                    "old": old}
        details = json.dumps([{"outerId": code, "goodsSectionCode": bin_code, "changeNum": str(qty)}],
                             ensure_ascii=False)
        try:
            res = api_call("inventory.sheet.batch.update",
                           {"details": details, "warehouseId": str(wid)},
                           current_session(), timeout=45)
            ok = bool((res or {}).get("success"))
            msg = str((res or {}).get("msg") or "")
            trace = str((res or {}).get("traceId") or "")
        except Exception as e:
            ok, msg, trace = False, str(e)[:200], ""
        try:
            conn = self._adjust_conn()
            conn.execute("INSERT INTO stock_adjust_log(ts,who,code,bin,old_num,new_num,ok,msg,trace)"
                         " VALUES(?,?,?,?,?,?,?,?,?)",
                         (now_gmt8(), who, code, bin_code, str(old if old is not None else "?"),
                          str(qty), 1 if ok else 0, msg[:300], trace))
            conn.commit()
            conn.close()
        except Exception:
            pass
        if ok:
            try:
                self.reload_shelf(background=True)      # 立刻重拉货位库存，界面就能看到新数
            except Exception:
                pass
        return {"ok": ok, "msg": msg, "trace": trace, "old": old, "new": qty,
                "code": code, "bin": bin_code, "warehouseId": wid}

    def stock_rows(self, kw="", only="all", sort="free"):
        """编码级现货可发列表（数据来自本地索引 + 货位在架，不联网）。"""
        items = (self.web_index_payload().get("items") or {})
        try:
            sent = self._sent_set()
        except Exception:
            sent = set()
        kw = str(kw or "").strip().upper()
        rows = []
        for code, v in items.items():
            shelf = int(v.get("s") or 0)
            pieces = int(v.get("p") or 0)
            orders = int(v.get("o") or 0)
            ones = int(v.get("n") or 0)
            uo = int(v.get("uo") or 0)
            up = int(v.get("up") or 0)
            if kw and kw not in str(code).upper():
                continue
            if _pick_group_excluded(code):        # 1166 / 买家秀 / 圆虹包 等占位、补偿商品：不显示
                continue
            multi_pieces = max(0, pieces - ones)   # 多件单需要的件数（一单一件每单恰好 1 件）
            # 可发 = 能发出去的件数：订单要的和库存取小的，再扣掉留给多件单的部分
            # 等价于 min(在架 − 多件件数, 一单一件件数)
            free = min(shelf, pieces) - multi_pieces
            if only == "free" and free <= 0:
                continue
            if only == "short" and free >= 0:
                continue
            if only == "orders" and pieces <= 0:
                continue
            if only == "urgent" and up <= 0 and uo <= 0:
                continue
            prio = 1 if ((uo > 0 or up > 0) and free > 0 and shelf > 0) else 0   # 加急且有货可发
            if only == "urg_free" and not prio:
                continue
            rows.append({"c": str(code), "s": shelf, "p": pieces, "o": orders,
                         "n": ones, "m": max(0, orders - ones), "mp": multi_pieces,
                         "uo": uo, "up": up, "p1": prio,
                         "sent": 1 if str(code) in sent else 0,
                         "b": str(v.get("b") or ""),
                         "bl": v.get("bl") or [],
                         "f": free, "l": int(v.get("l") or 0)})
        key = {"shelf": lambda r: (-r["s"], r["c"]),
               "pieces": lambda r: (-r["p"], r["c"]),
               "code": lambda r: r["c"],
               "urgent": lambda r: (-r["up"], -r["uo"], r["c"]),
               "free": lambda r: (-r["f"], r["c"]),
               "urg_free": lambda r: (-r["p1"], -r["f"], r["c"])}.get(
                   sort, lambda r: (-r["p1"], -r["f"], r["c"]))
        rows.sort(key=key)
        return rows

    def web_stock(self, kw="", only="all", sort="free"):
        rows = self.stock_rows(kw, only, sort)
        return {"total": len(rows), "rows": rows,
                "totals": {"shelf": sum(r["s"] for r in rows),
                           "pieces": sum(r["p"] for r in rows),
                           "ones": sum(r["n"] for r in rows),
                           "multi": sum(r["mp"] for r in rows),
                           "uo": sum(r["uo"] for r in rows),
                           "up": sum(r["up"] for r in rows),
                           "prio": sum(r["p1"] for r in rows),
                           "sent": sum(r["sent"] for r in rows),
                           "free": sum(r["f"] for r in rows)},
                "loaded_at": self.loaded_at, "shelf_at": self.shelf_at,
                "codes": len((self.web_index_payload().get("items") or {}))}

    def stock_xlsx(self, kw="", only="all", sort="free"):
        """导出 Excel：编码 / 一单一件订单数 / 一单多件订单数 / 多件件数 / 待发货件数 / 在架数 / 可发数量。"""
        rows = self.stock_rows(kw, only, sort)
        headers = ["编码", "货位", "一单一件订单数", "一单多件订单数", "多件件数", "加急订单数", "加急件数",
                   "待发货件数", "在架数", "可发数量", "加急且有货"]
        data = [[r["c"], r.get("b", ""), r["n"], r["m"], r["mp"], r["uo"], r["up"],
                 r["p"], r["s"], r["f"], ("是" if r["p1"] else "")] for r in rows]
        if not data:
            return b""
        path = os.path.join(os.environ.get("TEMP", "."),
                            "现货可发_%s.xlsx" % datetime.now().strftime("%Y%m%d_%H%M%S"))
        write_xlsx(path, headers, data)
        try:
            with open(path, "rb") as fp:
                out = fp.read()
        finally:
            try:
                os.remove(path)
            except Exception:
                pass
        return out

    def record_web_scan(self, out, who=""):
        """把手机/网页的扫码写进扫码记录（和电脑版同一张表，带账号）。"""
        try:
            if not isinstance(out, dict):
                return
            if out.get("series"):
                items = out.get("items") or []
                code = "%s（系列 %d 个）" % (out.get("code") or "", len(items))
                pend = sum(int(i.get("qty", 0) or 0) for i in items)
                shl = sum(int(i.get("shelf", 0) or 0) for i in items)
                orders = len(items)
                light = "绿" if shl >= pend else "红"
            else:
                code = str(out.get("code") or "")
                pend = int(out.get("qty") or out.get("pending") or out.get("pieces") or 0)
                shl = int(out.get("shelf") or 0)
                orders = int(out.get("orders") or 0)
                light = "绿" if (shl >= pend and (pend or orders)) else "红"
            if not code:
                return
            insert_scan(code, pend, shl, orders, light, who=who)
        except Exception:
            pass

    def web_lookup(self, code, rel, n):
        idx, _stat = self._web_index(rel, n)
        keys, is_series = series_matches(idx, code)
        if is_series:
            items = []
            for k in keys[:150]:
                e, _c = dict_get_ci(idx, k)
                e = e or {}
                sh, _k2 = dict_get_ci(self.shelf_map, k)
                sh = sh or {}
                lk, _k3 = dict_get_ci(self.lock_map, k)
                lk = lk or {}
                items.append({"code": k,
                              "bins": "、".join(b[0] for b in (sh.get("bins") or [])) or "无货位",
                              "shelf": int(sh.get("shelf", 0) or 0),
                              "qty": int(e.get("qty", 0) or 0),
                              "orders": int(e.get("orders", 0) or 0),
                              "lock": int((lk or {}).get("lock", 0) or 0)})
            return {"series": True, "code": code, "items": items, "total": len(keys),
                    "shelf_at": self.shelf_at}
        e, canon = dict_get_ci(idx, code)          # 编码不分大小写
        e = e or {}
        sh, _k = dict_get_ci(self.shelf_map, canon)
        lk, _k2 = dict_get_ci(self.lock_map, canon)
        sh = sh or {}
        lk = lk or {}
        return {
            "code": canon,
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
    def _setup_style(self):
        """macOS 风格扁平主题（clam 起底 + 自定义样式）。"""
        st = ttk.Style()
        try:
            st.theme_use("clam")
        except Exception:
            pass
        f = ("Microsoft YaHei UI", 10)
        fb = ("Microsoft YaHei UI", 10, "bold")
        st.configure(".", font=f, background=UI_BG, foreground=UI_INK)
        st.configure("TFrame", background=UI_BG)
        st.configure("Card.TFrame", background=UI_CARD)
        st.configure("TLabel", background=UI_BG, foreground=UI_INK)
        st.configure("Muted.TLabel", background=UI_BG, foreground=UI_SUB)
        st.configure("Title.TLabel", background=UI_BG, foreground=UI_INK,
                     font=("Microsoft YaHei UI", 16, "bold"))
        st.configure("TButton", padding=(10, 7), font=f, borderwidth=0, relief="flat",
                     background=UI_FILL, foreground=UI_INK, focusthickness=0)
        st.map("TButton", background=[("pressed", UI_FILL_PRESS), ("active", UI_FILL_HOVER)],
               foreground=[("disabled", "#b0b3b8")])
        st.configure("Accent.TButton", background=UI_BLUE, foreground="#ffffff", font=fb)
        st.map("Accent.TButton", background=[("pressed", "#0060d0"), ("active", "#1a88ff")])
        st.configure("TLabelframe", background=UI_BG, bordercolor=UI_LINE, relief="solid",
                     borderwidth=1, padding=8)
        st.configure("TLabelframe.Label", background=UI_BG, foreground=UI_SUB, font=fb)
        st.configure("TCheckbutton", background=UI_BG, foreground=UI_INK, font=f, focusthickness=0)
        st.map("TCheckbutton", background=[("active", UI_BG)])
        st.configure("Treeview", background=UI_CARD, fieldbackground=UI_CARD, foreground=UI_INK,
                     rowheight=27, font=f, borderwidth=0)
        st.configure("Treeview.Heading", background="#f0f1f4", foreground=UI_SUB, font=fb,
                     relief="flat", padding=6)
        st.map("Treeview", background=[("selected", "#d6e7ff")], foreground=[("selected", UI_INK)])
        st.configure("TEntry", fieldbackground="#ffffff", bordercolor=UI_LINE, padding=6)
        st.map("TEntry", bordercolor=[("focus", UI_BLUE)])
        st.configure("TCombobox", fieldbackground="#ffffff", padding=4)
        st.configure("TSpinbox", fieldbackground="#ffffff", padding=4)
        st.configure("TProgressbar", background=UI_BLUE, troughcolor=UI_FILL, borderwidth=0)

    def _build_ui(self):
        self._setup_style()
        # 外层套一层可滚动区域：窗口右侧竖滚动条；默认看到的区域里就是扫码记录，
        # 往下滑才看到「操作」「刷新周期」（放到最下面）。
        wrap = ttk.Frame(self.root)
        wrap.pack(fill=tk.BOTH, expand=True)
        _vsb = ttk.Scrollbar(wrap, orient="vertical")
        _vsb.pack(side=tk.RIGHT, fill=tk.Y)
        _canvas = tk.Canvas(wrap, highlightthickness=0, yscrollcommand=_vsb.set)
        _canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        _vsb.configure(command=_canvas.yview)
        self._main_canvas = _canvas
        main = ttk.Frame(_canvas, padding=12)
        _mw = _canvas.create_window((0, 0), window=main, anchor="nw")

        def _on_main_cfg(_e=None):
            try:
                _canvas.configure(scrollregion=_canvas.bbox("all"))
            except Exception:
                pass

        def _on_canvas_cfg(e):
            try:
                _canvas.itemconfigure(_mw, width=e.width)
            except Exception:
                pass

        main.bind("<Configure>", _on_main_cfg)
        _canvas.bind("<Configure>", _on_canvas_cfg)

        def _on_wheel(event):
            try:
                over = self.root.winfo_containing(event.x_root, event.y_root)
                step = int(-1 * (event.delta / 120))
                if over is not None and str(over).startswith(str(getattr(self, "tree", None))):
                    self.tree.yview_scroll(step, "units")      # 滚轮压在记录表上 → 滚表格
                    return "break"
                _canvas.yview_scroll(step, "units")              # 否则滚动整页
            except Exception:
                pass

        _canvas.bind_all("<MouseWheel>", _on_wheel)
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

        # 结果面板：第一行=编码（黑色加粗），下面三行=一单一件/一单多件/货位
        self.result = tk.Label(
            main, text="扫码后显示编码",
            font=("Microsoft YaHei", 16, "bold"),
            bg=self.GREY_BG, fg="#000000", height=1, anchor="center",
        )
        self.result.grid(row=1, column=0, sticky="ew", pady=4)
        det = ttk.Frame(main)
        det.grid(row=2, column=0, sticky="ew")
        self.result_detail = tk.Label(det, text="", font=("Microsoft YaHei", 12), fg=UI_INK,
                                      bg=UI_BG, justify="left", anchor="w")
        self.result_detail.pack(anchor="w")
        self.warn_label = tk.Label(det, text="", font=("Microsoft YaHei", 18, "bold"),
                                   fg=self.RED, bg=UI_BG)
        self.warn_label.pack(anchor="w", pady=(4, 0))

        # 商品数量筛选
        flt = ttk.LabelFrame(main, text="商品数量筛选（按订单商品件数加载待发货订单）")
        flt.grid(row=4, column=0, sticky="ew", pady=8)
        ttk.Label(flt, text="订单商品数量").grid(row=0, column=0, padx=6, pady=6)
        ttk.Combobox(flt, textvariable=self.filter_relation, values=FILTER_OPTIONS,
                     width=6, state="readonly").grid(row=0, column=1, padx=4)
        ttk.Entry(flt, textvariable=self.filter_n, width=6).grid(row=0, column=2, padx=4)
        ttk.Label(flt, text="件").grid(row=0, column=3)
        ttk.Button(flt, text="按条件筛选(本地)", command=self.apply_filter).grid(row=0, column=4, padx=10)

        # 操作按钮（网格排布：窄窗口/小屏也不会被切掉）
        ops = ttk.LabelFrame(main, text="操作")
        ops.grid(row=6, column=0, sticky="ew", pady=6)
        for c in range(5):
            ops.columnconfigure(c, weight=1)
        for i, (txt, cmd, sty) in enumerate((
                ("现货可发", self.on_stock_dialog, "Accent.TButton"),
                ("增量刷新", lambda: self.sync_pending(background=True), "TButton"),
                ("全量重拉", lambda: self.full_reload(background=True), "TButton"),
                ("刷新货位库存", lambda: self.reload_shelf(background=True), "TButton"),
                ("刷新锁定数", lambda: self.reload_lock(background=True), "TButton"),
                ("导出扫码日志 Excel", self.on_export, "TButton"),
                ("清空日志", self.on_clear_logs, "TButton"),
                ("API 设置", self.on_api_settings, "TButton"))):
            ttk.Button(ops, text=txt, command=cmd, style=sty).grid(
                row=i // 5, column=i % 5, sticky="ew", padx=5, pady=5)
        chk = ttk.Frame(ops)
        chk.grid(row=3, column=0, columnspan=5, sticky="w", padx=5, pady=(2, 4))
        ttk.Checkbutton(chk, text="后台扫码监听（最小化也能扫）", variable=self.hook_on,
                        command=self.on_hook_toggle).pack(side=tk.LEFT, padx=(0, 14))
        ttk.Checkbutton(chk, text="不回车的扫码枪：停顿时自动查", variable=self.autosubmit_on,
                        command=self.on_autosubmit_toggle).pack(side=tk.LEFT)

        # 刷新周期
        itv = ttk.LabelFrame(main, text="刷新周期（分钟）")
        itv.grid(row=7, column=0, sticky="ew", pady=4)
        ttk.Label(itv, text="增量刷新").grid(row=0, column=0, padx=6, pady=6)
        ttk.Spinbox(itv, from_=1, to=180, width=5, textvariable=self.auto_min_var).grid(row=0, column=1)
        ttk.Label(itv, text="全量重拉").grid(row=0, column=2, padx=6)
        ttk.Spinbox(itv, from_=5, to=600, width=5, textvariable=self.full_min_var).grid(row=0, column=3)
        ttk.Label(itv, text="锁定数").grid(row=0, column=4, padx=6)
        ttk.Spinbox(itv, from_=1, to=600, width=5, textvariable=self.lock_min_var).grid(row=0, column=5)
        ttk.Button(itv, text="应用", command=self.apply_intervals).grid(row=0, column=6, padx=10)

        status_row = ttk.Frame(main)
        status_row.grid(row=5, column=0, sticky="ew", pady=4)
        status_row.columnconfigure(0, weight=1)
        self.status_label = ttk.Label(status_row, textvariable=self.status_text, foreground="#0b5394")
        self.status_label.grid(row=0, column=0, sticky="w")
        self.progress = ttk.Progressbar(status_row, mode="indeterminate", length=200)
        self.progress.grid(row=0, column=1, sticky="e", padx=8)
        self.progress.grid_remove()

        # 扫码记录
        log = ttk.LabelFrame(main, text="扫码记录")
        log.grid(row=3, column=0, sticky="nsew")          # 扫码记录：紧跟在「扫码后显示编码」下面
        main.rowconfigure(3, weight=1)
        cols = ("time", "barcode", "pending", "shelf", "orders", "who", "print_num", "printed")
        self.tree = ttk.Treeview(log, columns=cols, show="headings", height=16)
        for c, t, w in (("time", "扫码时间", 155), ("barcode", "商家编码", 210),
                        ("pending", "待发货订单数", 100), ("shelf", "货架在架数", 90),
                        ("orders", "件数", 60), ("who", "扫码账号", 125),
                        ("print_num", "可打单数量", 95), ("printed", "已打", 80)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="center")
        self.tree.pack(fill=tk.BOTH, expand=True)
        _tsb = ttk.Scrollbar(log, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=_tsb.set)
        _tsb.pack(side=tk.RIGHT, fill="y")
        ttk.Button(log, text="刷新记录",
                   command=lambda: self._poll_records(force=True)).pack(side=tk.BOTTOM, pady=3)
        self.tree.tag_configure("ok", background=self.GREEN_BG)
        self.tree.tag_configure("alert", background=self.RED_BG)
        self.tree.tag_configure("printed", background="#FFF6CC", foreground="#B8860B")   # 已打：黄色
        self.tree.bind("<Button-1>", self._on_record_click)      # 点「已打」那一格可切换
        self.tree.bind("<Double-Button-1>", self._on_record_dblclick)   # 双击整行也能切换

        self.scan_entry.focus()
        self._log_count = -1
        self.root.after(1500, self._poll_records)      # 手机/网页扫的码也会进这张表，定时刷新
        try:                                           # 切回窗口时也刷一次
            self.root.bind("<FocusIn>", lambda e: self._poll_records(force=True))
        except Exception:
            pass

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
        meta = load_orders_meta(("shelf_at", "shelf_stat", "shelf_ts"))
        self.shelf_at = meta.get("shelf_at") or "未知"
        try:
            self.shelf_at_ts = float(meta.get("shelf_ts") or 0)
        except Exception:
            self.shelf_at_ts = 0
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
        self.shelf_at_ts = time.time()
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

    # ---------- 首次使用（未配置 API）----------
    def _first_run_api_hint(self):
        """没配置 API 参数时（新电脑首次装）：提示并直接打开设置窗口。"""
        if API_CONF.get("appKey") and API_CONF.get("sessionId"):
            return
        self.status_text.set("还没配置 API 参数：点「API 设置」填 appKey / appSecret / refreshToken / sessionId")
        try:
            messagebox.showinfo("首次使用",
                                "还没有配置快麦接口参数。\n\n"
                                "请在接下来的窗口里填写 appKey / appSecret / refreshToken / sessionId，\n"
                                "可以点「测试连接」验证，然后「保存并应用」——之后会自动开始拉取数据。",
                                parent=self.root)
        except Exception:
            pass
        self.on_api_settings()

    # ---------- 后台扫码监听（最小化 / 不在前台也能扫） ----------
    def _init_scan_hook(self):
        """按设置启动全局键盘监听；抓到扫码枪就查询并弹浮窗，不依赖窗口焦点。"""
        if self.hook_on.get():
            self._start_hook()
        else:
            self.status_text.set("后台扫码监听：已关闭（勾选「后台扫码监听」可开启）")

    def _start_hook(self):
        try:
            if self._hook is None or not self._hook.alive():
                self._hook = ScanKeyHook(self._on_hook_code)
                self._hook.start()

            def _report():
                h = self._hook
                if h and h.ok:
                    self.status_text.set("后台扫码监听：已开启（最小化/不在前台也能扫）")
                else:
                    self.status_text.set("后台扫码监听：启动失败 %s" % ((h.err if h else "") or ""))

            self.root.after(800, _report)
        except Exception as e:
            self.status_text.set("后台扫码监听启动失败：%s" % str(e)[:80])

    def on_autosubmit_toggle(self):
        """「不回车的扫码枪：停顿时自动查」开关（默认关 = 手动输入不自动查）。"""
        val = bool(self.autosubmit_on.get())
        s = load_settings()
        s["auto_submit"] = val
        save_settings(s)
        self.status_text.set("输入停顿自动查询：%s（%s）"
                             % ("已开启" if val else "已关闭",
                                "打字停顿约 0.35 秒就查询" if val else "回车或点「查询」才查"))

    def on_hook_toggle(self):
        val = bool(self.hook_on.get())
        s = load_settings()
        s["bg_scan_hook"] = val
        save_settings(s)
        if val:
            self._start_hook()
        else:
            try:
                if self._hook:
                    self._hook.stop()
            except Exception:
                pass
            self._hide_float()
            self.status_text.set("后台扫码监听：已关闭")

    def _on_hook_code(self, code):
        """钩子线程回调：只把结果丢进队列（Tk 只能主线程碰）。"""
        try:
            code = (code or "").strip()
            if code:
                self.q.put(lambda: self._hook_scan(code))
        except Exception:
            pass

    def _hook_scan(self, code):
        """全局监听捕到的扫码。程序在前台时由输入框处理，这里不重复记。"""
        if self._scanning:
            return
        if self._is_foreground():
            return
        now = time.time()
        if code == self._last_hook_code and (now - self._last_hook_at) < 1.5:
            return
        self._last_hook_code, self._last_hook_at = code, now
        self._scanning = True
        self._run_bg(self._worker_scan, code, True)

    def _is_foreground(self):
        """当前前台窗口是不是本程序。"""
        try:
            import ctypes
            from ctypes import wintypes
            user32 = ctypes.WinDLL("user32", use_last_error=True)
            hwnd = user32.GetForegroundWindow()
            pid = wintypes.DWORD()
            user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
            return int(pid.value) == os.getpid()
        except Exception:
            return False

    # ---------- 扫码浮窗（后台扫码时显示） ----------
    FLOAT_MS = 10000        # 停留时间（毫秒）

    def _show_float(self, code, one_piece, multi_piece, bin_txt, shelf, ok, short):
        """置顶浮窗：不抢焦点、10 秒自动消失、点一下立即关。"""
        try:
            bg = self.GREEN_BG if ok else self.RED_BG
            if self._float is None:
                f = tk.Toplevel(self.root)
                f.overrideredirect(True)
                f.attributes("-topmost", True)
                f.configure(bg="#9aa0a6")
                inner = tk.Frame(f, bg=bg)
                inner.pack(fill=tk.BOTH, expand=True, padx=1, pady=1)
                self._float_inner = inner
                self._float_code = tk.Label(inner, text="", font=("Microsoft YaHei", 24, "bold"),
                                            fg="#000000", bg=bg, anchor="w", justify="left")
                self._float_code.pack(fill=tk.X, padx=16, pady=(12, 2))
                self._float_body = tk.Label(inner, text="", font=("Microsoft YaHei", 13),
                                            fg="#222222", bg=bg, anchor="w", justify="left")
                self._float_body.pack(fill=tk.X, padx=16)
                self._float_warn = tk.Label(inner, text="", font=("Microsoft YaHei", 22, "bold"),
                                            fg=self.RED, bg=bg, anchor="w")
                self._float_warn.pack(fill=tk.X, padx=16, pady=(0, 12))
                for w in (f, inner, self._float_code, self._float_body, self._float_warn):
                    w.bind("<Button-1>", lambda e: self._hide_float())
                self._float = f
            self._float_inner.configure(bg=bg)
            for w in (self._float_code, self._float_body, self._float_warn):
                w.configure(bg=bg)
            self._float_code.config(text=code)
            self._float_body.config(text="待发货一单一件：%d\n待发货一单多件：%d\n货位：%s（在架 %d）"
                                         % (one_piece, multi_piece, bin_txt, shelf))
            self._float_warn.config(text="需补货" if short else "")
            self._float.update_idletasks()
            x, y = self._float_pos()
            self._float.geometry("+%d+%d" % (x, y))
            self._float.deiconify()
            self._float.lift()
            if self._float_after:
                try:
                    self.root.after_cancel(self._float_after)
                except Exception:
                    pass
            self._float_after = self.root.after(self.FLOAT_MS, self._hide_float)
        except Exception as e:
            self.status_text.set("浮窗显示失败：%s" % str(e)[:80])

    def _float_pos(self):
        """屏幕右下角（按工作区算，避开任务栏）。"""
        try:
            import ctypes

            class RECT(ctypes.Structure):
                _fields_ = [("l", ctypes.c_long), ("t", ctypes.c_long),
                            ("r", ctypes.c_long), ("b", ctypes.c_long)]

            r = RECT()
            ctypes.windll.user32.SystemParametersInfoW(0x0030, 0, ctypes.byref(r), 0)  # SPI_GETWORKAREA
            w = self._float.winfo_reqwidth()
            h = self._float.winfo_reqheight()
            return r.r - w - 18, r.b - h - 18
        except Exception:
            return (max(0, self.root.winfo_screenwidth() - 400),
                    max(0, self.root.winfo_screenheight() - 240))

    def _hide_float(self):
        try:
            if self._float is not None:
                self._float.withdraw()
        except Exception:
            pass
        if self._float_after:
            try:
                self.root.after_cancel(self._float_after)
            except Exception:
                pass
            self._float_after = None

    # ---------- 现货可发（在架 / 待发货 / 可发件数） ----------
    def on_stock_dialog(self):
        """现货可发窗口：可发 = min(在架, 待发货件数) − 一单多件件数。

        只给多件单预留库存；例：一单一件 100 件、一单多件 20 件、在架 80 件 → 可发 60 件。
        """
        old = getattr(self, "_stock_win", None)
        if old is not None:
            try:
                old.destroy()
            except Exception:
                pass
        win = tk.Toplevel(self.root)
        self._stock_win = win
        win.title("现货可发（在架 / 待发货 / 可发件数）")
        win.geometry("1060x660")
        win.transient(self.root)
        top = ttk.Frame(win, padding=(10, 8))
        top.pack(fill=tk.X)
        ttk.Label(top, text="编码/款号").pack(side=tk.LEFT)
        kw = tk.StringVar()
        ent = ttk.Entry(top, textvariable=kw, width=18, font=("Consolas", 14))
        ent.pack(side=tk.LEFT, padx=6)
        ttk.Label(top, text="排序").pack(side=tk.LEFT, padx=(8, 2))
        sort = tk.StringVar(value="加急有货优先（可发多→少）")
        cb_sort = ttk.Combobox(top, textvariable=sort, width=20, state="readonly",
                               values=("加急有货优先（可发多→少）", "可发数量（多→少）", "加急件数（多→少）",
                                       "在架数（多→少）", "待发货件数（多→少）", "编码 A→Z"))
        cb_sort.pack(side=tk.LEFT)
        ttk.Label(top, text="只看").pack(side=tk.LEFT, padx=(8, 2))
        only = tk.StringVar(value="全部")
        cb_only = ttk.Combobox(top, textvariable=only, width=15, state="readonly",
                               values=("全部", "只看加急且有货", "只看有加急", "只看可发（>0）",
                                       "只看缺货（<0）", "只看有待发货"))
        cb_only.pack(side=tk.LEFT)
        rows = []
        btn = ttk.Button(top, text="查询")
        btn.pack(side=tk.LEFT, padx=6)
        ttk.Button(top, text="导出 Excel",
                   command=lambda: self._export_stock(rows)).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="标记已发",
                   command=lambda: mark_sel(True)).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="撤回", command=lambda: mark_sel(False)).pack(side=tk.LEFT, padx=3)
        ttk.Button(top, text="清空已发", command=lambda: clear_all()).pack(side=tk.LEFT, padx=3)
        ttk.Button(top, text="改库存", command=lambda: adjust_one()).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="操作日志",
                   command=lambda: self.on_adjust_log_dialog()).pack(side=tk.LEFT, padx=4)
        hide_sent = tk.BooleanVar(value=True)
        ttk.Checkbutton(top, text="隐藏已发", variable=hide_sent,
                        command=lambda: refresh()).pack(side=tk.LEFT, padx=6)
        info = tk.StringVar(value="可发 = 能发出去的件数：订单要的和库存取小的，再扣掉留给多件单的部分")
        ttk.Label(win, textvariable=info, foreground="#0b5394").pack(anchor="w", padx=12)
        cols = ("code", "bin", "shelf", "ones", "multi", "mp", "urgent", "pieces", "free")
        heads = (("code", "编码", 190), ("bin", "货位", 130),
                 ("shelf", "在架数", 75), ("ones", "一单一件（单/件）", 105),
                 ("multi", "一单多件（单）", 95), ("mp", "多件件数", 75),
                 ("urgent", "加急（单/件）", 95),
                 ("pieces", "待发货件数", 85), ("free", "可发数量", 85))
        tree = ttk.Treeview(win, columns=cols, show="headings", height=18)
        for c, t, w in heads:
            tree.heading(c, text=t)
            tree.column(c, width=w, anchor="center")
        tree.tag_configure("neg", foreground="#c62828")
        tree.tag_configure("pos", foreground="#1b7f35")
        tree.tag_configure("urgent", foreground="#d81b60")
        tree.tag_configure("prio", foreground="#FF3B30", font=("Microsoft YaHei", 10, "bold"))
        tree.tag_configure("sent", foreground="#1B7F35")
        tree.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)

        only_map = {"全部": "all", "只看可发（>0）": "free", "只看缺货（<0）": "short",
                    "只看有待发货": "orders", "只看有加急": "urgent", "只看加急且有货": "urg_free"}
        sort_map = {"可发数量（多→少）": "free", "在架数（多→少）": "shelf",
                    "待发货件数（多→少）": "pieces", "编码 A→Z": "code",
                    "加急件数（多→少）": "urgent", "加急有货优先（可发多→少）": "urg_free"}

        def mark_sel(mark=True):
            sel = [tree.item(i, "values")[0] for i in tree.selection()]
            if not sel:
                messagebox.showinfo("提示", "先在表格里选中要处理的编码（可多选）")
                return
            self.mark_sent([str(x) for x in sel], undo=not mark)
            refresh()

        def clear_all():
            if messagebox.askyesno("确认", "清空所有「已发」标记？"):
                self.clear_sent()
                refresh()

        def adjust_one():
            """按货位改库存（盘点接口，绝对值）：选中行 → 填货位/数量 → 二次确认。"""
            sel = tree.selection()
            if not sel:
                messagebox.showinfo("提示", "先在表格里选中要改库存的编码")
                return
            code = str(tree.item(sel[0], "values")[0])
            info_b = self.stock_bins_of(code)
            bins = info_b.get("bins") or []
            hint = "、".join("%s=%s" % (b[0], b[1]) for b in bins) if bins else "无货位记录"
            bin_code = simpledialog.askstring("改库存", "编码 %s\n货位号（现有：%s）" % (code, hint),
                                              initialvalue=str(bins[0][0]) if bins else "", parent=win)
            if not bin_code:
                return
            bin_code = bin_code.strip()
            cur = None
            for b in bins:
                if str(b[0]).upper() == bin_code.upper():
                    cur = b[1]
            qty = simpledialog.askstring("改库存", "把 %s 货位 %s 改成多少件？（当前 %s）"
                                         % (code, bin_code,
                                            ("%s 件" % cur) if cur is not None else "无记录"),
                                         initialvalue=("0" if cur is None else str(cur)), parent=win)
            if qty is None:
                return
            try:
                q = int(str(qty).strip())
                if q < 0:
                    raise ValueError
            except Exception:
                messagebox.showerror("改库存", "数量要填 0 或正整数")
                return
            if not messagebox.askyesno("确认改库存",
                                       "编码：%s\n货位：%s\n%s → %d 件\n\n"
                                       "【这会真实修改快麦里的库存，不可撤销】\n继续？"
                                       % (code, bin_code,
                                          ("当前 %s 件" % cur) if cur is not None else "当前无记录", q),
                                       parent=win):
                return
            out = self.stock_adjust(code, bin_code, q, who="桌面版·%s" % (os.environ.get("USERNAME") or "本机"))
            if out.get("ok"):
                messagebox.showinfo("改库存", "✓ 已改：%s @ %s → %d 件" % (code, bin_code, q), parent=win)
                refresh()
            else:
                messagebox.showerror("改库存失败", str(out.get("msg") or "未知错误"), parent=win)

        def refresh(*_a):
            try:
                got = self.stock_rows(kw.get(), only_map.get(only.get(), "all"),
                                      sort_map.get(sort.get(), "free"))
            except Exception as e:
                info.set("读取失败：%s" % str(e)[:80])
                return
            rows[:] = got
            shown = [r for r in got if not (hide_sent.get() and r.get("sent"))]
            tree.delete(*tree.get_children())
            for r in shown[:3000]:
                if r.get("sent"):
                    tags = ("sent",)
                elif r["f"] < 0:
                    tags = ("neg",)
                elif r.get("p1"):
                    tags = ("prio",)
                elif (r.get("up") or r.get("uo")):
                    tags = ("urgent",)
                else:
                    tags = ("pos",)
                tree.insert("", tk.END, values=(r["c"], r.get("b", ""), r["s"],
                                                "%d / %d" % (r["n"], r["n"]),
                                                r["m"], r["mp"],
                                                "%d / %d" % (r.get("uo", 0), r.get("up", 0)),
                                                r["p"], r["f"]),
                            tags=tags)
            info.set("共 %d 个编码（显示 %d）　已发 %d 个　加急且有货 %d 个（排最前，红字）　"
                     "在架合计 %d 件　一单一件 %d 件　一单多件 %d 件　加急 %d 单/%d 件　可发合计 %d 件%s"
                     % (len(rows), len(shown), sum(r.get("sent", 0) for r in rows),
                        sum(r.get("p1", 0) for r in rows),
                        sum(r["s"] for r in rows), sum(r["n"] for r in rows),
                        sum(r["mp"] for r in rows), sum(r.get("uo", 0) for r in rows),
                        sum(r.get("up", 0) for r in rows), sum(r["f"] for r in rows),
                        "　（只显示前 3000 行，导出含全部）" if len(shown) > 3000 else ""))

        btn.configure(command=refresh)
        ent.bind("<Return>", refresh)
        cb_sort.bind("<<ComboboxSelected>>", refresh)
        cb_only.bind("<<ComboboxSelected>>", refresh)
        refresh()
        ent.focus_set()

    def _export_stock(self, rows):
        """现货可发 → Excel。"""
        rows = list(rows or [])
        if not rows:
            messagebox.showinfo("提示", "没有数据可导出（先点「查询」）")
            return
        path = filedialog.asksaveasfilename(defaultextension=".xlsx", initialfile="现货可发.xlsx",
                                           filetypes=[("Excel 文件", "*.xlsx")],
                                           title="导出现货可发")
        if not path:
            return
        try:
            write_xlsx(path, ["编码", "货位", "一单一件订单数", "一单多件订单数", "多件件数", "加急订单数", "加急件数",
                              "待发货件数", "在架数", "可发数量", "加急且有货"],
                       [[r["c"], r.get("b", ""), r["n"], r["m"], r["mp"], r.get("uo", 0), r.get("up", 0),
                         r["p"], r["s"], r["f"], ("是" if r.get("p1") else "")] for r in rows])
        except Exception as e:
            messagebox.showerror("导出失败", str(e)[:200])
            return
        messagebox.showinfo("已导出", "%s\n共 %d 行" % (path, len(rows)))

    # ---------- 批次查询（按打印批次号） ----------
    def on_adjust_log_dialog(self):
        """改库存操作日志：时间 / 操作账号 / 编码 / 货位 / 原值→新值 / 结果。"""
        win = tk.Toplevel(self.root)
        win.title("改库存 · 操作日志")
        win.geometry("1000x560")
        top = tk.Frame(win)
        top.pack(fill="x", padx=10, pady=8)
        info = tk.StringVar(value="")
        ttk.Label(top, textvariable=info, foreground="#0b5394").pack(side=tk.LEFT)
        cols = ("ts", "who", "code", "bin", "old", "new", "ok", "msg")
        heads = (("ts", "时间", 150), ("who", "操作账号", 160), ("code", "编码", 175),
                 ("bin", "货位", 100), ("old", "原数量", 75), ("new", "新数量", 75),
                 ("ok", "结果", 65), ("msg", "说明", 190))
        box = tk.Frame(win)
        box.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        tree = ttk.Treeview(box, columns=cols, show="headings", height=18)
        for k, txt, w in heads:
            tree.heading(k, text=txt)
            tree.column(k, width=w,
                        anchor="w" if k in ("who", "code", "msg") else "center")
        vs = ttk.Scrollbar(box, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vs.set)
        tree.pack(side=tk.LEFT, fill="both", expand=True)
        vs.pack(side=tk.RIGHT, fill="y")
        tree.tag_configure("bad", foreground="#c62828")

        def refresh():
            try:
                logs = self.adjust_logs(500)
            except Exception as e:
                info.set("读取失败：%s" % str(e)[:80])
                return
            tree.delete(*tree.get_children())
            for L in logs:
                tree.insert("", tk.END,
                            values=(L["ts"], L["who"], L["code"], L["bin"],
                                    L["old"], L["new"], "成功" if L["ok"] else "失败", L["msg"]),
                            tags=() if L["ok"] else ("bad",))
            info.set("共 %d 条（倒序，最多显示最近 500 条）　时间 / 操作账号 / 内容 / 结果" % len(logs))

        ttk.Button(top, text="刷新", command=refresh).pack(side=tk.RIGHT, padx=4)
        refresh()
        return win

    def on_stocktake_dialog(self):
        """（按用户要求）库存盘点只做在网页版，电脑版不再提供入口。"""
        return None
        win = tk.Toplevel(self.root)
        win.title("库存盘点（按款号）")
        win.geometry("1000x620")
        top = tk.Frame(win)
        top.pack(fill="x", padx=10, pady=8)
        ttk.Label(top, text="款号：").pack(side=tk.LEFT)
        kw = tk.StringVar(value="")
        ent = ttk.Entry(top, textvariable=kw, width=16)
        ent.pack(side=tk.LEFT)
        info = tk.StringVar(value="输入款号（如 7107）后回车：列出该款所有颜色尺码的货位与在架数")

        cols = ("code", "bin", "shelf", "pend")
        tree = ttk.Treeview(win, columns=cols, show="headings", height=18)
        for c, t, w in (("code", "编码", 250), ("bin", "货位", 130),
                        ("shelf", "在架", 90), ("pend", "待发货（件）", 110)):
            tree.heading(c, text=t)
            tree.column(c, width=w, anchor="w" if c == "code" else "center")
        vs = ttk.Scrollbar(win, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vs.set)
        tree.tag_configure("zero", foreground="#c62828")

        def do_query(*_a):
            k = kw.get().strip().upper()
            tree.delete(*tree.get_children())
            if not k:
                info.set("先输入款号")
                return
            idx, _st = self._web_index("any", 0)
            hits = []
            for code in (idx or {}):
                if k in str(code).upper():
                    sh, _c = dict_get_ci(self.shelf_map, code)
                    sh = sh or {}
                    e = (idx or {}).get(code) or {}
                    pend = int(e.get("qty", 0) or 0)
                    bins = sh.get("bins") or [["无在架货位", 0]]
                    if not bins:
                        bins = [["无在架货位", 0]]
                    for b in bins:
                        hits.append((str(code), str(b[0]), int(b[1] or 0), pend))
            hits.sort(key=lambda x: (x[0], x[1]))
            for code, bin_, shl, pend in hits:
                tree.insert("", tk.END, values=(code, bin_, shl, pend),
                            tags=("zero",) if shl == 0 else ())
            info.set("款号 %s：%d 个编码 / %d 个货位行，在架合计 %d 件（红字 = 该货位在架 0）"
                     % (k, len(set(h[0] for h in hits)), len(hits), sum(h[2] for h in hits)))

        def sel_one():
            sel = tree.selection()
            if not sel:
                messagebox.showinfo("提示", "先在表格里选中一行（编码 + 货位）", parent=win)
                return None, None, None
            v = tree.item(sel[0], "values")
            return str(v[0]), str(v[1]), v[2]

        def who_am_i():
            return "桌面版·%s" % (os.environ.get("USERNAME") or "本机")

        def adjust_sel():
            code, bin_, shl = sel_one()
            if not code:
                return
            v = simpledialog.askstring("改库存", "%s @ %s 改成多少件？（当前 %s）" % (code, bin_, shl),
                                       initialvalue=str(shl), parent=win)
            if v is None:
                return
            try:
                q = int(str(v).strip())
                if q < 0:
                    raise ValueError
            except Exception:
                messagebox.showerror("改库存", "数量要填 0 或正整数", parent=win)
                return
            if not messagebox.askyesno("确认改库存",
                                       "%s @ %s\n%s → %d 件\n\n【真实修改快麦库存，不可撤销】继续？"
                                       % (code, bin_, shl, q), parent=win):
                return
            out = self.stock_adjust(code, bin_, q, who=who_am_i())
            if out.get("ok"):
                messagebox.showinfo("改库存", "✓ 已改：%s @ %s → %d 件" % (code, bin_, q), parent=win)
            else:
                messagebox.showerror("改库存失败", str(out.get("msg") or "未知错误"), parent=win)
            do_query()

        def zero_sel():
            code, bin_, shl = sel_one()
            if not code:
                return
            if int(shl or 0) == 0:
                messagebox.showinfo("盘0", "这个货位本来就是在架 0，不用盘", parent=win)
                return
            if not messagebox.askyesno("确认盘0",
                                       "%s @ %s\n%s 件 → 0 件\n\n【真实修改快麦库存，不可撤销】"
                                       % (code, bin_, shl), parent=win):
                return
            if not messagebox.askyesno("再确认一次",
                                       "真的要盘0吗？\n%s @ %s → 0 件" % (code, bin_), parent=win):
                return
            out = self.stock_adjust(code, bin_, 0, who=who_am_i())
            if out.get("ok"):
                messagebox.showinfo("盘0", "✓ 已盘0：%s @ %s" % (code, bin_), parent=win)
            else:
                messagebox.showerror("盘0失败", str(out.get("msg") or "未知错误"), parent=win)
            do_query()

        ttk.Button(top, text="查询", command=do_query).pack(side=tk.LEFT, padx=6)
        ttk.Button(top, text="改库存（选中）", command=adjust_sel).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="盘0（选中）", command=zero_sel).pack(side=tk.LEFT, padx=4)
        ent.bind("<Return>", do_query)
        ttk.Label(win, textvariable=info, foreground="#0b5394").pack(anchor="w", padx=12, pady=(0, 6))
        tree.pack(fill="both", expand=True, padx=10, pady=(0, 10))
        vs.pack(side=tk.RIGHT, fill="y", pady=(0, 10))
        ent.focus()
        return win

    def on_batch_dialog(self):
        """输入打印批次号 → 列出该批次订单 + 每单商品编码/货位，并按货位汇总。"""
        old = getattr(self, "_batch_win", None)
        if old is not None:
            try:
                old.destroy()
            except Exception:
                pass
        win = tk.Toplevel(self.root)
        self._batch_win = win
        win.title("批次查询（按打印批次号）")
        win.geometry("1020x640")
        win.transient(self.root)
        top = ttk.Frame(win, padding=(10, 8))
        top.pack(fill=tk.X)
        ttk.Label(top, text="打印批次号").pack(side=tk.LEFT)
        var = tk.StringVar()
        ent = ttk.Entry(top, textvariable=var, width=14, font=("Consolas", 15))
        ent.pack(side=tk.LEFT, padx=6)
        ttk.Label(top, text="查最近").pack(side=tk.LEFT, padx=(8, 2))
        days = tk.StringVar(value="3")
        ttk.Spinbox(top, from_=1, to=90, width=4, textvariable=days).pack(side=tk.LEFT)
        ttk.Label(top, text="天").pack(side=tk.LEFT, padx=(2, 8))
        btn = ttk.Button(top, text="查询")
        btn.pack(side=tk.LEFT, padx=4)
        exp = ttk.Button(top, text="导出 Excel", state=tk.DISABLED, command=self._export_batch)
        exp.pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="读导出文件…", command=self.on_pick_file).pack(side=tk.LEFT, padx=4)
        info = tk.StringVar(value="输入批次号后回车或点「查询」；默认按打印顺序出拣货清单")
        ttk.Label(win, textvariable=info, foreground="#0b5394").pack(anchor="w", padx=12)
        cols = ("seq", "sid", "short", "express", "code", "num", "bins", "shelf", "status")
        heads = (("seq", "打印序号", 60), ("sid", "系统单号", 150), ("short", "内部单号", 90),
                 ("express", "快递单号", 130), ("code", "商品编码", 140), ("num", "件数", 50),
                 ("bins", "货位", 130), ("shelf", "在架", 50), ("status", "系统状态", 150))
        nb = ttk.Notebook(win)
        nb.pack(fill=tk.BOTH, expand=True, padx=12, pady=6)
        f1 = ttk.Frame(nb)
        nb.add(f1, text="按打印顺序（拣货）")
        picktxt = tk.Text(f1, font=("Microsoft YaHei", 13), wrap="none")
        picktxt.pack(fill=tk.BOTH, expand=True)
        f2 = ttk.Frame(nb)
        nb.add(f2, text="明细表")
        tree = ttk.Treeview(f2, columns=cols, show="headings", height=14)
        for c, t, w in heads:
            tree.heading(c, text=t)
            tree.column(c, width=w, anchor="center")
        tree.pack(fill=tk.BOTH, expand=True)
        f3 = ttk.Frame(nb)
        nb.add(f3, text="按货位汇总")
        sumtxt = tk.Text(f3, font=("Microsoft YaHei", 12), wrap="none")
        sumtxt.pack(fill=tk.BOTH, expand=True)
        f4 = ttk.Frame(nb)
        nb.add(f4, text="按分区")
        zonetxt = tk.Text(f4, font=("Microsoft YaHei", 12), wrap="none")
        zonetxt.pack(fill=tk.BOTH, expand=True)
        self._batch_no, self._batch_rows = "", []
        self._batch_ui = {"win": win, "tree": tree, "sum": sumtxt, "pick": picktxt, "nb": nb,
                          "zone": zonetxt,
                          "info": info, "btn": btn, "exp": exp, "var": var, "days": days}

        def do_query():
            b = var.get().strip()
            if not b:
                info.set("请先输入打印批次号")
                return
            btn.config(state=tk.DISABLED)
            exp.config(state=tk.DISABLED)
            info.set("查询中…")
            tree.delete(*tree.get_children())
            sumtxt.delete("1.0", tk.END)
            self._run_bg(self._worker_batch, b, days.get(), btn, exp, info, tree, sumtxt)

        btn.config(command=do_query)
        ent.bind("<Return>", lambda e: do_query())
        try:
            win.grab_set()
        except Exception:
            pass
        ent.focus_set()

    def _worker_batch(self, batch, days, btn, exp, info, tree, sumtxt):
        try:
            def prog(n, page, got):
                self.q.put(lambda: info.set("查询中…已找到 %d 单（第 %d 页，本页 %d 条）" % (n, page, got)))

            orders, err = fetch_print_batch(batch, days, progress=prog)
            if err:
                self.q.put(lambda: (info.set(err), btn.config(state=tk.NORMAL)))
                return
            rows = []
            for o in orders:
                items = o.get("items") or []
                if not items:
                    rows.append([o, "", 0, 0, "（未取到明细）"])
                    continue
                for code, num in items:
                    sh, _k = dict_get_ci(self.shelf_map, code)
                    sh = sh or {}
                    bins = "、".join(b[0] for b in (sh.get("bins") or [])) or "无在架货位"
                    rows.append([o, code, num, int(sh.get("shelf", 0) or 0), bins])
            self.q.put(lambda: self._apply_batch(batch, orders, rows, btn, exp, info, tree, sumtxt,
                                                getattr(self, "_batch_ui", {}).get("pick"),
                                                getattr(self, "_batch_ui", {}).get("zone")))
        except Exception as e:
            msg = str(e)[:160]
            self.q.put(lambda: (info.set("查询失败：%s" % msg), btn.config(state=tk.NORMAL)))

    def _apply_batch(self, batch, orders, rows, btn, exp, info, tree, sumtxt, picktxt=None,
                     zonetxt=None):
        try:
            agg = {}
            pick = []
            miss = 0
            for o, code, num, shelf_qty, bins in rows:
                seq = o.get("seq") or 0
                if pick and pick[-1][2] == code and pick[-1][4] == bins:
                    p = pick[-1]
                    p[1] = seq
                    p[3] += int(num or 0)
                    p[7] += 1
                else:
                    pick.append([seq, seq, code, int(num or 0), bins, shelf_qty, 0, 1])
                if bins and bins != "无在架货位":
                    keys = bins.split("、")
                else:
                    miss += 1
                    keys = ["（无在架货位）"]
                for one_b in keys:
                    a = agg.setdefault((one_b, code), [0, 0])   # [件数, 行数]
                    a[0] += int(num or 0)
                    a[1] += 1
                tree.insert("", tk.END, values=(
                    ("★%s" % seq) if o.get("urgent") else seq,
                    o.get("sid"), o.get("short_id"),
                                                o.get("express"), code, num, bins, shelf_qty,
                                                STATUS_LABEL.get(o.get("sys_status"), o.get("sys_status"))))
            # ① 按打印顺序的拣货清单（相邻同编码同货位合并成一段）
            if picktxt is not None:
                plines = ["批次 %s：%d 单 / %d 行商品" % (batch, len(orders), len(rows)), ""]
                for seq_a, seq_b, code, tot, bins, sq, _x, cnt in pick:
                    rng = ("第 %s 张" % seq_a) if seq_a == seq_b else ("第 %s-%s 张" % (seq_a, seq_b))
                    plines.append("%-14s %-18s ×%-3d  货位：%s（在架 %s）"
                                  % (rng, code, tot, bin_label(bins), sq))
                if miss:
                    plines.append("")
                    plines.append("注：%d 行显示「无在架货位」，说明当前不在常规货位上。" % miss)
                picktxt.delete("1.0", tk.END)
                picktxt.insert("1.0", "\n".join(plines))
            # ② 按分区（A/B/C/D 分开列，可分别发给不同的人去拣）
            if zonetxt is not None:
                byzone = {}
                for g in pick:
                    z = zone_of(g[4]) or "无货位"
                    byzone.setdefault(z, []).append(g)
                zlines = ["批次 %s：%d 单 / %d 行商品（按分区）" % (batch, len(orders), len(rows)), ""]
                for z in sorted(byzone, key=lambda x: (zone_rank(x if x != "无货位" else ""), x)):
                    zl = byzone[z]
                    tot = sum(g[3] for g in zl)
                    zlines.append(("【%s】%d 组 / %d 件" if z == "无货位" else "【%s区】%d 组 / %d 件")
                                  % (z, len(zl), tot))
                    for g in sorted(zl, key=lambda g: g[0]):
                        rng = ("第 %s 张" % g[0]) if g[0] == g[1] else ("第 %s-%s 张" % (g[0], g[1]))
                        zlines.append("    %-14s %-18s ×%-4d 货位 %s（在架 %s）"
                                      % (rng, g[2], g[3], bin_label(g[4]), g[5]))
                    zlines.append("")
                if miss:
                    zlines.append("注：%d 行显示「无在架货位」。" % miss)
                zonetxt.delete("1.0", tk.END)
                zonetxt.insert("1.0", "\n".join(zlines))
            lines = ["批次 %s：%d 单，%d 行商品" % (batch, len(orders), len(rows))]
            cur = None
            for (one_b, code) in sorted(agg):
                if one_b != cur:
                    lines.append("%s：" % one_b)
                    cur = one_b
                n, c = agg[(one_b, code)]
                lines.append("    %s ×%d（%d 行）" % (code, n, c))
            if miss:
                lines.append("提示：有 %d 行当前不在常规货位上（无在架货位）。" % miss)
            sumtxt.delete("1.0", tk.END)
            sumtxt.insert("1.0", "\n".join(lines))
            self._batch_no, self._batch_rows = batch, rows
            exp.config(state=tk.NORMAL)
            info.set("完成：批次 %s 共 %d 单 / %d 行商品" % (batch, len(orders), len(rows)))
            # 货位数据旧了就顺手刷一次，下次查批次/扫码就是新的
            if time.time() - getattr(self, "shelf_at_ts", 0) > 120:
                self.reload_shelf(background=True)
        except Exception as e:
            info.set("渲染失败：%s" % str(e)[:120])
        finally:
            btn.config(state=tk.NORMAL)

    def on_pick_file(self):
        """从 ERP 导出的「批次打印记录」Excel/CSV 出拣货清单（不依赖接口）。"""
        path = filedialog.askopenfilename(
            title="选择 ERP 导出的批次文件",
            filetypes=[("Excel / CSV", "*.xlsx *.xls *.csv *.txt"), ("所有文件", "*.*")])
        if not path:
            return
        try:
            headers, data = read_table_file(path)
        except Exception as e:
            messagebox.showerror("读取失败", "%s\n\n%s" % (path, e))
            return
        if not data:
            messagebox.showerror("读取失败", "文件里没有数据行：\n%s" % path)
            return
        i_seq = _pick_col(headers, ("打印序号", "序号", "sequenc", "seq"))
        i_code = _pick_col(headers, ("商品编码", "商家编码", "规格编码", "编码", "sku", "outerid"))
        i_num = _pick_col(headers, ("件数", "数量", "num", "qty"))
        i_sid = _pick_col(headers, ("系统单号", "sid", "订单号", "内部单号"))
        i_exp = _pick_col(headers, ("快递单号", "物流单号", "运单号", "outsid"))
        i_batch = _pick_col(headers, ("打印批次号", "批次号", "batch"))
        if i_code < 0:
            messagebox.showerror("读取失败",
                                 "没找到「商品编码 / 商家编码」列。\n表头：%s"
                                 % " | ".join(str(h) for h in headers)[:300])
            return
        orders, rows, seen = [], [], set()
        batch_no = ""
        for n, r in enumerate(data):
            def cell(i):
                return str(r[i]).strip() if (0 <= i < len(r) and r[i] is not None) else ""
            code = cell(i_code)
            if not code:
                continue
            try:
                num = int(float(cell(i_num) or 1))
            except Exception:
                num = 1
            try:
                seq = int(float(cell(i_seq))) if i_seq >= 0 and cell(i_seq) else (n + 1)
            except Exception:
                seq = n + 1
            sid = cell(i_sid)
            key = (seq, code, sid)
            if key in seen:
                continue
            seen.add(key)
            if i_batch >= 0 and not batch_no:
                batch_no = cell(i_batch)
            orders.append({"seq": seq, "sid": sid, "short_id": "", "express": cell(i_exp),
                           "sys_status": "", "items": [(code, num)]})
            bins, shelf = self._shelf_lookup(code)
            rows.append([orders[-1], code, num, shelf, bins])
        if not rows:
            messagebox.showerror("读取失败", "没能从文件里解析出编码/件数。")
            return
        orders.sort(key=lambda o: o.get("seq") or 0)
        self.on_batch_dialog()
        ui = self._batch_ui
        label = batch_no or os.path.basename(path)
        ttk.Style()  # 占位（不影响）
        ui["var"].set(str(batch_no or ""))
        self._apply_batch(label, orders, rows, ui["btn"], ui["exp"], ui["info"],
                          ui["tree"], ui["sum"], ui["pick"], ui["zone"])
        try:
            ui["nb"].select(0)
        except Exception:
            pass
        self.status_text.set("已从文件出拣货清单：%s（%d 行）" % (os.path.basename(path), len(rows)))

    def _export_batch(self):
        rows = getattr(self, "_batch_rows", None) or []
        if not rows:
            return
        batch = getattr(self, "_batch_no", "")
        headers = ["打印序号", "系统单号", "内部单号", "快递单号", "商品编码", "件数", "分区", "货位", "在架", "系统状态"]
        data = [[o.get("seq"), o.get("sid"), o.get("short_id"), o.get("express"), code, num,
                 zone_of(bins), bins, shelf_qty,
                 STATUS_LABEL.get(o.get("sys_status"), o.get("sys_status"))]
                for o, code, num, shelf_qty, bins in rows]
        path = os.path.join(BASE_DIR, "批次%s_%s.xlsx" % (batch, datetime.now().strftime("%Y%m%d_%H%M%S")))
        try:
            write_xlsx(path, headers, data)
            self.status_text.set("已导出批次 %s：%s" % (batch, path))
            messagebox.showinfo("导出成功", "已导出 %d 行到：\n%s" % (len(data), path))
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    # ---------- API 设置 ----------
    def on_api_settings(self):
        """改 appKey/appSecret/refreshToken/session/网关/版本 —— 换账号不用重新打包。"""
        win = tk.Toplevel(self.root)
        win.title("API 设置（换账号 / 换网关 / 换版本）")
        win.transient(self.root)
        win.resizable(False, False)
        conf = dict(API_CONF)
        rows = (("gateway", "网关地址"),
                ("version", "API 版本"),
                ("appKey", "appKey"),
                ("appSecret", "appSecret"),
                ("refreshToken", "refreshToken"),
                ("sessionId", "sessionId (accessToken)"))
        frm = ttk.Frame(win, padding=10)
        frm.pack(fill=tk.BOTH, expand=True)
        frm.columnconfigure(1, weight=1)
        vars_ = {}
        for i, (key, label) in enumerate(rows):
            ttk.Label(frm, text=label).grid(row=i, column=0, sticky="w", padx=(0, 8), pady=3)
            v = tk.StringVar(value=str(conf.get(key) or ""))
            vars_[key] = v
            ttk.Entry(frm, textvariable=v, width=54).grid(row=i, column=1, sticky="ew", pady=3)
        sm_var = tk.StringVar(value=str(conf.get("signMethod") or "hmac-sha256"))
        up_var = tk.BooleanVar(value=bool(conf.get("signUpper")))
        ttk.Label(frm, text="签名方式").grid(row=len(rows), column=0, sticky="w", padx=(0, 8), pady=3)
        sub = ttk.Frame(frm)
        sub.grid(row=len(rows), column=1, sticky="w", pady=3)
        ttk.Combobox(sub, textvariable=sm_var, values=("hmac-sha256", "hmac", "md5"),
                     width=14, state="readonly").pack(side=tk.LEFT)
        ttk.Checkbutton(sub, text="签名结果大写", variable=up_var).pack(side=tk.LEFT, padx=10)
        ttk.Label(frm, foreground="#666", justify="left",
                  text="· 改完点「保存并应用」；换账号后建议再点「全量重拉」重建数据（旧账号的单会留在库里）。\n"
                       "· 这些值存在 exe 同目录的 kuaimai_api.json（可直接拷到别的电脑，不用重打包）。"
                  ).grid(row=len(rows) + 1, column=0, columnspan=2, sticky="w", pady=(8, 0))
        tip = tk.StringVar(value="")
        ttk.Label(frm, textvariable=tip, foreground="#0b5394").grid(
            row=len(rows) + 2, column=0, columnspan=2, sticky="w", pady=(4, 0))

        def _collect():
            c = {k: vars_[k].get().strip() for k in vars_}
            c["signMethod"] = sm_var.get()
            c["signUpper"] = bool(up_var.get())
            return c

        def _restore_defaults():
            for k in vars_:
                vars_[k].set(str(DEFAULT_API.get(k) or ""))
            sm_var.set(DEFAULT_API["signMethod"])
            up_var.set(bool(DEFAULT_API["signUpper"]))
            tip.set("已填入内置默认值（还没保存）")

        def _do_save():
            try:
                save_api_conf(_collect())
            except Exception as e:
                messagebox.showerror("保存失败", str(e), parent=win)
                return
            self.status_text.set("API 参数已更新：网关 %s，版本 %s（存在 kuaimai_api.json）"
                                 % (API_CONF.get("gateway"), API_CONF.get("version")))
            win.destroy()
            if db_orders_total() <= 0:
                messagebox.showinfo("已保存",
                                    "API 参数已生效。\n\n本地还没有订单数据，现在开始全量拉取"
                                    "（约 20 分钟，界面上有进度）。", parent=self.root)
                self.full_reload(background=True)
            elif messagebox.askyesno("已保存",
                                     "API 参数已生效。\n\n换了账号/网关的话，库里还是旧账号的数据。\n"
                                     "现在马上「全量重拉」吗？", parent=self.root):
                self.full_reload(background=True)

        def _do_test():
            c = _collect()
            tip.set("测试中（用输入框里的值，不影响已保存的设置）…")
            saved = dict(API_CONF)

            def work():
                try:
                    API_CONF.clear()
                    API_CONF.update(c)
                    res = api_call("erp.trade.list.query",
                                   {"status": "WAIT_SEND_GOODS", "pageNo": "1", "pageSize": "1"},
                                   c.get("sessionId") or "", 20)
                    if isinstance(res, dict) and res.get("success"):
                        msg = "✓ 连接成功（待发货总数 %s）" % res.get("total", "?")
                    else:
                        code = res.get("code") if isinstance(res, dict) else "?"
                        m = res.get("msg") if isinstance(res, dict) else str(res)[:80]
                        msg = "✗ 失败 code=%s msg=%s" % (code, m)
                except Exception as e:
                    msg = "✗ 网络/接口异常：%s" % str(e)[:120]
                finally:
                    API_CONF.clear()
                    API_CONF.update(saved)
                self.q.put(lambda: tip.set(msg))

            threading.Thread(target=work, daemon=True).start()

        btns = ttk.Frame(frm)
        btns.grid(row=len(rows) + 3, column=0, columnspan=2, sticky="e", pady=(10, 0))
        ttk.Button(btns, text="保存并应用", command=_do_save).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="测试连接", command=_do_test).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="恢复默认值", command=_restore_defaults).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="取消", command=win.destroy).pack(side=tk.LEFT, padx=4)
        win.grab_set()

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
        """定时：到点跑全量（每 full_refresh_min 分钟），其余时候跑增量；并定期刷新锁定数、货位。"""
        if not self._syncing:
            if (time.time() - self.last_full_ts) >= self.full_refresh_min * 60:
                self.full_reload(background=True)
            else:
                self.sync_pending(background=True)
        if time.time() - self.lock_at_ts > self.lock_refresh_min * 60:
            self.reload_lock(background=True)
        if time.time() - self.shelf_at_ts > self.shelf_refresh_min * 60:
            self.reload_shelf(background=True)
        self.root.after(1000 * 60 * self.auto_refresh_min, self._auto_tick)

    # ---------- 扫码 ----------
    def _on_scan_key(self, event):
        """回车提交由 <Return> 绑定负责。

        手动输入**不再自动查**（与手机网页一致）；只有勾了「不回车的扫码枪：停顿时自动查」
        才按输入停顿自动提交（老型号枪不回车时用）。
        """
        if not self.autosubmit_on.get():
            return
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
            # 输入框空着点「查询」：清空上一次的扫码结果
            try:
                self.result.config(text="")
                self.result_detail.config(text="")
                self.warn_label.config(text="")
            except Exception:
                pass
            self.status_text.set("已清空上次结果（扫入/输入商家编码后回车查询）")
            return
        if self._scanning:
            return
        self._scanning = True
        self.status_text.set("查询中：%s …" % code)
        self._run_bg(self._worker_scan, code)

    def _worker_scan(self, code, from_hook=False):
        try:
            # 主编码/系列查询：输入 9687 就列全部 9687-* 规格的货位
            keys, is_series = series_matches(self.index, code)
            if is_series:
                self._worker_series(code, keys)
                return
            # 编码不分大小写：先精确、再忽略大小写；命中后用库里那个写法
            entry, canon = dict_get_ci(self.index, code)
            entry = entry or {"qty": 0, "orders": 0, "ones": 0, "main": False}
            pending = int(entry.get("qty", 0))
            orders_count = int(entry.get("orders", 0))
            ones = int(entry.get("ones", 0))

            # 货架在架数：直接取本地货位缓存（秒查，不联网）
            shelf_entry, _k = dict_get_ci(self.shelf_map, canon)
            shelf_entry = shelf_entry or {}
            shelf = int(shelf_entry.get("shelf", 0) or 0)
            bins = shelf_entry.get("bins") or []
            shelf_note = "货位缓存 %s" % self.shelf_at if self.shelf_map else "货位缓存未加载"

            # 库存锁定数：本地缓存
            lock_entry, _k = dict_get_ci(self.lock_map, canon)
            lock_entry = lock_entry or {}
            lock_n = int(lock_entry.get("lock", 0) or 0)
            sell_n = int(lock_entry.get("sellable", 0) or 0)
            avail_n = int(lock_entry.get("avail", 0) or 0)

            light = "绿" if orders_count > 0 else "红"
            insert_scan(canon, orders_count, shelf, pending, light,
                        who="桌面版·%s" % (os.environ.get("USERNAME") or "本机"))
            self.q.put(lambda: self._apply_scan(canon, orders_count, pending, ones, shelf, shelf_note,
                                               bins, lock_n, sell_n, avail_n, from_hook))
        except Exception as e:
            msg = str(e)[:200]
            self.q.put(lambda: self._finish_scan("扫码查询失败：%s" % msg))

    def _worker_series(self, code, keys):
        """主编码查询：列出该主编码下所有规格的货位/在架/待发货/锁定。"""
        lines = []
        for k in keys[:120]:
            e, _c = dict_get_ci(self.index, k)
            e = e or {}
            sh, _k2 = dict_get_ci(self.shelf_map, k)
            sh = sh or {}
            lk, _k3 = dict_get_ci(self.lock_map, k)
            lk = lk or {}
            bins = "、".join(b[0] for b in (sh.get("bins") or [])) or "无货位"
            lines.append("%-22s 货位 %-16s 在架 %-6s 待发货 %-5s 锁定 %s"
                         % (k, bins, sh.get("shelf", 0),
                            "%s件/%s单" % (e.get("qty", 0), e.get("orders", 0)), lk.get("lock", 0)))
        more = max(0, len(keys) - 120)
        self.q.put(lambda: self._apply_series(code, lines, len(keys), more))

    def _apply_series(self, code, lines, total, more=0):
        txt = "\n".join(lines) + (("\n……还有 %d 个规格未列出" % more) if more else "")
        self.result.config(text="%s（主编码，共 %d 个规格）" % (code, total), bg=self.GREY_BG, fg="#000000")
        self.result_detail.config(text=txt or "没找到该主编码下的规格")
        self.warn_label.config(text="")
        self.status_text.set("主编码查询 %s：%d 个规格" % (code, total))
        self._scanning = False

    def _apply_scan(self, code, orders_count, pending, ones, shelf, shelf_note, bins,
                    lock_n=0, sell_n=0, avail_n=0, from_hook=False):
        self._scanning = False
        ok = orders_count > 0
        # 一单一件：整单只有一件的单（每单正好 1 件）；剩下的就是“一单多件”
        one_piece = min(int(ones or 0), int(pending or 0))
        multi_piece = max(0, int(pending or 0) - one_piece)
        short = ok and (int(pending or 0) > int(shelf or 0))
        self.result.config(
            text=code,
            bg=self.GREEN_BG if ok else self.RED_BG,
            fg="#000000",
            font=("Microsoft YaHei", 26, "bold"),
        )
        bin_txt = "、".join("%s×%d" % (b[0], b[1]) for b in bins[:6]) if bins else "无在架货位"
        self.result_detail.config(
            text="待发货一单一件：%d\n待发货一单多件：%d\n货位：%s（在架 %d）"
            % (one_piece, multi_piece, bin_txt, int(shelf or 0)))
        self.warn_label.config(text="需补货" if short else "")
        self.tree.insert("", 0, values=(now_gmt8(), code, orders_count, shelf, pending,
                                        "桌面版·%s" % (os.environ.get("USERNAME") or "本机"),
                                        "", "【打单】"),
                         tags=("ok",) if ok else ("alert",))
        self.status_text.set("查询完成：%s（一单一件 %d / 一单多件 %d；在架 %d）%s"
                             % (code, one_piece, multi_piece, int(shelf or 0),
                                "；需补货" if short else ""))
        if from_hook:
            self._show_float(code, one_piece, multi_piece, bin_txt, int(shelf or 0), ok, short)
        else:
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

    def _poll_records(self, force=False):
        """手机/网页扫的码也会写进扫码记录表：定时看条数变没变，变了就刷新（不打断输入）。
        刷新失败不推进计数，下次继续重试。"""
        n = None
        try:
            conn = get_conn()
            n = int(conn.cursor().execute("SELECT COUNT(*) FROM scan_record").fetchone()[0])
            conn.close()
        except Exception:
            n = None
        if (force or (n is not None and n != getattr(self, "_log_count", -1))):
            if (not force) and (time.time() - getattr(self, "_touch_ts", 0)) < 3:
                pass                      # 刚点过「已打」，先别重建行
            else:
                try:
                    self.reload_records()
                    if n is not None:
                        self._log_count = n
                except Exception:
                    pass
        try:
            self.root.after(2000, self._poll_records)
        except Exception:
            pass

    def _on_record_click(self, event):
        """点「已打」那一格 → 切换已打（已打的整行变黄）；双击整行也可以。"""
        try:
            if self.tree.identify_column(event.x) != "#8":
                return
            row = self.tree.identify_row(event.y)
            if row:
                self._toggle_printed(row)
        except Exception:
            pass

    def _on_record_dblclick(self, event):
        try:
            row = self.tree.identify_row(event.y)
            if row:
                self._toggle_printed(row)
        except Exception:
            pass

    def _toggle_printed(self, row):
        """先改界面再写库（写成才保留）；因此点击永远不会"没反应"。"""
        try:
            rid = int(row)                 # 行 iid = 记录 id；新扫的临时行（未入库）忽略
        except Exception:
            self.status_text.set("这条是刚扫的新记录，稍后自动刷新后再点")
            return
        try:
            vals = list(self.tree.item(row, "values"))
            if len(vals) < 8:
                return
            newf = 0 if "已打" in str(vals[7]) else 1
            self._touch_ts = time.time()   # 3 秒内不让定时刷新重建行
            self._apply_printed(row, newf)
            if set_printed(rid, newf):
                self.status_text.set("已标记：%s" % ("已打" if newf else "未打"))
            else:
                self._apply_printed(row, 0 if newf else 1)     # 写失败回滚
                self.status_text.set("「已打」没能写入数据库，请再点一次")
        except Exception:
            pass

    def _apply_printed(self, iid, flag):
        try:
            vals = list(self.tree.item(iid, "values"))
            if len(vals) > 7:
                vals[7] = "【已打】" if flag else "【打单】"
                self.tree.item(iid, values=vals, tags=("printed",) if flag else ())
        except Exception:
            pass

    def reload_records(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        for r in fetch_all_scans():        # 由旧到新逐个插到第一行 → 最新的排在最上面
            pid, st, bc, pq, sh, oc, light = r[:7]
            who = r[7] if len(r) > 7 else ""
            pnum = r[8] if len(r) > 8 else ""
            prn = int(r[9] or 0) if len(r) > 9 else 0
            ok = (light == "绿")
            self.tree.insert("", 0, iid=str(pid),
                             values=(st, bc, pq or 0, sh or 0, oc or 0, who or "（本机扫码）",
                                     pnum, "【已打】" if prn else "【打单】"),
                             tags=("printed",) if prn else (("ok",) if ok else ("alert",)))
        try:
            self.tree.yview_moveto(0)      # 刷新后停在顶部，最新那条一眼能看到
        except Exception:
            pass


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


def _single_instance_guard():
    """单实例保护：同一时间只允许跑一个。

    两个实例会同时抢同一个 SQLite 库（各自全量拉取 + 写库），主线程卡在等锁上时
    界面就不再处理扫码，表现为“扫码没反应”。返回 False 表示已有实例在跑。
    """
    if os.name != "nt":
        return None
    global _INSTANCE_MUTEX
    try:
        import ctypes
        from ctypes import wintypes
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateMutexW.argtypes = [wintypes.LPVOID, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.CreateMutexW.restype = wintypes.HANDLE
        handle = kernel32.CreateMutexW(None, False, "Local\\KuaimaiScanSingleton")
        if not handle:
            return None
        if ctypes.get_last_error() == 183:      # ERROR_ALREADY_EXISTS
            return False
        _INSTANCE_MUTEX = handle                # 持有到进程结束，由系统自动释放
        return handle
    except Exception:
        return None


def main():
    if "--selftest" in sys.argv:
        run_selftest()
        return
    if _single_instance_guard() is False:
        try:
            tip = tk.Tk()
            tip.withdraw()
            messagebox.showwarning(
                "已经在运行",
                "快麦扫码查询已经在运行了。\n\n"
                "请直接用屏幕上已经开着的那个窗口；不要开两个，\n"
                "两个窗口会抢同一个数据库，扫码会没反应。")
            tip.destroy()
        except Exception:
            pass
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
