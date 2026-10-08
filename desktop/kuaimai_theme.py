# -*- coding: utf-8 -*-
"""让老的那些 Tk 设置窗，跟新版电脑版（Qt）界面看起来是同一套。

做法是**全局换肤**，所以不用改任何一个设置窗的代码：
  · tk.option_add   → 管经典 Tk 控件（Toplevel / Label / Button / Entry / Text / Listbox…）
  · ttk.Style       → 管 ttk 控件（用 clam 主题，因为只有它能自由配色）
只动颜色和字体，**不动任何布局和逻辑**。

什么时候生效：只在 ui=qt（用电脑版界面）时调用。
选 ui=tk 时完全不动 —— 保持老界面原样，避免影响你熟悉的布局。
"""
import tkinter as tk
from tkinter import ttk

# 跟 desktop/qtui/ui.py 里的 LIGHT 配色保持一致
LIGHT = {
    "bg": "#eef2f8", "panel": "#ffffff", "panel2": "#fbfdff", "head": "#e9f1f9",
    "input": "#f7fafd", "line": "#d7e3ef",
    "ink": "#16222e", "dim": "#5b7085", "dim2": "#4a6076",
    "btn_top": "#ffffff", "btn_bot": "#eef5fb", "btn_hover": "#d9edf7",
    "accent": "#0891b2", "accent_ink": "#ffffff",
    "sel": "#cfeaf3", "field": "#ffffff",
}
DARK = {
    "bg": "#0f1722", "panel": "#0f1722", "panel2": "#0c141d", "head": "#0d1621",
    "input": "#08101a", "line": "#1b3348",
    "ink": "#cfe0f0", "dim": "#7d97af", "dim2": "#8fb4cf",
    "btn_top": "#142a3c", "btn_bot": "#0c161f", "btn_hover": "#1d4b60",
    "accent": "#22d3ee", "accent_ink": "#04141c",
    "sel": "#14435a", "field": "#0a1520",
}

FONT = ("Microsoft YaHei UI", 9)
FONT_BOLD = ("Microsoft YaHei UI", 9, "bold")
MONO = ("Consolas", 10)


def apply(root, dark=False):
    """全局换肤。root 用主窗口就行。失败也不抛（换肤失败不影响功能）。"""
    c = DARK if dark else LIGHT
    try:
        # ---------- ① 经典 Tk 控件 ----------
        root.option_add("*Font", FONT)
        root.option_add("*Background", c["bg"])
        root.option_add("*Foreground", c["ink"])
        root.option_add("*highlightBackground", c["line"])
        root.option_add("*highlightColor", c["accent"])
        root.option_add("*selectBackground", c["accent"])
        root.option_add("*selectForeground", c["accent_ink"])
        root.option_add("*Entry.Background", c["input"])
        root.option_add("*Text.Background", c["input"])
        root.option_add("*Listbox.Background", c["input"])
        root.option_add("*Listbox.selectBackground", c["accent"])
        root.option_add("*Button.Background", c["btn_bot"])
        root.option_add("*Button.activeBackground", c["btn_hover"])
        root.option_add("*Button.highlightThickness", 0)
        root.option_add("*Button.relief", "flat")
        root.option_add("*Toplevel.Background", c["bg"])
        root.option_add("*Menu.Background", c["panel"])
        root.option_add("*Menu.activeBackground", c["sel"])

        # ---------- ② ttk 控件 ----------
        st = ttk.Style(root)
        try:
            st.theme_use("clam")      # 只有 clam 能自由配色
        except Exception:
            pass
        st.configure(".", background=c["bg"], foreground=c["ink"],
                     fieldbackground=c["input"], bordercolor=c["line"],
                     lightcolor=c["panel"], darkcolor=c["panel"],
                     troughcolor=c["head"], focuscolor=c["accent"],
                     font=FONT, relief="flat")
        st.configure("TFrame", background=c["bg"])
        st.configure("TLabel", background=c["bg"], foreground=c["ink"])
        st.configure("TLabelframe", background=c["bg"], bordercolor=c["line"],
                     relief="solid", borderwidth=1)
        st.configure("TLabelframe.Label", background=c["bg"], foreground=c["dim2"],
                     font=FONT_BOLD)
        st.configure("TButton", background=c["btn_bot"], foreground=c["ink"],
                     bordercolor=c["line"], relief="flat", padding=(12, 6),
                     focuscolor=c["accent"])
        st.map("TButton",
               background=[("pressed", c["accent"]), ("active", c["btn_hover"])],
               foreground=[("pressed", c["accent_ink"])])
        st.configure("Accent.TButton", background=c["accent"], foreground=c["accent_ink"],
                     bordercolor=c["accent"], relief="flat", padding=(14, 6))
        st.map("Accent.TButton",
               background=[("pressed", c["accent"]), ("active", c["btn_hover"])],
               foreground=[("active", c["accent_ink"])])
        st.configure("TCheckbutton", background=c["bg"], foreground=c["ink"],
                     focuscolor=c["accent"])
        st.map("TCheckbutton", background=[("active", c["bg"])])
        st.configure("TRadiobutton", background=c["bg"], foreground=c["ink"])
        st.configure("TEntry", fieldbackground=c["input"], foreground=c["ink"],
                     bordercolor=c["line"], insertcolor=c["ink"], padding=4)
        st.map("TEntry", bordercolor=[("focus", c["accent"])])
        st.configure("TCombobox", fieldbackground=c["input"], background=c["btn_bot"],
                     foreground=c["ink"], bordercolor=c["line"], arrowcolor=c["dim2"],
                     padding=3)
        st.map("TCombobox",
               fieldbackground=[("readonly", c["input"])],
               bordercolor=[("focus", c["accent"])])
        st.configure("TSpinbox", fieldbackground=c["input"], foreground=c["ink"],
                     bordercolor=c["line"], arrowcolor=c["dim2"])
        st.configure("Treeview", background=c["panel"], fieldbackground=c["panel"],
                     foreground=c["ink"], bordercolor=c["line"], rowheight=26,
                     relief="flat")
        st.map("Treeview",
               background=[("selected", c["sel"])],
               foreground=[("selected", c["ink"])])
        st.configure("Treeview.Heading", background=c["head"], foreground=c["dim2"],
                     relief="flat", font=FONT_BOLD, padding=(8, 6))
        st.map("Treeview.Heading", background=[("active", c["btn_hover"])])
        st.configure("TNotebook", background=c["bg"], bordercolor=c["line"],
                     tabmargins=(4, 6, 4, 0))
        st.configure("TNotebook.Tab", background=c["head"], foreground=c["dim"],
                     padding=(16, 7), font=FONT)
        st.map("TNotebook.Tab",
               background=[("selected", c["panel"]), ("active", c["btn_hover"])],
               foreground=[("selected", c["accent"])])
        st.configure("TScrollbar", background=c["head"], troughcolor=c["bg"],
                     bordercolor=c["bg"], arrowcolor=c["dim2"])
        st.configure("TProgressbar", background=c["accent"], troughcolor=c["head"],
                     bordercolor=c["line"])
        st.configure("TSeparator", background=c["line"])
        st.configure("TPanedwindow", background=c["bg"])
        return True
    except Exception:
        return False
