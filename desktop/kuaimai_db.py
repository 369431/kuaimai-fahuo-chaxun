# -*- coding: utf-8 -*-
"""SQLite 存储层：订单缓存从 JSON 迁到数据库。

表结构：
  orders(sid, sys_status, us, item_count, upd_ts)      订单主表
  order_items(sid, code, qty, is_main)                 订单商品明细（code 建索引）
  shelf(code, qty, bins)                               货位在架数
  lock(code, lck, sellable, avail)                     库存锁定数
  meta(k, v)                                           版本 / 数据时间

与 JSON 版语义完全一致：
  · 已发货剔除只看 orders.sys_status（SELLER_SEND_GOODS/FINISHED/CLOSED）
  · 编码计数按「明细行」累加（主编码已由 pairs 展开，和 JSON 版一致）
"""
import json
import os
import sqlite3
import time

SHIPPED = ("SELLER_SEND_GOODS", "FINISHED", "CLOSED")
SHIPPED_SQL = ",".join("'%s'" % s for s in SHIPPED)

SCHEMA = """
CREATE TABLE IF NOT EXISTS orders(
  sid TEXT PRIMARY KEY, sys_status TEXT, us TEXT, item_count INTEGER, upd_ts REAL);
CREATE TABLE IF NOT EXISTS order_items(
  sid TEXT, code TEXT, qty INTEGER, is_main INTEGER);
CREATE INDEX IF NOT EXISTS idx_items_code ON order_items(code);
CREATE INDEX IF NOT EXISTS idx_items_sid ON order_items(sid);
CREATE TABLE IF NOT EXISTS shelf(code TEXT PRIMARY KEY, qty INTEGER, bins TEXT);
CREATE TABLE IF NOT EXISTS lock(code TEXT PRIMARY KEY, lck INTEGER, sellable INTEGER, avail INTEGER);
CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
"""


def connect(path, check_same_thread=True):
    """打开（并按需建表）。多线程共享连接时传 check_same_thread=False 并自行加锁。"""
    conn = sqlite3.connect(path, timeout=60, check_same_thread=check_same_thread)
    conn.executescript(SCHEMA)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


# ---------------------------------------------------------------- 口径表达式
def _ship_expr(col):
    """与 JSON 版 _rec_shipped 一致：strip().upper() 后判等；NULL 当空串。"""
    return "UPPER(TRIM(COALESCE(%s,'')))" % col


def live_where(alias=""):
    """「未发货」条件（JSON 版 _rec_shipped() 为 False）。"""
    col = (alias + ".sys_status") if alias else "sys_status"
    return "%s NOT IN (%s)" % (_ship_expr(col), SHIPPED_SQL)


def shipped_where(alias=""):
    """「已发货」条件。"""
    col = (alias + ".sys_status") if alias else "sys_status"
    return "%s IN (%s)" % (_ship_expr(col), SHIPPED_SQL)


def _count_filter(relation, n):
    """件数筛选 SQL 片段（与界面「大于/小于/等于」一致），orders 别名固定为 o。"""
    try:
        n = int(n or 0)
    except Exception:
        n = 0
    if relation == "大于":
        return " AND o.item_count > ?", [n]
    if relation == "小于":
        return " AND o.item_count < ?", [n]
    if relation == "等于":
        return " AND o.item_count = ?", [n]
    return "", []


def _chunks(seq, size=400):
    seq = list(seq)
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


# ---------------------------------------------------------------- 写入
def _record_rows(sid, rec):
    """一条 store 记录 → (orders 行, order_items 行列表)。"""
    out = (str(sid), rec.get("status"), rec.get("us"),
           int(rec.get("count") or 0), time.time())
    items = []
    for pair in (rec.get("pairs") or []):
        try:
            code, qty = pair[0], int(pair[1] or 0)
        except Exception:
            continue
        items.append((str(sid), str(code), qty, 0))
    return out, items


