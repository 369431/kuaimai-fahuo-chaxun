# -*- coding: utf-8 -*-
"""跨线程更新界面的小工具。

后台线程**不能**直接 `widget.after(...)` —— 有时候会静默失败（界面一直停在“正在检查…”），
所以统一走这里：后台线程 post，UI 线程自己按固定间隔取出来执行。
"""
import queue


def _pump(widget):
    q = getattr(widget, "_km_uiq", None)
    if q is None:
        return
    for _ in range(50):
        try:
            fn, args = q.get_nowait()
        except Exception:
            break
        try:
            fn(*args)
        except Exception:
            pass
    try:
        widget.after(120, lambda: _pump(widget))
    except Exception:
        pass


def start(widget):
    """在 UI 线程里调一次（窗口构造时），之后 post() 才能可靠地跑。"""
    q = getattr(widget, "_km_uiq", None)
    if q is None:
        try:
            setattr(widget, "_km_uiq", queue.Queue())
        except Exception:
            return False
    try:
        widget.after(120, lambda: _pump(widget))
        return True
    except Exception:
        return False


def post(widget, fn, *args):
    """把 fn(*args) 丢回 UI 线程执行（widget 用窗口就行）。"""
    q = getattr(widget, "_km_uiq", None)
    if q is None:
        # 没 start() 过：先自己试着排一次（能成最好，拿不准就让调用方补 start）
        start(widget)
        q = getattr(widget, "_km_uiq", None)
    if q is None:
        return
    try:
        q.put((fn, args))
    except Exception:
        pass
