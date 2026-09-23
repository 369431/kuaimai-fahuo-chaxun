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
    from kuaimai_webui import (WEB_INDEX_HTML, PICK_HTML, ORDER_HTML, STOCK_HTML,
                               STOCKTAKE_HTML, PERMS_HTML, PRINTS_HTML)
    from kuaimai_login_ui import LOGIN_HTML
except Exception:
    WEB_INDEX_HTML = "<h1>缺少 kuaimai_webui.py</h1>"
    PICK_HTML = WEB_INDEX_HTML
    ORDER_HTML = WEB_INDEX_HTML
    STOCK_HTML = WEB_INDEX_HTML
    STOCKTAKE_HTML = WEB_INDEX_HTML
    PERMS_HTML = WEB_INDEX_HTML
    PRINTS_HTML = WEB_INDEX_HTML
    LOGIN_HTML = WEB_INDEX_HTML
try:
    import kuaimai_auth as auth
except Exception:
    auth = None
try:
    import kuaimai_perms as perms      # 网页按钮权限清单（权限键的唯一来源）
except Exception:
    perms = None
try:
    import kuaimai_client as kmclient   # 桌面端登录 / 主-子客户端（会话、局域网发现、远程接口）
except Exception:
    kmclient = None
try:
    from kuaimai_login_window import ask_login   # 桌面端登录窗
except Exception:
    ask_login = None
try:
    import kuaimai_admin_panel          # 主账号的「子客户端管理」面板
except Exception:
    kuaimai_admin_panel = None
try:
    import kuaimai_gateway_ui           # 「对外访问设置」（域名 / frp / 证书）
except Exception:
    kuaimai_gateway_ui = None
try:
    import kuaimai_update as kmupd      # 检查更新（拉 version.json）
except Exception:
    kmupd = None
try:
    import kuaimai_update_ui as kmupdui
except Exception:
    kmupdui = None
try:
    import kuaimai_gateway as kmgw      # 对外访问配置 / 证书 / 隧道启停
except Exception:
    kmgw = None
import kuaimai_db              # 订单缓存 SQLite 存储层（kuaimai_db.py）
try:
    import kuaimai_uikit as uikit       # 后台线程安全地刷界面
except Exception:
    uikit = None
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


WEB_HOLD_DEFAULT = 10          # 网页「可发」的撤回宽限（秒），电脑端可改


def get_web_hold():
    """网页可发的撤回宽限秒数（电脑端设置，网页按这个走）。"""
    try:
        v = int(float((load_settings() or {}).get("web_hold_secs", WEB_HOLD_DEFAULT)))
    except Exception:
        v = WEB_HOLD_DEFAULT
    return max(0, min(600, v))


def set_web_hold(secs):
    try:
        s = load_settings() or {}
        s["web_hold_secs"] = max(0, min(600, int(float(secs))))
        save_settings(s)
    except Exception:
        pass


# ==================== 打印分工（哪个账号由哪台电脑自动打） ====================
# 数据目录里两个文件（都由主端界面写，和 kuaimai_print_jobs.py 的账号映射同一份）：
#   print_clients.json  {"123":"pc1","最帅的男人":"pc2","default":"pc1"}
#       键 = 来源账号（scan_record.who），值 = 电脑名（pc1/pc2/pc3）；
#       "default" = 没单独列出的账号跑哪台；没有 default = 谁都能领（不自动打）。
#   print_client.json   {"client":"pc1"}
#       这台电脑自己的「本机打印身份」（每台电脑各存一份，子端也要设）。
PRINT_CLIENTS_FILE = os.path.join(BASE_DIR, "print_clients.json")
PRINT_CLIENT_FILE = os.path.join(BASE_DIR, "print_client.json")
PRINT_CLIENT_IDS = ("pc1", "pc2", "pc3")           # 可指定的电脑名
PRINT_CLIENT_NONE = "不自动打"                        # 账号行选它 = 不写进映射
PRINT_CLIENT_SELF = "本机"                            # 账号行选它 = 保存时写成上面的「本机打印身份」
PRINT_CLIENT_ROW_OPTS = (PRINT_CLIENT_NONE,) + PRINT_CLIENT_IDS + (PRINT_CLIENT_SELF,)
PRINT_DEFAULT_ROW = "默认（没单独列出的账号）"            # 映射到文件里的 "default"


def load_print_clients():
    """账号 → 电脑 映射（文件不存在/坏掉都当空表）。"""
    d = load_json(PRINT_CLIENTS_FILE, {})
    return dict(d) if isinstance(d, dict) else {}


def save_print_clients(m):
    save_json(PRINT_CLIENTS_FILE, {str(k): str(v) for k, v in (m or {}).items() if k})


def load_print_client():
    """本机是第几台电脑（pc1/pc2/pc3）；没有/不合法就默认 pc1。子端也读这个。"""
    d = load_json(PRINT_CLIENT_FILE, {})
    c = str((d or {}).get("client") or "").strip() if isinstance(d, dict) else ""
    return c if c in PRINT_CLIENT_IDS else PRINT_CLIENT_IDS[0]


def save_print_client(name):
    name = str(name or "").strip()
    if name not in PRINT_CLIENT_IDS:
        return "只能选 pc1 / pc2 / pc3"
    save_json(PRINT_CLIENT_FILE, {"client": name})
    return ""


def read_local_print_client():
    """本机打印身份：只有 print_client.json **明确设过**才返回，否则返回 ''。

    和 load_print_client() 的区别：后者没设也默认 pc1（界面显示用），
    而「认领任务」必须没设就不认领（否则子端会误领 pc1 的单），所以单独一个。
    """
    try:
        d = load_json(PRINT_CLIENT_FILE, {})
    except Exception:
        return ""
    c = str((d or {}).get("client") or "").strip() if isinstance(d, dict) else ""
    return c if c in PRINT_CLIENT_IDS else ""


def print_jobs_log(msg):
    """打单任务留痕：写进和自动打单同一个 auto_print.log（便于排查）。"""
    line = "%s  [任务] %s" % (time.strftime("%m-%d %H:%M:%S"), msg)
    try:
        with open(os.path.join(BASE_DIR, "auto_print.log"), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    try:
        print(line, flush=True)
    except Exception:
        pass


def print_account_names():
    """要分工的账号 = 扫码记录里出现过的扫码账号 ∪ 账号模块里的用户（取并集）。"""
    out = []
    try:
        conn = sqlite3.connect(DB_FILE, timeout=10)
        try:
            for r in conn.execute("SELECT DISTINCT who FROM scan_record "
                                  "WHERE COALESCE(who,'')<>'' ORDER BY who"):
                w = str(r[0] or "").strip()
                if w and w not in out:
                    out.append(w)
        finally:
            conn.close()
    except Exception:
        pass
    try:
        if auth is not None:
            for u in auth.list_users():
                n = str((u or {}).get("name") or "").strip()
                if n and n not in out:
                    out.append(n)
    except Exception:
        pass
    return out


# ============================ 打单进度面板 ============================
# 数据来源（都已存在，只读不写）：
#   1) print_jobs 任务表（scan_log.db）→ stats() 的 live{printing,queue,failed} + recent
#   2) print_progress.json（kuaimai_print.py 打单链路的实时上报）
#   3) auto_print.log 尾部（认领/打印日志，认领模式也写这里）
PROGRESS_FILE = os.path.join(BASE_DIR, "print_progress.json")
AUTO_PRINT_LOG = os.path.join(BASE_DIR, "auto_print.log")
PROGRESS_PHASE_HINT = {
    "开始": "开始打单", "挑单": "挑单", "取号": "取号", "设每页": "设每页显示",
    "扫描勾选": "逐屏扫描勾选", "点打印": "点打印", "核对": "打印后核对",
    "完成": "完成", "失败": "失败",
}
PROGRESS_STATUS_CN = {"pending": "排队中", "claimed": "打印中", "printing": "打印中",
                      "done": "已完成", "failed": "失败"}


def read_print_progress():
    """读 print_progress.json（打单链路写的进度快照）；读不到返回 {}。"""
    for p in (PROGRESS_FILE,
              os.path.join(os.environ.get("LOCALAPPDATA") or "", "KuaimaiScan",
                           "print_progress.json")):
        if not p:
            continue
        try:
            if os.path.isfile(p):
                with open(p, encoding="utf-8") as f:
                    d = json.load(f)
                if isinstance(d, dict):
                    return d
        except Exception:
            pass
    return {}


def read_log_tail(n=5):
    """auto_print.log 尾部 n 行（认领/打印都写这里）。"""
    try:
        with open(AUTO_PRINT_LOG, encoding="utf-8", errors="replace") as f:
            lines = [x.rstrip() for x in f.read().splitlines()]
        lines = [x for x in lines if x.strip()]
        return lines[-int(n):] if n else lines
    except Exception:
        return []


AUTO_PUTAWAY_LOG = os.path.join(BASE_DIR, "auto_putaway.log")
AUTO_AUDIT_LOG = os.path.join(BASE_DIR, "auto_audit.log")


def read_auto_ops_tail(n=8):
    """自动上架 / 智能审核日志尾部 n 行（两个文件合并，按时间排）。

    两个日志都落在同一个数据目录：auto_putaway.log（上架）、auto_audit.log（审核）。
    行首都是「MM-DD HH:MM:SS」→ 各自取尾部后拼一起再按时间排序。
    没跑过就是还没生成文件，**不算错**（返回空，界面显示「暂无日志」）。
    """
    merged = []
    for tag, p in (("上架", AUTO_PUTAWAY_LOG), ("审核", AUTO_AUDIT_LOG)):
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                lines = [x.rstrip() for x in f.read().splitlines()]
        except Exception:
            continue
        for ln in [x for x in lines if x.strip()][-int(n):]:
            merged.append((ln[:14], "[%s] %s" % (tag, ln)))
    merged.sort(key=lambda t: t[0])
    return [x[1] for x in merged[-int(n):]]


def _fmt_elapsed(sec):
    sec = int(sec or 0)
    if sec < 60:
        return "%d 秒" % sec
    if sec < 3600:
        return "%d 分 %d 秒" % (sec // 60, sec % 60)
    return "%d 时 %d 分" % (sec // 3600, (sec % 3600) // 60)


def print_progress_payload():
    """面板数据：print_jobs.stats()（真库，几十行）+ 进度 JSON + 日志尾部。

    只读、轻量（主线程直查没问题）；出错不抛，返回 ok=False + err。
    """
    out = {"ok": True, "err": "", "progress": read_print_progress(), "log": read_log_tail(5),
           "auto_log": read_auto_ops_tail(8),
           "live": {"printing": [], "queue": [], "done": [], "failed": [], "counts": {}},
           "recent": []}
    try:
        import kuaimai_print_jobs as pj
        conn = sqlite3.connect(DB_FILE, timeout=10)
        try:
            conn.row_factory = sqlite3.Row
            st = pj.stats(conn)
        finally:
            conn.close()
        lv = st.get("live") or {}
        out["live"] = {"printing": lv.get("printing") or [], "queue": lv.get("queue") or [],
                       "done": lv.get("done") or [], "failed": lv.get("failed") or [],
                       "counts": lv.get("counts") or {}}
        out["recent"] = st.get("recent") or []
    except Exception as e:
        out["ok"] = False
        out["err"] = str(e)[:200]
    return out


def print_jobs_delete(ids=None, status=None):
    """删打单任务（本机权威库 scan_log.db）：按 id 列表 / 按状态（如 failed）。

    返回删除条数；两个都没给 → 0（不删任何东西）。只动 print_jobs，不碰别的表。
    """
    import kuaimai_print_jobs as pj
    conn = sqlite3.connect(DB_FILE, timeout=10)
    try:
        return int(pj.delete_jobs(conn, ids=ids, status=status) or 0)
    finally:
        conn.close()


def format_progress(payload, now=None):
    """把 payload 变成面板要显示的文字（纯函数，便于桩对象断言）。"""
    now = time.time() if now is None else float(now)
    payload = payload or {}
    lv = payload.get("live") or {}
    pg = payload.get("progress") or {}
    printing = lv.get("printing") or []
    queue = lv.get("queue") or []
    done = lv.get("done") or []
    failed = lv.get("failed") or []
    recent = payload.get("recent") or []

    # —— 正在打印（大字：编码 ×数量、哪台电脑、已用时）——
    if printing:
        p = printing[0]
        big = "%s ×%s  @%s  已用时 %s" % (p.get("code") or "?", p.get("qty") or 0,
                                        p.get("claimed_by") or "?",
                                        _fmt_elapsed(p.get("elapsed")))
    else:
        big = "（当前没有正在打的任务）"

    # —— 阶段行（print_progress.json 的 phase / checked / want）——
    phase = str(pg.get("phase") or "")
    checked, want = pg.get("checked"), pg.get("want")
    bits = []
    if phase:
        bits.append(PROGRESS_PHASE_HINT.get(phase, phase))
        if checked is not None and want:
            bits.append("已勾 %s/%s" % (checked, want))
        elif checked is not None:
            bits.append("已勾 %s" % checked)
        if pg.get("page"):
            bits.append("第 %s 屏" % pg.get("page"))
    else:
        bits.append("（还没有打单进度上报）")
    line = " ".join(str(b) for b in bits if str(b))
    if pg.get("msg"):
        line += " ｜ " + str(pg.get("msg"))
    if pg.get("ok") is True:
        line += " ｜ 结果：成功"
    elif pg.get("ok") is False:
        line += " ｜ 结果：失败"

    # —— 排队中 ——
    q_lines = []
    for q in queue:
        s = "#%s %s ×%s → %s" % (q.get("job_id"), q.get("code") or "?", q.get("qty") or 0,
                                 q.get("client") or q.get("target_client") or "未指派(不自动打)")
        if q.get("retrying"):
            s += "（重试中，已失败 %s 次）" % (q.get("tries") or 0)
        if q.get("last_msg"):
            s += " ｜ %s" % str(q.get("last_msg"))[:90]
        q_lines.append(s)

    # —— 打印完成（运单号 + 完成时间；打完了就不再算「排队中」）——
    d_lines = []
    for q in done:
        ts = q.get("done_ts")
        try:
            when = time.strftime("%m-%d %H:%M:%S", time.localtime(int(ts))) if ts else ""
        except Exception:
            when = str(ts or "")
        s = "#%s %s ×%s" % (q.get("job_id"), q.get("code") or "?", q.get("qty") or 0)
        if q.get("out_sid"):
            s += " ｜ 运单号 %s" % q.get("out_sid")
        if when:
            s += " ｜ %s" % when
        d_lines.append(s)

    # —— 失败 ——
    f_lines = []
    for q in failed:
        s = "#%s %s ×%s" % (q.get("job_id"), q.get("code") or "?", q.get("qty") or 0)
        if q.get("last_msg"):
            s += " ｜ 原因：%s" % str(q.get("last_msg"))[:140]
        f_lines.append(s)

    # —— 最近结果（前 8 条）——
    rows = []
    keys = []
    for r in recent[:8]:
        rows.append(("#%s" % r.get("job_id"), str(r.get("code") or ""), str(r.get("qty") or 0),
                     PROGRESS_STATUS_CN.get(str(r.get("status")), str(r.get("status") or "")),
                     str(r.get("claimed_by") or r.get("target_client") or "-"),
                     str(r.get("out_sid") or ""), str(r.get("last_msg") or "")))
        keys.append({"job_id": r.get("job_id"), "status": str(r.get("status") or ""),
                     "code": str(r.get("code") or ""), "qty": r.get("qty") or 0})

    return {"printing_big": big, "printing_phase": line,
            "queue_title": "排队中（%d）" % len(queue),
            "queue_text": "\n".join(q_lines) if q_lines else "（队列里没有待打任务）",
            "done_title": "打印完成（%d）" % len(done),
            "done_text": "\n".join(d_lines) if d_lines else "（暂无）",
            "failed_title": "失败（%d）" % len(failed),
            "failed_text": "\n".join(f_lines) if f_lines else "（没有失败任务）",
            "recent_rows": rows,
            "recent_keys": keys,
            "log_text": "\n".join(payload.get("log") or []) or "（暂无日志）",
            "auto_log_text": "\n".join(payload.get("auto_log") or [])
                             or "（暂无上架/审核日志）",
            "updated": "更新于 %s（每 1.5 秒自动刷新）"
                       % time.strftime("%H:%M:%S", time.localtime(now))}


class PrintProgressDialog(object):
    """「打单进度」实时面板（**新增** Toplevel，不动主界面既有布局）。

    · 每 1.5 秒自动刷新（Toplevel.after 自循环，关窗即停；**不在后台线程碰控件**）；
    · 数据在主线程读（print_jobs 只有几十行，SQLite 查询轻量）；
    · app 只要提供 root / status_text 就行（测试传桩对象即可）；
    · payload_fn 可注入（桩对象验证用）。
    """

    def __init__(self, app, parent=None, payload_fn=None, delete_fn=None):
        self.app = app
        self.payload_fn = payload_fn or print_progress_payload
        self.delete_fn = delete_fn                 # None → 用 self._delete_ids（自检可注入桩）
        self._rows = {}
        self._after = None
        _parent = parent if parent is not None else getattr(app, "root", None)
        self.win = tk.Toplevel(_parent)
        self.win.title("打单进度（实时）")
        # parent 还藏着（如登录窗）时**不要** transient：owner 不可见 → 子窗口也不显示
        try:
            if _parent is not None and _parent.winfo_viewable():
                self.win.transient(_parent)
        except Exception:
            pass
        self.win.geometry("820x600")
        self.win.minsize(640, 420)
        self._build()
        self.refresh()
        self._schedule()
        try:
            self.win.deiconify()
            self.win.lift()
        except Exception:
            pass
        self.win.protocol("WM_DELETE_WINDOW", self.close)

    def _build(self):
        frm = ttk.Frame(self.win, padding=10)
        frm.pack(fill=tk.BOTH, expand=True)

        # 底部按钮**先**占位：中间内容再长也不会把按钮挤出可视区
        btns = ttk.Frame(frm)
        btns.pack(side=tk.BOTTOM, fill="x", pady=(8, 0))
        ttk.Button(btns, text="关闭", command=self.close).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btns, text="立即刷新", command=self.refresh).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btns, text="打开数据目录", command=self._open_dir).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btns, text="清空失败任务", command=self.on_clear_failed).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btns, text="删除选中任务", command=self.on_delete_selected).pack(side=tk.RIGHT, padx=4)
        # 暂停/恢复「自动打单」（与主界面勾选框、监听线程同一个 flag 文件）
        self.btn_pause = ttk.Button(btns, text="暂停自动打单", command=self.on_toggle_pause)
        self.btn_pause.pack(side=tk.RIGHT, padx=4)
        self.lbl_updated = ttk.Label(btns, text="", foreground="#6e6e73")
        self.lbl_updated.pack(side=tk.LEFT)

        # 底部：实时日志尾部（在按钮上面）
        logbox = ttk.LabelFrame(frm, text="实时日志（auto_print.log 尾部）")
        logbox.pack(side=tk.BOTTOM, fill="x", pady=(8, 0))
        self.log_text = tk.Text(logbox, height=5, wrap="none", font=("Consolas", 9),
                                background="#F7F7F8")
        self.log_text.pack(fill="x", padx=6, pady=4)
        self.log_text.configure(state="disabled")

        # 自动上架 / 智能审核日志（两个文件合并尾部，同样是只读快照）
        autobox = ttk.LabelFrame(
            frm, text="自动上架 / 智能审核日志（auto_putaway.log + auto_audit.log 尾部）")
        autobox.pack(side=tk.BOTTOM, fill="x", pady=(8, 0))
        self.auto_log_text = tk.Text(autobox, height=6, wrap="none", font=("Consolas", 9),
                                     background="#F7F7F8")
        self.auto_log_text.pack(fill="x", padx=6, pady=4)
        self.auto_log_text.configure(state="disabled")

        # 正在打印（大字）
        top = ttk.LabelFrame(frm, text="正在打印")
        top.pack(side=tk.TOP, fill="x")
        self.lbl_printing = tk.Label(top, text="", font=("Microsoft YaHei", 15, "bold"),
                                     fg="#0b5394", bg=UI_BG, justify="left", anchor="w")
        self.lbl_printing.pack(fill="x", padx=8, pady=(6, 0))
        self.lbl_phase = ttk.Label(top, text="", foreground="#333333", justify="left")
        self.lbl_phase.pack(fill="x", padx=8, pady=(2, 8))

        # 排队中
        qbox = ttk.LabelFrame(frm, text="排队中")
        qbox.pack(side=tk.TOP, fill="x", pady=(8, 0))
        self.lbl_queue_title = ttk.Label(qbox, text="", font=("Microsoft YaHei", 11, "bold"))
        self.lbl_queue_title.pack(anchor="w", padx=8, pady=(4, 0))
        self.lbl_queue = ttk.Label(qbox, text="", justify="left")
        self.lbl_queue.pack(fill="x", padx=8, pady=(0, 6))

        # 打印完成（打完了就不再显示在「排队中」；这里可查运单号 + 完成时间）
        dbox = ttk.LabelFrame(frm, text="打印完成")
        dbox.pack(side=tk.TOP, fill="x", pady=(8, 0))
        self.lbl_done_title = ttk.Label(dbox, text="", font=("Microsoft YaHei", 11, "bold"))
        self.lbl_done_title.pack(anchor="w", padx=8, pady=(4, 0))
        self.lbl_done = ttk.Label(dbox, text="", justify="left")
        self.lbl_done.pack(fill="x", padx=8, pady=(0, 6))

        # 失败
        fbox = ttk.LabelFrame(frm, text="失败")
        fbox.pack(side=tk.TOP, fill="x", pady=(8, 0))
        self.lbl_failed_title = ttk.Label(fbox, text="", font=("Microsoft YaHei", 11, "bold"))
        self.lbl_failed_title.pack(anchor="w", padx=8, pady=(4, 0))
        self.lbl_failed = ttk.Label(fbox, text="", justify="left")
        self.lbl_failed.pack(fill="x", padx=8, pady=(0, 6))

        # 最近结果
        rbox = ttk.LabelFrame(frm, text="最近结果")
        rbox.pack(side=tk.TOP, fill=tk.BOTH, expand=True, pady=(8, 0))
        cols = ("job", "code", "qty", "status", "client", "sid", "msg")
        self.tree = ttk.Treeview(rbox, columns=cols, show="headings", height=6,
                                 selectmode="extended")
        for c, t, w in (("job", "任务号", 70), ("code", "编码", 150), ("qty", "数量", 55),
                        ("status", "状态", 70), ("client", "哪台电脑", 80),
                        ("sid", "运单号", 130), ("msg", "失败原因/备注", 240)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="w")
        self.tree.pack(fill=tk.BOTH, expand=True, padx=6, pady=4)

    def _open_dir(self):
        try:
            os.startfile(BASE_DIR)
        except Exception:
            pass

    # ---------- 删除任务（新增）----------
    def _who(self):
        """当前登录账号名（写日志用）；拿不到就当「本机」。"""
        try:
            n = str(getattr(getattr(self.app, "session", None), "name", "") or "")
            if n:
                return n
            return str((getattr(self.app, "me", None) or {}).get("name") or "") or "本机"
        except Exception:
            return "本机"

    def _sel_jobs(self):
        """当前选中的任务：[{job_id,status,code,qty,iid}]（支持多选）。"""
        try:
            sels = list(self.tree.selection())
        except Exception:
            sels = []
        out = []
        for iid in sels:
            info = dict(self._rows.get(iid) or {})
            if info.get("job_id") is None:
                try:
                    info["job_id"] = int(str(iid).lstrip("#"))
                except Exception:
                    continue
            info["iid"] = iid
            out.append(info)
        return out

    def _delete_ids(self, ids):
        """删任务：子端走主端接口，主端直接改本地库。返回 (ok, msg)。"""
        ids = [int(i) for i in (ids or []) if i is not None]
        if not ids:
            return True, "没有要删的任务"
        if getattr(self.app, "remote", False):
            try:
                ok, res = self.app._remote_api("/api/print/jobs_del", "POST",
                                               body={"ids": ids}, timeout=30)
            except Exception as e:
                return False, "主客户端请求失败：%s" % str(e)[:120]
            if not ok or not isinstance(res, dict):
                return False, "主客户端没返回结果"
            if not res.get("ok"):
                return False, str(res.get("error") or "主客户端拒绝删除")
            return True, "已删除 %s 条" % res.get("deleted")
        try:
            return True, "已删除 %s 条" % print_jobs_delete(ids=ids)
        except Exception as e:
            return False, "删除失败：%s" % str(e)[:120]

    def _note_delete(self, jobs, msg):
        for j in jobs:
            print_jobs_log("删除 #%s %s ×%s（%s 删的）"
                           % (j.get("job_id"), j.get("code") or "?", j.get("qty") or 0,
                              self._who()))
        try:
            self.app.status_text.set(msg)
        except Exception:
            pass

    def on_delete_selected(self):
        """删除列表里选中的任务（可多选）；正在打印的默认拦一下。"""
        jobs = self._sel_jobs()
        if not jobs:
            messagebox.showinfo("删除任务",
                                "先在下面「最近结果」里选中要删的任务（按住 Ctrl 可多选）。")
            return
        busy = [j for j in jobs if str(j.get("status") or "") in ("claimed", "printing")]
        detail = "\n".join("  #%s  %s ×%s%s" % (j.get("job_id"), j.get("code") or "?",
                                            j.get("qty") or 0,
                                            "（正在打印中）" if j in busy else "")
                          for j in jobs)
        if busy:
            if not messagebox.askyesno("正在打印中",
                                       "选中的任务里有 %d 条正在打印：\n\n%s\n\n"
                                       "正在打印中，先暂停再删（若坚持要删可再确认）。\n仍要删除吗？"
                                       % (len(busy), detail)):
                return
        elif not messagebox.askyesno("删除任务",
                                     "确定删除下面 %d 条任务吗？\n\n%s\n\n（删了就没了，不能撤销）"
                                     % (len(jobs), detail)):
            return
        ids = [j["job_id"] for j in jobs if j.get("job_id") is not None]
        fn = self.delete_fn or self._delete_ids
        ok, msg = fn(ids)
        if not ok:
            messagebox.showerror("删除任务", str(msg))
            return
        self._note_delete(jobs, "已删除 %d 条任务（%s）" % (len(ids), msg))
        self.refresh()

    def on_toggle_pause(self):
        """暂停 / 恢复「网页提交后自动打单」（与主界面勾选框、监听线程同一个 flag 文件）。

        暂停期间监听线程**不认领新任务**（正在打的那一单会打完）；恢复即继续认领。
        """
        from tkinter import messagebox
        p = auto_print_pause_flag()
        try:
            if os.path.isfile(p):
                os.remove(p)
                msg = "已恢复自动打单：监听会继续认领新任务"
            else:
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "w", encoding="utf-8") as f:
                    f.write("paused")
                msg = "已暂停自动打单：不再认领新任务（正在打的那单会打完）"
        except Exception as e:
            messagebox.showerror("自动打单", "切换失败：%s" % str(e)[:120])
            return
        try:
            self.lbl_updated.config(text=msg)
        except Exception:
            pass
        self.refresh()

    def on_clear_failed(self):
        """一次删掉所有 failed 任务（删前确认）。"""
        try:
            payload = self.payload_fn() or {}
        except Exception:
            payload = {}
        failed = ((payload.get("live") or {}).get("failed") or [])
        detail = "\n".join("  #%s  %s ×%s" % (j.get("job_id"), j.get("code") or "?",
                                             j.get("qty") or 0) for j in failed[:12])
        if not messagebox.askyesno("清空失败任务",
                                   "确定删掉全部「失败」任务吗？（当前 %d 条）\n\n%s\n\n"
                                   "（删了就没了，不能撤销）" % (len(failed), detail or "（列表为空）")):
            return
        fn = self.delete_fn
        if fn is not None:                          # 注入桩：自己决定怎么删
            ok, msg = fn([])
            if not ok:
                messagebox.showerror("删除任务", str(msg))
                return
        elif getattr(self.app, "remote", False):   # 子端：走主端接口按状态删
            try:
                ok, res = self.app._remote_api("/api/print/jobs_del", "POST",
                                               body={"status": "failed"}, timeout=30)
            except Exception as e:
                messagebox.showerror("删除任务", "主客户端请求失败：%s" % str(e)[:120])
                return
            if not ok or not isinstance(res, dict) or not res.get("ok"):
                messagebox.showerror("删除任务", "主客户端没删成：%s"
                                     % (res.get("error") if isinstance(res, dict) else res))
                return
        else:
            try:
                print_jobs_delete(status="failed")
            except Exception as e:
                messagebox.showerror("删除任务", "删除失败：%s" % str(e)[:120])
                return
        print_jobs_log("清空失败任务 %d 条（%s 删的）" % (len(failed), self._who()))
        try:
            self.app.status_text.set("已清空失败任务")
        except Exception:
            pass
        self.refresh()

    # ---------- 刷新 ----------
    def refresh(self):
        try:
            payload = self.payload_fn()
        except Exception as e:
            payload = {"ok": False, "err": str(e)[:200]}
        d = format_progress(payload)
        try:
            self.lbl_printing.config(text=d["printing_big"])
            self.lbl_phase.config(text=d["printing_phase"])
            self.lbl_queue_title.config(text=d["queue_title"])
            self.lbl_queue.config(text=d["queue_text"])
            self.lbl_done_title.config(text=d["done_title"])
            self.lbl_done.config(text=d["done_text"])
            self.lbl_failed_title.config(text=d["failed_title"])
            self.lbl_failed.config(text=d["failed_text"])
            for iid in self.tree.get_children():
                self.tree.delete(iid)
            self._rows = {}
            keys = d.get("recent_keys") or []
            for i, row in enumerate(d["recent_rows"]):
                iid = str(row[0])
                try:
                    self.tree.insert("", "end", iid=iid, values=row)
                except Exception:
                    iid = ""
                    self.tree.insert("", "end", values=row)
                if iid:
                    self._rows[iid] = (keys[i] if i < len(keys) else {})
            self.log_text.configure(state="normal")
            self.log_text.delete("1.0", "end")
            self.log_text.insert("1.0", d["log_text"])
            self.log_text.configure(state="disabled")
            self.auto_log_text.configure(state="normal")
            self.auto_log_text.delete("1.0", "end")
            self.auto_log_text.insert("1.0", d.get("auto_log_text") or "（暂无上架/审核日志）")
            self.auto_log_text.configure(state="disabled")
            note = d["updated"]
            if not (payload or {}).get("ok", True):
                note += "  ｜ 读取失败：%s" % (payload.get("err") or "")
            self.lbl_updated.config(text=note)
            try:                                   # 暂停按钮文案跟随当前状态
                self.btn_pause.config(text=("恢复自动打单" if os.path.isfile(auto_print_pause_flag())
                                            else "暂停自动打单"))
            except Exception:
                pass
        except Exception:
            pass

    def _schedule(self):
        try:
            self._after = self.win.after(1500, self._tick)
        except Exception:
            self._after = None

    def _tick(self):
        self._after = None
        try:
            if not self.win.winfo_exists():
                return
        except Exception:
            return
        self.refresh()
        self._schedule()

    def close(self):
        """关窗：先停定时刷新，再销毁（不留 root.after 回调）。"""
        try:
            if self._after:
                self.win.after_cancel(self._after)
        except Exception:
            pass
        self._after = None
        try:
            self.win.destroy()
        except Exception:
            pass


