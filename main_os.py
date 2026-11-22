"""
MiniOS Lite v2.0 - 完整核心主系统
功能：动态 App Store 支持、模块化管理、精美 UI、所有基础工具
"""

import os
import re
import sys
import json
import random
import datetime
import subprocess
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, scrolledtext, colorchooser, filedialog
from tkinter import font as tkfont

# ====================== 配色 ======================
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


SYS_NAME = "MiniOS Lite v2.0"
DISK_PATH = "./mini_system_disk"
USER_DB_PATH = "./userdata.txt"
SETTINGS_PATH = "./settings.json"

# 壁纸预设：名称 + 色值。深色系，但彼此差异明显，不再是"五个几乎一样的深蓝黑"
WALLPAPER_THEMES = [
    ("深空蓝", "#1a1a2e"),
    ("午夜紫", "#241b3d"),
    ("靛蓝",   "#141c3a"),
    ("深海青", "#0e2a33"),
    ("墨绿",   "#10241c"),
    ("酒红",   "#2b1620"),
    ("炭灰",   "#202124"),
    ("石墨",   "#2b2b2b"),
    ("暖棕",   "#241a14"),
    ("黑金",   "#1c1a14"),
]
WALLPAPERS = [c for _, c in WALLPAPER_THEMES]

# 所有可持久化的设置项（新增项只要往这里加，读写逻辑会自动跟上）
DEFAULT_SETTINGS = {
    "wallpaper": WALLPAPERS[0],
    "clock_24h": True,
    "show_seconds": False,
    "show_desktop_icons": True,
}

# 桌面图标：每列从上往下放几个，满了自动换到右边一列（同 Windows 桌面）
ICON_ROWS = 5
ICON_CELL_W = 96
ICON_CELL_H = 92

# 初始化目录和用户文件
if not os.path.exists(DISK_PATH):
    os.mkdir(DISK_PATH)
if not os.path.exists(USER_DB_PATH):
    with open(USER_DB_PATH, "w", encoding="utf-8") as f:
        f.write("admin|123456\n")