def import_store(conn, store, loaded_at="", replace=True):
    """把 JSON 版 store（sid -> {status, us, count, pairs}）整体导入数据库。

    store 为空时拒绝写入（安全阀：空结果绝不覆盖已有数据）。
    """
    if not store:
        raise ValueError("空结果，拒绝写入订单库")
    rows, items = [], []
    for sid, rec in store.items():
        o, it = _record_rows(sid, rec)
        rows.append(o)
        items.extend(it)
    cur = conn.cursor()
    try:
        if replace:
            cur.execute("DELETE FROM orders")
            cur.execute("DELETE FROM order_items")
        cur.executemany("INSERT OR REPLACE INTO orders VALUES(?,?,?,?,?)", rows)
        cur.executemany("INSERT INTO order_items VALUES(?,?,?,?)", items)
        if loaded_at:
            cur.execute("INSERT OR REPLACE INTO meta VALUES('loaded_at',?)", (loaded_at,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return len(rows), len(items)


def upsert_records(conn, records, delete_sids=(), commit=True):
    """按 sid UPSERT（增量同步）：orders 一行 + order_items 若干行。

    records: [(sid, rec), ...]；delete_sids: 离开待发货口径的 sid（连带明细删除）。
    """
    cur = conn.cursor()
    try:
        for chunk in _chunks([str(s) for s in delete_sids]):
            ph = ",".join("?" * len(chunk))
            cur.execute("DELETE FROM order_items WHERE sid IN (%s)" % ph, chunk)
            cur.execute("DELETE FROM orders WHERE sid IN (%s)" % ph, chunk)
        rows, items = [], []
        for sid, rec in records:
            o, it = _record_rows(sid, rec)
            rows.append(o)
            items.extend(it)
        for chunk in _chunks([r[0] for r in rows]):
            ph = ",".join("?" * len(chunk))
            cur.execute("DELETE FROM order_items WHERE sid IN (%s)" % ph, chunk)
        cur.executemany("INSERT OR REPLACE INTO orders VALUES(?,?,?,?,?)", rows)
        cur.executemany("INSERT INTO order_items VALUES(?,?,?,?)", items)
        if commit:
            conn.commit()
    except Exception:
        conn.rollback()
        raise
    return len(rows), len(items)


def save_shelf(conn, shelf_map):
    rows = [(code, int(e.get("shelf") or 0), json.dumps(e.get("bins") or [], ensure_ascii=False))
            for code, e in shelf_map.items()]
    try:
        conn.execute("DELETE FROM shelf")
        conn.executemany("INSERT OR REPLACE INTO shelf VALUES(?,?,?)", rows)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return len(rows)


def save_lock(conn, lock_map):
    rows = [(code, int(e.get("lock") or 0), int(e.get("sellable") or 0), int(e.get("avail") or 0))
            for code, e in lock_map.items()]
    try:
        conn.execute("DELETE FROM lock")
        conn.executemany("INSERT OR REPLACE INTO lock VALUES(?,?,?,?)", rows)
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return len(rows)


# ---------------------------------------------------------------- meta
def set_meta(conn, kv):
    conn.executemany("INSERT OR REPLACE INTO meta VALUES(?,?)",
                     [(k, "" if v is None else str(v)) for k, v in kv.items()])
    conn.commit()


def get_meta(conn, key, default=""):
    row = conn.execute("SELECT v FROM meta WHERE k=?", (key,)).fetchone()
    return row[0] if row and row[0] is not None else default


def get_meta_float(conn, key, default=0.0):
    try:
        return float(get_meta(conn, key, default) or default)
    except Exception:
        return float(default)


def get_meta_int(conn, key, default=0):
    try:
        return int(float(get_meta(conn, key, default) or default))
    except Exception:
        return int(default)


# ---------------------------------------------------------------- 读取 / 聚合
def orders_total(conn):
    return conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0] or 0


def shelf_total(conn):
    return conn.execute("SELECT COUNT(*) FROM shelf").fetchone()[0] or 0


def lock_total(conn):
    return conn.execute("SELECT COUNT(*) FROM lock").fetchone()[0] or 0


def index_counts(conn, relation="不限", n=0):
    """SQL 聚合：编码 -> [订单数, 件数, 一件订单数]（已发货不计，可加件数条件）。"""
    filt, args = _count_filter(relation, n)
    q = ("SELECT i.code, COUNT(*), COALESCE(SUM(i.qty),0),"
         " SUM(CASE WHEN o.item_count = 1 THEN 1 ELSE 0 END)"
         " FROM order_items i JOIN orders o ON o.sid = i.sid"
         " WHERE " + live_where("o") + filt +
         " GROUP BY i.code")
    out = {}
    for code, orders, pieces, ones in conn.execute(q, args):
        out[code] = [int(orders or 0), int(pieces or 0), int(ones or 0)]
    return out


def orders_stat(conn, relation="不限", n=0):
    """与 JSON 版 rebuild_index 的 stat 同字段同口径。"""
    filt, args = _count_filter(relation, n)
    store_orders = orders_total(conn)
    live = conn.execute("SELECT COUNT(*) FROM orders o WHERE " + live_where("o")).fetchone()[0] or 0
    shipped = conn.execute("SELECT COUNT(*) FROM orders o WHERE " + shipped_where("o")).fetchone()[0] or 0
    included = conn.execute("SELECT COUNT(*) FROM orders o WHERE " + live_where("o") + filt,
                            args).fetchone()[0] or 0
    breakdown = {}
    for st, c in conn.execute("SELECT sys_status, COUNT(*) FROM orders o WHERE "
                              + live_where("o") + " GROUP BY sys_status"):
        breakdown[st] = int(c or 0)
    return {"total_orders": live, "store_orders": store_orders,
            "shipped_excluded": shipped, "included_orders": included,
            "breakdown": breakdown}


def rebuild_index_db(conn, relation="不限", n=0):
    """SQL 版 rebuild_index：返回 (index, stat)，index 结构与 JSON 版一致。"""
    raw = index_counts(conn, relation, n)
    index = {code: {"qty": v[1], "orders": v[0], "ones": v[2], "main": False}
             for code, v in raw.items()}
    return index, orders_stat(conn, relation, n)


def stats(conn):
    live = conn.execute("SELECT COUNT(*) FROM orders o WHERE " + live_where("o")).fetchone()[0] or 0
    total = orders_total(conn)
    codes = conn.execute("SELECT COUNT(DISTINCT code) FROM order_items").fetchone()[0]
    return {"orders_total": total, "live_orders": live, "codes": codes,
            "loaded_at": get_meta(conn, "loaded_at", "")}


def load_shelf(conn):
    out = {}
    for code, qty, bins in conn.execute("SELECT code, qty, bins FROM shelf"):
        try:
            b = json.loads(bins) if bins else []
        except Exception:
            b = []
        out[code] = {"shelf": int(qty or 0), "bins": b}
    return out


def load_lock(conn):
    out = {}
    for code, lck, sellable, avail in conn.execute("SELECT code, lck, sellable, avail FROM lock"):
        out[code] = {"lock": int(lck or 0), "sellable": int(sellable or 0),
                     "avail": int(avail or 0)}
    return out


if __name__ == "__main__":
    print("kuaimai_db 模块（被 kuaimai_scan.py 使用）")
