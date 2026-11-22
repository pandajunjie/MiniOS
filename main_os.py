"""
MiniOS Lite v2.1 - 完整核心主系统
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
from tkinter import ttk, messagebox, simpledialog, colorchooser
from tkinter import font as tkfont

# ====================== 配色 ======================
# 配色表和悬停按钮已抽到 minios_ui.py，两处共用一套
from minios_ui import Theme, HoverButton
from apps_basic import AppMixin
SYS_NAME = "MiniOS Lite v2.1"

# 所有数据都存放于程序所在目录，跟启动位置（当前工作目录）无关。
# 这样双击、快捷方式、命令行启动都指向同一份数据，也方便整体搬迁。
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DISK_PATH = os.path.join(BASE_DIR, "mini_system_disk")
USER_DB_PATH = os.path.join(BASE_DIR, "userdata.txt")
SETTINGS_PATH = os.path.join(BASE_DIR, "settings.json")

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
class MiniOSGUI(AppMixin):
    def __init__(self, root):
        self.root = root
        # 应用方法里通过 self 取这些常量，方便以后改路径
        self.DISK_PATH = DISK_PATH
        self.SYS_NAME = SYS_NAME
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
        self._win_btns = {}      # 任务栏窗口条目：{窗口: 按钮}
        self._power_menu = None  # 开始菜单的电源二级菜单
        self._locked = False     # 是否处于锁屏
        self._lock_frame = None  # 锁屏覆盖层（嵌在桌面里的 Frame）
        self._lock_hidden = []   # 锁屏时被隐藏的窗口，解锁后恢复

        self.root.withdraw()
        
        # ✅ 将自身挂载，供 App Store 调用
        self.root.app_instance = self
        
        # ✅ 实例化 App Store (确保 app_store.py 在同级目录)
        AppStore = None
        try:
            from app_store import AppStore
        except ImportError:
            print("警告：未找到 app_store.py，App Store 功能不可用！")
        if AppStore is None:
            self.app_store = None
        else:
            try:
                self.app_store = AppStore(self.root, self)
            except Exception as e:
                self.app_store = None
                print(f"警告：App Store 初始化失败：{e}")

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
        try:
            self._taskbar_register(win)
        except Exception:
            pass
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
        self.root.after(1500, self._update_boot_notice)
        
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

        # ---------- 右侧托盘：先占位，窗口条目再多也挤不走 ----------
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
                 fg=Theme.TEXT_DIM, font=("微软雅黑", 9)).pack(side=tk.RIGHT, padx=8)

        # 锁屏按钮（固定在托盘里，不参与左侧排布）
        self.lock_btn = tk.Label(tray, text="🔒", font=("Segoe UI Emoji", 12),
                                 bg=Theme.TASKBAR, fg=Theme.TEXT,
                                 cursor="hand2", padx=6)
        self.lock_btn.pack(side=tk.RIGHT, padx=(2, 4))
        self.lock_btn.bind("<Button-1>", lambda e: self.lock_screen())
        self.lock_btn.bind("<Enter>",
                           lambda e: self.lock_btn.config(bg=Theme.TASKBAR_HOVER))
        self.lock_btn.bind("<Leave>",
                           lambda e: self.lock_btn.config(bg=Theme.TASKBAR))

        # 重启已移入开始菜单的电源菜单，托盘不再占位

        # ---------- 左侧：开始 + 快捷图标 + 窗口条目 ----------
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

        # 运行中的窗口条目区：弹性填满中间剩余空间，右侧托盘已经先占位
        self.win_bar = tk.Frame(self.taskbar, bg=Theme.TASKBAR)
        self.win_bar.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(0, 4))
        self.win_bar.bind("<Configure>",
                          lambda e: self._taskbar_relayout())

    # ====================== 任务栏窗口条目 ======================
    WINBAR_MAX_WIDTH = 520    # 条目区定宽，防止把右侧托盘挤出去

    @staticmethod
    def _is_icon_char(ch):
        """判断是不是 emoji 图标字符（汉字码位也很大，不能只看大小）"""
        o = ord(ch)
        return ((0x1F000 <= o <= 0x1FAFF)
                or (0x2600 <= o <= 0x27BF)
                or (0x2B00 <= o <= 0x2BFF))

    def _split_title(self, title):
        """把「📝 记事本」这类标题拆成图标和名字"""
        t = (title or "").strip()
        if t and self._is_icon_char(t[0]):
            rest = t[1:].lstrip("\ufe0f\u200d").strip()
            return t[0], rest
        return "▣", t

    def _taskbar_register(self, win):
        """窗口注册时顺手在任务栏长一个条目"""
        bar = getattr(self, "win_bar", None)
        if bar is None or win in self._win_btns:
            return
        try:
            if not bar.winfo_exists():
                return
        except Exception:
            return

        icon, name = self._split_title(win.title())
        if len(name) > 8:
            name = name[:8] + "…"
        btn = tk.Button(bar, text=f"{icon} {name}",
                        font=("微软雅黑", 9),
                        bg=Theme.TASKBAR_HOVER, fg=Theme.TEXT,
                        activebackground=Theme.BG_HOVER,
                        activeforeground=Theme.TEXT,
                        relief=tk.FLAT, bd=0, cursor="hand2",
                        padx=8, pady=2)
        btn.pack_forget()
        btn.place(x=0, y=9, width=100, height=30)
        btn.bind("<Button-1>", lambda e, w=win: self._taskbar_toggle(w))
        self._win_btns[win] = btn
        self._taskbar_relayout()
        # register_window 通常比 win.title() 早执行，标题这时还是窗口默认值，
        # 所以稍后补一次，把真正的标题读回来
        for delay in (60, 500):
            try:
                win.after(delay, lambda w=win: self._taskbar_sync_label(w))
            except Exception:
                pass
        # Destroy 会向所有子控件冒泡，必须确认是窗口本身
        win.bind("<Destroy>",
                 lambda e, w=win: self._taskbar_unregister(w)
                 if e.widget is w else None, add="+")

    def _taskbar_sync_label(self, win):
        """把窗口当前标题同步到任务栏条目上"""
        btn = self._win_btns.get(win)
        if btn is None:
            return
        try:
            if not win.winfo_exists() or not btn.winfo_exists():
                return
            icon, name = self._split_title(win.title())
            if not name or name == SYS_NAME:
                name = "窗口"
            if len(name) > 8:
                name = name[:8] + "…"
            btn.config(text=f"{icon} {name}")
        except Exception:
            pass

    def _taskbar_relayout(self):
        """按条目数量均分宽度：少了宽一点，多了自动缩窄"""
        bar = getattr(self, "win_bar", None)
        if bar is None:
            return
        try:
            if not bar.winfo_exists():
                return
        except Exception:
            return
        btns = [b for b in self._win_btns.values()]
        if not btns:
            return
        n = len(btns)
        # 用条目区实际可用宽度来排；布局还没算出来时用上限兜底
        try:
            maxw = bar.winfo_width()
        except Exception:
            maxw = 0
        if maxw <= 1:
            maxw = self.WINBAR_MAX_WIDTH
        w = max(48, min(112, maxw // n))
        capacity = max(1, maxw // w)
        # 条目放不下时优先保留最近打开的窗口
        shown = btns[-capacity:]
        hidden = btns[:-capacity] if n > capacity else []
        for b in hidden:
            try:
                b.place_forget()
            except Exception:
                pass
        for i, b in enumerate(shown):
            try:
                if not b.winfo_exists():
                    continue
                b.place(x=i * w + 2, y=9, width=w - 4, height=30)
            except Exception:
                pass

    def _taskbar_unregister(self, win):
        btn = self._win_btns.pop(win, None)
        if btn is not None:
            try:
                btn.destroy()
            except Exception:
                pass
        self._taskbar_relayout()

    def _taskbar_toggle(self, win):
        """点条目：隐藏着的叫回来，显示着的收起来"""
        btn = self._win_btns.get(win)
        try:
            if not win.winfo_exists():
                self._taskbar_unregister(win)
                return
            if win.state() == "withdrawn":
                win.deiconify()
                try:
                    win.lift()
                except Exception:
                    pass
                if btn is not None:
                    btn.config(bg=Theme.TASKBAR_HOVER)
            else:
                win.withdraw()
                if btn is not None:
                    btn.config(bg=Theme.BG_PANEL)
        except Exception:
            self._taskbar_unregister(win)

    # ====================== 锁屏 ======================
    def lock_screen(self):
        """锁屏：收起所有窗口，盖一层全屏解锁界面"""
        if getattr(self, "_locked", False):
            return
        self._locked = True
        self._lock_hidden = []
        for w in list(self._open_windows):
            try:
                if w.winfo_exists() and w.state() != "withdrawn":
                    w.withdraw()
                    self._lock_hidden.append(w)
            except Exception:
                pass

        # 锁屏层直接嵌在 MiniOS 桌面里，不是独立窗口：
        # 独立窗口能拖到旁边、能跟着主窗口最小化跑掉，等于没锁
        lock = tk.Frame(self.bg, bg=Theme.BG_MAIN)
        lock.place(x=0, y=0, relwidth=1, relheight=1)
        try:
            lock.lift()
        except Exception:
            pass
        self._lock_frame = lock

        center = tk.Frame(lock, bg=Theme.BG_MAIN)
        center.place(relx=0.5, rely=0.45, anchor="center")

        clock = tk.Label(center, text="", font=("Segoe UI", 54, "bold"),
                         bg=Theme.BG_MAIN, fg=Theme.TEXT)
        clock.pack()
        date_lbl = tk.Label(center, text="", font=("微软雅黑", 13),
                            bg=Theme.BG_MAIN, fg=Theme.TEXT_DIM)
        date_lbl.pack(pady=(0, 26))

        tk.Label(center, text=f"🔒 已锁定　　用户：{self.login_user or '未知'}",
                 font=("微软雅黑", 12), bg=Theme.BG_MAIN,
                 fg=Theme.ACCENT).pack(pady=(0, 12))

        pwd_frame = tk.Frame(center, bg=Theme.BG_MAIN)
        pwd_frame.pack()
        pwd_in = tk.Entry(pwd_frame, show="*", font=("微软雅黑", 13),
                          width=18, bg=Theme.BG_CARD, fg=Theme.TEXT,
                          insertbackground=Theme.ACCENT,
                          relief=tk.FLAT, bd=0)
        pwd_in.pack(side=tk.LEFT, ipady=6, padx=(0, 8))
        unlock_btn = tk.Button(pwd_frame, text="解锁",
                               font=("微软雅黑", 11, "bold"),
                               bg=Theme.BTN_PRIMARY, fg="#ffffff",
                               activebackground=Theme.BG_HOVER,
                               activeforeground=Theme.TEXT,
                               relief=tk.FLAT, bd=0, cursor="hand2",
                               padx=16, pady=4)
        unlock_btn.pack(side=tk.LEFT)

        tip = tk.Label(center, text="输入登录密码后按回车", font=("微软雅黑", 9),
                       bg=Theme.BG_MAIN, fg=Theme.TEXT_DIM)
        tip.pack(pady=(10, 0))

        week_cn = "一二三四五六日"

        def tick():
            try:
                if not lock.winfo_exists():
                    return
                now = datetime.datetime.now()
                clock.config(text=now.strftime("%H:%M"))
                date_lbl.config(
                    text=f"{now.year}年{now.month:02d}月{now.day:02d}日  "
                         f"星期{week_cn[now.weekday()]}")
                lock.after(1000, tick)
            except Exception:
                pass

        def do_unlock():
            self._locked = False
            try:
                lock.place_forget()
                lock.destroy()
            except Exception:
                pass
            self._lock_frame = None
            for w in self._lock_hidden:
                try:
                    if w.winfo_exists():
                        w.deiconify()
                except Exception:
                    pass
            self._lock_hidden = []
            try:
                self.toast("🔓 已解锁")
            except Exception:
                pass

        def unlock(event=None):
            pwd = pwd_in.get().strip()
            users = self.load_users()
            ok = False
            if self.login_user and users.get(self.login_user) == pwd:
                ok = True
            elif not self.login_user:
                for u, p in users.items():
                    if p == pwd:
                        self.login_user = u
                        ok = True
                        break
            if ok:
                do_unlock()
            else:
                tip.config(text="✗ 密码错误，请重试", fg=Theme.ACCENT2)
                pwd_in.delete(0, "end")
                pwd_in.focus_set()

        pwd_in.bind("<Return>", unlock)
        unlock_btn.config(command=unlock)
        tick()
        try:
            lock.update_idletasks()
            pwd_in.focus_force()
        except Exception:
            pass

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

        self.power_btn = tk.Button(
            bottom_frame, text="⏻ 电源", command=self._popup_power_menu,
            font=("微软雅黑", 10, "bold"), bg=Theme.START_BG, fg=Theme.BTN_DANGER,
            activebackground=Theme.BG_HOVER, relief=tk.FLAT, cursor="hand2", bd=0, padx=15
        )
        self.power_btn.pack(side=tk.RIGHT, pady=6)
        self.power_btn.bind("<Enter>", lambda e: self.power_btn.config(bg=Theme.BG_HOVER))
        self.power_btn.bind("<Leave>", lambda e: self.power_btn.config(bg=Theme.START_BG))

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

    # ====================== 电源二级菜单 ======================
    def _popup_power_menu(self):
        """点「电源」后向上弹出一小条：关机 / 锁屏 / 重启；再点一次收起"""
        if getattr(self, "_power_menu", None) is not None:
            self._close_power_menu()
            return

        w, row_h, pad = 176, 44, 6
        h = row_h * 3 + pad * 2
        try:
            ax = self.power_btn.winfo_rootx() + self.power_btn.winfo_width() - w
            ay = self.power_btn.winfo_rooty() - h - 4
        except Exception:
            ax = self.root.winfo_x() + 100
            ay = self.root.winfo_y() + self.root.winfo_height() - 220

        m = tk.Toplevel(self.root)
        m.overrideredirect(True)
        m.configure(bg=Theme.BG_CARD)
        m.geometry(f"{w}x{h}+{max(0, ax)}+{max(0, ay)}")
        try:
            m.attributes("-topmost", True)
        except Exception:
            pass
        self._power_menu = m

        items = [
            ("⏻", "关机", Theme.BTN_DANGER, self.shutdown),
            ("🔒", "锁屏", Theme.ACCENT, self.lock_screen),
            ("🔄", "重启", Theme.BTN_WARNING, self.system_restart),
        ]
        for icon, name, color, cmd in items:
            row = tk.Button(m, text=f"{icon}   {name}", anchor="w",
                            font=("微软雅黑", 10, "bold"),
                            bg=Theme.BG_CARD, fg=color,
                            activebackground=Theme.BG_HOVER,
                            activeforeground=Theme.TEXT,
                            relief=tk.FLAT, bd=0, cursor="hand2",
                            padx=14, pady=6,
                            command=lambda c=cmd: self._run_power(c))
            row.pack(fill=tk.X, padx=pad, pady=3)
            row.bind("<Enter>", lambda e, b=row: b.config(bg=Theme.BG_HOVER))
            row.bind("<Leave>", lambda e, b=row: b.config(bg=Theme.BG_CARD))

        def arm():
            # 等窗口真正拿到焦点再挂 FocusOut，否则会立刻自我关闭
            try:
                if m.winfo_exists():
                    m.focus_force()
                    m.bind("<FocusOut>", lambda e: self._close_power_menu())
                    m.bind("<Escape>", lambda e: self._close_power_menu())
            except Exception:
                pass

        m.after(80, arm)

    def _run_power(self, cmd):
        self._close_power_menu()
        self.hide_start_menu()
        self.root.after(120, cmd)

    def _close_power_menu(self):
        m = getattr(self, "_power_menu", None)
        self._power_menu = None
        if m is not None:
            try:
                if m.winfo_exists():
                    m.destroy()
            except Exception:
                pass

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
            # 电源二级菜单也是从开始菜单里开出来的，别把它一起收掉
            if getattr(self, "_power_menu", None) is not None:
                return
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
        self._close_power_menu()
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
                 justify="left").pack(anchor="w", padx=12, pady=(4, 4))

        HoverButton(g5, "🔄 检查系统更新", self.system_update, Theme.BTN_PRIMARY,
                    width=14).pack(anchor="w", padx=12, pady=(0, 8))

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

    # ====================== 系统更新 ======================
    def system_update(self):
        """打开系统更新窗口（从 GitHub 拉取新版本）"""
        try:
            from updater import open_updater
            open_updater(self)
        except Exception as e:
            messagebox.showerror("更新模块不可用",
                                 f"无法加载 updater 模块：\n{e}\n"
                                 "请确认 updater.py 与 main_os.py 在同一目录。")

    def _update_boot_notice(self):
        """启动后检查上次更新结果，有就弹一条 Toast"""
        try:
            from updater import boot_notice
            boot_notice(self)
        except Exception:
            pass



# ====================== 入口 ======================
if __name__ == "__main__":
    root = tk.Tk()
    app = MiniOSGUI(root)
    root.mainloop()