# ====================== 悬停按钮 ======================
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
class MiniOSGUI:
    def __init__(self, root):
        self.root = root
        self.root.title(SYS_NAME)
        self.root.geometry("1100x720")
        self.root.resizable(False, False)
        self.root.configure(bg=Theme.BG_MAIN)

        self.prefs = dict(DEFAULT_SETTINGS)
        self._wallpaper_known = set(WALLPAPERS)   # 用于识别"哪些控件的背景属于壁纸层"
        self.load_settings()
        self._wallpaper_known.add(self.current_wallpaper)
        self.login_user = ""
        self._after_ids = set()
        self._open_windows = set()
        self._desktop_sig = None      # 桌面图标内容签名，用于跳过无意义重建
        self._last_time_text = ""     # 上次显示的时间文本，避免每秒重复重绘
        self.start_menu_open = False
        self.start_menu = None
        self.start_btn = None

        self.root.withdraw()
        
        # ✅ 将自身挂载，供 App Store 调用
        self.root.app_instance = self
        
        # ✅ 实例化 App Store (确保 app_store.py 在同级目录)
        try:
            from app_store import AppStore
            self.app_store = AppStore(self.root, self)
        except ImportError:
            self.app_store = None
            print("警告：未找到 app_store.py，App Store 功能不可用！")

        self.show_login()

    # ====================== 定时任务管理 ======================
    def safe_after(self, ms, func, *args):
        aid = [None]
        def wrapper():
            self._after_ids.discard(aid[0])
            func(*args)
        aid[0] = self.root.after(ms, wrapper)
        self._after_ids.add(aid[0])
        return aid[0]

    def cancel_all_after(self):
        for aid in list(self._after_ids):
            try:
                self.root.after_cancel(aid)
            except Exception:
                pass
        self._after_ids.clear()

    # ====================== 窗口管理 ======================
    def register_window(self, win):
        self._open_windows.add(win)

        def on_close():
            self._open_windows.discard(win)
            try:
                if hasattr(win, "_after_ids"):
                    for aid in list(win._after_ids):
                        try:
                            win.after_cancel(aid)
                        except Exception:
                            pass
                    win._after_ids.clear()
                win.destroy()
            except Exception:
                pass

        win.protocol("WM_DELETE_WINDOW", on_close)
        win._after_ids = set()
        win._on_close = on_close      # 暴露出来，供进程管理器优雅关闭用
        return win

    def close_all_windows(self):
        for win in list(self._open_windows):
            try:
                # 优先走登记的关闭钩子，能顺带取消定时器；窗口已销毁则直接跳过
                if not win.winfo_exists():
                    continue
                handler = getattr(win, "_on_close", None)
                if callable(handler):
                    handler()
                else:
                    win.destroy()
            except Exception:
                pass
        self._open_windows.clear()

    # ====================== 用户系统 ======================
    def load_users(self):
        users = {}
        try:
            with open(USER_DB_PATH, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if "|" in line:
                        u, p = line.split("|", 1)
                        users[u] = p
        except Exception:
            pass
        return users

    def save_user(self, username, pwd):
        try:
            with open(USER_DB_PATH, "a", encoding="utf-8") as f:
                f.write(f"{username}|{pwd}\n")
        except Exception as e:
            messagebox.showerror("保存失败", str(e))

    # ====================== 登录 ======================
    def show_login(self):
        login_win = tk.Toplevel()
        login_win.title("系统登录")
        login_win.geometry("440x360")
        login_win.configure(bg=Theme.BG_PANEL)
        login_win.grab_set()
        login_win.resizable(False, False)

        login_win.update_idletasks()
        x = (login_win.winfo_screenwidth() - 440) // 2
        y = (login_win.winfo_screenheight() - 360) // 2
        login_win.geometry(f"+{x}+{y}")

        def on_login_close():
            login_win.destroy()
            self.root.destroy()

        login_win.protocol("WM_DELETE_WINDOW", on_login_close)

        title_frame = tk.Frame(login_win, bg=Theme.BG_PANEL)
        title_frame.pack(pady=20)
        tk.Label(title_frame, text="🖥️", font=("Segoe UI Emoji", 40),
                 bg=Theme.BG_PANEL, fg=Theme.ACCENT).pack()
        tk.Label(title_frame, text=SYS_NAME, font=("微软雅黑", 16, "bold"),
                 bg=Theme.BG_PANEL, fg=Theme.TEXT).pack(pady=5)

        form = tk.Frame(login_win, bg=Theme.BG_PANEL)
        form.pack(pady=8)

        tk.Label(form, text="👤 用户名", font=("微软雅黑", 10),
                 bg=Theme.BG_PANEL, fg=Theme.TEXT_DIM,
                 anchor="w").grid(row=0, column=0, sticky="w", pady=3)
        user_in = tk.Entry(form, font=("微软雅黑", 12), width=24,
                           bg=Theme.BG_CARD, fg=Theme.TEXT,
                           insertbackground=Theme.ACCENT, relief=tk.FLAT, bd=0)
        user_in.insert(0, "admin")
        user_in.grid(row=1, column=0, pady=3, ipady=5)

        tk.Label(form, text="🔒 密码", font=("微软雅黑", 10),
                 bg=Theme.BG_PANEL, fg=Theme.TEXT_DIM,
                 anchor="w").grid(row=2, column=0, sticky="w", pady=(10, 3))
        pwd_in = tk.Entry(form, font=("微软雅黑", 12), width=24,
                          show="*", bg=Theme.BG_CARD, fg=Theme.TEXT,
                          insertbackground=Theme.ACCENT, relief=tk.FLAT, bd=0)
        pwd_in.insert(0, "123456")
        pwd_in.grid(row=3, column=0, pady=3, ipady=5)

        def login(event=None):
            usr = user_in.get().strip()
            pw = pwd_in.get().strip()
            userlist = self.load_users()
            if usr in userlist and userlist[usr] == pw:
                self.login_user = usr
                login_win.destroy()
                self.root.deiconify()
                self.build_desktop()
            else:
                messagebox.showerror("登录失败", "用户名或密码错误", parent=login_win)

        def register():
            new_u = simpledialog.askstring("注册账号", "输入新用户名", parent=login_win)
            if not new_u:
                return
            if new_u in self.load_users():
                messagebox.showwarning("提示", "用户名已存在", parent=login_win)
                return
            new_p = simpledialog.askstring("设置密码", "输入登录密码",
                                           show="*", parent=login_win)
            if new_p:
                self.save_user(new_u, new_p)
                messagebox.showinfo("注册成功", f"账号 {new_u} 已创建", parent=login_win)

        user_in.bind("<Return>", login)
        pwd_in.bind("<Return>", login)

        btn_frame = tk.Frame(login_win, bg=Theme.BG_PANEL)
        btn_frame.pack(pady=15)
        HoverButton(btn_frame, "🚀 登录", login, Theme.BTN_PRIMARY,
                    width=10).grid(row=0, column=0, padx=5)
        HoverButton(btn_frame, "📝 注册", register, Theme.BTN_DEFAULT,
                    width=10).grid(row=0, column=1, padx=5)

    # ====================== 桌面与动态刷新 ======================
    def build_desktop(self):
        self.bg = tk.Frame(self.root, bg=self.current_wallpaper)
        self.bg.pack(fill=tk.BOTH, expand=True)

        self._setup_styles()
        self._build_taskbar()
        
        # 创建存放图标的容器
        self.icons_container = tk.Frame(self.bg, bg=self.current_wallpaper)
        self.icons_container.pack(expand=True, fill=tk.BOTH, padx=40)
        
        # 首次生成桌面图标
        self.refresh_desktop_icons()
        
        self._build_start_menu()
        self._build_pet()
        self._build_desktop_right_click()

    # ====================== 桌面宠物 ======================
    PET_FRAMES = {
        "cat": ("🐱", "😺", "😸", "😻", "🐈"),
        "dog": ("🐶", "🐕", "🦮"),
    }
    PET_KIND_NAME = {"cat": "小猫", "dog": "小柴犬"}

    def _build_pet(self):
        """右下角的小宠物：每几秒动一下，点它会叫，右键能换品种"""
        self.pet_kind = "cat"
        self.pet_hidden = False
        self.pet_label = tk.Label(self.bg, text="🐱",
                                  font=("Segoe UI Emoji", 26),
                                  bg=self.current_wallpaper,
                                  cursor="hand2", bd=0)
        self.pet_label.place(relx=1.0, rely=1.0, x=-26, y=-62, anchor="se")
        self.pet_label.bind("<Button-1>", lambda e: self._pet_poke())
        self.pet_label.bind("<Button-3>", self._pet_menu)
        self._pet_dock_sync()
        self._pet_tick()

    def _pet_tick(self):
        """每 4 秒换个表情并轻轻弹一下"""
        if not self._alive(getattr(self, "pet_label", None)):
            return
        if getattr(self, "pet_hidden", False):
            self.safe_after(1500, self._pet_tick)
            return
        frames = self.PET_FRAMES.get(self.pet_kind, ("🐱",))
        try:
            self.pet_label.config(text=random.choice(frames))
            self.pet_label.place_configure(y=-70)
            self.safe_after(260, self._pet_settle)
        except Exception:
            pass
        self.safe_after(4200, self._pet_tick)

    def _pet_settle(self):
        if not self._alive(getattr(self, "pet_label", None)):
            return
        try:
            self.pet_label.place_configure(y=-62)
        except Exception:
            pass

    def _pet_poke(self):
        """点一下：换个开心表情 + 冒气泡 + 叫一声"""
        if not self._alive(getattr(self, "pet_label", None)):
            return
        cat = self.pet_kind == "cat"
        try:
            self.pet_label.config(text="😻" if cat else "🐕")
        except Exception:
            pass
        self._pet_say("喵～" if cat else "汪！")
        self._pet_beep()

    def _pet_say(self, text):
        """在宠物头上冒个小气泡"""
        try:
            old = getattr(self, "_pet_bubble", None)
            if self._alive(old):
                old.destroy()
            b = tk.Label(self.bg, text=text, font=("微软雅黑", 10, "bold"),
                         bg=Theme.BG_PANEL, fg=Theme.TEXT,
                         padx=10, pady=3, bd=1, relief=tk.SOLID)
            b.place(relx=1.0, rely=1.0, x=-26, y=-112, anchor="se")
            self._pet_bubble = b
            self.safe_after(1500, lambda w=b: self._alive(w) and w.destroy())
        except Exception:
            pass

    def _pet_beep(self):
        """叫一声：用线程播放系统音，不卡界面"""
        kind = self.pet_kind
        def play():
            try:
                import winsound
                if kind == "cat":
                    winsound.Beep(1500, 60)
                    winsound.Beep(1000, 120)
                else:
                    winsound.Beep(760, 90)
                    winsound.Beep(520, 110)
            except Exception:
                pass
        try:
            import threading
            threading.Thread(target=play, daemon=True).start()
        except Exception:
            pass

    def _pet_menu(self, event):
        """右键：换品种 / 让开一会儿"""
        try:
            m = tk.Menu(self.root, tearoff=0, bg=Theme.BG_PANEL, fg=Theme.TEXT,
                        activebackground=Theme.BG_HOVER,
                        activeforeground=Theme.TEXT)
            m.add_command(label="换成小猫 🐱", command=lambda: self._set_pet("cat"))
            m.add_command(label="换成小柴犬 🐕", command=lambda: self._set_pet("dog"))
            m.add_separator()
            m.add_command(label="隐藏宠物", command=self._pet_hide)
            m.add_command(label="叫它回来", command=self._pet_show)
            m.tk_popup(event.x_root, event.y_root)
        except Exception:
            pass
        finally:
            try:
                m.grab_release()
            except Exception:
                pass

    def _set_pet(self, kind):
        self.pet_kind = kind
        frames = self.PET_FRAMES.get(kind, ("🐱",))
        try:
            self.pet_label.config(text=frames[0])
        except Exception:
            pass
        self.toast(f"宠物换成{self.PET_KIND_NAME.get(kind, kind)}了", icon="🐾")

    def _pet_hide(self):
        self.pet_hidden = True
        if self._alive(getattr(self, "pet_label", None)):
            try:
                self.pet_label.place_forget()
            except Exception:
                pass
        self._pet_dock_sync()

    def _pet_show(self):
        if self._alive(getattr(self, "pet_label", None)):
            try:
                self.pet_label.place(relx=1.0, rely=1.0, x=-26, y=-62, anchor="se")
            except Exception:
                pass
        if getattr(self, "pet_hidden", False):
            self.pet_hidden = False
            self._pet_tick()
        self._pet_dock_sync()

    def _pet_toggle(self):
        """任务栏宠物窝：点一下收起/叫回"""
        if getattr(self, "pet_hidden", False):
            self._pet_show()
        else:
            self._pet_hide()

    def _pet_dock_sync(self):
        """宠物在家（🏠）还是出来玩（🐾），图标跟着变"""
        dock = getattr(self, "pet_dock", None)
        if not self._alive(dock):
            return
        try:
            if getattr(self, "pet_hidden", False):
                dock.config(text="🏠", fg=Theme.TEXT_DIM)
            else:
                dock.config(text="🐾", fg=Theme.TEXT)
        except Exception:
            pass

    @staticmethod
    def _alive(w):
        try:
            return bool(w is not None and w.winfo_exists())
        except Exception:
            return False

    # ====================== Toast 通知 ======================
    def toast(self, text, icon="✅", duration=3200):
        """右下角半透明通知：3 秒后淡出消失，新的往上叠"""
        try:
            rw, rh = self.root.winfo_width(), self.root.winfo_height()
            rx, ry = self.root.winfo_rootx(), self.root.winfo_rooty()
            if rw < 300:
                rw, rh = 1280, 800
        except Exception:
            return
        try:
            f = tkfont.Font(family="微软雅黑", size=10)
            tw = int(min(460, max(210, f.measure(str(text)) + 96)))
        except Exception:
            tw = 320
        th = 56

        live = [r for r in getattr(self, "_toasts", []) if self._alive(r.get("win"))]
        self._toasts = live
        n = len(live)
        x = rx + rw - tw - 18
        y = ry + rh - 50 - th - 14 - n * (th + 8)

        try:
            win = tk.Toplevel(self.root)
            win.overrideredirect(True)
            win.attributes("-topmost", True)
            win.attributes("-alpha", 0.94)
            win.geometry(f"{tw}x{th}+{max(0, x)}+{max(0, y)}")
            win.configure(bg=Theme.BG_CARD)

            box = tk.Frame(win, bg=Theme.BG_CARD, highlightthickness=1,
                           highlightbackground=Theme.ACCENT)
            box.pack(fill=tk.BOTH, expand=True)
            tk.Label(box, text=icon, font=("Segoe UI Emoji", 16),
                     bg=Theme.BG_CARD, fg=Theme.TEXT).pack(side=tk.LEFT, padx=(14, 9))
            tk.Label(box, text=str(text), font=("微软雅黑", 10),
                     bg=Theme.BG_CARD, fg=Theme.TEXT,
                     anchor="w", justify="left").pack(
                side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 12))
        except Exception:
            return

        rec = {"win": win}
        self._toasts.append(rec)

        def fade(alpha=0.94):
            if not self._alive(win):
                return
            alpha -= 0.08
            if alpha <= 0:
                try:
                    win.destroy()
                except Exception:
                    pass
                if rec in self._toasts:
                    self._toasts.remove(rec)
                return
            try:
                win.attributes("-alpha", alpha)
            except Exception:
                pass
            win.after(60, lambda: fade(alpha))

        win.after(max(800, duration), fade)

    def notify(self, text, icon="✅"):
        """给 app_store 等模块用的通用通知入口"""
        self.toast(text, icon=icon)

    # ====================== 桌面右键菜单 ======================
    def _build_desktop_right_click(self):
        """桌面右键菜单：刷新 / 换壁纸 / 终端 / 宠物 / 设置"""
        menu = tk.Menu(self.root, tearoff=0, bg=Theme.BG_PANEL, fg=Theme.TEXT,
                       activebackground=Theme.BG_HOVER,
                       activeforeground=Theme.TEXT)
        menu.add_command(label="🔄 刷新桌面", command=self._desktop_menu_refresh)
        menu.add_command(label="🎨 更换壁纸", command=self.change_wallpaper)
        menu.add_separator()
        menu.add_command(label="💻 打开终端", command=self._open_terminal_stub)
        menu.add_separator()
        menu.add_command(label="🐾 宠物：收起 / 叫回", command=self._pet_toggle)
        menu.add_command(label="⚙️ 设置中心", command=self.settings)
        menu.add_command(label="📊 进程管理器", command=self.task_manager)

        def show_menu(event):
            try:
                menu.tk_popup(event.x_root, event.y_root)
            finally:
                menu.grab_release()

        self.desktop_menu = menu
        # 图标容器盖住了 bg 的大部分区域，两处都绑上才点得到
        for w in (self.bg, self.icons_container):
            w.bind("<Button-3>", show_menu)

    def _desktop_menu_refresh(self):
        """右键刷新：绕过内容指纹缓存，强制重建一遍图标"""
        self.refresh_desktop_icons(force=True)
        self.toast("桌面已刷新", icon="🔄")

    def _open_terminal_stub(self):
        """终端还没实现：给个看得见的提示，而不是 print 到控制台"""
        self.toast("终端还没做，先用记事本凑合一下", icon="💻")

    # ====================== ttk 样式 ======================
    def _setup_styles(self):
        """统一 ttk 样式：进程管理器的 Treeview 用它，否则会显示成刺眼的白底。"""
        try:
            style = ttk.Style()
            style.theme_use("default")   # vista 主题下无法自定义背景色
            style.configure("Custom.Treeview",
                            background=Theme.BG_PANEL,
                            foreground=Theme.TEXT,
                            fieldbackground=Theme.BG_PANEL,
                            font=("微软雅黑", 10),
                            rowheight=28)
            style.configure("Custom.Treeview.Heading",
                            background=Theme.BG_CARD,
                            foreground=Theme.TEXT,
                            font=("微软雅黑", 10, "bold"))
            style.map("Custom.Treeview",
                      background=[("selected", Theme.BG_HOVER)],
                      foreground=[("selected", Theme.TEXT)])
        except Exception:
            pass

    def _desktop_signature(self):
        """桌面图标的“内容指纹”：只有它变了才需要重建。"""
        try:
            if not getattr(self, 'app_store', None):
                return ()
            desk = getattr(self.app_store, "desktop_apps", None)
            if desk is None:                 # 兼容没有桌面列表的旧商店
                desk = self.app_store.installed_apps
            return tuple(sorted(desk))
        except Exception:
            return ()

    def refresh_desktop_icons(self, force=False):
        """动态刷新桌面图标（内容没变就直接返回，避免每次重建 60+ 控件卡顿）"""
        # 设置里关掉了"显示桌面图标"：直接清空，用特殊签名区分
        if not self.prefs.get("show_desktop_icons", True):
            if not force and self._desktop_sig == "__hidden__":
                return
            self._desktop_sig = "__hidden__"
            try:
                for w in self.icons_container.winfo_children():
                    w.destroy()
            except Exception:
                pass
            return

        sig = self._desktop_signature()
        if not force and self._desktop_sig is not None and sig == self._desktop_sig:
            return
        self._desktop_sig = sig

        for widget in self.icons_container.winfo_children():
            widget.destroy()

        # 合并成一个列表，按 Windows 桌面的方式平铺（不再分卡片）
        all_apps = [
            ("📁", "文件管理器", self.file_manager),
            ("📝", "记事本", self.notepad),
            ("🔢", "计算器", self.calculator),
            ("⏱", "倒计时", self.timer_tool),
        ]

        # 读取 App Store 已安装的应用
        if getattr(self, 'app_store', None):
            all_apps += self.app_store.get_installed_for_desktop()

        # 系统功能
        if self.app_store:
            all_apps.append(("🛍️", "App Store", self.app_store.open))
        all_apps.append(("📊", "进程管理器", self.task_manager))
        all_apps.append(("⚙️", "设置中心", self.settings))

        self._create_icon_grid(self.icons_container, all_apps, rows=ICON_ROWS)

        # 让图标从左上角开始排，而不是飘在中间
        try:
            self.icons_container.grid_anchor("nw")
        except Exception:
            pass

        # 强制刷新，防止界面卡住不渲染
        self.icons_container.update_idletasks()

    def _create_group(self, parent, title, apps, row):
        if not apps: return
        group = tk.Frame(parent, bg=Theme.BG_PANEL,
                         highlightbackground=Theme.BG_CARD,
                         highlightthickness=1)
        group.grid(row=row, column=0, sticky="ew", pady=8)
        parent.grid_columnconfigure(0, weight=1)

        tk.Label(group, text=title, font=("微软雅黑", 12, "bold"),
                 bg=Theme.BG_PANEL, fg=Theme.ACCENT,
                 anchor="w").pack(fill=tk.X, padx=15, pady=(8, 4))

        icon_row = tk.Frame(group, bg=Theme.BG_PANEL)
        icon_row.pack(fill=tk.X, padx=15, pady=(0, 10))

        for icon, name, cmd in apps:
            card = tk.Frame(icon_row, bg=Theme.BG_PANEL)
            card.pack(side=tk.LEFT, padx=6)

            btn = tk.Button(
                card, text=icon, command=cmd,
                font=("Segoe UI Emoji", 22),
                bg=Theme.BG_CARD, fg=Theme.TEXT,
                activebackground=Theme.BG_HOVER,
                relief=tk.FLAT, cursor="hand2",
                width=3, height=1, bd=0
            )
            btn.pack()
            btn.bind("<Enter>", lambda e, b=btn: b.config(bg=Theme.BG_HOVER))
            btn.bind("<Leave>", lambda e, b=btn: b.config(bg=Theme.BG_CARD))

            tk.Label(card, text=name, font=("微软雅黑", 9),
                     bg=Theme.BG_PANEL, fg=Theme.TEXT_DIM).pack(pady=2)

    # ====================== Windows 风格图标网格 ======================
    def _create_icon_grid(self, parent, apps, rows=ICON_ROWS):
        """像 Windows 桌面那样：先从上往下填满一列，再往右边起新的一列。
        列数超过窗口宽度时，自动往每列里多塞几个，避免图标跑出屏幕。"""
        if not apps:
            return

        # 这一块区域横向最多能放几列
        try:
            avail_w = parent.winfo_width()
            if avail_w <= 1:                     # 布局还没算完，按窗口宽度估
                avail_w = self.root.winfo_width() - 80
        except Exception:
            avail_w = 1020
        max_cols = max(1, avail_w // (ICON_CELL_W + 20))

        rows = max(1, rows or ICON_ROWS)
        if -(-len(apps) // rows) > max_cols:     # 列太多会超出右侧 → 每列多放几个
            rows = -(-len(apps) // max_cols)

        for idx, (icon, name, cmd) in enumerate(apps):
            row = idx % rows          # 先填满当前列
            col = idx // rows         # 满了才换列

            cell = tk.Frame(parent, bg=self.current_wallpaper, cursor="hand2",
                            width=ICON_CELL_W, height=ICON_CELL_H)
            cell.grid(row=row, column=col, padx=10, pady=10, sticky="nw")
            cell.pack_propagate(False)
            cell.grid_propagate(False)

            glyph = tk.Label(cell, text=icon, font=("Segoe UI Emoji", 21),
                             bg=self.current_wallpaper, fg=Theme.TEXT,
                             cursor="hand2", bd=0)
            glyph.pack(pady=(9, 1))

            caption = tk.Label(cell, text=name, font=("微软雅黑", 9),
                               bg=self.current_wallpaper, fg=Theme.TEXT,
                               cursor="hand2", bd=0,
                               wraplength=ICON_CELL_W - 6, justify="center")
            caption.pack()

            def _paint(bg, c=cell, g=glyph, t=caption):
                for w in (c, g, t):
                    try:
                        w.config(bg=bg)
                    except Exception:
                        pass

            def _on_enter(event, paint=_paint):
                paint(Theme.BG_HOVER)

            def _on_leave(event, c=cell, paint=_paint):
                # 光标只是从图标挪到名字上时，不该闪一下
                try:
                    px, py = c.winfo_pointerxy()
                    x, y = c.winfo_rootx(), c.winfo_rooty()
                    w, h = c.winfo_width(), c.winfo_height()
                    if x <= px < x + w and y <= py < y + h:
                        return
                except Exception:
                    pass
                paint(self.current_wallpaper)

            def _on_click(event, action=cmd):
                try:
                    action()
                except Exception as e:
                    messagebox.showerror("启动失败", str(e), parent=self.root)

            for widget in (cell, glyph, caption):
                widget.bind("<Enter>", _on_enter)
                widget.bind("<Leave>", _on_leave)
                widget.bind("<Button-1>", _on_click)

    def _build_taskbar(self):
        self.taskbar = tk.Frame(self.bg, bg=Theme.TASKBAR, height=50)
        self.taskbar.pack(fill=tk.X, side=tk.BOTTOM)
        self.taskbar.pack_propagate(False)

        self.start_btn = tk.Button(
            self.taskbar, text="🪟 开始",
            command=self.toggle_start_menu,
            font=("微软雅黑", 11, "bold"),
            bg=Theme.TASKBAR, fg=Theme.TEXT,
            activebackground=Theme.TASKBAR_HOVER,
            relief=tk.FLAT, cursor="hand2",
            padx=15, bd=0
        )
        self.start_btn.pack(side=tk.LEFT, padx=5, pady=8)
        self.start_btn.bind("<Enter>", lambda e: self.start_btn.config(bg=Theme.TASKBAR_HOVER))
        self.start_btn.bind("<Leave>", lambda e: self.start_btn.config(bg=Theme.TASKBAR))

        tk.Frame(self.taskbar, bg=Theme.BG_CARD, width=1).pack(
            side=tk.LEFT, fill=tk.Y, padx=5, pady=10)

        quick_apps = [
            ("📝", self.notepad),
            ("🔢", self.calculator),
            ("📁", self.file_manager),
            ("🐍", self.game_snake),
        ]
        for icon, cmd in quick_apps:
            btn = tk.Button(self.taskbar, text=icon, command=cmd,
                            font=("Segoe UI Emoji", 13),
                            bg=Theme.TASKBAR, fg=Theme.TEXT,
                            activebackground=Theme.TASKBAR_HOVER,
                            relief=tk.FLAT, cursor="hand2",
                            width=3, bd=0)
            btn.pack(side=tk.LEFT, padx=2, pady=8)
            btn.bind("<Enter>", lambda e, b=btn: b.config(bg=Theme.TASKBAR_HOVER))
            btn.bind("<Leave>", lambda e, b=btn: b.config(bg=Theme.TASKBAR))

        tk.Frame(self.taskbar, bg=Theme.BG_CARD, width=1).pack(
            side=tk.LEFT, fill=tk.Y, padx=5, pady=10)

        self.restart_btn = tk.Button(
            self.taskbar, text="🔄 重启", command=self.system_restart,
            font=("微软雅黑", 10, "bold"),
            bg=Theme.BTN_WARNING, fg=Theme.TEXT,
            activebackground=Theme.BTN_WARNING, activeforeground=Theme.TEXT,
            relief=tk.FLAT, cursor="hand2", padx=10, bd=0)
        self.restart_btn.pack(side=tk.LEFT, padx=4, pady=8)

        tray = tk.Frame(self.taskbar, bg=Theme.TASKBAR)
        tray.pack(side=tk.RIGHT, padx=10)

        self.time_label = tk.Label(tray, bg=Theme.TASKBAR, fg=Theme.TEXT,
                                   font=("微软雅黑", 10))
        self.time_label.pack(side=tk.RIGHT, padx=5)
        self._refresh_time()

        # 宠物窝：宠物藏起来之后，从这里把它叫回来
        self.pet_dock = tk.Label(tray, text="🐾", font=("Segoe UI Emoji", 13),
                                 bg=Theme.TASKBAR, fg=Theme.TEXT,
                                 cursor="hand2", padx=6)
        self.pet_dock.pack(side=tk.RIGHT, padx=(2, 6))
        self.pet_dock.bind("<Button-1>", lambda e: self._pet_toggle())
        self.pet_dock.bind("<Button-3>", self._pet_menu)
        self.pet_dock.bind("<Enter>",
                           lambda e: self.pet_dock.config(bg=Theme.TASKBAR_HOVER))
        self.pet_dock.bind("<Leave>",
                           lambda e: self.pet_dock.config(bg=Theme.TASKBAR))

        tk.Label(tray, text=f"👤 {self.login_user}", bg=Theme.TASKBAR,
                 fg=Theme.TEXT_DIM, font=("微软雅黑", 9)).pack(side=tk.RIGHT, padx=10)

    # ====================== 系统重启 ======================
    def system_restart(self):
        """重启 MiniOS：关闭所有窗口，用当前解释器重新拉起本脚本。"""
        if not messagebox.askyesno("重启 MiniOS",
                                   "确定要重启系统吗？\n当前打开的所有窗口会被关闭。"):
            return

        try:
            self.cancel_all_after()
            self.close_all_windows()
        except Exception:
            pass

        try:
            script = os.path.abspath(__file__)
            subprocess.Popen([sys.executable, script], cwd=os.path.dirname(script))
        except Exception as e:
            messagebox.showerror("重启失败", f"无法重新启动进程：{e}")
            return

        try:
            self.root.destroy()
        except Exception:
            pass

    # ====================== 开始菜单 ======================
    def _build_start_menu(self):
        if self.start_menu and self.start_menu.winfo_exists():
            try: self.start_menu.destroy()
            except: pass

        self.start_menu = tk.Toplevel(self.root)
        self.start_menu.title("开始菜单")
        self.start_menu.geometry("320x500")
        self.start_menu.configure(bg=Theme.START_BG)
        self.start_menu.overrideredirect(True)
        self.start_menu.withdraw()
        self.start_menu.resizable(False, False)
        self.start_menu.protocol("WM_DELETE_WINDOW", self.hide_start_menu)

        user_frame = tk.Frame(self.start_menu, bg=Theme.BG_CARD, height=60)
        user_frame.pack(fill=tk.X)
        user_frame.pack_propagate(False)
        tk.Label(user_frame, text="👤", font=("Segoe UI Emoji", 20),
                 bg=Theme.BG_CARD, fg=Theme.ACCENT).pack(side=tk.LEFT, padx=15)
        tk.Label(user_frame, text=self.login_user, font=("微软雅黑", 13, "bold"),
                 bg=Theme.BG_CARD, fg=Theme.TEXT).pack(side=tk.LEFT, pady=18)

        search_frame = tk.Frame(self.start_menu, bg=Theme.START_BG)
        search_frame.pack(fill=tk.X, padx=10, pady=8)

        search_box = tk.Frame(search_frame, bg=Theme.BG_CARD,
                              highlightbackground=Theme.BG_HOVER,
                              highlightthickness=1)
        search_box.pack(fill=tk.X)
        tk.Label(search_box, text="🔍", bg=Theme.BG_CARD, fg=Theme.TEXT_DIM,
                 font=("Segoe UI Emoji", 11)).pack(side=tk.LEFT, padx=8, pady=6)
        self.search_entry = tk.Entry(search_box, font=("微软雅黑", 10),
                                      bg=Theme.BG_CARD, fg=Theme.TEXT,
                                      insertbackground=Theme.ACCENT,
                                      relief=tk.FLAT, bd=0)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True,
                                padx=(0, 8), pady=6)
        self.search_entry.bind("<KeyRelease>", self._filter_menu)

        list_frame = tk.Frame(self.start_menu, bg=Theme.START_BG)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        self.menu_listbox = tk.Listbox(
            list_frame, font=("微软雅黑", 11), bg=Theme.START_BG, fg=Theme.TEXT,
            selectbackground=Theme.BG_HOVER, selectforeground=Theme.TEXT,
            relief=tk.FLAT, bd=0, highlightthickness=0, activestyle="none"
        )
        self.menu_listbox.pack(fill=tk.BOTH, expand=True)
        self.menu_listbox.bind("<ButtonRelease-1>", self._on_menu_select)
        self.menu_listbox.bind("<Return>", self._on_menu_select)

        # ==========================================
        # 1. 重置列表（防止重复添加）
        self.all_apps = [
            ("📁", "文件管理器", self.file_manager),
            ("📝", "记事本", self.notepad),
            ("🔢", "计算器", self.calculator),
            ("⏱", "倒计时", self.timer_tool),
            ("🖌", "画图", self.paint_tool),
            ("🟥", "RGB调色盘", self.rgb_color_picker),
            ("🕒", "数字时钟", self.clock_widget),
            ("🎲", "随机抽签", self.random_draw),
            ("🔢", "猜数字", self.game_guess),
            ("🐍", "贪吃蛇", self.game_snake),
            ("⚫", "五子棋", self.game_gobang),
            ("💣", "扫雷", self.game_mine),
            ("🎨", "更换壁纸", self.change_wallpaper),
        ]

        # 2. 动态加入已安装的第三方应用（如果你刚才截图里的代码在这，那就把它留下，但一定要加上 try-except）
        if getattr(self, 'app_store', None):
            try:
                for icon, name, cmd in self.app_store.get_installed_for_desktop():
                    self.all_apps.append((icon, name, cmd))
            except Exception:
                pass # 忽略报错，保证菜单能打开

        # 3. 永远保底 App Store 入口
        if getattr(self, 'app_store', None):
            self.all_apps.append(("🛍️", "App Store", self.app_store.open))

        self.menu_filtered = list(self.all_apps)
        self._populate_menu(self.all_apps)

        bottom_frame = tk.Frame(self.start_menu, bg=Theme.START_BG, height=45)
        bottom_frame.pack(fill=tk.X, side=tk.BOTTOM)
        bottom_frame.pack_propagate(False)
        tk.Frame(bottom_frame, bg=Theme.BG_CARD, height=1).pack(fill=tk.X)

        power_btn = tk.Button(
            bottom_frame, text="⏻ 关机", command=self.shutdown,
            font=("微软雅黑", 10, "bold"), bg=Theme.START_BG, fg=Theme.BTN_DANGER,
            activebackground=Theme.BG_HOVER, relief=tk.FLAT, cursor="hand2", bd=0, padx=15
        )
        power_btn.pack(side=tk.RIGHT, pady=6)
        power_btn.bind("<Enter>", lambda e: power_btn.config(bg=Theme.BG_HOVER))
        power_btn.bind("<Leave>", lambda e: power_btn.config(bg=Theme.START_BG))

        self.start_menu_open = False

    def _populate_menu(self, apps):
        self.menu_listbox.delete(0, tk.END)
        self.menu_filtered = list(apps)
        for icon, name, _ in apps:
            self.menu_listbox.insert(tk.END, f"  {icon}  {name}")

    def _filter_menu(self, event=None):
        keyword = self.search_entry.get().strip().lower()
        if not keyword:
            self._populate_menu(self.all_apps)
            return
        filtered = [
            (icon, name, cmd) for icon, name, cmd in self.all_apps
            if keyword in name.lower()
        ]
        self._populate_menu(filtered)

    def _on_menu_select(self, event=None):
        sel = self.menu_listbox.curselection()
        if not sel: return
        idx = sel[0]
        if idx >= len(self.menu_filtered): return
        _, _, cmd = self.menu_filtered[idx]
        self.hide_start_menu()
        self.root.after(80, cmd)

    def toggle_start_menu(self):
        if self.start_menu_open: self.hide_start_menu()
        else: self.show_start_menu()

    def show_start_menu(self):
        if not self.start_menu or not self.start_menu.winfo_exists():
            self._build_start_menu()

        self.root.update_idletasks()
        try:
            btn_x = self.start_btn.winfo_rootx()
            btn_y = self.start_btn.winfo_rooty()
        except Exception:
            btn_x = self.root.winfo_x() + 10
            btn_y = self.root.winfo_y() + self.root.winfo_height() - 60

        menu_w, menu_h = 320, 500
        screen_h = self.root.winfo_screenheight()
        x, y = btn_x, btn_y - menu_h - 5
        if y < 0: y = 5
        if y + menu_h > screen_h: y = screen_h - menu_h - 10

        self.start_menu.deiconify()
        self.start_menu.geometry(f"{menu_w}x{menu_h}+{x}+{y}")
        self.start_menu.lift()
        self.start_menu.attributes("-topmost", True)
        self.start_menu.after(100, lambda: self.start_menu.attributes("-topmost", False))
        self.start_menu_open = True

        self.search_entry.delete(0, tk.END)
        self._populate_menu(self.all_apps)
        self.menu_listbox.focus_set()
        self.start_menu.bind("<FocusOut>", self._on_menu_focus_out)

    def _on_menu_focus_out(self, event):
        def check():
            if not self.start_menu_open: return
            try: focused = self.root.focus_get()
            except Exception: focused = None
            if focused is None: return
            try:
                if not str(focused).startswith(str(self.start_menu)):
                    self.hide_start_menu()
            except Exception:
                pass
        self.root.after(200, check)

    def hide_start_menu(self):
        if self.start_menu and self.start_menu.winfo_exists():
            try: self.start_menu.withdraw()
            except Exception: pass
        self.start_menu_open = False

    # ====================== 系统设置 ======================
    def _refresh_time(self):
        try:
            if not self.time_label.winfo_exists():
                return
            dt = datetime.datetime.now()
            sec = self.prefs.get("show_seconds", False)
            if self.prefs.get("clock_24h", True):
                clock = dt.strftime("%H:%M:%S" if sec else "%H:%M")
            else:
                h = dt.hour % 12 or 12
                clock = f"{h:02d}:{dt.minute:02d}"
                if sec:
                    clock += f":{dt.second:02d}"
                clock += " AM" if dt.hour < 12 else " PM"
            now = dt.strftime("%Y-%m-%d ") + clock
            if self._last_time_text != now:
                self._last_time_text = now
                self.time_label.config(text=f"🕐 {now}")
            self.safe_after(1000, self._refresh_time)
        except Exception:
            pass

    # ---------- 设置持久化 ----------
    def load_settings(self):
        """读取 settings.json。任何坏数据都忽略，绝不让配置损坏拖垮启动"""
        if os.path.exists(SETTINGS_PATH):
            try:
                with open(SETTINGS_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    for key, default in DEFAULT_SETTINGS.items():
                        val = data.get(key, default)
                        if isinstance(default, bool) and not isinstance(val, bool):
                            val = default        # 类型不对就用默认值
                        self.prefs[key] = val
            except Exception:
                pass
        w = self._normalize_color(self.prefs.get("wallpaper"))
        self.current_wallpaper = w or DEFAULT_SETTINGS["wallpaper"]
        self.prefs["wallpaper"] = self.current_wallpaper
        return self.prefs

    def save_settings(self):
        try:
            self.prefs["wallpaper"] = self.current_wallpaper
            with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
                json.dump(self.prefs, f, ensure_ascii=False, indent=2)
            return True
        except Exception:
            return False

    def reset_settings(self):
        self.prefs = dict(DEFAULT_SETTINGS)
        self.save_settings()

    @staticmethod
    def _normalize_color(color):
        """校验并规范化 #RRGGBB，非法返回 None"""
        if not isinstance(color, str):
            return None
        c = color.strip().lower()
        if not c.startswith("#"):
            c = "#" + c
        return c if re.fullmatch(r"#[0-9a-f]{6}", c) else None

    def wallpaper_name(self):
        for name, color in WALLPAPER_THEMES:
            if color == self.current_wallpaper:
                return name
        return f"自定义 {self.current_wallpaper}"

    def apply_wallpaper(self, color, save=True):
        """换壁纸：所有"壁纸层"控件一起变色，并写入 settings.json"""
        color = self._normalize_color(color)
        if not color:
            return False
        old = self.current_wallpaper
        self.current_wallpaper = color
        self.prefs["wallpaper"] = color
        self._wallpaper_known.add(color)
        self._wallpaper_known.add(old)

        def update_bg(widget):
            try:
                if widget.cget("bg") in self._wallpaper_known:
                    widget.config(bg=color)
            except Exception:
                pass
            for child in widget.winfo_children():
                update_bg(child)

        try:
            self.bg.config(bg=color)
            update_bg(self.bg)
        except Exception:
            pass

        if save:
            self.save_settings()
        return True

    def change_wallpaper(self):
        """任务栏/开始菜单里的"更换壁纸"：循环切换并记住"""
        try:
            idx = WALLPAPERS.index(self.current_wallpaper)
        except ValueError:
            idx = -1
        self.apply_wallpaper(WALLPAPERS[(idx + 1) % len(WALLPAPERS)])

    def shutdown(self):
        if messagebox.askyesno("关机", "确认要关机吗？"):
            self.cancel_all_after()
            self.close_all_windows()
            try:
                if self.start_menu and self.start_menu.winfo_exists():
                    self.start_menu.destroy()
            except Exception:
                pass
            self.root.quit()
            self.root.destroy()

    def task_manager(self):
        """📊 进程管理器"""
        win = self.register_window(tk.Toplevel())
        win.title("📊 任务管理器")
        win.geometry("500x400")
        win.configure(bg=Theme.BG_MAIN)

        # 顶部标题
        header = tk.Frame(win, bg=Theme.BG_CARD, height=50)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text="📊 运行中的进程 / 窗口", font=("微软雅黑", 12, "bold"),
                 bg=Theme.BG_CARD, fg=Theme.ACCENT).pack(side=tk.LEFT, padx=15, pady=15)

        # 列表框架
        list_frame = tk.Frame(win, bg=Theme.BG_PANEL)
        list_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        columns = ("win_id", "title")
        tree = ttk.Treeview(list_frame, columns=columns, show="headings", style="Custom.Treeview")
        tree.heading("win_id", text="进程 ID (Win ID)")
        tree.heading("title", text="窗口名称 / 应用名")
        tree.column("win_id", width=120, anchor="center")
        tree.column("title", width=300, anchor="w")

        # 配置滚动条
        vsb = ttk.Scrollbar(list_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        vsb.pack(side=tk.RIGHT, fill=tk.Y)

        # 核心：扫描所有窗口
        def scan_windows():
            for item in tree.get_children():
                tree.delete(item)

            # 我们系统里有一个 self._open_windows 集合专门记录所有打开的窗口
            for w in list(self._open_windows):
                if w.winfo_exists():
                    # 如果窗口最小化了，标题可能为空，给个默认名
                    title = w.title() if w.title() else "未命名窗口"
                    # 系统主窗口不杀
                    if title != SYS_NAME:
                        tree.insert("", "end", values=(str(w.winfo_id()), title), iid=str(w.winfo_id()))

        def kill_process():
            sel = tree.selection()
            if not sel: return
            win_id = int(sel[0])

            if messagebox.askyesno("结束进程", "确定要强制关闭这个窗口吗？未保存的数据会丢失！", parent=win):
                for w in list(self._open_windows):
                    if w.winfo_exists() and w.winfo_id() == win_id:
                        # 走正规关闭流程：取消定时器 → 移出列表 → 销毁
                        try:
                            handler = getattr(w, "_on_close", None)
                            if handler:
                                handler()
                            else:
                                w.destroy()
                        except Exception:
                            pass
                        self._open_windows.discard(w)
                        break
            scan_windows()

        # 底部按钮
        bottom = tk.Frame(win, bg=Theme.BG_MAIN)
        bottom.pack(fill=tk.X, padx=10, pady=(0, 10))

        HoverButton(bottom, "🔄 刷新列表", scan_windows, Theme.BTN_PRIMARY).pack(side=tk.LEFT, padx=5)
        HoverButton(bottom, "🛑 结束进程", kill_process, Theme.BTN_DANGER).pack(side=tk.LEFT, padx=5)

        scan_windows()

    def settings(self):
        """⚙️ 设置中心：所有选项即时生效并写入 settings.json"""
        win = self.register_window(tk.Toplevel())
        win.title("⚙️ 设置中心")
        win.geometry("680x660")
        win.configure(bg=Theme.BG_MAIN)
        win.resizable(False, False)

        header = tk.Frame(win, bg=Theme.BG_CARD, height=56)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text="⚙️ 系统设置", font=("微软雅黑", 16, "bold"),
                 bg=Theme.BG_CARD, fg=Theme.TEXT).pack(side=tk.LEFT, padx=20, pady=12)
        tk.Label(header, text="改动即时生效，并自动保存", font=("微软雅黑", 9),
                 bg=Theme.BG_CARD, fg=Theme.TEXT_DIM).pack(side=tk.RIGHT, padx=20)

        content = tk.Frame(win, bg=Theme.BG_MAIN)
        content.pack(fill=tk.BOTH, expand=True, padx=18, pady=(12, 10))

        def make_group(title):
            g = tk.LabelFrame(content, text=title, font=("微软雅黑", 10, "bold"),
                              bg=Theme.BG_MAIN, fg=Theme.ACCENT, bd=1,
                              relief=tk.GROOVE, labelanchor="nw")
            g.pack(fill=tk.X, pady=(0, 8))
            return g

        def make_check(parent_, text, var, key):
            return tk.Checkbutton(parent_, text=text, variable=var,
                                  bg=Theme.BG_MAIN, fg=Theme.TEXT,
                                  activebackground=Theme.BG_MAIN,
                                  activeforeground=Theme.TEXT,
                                  selectcolor=Theme.BG_PANEL, bd=0,
                                  font=("微软雅黑", 10), cursor="hand2",
                                  command=lambda: self._toggle_setting(key, var))

        # ================= 1. 壁纸 =================
        g1 = make_group("🎨 桌面壁纸")
        wall_tip = tk.Label(g1, text=f"当前：{self.wallpaper_name()}", font=("微软雅黑", 9),
                            bg=Theme.BG_MAIN, fg=Theme.TEXT_DIM)
        wall_tip.pack(anchor="w", padx=12, pady=(2, 0))

        swatch_row = tk.Frame(g1, bg=Theme.BG_MAIN)
        swatch_row.pack(anchor="w", padx=10, pady=6)
        swatches = {}

        def mark_current():
            for color, btn in swatches.items():
                try:
                    on = (color == self.current_wallpaper)
                    btn.config(relief=tk.SOLID if on else tk.FLAT,
                               bd=2 if on else 0,
                               highlightthickness=1 if on else 0,
                               highlightbackground=Theme.ACCENT,
                               highlightcolor=Theme.ACCENT)
                except Exception:
                    pass

        def pick(color, name):
            if not self.apply_wallpaper(color):
                return
            wall_tip.config(text=f"当前：{name}", fg=Theme.BTN_SUCCESS)
            mark_current()

        for i, (name, color) in enumerate(WALLPAPER_THEMES):
            b = tk.Button(swatch_row, text=name, bg=color, fg=Theme.TEXT_DIM,
                          font=("微软雅黑", 8), width=7, height=2, bd=0,
                          relief=tk.FLAT, activebackground=color,
                          activeforeground=Theme.TEXT, cursor="hand2",
                          command=lambda c=color, n=name: pick(c, n))
            b.grid(row=i // 5, column=i % 5, padx=3, pady=3)
            swatches[color] = b
        mark_current()

        def custom_color():
            c = colorchooser.askcolor(title="选择壁纸颜色", parent=win)[1]
            if not c:
                return
            c = self._normalize_color(c)
            if not c:
                messagebox.showerror("颜色无效", "无法识别的颜色值。", parent=win)
                return
            pick(c, f"自定义 {c}")

        bottom_row = tk.Frame(g1, bg=Theme.BG_MAIN)
        bottom_row.pack(anchor="w", padx=12, pady=(0, 8))
        HoverButton(bottom_row, "🎨 自定义颜色", custom_color, Theme.BTN_PURPLE,
                    width=12).pack(side=tk.LEFT)

        # ================= 2. 时间 =================
        g2 = make_group("🕐 时间与任务栏")
        row2 = tk.Frame(g2, bg=Theme.BG_MAIN)
        row2.pack(anchor="w", padx=12, pady=8)
        var_24h = tk.BooleanVar(value=self.prefs.get("clock_24h", True))
        var_sec = tk.BooleanVar(value=self.prefs.get("show_seconds", False))
        make_check(row2, "24 小时制", var_24h, "clock_24h").pack(side=tk.LEFT, padx=(0, 24))
        make_check(row2, "显示秒", var_sec, "show_seconds").pack(side=tk.LEFT)

        # ================= 3. 桌面 =================
        g3 = make_group("🖥️ 桌面")
        row3 = tk.Frame(g3, bg=Theme.BG_MAIN)
        row3.pack(anchor="w", padx=12, pady=8)
        var_icons = tk.BooleanVar(value=self.prefs.get("show_desktop_icons", True))

        def toggle_icons():
            self.prefs["show_desktop_icons"] = bool(var_icons.get())
            self.save_settings()
            self.refresh_desktop_icons(force=True)

        tk.Checkbutton(row3, text="显示桌面图标", variable=var_icons,
                       bg=Theme.BG_MAIN, fg=Theme.TEXT,
                       activebackground=Theme.BG_MAIN, activeforeground=Theme.TEXT,
                       selectcolor=Theme.BG_PANEL, bd=0, font=("微软雅黑", 10),
                       cursor="hand2", command=toggle_icons).pack(side=tk.LEFT)

        # ================= 4. 账户 =================
        g4 = make_group("🔒 账户")

        def modify_pwd():
            old = simpledialog.askstring("验证旧密码", "请输入当前登录密码：", show="*", parent=win)
            if not old:
                return
            users = self.load_users()
            if users.get(self.login_user, "") != old:
                messagebox.showerror("错误", "原密码不正确！", parent=win)
                return
            new_p = simpledialog.askstring("设置新密码", "请输入新密码：", show="*", parent=win)
            if not new_p:
                return
            try:
                lines = []
                with open(USER_DB_PATH, "r", encoding="utf-8") as f:
                    for line in f.readlines():
                        u, p = line.strip().split("|")
                        if u == self.login_user:
                            lines.append(f"{u}|{new_p}\n")
                        else:
                            lines.append(line)
                with open(USER_DB_PATH, "w", encoding="utf-8") as f:
                    f.writelines(lines)
                messagebox.showinfo("成功", "密码修改成功！下次登录请使用新密码。", parent=win)
            except Exception as e:
                messagebox.showerror("失败", str(e), parent=win)

        HoverButton(g4, "修改登录密码", modify_pwd, Theme.BTN_WARNING,
                    width=12).pack(anchor="w", padx=12, pady=(6, 8))

        # ================= 5. 系统信息 =================
        g5 = make_group("ℹ️ 系统信息")
        tk.Label(g5, text=self._system_info_text(), font=("微软雅黑", 9),
                 bg=Theme.BG_MAIN, fg=Theme.TEXT_DIM,
                 justify="left").pack(anchor="w", padx=12, pady=(4, 8))

        # ================= 底部按钮 =================
        bar = tk.Frame(content, bg=Theme.BG_MAIN)
        bar.pack(fill=tk.X)

        def do_reset():
            if not messagebox.askyesno("恢复默认设置",
                                       "壁纸、时间格式、桌面图标显示都会回到默认，确定吗？",
                                       parent=win):
                return
            self.reset_settings()
            self.apply_wallpaper(DEFAULT_SETTINGS["wallpaper"], save=False)
            self.refresh_desktop_icons(force=True)
            self._last_time_text = ""
            messagebox.showinfo("完成", "已恢复默认设置，重新打开设置中心即可看到变化。", parent=win)
            try:
                win._on_close()
            except Exception:
                pass

        HoverButton(bar, "♻️ 恢复默认设置", do_reset, Theme.BTN_DEFAULT,
                    width=14).pack(side=tk.LEFT)
        HoverButton(bar, "📂 打开虚拟磁盘", self.file_manager, Theme.BTN_PRIMARY,
                    width=14).pack(side=tk.LEFT, padx=10)
        HoverButton(bar, "🗑 关闭", lambda: win._on_close(), Theme.BTN_DANGER,
                    width=8).pack(side=tk.RIGHT)

    def _toggle_setting(self, key, var):
        """开关类设置统一入口：写内存 -> 落盘 -> 立刻刷新时间显示"""
        self.prefs[key] = bool(var.get())
        self.save_settings()
        self._last_time_text = ""
        try:
            self._refresh_time_once()
        except Exception:
            pass

    def _refresh_time_once(self):
        try:
            dt = datetime.datetime.now()
            sec = self.prefs.get("show_seconds", False)
            if self.prefs.get("clock_24h", True):
                clock = dt.strftime("%H:%M:%S" if sec else "%H:%M")
            else:
                h = dt.hour % 12 or 12
                clock = f"{h:02d}:{dt.minute:02d}"
                if sec:
                    clock += f":{dt.second:02d}"
                clock += " AM" if dt.hour < 12 else " PM"
            self._last_time_text = dt.strftime("%Y-%m-%d ") + clock
            self.time_label.config(text=f"🕐 {self._last_time_text}")
        except Exception:
            pass

    def _system_info_text(self):
        try:
            names = os.listdir(DISK_PATH)
            total = 0
            for n in names:
                p = os.path.join(DISK_PATH, n)
                if os.path.isfile(p):
                    total += os.path.getsize(p)
        except Exception:
            names, total = [], 0
        store = getattr(self, "app_store", None)
        apps = len(getattr(store, "installed_apps", []) or [])
        desk = len(getattr(store, "desktop_apps", []) or [])
        return (f"版本：{SYS_NAME}      当前用户：{self.login_user or '未登录'}\n"
                f"应用：已安装 {apps} 个，桌面显示 {desk} 个\n"
                f"虚拟磁盘：{len(names)} 个文件，占用 {total / 1024:.1f} KB\n"
                f"框架：Python + Tkinter，插件化 App Store")

    # ====================== 基础应用 ======================
    def file_manager(self):
        win = self.register_window(tk.Toplevel())
        win.title("文件管理器")
        win.geometry("720x460")
        win.configure(bg=Theme.BG_MAIN)

        title = tk.Frame(win, bg=Theme.BG_CARD, height=40)
        title.pack(fill=tk.X)
        title.pack_propagate(False)
        tk.Label(title, text="📁 文件管理器（虚拟磁盘）", font=("微软雅黑", 12, "bold"),
                 bg=Theme.BG_CARD, fg=Theme.TEXT).pack(side=tk.LEFT, padx=15, pady=10)

        main = tk.Frame(win, bg=Theme.BG_MAIN)
        main.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        left = tk.Frame(main, bg=Theme.BG_PANEL)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        listbox = tk.Listbox(left, font=("微软雅黑", 11), bg=Theme.BG_PANEL,
                             fg=Theme.TEXT, selectbackground=Theme.BG_HOVER,
                             selectforeground=Theme.TEXT, relief=tk.FLAT, bd=0,
                             highlightthickness=0)
        listbox.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        right = tk.Frame(main, bg=Theme.BG_MAIN, width=120)
        right.pack(side=tk.RIGHT, padx=(10, 0))
        right.pack_propagate(False)

        def refresh():
            if not listbox.winfo_exists(): return
            listbox.delete(0, tk.END)
            try:
                for f in os.listdir(DISK_PATH):
                    listbox.insert(tk.END, f"  📄  {f}")
            except Exception: pass

        def get_selected():
            sel = listbox.curselection()
            if not sel: return None
            return listbox.get(sel[0]).replace("📄", "").strip()

        DEFAULT_EXT = ".txt"
        ILLEGAL_CHARS = '\\/:*?"<>|'

        def clean_name(name):
            """去掉路径部分和非法字符，空则返回 None"""
            if not name:
                return None
            name = os.path.basename(name.strip())
            for ch in ILLEGAL_CHARS:
                name = name.replace(ch, "_")
            name = name.strip()
            return name or None

        def normalize_name(name, keep_ext_from=None):
            """没有扩展名时自动补后缀；重命名沿用原文件的后缀"""
            name = clean_name(name)
            if not name:
                return None
            if not os.path.splitext(name)[1]:
                ext = os.path.splitext(keep_ext_from)[1] if keep_ext_from else ""
                name += ext or DEFAULT_EXT
            return name

        def new_file():
            n = simpledialog.askstring("新建文件", "输入文件名（不写后缀默认 .txt）", parent=win)
            n = normalize_name(n)
            if not n:
                return
            if os.path.exists(os.path.join(DISK_PATH, n)):
                messagebox.showwarning("提示", f"{n} 已存在", parent=win)
                return
            try:
                open(os.path.join(DISK_PATH, n), "w", encoding="utf-8").close()
                refresh()
            except Exception as e:
                messagebox.showerror("错误", str(e), parent=win)

        def rename_file():
            old = get_selected()
            if not old: return
            new = simpledialog.askstring("重命名", "新文件名（不写后缀沿用原后缀）", parent=win)
            new = normalize_name(new, keep_ext_from=old)
            if not new:
                return
            if new == old:
                return
            if os.path.exists(os.path.join(DISK_PATH, new)):
                messagebox.showwarning("提示", f"{new} 已存在", parent=win)
                return
            try:
                os.rename(os.path.join(DISK_PATH, old),
                          os.path.join(DISK_PATH, new))
                refresh()
            except Exception as e:
                messagebox.showerror("错误", str(e), parent=win)

        def del_file():
            name = get_selected()
            if not name: return
            if messagebox.askyesno("删除", f"确认删除 {name}？", parent=win):
                try:
                    os.remove(os.path.join(DISK_PATH, name))
                    refresh()
                except Exception as e:
                    messagebox.showerror("错误", str(e), parent=win)

        def open_file():
            name = get_selected()
            if not name: return
            fp = os.path.join(DISK_PATH, name)

            w = self.register_window(tk.Toplevel())
            w.title(f"查看 - {name}")
            w.geometry("600x450")
            w.configure(bg=Theme.BG_MAIN)
            st = scrolledtext.ScrolledText(w, font=("Consolas", 10),
                                            bg=Theme.BG_PANEL, fg=Theme.TEXT,
                                            relief=tk.FLAT, bd=0)
            st.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
            try:
                with open(fp, "r", encoding="utf-8") as f:
                    st.insert(tk.END, f.read())
            except Exception as e:
                st.insert(tk.END, f"读取失败：{e}")
            st.config(state=tk.DISABLED)

        HoverButton(right, "➕ 新建", new_file, Theme.BTN_SUCCESS, width=8).pack(pady=4, fill=tk.X)
        HoverButton(right, "✏️ 重命名", rename_file, Theme.BTN_WARNING, width=8).pack(pady=4, fill=tk.X)
        HoverButton(right, "📂 打开", open_file, Theme.BTN_PRIMARY, width=8).pack(pady=4, fill=tk.X)
        HoverButton(right, "🗑 删除", del_file, Theme.BTN_DANGER, width=8).pack(pady=4, fill=tk.X)
        HoverButton(right, "🔄 刷新", refresh, Theme.BTN_DEFAULT, width=8).pack(pady=4, fill=tk.X)

        listbox.bind("<Double-Button-1>", lambda e: open_file())
        refresh()

    def notepad(self):
        win = self.register_window(tk.Toplevel())
        win.title("记事本")
        win.geometry("620x500")
        win.configure(bg=Theme.BG_MAIN)
        win._modified = False

        text = scrolledtext.ScrolledText(win, font=("微软雅黑", 11),
                                          bg=Theme.BG_PANEL, fg=Theme.TEXT,
                                          insertbackground=Theme.ACCENT,
                                          relief=tk.FLAT, bd=0,
                                          padx=10, pady=10)
        text.pack(fill=tk.BOTH, expand=True, padx=10, pady=(10, 5))

        def on_modify(event=None): win._modified = True
        text.bind("<<Modified>>", on_modify)
        text.edit_modified(False)

        cur_file = tk.StringVar(value="未命名文档")
        title_var = tk.StringVar(value="未命名文档")

        def save():
            fn = cur_file.get()
            if fn == "未命名文档":
                fn = simpledialog.askstring("保存文件", "文件名", parent=win)
                if not fn: return
                if not fn.endswith(".txt"): fn += ".txt"
                cur_file.set(fn)
            try:
                with open(os.path.join(DISK_PATH, fn), "w", encoding="utf-8") as f:
                    f.write(text.get("1.0", tk.END))
                win._modified = False
                title_var.set(fn)
                messagebox.showinfo("成功", "文件已保存", parent=win)
            except Exception as e:
                messagebox.showerror("错误", str(e), parent=win)

        def open_doc():
            try: flist = os.listdir(DISK_PATH)
            except Exception: flist = []
            if not flist:
                messagebox.showinfo("提示", "暂无文件", parent=win)
                return
            sel = simpledialog.askstring("打开文件", "现有文件：\n" + "\n".join(flist) + "\n\n输入文件名", parent=win)
            if sel and sel in flist:
                try:
                    cur_file.set(sel)
                    title_var.set(sel)
                    with open(os.path.join(DISK_PATH, sel), "r", encoding="utf-8") as f:
                        text.delete("1.0", tk.END)
                        text.insert(tk.END, f.read())
                    win._modified = False
                except Exception as e:
                    messagebox.showerror("错误", str(e), parent=win)

        bar = tk.Frame(win, bg=Theme.BG_MAIN)
        bar.pack(fill=tk.X, padx=10, pady=(0, 10))
        HoverButton(bar, "📂 打开", open_doc, Theme.BTN_PRIMARY).pack(side=tk.LEFT, padx=3)
        HoverButton(bar, "💾 保存", save, Theme.BTN_SUCCESS).pack(side=tk.LEFT, padx=3)
        tk.Label(bar, textvariable=title_var, bg=Theme.BG_MAIN, fg=Theme.TEXT_DIM, font=("微软雅黑", 9)).pack(side=tk.RIGHT, padx=10)

        def on_close():
            if win._modified:
                r = messagebox.askyesnocancel("提示", "内容未保存，是否保存？", parent=win)
                if r is None: return
                if r:
                    save()
                    if win._modified: return
            self._open_windows.discard(win)
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", on_close)

    def calculator(self):
        win = self.register_window(tk.Toplevel())
        win.title("计算器")
        win.geometry("320x440")
        win.configure(bg=Theme.BG_MAIN)
        win.resizable(False, False)

        var = tk.StringVar()
        display = tk.Entry(win, textvariable=var, font=("Consolas", 22, "bold"),
                           justify="right", bg=Theme.BG_PANEL, fg=Theme.ACCENT,
                           insertbackground=Theme.ACCENT, relief=tk.FLAT, bd=0)
        display.pack(fill=tk.X, padx=15, pady=15, ipady=12)

        def safe_eval(expr):
            if not re.match(r"^[\d+\-*/().%\s]+$", expr):
                raise ValueError("非法字符")
            return eval(expr, {"__builtins__": {}}, {})

        def eq():
            try:
                result = safe_eval(var.get())
                var.set(str(result))
            except ZeroDivisionError:
                var.set("除以零")
            except Exception:
                var.set("计算错误")

        frm = tk.Frame(win, bg=Theme.BG_MAIN)
        frm.pack(fill=tk.BOTH, expand=True, padx=10, pady=(0, 10))

        keys = [("C", 0, 0), ("(", 0, 1), (")", 0, 2), ("/", 0, 3),
                ("7", 1, 0), ("8", 1, 1), ("9", 1, 2), ("*", 1, 3),
                ("4", 2, 0), ("5", 2, 1), ("6", 2, 2), ("-", 2, 3),
                ("1", 3, 0), ("2", 3, 1), ("3", 3, 2), ("+", 3, 3),
                ("0", 4, 0), (".", 4, 1), ("%", 4, 2), ("=", 4, 3)]

        for t, r, c in keys:
            if t == "=": color = Theme.BTN_SUCCESS
            elif t == "C": color = Theme.BTN_DANGER
            elif t in "+-*/%()": color = Theme.BTN_WARNING
            else: color = Theme.BTN_DEFAULT

            if t == "=": cmd = eq
            elif t == "C": cmd = lambda: var.set("")
            else: cmd = (lambda x=t: var.set(var.get() + x))

            btn = HoverButton(frm, t, cmd, color)
            btn.config(font=("Consolas", 14, "bold"))
            btn.grid(row=r, column=c, sticky="nsew", padx=3, pady=3)

        for i in range(5): frm.grid_rowconfigure(i, weight=1)
        for i in range(4): frm.grid_columnconfigure(i, weight=1)

    def timer_tool(self):
        win = self.register_window(tk.Toplevel())
        win.title("倒计时")
        win.geometry("360x300")
        win.configure(bg=Theme.BG_MAIN)

        text_var = tk.StringVar(value="00:00")
        tk.Label(win, textvariable=text_var, font=("Consolas", 42, "bold"), bg=Theme.BG_MAIN, fg=Theme.ACCENT).pack(pady=20)

        input_frame = tk.Frame(win, bg=Theme.BG_MAIN)
        input_frame.pack()
        m_in = tk.Entry(input_frame, font=("微软雅黑", 14), width=8, justify="center", bg=Theme.BG_PANEL, fg=Theme.TEXT, insertbackground=Theme.ACCENT, relief=tk.FLAT, bd=0)
        m_in.insert(0, "1")
        m_in.pack(side=tk.LEFT, ipady=5, padx=5)
        tk.Label(input_frame, text="分钟", font=("微软雅黑", 12), bg=Theme.BG_MAIN, fg=Theme.TEXT_DIM).pack(side=tk.LEFT)

        task_id = [None]
        running = [True]

        def close_window():
            running[0] = False
            if task_id[0] is not None:
                try: win.after_cancel(task_id[0])
                except: pass
            self._open_windows.discard(win)
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", close_window)

        def tick(left):
            if not running[0] or not win.winfo_exists(): return
            if left <= 0:
                text_var.set("时间到！")
                messagebox.showinfo("提醒", "倒计时结束", parent=win)
                return
            m, s = left // 60, left % 60
            text_var.set(f"{m:02d}:{s:02d}")
            task_id[0] = win.after(1000, tick, left - 1)

        def start():
            if task_id[0] is not None:
                try: win.after_cancel(task_id[0])
                except: pass
                task_id[0] = None
            try:
                total = int(m_in.get()) * 60
                if total <= 0: raise ValueError
                tick(total)
            except ValueError:
                messagebox.showerror("错误", "请输入正整数", parent=win)

        HoverButton(win, "▶ 开始倒计时", start, Theme.BTN_SUCCESS, width=14).pack(pady=15)

    def paint_tool(self):
        win = self.register_window(tk.Toplevel())
        win.title("画图")
        win.geometry("760x620")
        win.configure(bg=Theme.BG_MAIN)

        canvas = tk.Canvas(win, bg="white", width=680, height=470, relief=tk.FLAT, bd=0, highlightthickness=0)
        canvas.pack(pady=10)
        color = ["black"]
        size_var = tk.IntVar(value=3)
        current_image = {"img": None, "path": None}

        def pick_color():
            c = colorchooser.askcolor()[1]
            if c: color[0] = c

        def draw_line(event):
            x, y = event.x, event.y
            r = size_var.get()
            if hasattr(draw_line, "last"):
                lx, ly = draw_line.last
                canvas.create_line(lx, ly, x, y, fill=color[0], width=r * 2, capstyle=tk.ROUND, smooth=True)
            draw_line.last = (x, y)

        def start_draw(event): draw_line.last = (event.x, event.y)
        def stop_draw(event):
            if hasattr(draw_line, "last"): del draw_line.last

        canvas.bind("<Button-1>", start_draw)
        canvas.bind("<B1-Motion>", draw_line)
        canvas.bind("<ButtonRelease-1>", stop_draw)

        def save_as_image():
            try:
                from PIL import Image, ImageDraw
            except ImportError:
                messagebox.showerror("缺少依赖", "需要安装 Pillow 库才能保存图片\n\n请在命令行运行：\n\npip install Pillow", parent=win)
                return

            path = filedialog.asksaveasfilename(parent=win, title="保存图片", defaultextension=".png", filetypes=[("PNG 图片", "*.png"), ("所有文件", "*.*")])
            if not path: return

            try:
                w = canvas.winfo_width()
                h = canvas.winfo_height()
                if w <= 1: w, h = 680, 470
                img = Image.new("RGB", (w, h), "white")
                draw = ImageDraw.Draw(img)

                for item in canvas.find_all():
                    item_type = canvas.type(item)
                    coords = canvas.coords(item)
                    fill = canvas.itemcget(item, "fill")

                    if item_type == "oval" and len(coords) == 4:
                        try: draw.ellipse(coords, fill=fill or "black")
                        except: pass
                    elif item_type == "line":
                        try:
                            width = int(float(canvas.itemcget(item, "width")))
                        except: width = 1
                        try: draw.line(coords, fill=fill or "black", width=width)
                        except: pass
                    elif item_type == "rectangle":
                        try: draw.rectangle(coords, fill=fill or "black")
                        except: pass

                img.save(path)
                current_image["path"] = path
                messagebox.showinfo("成功", f"✅ 图片已保存到：\n{path}", parent=win)
            except Exception as e:
                messagebox.showerror("保存失败", str(e), parent=win)

        def open_image():
            try:
                from PIL import Image, ImageTk
            except ImportError:
                messagebox.showerror("缺少依赖", "需要安装 Pillow 库才能打开图片\n\n请在命令行运行：\n\npip install Pillow", parent=win)
                return

            path = filedialog.askopenfilename(parent=win, title="打开图片", filetypes=[("图片文件", "*.png *.jpg *.jpeg *.bmp *.gif"), ("所有文件", "*.*")])
            if not path: return

            try:
                img = Image.open(path)
                max_w = canvas.winfo_width() if canvas.winfo_width() > 1 else 680
                max_h = canvas.winfo_height() if canvas.winfo_height() > 1 else 470
                img.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)

                photo = ImageTk.PhotoImage(img)
                canvas.delete("all")
                cx, cy = (max_w - img.width) // 2, (max_h - img.height) // 2
                canvas.create_image(cx, cy, anchor="nw", image=photo)

                current_image["img"] = photo
                current_image["path"] = path
            except Exception as e:
                messagebox.showerror("打开失败", str(e), parent=win)

        def clear_canvas():
            if messagebox.askyesno("清空", "确认清空画布？", parent=win):
                canvas.delete("all")
                current_image["img"] = None
                current_image["path"] = None

        bar = tk.Frame(win, bg=Theme.BG_MAIN)
        bar.pack(fill=tk.X, padx=10, pady=5)

        left_btns = tk.Frame(bar, bg=Theme.BG_MAIN)
        left_btns.pack(side=tk.LEFT)
        HoverButton(left_btns, "🎨 调色板", pick_color, Theme.BTN_PURPLE).pack(side=tk.LEFT, padx=3)
        HoverButton(left_btns, "🧹 橡皮擦", lambda: color.__setitem__(0, "white"), Theme.BTN_DEFAULT).pack(side=tk.LEFT, padx=3)
        tk.Label(left_btns, text="笔刷:", bg=Theme.BG_MAIN, fg=Theme.TEXT).pack(side=tk.LEFT, padx=(10, 3))
        tk.Scale(left_btns, from_=1, to=20, orient=tk.HORIZONTAL, variable=size_var, bg=Theme.BG_MAIN, fg=Theme.TEXT, troughcolor=Theme.BG_PANEL, highlightthickness=0, length=100).pack(side=tk.LEFT)

        right_btns = tk.Frame(bar, bg=Theme.BG_MAIN)
        right_btns.pack(side=tk.RIGHT)
        HoverButton(right_btns, "📂 打开", open_image, Theme.BTN_PRIMARY).pack(side=tk.RIGHT, padx=3)
        HoverButton(right_btns, "💾 保存", save_as_image, Theme.BTN_SUCCESS).pack(side=tk.RIGHT, padx=3)
        HoverButton(right_btns, "🗑 清空", clear_canvas, Theme.BTN_DANGER).pack(side=tk.RIGHT, padx=3)

    # ====================== 其他小工具 & 游戏 ======================
    def rgb_color_picker(self):
        win = self.register_window(tk.Toplevel())
        win.title("RGB调色盘")
        win.geometry("520x520")
        win.configure(bg=Theme.BG_MAIN)
        win.resizable(False, False)

        preview_label = tk.Label(win, bg="#000000", width=22, height=5, relief=tk.FLAT, bd=0)
        preview_label.pack(pady=20)

        hex_var = tk.StringVar(value="#000000")
        tk.Label(win, textvariable=hex_var, font=("Consolas", 16, "bold"), bg=Theme.BG_MAIN, fg=Theme.ACCENT).pack()

        r_var, g_var, b_var = tk.IntVar(value=0), tk.IntVar(value=0), tk.IntVar(value=0)

        def update_color(*args):
            r, g, b = r_var.get(), g_var.get(), b_var.get()
            hex_color = f"#{r:02x}{g:02x}{b:02x}"
            preview_label.config(bg=hex_color)
            hex_var.set(hex_color.upper())

        frame = tk.Frame(win, bg=Theme.BG_MAIN)
        frame.pack(pady=15)

        for i, (label, var, color) in enumerate([("R", r_var, "#e74c3c"), ("G", g_var, "#2ecc71"), ("B", b_var, "#3498db")]):
            tk.Label(frame, text=label, bg=Theme.BG_MAIN, fg=color, font=("微软雅黑", 14, "bold"), width=2).grid(row=i, column=0, padx=5, pady=8)
            scale = tk.Scale(frame, from_=0, to=255, orient=tk.HORIZONTAL, variable=var, length=280, bg=Theme.BG_MAIN, fg=Theme.TEXT, troughcolor=Theme.BG_PANEL, highlightthickness=0, command=update_color)
            scale.grid(row=i, column=1, padx=5)
            tk.Label(frame, textvariable=var, bg=Theme.BG_MAIN, fg=Theme.TEXT, width=4, font=("Consolas", 11)).grid(row=i, column=2)

        tk.Label(win, text="快捷颜色：", bg=Theme.BG_MAIN, fg=Theme.TEXT_DIM, font=("微软雅黑", 10)).pack()

        presets = ["#FF0000", "#FF8800", "#FFFF00", "#00FF00", "#00FFFF", "#0000FF", "#8800FF", "#FF00FF", "#FFFFFF", "#000000"]
        def set_preset(color):
            r_var.set(int(color[1:3], 16))
            g_var.set(int(color[3:5], 16))
            b_var.set(int(color[5:7], 16))
            update_color()

        color_row = tk.Frame(win, bg=Theme.BG_MAIN)
        color_row.pack(pady=8)
        for color in presets:
            tk.Button(color_row, bg=color, width=3, height=1, relief=tk.FLAT, bd=1, cursor="hand2", command=lambda c=color: set_preset(c)).pack(side=tk.LEFT, padx=2)

        update_color()

    def clock_widget(self):
        win = self.register_window(tk.Toplevel())
        win.title("数字时钟")
        win.geometry("420x260")
        win.configure(bg=Theme.BG_MAIN)

        time_text = tk.StringVar(value="00:00:00")
        date_text = tk.StringVar(value="2000-01-01")

        tk.Label(win, textvariable=date_text, font=("微软雅黑", 14), bg=Theme.BG_MAIN, fg=Theme.TEXT_DIM).pack(pady=25)
        tk.Label(win, textvariable=time_text, font=("Consolas", 48, "bold"), bg=Theme.BG_MAIN, fg=Theme.ACCENT).pack()

        task_id = [None]
        def close_window():
            if task_id[0] is not None:
                try: win.after_cancel(task_id[0])
                except: pass
            self._open_windows.discard(win)
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", close_window)

        def update_clock():
            if not win.winfo_exists(): return
            now = datetime.datetime.now()
            date_text.set(now.strftime("%Y年%m月%d日 %A"))
            time_text.set(now.strftime("%H:%M:%S"))
            task_id[0] = win.after(1000, update_clock)

        update_clock()

    def random_draw(self):
        win = self.register_window(tk.Toplevel())
        win.title("随机抽签")
        win.geometry("450x400")
        win.configure(bg=Theme.BG_MAIN)

        tk.Label(win, text="📝 名单（每行一个）", font=("微软雅黑", 11), bg=Theme.BG_MAIN, fg=Theme.TEXT).pack(pady=(15, 5))
        text_box = scrolledtext.ScrolledText(win, height=10, bg=Theme.BG_PANEL, fg=Theme.TEXT, font=("微软雅黑", 10), relief=tk.FLAT, bd=0)
        text_box.pack(padx=15, fill=tk.BOTH, expand=True)

        result_var = tk.StringVar(value="✨ 等待抽签")
        tk.Label(win, textvariable=result_var, font=("微软雅黑", 16, "bold"), bg=Theme.BG_MAIN, fg=Theme.ACCENT).pack(pady=15)

        def draw():
            names = [n.strip() for n in text_box.get("1.0", tk.END).splitlines() if n.strip()]
            if not names:
                result_var.set("⚠ 请输入名单！")
                return
            result_var.set(f"🎉 抽中: {random.choice(names)}")

        HoverButton(win, "🎲 开始抽签", draw, Theme.BTN_PRIMARY, width=14).pack(pady=5)

    def game_guess(self):
        win = self.register_window(tk.Toplevel())
        win.title("猜数字")
        win.geometry("400x300")
        win.configure(bg=Theme.BG_MAIN)

        state = {"target": random.randint(1, 100), "tries": 0}

        tk.Label(win, text="🔢 猜数字（1~100）", font=("微软雅黑", 14, "bold"), bg=Theme.BG_MAIN, fg=Theme.ACCENT).pack(pady=20)
        msg = tk.StringVar(value="请输入你猜的数字")
        tk.Label(win, textvariable=msg, font=("微软雅黑", 12), bg=Theme.BG_MAIN, fg=Theme.TEXT).pack(pady=10)

        var = tk.StringVar()
        entry = tk.Entry(win, textvariable=var, font=("微软雅黑", 14), width=10, justify="center", bg=Theme.BG_PANEL, fg=Theme.TEXT, insertbackground=Theme.ACCENT, relief=tk.FLAT, bd=0)
        entry.pack(pady=5, ipady=5)
        entry.focus_force()

        def check(event=None):
            try:
                n = int(var.get())
                state["tries"] += 1
                if n == state["target"]: msg.set(f"🎉 答对了！共猜 {state['tries']} 次")
                elif n < state["target"]: msg.set(f"⬆ 偏小（已猜 {state['tries']} 次）")
                else: msg.set(f"⬇ 偏大（已猜 {state['tries']} 次）")
            except ValueError:
                msg.set("⚠ 请输入数字")

        entry.bind("<Return>", check)
        HoverButton(win, "提交", check, Theme.BTN_PRIMARY).pack(pady=10)

    def game_snake(self):
        win = self.register_window(tk.Toplevel())
        win.title("贪吃蛇")
        win.geometry("440x520")
        win.configure(bg=Theme.BG_MAIN)
        win.resizable(False, False)

        canvas = tk.Canvas(win, bg="#000000", width=400, height=400, highlightthickness=0)
        canvas.pack(pady=8)

        size = 20
        GRID = 20
        state = {"snake": [(100, 100), (80, 100)], "food": [random.randrange(0, GRID) * size, random.randrange(0, GRID) * size], "dx": size, "dy": 0, "score": 0, "running": True, "task_id": None}

        score_var = tk.StringVar(value="分数：0")
        tk.Label(win, textvariable=score_var, bg=Theme.BG_MAIN, fg=Theme.TEXT, font=("微软雅黑", 12)).pack()
        hint_var = tk.StringVar(value="⌨ 方向键控制 · 空格暂停")
        tk.Label(win, textvariable=hint_var, bg=Theme.BG_MAIN, fg=Theme.TEXT_DIM, font=("微软雅黑", 9)).pack(pady=2)

        ctrl = tk.Frame(win, bg=Theme.BG_MAIN)
        ctrl.pack(pady=6)

        def pause_game():
            state["running"] = not state["running"]
            if state["running"]:
                hint_var.set("⌨ 方向键控制 · 空格暂停")
                move()
            else:
                hint_var.set("⏸ 已暂停 · 按空格继续")
                if state["task_id"] is not None:
                    try:
                        win.after_cancel(state["task_id"])
                        state["task_id"] = None
                    except Exception: pass

        def restart_game():
            state["snake"] = [(100, 100), (80, 100)]
            state["food"] = [random.randrange(0, GRID) * size, random.randrange(0, GRID) * size]
            state["dx"] = size
            state["dy"] = 0
            state["score"] = 0
            state["running"] = True
            score_var.set("分数：0")
            hint_var.set("⌨ 方向键控制 · 空格暂停")
            if state["task_id"] is not None:
                try:
                    win.after_cancel(state["task_id"])
                    state["task_id"] = None
                except Exception: pass
            draw()
            move()

        HoverButton(ctrl, "⏸ 暂停", pause_game, Theme.BTN_WARNING).pack(side=tk.LEFT, padx=4)
        HoverButton(ctrl, "🔄 重来", restart_game, Theme.BTN_SUCCESS).pack(side=tk.LEFT, padx=4)

        def close_window():
            state["running"] = False
            if state["task_id"] is not None:
                try: win.after_cancel(state["task_id"])
                except Exception: pass
            self._open_windows.discard(win)
            win.destroy()

        win.protocol("WM_DELETE_WINDOW", close_window)

        def draw():
            if not canvas.winfo_exists(): return
            canvas.delete("all")
            for i in range(GRID):
                canvas.create_line(i * size, 0, i * size, 400, fill="#111")
                canvas.create_line(0, i * size, 400, i * size, fill="#111")
            fx, fy = state["food"]
            canvas.create_oval(fx + 3, fy + 3, fx + size - 3, fy + size - 3, fill="#e94560", outline="#8b0000", width=1)
            for i, (x, y) in enumerate(state["snake"]):
                if i == 0:
                    canvas.create_rectangle(x + 1, y + 1, x + size - 1, y + size - 1, fill="#00ff00", outline="#00aa00", width=2)
                else:
                    canvas.create_rectangle(x + 1, y + 1, x + size - 1, y + size - 1, fill="#00aa00", outline="#005500")

        def move():
            if not state["running"] or not win.winfo_exists(): return
            head = (state["snake"][0][0] + state["dx"], state["snake"][0][1] + state["dy"])

            if (head[0] < 0 or head[0] >= 400 or head[1] < 0 or head[1] >= 400 or head in state["snake"]):
                state["running"] = False
                hint_var.set(f"💀 游戏结束 · 得分：{state['score']}")
                messagebox.showerror("游戏结束", f"最终得分：{state['score']}", parent=win)
                return

            state["snake"].insert(0, head)
            if head[0] == state["food"][0] and head[1] == state["food"][1]:
                state["score"] += 10
                score_var.set(f"分数：{state['score']}")
                state["food"][0] = random.randrange(0, GRID) * size
                state["food"][1] = random.randrange(0, GRID) * size
            else:
                state["snake"].pop()

            draw()
            state["task_id"] = win.after(110, move)

        def on_key(event):
            if not state["running"]: return
            k = event.keysym
            if k == "Left" and state["dx"] != size: state["dx"], state["dy"] = -size, 0
            elif k == "Right" and state["dx"] != -size: state["dx"], state["dy"] = size, 0
            elif k == "Up" and state["dy"] != size: state["dx"], state["dy"] = 0, -size
            elif k == "Down" and state["dy"] != -size: state["dx"], state["dy"] = 0, size
            elif k == "space": pause_game()

        win.bind("<KeyPress>", on_key)
        win.focus_force()
        win.after(100, lambda: win.focus_force())

        draw()
        move()

    def game_gobang(self):
        win = self.register_window(tk.Toplevel())
        win.title("五子棋")
        win.geometry("520x620")
        win.configure(bg=Theme.BG_MAIN)
        win.resizable(False, False)

        board_size, cell, margin = 15, 30, 40
        canvas_size = cell * (board_size - 1) + margin * 2

        canvas = tk.Canvas(win, bg="#ddb888", width=canvas_size, height=canvas_size, highlightthickness=0)
        canvas.pack(pady=8)

        state = {"board": [[0] * board_size for _ in range(board_size)], "turn": 1, "game_over": False, "win_line": []}
        info_frame = tk.Frame(win, bg=Theme.BG_MAIN)
        info_frame.pack(pady=6)

        tip = tk.StringVar(value="⚫ 黑棋落子")
        tip_label = tk.Label(info_frame, textvariable=tip, font=("微软雅黑", 15, "bold"), bg=Theme.BG_MAIN, fg=Theme.TEXT)
        tip_label.pack()

        def restart():
            state["board"] = [[0] * board_size for _ in range(board_size)]
            state["turn"] = 1
            state["game_over"] = False
            state["win_line"] = []
            tip.set("⚫ 黑棋落子")
            tip_label.config(fg=Theme.TEXT)
            canvas.delete("all")
            draw_board()
            canvas.bind("<Button-1>", click)

        HoverButton(info_frame, "🔄 重新开始", restart, Theme.BTN_DEFAULT).pack(pady=4)

        def draw_board():
            for i in range(board_size):
                pos = margin + i * cell
                canvas.create_line(margin, pos, margin + (board_size - 1) * cell, pos, fill="black")
                canvas.create_line(pos, margin, pos, margin + (board_size - 1) * cell, fill="black")
            for r, c in [(3, 3), (3, 11), (11, 3), (11, 11), (7, 7)]:
                x, y = margin + c * cell, margin + r * cell
                canvas.create_oval(x - 4, y - 4, x + 4, y + 4, fill="black", outline="black")

        draw_board()

        def check_win(row, col, player):
            directions = [(0, 1), (1, 0), (1, 1), (1, -1)]
            for dr, dc in directions:
                line = [(row, col)]
                r, c = row + dr, col + dc
                while (0 <= r < board_size and 0 <= c < board_size and state["board"][r][c] == player):
                    line.append((r, c)); r += dr; c += dc
                r, c = row - dr, col - dc
                while (0 <= r < board_size and 0 <= c < board_size and state["board"][r][c] == player):
                    line.insert(0, (r, c)); r -= dr; c -= dc
                if len(line) >= 5: return line
            return None

        def click(event):
            if state["game_over"]: return
            col = round((event.x - margin) / cell)
            row = round((event.y - margin) / cell)
            if not (0 <= row < board_size and 0 <= col < board_size): return
            cx, cy = margin + col * cell, margin + row * cell
            if abs(event.x - cx) > cell * 0.45 or abs(event.y - cy) > cell * 0.45: return
            if state["board"][row][col] != 0: return

            player = state["turn"]
            state["board"][row][col] = player
            color = "black" if player == 1 else "white"
            radius = cell // 2 - 3
            canvas.create_oval(cx - radius, cy - radius, cx + radius, cy + radius, fill=color, outline="#555", width=1)

            win_line = check_win(row, col, player)
            if win_line:
                state["game_over"] = True
                winner_name = "黑棋" if player == 1 else "白棋"
                tip.set(f"🎉 {winner_name} 五子连珠，获胜！")
                tip_label.config(fg=Theme.GOLD, font=("微软雅黑", 16, "bold"))
                for (r, c) in win_line:
                    hx, hy = margin + c * cell, margin + r * cell
                    canvas.create_oval(hx - radius - 4, hy - radius - 4, hx + radius + 4, hy + radius + 4, outline=Theme.GOLD, width=3)
                center = canvas_size // 2
                canvas.create_text(center, center - 40, text=f"🎉 {winner_name} 获胜！", font=("微软雅黑", 34, "bold"), fill=Theme.GOLD)
                canvas.create_text(center, center + 15, text="点击「重新开始」再战", font=("微软雅黑", 14), fill="#333333")
                win.after(200, lambda: messagebox.showinfo("🎉 游戏结束", f"{winner_name} 五子连珠，获胜！", parent=win))
                return

            state["turn"] = 2 if player == 1 else 1
            tip.set("⚫ 黑棋落子" if state["turn"] == 1 else "⚪ 白棋落子")
            tip_label.config(fg=Theme.TEXT)

        canvas.bind("<Button-1>", click)

    def game_mine(self):
        win = self.register_window(tk.Toplevel())
        win.title("扫雷")
        win.geometry("380x460")
        win.configure(bg=Theme.BG_MAIN)

        rows, cols, mines = 9, 9, 10
        board = [[0] * cols for _ in range(rows)]
        revealed = [[False] * cols for _ in range(rows)]
        flagged = [[False] * cols for _ in range(rows)]
        game_over = [False]

        placed = 0
        while placed < mines:
            r, c = random.randint(0, rows - 1), random.randint(0, cols - 1)
            if board[r][c] != -1:
                board[r][c] = -1
                placed += 1

        for r in range(rows):
            for c in range(cols):
                if board[r][c] == -1: continue
                count = 0
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        nr, nc = r + dr, c + dc
                        if (0 <= nr < rows and 0 <= nc < cols and board[nr][nc] == -1): count += 1
                board[r][c] = count

        info = tk.Frame(win, bg=Theme.BG_MAIN)
        info.pack(pady=10)
        status_var = tk.StringVar(value="🙂")
        tk.Label(info, textvariable=status_var, font=("Segoe UI Emoji", 24), bg=Theme.BG_MAIN).pack(side=tk.LEFT, padx=10)

        def restart():
            game_over[0] = False
            status_var.set("🙂")
            for r in range(rows):
                for c in range(cols):
                    revealed[r][c] = False
                    flagged[r][c] = False
            nonlocal board
            board = [[0] * cols for _ in range(rows)]
            placed = 0
            while placed < mines:
                r, c = random.randint(0, rows - 1), random.randint(0, cols - 1)
                if board[r][c] != -1:
                    board[r][c] = -1
                    placed += 1
            for r in range(rows):
                for c in range(cols):
                    if board[r][c] == -1: continue
                    count = 0
                    for dr in (-1, 0, 1):
                        for dc in (-1, 0, 1):
                            nr, nc = r + dr, c + dc
                            if (0 <= nr < rows and 0 <= nc < cols and board[nr][nc] == -1): count += 1
                    board[r][c] = count
            draw_board()

        HoverButton(info, "🔄", restart, Theme.BTN_DEFAULT, width=3).pack(side=tk.LEFT, padx=10)

        canvas = tk.Canvas(win, bg="#c0c0c0", width=270, height=270, highlightthickness=0)
        canvas.pack(pady=10)

        def draw_board():
            if not canvas.winfo_exists(): return
            canvas.delete("all")
            cell_size = 30
            for r in range(rows):
                for c in range(cols):
                    x, y = c * cell_size, r * cell_size
                    tag = f"cell_{r}_{c}"
                    if game_over[0] and board[r][c] == -1:
                        canvas.create_rectangle(x, y, x + cell_size, y + cell_size, fill="#e74c3c", outline="#999", tags=tag)
                        canvas.create_text(x + 15, y + 15, text="💣", font=("Segoe UI Emoji", 12), tags=tag)
                    elif flagged[r][c]:
                        canvas.create_rectangle(x, y, x + cell_size, y + cell_size, fill="#f39c12", outline="#999", tags=tag)
                        canvas.create_text(x + 15, y + 15, text="🚩", font=("Segoe UI Emoji", 12), tags=tag)
                    elif revealed[r][c]:
                        canvas.create_rectangle(x, y, x + cell_size, y + cell_size, fill="#ecf0f1", outline="#999", tags=tag)
                        if board[r][c] > 0:
                            colors = ['', '#3498db', '#27ae60', '#e74c3c', '#8e44ad', '#d35400', '#16a085', '#2c3e50', '#7f8c8d']
                            canvas.create_text(x + 15, y + 15, text=str(board[r][c]), fill=colors[board[r][c]], font=("Consolas", 13, "bold"), tags=tag)
                    else:
                        canvas.create_rectangle(x, y, x + cell_size, y + cell_size, fill="#bdc3c7", outline="#95a5a6", tags=tag)

                    if not revealed[r][c] and not flagged[r][c] and not game_over[0]:
                        canvas.tag_bind(tag, "<Button-1>", lambda e, rr=r, cc=c: reveal(rr, cc))
                        canvas.tag_bind(tag, "<Button-3>", lambda e, rr=r, cc=c: flag(rr, cc))

        def _reveal(r, c):
            if (r < 0 or r >= rows or c < 0 or c >= cols or revealed[r][c] or flagged[r][c] or board[r][c] == -1): return
            revealed[r][c] = True
            if board[r][c] == 0:
                for dr in (-1, 0, 1):
                    for dc in (-1, 0, 1):
                        _reveal(r + dr, c + dc)

        def reveal(r, c):
            if game_over[0] or flagged[r][c]: return
            if board[r][c] == -1:
                game_over[0] = True
                status_var.set("😵")
                draw_board()
                messagebox.showerror("游戏结束", "踩到地雷了！", parent=win)
                return
            _reveal(r, c)
            draw_board()
            if sum(1 for rr in range(rows) for cc in range(cols) if not revealed[rr][cc] and board[rr][cc] != -1) == 0:
                game_over[0] = True
                status_var.set("😎")
                messagebox.showinfo("恭喜", "你赢了！", parent=win)

        def flag(r, c):
            if game_over[0] or revealed[r][c]: return
            flagged[r][c] = not flagged[r][c]
            draw_board()

        draw_board()


# ====================== 入口 ======================
if __name__ == "__main__":
    root = tk.Tk()
    app = MiniOSGUI(root)
    root.mainloop()