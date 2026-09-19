# -*- coding: utf-8 -*-
"""网页端「按账号的按钮权限」清单 —— 权限键的唯一来源。

加一条新权限（例如以后网页上多一个按钮）只改这一处：
  1. 在下面 CATALOG 里加一行 (权限键, 显示名, 分组, 默认是否开放)；
  2. 页面上给按钮加 data-perm="权限键"（动态生成的按钮用 CAN('权限键') 判断）；
  3. 服务端处理该按钮对应接口时加一句 need(me, "权限键")。
老数据（users.json 里没有 perms 字段）按 DEFAULTS 处理，所以向后兼容。
"""
import json
import os

# (权限键, 显示名, 分组, 默认是否开放)
# 「查询类」= 只看不改数据，默认对所有人开放；「动作类」= 会改数据/写记录，默认关闭。
CATALOG = [
    ("scan.query",     "查询（扫码 / 手动输入编码）",            "查询类（默认开放）", True),
    ("scan.camera",    "摄像头扫码",                             "查询类（默认开放）", True),
    ("scan.filter",    "订单件数筛选（应用）",                    "查询类（默认开放）", True),
    ("ui.sound",       "声音提示开关",                           "查询类（默认开放）", True),
    ("order.query",    "订单查询（含订单图片）",                  "查询类（默认开放）", True),
    ("stock.view",     "现货可发（查看）",                        "查询类（默认开放）", True),
    ("stock.export",   "现货可发 · 导出 Excel",                   "查询类（默认开放）", True),
    ("stocktake.view", "库存盘点（查看）",                        "查询类（默认开放）", True),
    ("stock.canprint", "现货可发 · 可发 / 撤回（写扫码记录）",     "动作类（默认关闭）", False),
    ("stock.edit",     "改库存",                                 "动作类（默认关闭）", False),
    ("stock.zero",     "盘0",                                    "动作类（默认关闭）", False),
    ("pick.view",      "拣货（进入拣货页）",                      "动作类（默认关闭）", False),
    ("pick.start",     "拣货 · 开始拣货 / 重新拉取",              "动作类（默认关闭）", False),
    ("pick.mark",      "拣货 · 拣货完成 / 无货",                  "动作类（默认关闭）", False),
    ("pick.end",       "拣货 · 结束批次",                         "动作类（默认关闭）", False),
    ("pick.zone",      "拣货 · 按分区拣货",                       "动作类（默认关闭）", False),
    ("pick.speak",     "拣货 · 语音播报",                         "动作类（默认关闭）", False),
    ("admin.perms",    "权限管理（仅管理员）",                     "管理", False),
    # ---- 桌面端（电脑版）用到的权限点 ----
    ("scan.record",     "扫码记录（查看 / 刷新）",                    "查询类（默认开放）", True),
    ("scan.printed",    "扫码记录 · 标记「已打」",                     "查询类（默认开放）", True),
    ("batch.query",     "批次查询（按打印批次号）",                    "查询类（默认开放）", True),
    ("batch.file",      "批次查询 · 读取 ERP 导出文件",                "查询类（默认开放）", True),
    ("data.refresh",    "刷新数据（增量 / 全量 / 货位 / 锁定）",        "动作类（默认关闭）", False),
    ("export.excel",    "导出 Excel（扫码记录 / 批次）",                "动作类（默认关闭）", False),
    ("api.settings",    "API 设置（换账号 / 换网关）",                  "动作类（默认关闭）", False),
    ("stock.sent.clear", "现货可发 · 清空已发",                        "管理", False),
    ("desktop.admin",   "子客户端管理（账号 / 权限 / 在线设备）",       "管理", False),
]

KEYS = [c[0] for c in CATALOG]
LABELS = {c[0]: c[1] for c in CATALOG}
GROUPS = {c[0]: c[2] for c in CATALOG}
DEFAULTS = {c[0]: bool(c[3]) for c in CATALOG}
# 只有管理员拿得到的权限点（普通账号一律 False，且不可被勾选配置）
ADMIN_ONLY = ("admin.perms", "desktop.admin")


def defaults():
    """所有权限键的默认值（新账号 / 老数据缺字段都按这个来）。"""
    return dict(DEFAULTS)


def catalog():
    """给权限管理页面用的清单。"""
    return [{"key": k, "label": LABELS[k], "group": GROUPS[k], "default": DEFAULTS[k]} for k in KEYS]


def groups():
    """按分组排好序的清单（页面表头用）。"""
    out = []
    for k in KEYS:
        g = GROUPS[k]
        if not out or out[-1][0] != g:
            out.append((g, []))
        out[-1][1].append(k)
    return out


def effective(stored, role="user"):
    """把账号里存的 perms 算成一张完整权限表（缺字段按默认值）。

    · 管理员：一律全开（管理员始终全量可见，不可被限制）；
    · 普通账号：先取默认值，再用账号里显式存的值覆盖（含显式的 False）；
    · admin.perms 永远只给管理员。
    """
    out = defaults()
    if str(role or "") == "admin":
        for k in KEYS:
            out[k] = True
        return out
    if isinstance(stored, dict):
        for k, v in stored.items():
            if k in out:
                out[k] = bool(v)
    for k in ADMIN_ONLY:
        out[k] = False
    return out


def sanitize(values):
    """保存前过滤：只保留认识的权限键，值统一成 bool（防止前端塞垃圾进来）。"""
    out = {}
    if isinstance(values, dict):
        for k, v in values.items():
            if k in DEFAULTS:
                out[k] = bool(v)
    return out
