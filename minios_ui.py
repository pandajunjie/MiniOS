"""MiniOS 公共 UI 层：配色表与悬停按钮。

主程序和各个应用模块都从这里取颜色和控件，改一套值全局生效。
"""

import tkinter as tk


class Theme:
    BG_MAIN = "#1a1a2e"
    BG_PANEL = "#16213e"
    BG_CARD = "#0f3460"
    BG_HOVER = "#1e4d8c"

    ACCENT = "#00d4ff"
    ACCENT2 = "#e94560"
    GOLD = "#ffd700"

    BTN_PRIMARY = "#00d4ff"
    BTN_DANGER = "#e94560"
    BTN_SUCCESS = "#2ecc71"
    BTN_WARNING = "#f39c12"
    BTN_PURPLE = "#9b59b6"
    BTN_DEFAULT = "#533483"

    TEXT = "#ffffff"
    TEXT_DIM = "#a0a8b8"

    TASKBAR = "#0d0d1a"
    TASKBAR_HOVER = "#2a2a4a"

    START_BG = "#0d0d1a"
    START_HOVER = "#1e4d8c"


class HoverButton(tk.Button):
    def __init__(self, master, text, command=None, color=Theme.BTN_DEFAULT,
                 hover_color=None, width=None, height=None, **kwargs):
        super().__init__(
            master, text=text, command=command,
            bg=color, fg=Theme.TEXT,
            activebackground=hover_color or self._lighten(color),
            activeforeground=Theme.TEXT,
            font=("微软雅黑", 10),
            relief=tk.FLAT, cursor="hand2",
            width=width, height=height,
            bd=0, padx=8, pady=4, **kwargs
        )
        self.default_bg = color
        self.hover_bg = hover_color or self._lighten(color)
        self.bind("<Enter>", lambda e: self.config(bg=self.hover_bg))
        self.bind("<Leave>", lambda e: self.config(bg=self.default_bg))

    @staticmethod
    def _lighten(color):
        color = color.lstrip("#")
        r, g, b = tuple(int(color[i:i+2], 16) for i in (0, 2, 4))
        r, g, b = min(255, r+30), min(255, g+30), min(255, b+30)
        return f"#{r:02x}{g:02x}{b:02x}"


# ====================== 主系统 ======================