class PrintClientsDialog(object):
    """「打印分工」设置窗（**新增** Toplevel，不动主界面既有 grid 布局）。

    · 账号 → 哪台电脑（只主端能改；子端打开时那一块置灰并提示"只能在主端设置"）；
    · 本机打印身份 pc1/pc2/pc3（哪一端都能改，每台电脑各存一份 print_client.json）。

    app 只要提供 root / remote / status_text 就行（测试时传桩对象即可）。
    """

    def __init__(self, app, parent=None):
        self.app = app
        self.remote = bool(getattr(app, "remote", False))
        self.rows = []                       # [(账号名, StringVar, 下拉控件)]
        _parent = parent if parent is not None else getattr(app, "root", None)
        self.win = tk.Toplevel(_parent)
        self.win.title("打印分工（哪个账号由哪台电脑自动打）")
        try:
            self.win.transient(_parent)
        except Exception:
            pass
        self.win.resizable(False, False)
        self._build()

    # ---------- 组装界面 ----------
    def _build(self):
        frm = ttk.Frame(self.win, padding=12)
        frm.pack(fill=tk.BOTH, expand=True)
        frm.columnconfigure(0, weight=1)

        # —— 账号分工（只有主端能改）——
        box = ttk.LabelFrame(frm, text="账号 → 哪台电脑自动打（「不自动打」的账号不写进文件）")
        box.grid(row=0, column=0, sticky="ew")
        box.columnconfigure(1, weight=1)
        cur = load_print_clients()
        local = load_print_client()
        names = print_account_names()
        r = 0
        if not names:
            ttk.Label(box, text="（还没有账号：扫码记录和账号模块里都没有）",
                      foreground="#8e8e93").grid(row=r, column=0, columnspan=2,
                                                sticky="w", padx=8, pady=6)
            r += 1
        for nm in names:
            ttk.Label(box, text=nm).grid(row=r, column=0, sticky="w", padx=(8, 10), pady=3)
            v = tk.StringVar(value=str(cur.get(nm) or PRINT_CLIENT_NONE))
            cb = ttk.Combobox(box, textvariable=v, values=PRINT_CLIENT_ROW_OPTS,
                              width=14, state="readonly")
            cb.grid(row=r, column=1, sticky="w", padx=(0, 8), pady=3)
            self.rows.append((nm, v, cb))
            r += 1
        # 「默认」行：文件里的 default（会写进 print_clients.json）
        ttk.Label(box, text=PRINT_DEFAULT_ROW).grid(row=r, column=0, sticky="w",
                                                    padx=(8, 10), pady=3)
        dv = tk.StringVar(value=str(cur.get("default") or PRINT_CLIENT_NONE))
        dcb = ttk.Combobox(box, textvariable=dv, values=PRINT_CLIENT_ROW_OPTS,
                           width=14, state="readonly")
        dcb.grid(row=r, column=1, sticky="w", padx=(0, 8), pady=3)
        self.default_var = dv
        self.default_cb = dcb
        self.rows.append((PRINT_DEFAULT_ROW, dv, dcb))
        r += 1
        self.perm_note = None
        if self.remote:
            # 子端：账号分工只能在主端改，这里只读（置灰）+ 明确提示
            self.perm_note = ttk.Label(
                box, text="本机的账号分工只能在主端设置（这边只能改下面的「本机打印身份」）",
                foreground="#c62828")
            self.perm_note.grid(row=r, column=0, columnspan=2, sticky="w", padx=8, pady=(4, 6))
            r += 1
            for _nm, _v, _cb in self.rows:
                try:
                    _cb.state(["disabled"])
                except Exception:
                    pass

        # —— 本机打印身份（每台电脑各一份）——
        idbox = ttk.LabelFrame(frm, text="本机打印身份（这台电脑是 pc1 / pc2 / pc3）")
        idbox.grid(row=1, column=0, sticky="ew", pady=(8, 0))
        ttk.Label(idbox, text="这台电脑").grid(row=0, column=0, sticky="w", padx=(8, 10), pady=6)
        self.local_var = tk.StringVar(value=local)
        ttk.Combobox(idbox, textvariable=self.local_var, values=PRINT_CLIENT_IDS,
                     width=14, state="readonly").grid(row=0, column=1, sticky="w", pady=6)
        ttk.Label(idbox, text="（保存后立即生效，不用重启）", foreground="#8e8e93").grid(
            row=0, column=2, sticky="w", padx=8)

        ttk.Label(frm, foreground="#6e6e73", justify="left",
                  text=("「本机」= 这台电脑（保存时写成上面的本机打印身份）。\n"
                        "「不自动打」的账号：网页点「可发」也**不会推送到任何电脑**（最安全）。\n"
                        "账号分工：%s\n本机身份：%s" % (PRINT_CLIENTS_FILE, PRINT_CLIENT_FILE))
                  ).grid(row=2, column=0, sticky="w", pady=(8, 0))

        btns = ttk.Frame(frm)
        btns.grid(row=3, column=0, sticky="e", pady=(10, 0))
        ttk.Button(btns, text="保存", command=self.on_save, style="Accent.TButton").pack(
            side=tk.LEFT, padx=4)
        ttk.Button(btns, text="取消", command=self.win.destroy).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="打开数据目录", command=self._open_dir).pack(side=tk.LEFT, padx=4)
        try:
            self.win.grab_set()
        except Exception:
            pass

    def _open_dir(self):
        try:
            os.startfile(BASE_DIR)
        except Exception:
            pass

    def _status(self, msg):
        try:
            self.app.status_text.set(msg)
        except Exception:
            pass

    # ---------- 保存 ----------
    def collect_accounts(self):
        """把界面上的选择收成映射表（含「不自动打」）。

        ★ 「不自动打」必须**明确写进文件**，不能像以前那样跳过 —— 跳过等于文件里没这个
          账号，取用时就可能落回「默认」那台电脑，于是网页点「可发」照样推送（用户报的不安全点）。
          写进去后 client_for 认得出「这个账号明确不自动打」→ 直接不派发、不落回 default。
          「本机」写成当前本机打印身份。
        """
        local = str(self.local_var.get() or "").strip() or load_print_client()
        m = {}
        for nm, var, _cb in self.rows:
            key = "default" if nm == PRINT_DEFAULT_ROW else nm
            v = str(var.get() or "").strip()
            if not v or v == PRINT_CLIENT_NONE:
                m[key] = PRINT_CLIENT_NONE          # 明确「不自动打」（不派发、不落回 default）
                continue
            if v == PRINT_CLIENT_SELF:
                v = local
            m[key] = v
        return m

    def on_save(self):
        err = save_print_client(self.local_var.get())
        if err:
            messagebox.showerror("保存失败", err, parent=self.win)
            return
        if not self.remote:
            try:
                save_print_clients(self.collect_accounts())
            except Exception as e:
                messagebox.showerror("保存失败", str(e)[:200], parent=self.win)
                return
            self._status("打印分工已保存（%s）；本机身份 %s"
                         % (PRINT_CLIENTS_FILE, self.local_var.get()))
        else:
            self._status("本机打印身份已保存：%s（账号分工只能在主端改）" % self.local_var.get())
        try:
            self.win.destroy()
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


def delete_pending_canprint(code):
    """撤回想「可发」写的记录 → 电脑端不再显示（已打印的、桌面自己扫的都不动）。返回删了几条。"""
    try:
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("ALTER TABLE scan_record ADD COLUMN hold_until INTEGER DEFAULT 0")
        conn.commit()
    except Exception:
        pass
    try:
        cur = conn.cursor()
        cur.execute("DELETE FROM scan_record WHERE barcode=? AND COALESCE(printed,0)=0 "
                    "AND COALESCE(hold_until,0) > 0", (str(code),))
        gone = cur.rowcount
        conn.commit()
        conn.close()
        return int(gone or 0)
    except Exception:
        try:
            conn.close()
        except Exception:
            pass
        return 0


