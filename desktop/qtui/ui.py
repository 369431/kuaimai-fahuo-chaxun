# -*- coding: utf-8 -*-
"""电脑版（Qt）的配色、样式表和自绘控件。

配色跟网页预览保持同一套：浅色/深色两套，青色(#22d3ee)作强调色。
控件：
  · GlowButton  —— 鼠标划过外发光（QGraphicsDropShadowEffect + QPropertyAnimation 真平滑）
  · MacTitleBar —— mac 风格标题栏（三个圆点），窗口行为交给 Windows 原生（见 window.py）
  · Pill        —— 彩色小胶囊标签
"""
from PySide6.QtCore import (QEasingCurve, QEvent, QObject, QPoint,
                            QPropertyAnimation, Qt)
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (QFrame, QGraphicsDropShadowEffect, QHBoxLayout,
                               QLabel, QPushButton, QSizePolicy, QWidget)

# ---------------- 两套配色 ----------------
LIGHT = {
    "bg": "#eef2f8", "panel": "#ffffff", "panel2": "#fbfdff", "head": "#e9f1f9",
    "input": "#f7fafd", "foot": "#e9f0f7", "line": "#d7e3ef",
    "ink": "#16222e", "ink2": "#1c2b3a", "dim": "#5b7085", "dim2": "#4a6076",
    "btn_ink": "#1b2b3a", "btn_top": "#ffffff", "btn_bot": "#eef5fb",
    "btn_hover_top": "#d9edf7", "btn_hover_bot": "#c3e2f0",
    "primary_ink": "#ffffff", "primary_top": "#22d3ee", "primary_bot": "#0891b2",
    "accent": "#0891b2", "titlebar": "#ffffff", "brand": "#0b3c4d",
    "row_even": "rgba(8,145,178,0.045)", "row_hover": "rgba(34,211,238,0.10)",
    "gr": "#059669", "am": "#b45309", "rd": "#dc2626", "cy": "#0284c7",
    "shadow": "rgba(38,68,98,0.16)",
    # 浅色主题：发光用**蓝色**（青色在白底上偏淡，蓝色更醒目）
    "glow": "#2563eb", "glow_a": 240,
}
DARK = {
    "bg": "#070a0f", "panel": "#0f1722", "panel2": "#0c141d", "head": "#0d1621",
    "input": "#08101a", "foot": "#0a121b", "line": "#1b3348",
    "ink": "#cfe0f0", "ink2": "#d8ecf8", "dim": "#7d97af", "dim2": "#8fb4cf",
    "btn_ink": "#cfe6f5", "btn_top": "#142a3c", "btn_bot": "#0c161f",
    "btn_hover_top": "#1d4b60", "btn_hover_bot": "#10303f",
    "primary_ink": "#04141c", "primary_top": "#7deefc", "primary_bot": "#22d3ee",
    "accent": "#22d3ee", "titlebar": "#0d151f", "brand": "#dff0ff",
    "row_even": "rgba(56,189,248,0.03)", "row_hover": "rgba(34,211,238,0.10)",
    "gr": "#34d399", "am": "#fbbf24", "rd": "#fb7185", "cy": "#38bdf8",
    "shadow": "rgba(0,0,0,0.6)",
    # 深色主题：发光用青色
    "glow": "#22d3ee", "glow_a": 220,
}


def qss(c):
    """按配色生成整窗样式表。"""
    return """
QWidget#root, QWidget#body { background: %(bg)s; }
QFrame#titlebar { background: %(titlebar)s; border-bottom: 1px solid %(line)s; }
QLabel#brand { color: %(brand)s; font-size: 15px; font-weight: 700; }
QLabel#badge { color: %(accent)s; background: %(panel)s;
                border: 1px solid %(line)s; border-radius: 9px; padding: 2px 9px;
                font-family: Consolas; font-size: 11px; }
QLabel#mactitle { color: %(dim)s; font-size: 12px; }
QLabel#hint { color: %(dim)s; font-size: 12px; }
QLabel#dimmer { color: %(dim)s; font-size: 11px; font-family: Consolas; }
QLabel#code { color: %(ink)s; font-family: Consolas; font-size: 30px; font-weight: 700; }
QLabel#sect { color: %(dim2)s; font-size: 12.5px; }
QFrame#panel { background: %(panel)s; border: 1px solid %(line)s; border-radius: 10px; }
QFrame#foot { background: %(foot)s; border-top: 1px solid %(line)s; }
QLineEdit { background: %(input)s; color: %(ink)s; border: 1px solid %(line)s;
             border-radius: 9px; padding: 10px 14px; font-family: Consolas; font-size: 17px;
             selection-background-color: %(accent)s; }
QLineEdit:focus { border: 1px solid %(accent)s; }
QPushButton { color: %(btn_ink)s;
               background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                           stop:0 %(btn_top)s, stop:1 %(btn_bot)s);
               border: 1px solid %(line)s; border-radius: 10px;
               padding: 9px 16px; font-size: 13px; }
QPushButton:hover { color: %(ink)s; border: 1px solid %(accent)s;
               background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                           stop:0 %(btn_hover_top)s, stop:1 %(btn_hover_bot)s); }
QPushButton#primary { color: %(primary_ink)s; font-size: 15px; font-weight: 700;
               letter-spacing: 2px;
               background: qlineargradient(x1:0,y1:0,x2:0,y2:1,
                           stop:0 %(primary_top)s, stop:1 %(primary_bot)s);
               border: 1px solid %(accent)s; padding: 12px 26px; }
QPushButton#menu { background: rgba(8,145,178,0.08); border: 1px solid %(line)s;
               color: %(ink)s; padding: 6px 14px; font-size: 13px; border-radius: 9px; }
QPushButton#menu:hover { background: rgba(34,211,238,0.20); border: 1px solid %(accent)s; }
QPushButton#icon { padding: 6px 10px; font-size: 14px; }
QMenu { background: %(panel)s; border: 1px solid %(accent)s; border-radius: 10px;
         padding: 6px; color: %(btn_ink)s; font-size: 13px; }
QMenu::item { padding: 9px 26px 9px 14px; border-radius: 7px; }
QMenu::item:selected { background: rgba(34,211,238,0.22); color: %(ink)s; }
QTableWidget { background: %(panel2)s; border: 1px solid %(line)s; border-radius: 10px;
         gridline-color: transparent; color: %(ink)s; font-size: 12px; }
QTableWidget::item { padding: 7px 10px; }
QTableWidget::item:selected { background: rgba(34,211,238,0.18); color: %(ink)s; }
QHeaderView::section { background: %(head)s; color: %(dim2)s; border: 0;
         border-bottom: 1px solid %(accent)s; padding: 9px 10px; font-size: 12px; }
QTabBar::tab { background: transparent; color: %(dim)s; padding: 9px 16px; margin-right: 3px;
         border: 1px solid transparent; border-top-left-radius: 9px;
         border-top-right-radius: 9px; font-size: 13px; }
QTabBar::tab:hover { color: %(ink)s; background: rgba(34,211,238,0.10); }
QTabBar::tab:selected { color: %(ink)s; font-weight: 600;
         background: rgba(34,211,238,0.16); border: 1px solid %(accent)s;
         border-bottom-color: transparent; }
QTabWidget::pane { border: 1px solid %(line)s; border-radius: 10px; background: %(panel)s; }
QScrollBar:vertical { background: transparent; width: 9px; }
QScrollBar::handle:vertical { background: %(line)s; border-radius: 4px; }
QScrollBar::handle:vertical:hover { background: %(accent)s; }
QToolTip { background: %(panel)s; color: %(ink)s; border: 1px solid %(accent)s; }
""" % c


class GlowButton(QPushButton):
    """鼠标划过外发光。

    · 真·平滑渐变：QGraphicsDropShadowEffect + QPropertyAnimation
    · 发光颜色随主题切（**浅色=蓝光**，深色=青光）
    · **拖动/缩放窗口时会自动关掉发光** —— QGraphicsDropShadowEffect 在窗口移动/重绘时
      容易留残影，动的时候暂停一下最省事也最有效（见 window.py 的 WM_ENTERSIZEMOVE）
    """

    def __init__(self, text, parent=None, primary=False, glow=52, icon_text=""):
        super().__init__((icon_text + "  " + text).strip() if icon_text else text, parent)
        self.setObjectName("primary" if primary else "btn")
        self.setCursor(Qt.PointingHandCursor)
        self._max = glow
        self._enabled = True
        self._fx = QGraphicsDropShadowEffect(self)
        self._fx.setOffset(0, 0)
        self._fx.setBlurRadius(0)
        self.setGraphicsEffect(self._fx)
        self._anim = QPropertyAnimation(self._fx, b"blurRadius", self)
        self._anim.setDuration(165)
        self._anim.setEasingCurve(QEasingCurve.OutCubic)
        self.set_glow("#22d3ee", 215)

    def set_glow(self, color, alpha=215):
        """换发光颜色（切主题时调）。"""
        try:
            c = QColor(color)
            c.setAlpha(int(alpha))
            self._fx.setColor(c)
        except Exception:
            pass

    def set_glow_enabled(self, on):
        """窗口正在拖动/缩放时关掉发光，避免残影。"""
        self._enabled = bool(on)
        if not on:
            try:
                self._anim.stop()
                self._fx.setBlurRadius(0)
            except Exception:
                pass

    def _to(self, v):
        self._anim.stop()
        self._anim.setStartValue(self._fx.blurRadius())
        self._anim.setEndValue(v)
        self._anim.start()

    def enterEvent(self, e):
        if self._enabled:
            self._to(self._max)
        super().enterEvent(e)

    def leaveEvent(self, e):
        self._to(0)
        super().leaveEvent(e)