def insert_canprint(code, qty, who="", bins="", pending_qty=0, shelf_qty=0, hold_secs=0):
    """网页现货可发点「可发」并输入数量 → 写一条扫码日志，可打单数量 = 输入的数量。"""
    conn = get_conn()
    cur = conn.cursor()
    for stmt in ("ALTER TABLE scan_record ADD COLUMN who TEXT",
                 "ALTER TABLE scan_record ADD COLUMN print_num TEXT",
                 "ALTER TABLE scan_record ADD COLUMN printed INTEGER DEFAULT 0",
                 "ALTER TABLE scan_record ADD COLUMN hold_until INTEGER DEFAULT 0"):
        try:
            cur.execute(stmt)
        except Exception:
            pass
    cur.execute(
        "INSERT INTO scan_record(scan_time,barcode,order_no,goods_name,status,pending_qty,shelf_qty,orders_count,who,print_num,printed,hold_until)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,0,?)",
        (now_gmt8(), str(code), "", str(bins or ""), "可", int(pending_qty or 0), int(shelf_qty or 0), 0,
         str(who or ""), str(int(qty)), int(time.time()) + int(hold_secs or 0)),
    )
    conn.commit()
    conn.close()


def _printed_mark_log(msg):
    """「已打」标记审计：谁在什么时机标的 → printed_mark.log（失败不影响主流程）。

    `printed` 只是「人已确认出纸」的人为标记；这份日志专门用来一眼看出
    **有没有自动链路偷偷写它**（自动链路永远不该出现在这里）。
    """
    line = "%s  [已打] %s" % (now_gmt8(), msg)
    try:
        with open(os.path.join(BASE_DIR, "printed_mark.log"), "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass
    try:
        print(line, flush=True)
    except Exception:
        pass


def set_printed(rec_id, flag, by=""):
    """把某条扫码日志标成「已打」（1）/ 未打（0）。返回是否写成功。

    ★ 语义约束（用户口径）：`printed` 是「人工确认出纸」的标记，
      **只有人工确认路径**可以调它：
        ① 电脑端扫码记录里点「已打」那一格（本地，或经 /api/scans/printed 的远端）；
        ② 子客户端同样的动作（也走 /api/scans/printed）。
      **建打单任务 / 认领任务 / 打印成功或失败 / 回写任务结果等自动链路一律不得写它**：
      排进队列 ≠ 打了纸；自动链路只写 print_jobs（任务表）与 printed_memory.json（去重记忆）。

      防回归：必须显式传 `by`（来源说明）。不传 → 拒绝写入并记日志（fail-safe），
      避免日后有人又在 add_job / claim / report 里顺手调它。
    """
    by = str(by or "").strip()
    if not by:
        _printed_mark_log("!! 拒绝写入 id=%r flag=%r：调用方没给来源（by）"
                          "—— 自动链路不允许写 scan_record.printed" % (rec_id, flag))
        return False
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
                _printed_mark_log("标记 id=%s → %s（来源 %s）" % (int(rec_id), want, by))
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
                 "ALTER TABLE scan_record ADD COLUMN printed INTEGER DEFAULT 0",
                 "ALTER TABLE scan_record ADD COLUMN hold_until INTEGER DEFAULT 0"):
        try:
            cur.execute(stmt)
            conn.commit()
        except Exception:
            pass
    rows = cur.execute(
        "SELECT id,scan_time,barcode,pending_qty,shelf_qty,orders_count,status,COALESCE(who,''),"
        "COALESCE(print_num,''),COALESCE(printed,0) FROM scan_record "
        "WHERE COALESCE(hold_until,0) <= ? ORDER BY id ASC", (int(time.time()),)
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


# 只统计这两家的加急（用户要求）
URGENT_EXPRESS_KEYS = ("中通", "申通")
URGENT_EXPRESS_CODES = ("ZTO", "STO", "ZHONGTONG", "SHENTONG")


def _urgent_express(name):
    """快递名 → 是否属于要统计的两家（返回规范名或 ""）。"""
    s = str(name or "").upper()
    for k in URGENT_EXPRESS_KEYS:
        if k in str(name or ""):
            return k
    for c in URGENT_EXPRESS_CODES:
        if c in s:
            return "中通" if c in ("ZTO", "ZHONGTONG") else "申通"
    return ""


def _store_record(trade):
    """生成 store 记录（全量保留，含平台状态；剔除动作放到本地建索引时做）。"""
    count, pairs = _order_contribution(trade)
    return {"status": trade.get("sysStatus"),
            "us": trade.get("unifiedStatus"),
            "urgent": bool(trade.get("isUrgent")),
            "ex": str(trade.get("expressCompanyName") or trade.get("logisticsCompanyName")
                      or trade.get("expressCode") or ""),
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
                # 一单一件的加急，按快递拆开（只统计中通/申通）
                if int(rec.get("count") or 0) == 1:
                    _ex = _urgent_express(rec.get("ex"))
                    if _ex:
                        ue = e.setdefault("ue", {})
                        ue[_ex] = int(ue.get(_ex, 0)) + 1
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
DISCOVER_PORT = 8791          # 子客户端「自动发现」的 UDP 广播端口
APP_VER = (getattr(kmclient, "APP_VER", "") or "v1.23") if kmclient else "v1.23"
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


class _Denied(Exception):
    """没有权限：由 _need() 抛出，在 do_GET / do_POST 顶层统一转成 403。

    不能直接把 _json(...) 的返回值当「拒绝标记」—— _json 会把响应立刻发出去并返回 None，
    调用方就看不见拒绝、继续把动作执行完了（客户端看到 403，接口却真的变了）。
    """

    def __init__(self, key, label):
        Exception.__init__(self, label)
        self.perm = key
        self.label = label


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
        """会话 token：查询串 sid / 请求头 X-KM-Token（桌面端用）/ Cookie。"""
        hdr = (self.headers.get("X-KM-Token") or "").strip()
        return ((qs.get("sid") or [""])[0] or "").strip() or hdr or self._cookie_token()

    def _peer_ip(self):
        try:
            return str((self.client_address or [""])[0] or "")
        except Exception:
            return ""

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

    # ---------- 按钮权限（按账号） ----------
    def _perms_of(self, me):
        """当前登录账号的完整权限表（管理员全开；老账号缺字段按默认值）。"""
        if not me or auth is None or perms is None:
            return {}
        try:
            return perms.effective(auth.user_perms_raw(me.get("name")), me.get("role"))
        except Exception:
            return {}

    def _can(self, me, key):
        if not me:
            return False
        pf = self._perms_of(me)
        if not pf:                      # 账号/权限模块不可用时不要把所有人锁死
            return auth is None or perms is None
        return bool(pf.get(key))

    def _deny(self, key):
        label = (perms.LABELS.get(key) if perms else None) or key
        raise _Denied(key, label)

    def _need(self, me, key):
        """有权限就返回 None 继续跑；没权限则抛 _Denied（顶层转 403，后续动作一律不执行）。"""
        if not self._can(me, key):
            self._deny(key)
        return None

    def _need_any(self, me, keys):
        for k in keys:
            if self._can(me, k):
                return None
        self._deny(keys[0])
        return None

    def _page(self, html, me):
        """把当前账号的权限表塞进页面：左上角入口和按钮显隐都由它决定。"""
        try:
            me_json = json.dumps({"name": (me or {}).get("name") or "",
                                  "role": (me or {}).get("role") or ""}, ensure_ascii=False)
            p_json = json.dumps(self._perms_of(me), ensure_ascii=False)
            inject = ("<script>window.KM_ME=%s;window.KM_PERMS=%s;"
                      "window.KM_CAN=function(k){var p=window.KM_PERMS;"
                      "if(!p)return true;return p[k]!==false;};"
                      "window.KM_APPLY=function(){var p=window.KM_PERMS;if(!p)return;"
                      "var els=document.querySelectorAll('[data-perm]');"
                      "for(var i=0;i<els.length;i++){"
                      "if(p[els[i].getAttribute('data-perm')]===false)els[i].style.display='none';}};"
                      "if(document.readyState==='loading')"
                      "{document.addEventListener('DOMContentLoaded',window.KM_APPLY);}"
                      "else{window.KM_APPLY();}</script>") % (me_json, p_json)
            # 左上角：管理员是可点的「权限管理」入口，普通账号显示账号名（服务端直接渲染）
            name = str((me or {}).get("name") or "")
            if str((me or {}).get("role") or "") == "admin":
                title = '<a href="/perms" style="color:inherit;text-decoration:none">权限管理</a>'
            else:
                title = (name.replace("&", "&amp;").replace("<", "&lt;")
                             .replace(">", "&gt;").replace('"', "&quot;"))
            html = html.replace('<span id="hdrTitle"></span>',
                                '<span id="hdrTitle">' + title + '</span>', 1)
            if "</head>" in html:
                return html.replace("</head>", inject + "</head>", 1).encode("utf-8")
            return (inject + html).encode("utf-8")
        except Exception:
            return html.encode("utf-8")

    def _forbidden_page(self, msg):
        body = ("<!doctype html><html lang='zh-CN'><head><meta charset='utf-8'>"
                "<meta name='viewport' content='width=device-width,initial-scale=1'>"
                "<title>无权访问</title></head>"
                "<body style='font-family:-apple-system,sans-serif;padding:28px;line-height:1.8'>"
                "<h3>无权访问</h3><p>%s</p>"
                "<p style='color:#666'>这是账号权限设置，请联系管理员。</p>"
                "<p><a href='/'>返回首页</a></p></body></html>") % (msg or "没有权限")
        return self._send(body.encode("utf-8"), "text/html; charset=utf-8", 403)

    def _perms_payload(self):
        """权限管理页面的数据：清单 + 每个账号当前的完整权限表。"""
        out = []
        for u in (auth.list_users() if auth else []):
            name = u.get("name")
            role = u.get("role") or "user"
            out.append({"name": name, "role": role, "device": u.get("device") or "",
                        "owner": bool(u.get("owner")),
                        "allow_multi_device": bool(u.get("allow_multi_device")),
                        "online": bool(u.get("online")),
                        "kinds": u.get("kinds") or [],
                        "perms": self._perms_of({"name": name, "role": role})})
        return {"catalog": (perms.catalog() if perms else []),
                "groups": ([{"name": g, "keys": ks} for g, ks in perms.groups()] if perms else []),
                "users": out}

    def _devices_payload(self):
        """子客户端管理：本机（主机）信息 + 每个账号的登录设备/最后活跃。"""
        return {"host": _web_host_info(), "devices": (auth.list_users() if auth else []),
                "server_time": now_gmt8(), "ver": APP_VER,
                "port": int(_WEB_STATE.get("port") or WEB_PORT),
                "ips": lan_ips()}

    def _auth_state(self, qs):
        u = self._auth(qs)
        return {"need_setup": bool(auth and auth.need_setup()),
                "local": self._client_is_local(),
                "user": (u or {}).get("name"), "role": (u or {}).get("role"),
                "owner": bool((u or {}).get("owner")),
                "allow_multi_device": bool((u or {}).get("allow_multi_device")),
                "host_kind": (u or {}).get("kind") or "",
                "users": (auth.list_users() if (auth and u and self._can(u, "admin.perms")) else []),
                "perms": self._perms_of(u),
                "app": "kuaimai-fahuo-chaxun", "ver": APP_VER,
                "host": _web_host_info().get("pc") or "",
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
            if path == "/api/ping":
                # 子客户端「测试连接 / 自动发现」用：不需要登录，只说“我是谁、能不能登录”
                return self._json(discovery_payload())
            me = self._auth(qs)
            if not me:
                if path.startswith("/api/"):
                    return self._json({"error": "请先登录", "login": True}, 401)
                # 没登录时直接返回登录页（不靠 302，中转/任何客户端都能看到）
                return self._send(LOGIN_HTML.encode("utf-8"), "text/html; charset=utf-8")
            if parsed.path in ("/", "/index.html"):
                return self._send(self._page(WEB_INDEX_HTML, me), "text/html; charset=utf-8")
            if parsed.path in ("/perms", "/perms.html"):        # 权限管理页：只有管理员进得去
                if not self._can(me, "admin.perms"):
                    return self._forbidden_page("权限管理只有管理员能打开")
                return self._send(self._page(PERMS_HTML, me), "text/html; charset=utf-8")
            if parsed.path in ("/pick", "/pick.html"):
                if not self._can(me, "pick.view"):
                    return self._forbidden_page("这个账号没有拣货权限")
                return self._send(self._page(PICK_HTML, me), "text/html; charset=utf-8")
            if parsed.path in ("/stocktake", "/stocktake.html"):
                if not self._can(me, "stocktake.view"):
                    return self._forbidden_page("这个账号没有库存盘点权限")
                return self._send(self._page(STOCKTAKE_HTML, me), "text/html; charset=utf-8")
            if parsed.path in ("/order", "/order.html"):
                if not self._can(me, "order.query"):
                    return self._forbidden_page("这个账号没有订单查询权限")
                return self._send(self._page(ORDER_HTML, me), "text/html; charset=utf-8")
            if parsed.path in ("/stock", "/stock.html"):
                if not self._can(me, "stock.view"):
                    return self._forbidden_page("这个账号没有现货可发权限")
                return self._send(self._page(STOCK_HTML, me), "text/html; charset=utf-8")
            if parsed.path in ("/prints", "/prints.html"):
                # 打印记录：数据来自 /api/print/stats（live + recent），登录/权限沿用现有机制
                if not self._can(me, "scan.printed"):
                    return self._forbidden_page("这个账号没有打印记录权限")
                return self._send(self._page(PRINTS_HTML, me), "text/html; charset=utf-8")
            if parsed.path == "/api/perms":
                if not self._can(me, "admin.perms"):
                    return self._deny("admin.perms")
                return self._json(self._perms_payload())
            if parsed.path == "/api/devices":
                # 子客户端管理：在线设备（主账号看）
                if not self._can(me, "desktop.admin"):
                    return self._deny("desktop.admin")
                return self._json(self._devices_payload())
            if parsed.path == "/api/print/memory":
                # 跨机共享的「已打订单」：各端打单前同步下来，合并进本机去重记忆。
                # 防两台电脑身份相同（或旧版空派单）时把同一单各打一遍。
                deny = self._need(me, "scan.printed")
                if deny:
                    return deny
                try:
                    import kuaimai_print_jobs as pj
                    conn = pj.connect(DB_FILE)
                    try:
                        return self._json({"ok": True, "sids": pj.printed_sids(conn)})
                    finally:
                        conn.close()
                except Exception as e:
                    return self._json({"error": "共享去重记忆失败：%s" % str(e)[:120]}, 500)
            if parsed.path == "/api/print/stats":
                # 打单任务看板（各端/各状态计数）
                _me = self._auth(urllib.parse.parse_qs(parsed.query))
                if not _me:
                    return self._json({"error": "请先登录", "login": True}, 401)
                try:
                    import kuaimai_print_jobs as pj
                    conn = pj.connect(DB_FILE)
                    try:
                        st = pj.stats(conn)
                    finally:
                        conn.close()
                except Exception as e:
                    return self._json({"error": "读取失败：%s" % str(e)[:120]}, 500)
                return self._json({"ok": True, "stats": st})
            if parsed.path == "/api/scans":
                deny = self._need(me, "scan.record")
                if deny:
                    return deny
                try:
                    lim = int((qs.get("limit") or ["300"])[0] or 300)
                except Exception:
                    lim = 300
                return self._json(app.web_scans(lim, (qs.get("who") or [""])[0],
                                                (qs.get("kw") or [""])[0]))
            if parsed.path == "/api/scans/export":
                deny = self._need(me, "export.excel")
                if deny:
                    return deny
                try:
                    lim = int((qs.get("limit") or ["0"])[0] or 0)
                except Exception:
                    lim = 0
                data = app.scans_xlsx(lim, (qs.get("who") or [""])[0], (qs.get("kw") or [""])[0])
                if not data:
                    return self._json({"error": "没有可导出的扫码记录"}, 400)
                return self._send_file(data,
                                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                       "saoma_jilu.xlsx")
            if parsed.path == "/api/batch":
                deny = self._need(me, "batch.query")
                if deny:
                    return deny
                try:
                    bdays = int((qs.get("days") or ["3"])[0] or 3)
                except Exception:
                    bdays = 3
                batch = (qs.get("batch") or [""])[0].strip()
                if not batch:
                    return self._json({"error": "缺少 batch"}, 400)
                out = app.web_batch(batch, bdays)
                return self._json(out, 200 if not out.get("error") else 400)
            if parsed.path == "/api/stock/bins":
                deny = self._need_any(me, ("stock.edit", "stock.zero"))
                if deny:
                    return deny
                code = (qs.get("code") or [""])[0].strip()
                if not code:
                    return self._json({"error": "缺少 code"}, 400)
                return self._json(app.stock_bins_of(code))
            if parsed.path == "/api/status":
                d_st = dict(app.web_status() or {})
                d_st["web_hold"] = get_web_hold()
                return self._json(d_st)
            if parsed.path == "/api/index":
                return self._json(app.web_index_payload())
            if parsed.path == "/api/pick/list":
                deny = self._need(me, "pick.view")
                if deny:
                    return deny
                try:
                    pdays = int((qs.get("days") or ["3"])[0] or 3)
                except Exception:
                    pdays = 3
                return self._json(app.web_pick_list((qs.get("batch") or [""])[0], pdays,
                                                    (qs.get("refresh") or ["0"])[0] in ("1", "true")))
            if parsed.path == "/api/pick/current":
                deny = self._need(me, "pick.view")
                if deny:
                    return deny
                return self._json(app.web_pick_current())
            if parsed.path == "/api/pick/mark":
                deny = self._need(me, "pick.mark")
                if deny:
                    return deny
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
                deny = self._need(me, "pick.end")
                if deny:
                    return deny
                return self._json(app.web_pick_end((qs.get("batch") or [""])[0]))
            if parsed.path == "/api/lookup":
                deny = self._need(me, "scan.query")
                if deny:
                    return deny
                code = (qs.get("code") or [""])[0].strip()
                rel = (qs.get("rel") or ["any"])[0] or "any"
                try:
                    n = int((qs.get("n") or ["0"])[0] or 0)
                except Exception:
                    n = 0
                if not code:
                    return self._json({"error": "缺少 code"}, 400)
                out = app.web_lookup(code, rel, n)
                # 说明：网页查询（摄像头/手动）**不再**写电脑端扫码记录 ——
                # 只有点「已发」并填了数量才写（见 /api/stock/canprint），避免查询把日志刷满。
                return self._json(out)
            if parsed.path == "/api/order":
                deny = self._need(me, "order.query")
                if deny:
                    return deny
                return self._json(app.web_order((qs.get("no") or [""])[0]))
            if parsed.path == "/api/order/img":
                deny = self._need(me, "order.query")
                if deny:
                    return deny
                ctype, data = app.web_order_image((qs.get("u") or [""])[0])
                if not data:
                    return self._json({"error": "图片地址不允许或取不到"}, 400)
                return self._send(data, ctype)
            if parsed.path == "/api/stock":
                deny = self._need_any(me, ("stock.view", "stocktake.view"))
                if deny:
                    return deny
                return self._json(app.web_stock((qs.get("kw") or [""])[0],
                                                (qs.get("only") or ["all"])[0],
                                                (qs.get("sort") or ["free"])[0]))
            if parsed.path == "/api/stock/export":
                deny = self._need(me, "stock.export")
                if deny:
                    return deny
                data = app.stock_xlsx((qs.get("kw") or [""])[0],
                                      (qs.get("only") or ["all"])[0],
                                      (qs.get("sort") or ["free"])[0])
                if not data:
                    return self._json({"error": "没有可导出的数据"}, 400)
                return self._send_file(data,
                                       "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                                       "xianhuo_kefa.xlsx")
            return self._json({"error": "not found"}, 404)
        except _Denied as d:
            return self._json({"error": "没有这个功能的权限：" + d.label,
                               "denied": True, "perm": d.perm}, 403)
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
                tok, err = auth.login(name, body.get("pw"), dev, body.get("dev_id"), body.get("model"),
                                      pc=body.get("pc") or "", win_user=body.get("win_user") or "",
                                      ip=self._peer_ip(), kind=body.get("kind") or "desktop")
                if err:
                    return self._json({"error": err}, 400)
                self._set_cookie(tok)
                _note_login(name, "admin", "host")
                return self._json({"ok": True, "token": tok, "name": name, "role": "admin",
                                   "owner": bool(auth.is_owner(name)),
                                   "allow_multi_device": bool((auth.users().get(name) or {})
                                                              .get("allow_multi_device")),
                                   "perms": self._perms_of({"name": name, "role": "admin"}),
                                   "ver": APP_VER})
            if path == "/api/auth/login":
                if not auth:
                    return self._json({"error": "账号模块不可用"}, 400)
                tok, err = auth.login(body.get("name"), body.get("pw"), dev, body.get("dev_id"),
                                      body.get("model"), pc=body.get("pc") or "",
                                      win_user=body.get("win_user") or "", ip=self._peer_ip(),
                                      kind=body.get("kind") or "web")
                if err:
                    return self._json({"error": err}, 400)
                self._set_cookie(tok)
                role = (auth.users().get(str(body.get("name")).strip()) or {}).get("role") or "user"
                _note_login(str(body.get("name")).strip(), role,
                            body.get("mode") or ("host" if body.get("kind") == "desktop" else "web"))
                return self._json({"ok": True, "token": tok, "name": body.get("name"), "role": role,
                                   "owner": bool(auth.is_owner(str(body.get("name")).strip())),
                                   "allow_multi_device": bool((auth.users().get(str(body.get("name")).strip())
                                                              or {}).get("allow_multi_device")),
                                   "perms": self._perms_of({"name": body.get("name"), "role": role}),
                                   "ver": APP_VER})
            me = self._auth(qs)
            if not me:
                return self._json({"error": "请先登录", "login": True}, 401)
            if path == "/api/auth/logout":
                if auth:
                    auth.logout(self._token(qs))
                self._set_cookie("")
                return self._json({"ok": True})
            if path == "/api/client/info":
                # 子客户端心跳：刷新“最后活跃”和设备信息，供「在线设备」列表用
                if auth:
                    try:
                        auth.touch(me.get("name"), ip=self._peer_ip(),
                                   pc=str(body.get("pc") or ""),
                                   win_user=str(body.get("win_user") or ""),
                                   kind=str(body.get("kind") or "desktop"))
                    except Exception:
                        pass
                return self._json({"ok": True, "name": me.get("name"), "role": me.get("role"),
                                   "server_time": now_gmt8(), "ver": APP_VER})
            if path == "/api/scans/printed":
                # 桌面端/子客户端把某条扫码记录标「已打」
                deny = self._need(me, "scan.printed")
                if deny:
                    return deny
                try:
                    rid = int(body.get("id"))
                except Exception:
                    return self._json({"error": "缺少 id"}, 400)
                flag = 1 if (body.get("flag") is None or body.get("flag")) else 0
                # 来源写进审计日志：人工确认的那只手是谁（电脑端 / 子端都走这里）
                okw = set_printed(rid, flag, by="接口 /api/scans/printed（%s）"
                                  % str((me or {}).get("name") or "-"))
                return self._json({"ok": bool(okw), "id": rid, "printed": flag})
            if path == "/api/print/claim":
                # 子客户端来认领属于它的打单任务（原子认领，多端同时抢只成一台）
                deny = self._need(me, "scan.printed")
                if deny:
                    return deny
                client = str(body.get("client") or "").strip()
                if not client:
                    return self._json({"error": "缺少 client（本机打印身份）"}, 400)
                try:
                    limit = max(1, min(20, int(body.get("limit") or 1)))
                except Exception:
                    limit = 1
                try:
                    import kuaimai_print_jobs as pj
                    conn = pj.connect(DB_FILE)
                    try:
                        pj.reclaim(conn)
                        jobs = pj.claim(conn, client, limit=limit)
                    finally:
                        conn.close()
                except Exception as e:
                    return self._json({"error": "认领失败：%s" % str(e)[:120]}, 500)
                return self._json({"ok": True, "client": client, "jobs": jobs})
            if path == "/api/print/report":
                # 客户端打完回写结果（done/failed + 运单号）
                deny = self._need(me, "scan.printed")
                if deny:
                    return deny
                client = str(body.get("client") or "").strip()
                try:
                    job_id = int(body.get("job_id"))
                except Exception:
                    return self._json({"error": "缺少 job_id"}, 400)
                try:
                    import kuaimai_print_jobs as pj
                    conn = pj.connect(DB_FILE)
                    try:
                        pj.report(conn, job_id, client, bool(body.get("ok")),
                                  msg=body.get("msg") or "", out_sid=body.get("out_sid") or "",
                                  picked_sids=body.get("picked_sids") or [])
                    finally:
                        conn.close()
                except Exception as e:
                    return self._json({"error": "回写失败：%s" % str(e)[:120]}, 500)
                return self._json({"ok": True, "job_id": job_id})
            if path == "/api/print/memory":
                # 打完把「已出纸的 sid」报上来 → 写进主端权威库（供所有电脑同步，跨机防重）
                deny = self._need(me, "scan.printed")
                if deny:
                    return deny
                sids = body.get("sids") or []
                if isinstance(sids, (str, int)):
                    sids = [sids]
                try:
                    import kuaimai_print_jobs as pj
                    conn = pj.connect(DB_FILE)
                    try:
                        n = pj.mark_printed(conn, list(sids), body.get("out_sids") or {},
                                            client=str(body.get("client") or ""))
                    finally:
                        conn.close()
                except Exception as e:
                    return self._json({"error": "共享去重记忆失败：%s" % str(e)[:120]}, 500)
                return self._json({"ok": True, "marked": n})
            if path == "/api/print/heartbeat":
                # 打单期间心跳：刷新 claim_ts，防长任务被超时回收后别的电脑重领重打
                deny = self._need(me, "scan.printed")
                if deny:
                    return deny
                try:
                    import kuaimai_print_jobs as pj
                    conn = pj.connect(DB_FILE)
                    try:
                        n = pj.heartbeat(conn, int(body.get("job_id")),
                                         str(body.get("client") or ""))
                    finally:
                        conn.close()
                except Exception as e:
                    return self._json({"error": "心跳失败：%s" % str(e)[:120]}, 500)
                return self._json({"ok": True, "refreshed": n})
            if path == "/api/print/jobs_add":
                # 提交一个打单任务（主端权威）：按 print_clients.json 的账号映射决定派给谁
                deny = self._need(me, "scan.printed")
                if deny:
                    return deny
                code = str(body.get("code") or "").strip()
                try:
                    qty = int(float(body.get("qty") or 0))
                except Exception:
                    qty = 0
                if not code or qty <= 0:
                    return self._json({"error": "code/qty 不合法"}, 400)
                who = str(body.get("who") or me.get("name") or "").strip()
                try:
                    import kuaimai_print_jobs as pj
                    mp = pj.load_client_map(os.path.join(BASE_DIR, "print_clients.json"))
                    tgt = str(body.get("target") or "").strip() or pj.client_for(mp, who)
                    if not tgt:
                        # 空 = 不自动打：拒绝建「任意」任务（旧行为会把空串当谁都能领 → 到处打单）
                        return self._json({"error": "该账号未配置自动打单（「不自动打」）："
                                                    "请到「打印分工」指定 pc1/pc2/pc3，"
                                                    "或用 target 明确指定"}, 400)
                    conn = pj.connect(DB_FILE)
                    try:
                        jid, why = pj.add_job_checked(conn, code, qty, who=who,
                                                      target_client=tgt,
                                                      force=bool(body.get("force")))
                    finally:
                        conn.close()
                except Exception as e:
                    return self._json({"error": "建任务失败：%s" % str(e)[:120]}, 500)
                if not jid:
                    return self._json({"error": why, "dup": True}, 409)
                return self._json({"ok": True, "job_id": jid, "target_client": tgt})
            if path == "/api/print/jobs_del":
                # 删除打单任务（主端权威）：job_id 单条 / ids 列表 / status 批量（如清空 failed）。
                # 权限：scan.printed；没权限时 _need 直接抛 _Denied（顶层统一转 403，
                # 不做返回值短路 —— 否则后面的删除动作照样会跑）。子端删主端任务也走这里。
                self._need(me, "scan.printed")
                ids = body.get("ids")
                if isinstance(ids, (str, int)):
                    ids = [ids]
                ids = list(ids or []) if isinstance(ids, (list, tuple)) else []
                try:
                    _jid = body.get("job_id")
                    if _jid not in (None, ""):
                        ids.append(int(_jid))
                except Exception:
                    pass
                status = str(body.get("status") or "").strip()
                if status and status not in ("pending", "claimed", "printing", "done", "failed"):
                    return self._json({"error": "status 只能是 pending/claimed/done/failed"}, 400)
                if not ids and not status:
                    return self._json({"error": "要删什么：请给 job_id / ids / status"}, 400)
                try:
                    import kuaimai_print_jobs as pj
                    conn = pj.connect(DB_FILE)
                    try:
                        n = pj.delete_jobs(conn, ids=ids, status=(status or None))
                    finally:
                        conn.close()
                except Exception as e:
                    return self._json({"error": "删除失败：%s" % str(e)[:120]}, 500)
                if n:
                    who = str((me or {}).get("name") or "-")
                    if len(ids) == 1 and not status:
                        print_jobs_log("删除任务 #%s（%s 删的）" % (ids[0], who))
                    else:
                        print_jobs_log("删除任务 %d 条%s（%s 删的）"
                                       % (n, ("，状态 %s" % status) if status else "", who))
                return self._json({"ok": True, "deleted": int(n)})
            if path == "/api/stock/sent":
                # 现货可发：标记/撤回「已发」（存在程序里，所有账号共用；拉新数据后自动清空）
                deny = self._need(me, "stock.canprint")
                if deny:
                    return deny
                app = self.app
                if body.get("clear"):
                    deny2 = self._need(me, "stock.sent.clear")
                    if deny2:
                        return deny2
                    app.clear_sent()
                    return self._json({"ok": True, "sent": 0})
                left = app.mark_sent(body.get("codes") or body.get("code") or [],
                                     undo=bool(body.get("undo")))
                return self._json({"ok": True, "sent": len(left)})
            if path == "/api/stock/canprint":
                # 网页现货可发点「可发」并输入数量 → 写一条扫码日志（可打单数量 = 输入值）
                deny = self._need(me, "stock.canprint")
                if deny:
                    return deny
                code = str(body.get("code") or "").strip()
                if not code:
                    return self._json({"error": "缺少编码"}, 400)
                if body.get("cancel"):
                    # 撤回：把还在 30 秒宽限期里的那条删掉 → 电脑端根本不会出现。
                    # ★ 同时取消该编码**还没开打**的 pending 打单任务（用户口径 2026-09-24）：
                    #   撤回就真的不打；正在打/已打完/失败的任务一律不动
                    #   （不打断出纸、也不涉重复打印）。只能在主端做（子端无本机库）。
                    gone = delete_pending_canprint(code)
                    n_cancel = 0
                    if not self.remote:
                        try:
                            import kuaimai_print_jobs as pj
                            _pc = pj.connect(DB_FILE)
                            try:
                                n_cancel = pj.cancel_pending_by_code(
                                    _pc, code, who=str((me or {}).get("name") or ""))
                            finally:
                                _pc.close()
                            if n_cancel:
                                print_jobs_log("可发撤回：取消该编码未开打的任务 %d 条（%s）"
                                               % (n_cancel, code))
                        except Exception as e:
                            print_jobs_log("可发撤回：取消失败（不影响撤回记录）：%s" % str(e)[:120])
                    return self._json({"ok": True, "code": code, "cancelled": gone,
                                       "jobs_cancelled": int(n_cancel)})
                try:
                    qty = int(body.get("qty"))
                except Exception:
                    return self._json({"error": "数量必须是整数"}, 400)
                hold = get_web_hold()          # 宽限只认电脑端的设置，网页传什么都被忽略
                if hold < 0:
                    hold = 0
                who = str((me or {}).get("name") or "")
                insert_canprint(code, qty, who=who,
                                bins=str(body.get("bins") or ""),
                                pending_qty=body.get("pending") or 0,
                                shelf_qty=body.get("shelf") or 0,
                                hold_secs=hold)
                # 同一条路径上再建一个打单任务（主端权威）：按 print_clients.json 派给对应电脑，
                # 各端启动后向本机主端认领 → 打单 → 回写（一台只打一次）。
                # 「桌面版」自己扫的记录不建任务（那是电脑端人工点数字才打）。
                dup = ""                      # 非空 = 重复提交、本次没建任务（回给网页提示）
                if not who.startswith("桌面版"):
                    try:
                        import kuaimai_print_jobs as pj
                        tgt = pj.client_for(load_print_clients(), who)
                        if not tgt:
                            # tgt 为空 = 「不自动打」（该账号没在「打印分工」里指派电脑，
                            # 或明确选了「不自动打」，或文件是空表）→ **不建任务**，绝不派给任意电脑。
                            print_jobs_log("不推送：来源 %s 在「打印分工」里是「不自动打」"
                                           "→ 网页可发也不派给任何电脑（要自动打请指定 pc1/pc2/pc3）"
                                           % (who or "-"))
                        else:
                            _pc = pj.connect(DB_FILE)
                            try:
                                jid, _why = pj.add_job_checked(_pc, code, qty, who=who,
                                                               target_client=tgt,
                                                               msg="网页提交",
                                                               force=bool(body.get("force")))
                            finally:
                                _pc.close()
                            if jid:
                                print_jobs_log("建任务 #%s：%s ×%s（来源 %s → %s）"
                                               % (jid, code, qty, who or "-", tgt))
                                dup = ""
                            else:
                                # 重复提交（同编码已在队列 / 窗口内刚打完）→ 不建第二个任务，
                                # 否则每次都各自去打一遍同一编码（实测 9681 ×5 提交 3 次打了 3 遍）
                                dup = str(_why or "重复提交")
                                print_jobs_log("不建任务（重复提交）：%s ×%s（来源 %s）→ %s"
                                               % (code, qty, who or "-", dup))
                    except Exception as e:
                        print_jobs_log("建任务失败（扫码记录已写，不影响提交）：%s" % str(e)[:120])
                return self._json({"ok": True, "code": code, "qty": qty, "hold": hold,
                                   "dup": bool(dup), "dup_msg": (dup or None)})
            if path == "/api/stock/adjust":
                # 改库存（盘点接口，按货位）。必须带 confirm 二次确认，改完写操作日志。
                try:
                    _qty = int(body.get("qty"))
                except Exception:
                    _qty = None
                deny = self._need(me, "stock.zero" if _qty == 0 else "stock.edit")
                if deny:
                    return deny
                app = self.app
                if not body.get("confirm"):
                    return self._json({"error": "缺少二次确认"}, 400)
                out = app.stock_adjust(body.get("code"), body.get("bin"), body.get("qty"),
                                       who=str((me or {}).get("name") or ""))
                return self._json(out, 200 if out.get("ok") else 400)
            if path == "/api/stock/adjust/log":
                deny = self._need_any(me, ("stock.edit", "stock.zero"))
                if deny:
                    return deny
                return self._json({"list": self.app.adjust_logs(int(body.get("limit") or 30))})
            if path == "/api/perms":
                # 保存某账号的按钮权限：只有管理员能调（非管理员连清单都拿不到）
                if not self._can(me, "admin.perms"):
                    return self._deny("admin.perms")
                if not (auth and perms):
                    return self._json({"error": "账号/权限模块不可用"}, 400)
                if str(body.get("action") or "save") == "list":
                    return self._json(self._perms_payload())
                target = str(body.get("name") or "").strip()
                if not target:
                    return self._json({"error": "缺少账号"}, 400)
                if (auth.users().get(target) or {}).get("role") == "admin":
                    return self._json({"error": "管理员始终拥有全部权限，不用配置"}, 400)
                err = auth.set_user_perms(target, perms.sanitize(body.get("perms") or {}))
                if err:
                    return self._json({"error": err}, 400)
                return self._json({"ok": True, "name": target,
                                   "perms": self._perms_of({"name": target, "role": "user"})})
            if path == "/api/users":
                if not auth:
                    return self._json({"error": "账号模块不可用"}, 400)
                # 管理权限：管理员，或被授予 admin.perms 的子账号（子账号也能管别的子账号）
                if not self._can(me, "admin.perms"):
                    return self._deny("admin.perms")
                act = str(body.get("action") or "list")
                target = str(body.get("name") or "").strip()
                i_am_owner = bool((me or {}).get("owner"))
                if act in ("del", "passwd", "kick", "multi") and target \
                        and auth.is_owner(target) and not i_am_owner:
                    return self._json({"error": "主账号只能由主账号本人管理"}, 403)
                err = ""
                if act == "add":
                    role = str(body.get("role") or "user")
                    if role == "admin" and not i_am_owner:
                        return self._json({"error": "只有主账号能新建管理员账号"}, 403)
                    err = auth.add_user(target, body.get("pw"), role)
                elif act == "del":
                    if auth.is_owner(target):
                        return self._json({"error": "主账号不能删"}, 400)
                    err = auth.del_user(target)
                elif act == "passwd":
                    # 改自己的密码：不踢自己、不锁自己；改别人的：旧会话失效 + 那台设备 10 分钟不能再登录
                    mine = (target == str(me.get("name") or ""))
                    err = auth.set_password(target, body.get("pw"), 0 if mine else 10)
                elif act == "kick":
                    if target == str(me.get("name") or ""):
                        return self._json({"error": "不能踢自己下线"}, 400)
                    err = auth.kick(target)
                elif act == "multi":
                    err = auth.set_multi_device(target, bool(body.get("flag")))
                if err:
                    return self._json({"error": err}, 400)
                return self._json({"ok": True, "users": auth.list_users(),
                                   "owner": auth.owner_names(), "me": str(me.get("name") or "")})
            return self._json({"error": "not found"}, 404)
        except _Denied as d:
            return self._json({"error": "没有这个功能的权限：" + d.label,
                               "denied": True, "perm": d.perm}, 403)
        except Exception as e:
            return self._json({"error": str(e)[:200]}, 500)


# ==================== 内置服务 / 子客户端发现（主客户端那一侧） ====================
_WEB_STATE = {"servers": [], "port": 0, "app": None, "user": "", "role": "",
              "mode": "", "login_at": "", "udp": False, "udp_stop": False, "lan": False}


class _NullHost:
    """登录阶段的内置服务“占位 app”：只给登录/状态接口用，不提供数据页。"""
    web_key = ""
    require_key = False

    def __getattr__(self, item):
        def _no(*_a, **_k):
            raise RuntimeError("还没登录：请先在程序里登录")
        return _no


def _web_host_info():
    """本机（主机侧）的登录信息，给「在线设备」列表用。"""
    try:
        host = socket.gethostname()
    except Exception:
        host = ""
    return {"name": _WEB_STATE.get("user") or "", "role": _WEB_STATE.get("role") or "",
            "pc": host, "win_user": (os.environ.get("USERNAME") or os.environ.get("USER") or ""),
            "mode": _WEB_STATE.get("mode") or "host", "login": _WEB_STATE.get("login_at") or "",
            "ver": APP_VER}


def _note_login(name, role, mode=""):
    _WEB_STATE["user"] = str(name or "")
    _WEB_STATE["role"] = str(role or "")
    _WEB_STATE["mode"] = str(mode or "")
    _WEB_STATE["login_at"] = now_gmt8()


def discovery_payload():
    """广播/接口告诉外面“我是主客户端”：子客户端自动发现和测试连接都看这个。"""
    info = _web_host_info()
    ips = []
    try:
        ips = lan_ips()
    except Exception:
        pass
    return {"app": "kuaimai-fahuo-chaxun",
            "name": ("快麦主客户端 · " + info["pc"]) if info.get("pc") else "快麦主客户端",
            "pc": info.get("pc") or "", "ip": (ips[0] if ips else ""),
            "ips": ips,
            "port": int(_WEB_STATE.get("port") or WEB_PORT),
            "need_setup": bool(auth and auth.need_setup()),
            "logged_in": bool(_WEB_STATE.get("user")),
            "user": _WEB_STATE.get("user") or "", "ver": APP_VER,
            "time": now_gmt8()}


def start_discovery_responder():
    """UDP 广播应答：子客户端的「自动发现」靠它（只在本机服务已起来时开）。"""
    if _WEB_STATE.get("udp"):
        return
    _WEB_STATE["udp"] = True
    _WEB_STATE["udp_stop"] = False

    def loop():
        s = None
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
            except Exception:
                pass
            s.bind(("0.0.0.0", int(DISCOVER_PORT)))
            s.settimeout(0.5)
        except Exception:
            if s is not None:
                try:
                    s.close()
                except Exception:
                    pass
            _WEB_STATE["udp"] = False
            return
        while not _WEB_STATE.get("udp_stop"):
            try:
                data, peer = s.recvfrom(1024)
            except socket.timeout:
                continue
            except Exception:
                time.sleep(0.3)
                continue
            try:
                if not data or not data.startswith(b"KUIMAI-SCAN-DISCOVER"):
                    continue
                s.sendto(json.dumps(discovery_payload(), ensure_ascii=False).encode("utf-8"), peer)
            except Exception:
                pass
        try:
            s.close()
        except Exception:
            pass
        _WEB_STATE["udp"] = False

    threading.Thread(target=loop, daemon=True).start()


def ensure_web_server(app=None, lan=False, port=None):
    """保证内置 HTTP 服务在跑；返回端口。

    · lan=False（登录阶段）：只在 127.0.0.1 上起，不对外暴露；
    · lan=True（主客户端模式）：对外（0.0.0.0 + IPv6）并开始广播应答，让子客户端能发现。
    模式变了就重建（先停再起），否则同一个端口会同时被两个监听占上。
    """
    start_port = int(port or WEB_PORT)
    want_lan = bool(lan)
    if _WEB_STATE.get("servers") and bool(_WEB_STATE.get("lan")) == want_lan:
        if app is not None:
            _WebHandler.app = app
            _WEB_STATE["app"] = app
        return int(_WEB_STATE.get("port") or 0)
    if _WEB_STATE.get("servers"):
        stop_web_server(clear_login=False)      # 只是换监听方式 → 保留“谁登录了”
    servers, p = start_web_server(app if app is not None else _NullHost(),
                                  port=start_port, host=("0.0.0.0" if want_lan else "127.0.0.1"))
    if servers:
        _WEB_STATE["servers"] = servers
        _WEB_STATE["port"] = int(p or 0)
        _WEB_STATE["app"] = app
        _WEB_STATE["lan"] = want_lan
        if want_lan:
            start_discovery_responder()
        return int(p or 0)
    return 0


def stop_web_server(clear_login=True):
    """关掉本机服务（选“子客户端”模式时用：这台只当终端，不对外服务）。

    clear_login=False：只是换监听方式（回环 → 对外）重建服务，别把“谁登录了”抹掉。
    """
    _WEB_STATE["udp_stop"] = True
    for s in (_WEB_STATE.get("servers") or []):
        try:
            s.shutdown()
        except Exception:
            pass
        try:
            s.server_close()
        except Exception:
            pass
    _WEB_STATE["servers"] = []
    _WEB_STATE["port"] = 0
    _WEB_STATE["app"] = None
    if clear_login:
        _WEB_STATE["user"] = ""


class _V6Server(ThreadingHTTPServer):
    address_family = socket.AF_INET6


def start_web_server(app, port=None, host="0.0.0.0"):
    """启动内置服务（默认 IPv4+IPv6 都监听，端口被占用就顺延）。

    host="127.0.0.1" = 只在回环上起（登录阶段用，不对外暴露、也不占用局域网端口）。
    """
    _WebHandler.app = app
    start = int(port or WEB_PORT)
    for p in range(start, start + 10):
        servers = []
        try:
            servers.append(ThreadingHTTPServer((host, p), _WebHandler))
        except OSError:
            pass
        if host == "0.0.0.0":
            try:
                servers.append(_V6Server(("::", p), _WebHandler))
            except OSError:
                pass
        if servers:
            for s in servers:
                threading.Thread(target=s.serve_forever, daemon=True).start()
            return servers, p
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

    def __init__(self, root, session=None):
        self.root = root
        self.session = session                 # kuaimai_client.Session（登录会话）
        self.remote = bool(kmclient and session is not None and session.is_remote)
        self.gated = {}                        # 权限键 → [(控件, 处理方式, 说明)]
        self._locked = False                   # 被踢下线后锁界面
        self.root.title("快麦扫码查询 %s%s" % (APP_VER, "（子客户端）" if self.remote else ""))
        self.root.geometry("1080x760")
        self.root.minsize(920, 620)
        try:
            self.root.configure(bg=UI_BG)
        except Exception:
            pass
        if session is not None:
            try:
                session.on_kicked = self._on_kicked
            except Exception:
                pass

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
        self.index_ready = False
        try:
            if uikit is not None:
                uikit.start(self.root)      # 后台加载完成后靠它安全地刷界面
        except Exception:
            pass
        if self.remote:
            self.status_text.set("正在从主客户端取数…")
            self.root.after(80, self._remote_startup)   # 子客户端：一个本地库都不碰，全走主端接口
        else:
            init_db()
            self._init_orders_db()
            self.reload_records()
            self._start_web()               # 先对外服务（手机能连），索引随后台加载
            self._restore_shelf_cache()
            self._restore_lock_cache()
            # 索引在后台建（51MB 的库聚合要几秒），界面先出来 —— 登录后不再“卡一下”
            self.root.after(80, self._load_index_async)
        self._apply_perms()
        self.root.after(100, self._drain_queue)
        if not self.remote:
            self.root.after(1200, self._first_run_api_hint)    # 新电脑首次装：提示填 API
            self.root.after(300, lambda: self.sync_pending(background=True))
            self.root.after(600, lambda: self.reload_shelf(background=True))
            self.root.after(900, lambda: self.reload_lock(background=True))
            self.root.after(1000 * 60 * self.auto_refresh_min, self._auto_tick)
        self.root.after(1500, self._init_scan_hook)      # 后台扫码监听（最小化也能扫）
        self.root.after(6000, lambda: self.on_check_update(silent=True))   # 开机悄悄查一次更新

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
            port = ensure_web_server(self, lan=True)   # 登录阶段可能已在回环上起过 → 换成对外监听
        except Exception as e:
            self.web_label.config(text="手机网页服务启动失败：%s" % str(e)[:60])
            return
        if port and self.session is not None:
            _note_login(self.session.name, self.session.role, self.session.mode)
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
        sub = []
        _dom = ""
        try:
            _dom = str((kmgw.load_config() if kmgw else {}).get("domain") or "").strip()
        except Exception:
            _dom = ""
        _dom = _dom or host                      # 对外域名：优光「对外访问设置」里填的
        if _dom:
            sub.append("https://%s:9443" % _dom)  # 客户那套：域名 + 9443（frp 转发到本机）
        _ips = lan_ips()
        if _ips:
            sub.append("%s:%d" % (_ips[0], port))
        tip = ("\n子客户端地址：这台就是主客户端，子端登录时填 %s" % "　或　".join(sub)) if sub else ""
        self.web_label.config(text="手机扫码地址：" + "    ".join(urls) + tip)

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
                "ue": {k: int(v or 0) for k, v in (e.get("ue") or {}).items()},
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
        if self.remote:                       # 子客户端：已发标记存在主端（所有账号共用）
            ok, res = self._remote_api("/api/stock/sent", "POST",
                                       body={"codes": list(codes or []) if not isinstance(codes, str) else [codes],
                                             "undo": bool(undo)})
            if not ok or not isinstance(res, dict):
                self._remote_err(res)
                return []
            return []
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
        if self.remote:
            ok, res = self._remote_api("/api/stock/sent", "POST", body={"clear": True})
            if not ok or not isinstance(res, dict):
                self._remote_err(res)
                return []
            return []
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
        if self.remote:
            ok, res = self._remote_api("/api/stock/adjust/log", "POST", body={"limit": int(limit)},
                                       timeout=25)
            if not ok or not isinstance(res, dict):
                self._remote_err(res)
                return []
            return res.get("list") or []
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
        if self.remote:
            ok, res = self._remote_api("/api/stock/bins", params={"code": code}, timeout=25)
            if not ok or not isinstance(res, dict):
                return {"code": code, "found": False, "shelf": 0, "bins": [],
                        "msg": self._remote_err(res, "")}
            return res
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
        if self.remote:                       # 子客户端：改库存也走主端接口（含权限/日志）
            ok, out = self._remote_api("/api/stock/adjust", "POST",
                                       body={"code": code, "bin": bin_code, "qty": qty,
                                             "confirm": True}, timeout=90)
            if not isinstance(out, dict):
                return {"ok": False, "msg": "主客户端没返回结果"}
            if not ok:
                return {"ok": False, "msg": str(out.get("error") or "改库存失败")}
            return out
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
        if self.remote:                       # 子客户端：让主端算好再给我
            ok, res = self._remote_api("/api/stock", params={"kw": kw, "only": only, "sort": sort},
                                       timeout=90)
            if not ok or not isinstance(res, dict):
                raise RuntimeError(kmclient.human_err(res, self.session.base) if kmclient else "读取失败")
            self.shelf_at = str(res.get("shelf_at") or self.shelf_at)
            self.loaded_at = str(res.get("loaded_at") or self.loaded_at)
            return res.get("rows") or []
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
            _ue_any = sum(int(x or 0) for x in (v.get("ue") or {}).values())
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
            if only == "urgent" and _ue_any <= 0:
                continue
            prio = 1 if (_ue_any > 0 and free > 0 and shelf > 0) else 0   # 加急且有货可发
            if only == "urg_free" and not prio:
                continue
            rows.append({"c": str(code), "s": shelf, "p": pieces, "o": orders,
                         "n": ones, "m": max(0, orders - ones), "mp": multi_pieces,
                         "uo": uo, "up": up, "p1": prio,
                         "ue": {k: int(v2 or 0) for k, v2 in ((v.get("ue") or {}).items())},
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

    def web_scans(self, limit=300, who="", kw=""):
        """扫码记录（给桌面端/子客户端用）：最新在前；limit<=0 = 全部。"""
        try:
            rows = fetch_all_scans()
        except Exception:
            rows = []
        kw = str(kw or "").strip().upper()
        who = str(who or "").strip()
        try:                                   # 中通/申通加急（按编码，只算一单一件的加急单）
            _items = (self.web_index_payload().get("items") or {})
        except Exception:
            _items = {}
        out = []
        for r in reversed(rows):                     # 最新的排最前
            rid, st, bc, pq, sh, oc, light = r[:7]
            w = r[7] if len(r) > 7 else ""
            pnum = r[8] if len(r) > 8 else ""
            prn = int(r[9] or 0) if len(r) > 9 else 0
            if who and who != "全部" and (w or "") != who:
                continue
            if kw and kw not in str(bc or "").upper():
                continue
            _e, _k = dict_get_ci(_items, bc)
            _ue = ((_e or {}).get("ue") or {})
            out.append({"id": rid, "time": st, "code": bc, "pending": pq or 0, "shelf": sh or 0,
                        "orders": oc or 0, "ok": (light == "绿"), "who": w or "",
                        "print_num": pnum or "", "printed": prn,
                        "ue": {"中通": int(_ue.get("中通") or 0),
                               "申通": int(_ue.get("申通") or 0)}})
            if limit and len(out) >= int(limit):
                break
        whos = sorted({((r[7] if len(r) > 7 else "") or "") for r in rows})
        whos = [w for w in whos if w]
        return {"rows": out, "count": len(rows), "who": whos,
                "loaded_at": self.loaded_at, "shelf_at": self.shelf_at}

    def scans_xlsx(self, limit=0, who="", kw=""):
        """扫码记录 → Excel（子客户端导出用）。返回 bytes（没数据返回 b""）。"""
        data = self.web_scans(limit, who, kw).get("rows") or []
        if not data:
            return b""
        headers = ["扫码时间", "商家编码", "待发货订单数", "货架在架数", "件数", "扫码账号",
                   "可打单数量", "已打"]
        rows = [[d["time"], d["code"], d["pending"], d["shelf"], d["orders"], d["who"],
                 d["print_num"], "已打" if d["printed"] else "打单"] for d in data]
        path = os.path.join(os.environ.get("TEMP", "."),
                            "扫码记录_%s.xlsx" % datetime.now().strftime("%Y%m%d_%H%M%S"))
        write_xlsx(path, headers, rows)
        try:
            with open(path, "rb") as fp:
                return fp.read()
        finally:
            try:
                os.remove(path)
            except Exception:
                pass

    def web_batch(self, batch, days=3, progress=None):
        """批次查询（给桌面端/子客户端用）：orders + rows（rows 只带订单下标 i）。"""
        orders, err = fetch_print_batch(batch, int(days or 3), progress=progress)
        if err:
            return {"error": err, "orders": [], "rows": []}
        out_orders = []
        rows = []
        for idx, o in enumerate(orders):
            out_orders.append({"seq": o.get("seq") or 0, "sid": o.get("sid") or "",
                               "short_id": o.get("short_id") or "",
                               "express": o.get("express") or "",
                               "urgent": bool(o.get("urgent")),
                               "sys_status": o.get("sys_status")})
            items = o.get("items") or []
            if not items:
                rows.append({"i": idx, "code": "", "num": 0, "shelf": 0, "bins": "（未取到明细）"})
                continue
            for code, num in items:
                sh, _k = dict_get_ci(self.shelf_map, code)
                sh = sh or {}
                bins = "、".join(b[0] for b in (sh.get("bins") or [])) or "无在架货位"
                rows.append({"i": idx, "code": code, "num": int(num or 0),
                             "shelf": int(sh.get("shelf", 0) or 0), "bins": bins})
        return {"orders": out_orders, "rows": rows, "count_orders": len(out_orders),
                "count_rows": len(rows), "batch": batch, "shelf_at": self.shelf_at}

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
            "ue": {k: int(v or 0) for k, v in (e.get("ue") or {}).items()},
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

        _size = {"w": 0, "h": 0}

        def _on_main_cfg(_e=None):
            try:
                _canvas.configure(scrollregion=_canvas.bbox("all"))
            except Exception:
                pass

        def _on_canvas_cfg(e):
            # 只有尺寸真的变了才动（最小化再打开会发一堆 Configure，全処理会让窗口闪一下）
            try:
                if (e.width, e.height) == (_size["w"], _size["h"]):
                    return
                _size["w"], _size["h"] = e.width, e.height
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
        _qbtn = ttk.Button(scan_box, text="查询", command=self.on_scan)
        _qbtn.grid(row=0, column=2, padx=6, pady=8)
        self._gate("scan.query", _qbtn)
        self.scan_entry.bind("<Return>", lambda e: self.on_scan())
        self.scan_entry.bind("<KeyRelease>", self._on_scan_key)   # 扫码枪不回车时按停顿自动查
        _snd = ttk.Checkbutton(scan_box, text="声音提示", variable=self.sound_on)
        _snd.grid(row=0, column=3, padx=6)
        self._gate("ui.sound", _snd)
        self.id_label = ttk.Label(scan_box, text="", foreground="#7a4f01")
        self.id_label.grid(row=1, column=0, columnspan=2, sticky="w", padx=6, pady=(0, 2))
        # 接口状态常驻显示（放扫描框右上角）：未配置时不用等弹窗也知道
        self.api_state_lbl = tk.Label(scan_box, text="", bg=UI_BG, fg="#6e6e73",
                                      font=("Microsoft YaHei", 9))
        self.api_state_lbl.grid(row=1, column=2, columnspan=2, sticky="e", padx=6, pady=(0, 2))
        self.web_label = ttk.Label(scan_box, text="", foreground="#0b5394")
        self.web_label.grid(row=2, column=0, columnspan=4, sticky="w", padx=6, pady=(0, 6))
        _key_chk = ttk.Checkbutton(scan_box, text="手机访问需口令", variable=self.key_on,
                                   command=self.on_key_toggle)
        _key_chk.grid(row=3, column=0, columnspan=4, sticky="w", padx=6, pady=(0, 6))
        self._gate("__host", _key_chk, "grid")            # 「__host」= 只有主客户端才有

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
        self._gate("scan.filter", flt.winfo_children()[-1])
        self._gate("__host", flt, "grid")            # 件数筛选靠本地订单库，子客户端没有

        # 操作按钮（网格排布：窄窗口/小屏也不会被切掉）
        ops = ttk.LabelFrame(main, text="操作")
        ops.grid(row=6, column=0, sticky="ew", pady=6)
        for c in range(5):
            ops.columnconfigure(c, weight=1)
        # 现货可发 / 批次查询 两个按钮按要求隐藏（功能代码保留：on_stock_dialog / on_batch_dialog）
        _ops_list = (("增量刷新", lambda: self.sync_pending(background=True), "TButton", "data.refresh"),
                     ("全量重拉", lambda: self.full_reload(background=True), "TButton", "data.refresh"),
                     ("刷新货位库存", lambda: self.reload_shelf(background=True), "TButton", "data.refresh"),
                     ("刷新锁定数", lambda: self.reload_lock(background=True), "TButton", "data.refresh"),
                     ("导出扫码日志 Excel", self.on_export, "TButton", "export.excel"),
                     ("清空日志", self.on_clear_logs, "TButton", "__host"),
                     ("API 设置", self.on_api_settings, "TButton", "api.settings"),
                     ("子客户端管理", self.on_admin_panel, "Accent.TButton", "desktop.admin"),
                     ("对外访问设置", self.on_gateway_settings, "TButton", "gateway.settings"),
                     ("检查更新", self.on_check_update, "TButton", "__any"),
                     ("重新登录", self.on_relogin, "TButton", "__any"),
                     ("打印分工", self.on_print_clients, "TButton", "__any"),
                     ("打单进度", self.on_print_progress, "TButton", "__any"))
        for i, (txt, cmd, sty, perm) in enumerate(_ops_list):
            _b = ttk.Button(ops, text=txt, command=cmd, style=sty)
            _b.grid(row=i // 5, column=i % 5, sticky="ew", padx=5, pady=5)
            self._gate(perm, _b)
        # 网页「可发」撤回宽限：放在「重新登录」右边（同一片操作区）
        _holdbox = ttk.Frame(ops)
        _holdbox.grid(row=2, column=4, sticky="w", padx=5, pady=5)
        ttk.Label(_holdbox, text="可发撤回宽限").pack(side=tk.LEFT, padx=(0, 4))
        self.hold_var = tk.StringVar(value=str(get_web_hold()))
        _hsp = ttk.Spinbox(_holdbox, from_=0, to=600, width=4, textvariable=self.hold_var)
        _hsp.pack(side=tk.LEFT)
        ttk.Label(_holdbox, text="秒").pack(side=tk.LEFT, padx=(4, 0))

        # 自动上架（推荐货位）：独立开关 + 可调刷新间隔，就放在「打单进度」旁边
        # （纯开放平台 API，不需要浏览器；只在主客户端跑，故 __host 门控）
        self.auto_putaway_var = tk.BooleanVar(value=self._auto_putaway_on())
        self.ap_secs_var = tk.StringVar(value=str(self._auto_putaway_secs()))
        _apbox = ttk.Frame(ops)
        _apbox.grid(row=2, column=3, sticky="w", padx=5, pady=5)
        ttk.Checkbutton(_apbox, text="自动上架推荐货位", variable=self.auto_putaway_var,
                        command=self._toggle_auto_putaway).pack(side=tk.LEFT)
        _apsb = ttk.Spinbox(_apbox, from_=AUTO_PUTAWAY_MIN_SECS, to=AUTO_PUTAWAY_MAX_SECS,
                            increment=10, width=4, textvariable=self.ap_secs_var)
        _apsb.pack(side=tk.LEFT, padx=(6, 0))
        ttk.Label(_apbox, text="秒").pack(side=tk.LEFT, padx=(4, 0))
        # 上架后自动智能审核（跟「自动上架」同一组，因为它是上架的后续动作）
        self.auto_audit_var = tk.BooleanVar(value=self._auto_audit_on())
        ttk.Checkbutton(_apbox, text="· 上架后自动智能审核", variable=self.auto_audit_var,
                        command=self._toggle_auto_audit).pack(side=tk.LEFT, padx=(14, 0))
        for _ev in ("<FocusOut>", "<Return>", "<<Increment>>", "<<Decrement>>"):
            try:
                _apsb.bind(_ev, lambda e: self._on_ap_secs())
            except Exception:
                pass
        self._gate("__host", _apbox, "grid")

        def _save_hold(_e=None):
            try:
                set_web_hold(self.hold_var.get())
                self.hold_var.set(str(get_web_hold()))
                self.status_text.set("已保存：网页可发撤回宽限 %d 秒" % get_web_hold())
            except Exception:
                self.status_text.set("宽限秒数要填 0～600 的整数")

        for _ev in ("<FocusOut>", "<Return>", "<<Increment>>", "<<Decrement>>"):
            try:
                _hsp.bind(_ev, _save_hold)
            except Exception:
                pass
        chk = ttk.Frame(ops)
        chk.grid(row=3, column=0, columnspan=5, sticky="w", padx=5, pady=(2, 4))
        _hk = ttk.Checkbutton(chk, text="后台扫码监听（最小化也能扫）", variable=self.hook_on,
                              command=self.on_hook_toggle)
        _hk.pack(side=tk.LEFT, padx=(0, 14))
        self._gate("scan.query", _hk)
        _as = ttk.Checkbutton(chk, text="不回车的扫码枪：停顿时自动查", variable=self.autosubmit_on,
                              command=self.on_autosubmit_toggle)
        _as.pack(side=tk.LEFT)
        self._gate("scan.query", _as)

        # 刷新周期
        itv = ttk.LabelFrame(main, text="刷新周期（分钟）")
        itv.grid(row=7, column=0, sticky="ew", pady=4)
        self._gate("data.refresh", itv, "grid")      # 周期刷新是主机那边的事
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
        self._gate("scan.record", log, "grid")
        main.rowconfigure(3, weight=1)
        cols = ("time", "barcode", "pending", "shelf", "who", "print_num", "ue_zt", "ue_st", "printed")
        _st = ttk.Style()
        _st.configure("ScanLog.Treeview", font=("微软雅黑", 12), rowheight=30)
        _st.configure("ScanLog.Treeview.Heading", font=("微软雅黑", 12, "bold"))
        self.tree = ttk.Treeview(log, columns=cols, show="headings", height=16, style="ScanLog.Treeview")
        for c, t, w in (("time", "扫码时间", 180), ("barcode", "商家编码", 240),
                        ("pending", "待发货订单数", 120), ("shelf", "在架数", 100),
                        ("who", "扫码账号", 145), ("print_num", "可打单数量", 115),
                        ("ue_zt", "中通加急", 100), ("ue_st", "申通加急", 100),
                        ("printed", "已打", 95)):
            self.tree.heading(c, text=t)
            self.tree.column(c, width=w, anchor="center")
        _bar = tk.Frame(log)
        _bar.pack(side=tk.TOP, fill="x", pady=(2, 2))
        ttk.Label(_bar, text="扫码账号：").pack(side=tk.LEFT, padx=(2, 2))
        self.acc_var = tk.StringVar(value="全部")
        self.acc_box = ttk.Combobox(_bar, textvariable=self.acc_var, width=18, state="readonly",
                                    values=["全部"])
        self.acc_box.pack(side=tk.LEFT)
        self.acc_box.bind("<<ComboboxSelected>>", lambda e: self.reload_records())
        ttk.Label(_bar, text="（选一个账号，只看它扫的记录）").pack(side=tk.LEFT, padx=6)
        self.tree.pack(fill=tk.BOTH, expand=True)
        _tsb = ttk.Scrollbar(log, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=_tsb.set)
        _tsb.pack(side=tk.RIGHT, fill="y")
        ttk.Button(log, text="刷新记录",
                   command=lambda: self._poll_records(force=True)).pack(side=tk.BOTTOM, pady=3)
        # 打单：选中若干行 → 预演 → 确认 → 取号/打印（不自动标「已打」）
        ttk.Button(log, text="打单", command=self.run_print_selected).pack(side=tk.BOTTOM, pady=3)
        # 网页提交后自动打单（总开关，与监听器共用暂停文件）
        self.auto_print_var = tk.BooleanVar(value=self._auto_print_on())
        ttk.Checkbutton(log, text="网页提交后自动打单", variable=self.auto_print_var,
                        command=self._toggle_auto_print).pack(side=tk.BOTTOM, pady=3)
        # 打单方式（本地设置，与「自动打单」并列；默认订单打印V2，切到后置打印即换链路）
        _pmf = ttk.Frame(log)
        _pmf.pack(side=tk.BOTTOM, pady=3)
        ttk.Label(_pmf, text="打单方式：").pack(side=tk.LEFT)
        self.print_method_var = tk.StringVar(value=self._print_method_label())
        _pmbox = ttk.Combobox(_pmf, textvariable=self.print_method_var, state="readonly",
                              width=22, values=list(self._print_method_labels()))
        _pmbox.pack(side=tk.LEFT)
        _pmbox.bind("<<ComboboxSelected>>", lambda e: self._on_print_method_change())
        self.tree.tag_configure("ok", background=self.GREEN_BG)
        self.tree.tag_configure("alert", background=self.RED_BG)
        self.tree.tag_configure("printed", background="#FFF6CC", foreground="#B8860B")   # 已打：黄色
        self.tree.bind("<Button-1>", self._on_record_click)      # 点「已打」那一格可切换
        self.tree.bind("<Button-1>", self._on_do_print_click, add="+")   # 点「打单」那格 = 直接按可打单数量打
        # 双击整行不再切「已打」（改为只能手动点那一格）；_on_record_dblclick 保留但不再绑定

        self.scan_entry.focus()
        self._log_count = -1
        self.root.after(1500, self._poll_records)      # 手机/网页扫的码也会进这张表，定时刷新
        self.root.after(6000, self._prefetch_loop)     # 后台预取订单：点「打单」时秒开
        # 以前这里绑了 FocusIn → 强制刷新：最小化再打开拿焦点的瞬间会整块重画（闪屏）。
        # 定时轮询（本地 2 秒 / 子端 10 秒）已经够用，不靠焦点事件。

    # ---------- 登录身份 / 按钮权限 ----------
    def can(self, key):
        """当前账号能不能用这个功能。未登录（老代码路径）= 全开。"""
        if key == "__any":
            return True
        if key == "__host":                 # 只有主客户端才能做的事
            return not self.remote
        if self.remote and key in ("data.refresh", "api.settings", "gateway.settings"):
            return False                    # 这些只能在主客户端那台上做
        s = self.session
        return True if s is None else bool(s.can(key))

    def _prefetch_loop(self):
        """后台预取扫码记录里待打编码的订单（不在主线程跑，不影响界面）。"""
        try:
            codes = []
            for iid in self.tree.get_children()[:15]:
                try:
                    if "printed" in (self.tree.item(iid, "tags") or ()):
                        continue                       # 已打的不用预取
                    v = self.tree.item(iid, "values")
                    code = str(v[1]).strip() if len(v) > 1 else ""
                    qty = int(float(v[5] or 0)) if len(v) > 5 else 0
                except Exception:
                    continue
                if code and qty > 0:
                    codes.append(code)
            if codes:
                import threading

                def work(cs=codes):
                    try:
                        import kuaimai_print as K
                        for c in cs[:5]:               # 每轮最多预取 5 个编码
                            K.prefetch(c)
                    except BaseException:
                        pass
                threading.Thread(target=work, daemon=True).start()
        except Exception:
            pass
        self.root.after(45000, self._prefetch_loop)    # 每 45 秒轮一次

    def _on_do_print_click(self, event):
        """点每行末尾的「打单」格 → 直接按该行「可打单数量」打单（不弹预演）。"""
        try:
            col = self.tree.identify_column(event.x)
            row = self.tree.identify_row(event.y)
            if col != "#6" or not row:           # #6 = 可打单数量 → 直接点数字打单
                return
            if "printed" in (self.tree.item(row, "tags") or ()):
                messagebox.showinfo("打单", "这行已经是「已打」状态，不能重复打单")
                return
            vals = self.tree.item(row, "values")
            code = str(vals[1] if len(vals) > 1 else "").strip()
            try:
                qty = int(float(vals[5] or 0))   # 可打单数量
            except Exception:
                qty = 0
            if not code or qty <= 0:
                messagebox.showinfo("打单", "这行的可打单数量是 0，无法打单")
                return
            if not messagebox.askyesno(
                    "打单", "是否直接打印？\n\n编码：%s\n共 %d 单\n（会取号并出纸，不可撤回）" % (code, qty)):
                return
            self._direct_print(code, qty)
        except Exception as e:
            messagebox.showerror("打单", str(e)[:200])

    def _direct_print(self, code, qty):
        """后台直接打单（浏览器自检 → 查单/缓存 → 挑单 → 取号 → 打印；不自动标已打）。"""
        import threading
        self.status_text.set("打单中：%s ×%s …" % (code, qty))

        def work():
            try:
                import kuaimai_print as K
                st, msg = K.ensure_browser()
                if st != "ok":
                    self.root.after(0, lambda: messagebox.showinfo("打单", msg))
                    return
                picked, skipped, logs = K.do_print(code, qty, dry_run=False)
                n = len(picked or [])
                txt = "\n".join(str(x) for x in (logs or []))
                self.root.after(0, lambda: self.status_text.set(
                    "打单完成：%s 共 %d 单（请确认出纸后自行标「已打」）" % (code, n)))
                self.root.after(0, lambda: messagebox.showinfo(
                    "打单结果 %s" % code, (txt[-1600:] or "（无输出）")))
            except BaseException as e:
                self.root.after(0, lambda: messagebox.showerror("打单失败", str(e)[:200]))

        threading.Thread(target=work, daemon=True).start()

    # ---------- 自动上架（推荐货位）：独立开关 + 刷新间隔 ----------
    def _auto_putaway_on(self):
        try:
            return auto_putaway_conf()[0]
        except Exception:
            return False

    def _auto_putaway_secs(self):
        try:
            return auto_putaway_conf()[1]
        except Exception:
            return AUTO_PUTAWAY_DEFAULT_SECS

    def _toggle_auto_putaway(self):
        """独立开关：只切换自动上架，不影响自动打单。监听每轮重读设置，不用重启。"""
        from tkinter import messagebox
        try:
            on = bool(self.auto_putaway_var.get())
            _o, secs = set_auto_putaway_conf(on=on)
            self.status_text.set("自动上架：%s（每 %d 秒查一次待上架单）"
                                 % ("已开启" if on else "已关闭", secs))
            print_jobs_log("自动上架：%s（间隔 %d 秒）"
                           % ("已开启" if on else "已关闭", secs))
        except Exception as e:
            messagebox.showerror("自动上架", "切换失败：%s" % str(e)[:120])

    def _on_ap_secs(self):
        """改刷新间隔（10–3600 秒）；写入设置，监听下一轮就按新间隔跑。"""
        try:
            v = int(float(self.ap_secs_var.get()))
        except Exception:
            v = AUTO_PUTAWAY_DEFAULT_SECS
        v = max(AUTO_PUTAWAY_MIN_SECS, min(AUTO_PUTAWAY_MAX_SECS, v))
        self.ap_secs_var.set(str(v))
        try:
            set_auto_putaway_conf(secs=v)
            self.status_text.set("自动上架刷新间隔：%d 秒" % v)
        except Exception as e:
            self.status_text.set("保存刷新间隔失败：%s" % str(e)[:80])

    # ---------- 上架后自动智能审核（上架的后续动作）----------
    def _auto_audit_on(self):
        try:
            return auto_audit_conf()
        except Exception:
            return False

    def _toggle_auto_audit(self):
        """上架成功后要不要顺手把那批编码的待审核单智能审掉。

        审的是 ERP 自己的审单规则（规则不放行的会留着），**不强制放行**。
        需要打单浏览器（Edge 9222）在跑；没开就只记日志、不影响上架。
        """
        from tkinter import messagebox
        try:
            on = bool(self.auto_audit_var.get())
            set_auto_audit_conf(on=on)
            self.status_text.set("上架后自动智能审核：%s" % ("已开启" if on else "已关闭"))
            print_jobs_log("上架后自动智能审核：%s" % ("已开启" if on else "已关闭"))
        except Exception as e:
            messagebox.showerror("自动审核", "切换失败：%s" % str(e)[:120])

    # ---------- 网页自动打单 总开关（与监听器共用「暂停文件」） ----------
    def _auto_pause_flag(self):
        return auto_print_pause_flag()      # 与自动打单监听线程同源

    def _auto_print_on(self):
        return not os.path.isfile(self._auto_pause_flag())

    # ---------- 打单方式（订单打印V2 / 后置打印）----------
    def _print_method_labels(self):
        """可选打单方式的中文标签（顺序：V2 在前 = 默认）。"""
        try:
            import kuaimai_print as K
            return [K.PRINT_METHOD_LABELS[K.PRINT_METHOD_PRINTV2],
                    K.PRINT_METHOD_LABELS[K.PRINT_METHOD_POSTPRINT]]
        except Exception:
            return ["订单打印V2（滚动勾选）", "后置打印（包装验货）"]

    def _print_method_label(self):
        """当前打单方式对应的中文标签（读不到则当 V2）。"""
        try:
            import kuaimai_print as K
            return K.PRINT_METHOD_LABELS.get(K.get_print_method(),
                                             self._print_method_labels()[0])
        except Exception:
            return self._print_method_labels()[0]

    def _on_print_method_change(self):
        """切换打单方式（本地设置，只写 print_method 一个键，不动其他设置）。"""
        try:
            import kuaimai_print as K
            label = self.print_method_var.get()
            m = dict((v, k) for k, v in K.PRINT_METHOD_LABELS.items()).get(label)
            if not m:
                return
            K.set_print_method(m)
            self.status_text.set("打单方式已切换为：%s" % label)
        except Exception as e:
            messagebox.showerror("打单方式", "切换失败：%s" % str(e)[:200])

    def _toggle_auto_print(self):
        from tkinter import messagebox
        p = self._auto_pause_flag()
        try:
            if self.auto_print_var.get():
                if os.path.isfile(p):
                    os.remove(p)
                self.status_text.set("网页自动打单：已开启")
            else:
                os.makedirs(os.path.dirname(p), exist_ok=True)
                with open(p, "w", encoding="utf-8") as f:
                    f.write("paused")
                self.status_text.set("网页自动打单：已暂停")
        except Exception as e:
            messagebox.showerror("自动打单", "切换失败：%s" % str(e)[:120])

    def run_print_selected(self):
        """把选中扫码记录里的「商家编码 + 可打单数量」交给打单窗口（预演→确认→取号/打印）。"""
        from tkinter import messagebox
        rows = []
        blocked = []
        try:
            sel = self.tree.selection()
        except Exception:
            sel = []
        for iid in sel:
            try:
                v = self.tree.item(iid, "values")
            except Exception:
                continue
            if not v or len(v) < 6:
                continue
            # 「已打」判定：用行标签（应用自己就是用它把已打行标黄的），比解析文字可靠
            try:
                tags = self.tree.item(iid, "tags") or ()
            except Exception:
                tags = ()
            if "printed" in tags:
                blocked.append(str(v[1]).strip())               # 已打的行 → 不允许再打
                continue
            code = str(v[1]).strip()          # barcode = 商家编码
            try:
                qty = int(float(v[5] or 0))   # print_num = 可打单数量
            except Exception:
                qty = 0
            if code and qty > 0:
                rows.append((code, qty))
        if not rows:
            tip = "请先在上面的扫码记录里选中行（可按住 Ctrl / Shift 多选）；\n" \
                  "选中的行需要有「商家编码」和大于 0 的「可打单数量」。"
            if blocked:
                tip = "选中的行已经是「已打」状态，不能再打单（避免重复打单）：\n%s" % "、".join(blocked[:10])
            messagebox.showinfo("打单", tip)
            return
        if blocked:
            messagebox.showinfo("打单", "已跳过 %d 行「已打」状态的记录：\n%s" % (
                len(blocked), "、".join(blocked[:10])))
        try:
            import kuaimai_print_ui as _ui
        except Exception as e:
            messagebox.showerror("打单", "打单模块不可用：%s" % e)
            return
        try:
            _ui.open_window(rows, master=self.root)
        except Exception as e:
            messagebox.showerror("打单", "打开打单窗口失败：%s" % e)

    def _gate(self, key, widget, mode="disable"):
        """把控件登记进权限表：mode = disable（置灰）/ grid（整块收起）。"""
        try:
            self.gated.setdefault(key, []).append((widget, mode))
        except Exception:
            pass
        return widget

    def _apply_perms(self):
        """按当前账号权限表置灰/收起控件（只是体验；真正的拦在 _need_perm）。"""
        for key, items in (self.gated or {}).items():
            allowed = self.can(key)
            for w, mode in items:
                try:
                    if mode == "grid":
                        if allowed:
                            w.grid()
                        else:
                            w.grid_remove()
                    elif mode == "pack":
                        if allowed:
                            w.pack()
                        else:
                            w.pack_forget()
                    else:
                        w.state(["!disabled"] if allowed else ["disabled"])
                except Exception:
                    pass
        self._update_identity()

    def _update_identity(self):
        s = self.session
        if s is None or not hasattr(self, "id_label"):
            return
        try:
            who = "管理员（主账号）" if s.is_admin else "子账号"
            off = sum(1 for k, items in (self.gated or {}).items()
                      if not self.can(k) for _ in items)
            self.id_label.config(
                text="登录：%s（%s）· %s　·　无权限按钮 %d 个%s"
                     % (s.name, who, s.label(), off,
                        "　【已被踢下线，界面已锁定】" if getattr(s, "kicked", False) else ""))
        except Exception:
            pass

    def _perm_label(self, key=None, note=""):
        if note:
            return note
        try:
            if perms and key:
                return perms.LABELS.get(key) or key
        except Exception:
            pass
        return key or "这个功能"

    def _no_perm(self, key=None, note=""):
        label = self._perm_label(key, note)
        self.status_text.set("没有权限：%s（请联系主账号管理员）" % label)
        try:
            messagebox.showwarning("没有权限",
                                   "当前账号没有「%s」权限。\n请让主账号在「子客户端管理 → 权限」里给你开。" % label)
        except Exception:
            pass
        return False

    def _need_perm(self, key, note=""):
        """动作前兜底校验：按钮置灰只是体验，这里才是拦住的地方。"""
        if self._locked:
            self.status_text.set("已被管理员踢下线，请重新登录")
            return False
        if self.can(key):
            return True
        return self._no_perm(key, note)

    def _guard(self, key, fn, note=""):
        def run(*_a, **_k):
            if self._need_perm(key, note):
                return fn()
            return None
        return run

    def _need_perm_any(self, keys, note=""):
        """几个权限里有一个就行（例如改库存：改→stock.edit，改成 0→stock.zero）。"""
        if self._locked:
            self.status_text.set("已被管理员踢下线，请重新登录")
            return False
        for k in (keys or ()):
            if self.can(k):
                return True
        return self._no_perm((keys or [""])[0], note)

    def _on_kicked(self):
        """会话失效 / 被主账号踢下线：锁界面并提示。"""
        if self._locked:
            return
        self._locked = True

        def apply():
            try:
                for items in (self.gated or {}).values():
                    for w, _m in items:
                        try:
                            w.state(["disabled"])
                        except Exception:
                            pass
                self.status_text.set("已被管理员踢下线：10 分钟后可重新登录")
                self._update_identity()
                messagebox.showwarning(
                    "已下线",
                    "这个账号已被主账号踢下线（或会话已失效）。\n"
                    "界面已锁定；关闭程序重新登录即可（那台设备 10 分钟内不能再登录）。")
            except Exception:
                pass
        try:
            self.root.after(0, apply)
        except Exception:
            pass

    def _host_only(self, what="这个功能"):
        self.status_text.set("%s只能在主客户端上操作" % what)
        try:
            messagebox.showinfo("只能在主客户端上操作",
                                "%s只能在主客户端（跑着程序、持有数据和快麦凭据的那台电脑）上做。" % what)
        except Exception:
            pass

    def on_relogin(self):
        """换账号 / 被踢下线后重新登录：退出当前进程，由启动器弹登录窗。"""
        if not messagebox.askyesno("重新登录", "退出当前窗口并重新登录？"):
            return
        try:
            if self.session is not None:
                self.session.stop_heartbeat()
        except Exception:
            pass
        try:
            self.root.destroy()
        except Exception:
            pass
        os._exit(0)

    def on_admin_panel(self):
        if not self._need_perm("desktop.admin"):
            return
        if kuaimai_admin_panel is None:
            messagebox.showerror("打不开", "缺少 kuaimai_admin_panel.py")
            return
        try:
            kuaimai_admin_panel.open_admin_panel(self)
        except Exception as e:
            messagebox.showerror("打不开", str(e)[:200])

    def on_gateway_settings(self):
        if self.remote:
            return self._host_only("对外访问设置")
        if not self._need_perm("gateway.settings"):
            return
        if kuaimai_gateway_ui is None:
            messagebox.showerror("打不开", "缺少 kuaimai_gateway_ui.py")
            return
        try:
            kuaimai_gateway_ui.open_gateway_dialog(self)
        except Exception as e:
            messagebox.showerror("打不开", str(e)[:200])

    # ---------- 检查更新 ----------
    def on_check_update(self, silent=False):
        """拉 version.json 看有没有新版；silent=True 时只有发现新版才弹窗。"""
        if kmupd is None or kmupdui is None:
            if not silent:
                messagebox.showerror("检查更新", "缺少 kuaimai_update.py / kuaimai_update_ui.py")
            return
        cur = APP_VER
        if not silent:
            self.status_text.set("正在检查更新…")

        def done(info):
            try:
                if not info.get("ok"):
                    if not silent:
                        messagebox.showwarning("检查更新", str(info.get("error") or "检查失败"))
                        self.status_text.set("检查更新失败（可能没网）")
                    return
                if not info.get("has_update"):
                    self.status_text.set("已是最新版 %s" % cur)
                    if not silent:
                        messagebox.showinfo("检查更新", "已经是最新版 %s" % cur)
                    return
                if silent:
                    try:
                        if kmclient and str(kmclient.load_config().get("update_skip") or "") == str(info.get("latest")):
                            return                     # 这版已经提醒过，不再弹
                    except Exception:
                        pass
                self.status_text.set("发现新版本 %s（点「检查更新」可下载）" % info.get("latest"))
                kmupdui.ask_update(
                    self.root, info, cur,
                    on_later=lambda i: (kmclient.save_config({"update_skip": str(i.get("latest") or "")})
                                        if kmclient else None))
            except Exception:
                pass

        kmupdui.check_in_background(self.root, cur, done)

    # ---------- 子客户端（远程模式） ----------
    def _remote_startup(self):
        s = self.session
        self.loaded_at = self.shelf_at = self.lock_at = "（主客户端）"
        try:
            if getattr(s, "local_sub", False):
                self.web_label.config(
                    text="本机子客户端模式：数据来自本机主客户端 %s（这台电脑的主客户端只能用主账号登录）"
                         % (s.base if s else ""))
            else:
                self.web_label.config(
                    text="子客户端模式：数据实时来自主客户端 %s（本机不存快麦凭据、不对外服务）"
                         % (s.base if s else ""))
        except Exception:
            pass
        self.reload_records()
        self.root.after(400, self._remote_status)
        self.root.after(1000 * 60 * max(1, int(self.auto_refresh_min or 5)), self._auto_tick)

    def _remote_api(self, path, method="GET", params=None, body=None, timeout=40):
        return self.session.api(path, method, params=params, body=body, timeout=timeout)

    def _remote_err(self, obj, prefix=""):
        msg = kmclient.human_err(obj, getattr(self.session, "base", "")) if kmclient else str(obj)
        self.status_text.set((prefix or "主客户端请求失败：") + msg)
        return msg

    def _remote_status(self):
        """子客户端顶部状态：主端的订单数 / 编码数 / 更新时间（后台取，不卡界面）。"""
        def on_ok(st):
            self.loaded_at = str(st.get("loaded_at") or "未加载")
            self.shelf_at = str(st.get("shelf_at") or "未加载")
            self.lock_at = str(st.get("lock_at") or "未加载")
            self.status_text.set("主客户端数据：待发货 %s 单 / %s 个编码（订单库 %s　货位 %s）"
                                 % (st.get("live_orders", 0), st.get("codes", 0),
                                    self.loaded_at, self.shelf_at))
        self._remote_bg("/api/status", None, 20, on_ok=on_ok)

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
        if self.remote:
            return
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
        if self.remote:
            return
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

    def _load_index_async(self):
        """后台建索引（登录后不再“卡一下”）：窗口先画出来，索引好了再刷状态。"""
        try:
            relation, n = self._filter_values()
        except Exception:
            relation, n = ("any", 0)
        try:
            self.status_text.set("正在加载订单索引…（首次打开要几秒，扫码会稍等一下）")
        except Exception:
            pass

        def work():
            err = ""
            try:
                if db_orders_total() <= 0:
                    err = "empty"
                else:
                    self.index, self.stat = build_index_db(relation, n)
                    self.store_orders = int(self.stat.get("store_orders", 0) or 0)
                    self._pending_meta = load_orders_meta(
                        ("loaded_at", "last_sync_ts", "last_full_ts", "total_estimate"))
            except Exception as e:
                err = str(e)[:150]
            uikit.post(self.root, self._index_loaded, err)

        threading.Thread(target=work, daemon=True).start()

    def _index_loaded(self, err):
        """索引建完了：在 UI 线程里补上状态显示。"""
        if err == "empty":
            self.status_text.set("订单库为空，等待首次全量拉取…")
            return
        if err:
            self.status_text.set("订单索引加载失败：%s" % err)
            return
        self.index_ready = True
        try:
            meta = getattr(self, "_pending_meta", {}) or {}
            self.last_sync_ts = float(meta.get("last_sync_ts") or 0)
            self.last_full_ts = float(meta.get("last_full_ts") or 0)
            self.total_est = int(float(meta.get("total_estimate") or 0))
            self.loaded_at = meta.get("loaded_at") or "未知"
        except Exception:
            pass
        try:
            self._show_load_status(from_cache=True)
        except Exception:
            pass

    def apply_filter(self):
        """改件数筛选：纯本地重建索引，不联网。"""
        if db_orders_total() <= 0:
            self.status_text.set("订单库还没有数据，先点「全量重拉」")
            return
        self.rebuild_local()
        self._show_load_status(prefix="已按条件筛选：")

    # ---------- 首次使用（未配置 API）----------
    def _first_run_api_hint(self):
        """API 参数不完整时：只在状态栏右侧写一行字，**不弹窗、不自动开窗口**。"""
        if API_CONF.get("appKey") and API_CONF.get("sessionId"):
            self._api_state_text("已配置")
            return
        missing = [k for k in ("appKey", "appSecret", "refreshToken", "sessionId")
                   if not API_CONF.get(k)]
        self._api_state_text("未配置（缺 %s）" % "、".join(missing))
        if not self.can("api.settings"):
            self.status_text.set("快麦接口未配置：请让主客户端那台在「API 设置」里填好")
            return
        self.status_text.set("快麦接口未配置（缺 %s）：点「API 设置」填写" % "、".join(missing))

    def _api_state_text(self, state):
        """状态栏右侧常驻显示接口状态：快麦接口：已配置 / 未配置（缺 xx）。"""
        try:
            if getattr(self, "api_state_lbl", None) is not None:
                self.api_state_lbl.config(
                    text="快麦接口：%s" % state,
                    fg=("#1B7F35" if state.startswith("已配置") else "#d70015"))
        except Exception:
            pass

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
                try:
                    self._float.attributes("-topmost", False)   # 别留着置顶属性（会干扰主窗口重画）
                except Exception:
                    pass
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
                   command=self._guard("stock.export", lambda: self._export_stock(rows))).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="标记已发",
                   command=self._guard("stock.canprint", lambda: mark_sel(True))).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="撤回",
                   command=self._guard("stock.canprint", lambda: mark_sel(False))).pack(side=tk.LEFT, padx=3)
        ttk.Button(top, text="清空已发",
                   command=self._guard("stock.sent.clear", clear_all)).pack(side=tk.LEFT, padx=3)
        ttk.Button(top, text="改库存",
                   command=self._guard("stock.edit", adjust_one, "改库存")).pack(side=tk.LEFT, padx=4)
        ttk.Button(top, text="操作日志",
                   command=self._guard("stock.edit", lambda: self.on_adjust_log_dialog(), "操作日志")
                   ).pack(side=tk.LEFT, padx=4)
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
            if not self._need_perm_any(("stock.edit", "stock.zero"), "改库存"):
                return
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

        def print_row(*_a):
            """双击某行 → 按该行「编码 + 可发数量」打单（弹打单窗口，先预演再打）。"""
            try:
                sel = tree.selection()
                if not sel:
                    return
                v = tree.item(sel[0], "values")
                code = str(v[0]).strip()
                qty = int(float(v[-1] or 0))      # 最后一列 = 可发数量
            except Exception:
                return
            if not code or qty <= 0:
                messagebox.showinfo("打单", "该行可发数量为 0，不能打单")
                return
            try:
                import kuaimai_print_ui as _ui
                _ui.open_window([(code, qty)], master=self.root)
            except Exception as e:
                messagebox.showerror("打单", "打单模块不可用：%s" % e)

        tree.bind("<Double-Button-1>", print_row)      # 双击一行 = 按该行打单
        btn.configure(command=refresh)
        ent.bind("<Return>", refresh)
        cb_sort.bind("<<ComboboxSelected>>", refresh)
        cb_only.bind("<<ComboboxSelected>>", refresh)
        refresh()
        ent.focus_set()

    def _export_stock(self, rows):
        """现货可发 → Excel。"""
        if not self._need_perm("stock.export"):
            return
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
            if self.remote:                       # 子客户端：让主端去查，这边只渲染
                self._remote_batch(batch, days, btn, exp, info, tree, sumtxt)
                return
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

    def _remote_batch(self, batch, days, btn, exp, info, tree, sumtxt):
        """子客户端批次查询：主端 /api/batch 返回 orders + rows，这里照旧渲染。"""
        try:
            self.q.put(lambda: info.set("向主客户端查询批次 %s …" % batch))
            ok, res = self._remote_api("/api/batch", params={"batch": batch, "days": days}, timeout=240)
            if not ok or not isinstance(res, dict) or res.get("error"):
                msg = ""
                if isinstance(res, dict):
                    msg = str(res.get("error") or "")
                if not msg and kmclient:
                    msg = kmclient.human_err(res, self.session.base)
                self.q.put(lambda: (info.set("查询失败：%s" % (msg or "未知错误")),
                                    btn.config(state=tk.NORMAL)))
                return
            orders = []
            for o in (res.get("orders") or []):
                orders.append({"seq": o.get("seq"), "sid": o.get("sid"),
                               "short_id": o.get("short_id"), "express": o.get("express"),
                               "urgent": bool(o.get("urgent")), "sys_status": o.get("sys_status"),
                               "items": []})
            rows = []
            for r in (res.get("rows") or []):
                try:
                    o = orders[int(r.get("i") or 0)]
                except Exception:
                    continue
                rows.append([o, r.get("code") or "", r.get("num") or 0,
                             r.get("shelf") or 0, r.get("bins") or ""])
            ui = getattr(self, "_batch_ui", {}) or {}
            self.q.put(lambda: self._apply_batch(batch, orders, rows, btn, exp, info, tree, sumtxt,
                                                ui.get("pick"), ui.get("zone")))
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
            if (not self.remote) and time.time() - getattr(self, "shelf_at_ts", 0) > 120:
                self.reload_shelf(background=True)
        except Exception as e:
            info.set("渲染失败：%s" % str(e)[:120])
        finally:
            btn.config(state=tk.NORMAL)

    def on_pick_file(self):
        """从 ERP 导出的「批次打印记录」Excel/CSV 出拣货清单（不依赖接口）。"""
        if not self._need_perm("batch.file"):
            return
        if self.remote:
            return self._host_only("读取 ERP 导出文件")
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
        if not self._need_perm("export.excel"):
            return
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

    # ---------- 打印分工（账号 → 哪台电脑 + 本机打印身份）----------
    def on_print_clients(self):
        """弹出「打印分工」设置窗（新增窗口，不动主界面既有布局）。

        主端：账号分工 + 本机身份都能改；子端：账号分工置灰提示"只能在主端设置"，
        本机身份照改（每台电脑各存一份 print_client.json）。
        """
        try:
            PrintClientsDialog(self, parent=self.root)
        except Exception as e:
            messagebox.showerror("打印分工", "打不开设置窗口：%s" % str(e)[:200])

    # ---------- 打单进度（实时面板）----------
    def on_print_progress(self):
        """弹出「打单进度」实时面板（新增窗口，不动主界面既有布局）。"""
        try:
            PrintProgressDialog(self, parent=self.root)
        except Exception as e:
            messagebox.showerror("打单进度", "打不开进度窗口：%s" % str(e)[:200])

    # ---------- API 设置 ----------
    def on_api_settings(self):
        """改 appKey/appSecret/refreshToken/session/网关/版本 —— 换账号不用重新打包。"""
        if self.remote:
            return self._host_only("API 设置")
        if not self._need_perm("api.settings"):
            return
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
        if self.remote:
            return
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
        if self.remote:
            return
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
        if self.remote:                       # 子客户端：只需刷新状态与扫码记录
            self._remote_status()
            self._poll_records(force=True)
            self.root.after(1000 * 60 * max(1, int(self.auto_refresh_min or 5)), self._auto_tick)
            return
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
        """扫码查询的干活线程（本地索引）。"""
        if not getattr(self, "index_ready", True):
            self.q.put(lambda: self._finish_scan("订单索引还在加载，等几秒再扫一下"))
            return
        try:
            if self.remote:                       # 子客户端：让主端算（含权限校验 + 写扫码记录）
                self._remote_scan(code, from_hook)
                return
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
                                               bins, lock_n, sell_n, avail_n, from_hook,
                                               (entry or {}).get("ue")))
        except Exception as e:
            msg = str(e)[:200]
            self.q.put(lambda: self._finish_scan("扫码查询失败：%s" % msg))

    def _remote_scan(self, code, from_hook=False):
        """子客户端扫码：主端 /api/lookup 算好（含权限校验与写扫码记录），这边只负责显示。"""
        rel_cn, n = self._filter_values()
        rel = {"大于": "gt", "小于": "lt", "等于": "eq"}.get(str(rel_cn), "any")
        ok, out = self._remote_api("/api/lookup", params={"code": code, "rel": rel, "n": n}, timeout=45)
        if not ok or not isinstance(out, dict) or out.get("error"):
            msg = kmclient.human_err(out, self.session.base) if kmclient else "查询失败"
            self.q.put(lambda: self._finish_scan("扫码查询失败：%s" % msg))
            return
        if out.get("series"):
            lines = []
            for it in (out.get("items") or []):
                lines.append("%-22s 货位 %-16s 在架 %-6s 待发货 %-5s 锁定 %s"
                             % (it.get("code"), it.get("bins") or "无货位", it.get("shelf"),
                                "%s件/%s单" % (it.get("qty"), it.get("orders")), it.get("lock")))
            total = int(out.get("total") or len(lines))
            self.q.put(lambda: self._apply_series(out.get("code") or code, lines, total,
                                                  max(0, total - len(lines))))
            return
        canon = str(out.get("code") or code)
        pending = int(out.get("pieces") or 0)
        orders_count = int(out.get("orders") or 0)
        ones = int(out.get("ones") or 0)
        shelf = int(out.get("shelf") or 0)
        bins = out.get("bins") or []
        self.shelf_at = str(out.get("shelf_at") or self.shelf_at)
        self.lock_at = str(out.get("lock_at") or self.lock_at)
        note = "主客户端货位缓存 %s" % out.get("shelf_at")
        self.q.put(lambda: self._apply_scan(canon, orders_count, pending, ones, shelf, note, bins,
                                            int(out.get("lock") or 0), int(out.get("sellable") or 0),
                                            int(out.get("avail") or 0), from_hook, out.get("ue")))

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
                    lock_n=0, sell_n=0, avail_n=0, from_hook=False, ue=None):
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
        self.tree.insert("", 0, values=(now_gmt8(), code, orders_count, shelf,
                                        "桌面版·%s" % (os.environ.get("USERNAME") or "本机"),
                                        "", int((ue or {}).get("中通") or 0),
                                        int((ue or {}).get("申通") or 0), "【打单】"),
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
        if not self._need_perm("export.excel"):
            return
        if self.remote:                       # 子客户端：让主端生成 Excel，这边只负责存盘
            ok, data = self._remote_api("/api/scans/export", timeout=180)
            if not ok or not isinstance(data, (bytes, bytearray)):
                messagebox.showerror("导出失败",
                                     kmclient.human_err(data, self.session.base) if kmclient else "导出失败")
                return
            path = filedialog.asksaveasfilename(defaultextension=".xlsx", initialfile="扫码日志.xlsx",
                                               filetypes=[("Excel 文件", "*.xlsx")], title="导出扫码日志")
            if not path:
                return
            try:
                with open(path, "wb") as f:
                    f.write(bytes(data))
            except Exception as e:
                messagebox.showerror("导出失败", str(e)[:200])
                return
            self.status_text.set("已导出扫码日志：%s" % path)
            messagebox.showinfo("导出成功", "已导出到：\n%s" % path)
            return
        try:
            path, n = export_scans_to_excel()
            self.status_text.set("已导出 %d 条扫码日志：%s" % (n, path))
            messagebox.showinfo("导出成功", "已导出 %d 条扫码日志到：\n%s" % (n, path))
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    def on_clear_logs(self):
        if self.remote:
            return self._host_only("清空扫码日志")
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
        刷新失败不推进计数，下次继续重试。子客户端：查条数也走后台（不能卡界面）。"""
        if self.remote:
            def work():
                ok, res = self._remote_api("/api/scans", params={"limit": 1}, timeout=20)

                def done():
                    n = None
                    if ok and isinstance(res, dict):
                        try:
                            n = int(res.get("count") or 0)
                        except Exception:
                            n = None
                    self._after_poll_count(n, force)

                if uikit is not None:
                    uikit.post(self.root, done)
                else:
                    try:
                        self.root.after(0, done)
                    except Exception:
                        pass

            threading.Thread(target=work, daemon=True).start()
            return
        try:
            conn = get_conn()
            n = int(conn.cursor().execute("SELECT COUNT(*) FROM scan_record "
                                          "WHERE COALESCE(hold_until,0) <= ?",
                                          (int(time.time()),)).fetchone()[0])
            conn.close()
        except Exception:
            n = None
        self._after_poll_count(n, force)

    def _after_poll_count(self, n, force=False):
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
            self.root.after(2000 if not self.remote else 10000, self._poll_records)
        except Exception:
            pass

    def _toast(self, text, ms=900):
        """屏幕右下角小提示（复制成功之类），自动消失。"""
        try:
            tt = tk.Toplevel(self.root)
            tt.overrideredirect(True)
            tt.attributes("-topmost", True)
            tk.Label(tt, text=text, bg="#1e9e4a", fg="white",
                     font=("Microsoft YaHei", 12, "bold"), padx=14, pady=8).pack()
            tt.update_idletasks()
            tt.geometry("+%d+%d" % (self.root.winfo_pointerx() + 14, self.root.winfo_pointery() + 14))
            tt.after(ms, lambda: (tt.destroy() if tt.winfo_exists() else None))
        except Exception:
            pass

    def _on_record_click(self, event):
        """点「已打」那一格 → 标记为已打（单向，之后锁定不可再点）；双击整行也可以。"""
        try:
            col = self.tree.identify_column(event.x)
            row = self.tree.identify_row(event.y)
            if col == "#2" and row:                    # 第 2 列 = 商家编码 → 点一下就复制
                vals = self.tree.item(row, "values")
                code = str(vals[1] if len(vals) > 1 else "").strip()
                if code:
                    try:
                        self.root.clipboard_clear()
                        self.root.clipboard_append(code)
                        self.root.update_idletasks()
                    except Exception:
                        pass
                    self.status_text.set("已复制商家编码：%s" % code)
                    self._toast("复制成功：" + code)
                return
            if col != "#9":               # 已打列（回到 #9：已去掉那一列）
                return
            if row:
                self._mark_printed(row)
        except Exception:
            pass

    def _on_record_dblclick(self, event):
        try:
            row = self.tree.identify_row(event.y)
            if row:
                self._mark_printed(row)
        except Exception:
            pass

    def _mark_printed(self, row):
        """单向：打单 → 已打。已打后锁定（再点无效），整行保持黄色。"""
        try:
            if not self._need_perm("scan.printed"):
                return
            vals = list(self.tree.item(row, "values"))
            if len(vals) >= 9 and "已打" in str(vals[8]):
                self.status_text.set("这条已经是「已打」，已锁定")
                return
            try:
                rid = int(row)             # 行 iid = 记录 id；新扫的临时行（未入库）忽略
            except Exception:
                self.status_text.set("这条是刚扫的新记录，稍后自动刷新后再点")
                return
            self._touch_ts = time.time()   # 3 秒内不让定时刷新重建行
            self._apply_printed(row, 1)
            if self.remote:
                okw, res = self._remote_api("/api/scans/printed", "POST", body={"id": rid, "flag": 1})
                wrote = bool(okw and isinstance(res, dict) and res.get("ok"))
            else:
                wrote = bool(set_printed(rid, 1, by="电脑端界面点「已打」"))
            if wrote:
                self.status_text.set("已标记：已打（该条已锁定）")
            else:
                self._apply_printed(row, 0)     # 写失败回滚成打单，可再点
                self.status_text.set("「已打」没能写入数据库，请再点一次")
        except Exception:
            pass

    def _apply_printed(self, iid, flag):
        try:
            vals = list(self.tree.item(iid, "values"))
            if len(vals) > 8:
                vals[8] = "【已打】" if flag else "【打单】"
                self.tree.item(iid, values=vals, tags=("printed",) if flag else ())
        except Exception:
            pass

    def reload_records(self, background=True):
        """刷新扫码记录。子客户端的 HTTP 全走后台线程（域名/frp 慢，绝不卡界面）。"""
        if self.remote:
            self._remote_bg("/api/scans", {"limit": 500}, 30,
                            on_ok=lambda res: self._render_records(self._rows_from_remote(res)),
                            label="正在读取扫码记录…")
            return
        self._render_records(self._rows_from_local())

    def _rows_from_local(self):
        """本地库 → 行列表（含中通/申通加急，按编码从本地索引取）。"""
        rows = []
        for r in fetch_all_scans():
            pid, st, bc, pq, sh, _oc, light = r[:7]
            who = r[7] if len(r) > 7 else ""
            pnum = r[8] if len(r) > 8 else ""
            prn = int(r[9] or 0) if len(r) > 9 else 0
            e, _k = dict_get_ci(self.index or {}, bc)
            ue = (e or {}).get("ue") or {}
            rows.append({"id": pid, "time": st, "code": bc, "pending": pq or 0,
                         "shelf": sh or 0, "ok": (light == "绿"), "who": who,
                         "pnum": pnum, "prn": prn,
                         "zt": int(ue.get("中通") or 0), "st": int(ue.get("申通") or 0)})
        return rows

    def _rows_from_remote(self, res):
        """主端 /api/scans 的返回 → 行列表。"""
        rows = []
        for r in ((res or {}).get("rows") or []):
            ue = r.get("ue") or {}
            rows.append({"id": r.get("id"), "time": r.get("time"), "code": r.get("code"),
                         "pending": r.get("pending") or 0, "shelf": r.get("shelf") or 0,
                         "ok": bool(r.get("ok")), "who": r.get("who") or "",
                         "pnum": r.get("print_num") or "", "prn": int(r.get("printed") or 0),
                         "zt": int(ue.get("中通") or 0), "st": int(ue.get("申通") or 0)})
        return rows

    def _render_records(self, rows):
        """把行列表画到表上（UI 线程）。

        **增量刷新**：只增删/更新真正变了的行 —— 以前是清空重插，最小化再打开时
        （FocusIn 会触发一次强制刷新）整张表会闪一下。
        """
        tree = self.tree
        try:
            acc = (self.acc_var.get() if getattr(self, "acc_var", None) else "") or "全部"
        except Exception:
            acc = "全部"
        # 账号下拉：列出记录里出现过的扫码账号（用全量行，不受筛选影响）
        accs = ["全部"]
        for r in rows:
            w = r.get("who") or ""
            if w and w not in accs:
                accs.append(w)
        try:
            if getattr(self, "acc_box", None):
                if getattr(self, "_acc_list", None) != accs:      # 列表没变就不动下拉（少一次重画）
                    self._acc_list = list(accs)
                    self.acc_box.configure(values=accs)
                if acc not in accs:
                    acc = "全部"
                    self.acc_var.set("全部")
        except Exception:
            pass

        def _vals(r):
            return (r.get("time"), r.get("code"), r.get("pending"), r.get("shelf"),
                    r.get("who") or "（本机扫码）", r.get("pnum") or "", r.get("zt") or 0,
                    r.get("st") or 0, "【已打】" if r.get("prn") else "【打单】")

        def _tags(r):
            return ("printed",) if r.get("prn") else (("ok",) if r.get("ok") else ("alert",))

        want = {}
        for r in rows:
            if acc != "全部" and (r.get("who") or "") != acc:
                continue
            want[str(r.get("id"))] = r
        shown = getattr(self, "_shown_rows", None)
        if shown is None:
            shown = {}
            self._shown_rows = shown
        changed = False
        for iid in list(shown.keys()):                     # 1) 不在列表里的删掉
            if iid not in want:
                try:
                    tree.delete(iid)
                except Exception:
                    pass
                shown.pop(iid, None)
                changed = True
        for iid, r in want.items():                        # 2) 新的插到最上面，变了的改值
            v = _vals(r)
            if iid in shown:
                if shown[iid] != v:
                    try:
                        tree.item(iid, values=v, tags=_tags(r))
                    except Exception:
                        pass
                    shown[iid] = v
                    changed = True
            else:
                try:
                    tree.insert("", 0, iid=iid, values=v, tags=_tags(r))
                    shown[iid] = v
                    changed = True
                except Exception:
                    pass
        if changed:
            try:
                tree.yview_moveto(0)      # 有变化才回到顶部，避免无谓跳动
            except Exception:
                pass

    def _remote_bg(self, path, params=None, timeout=25, on_ok=None, label=""):
        """子客户端：所有主端请求都丢后台线程，回来再用 uikit 刷界面（不卡）。"""
        if label:
            try:
                self.status_text.set(label)
            except Exception:
                pass

        def work():
            ok, res = self._remote_api(path, params=params, timeout=timeout)

            def done():
                if ok and isinstance(res, dict) and not res.get("error"):
                    if on_ok:
                        try:
                            on_ok(res)
                        except Exception:
                            pass
                else:
                    self._remote_err(res)

            if uikit is not None:
                uikit.post(self.root, done)
            else:
                try:
                    self.root.after(0, done)
                except Exception:
                    pass

        threading.Thread(target=work, daemon=True).start()


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


def auto_print_pause_flag():
    """「网页提交后自动打单」总开关文件（存在=暂停）。界面勾选框与监听线程同源。"""
    return os.path.join(os.environ.get("LOCALAPPDATA") or os.path.expanduser("~"),
                        "KuaimaiScan", "auto_print_pause.flag")


# ==================== 自动上架（推荐货位）====================
# 纯**开放平台 API**：查待上架 → 本地算推荐货位 → 上架。不依赖浏览器/登录态。
# 独立于「自动打单」的开关 + 可调间隔，都存在 kuaimai_settings.json 里，
# 监听每轮重读，界面改了立刻生效。
AUTO_PUTAWAY_DEFAULT_SECS = 60        # 默认间隔（秒）
AUTO_PUTAWAY_MIN_SECS = 10
AUTO_PUTAWAY_MAX_SECS = 3600
AUTO_AUDIT_LOOKBACK_DAYS = 7          # 「上架后自动智能审核」找待审核单的回溯天数


def auto_putaway_conf():
    """自动上架设置 → (开关, 间隔秒)。开关与「自动打单」互相独立。"""
    s = load_settings() or {}
    on = bool(s.get("auto_putaway_on", False))
    try:
        secs = int(float(s.get("auto_putaway_secs", AUTO_PUTAWAY_DEFAULT_SECS)))
    except Exception:
        secs = AUTO_PUTAWAY_DEFAULT_SECS
    return on, max(AUTO_PUTAWAY_MIN_SECS, min(AUTO_PUTAWAY_MAX_SECS, secs))


def set_auto_putaway_conf(on=None, secs=None):
    """写自动上架设置：**只改这两个键**，其他设置原样保留（与 set_print_method 同做法）。"""
    s = load_settings() or {}
    if on is not None:
        s["auto_putaway_on"] = bool(on)
    if secs is not None:
        try:
            v = int(float(secs))
        except Exception:
            v = AUTO_PUTAWAY_DEFAULT_SECS
        s["auto_putaway_secs"] = max(AUTO_PUTAWAY_MIN_SECS, min(AUTO_PUTAWAY_MAX_SECS, v))
    save_settings(s)
    return auto_putaway_conf()


def auto_audit_conf():
    """上架后自动智能审核 → 开关（默认 **关**）。

    用户口径：「操作完上架单还要智能审核才能去打印快递单」。
    只在上架成功且本开关打开时才触发；审核走 ERP 自己的审单规则（不强制放行）。
    """
    s = load_settings() or {}
    return bool(s.get("auto_audit_on", False))


def set_auto_audit_conf(on=None):
    """写自动审核开关（只改这一个键，其他设置原样保留）。"""
    s = load_settings() or {}
    if on is not None:
        s["auto_audit_on"] = bool(on)
    save_settings(s)
    return auto_audit_conf()


def _load_shelf_map_now():
    r"""从订单库现读一份货位索引（界面实例拿不到时兜底）。**找不到库就报错，不新建空库**。

    坑：`ORDERS_DB_FILE` 在模块导入时就定死了 —— 源码模式下它会指向 desktop\，
    而真实库在 %LOCALAPPDATA%\KuaimaiScan\。若直接把不存在的路径交给
    `kuaimai_db.connect()`，它会**建一个空库**并返回空货位表，
    后果是「每张单都推荐不出货位 → 静默全部跳过」。所以只挑**已存在**的库，
    且有货位数据的优先；一个都没有就抛错（监听会记日志并跳过本轮，不用空表乱推）。
    """
    cands = []
    for p in (ORDERS_DB_FILE,
              os.path.join(os.environ.get("LOCALAPPDATA") or "", "KuaimaiScan", "kuaimai_data.db"),
              os.path.join(BASE_DIR, "kuaimai_data.db")):
        if p and os.path.isfile(p) and os.path.abspath(p) not in [os.path.abspath(x) for x in cands]:
            cands.append(p)
    if not cands:
        raise RuntimeError("找不到订单库（货位索引读不到）")
    cands.sort(key=lambda p: -os.path.getsize(p))     # 大的更可能是真库，空库排后面
    best = None
    for p in cands:
        try:
            conn = kuaimai_db.connect(p, check_same_thread=True)
            try:
                m = kuaimai_db.load_shelf(conn) or {}
            finally:
                conn.close()
            if m:
                return m
            if best is None:
                best = m
        except Exception:
            continue
    if best is not None:
        raise RuntimeError("订单库里没有货位数据（请先在主程序「刷新货位库存」）")
    raise RuntimeError("订单库都读不开（货位索引读不到）")


def start_auto_putaway_watcher(session=None, shelf_map_getter=None):
    """自动上架（推荐货位）监听放进主程序 daemon 线程。

    · 纯开放平台 API：`erp.purchase.shelf.query/get/save` + 本地货位索引，**不用浏览器**；
    · 只在**主客户端**跑（子端没有开放平台 API 配置）；
    · 开关与间隔每轮从设置里重读 → 界面改了立刻生效，不用重启；
    · 推荐不出货位的单**整张跳过**，只记日志等人工，绝不乱猜货位。
    """
    if _WEB_STATE.get("auto_putaway_thread") is not None:
        return _WEB_STATE.get("auto_putaway_thread")
    mode = str(getattr(session, "mode", "") or "")
    if session is not None and mode != "host":
        print_jobs_log("自动上架只在主客户端运行（子端没有 API 配置）")
        return None
    try:
        import auto_putaway as ap
    except Exception as e:
        print_jobs_log("自动上架模块加载失败：%s" % str(e)[:120])
        return None

    def api(method, biz, timeout=60):
        return api_call_authed(method, biz, timeout=timeout)

    def getter():
        if shelf_map_getter is not None:
            try:
                m = shelf_map_getter() or {}
                if m:
                    return m
            except Exception:
                pass
        return _load_shelf_map_now()

    stop = threading.Event()
    _WEB_STATE["auto_putaway_stop"] = stop

    def on_done(codes):
        """上架成功后：若开了「上架后自动智能审核」→ 把这批编码的待审核单智能审掉。

        用户口径：「操作完上架单还要智能审核才能去打印快递单」。
        **未开开关就直接返回**（不影响上架）；审核异常也不影响上架（process_once 已兜住）。
        """
        if not auto_audit_conf():
            return
        try:
            import auto_audit as aa
        except Exception as e:
            print_jobs_log("自动审核模块加载失败：%s" % str(e)[:120])
            return

        def cdp_factory():
            import kuaimai_print as KP
            return KP.open_cdp_page()

        n, lines = aa.audit_codes(cdp_factory, api, codes,
                                  days=AUTO_AUDIT_LOOKBACK_DAYS)
        for ln in lines:
            print_jobs_log("[自动审核]%s" % ln)
        if n:
            print_jobs_log("[自动审核] 已审 %d 单（编码：%s）"
                           % (n, "、".join(list(codes)[:8])))

    def run():
        try:
            ap.watch(api=api, shelf_map_getter=getter, stop_event=stop,
                     log_path=os.path.join(BASE_DIR, "auto_putaway.log"),
                     is_on=lambda: auto_putaway_conf()[0],
                     on_done=on_done)
        except BaseException:
            pass

    t = threading.Thread(target=run, daemon=True, name="auto-putaway-watcher")
    _WEB_STATE["auto_putaway_thread"] = t
    t.start()
    _on, _secs = auto_putaway_conf()
    print_jobs_log("自动上架监听已启动（开关 %s，每 %d 秒查一次待上架单）"
                   % ("开" if _on else "关", _secs))
    return t


def start_auto_print_watcher(db_path=None, session=None):
    """把「打单」监听放进主程序的 daemon 线程（不再另发一个 exe）。

    · 本机设过「本机打印身份」（print_client.json）→ **认领模式**：向本机主端
      `POST /api/print/claim` 认领属于本机的任务 → 打单 → `POST /api/print/report` 回写。
      主端自己也一样（主端=pc1，也是向 127.0.0.1 的本机服务认领），
      所以「网页提交 → 建任务 → 哪台认领 → 就打」是一条链路。
    · 没设身份（主端）→ 保持原来的「读本机 scan_record」模式，行为不变。
    · 子端没设身份时不做任何事（它没有本机库，原来也不该读）。
    · 单实例保护已在 main() 里做过，这里只保证同一个进程内不起两个监听线程。
    """
    if _WEB_STATE.get("auto_print_thread") is not None:
        return _WEB_STATE.get("auto_print_thread")
    try:
        import auto_print_watcher as apw
    except Exception:
        return None
    mode = str(getattr(session, "mode", "") or "")
    is_host = (session is None) or (mode == "host")
    client = read_local_print_client()

    def api(path, method="GET", params=None, body=None, timeout=25):
        # 复用现有会话/主端地址机制：主端 → 127.0.0.1:本机端口；子端 → session.base
        if session is not None:
            return session.api(path, method=method, params=params, body=body, timeout=timeout)
        import kuaimai_client as kc
        base = "http://127.0.0.1:%d" % int(_WEB_STATE.get("port") or WEB_PORT)
        return kc.http_json(base, path, method=method, params=params, body=body, timeout=timeout)

    stop = threading.Event()
    _WEB_STATE["auto_print_stop"] = stop
    db = db_path or DB_FILE
    log_path = os.path.join(BASE_DIR, "auto_print.log")
    pause_path = auto_print_pause_flag()

    if client:
        def run():
            try:
                apw.watch_claims(api=api, client=client, stop_event=stop, log_path=log_path,
                                 pause_path=pause_path)
            except BaseException:
                pass
        why = "认领模式（本机身份 %s）" % client
    elif is_host:
        def run():
            try:
                apw.watch(stop_event=stop, db=db, log_path=log_path, pause_path=pause_path)
            except BaseException:
                pass
        why = "原本地模式（未设本机身份）"
    else:
        print_jobs_log("子端未设「本机打印身份」，认领没开"
                       "（请在「打印分工」里给这台电脑选 pc1/pc2/pc3）")
        return None

    t = threading.Thread(target=run, daemon=True, name="auto-print-watcher")
    _WEB_STATE["auto_print_thread"] = t
    t.start()
    print_jobs_log("自动打单监听已启动：%s" % why)
    return t


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
    if ask_login is None or kmclient is None:
        try:
            messagebox.showerror("启动失败", "缺少桌面端登录模块（kuaimai_client.py / kuaimai_login_window.py），请重新安装。")
        except Exception:
            pass
        return
    root = tk.Tk()
    root.withdraw()
    session = None
    try:
        session = ask_login(root, lambda: ensure_web_server(None, lan=False), default_port=WEB_PORT)
    except Exception:
        detail = traceback.format_exc()
        try:
            sys.stderr.write(detail)
        except Exception:
            pass
        try:
            messagebox.showerror("登录窗打不开", detail)
        except Exception:
            pass
    if session is None:
        try:
            root.destroy()
        except Exception:
            pass
        return
    if session.mode == "host":
        if _single_instance_guard() is False:
            try:
                messagebox.showwarning(
                    "已经在运行",
                    "快麦扫码查询（主客户端）已经在运行了。\n\n"
                    "请直接用屏幕上已经开着的那个窗口；不要开两个，\n"
                    "两个窗口会抢同一个数据库，扫码会没反应。")
            except Exception:
                pass
            try:
                root.destroy()
            except Exception:
                pass
            return
    else:
        stop_web_server()      # 子客户端：本机不对外服务，也不广播
    try:
        session._port = int(_WEB_STATE.get("port") or WEB_PORT)
        root.deiconify()
        app = ScanApp(root, session)
        try:
            session.start_heartbeat()
        except Exception:
            pass
        try:
            # 主端/子端都起：设过「本机打印身份」就走认领模式（各打各的活），
            # 主端没设身份时保持原来的「读本机 scan_record」模式。
            start_auto_print_watcher(DB_FILE if session.mode == "host" else None,
                                     session=session)
        except Exception:
            pass
        try:
            # 自动上架（推荐货位）：独立开关 + 可调间隔，纯开放平台 API（只在主客户端跑）
            start_auto_putaway_watcher(
                session, shelf_map_getter=lambda: getattr(app, "shelf_map", {}) or {})
        except Exception:
            pass
        _note_login(session.name, session.role, session.mode)
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