class Pill(QLabel):
    """彩色小胶囊（波次状态之类）。"""

    def __init__(self, text, color, parent=None):
        super().__init__(text, parent)
        self.setAlignment(Qt.AlignCenter)
        self.apply(color)

    def apply(self, color):
        self.setStyleSheet(
            "color:%s; border:1px solid %s; border-radius:11px; padding:2px 10px;"
            "font-size:12px; background: rgba(127,127,127,0.06);" % (color, color))


class MacTitleBar(QFrame):
    """mac 风格标题栏：三个圆点 + 品牌 + 版本 + 居中标题 + 右侧插槽。

    窗口的拖动/贴边/缩放**不在这里做** —— 交给 Windows 原生（见 window.py 的 WM_NCHITTEST）。
    """

    def __init__(self, win, brand, ver, on_theme=None, parent=None):
        super().__init__(parent)
        self.win = win
        self.setObjectName("titlebar")
        self.setFixedHeight(46)
        lay = QHBoxLayout(self)
        lay.setContentsMargins(14, 0, 12, 0)
        lay.setSpacing(8)

        self.dots = []
        for color, glyph, tip in (("#ff5f57", "✕", "关闭"),
                                  ("#febc2e", "－", "最小化"),
                                  ("#28c840", "＋", "最大化 / 还原")):
            d = QLabel(glyph)
            d.setAlignment(Qt.AlignCenter)
            d.setFixedSize(14, 14)
            d.setCursor(Qt.PointingHandCursor)
            d.setToolTip(tip)
            d.setStyleSheet("color: rgba(0,0,0,0.55); font-size: 9px; font-weight: 700;"
                            "background: %s; border-radius: 7px;" % color)
            lay.addWidget(d)
            self.dots.append(d)
        self.dots[0].mousePressEvent = lambda e: self.win.close()
        self.dots[1].mousePressEvent = lambda e: self.win.showMinimized()
        self.dots[2].mousePressEvent = lambda e: (
            self.win.showNormal() if self.win.isMaximized() else self.win.showMaximized())

        lay.addSpacing(6)
        b = QLabel(brand)
        b.setObjectName("brand")
        lay.addWidget(b)
        self.badge = QLabel(" " + ver + " ")
        self.badge.setObjectName("badge")
        lay.addWidget(self.badge)
        lay.addStretch(1)
        self.title = QLabel("")
        self.title.setObjectName("mactitle")
        lay.addWidget(self.title)
        lay.addStretch(1)

        self.extra = QHBoxLayout()
        self.extra.setSpacing(6)
        lay.addLayout(self.extra)

        self.theme_btn = GlowButton("🌙", glow=22)
        self.theme_btn.setObjectName("icon")
        self.theme_btn.setToolTip("切换 浅色 / 深色")
        self.theme_btn.setFixedWidth(46)
        if on_theme:
            self.theme_btn.clicked.connect(on_theme)
        lay.addWidget(self.theme_btn)

    def menu_button(self, text):
        # ★ 用 GlowButton：鼠标划过外发光（跟「查 询」那些按钮同一套效果）。
        #   主题切换/拖动窗口时的发光统一处理在 window.py 里按 findChildren(GlowButton) 走，
        #   所以这里换成 GlowButton 就自动被纳管，不用另写代码。
        b = GlowButton(text + "  ▾", glow=30)
        b.setObjectName("menu")
        b.setCursor(Qt.PointingHandCursor)
        return b

    def tab_glow(self, tabs):
        """给 QTabWidget 的页签加「鼠标划过外发光」。

        做法：在 tabBar 上装事件过滤器，跟踪鼠标下的页签索引 → 给 tabBar 挂
        QGraphicsDropShadowEffect（整体淡光晕，不需要自己画）。
        """
        try:
            bar = tabs.tabBar()
        except Exception:
            return None
        fx = QGraphicsDropShadowEffect(bar)
        fx.setOffset(0, 0)
        fx.setBlurRadius(0)
        fx.setColor(QColor("#2563eb"))
        bar.setGraphicsEffect(fx)
        anim = QPropertyAnimation(fx, b"blurRadius", bar)
        anim.setDuration(150)

        def to(v):
            try:
                anim.stop()
                anim.setStartValue(fx.blurRadius())
                anim.setEndValue(v)
                anim.start()
            except Exception:
                pass

        def ev(obj, e):
            try:
                if e.type() == QEvent.MouseMove:
                    idx = bar.tabAt(e.position().toPoint())
                    to(26 if idx >= 0 else 0)
                elif e.type() == QEvent.Leave:
                    to(0)
            except Exception:
                pass
            return False

        class _F(QObject):
            def eventFilter(self, o, e):
                return ev(o, e)

        bar.setMouseTracking(True)
        f = _F(bar)
        bar.installEventFilter(f)
        tabs._km_tabglow = (bar, fx, f)      # 持有引用，别被回收
        return anim


def panel(parent=None):
    f = QFrame(parent)
    f.setObjectName("panel")
    return f
