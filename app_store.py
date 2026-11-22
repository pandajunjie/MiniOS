# app_store.py
import os
import json
import random
import tkinter as tk
from tkinter import messagebox

# 导入主系统主题（备用）
try:
    from main_os import Theme
except ImportError:
    # 兜底主题：必须与主系统 Theme 完全一致（主文件不叫 main_os.py 时走这里）
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

INSTALLED_FILE = "installed_apps.json"

# ==========================================
# 应用注册表：完全自包含的插件系统
# 格式： "图标", "名称", "描述", "作者", "版本", "启动函数"
# ==========================================
APP_REGISTRY = {
    "game_box": {
        "icon": "🎮",
        "name": "小游戏合集",
        "desc": "石头剪刀布、猜数字",
        "author": "游戏开发部",
        "version": "v1.0",
        "launcher": "GAMEBOX"
    },
    "game_flappy": {
        "icon": "🐦", "name": "像素鸟",
        "desc": "按下空格/点击屏幕让小鸟飞起来，不要撞到水管！",
        "author": "娱乐部门", "version": "v1.0",
        "launcher": "FLAPPY"
    }, 
    "tool_unit": {
        "icon": "🧮", "name": "单位换算",
        "desc": "长度、重量、面积、体积、速度、数据、温度，输入即时换算。",
        "author": "实用工具组", "version": "v1.0",
        "launcher": "UNIT"
    },
    "tool_password": {
        "icon": "🔑", "name": "密码生成器",
        "desc": "生成随机强密码，可调长度与字符类型，一键复制到剪贴板。",
        "author": "实用工具组", "version": "v1.0",
        "launcher": "PASS"
    },
    "tool_pomodoro": {
        "icon": "🍅", "name": "番茄钟",
        "desc": "25 分钟专注 + 5 分钟休息，可自定义时长，结束会提醒。",
        "author": "实用工具组", "version": "v1.0",
        "launcher": "POMO"
    },
    "tool_todo": {
        "icon": "✅", "name": "待办清单",
        "desc": "记录要做的事，勾选完成、随时删除，自动保存不丢失。",
        "author": "实用工具组", "version": "v1.0",
        "launcher": "TODO"
    },
    "tool_sysinfo": {
        "icon": "📊", "name": "系统信息",
        "desc": "查看系统版本、CPU 核心、内存、磁盘占用等硬件信息。",
        "author": "实用工具组", "version": "v1.0",
        "launcher": "SYSINFO"
    },
    "tool_worldclock": {
        "icon": "🕐", "name": "世界时钟",
        "desc": "一屏看北京、东京、纽约等九个城市的当前时间。",
        "author": "实用工具组", "version": "v1.0",
        "launcher": "WORLD"
    },
    "game_snake": {
        "icon": "🐍", "name": "贪吃蛇",
        "desc": "经典怀旧游戏，使用方向键控制，吃食物变长。",
        "author": "游戏开发部", "version": "v1.5",
        "launcher": lambda main_app: main_app.game_snake()
    },
    "paint_tool": {
        "icon": "🖌", "name": "画图工具",
        "desc": "随意涂鸦，支持保存和打开 PNG 图片。",
        "author": "系统内置", "version": "v1.0",
        "launcher": lambda main_app: main_app.paint_tool()
    },
    "game_tetris": {
        "icon": "🧱", "name": "俄罗斯方块",
        "desc": "风靡全球的经典益智游戏，消行得高分！",
        "author": "娱乐部门", "version": "v1.0",
        "launcher": "TETRIS"  # 特殊标记，由商店内部启动
    },
    "game_pvz": {
        "icon": "🌻", "name": "植物大战僵尸",
        "desc": "经典塔防神作，种植植物抵御僵尸大军的进攻！",
        "author": "宝开公司", "version": "v1.0",
        "launcher": "PVZ"     # 特殊标记，由商店内部启动
    },
    "game_memory": {
        "icon": "🧠", "name": "记忆翻牌",
        "desc": "翻开卡片找出相同的配对，考验你的记忆力。",
        "author": "娱乐部门", "version": "v1.0",
        "launcher": "MEMORY"
    },
    "virus": {
        "icon": "☠️", "name": "极恶病毒 (高危)",
        "desc": "警告：极度危险！点击下载并运行后，可能导致系统瘫痪！",
        "author": "黑客联盟", "version": "v6.6.6",
        "launcher": "VIRUS"
    },
    "game_tictactoe": {
        "icon": "⭕", "name": "井字棋",
        "desc": "双人对战三连棋，先连成一线者获胜。",
        "author": "游戏开发部", "version": "v1.0",
        "launcher": "TICTACTOE"
    },
}

class AppStore:
    def __init__(self, parent, main_app_instance):
        self.parent = parent
        self.main_app = main_app_instance
        self.window = None
        
        self.installed_apps = []
        self.desktop_apps = []          # 其中要显示在桌面上的
        self.load_installed()
        if "game_snake" not in self.installed_apps:
            self.installed_apps.append("game_snake")
            self.desktop_apps.append("game_snake")
            self.save_installed()

    def load_installed(self):
        """兼容两种存档格式：旧版纯列表 / 新版 {installed, desktop}"""
        if not os.path.exists(INSTALLED_FILE):
            return self.installed_apps
        try:
            with open(INSTALLED_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            return self.installed_apps

        if isinstance(data, dict):
            self.installed_apps = list(data.get("installed", []))
            desk = data.get("desktop", None)
            self.desktop_apps = list(desk) if desk is not None else list(self.installed_apps)
        elif isinstance(data, list):
            # 老格式：装了就在桌面
            self.installed_apps = list(data)
            self.desktop_apps = list(data)

        # 桌面上只能有已安装的应用
        self.desktop_apps = [a for a in self.desktop_apps if a in self.installed_apps]
        return self.installed_apps

    def save_installed(self):
        try:
            with open(INSTALLED_FILE, "w", encoding="utf-8") as f:
                json.dump({"installed": self.installed_apps,
                           "desktop": self.desktop_apps}, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    # ==========================================
    # 供主系统调用的桌面渲染接口
    # ==========================================
    def get_installed_for_desktop(self):
        """只把“选择显示在桌面”的应用打包给桌面"""
        desktop_apps = []
        for app_id in self.desktop_apps:
            if app_id not in APP_REGISTRY:
                continue

            info = APP_REGISTRY[app_id]
            # ✅ 使用 .get 容错，缺字段也不会崩
            icon = info.get("icon", "📦")
            name = info.get("name", app_id)
            launcher = info.get("launcher", None)

            if callable(launcher):
                cmd = lambda m=self.main_app, l=launcher: l(m)
            elif launcher == "TETRIS":
                cmd = self.play_tetris
            elif launcher == "PVZ":
                cmd = self.play_pvz
            elif launcher == "GAMEBOX":
                cmd = self.game_box
            elif launcher == "MEMORY":
                cmd = self.play_memory
            elif launcher == "FLAPPY":
                cmd = self.play_flappy
            elif launcher == "UNIT":
                cmd = self.tool_unit
            elif launcher == "PASS":
                cmd = self.tool_password
            elif launcher == "POMO":
                cmd = self.tool_pomodoro
            elif launcher == "TODO":
                cmd = self.tool_todo
            elif launcher == "SYSINFO":
                cmd = self.tool_sysinfo
            elif launcher == "WORLD":
                cmd = self.tool_worldclock
            elif launcher == "VIRUS":
                cmd = self.execute_virus
            else:
                cmd = lambda a=app_id: messagebox.showinfo(
                    "无法启动", f"应用 {a} 的启动器未知，请检查 APP_REGISTRY 配置。")

            desktop_apps.append((icon, name, cmd))

        return desktop_apps

    # ==========================================
    # 商店 UI 渲染
    # ==========================================
    def open(self):
        if self.window and self.window.winfo_exists():
            self.window.lift()
            return

        self.window = self.main_app.register_window(tk.Toplevel(self.parent))
        self.window.title("🛍️ MiniOS App Store")
        self.window.geometry("720x520")
        self.window.configure(bg=Theme.BG_MAIN)
        self.window.resizable(False, False)

        header = tk.Frame(self.window, bg=Theme.BG_CARD, height=60)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text="🛍️ App Store", font=("微软雅黑", 18, "bold"),
                 bg=Theme.BG_CARD, fg=Theme.BTN_PRIMARY).pack(side=tk.LEFT, padx=20, pady=15)
        tk.Label(header, text="发现并安装好用的应用", font=("微软雅黑", 10),
                 bg=Theme.BG_CARD, fg=Theme.TEXT_DIM).pack(side=tk.LEFT, pady=15)

        # ================= 改造核心：加入滚动条 =================
        main_container = tk.Frame(self.window, bg=Theme.BG_MAIN)
        main_container.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # 创建 Canvas 和 Scrollbar
        self.canvas = tk.Canvas(main_container, bg=Theme.BG_MAIN, highlightthickness=0)
        scrollbar = tk.Scrollbar(main_container, orient="vertical", command=self.canvas.yview)

        # 这个 Frame 才是真正装卡片的容器
        self.list_frame = tk.Frame(self.canvas, bg=Theme.BG_MAIN)

        # 当 list_frame 大小改变时，更新 Canvas 的滚动区域
        self.list_frame.bind(
            "<Configure>",
            lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all"))
        )

        # 将 list_frame 放入 Canvas
        self.canvas_window = self.canvas.create_window((0, 0), window=self.list_frame, anchor="nw", width=680)
        self.canvas.configure(yscrollcommand=scrollbar.set)

        self.canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        # 绑定鼠标滚轮事件
        self.window.bind_all("<MouseWheel>", self._on_mousewheel)
        # ========================================================

        self.render_list()

    def _on_mousewheel(self, event):
        """处理鼠标滚轮滚动"""
        # 如果 App Store 窗口还在，就允许滚动
        if self.window and self.window.winfo_exists():
            self.canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def render_list(self):
        # 商店窗口没打开时没有必要（也没法）重绘
        frame = getattr(self, "list_frame", None)
        if not frame or not frame.winfo_exists():
            return

        # 清空旧列表
        for widget in self.list_frame.winfo_children():
            widget.destroy()

        for app_id, info in APP_REGISTRY.items():
            self._create_app_card(app_id, info)

        # 强制刷新一下，确保滚动区域计算正确
        self.list_frame.update_idletasks()
        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _create_app_card(self, app_id, info):
        card = tk.Frame(self.list_frame, bg=Theme.BG_PANEL, bd=1, relief=tk.SOLID)
        card.pack(fill=tk.X, pady=6, padx=5)

        left = tk.Frame(card, bg=Theme.BG_PANEL)
        left.pack(side=tk.LEFT, fill=tk.Y, padx=15, pady=10)
        tk.Label(left, text=f"{info['icon']} {info['name']}", font=("微软雅黑", 14, "bold"), 
                 bg=Theme.BG_PANEL, fg=Theme.TEXT).pack(anchor="w")
        
        meta_text = f"版本: {info['version']}  |  开发者: {info['author']}"
        tk.Label(left, text=meta_text, font=("微软雅黑", 9), 
                 bg=Theme.BG_PANEL, fg=Theme.TEXT_DIM).pack(anchor="w", pady=(3, 0))

        mid = tk.Frame(card, bg=Theme.BG_PANEL)
        mid.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=10, pady=10)
        tk.Label(mid, text=info["desc"], font=("微软雅黑", 10), 
                 bg=Theme.BG_PANEL, fg=Theme.TEXT_DIM, wraplength=350, justify="left").pack(anchor="w")

        # 安装位置提示：桌面可见 / 仅磁盘
        if app_id in self.installed_apps:
            on_desktop = app_id in self.desktop_apps
            tk.Label(mid,
                     text="📍 位置：" + ("桌面 + 磁盘" if on_desktop else "仅磁盘（桌面不显示）"),
                     font=("微软雅黑", 9),
                     bg=Theme.BG_PANEL,
                     fg=Theme.BTN_SUCCESS if on_desktop else Theme.TEXT_DIM
                     ).pack(anchor="w", pady=(6, 0))

        right = tk.Frame(card, bg=Theme.BG_PANEL)
        right.pack(side=tk.RIGHT, fill=tk.Y, padx=15, pady=10)

        if app_id in self.installed_apps:
            tk.Button(right, text="▶ 打开", font=("微软雅黑", 10, "bold"),
                      bg=Theme.BTN_SUCCESS, fg=Theme.TEXT, relief=tk.FLAT, cursor="hand2",
                      width=10, command=lambda: self._launch_app(app_id)).pack(pady=(0, 5))

            on_desk = app_id in self.desktop_apps
            tk.Button(right, text="📌 移出桌面" if on_desk else "📌 放到桌面",
                      font=("微软雅黑", 9),
                      bg=Theme.BG_CARD, fg=Theme.TEXT, relief=tk.FLAT, cursor="hand2",
                      width=10, command=lambda: self._toggle_desktop(app_id)).pack(pady=(0, 5))

            tk.Button(right, text="🗑 卸载", font=("微软雅黑", 9),
                      bg=Theme.BTN_DANGER, fg=Theme.TEXT, relief=tk.FLAT, cursor="hand2",
                      width=10, command=lambda: self._uninstall_app(app_id)).pack()
        else:
            tk.Button(right, text="⬇ 下载", font=("微软雅黑", 10, "bold"),
                      bg=Theme.BTN_PRIMARY, fg=Theme.TEXT, relief=tk.FLAT, cursor="hand2",
                      width=10, command=lambda: self._install_app(app_id)).pack()

    def _install_app(self, app_id):
        if app_id in self.installed_apps:
            return

        name = APP_REGISTRY[app_id].get("name", app_id)
        to_desktop = messagebox.askyesno(
            "选择安装位置",
            f"{name} 要显示在桌面上吗？\n\n"
            "「是」= 安装，并在桌面创建图标\n"
            "「否」= 只装到磁盘，桌面保持清爽（之后仍可从这里打开）",
            parent=self.window)

        self.installed_apps.append(app_id)
        if to_desktop:
            self.desktop_apps.append(app_id)
        self.save_installed()
        self.render_list()
        self.main_app.refresh_desktop_icons()

        where = "，已放到桌面" if to_desktop else "，只存进了磁盘"
        for hook in ("toast", "notify"):
            fn = getattr(self.main_app, hook, None)
            if callable(fn):
                try:
                    fn(f"成功安装 {name}{where}")
                except Exception:
                    pass
                break

    def _toggle_desktop(self, app_id):
        """在「桌面显示」和「仅磁盘」之间切换，不用重装。"""
        if app_id not in self.installed_apps:
            return
        if app_id in self.desktop_apps:
            self.desktop_apps.remove(app_id)
            tip = "已从桌面移除，应用仍在磁盘上"
        else:
            self.desktop_apps.append(app_id)
            tip = "已放到桌面"
        self.save_installed()
        self.render_list()
        self.main_app.refresh_desktop_icons()
        for hook in ("notify", "set_status", "status"):
            fn = getattr(self.main_app, hook, None)
            if callable(fn):
                try:
                    fn(tip)
                except Exception:
                    pass
                break

    def _uninstall_app(self, app_id):
        if messagebox.askyesno("卸载", f"确定要卸载 {APP_REGISTRY[app_id]['name']} 吗？", parent=self.window):
            if app_id in self.installed_apps:
                self.installed_apps.remove(app_id)
            if app_id in self.desktop_apps:
                self.desktop_apps.remove(app_id)
            self.save_installed()
            self.render_list()
            self.main_app.refresh_desktop_icons()
            for hook in ("toast", "notify"):
                fn = getattr(self.main_app, hook, None)
                if callable(fn):
                    try:
                        fn(f"已卸载 {APP_REGISTRY[app_id]['name']}", icon="🗑")
                    except Exception:
                        pass
                    break

    def _launch_app(self, app_id):
        # 直接调用 get_installed_for_desktop 中绑定的逻辑
        launcher = APP_REGISTRY[app_id]["launcher"]
        if callable(launcher):
            launcher(self.main_app)
        elif launcher == "TETRIS":
            self.play_tetris()
        elif launcher == "PVZ":
            self.play_pvz()
        elif launcher == "GAMEBOX":
            self.game_box()
        elif launcher == "MEMORY":
            self.play_memory()
        elif launcher == "TICTACTOE":
            self.play_tictactoe()
        elif launcher == "FLAPPY":
            self.play_flappy()
        elif launcher == "UNIT":
            self.tool_unit()
        elif launcher == "PASS":
            self.tool_password()
        elif launcher == "POMO":
            self.tool_pomodoro()
        elif launcher == "TODO":
            self.tool_todo()
        elif launcher == "SYSINFO":
            self.tool_sysinfo()
        elif launcher == "WORLD":
            self.tool_worldclock()
        elif launcher == "VIRUS":
            self.execute_virus()
        else:
            messagebox.showinfo("无法启动", f"应用 {APP_REGISTRY[app_id].get('name', app_id)} 的启动器未知。",
                                parent=self.window)




    # ==========================================
    # 🧱 俄罗斯方块代码
    # ==========================================
    def play_tetris(self):
        win = self.main_app.register_window(tk.Toplevel(self.parent))
        win.title("🧱 俄罗斯方块")
        win.geometry("380x520")
        win.configure(bg=Theme.BG_MAIN)
        win.resizable(False, False)

        cols, rows = 10, 20
        cell_size = 22
        grid = [[0] * cols for _ in range(rows)]
        
        shapes = [
            [[1, 1, 1, 1]], [[1, 1], [1, 1]], [[0, 1, 0], [1, 1, 1]],
            [[1, 0, 0], [1, 1, 1]], [[0, 0, 1], [1, 1, 1]],
            [[1, 1, 0], [0, 1, 1]], [[0, 1, 1], [1, 1, 0]]
        ]
        colors = ["#00ffff", "#ffff00", "#800080", "#0000ff", "#ffa500", "#00ff00", "#ff0000"]

        state = {"shape": None, "color": None, "x": 0, "y": 0, "running": True, "score": 0, "speed": 500, "task_id": None}

        canvas = tk.Canvas(win, width=cols*cell_size, height=rows*cell_size, bg="#111111", highlightthickness=0)
        canvas.pack(pady=10, side=tk.LEFT, padx=20)

        score_var = tk.StringVar(value="分数: 0")
        tk.Label(win, textvariable=score_var, font=("微软雅黑", 14), bg=Theme.BG_MAIN, fg=Theme.TEXT).pack(anchor="w", pady=10)
        
        def draw():
            canvas.delete("all")
            for r in range(rows):
                for c in range(cols):
                    if grid[r][c] != 0:
                        canvas.create_rectangle(c*cell_size, r*cell_size, (c+1)*cell_size, (r+1)*cell_size, fill=grid[r][c], outline="#333")
            if state["shape"]:
                for r, row in enumerate(state["shape"]):
                    for c, val in enumerate(row):
                        if val:
                            x, y = (state["x"]+c)*cell_size, (state["y"]+r)*cell_size
                            canvas.create_rectangle(x, y, x+cell_size, y+cell_size, fill=state["color"], outline="#333")

        def new_piece():
            idx = random.randint(0, len(shapes)-1)
            state["shape"] = shapes[idx]
            state["color"] = colors[idx]
            state["x"] = cols // 2 - len(state["shape"][0]) // 2
            state["y"] = 0
            if not valid(0, 0):
                state["running"] = False
                messagebox.showinfo("游戏结束", f"最终分数: {state['score']}", parent=win)

        def valid(dx, dy, shape=None):
            s = shape or state["shape"]
            for r, row in enumerate(s):
                for c, val in enumerate(row):
                    if val:
                        nx, ny = state["x"]+c+dx, state["y"]+r+dy
                        if nx < 0 or nx >= cols or ny >= rows or (ny >= 0 and grid[ny][nx] != 0): return False
            return True

        def lock_piece():
            for r, row in enumerate(state["shape"]):
                for c, val in enumerate(row):
                    if val:
                        ny, nx = state["y"]+r, state["x"]+c
                        if 0 <= ny < rows and 0 <= nx < cols: grid[ny][nx] = state["color"]
            
            cleared = 0
            for r in range(rows-1, -1, -1):
                if all(grid[r]):
                    del grid[r]
                    grid.insert(0, [0]*cols)
                    cleared += 1
            if cleared > 0:
                state["score"] += cleared * 100
                score_var.set(f"分数: {state['score']}")
                state["speed"] = max(100, state["speed"] - 20)
            new_piece()

        def move(dx, dy):
            if not state["running"]: return
            if valid(dx, dy):
                state["x"] += dx
                state["y"] += dy
                draw()
            elif dy > 0:
                lock_piece()

        def rotate():
            if not state["running"]: return
            rotated = [list(row) for row in zip(*state["shape"][::-1])]
            if valid(0, 0, rotated):
                state["shape"] = rotated
                draw()

        def game_loop():
            if not state["running"] or not win.winfo_exists(): return
            move(0, 1)
            state["task_id"] = win.after(state["speed"], game_loop)

        def on_key(e):
            if e.keysym == "Left": move(-1, 0)
            elif e.keysym == "Right": move(1, 0)
            elif e.keysym == "Down": move(0, 1)
            elif e.keysym == "Up": rotate()
            elif e.keysym == "space":
                while valid(0, 1): state["y"] += 1
                lock_piece()
                draw()

        win.bind("<KeyPress>", on_key)
        win.focus_force()
        
        new_piece()
        draw()
        game_loop()

    # ==========================================
    # 🌻 植物大战僵尸代码
    # ==========================================
    def play_pvz(self):
        """🌻 植物大战僵尸：已独立成 pvz.py，这里只负责启动"""
        try:
            from pvz import open_game
        except ImportError as e:
            messagebox.showwarning(
                "缺少模块",
                f"没有找到 pvz.py，请确保它和 app_store.py 放在同一个目录。\n\n{e}",
                parent=self.window)
            return
        try:
            open_game(self.main_app, self.parent)
        except Exception as e:
            messagebox.showerror("启动失败", f"植物大战僵尸启动出错：{e}",
                                 parent=self.window)



    def game_box(self):
        """🎮 小游戏合集：所有小游戏都从这里进"""
        win = self.main_app.register_window(tk.Toplevel(self.parent))
        win.title("🎮 小游戏合集")
        win.geometry("500x520")
        win.configure(bg=Theme.BG_MAIN)
        win.resizable(False, False)

        header = tk.Frame(win, bg=Theme.BG_CARD, height=52)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text="🎮 小游戏合集", font=("微软雅黑", 15, "bold"),
                 bg=Theme.BG_CARD, fg=Theme.TEXT).pack(side=tk.LEFT, padx=18, pady=10)
        tk.Label(header, text="7 款小游戏", font=("微软雅黑", 9),
                 bg=Theme.BG_CARD, fg=Theme.TEXT_DIM).pack(side=tk.RIGHT, padx=18)

        frame_main = tk.Frame(win, bg=Theme.BG_MAIN)
        frame_main.pack(fill=tk.BOTH, expand=True, padx=16, pady=12)

        def btn(parent_, text, cmd, color=Theme.BTN_PRIMARY, width=16):
            """本地小按钮（app_store 里没有 HoverButton，这里自带悬停效果）"""
            b = tk.Button(parent_, text=text, command=cmd, bg=color, fg=Theme.TEXT,
                          font=("微软雅黑", 10), relief=tk.FLAT, bd=0,
                          cursor="hand2", activebackground=Theme.BG_HOVER,
                          activeforeground=Theme.TEXT, padx=6, pady=5, width=width)
            def on_enter(event=None):
                try:
                    b.config(bg=Theme.BG_HOVER)
                except Exception:
                    pass

            def on_leave(event=None):
                try:
                    b.config(bg=color)
                except Exception:
                    pass
            b.bind("<Enter>", on_enter)
            b.bind("<Leave>", on_leave)
            return b

        def clear_frame():
            for w in frame_main.winfo_children():
                w.destroy()

        def back_menu():
            clear_frame()
            draw_menu()

        def external(fn):
            """独立游戏：另开一个窗口，合集窗口留着当入口"""
            def go():
                try:
                    fn()
                except Exception as e:
                    messagebox.showerror("启动失败", str(e), parent=win)
            return go

        # ================= 主菜单 =================
        def draw_menu():
            clear_frame()
            tk.Label(frame_main, text="完整游戏", font=("微软雅黑", 10, "bold"),
                     bg=Theme.BG_MAIN, fg=Theme.ACCENT).pack(anchor="w")

            grid = tk.Frame(frame_main, bg=Theme.BG_MAIN)
            grid.pack(fill=tk.X, pady=(4, 8))
            games = [
                ("🐍 贪吃蛇", self.main_app.game_snake),
                ("🧱 俄罗斯方块", self.play_tetris),
                ("🌻 植物大战僵尸", self.play_pvz),
                ("🧠 记忆翻牌", self.play_memory),
                ("⭕ 井字棋", self.play_tictactoe),
            ]
            for i, (name, fn) in enumerate(games):
                btn(grid, name, external(fn), Theme.BTN_PRIMARY, width=15).grid(
                    row=i // 2, column=i % 2, padx=3, pady=3, sticky="ew")
            grid.columnconfigure(0, weight=1)
            grid.columnconfigure(1, weight=1)

            tk.Label(frame_main, text="内置小游戏", font=("微软雅黑", 10, "bold"),
                     bg=Theme.BG_MAIN, fg=Theme.ACCENT).pack(anchor="w")
            inline = tk.Frame(frame_main, bg=Theme.BG_MAIN)
            inline.pack(fill=tk.X, pady=(4, 8))
            btn(inline, "✊ 石头剪刀布", draw_rps, Theme.BTN_DEFAULT, width=15).grid(
                row=0, column=0, padx=3, pady=3, sticky="ew")
            btn(inline, "🔢 猜数字", draw_guess, Theme.BTN_DEFAULT, width=15).grid(
                row=0, column=1, padx=3, pady=3, sticky="ew")
            inline.columnconfigure(0, weight=1)
            inline.columnconfigure(1, weight=1)

            tk.Label(frame_main,
                     text="点上面的按钮会另开一个游戏窗口，合集窗口可以留着当游戏入口。",
                     font=("微软雅黑", 9), bg=Theme.BG_MAIN, fg=Theme.TEXT_DIM,
                     wraplength=440, justify="left").pack(anchor="w", pady=(4, 0))

            btn(frame_main, "关闭窗口", lambda: win._on_close(), Theme.BTN_DANGER,
                width=12).pack(pady=10)

        # ================= 石头剪刀布 =================
        def draw_rps():
            clear_frame()
            tk.Label(frame_main, text="✊ 石头剪刀布", font=("微软雅黑", 14, "bold"),
                     bg=Theme.BG_MAIN, fg=Theme.TEXT).pack(pady=(6, 4))
            result_var = tk.StringVar(value="选一个出拳吧")
            tk.Label(frame_main, textvariable=result_var, font=("微软雅黑", 11),
                     bg=Theme.BG_MAIN, fg=Theme.TEXT_DIM, wraplength=420,
                     justify="center").pack(pady=(0, 10))

            def play(select):
                opts = ["石头", "剪刀", "布"]
                cpu = random.choice(opts)
                if select == cpu:
                    res = "平局"
                elif ((select == "石头" and cpu == "剪刀") or
                      (select == "剪刀" and cpu == "布") or
                      (select == "布" and cpu == "石头")):
                    res = "你赢了！"
                else:
                    res = "你输了"
                result_var.set(f"你出 {select}，电脑出 {cpu}\n{res}")

            row = tk.Frame(frame_main, bg=Theme.BG_MAIN)
            row.pack(pady=4)
            for txt, emo in (("石头", "✊"), ("剪刀", "✌️"), ("布", "✋")):
                btn(row, f"{emo} {txt}", lambda t=txt: play(t), Theme.BTN_PRIMARY,
                    width=7).pack(side=tk.LEFT, padx=4)

            btn(frame_main, "← 返回菜单", back_menu, Theme.BTN_DEFAULT,
                width=12).pack(pady=14)

        # ================= 猜数字 =================
        def draw_guess():
            clear_frame()
            target = random.randint(1, 100)
            tk.Label(frame_main, text="🔢 猜数字（1~100）", font=("微软雅黑", 14, "bold"),
                     bg=Theme.BG_MAIN, fg=Theme.TEXT).pack(pady=(6, 4))
            msg_var = tk.StringVar(value="输入一个数字，我告诉你大了还是小了")
            tk.Label(frame_main, textvariable=msg_var, font=("微软雅黑", 11),
                     bg=Theme.BG_MAIN, fg=Theme.TEXT_DIM, wraplength=420,
                     justify="center").pack(pady=(0, 10))

            entry = tk.Entry(frame_main, font=("微软雅黑", 13), bg=Theme.BG_PANEL,
                             fg=Theme.TEXT, insertbackground=Theme.ACCENT,
                             relief=tk.FLAT, width=10, justify="center", bd=0)
            entry.pack(pady=6, ipady=4)
            entry.focus_set()
            tries = {"n": 0}

            def check(event=None):
                txt = entry.get().strip()
                if not txt:
                    return
                if not txt.isdigit():
                    msg_var.set("请输入数字！")
                    return
                n = int(txt)
                tries["n"] += 1
                if n < target:
                    msg_var.set(f"小了！已猜 {tries['n']} 次")
                elif n > target:
                    msg_var.set(f"大了！已猜 {tries['n']} 次")
                else:
                    msg_var.set(f"🎉 猜对了！答案就是 {target}，共用了 {tries['n']} 次")
                    entry.config(state=tk.DISABLED)
                entry.delete(0, tk.END)

            entry.bind("<Return>", check)
            btn(frame_main, "提交", check, Theme.BTN_SUCCESS, width=10).pack(pady=6)
            btn(frame_main, "← 返回菜单", back_menu, Theme.BTN_DEFAULT,
                width=12).pack(pady=10)

        draw_menu()

    # ==========================================
    # 🧠 记忆翻牌
    # ==========================================
    def play_memory(self):
        win = self.main_app.register_window(tk.Toplevel(self.parent))
        win.title("🧠 记忆翻牌")
        win.geometry("440x520")
        win.configure(bg=Theme.BG_MAIN)
        win.resizable(False, False)

        emojis = ["🐱", "🐶", "🦊", "🐼", "🐰", "🐸"]
        deck = emojis * 2
        random.shuffle(deck)

        state = {
            "first": None,
            "lock": False,
            "matched": set(),
            "moves": 0
        }
        buttons = []

        top = tk.Frame(win, bg=Theme.BG_PANEL)
        top.pack(fill=tk.X, padx=12, pady=10)
        moves_var = tk.StringVar(value="步数：0")
        tk.Label(top, textvariable=moves_var, font=("微软雅黑", 12, "bold"),
                 bg=Theme.BG_PANEL, fg=Theme.TEXT).pack(side=tk.LEFT, padx=10)

        def reset_game():
            """重新开局"""
            nonlocal deck
            deck = emojis * 2
            random.shuffle(deck)
            state["first"] = None
            state["lock"] = False
            state["matched"].clear()
            state["moves"] = 0
            moves_var.set("步数：0")
            for idx, btn in enumerate(buttons):
                btn.config(text="❓", state=tk.NORMAL)

        tk.Button(top, text="🔄重新开始", command=reset_game, font=("微软雅黑", 10),
                  bg=Theme.BTN_PRIMARY, fg=Theme.TEXT, relief=tk.FLAT).pack(side=tk.RIGHT, padx=10)

        grid = tk.Frame(win, bg=Theme.BG_MAIN)
        grid.pack(pady=8)

        def on_click(i):
            if state["lock"]:
                return
            # 已经配对的卡片禁止点击
            if i in state["matched"]:
                return
            btn = buttons[i]
            # =========修复核心：禁止点击同一张卡片两次=========
            if state["first"] == i:
                return

            btn.config(text=deck[i])

            if state["first"] is None:
                # 第一张牌
                state["first"] = i
                return

            # 第二张牌
            state["moves"] += 1
            moves_var.set(f"步数：{state['moves']}")
            j = state["first"]
            state["first"] = None
            state["lock"] = True

            btn1 = buttons[j]
            if deck[i] == deck[j]:
                # 配对成功
                state["matched"].add(i)
                state["matched"].add(j)
                btn.config(state=tk.DISABLED)
                btn1.config(state=tk.DISABLED)
                if len(state["matched"]) == len(deck):
                    from tkinter import messagebox
                    messagebox.showinfo("🎉胜利", f"全部配对完成！总步数：{state['moves']}", parent=win)
                state["lock"] = False
            else:
                # 不匹配，延时翻回去
                def flip_back():
                    try:
                        buttons[i].config(text="❓", state=tk.NORMAL)
                        buttons[j].config(text="❓", state=tk.NORMAL)
                    except Exception:
                        pass
                    state["lock"] = False

                win.after(700, flip_back)

        buttons.clear()
        for i in range(len(deck)):
            r, c = divmod(i, 3)
            b = tk.Button(grid, text="❓", font=("Segoe UI Emoji", 22),
                          width=4, height=2, bg=Theme.BG_CARD, fg=Theme.TEXT,
                          activebackground=Theme.BG_PANEL, relief=tk.FLAT,
                          cursor="hand2", bd=0,
                          command=lambda idx=i: on_click(idx))
            b.grid(row=r, column=c, padx=6, pady=6)
            buttons.append(b)
#===============================
#⭕ 井字棋代码                   =
#===============================
    def play_tictactoe(self):
        win = self.main_app.register_window(tk.Toplevel(self.parent))
        win.title("⭕ 井字棋")
        win.geometry("360x430")
        win.configure(bg=Theme.BG_MAIN)
        win.resizable(False, False)

        board = [""] * 9
        buttons = []
        state = {"turn": "X", "over": False}
        wins = [(0, 1, 2), (3, 4, 5), (6, 7, 8),
                (0, 3, 6), (1, 4, 7), (2, 5, 8),
                (0, 4, 8), (2, 4, 6)]

        status_var = tk.StringVar(value="⚫ X 回合")
        tk.Label(win, textvariable=status_var, font=("微软雅黑", 14, "bold"),
                 bg=Theme.BG_MAIN, fg=Theme.TEXT).pack(pady=12)

        grid = tk.Frame(win, bg=Theme.BG_MAIN)
        grid.pack()

        def check_winner():
            for a, b, c in wins:
                if board[a] and board[a] == board[b] == board[c]:
                    return board[a]
            if all(board):
                return "draw"
            return None

        def on_click(i):
            if state["over"] or board[i]:
                return
            board[i] = state["turn"]
            buttons[i].config(text=state["turn"],
                              fg=Theme.BTN_PRIMARY if state["turn"] == "X" else Theme.BTN_DANGER)
            result = check_winner()
            if result == "draw":
                state["over"] = True
                status_var.set("🤝 平局！")
                messagebox.showinfo("井字棋", "双方打平！")
            elif result:
                state["over"] = True
                status_var.set(f"🎉 {result} 获胜！")
                messagebox.showinfo("井字棋", f"{result} 连成一线，获胜！")
            else:
                state["turn"] = "O" if state["turn"] == "X" else "X"
                status_var.set("⚫ X 回合" if state["turn"] == "X" else "🔴 O 回合")

        for i in range(9):
            btn = tk.Button(grid, text="", font=("微软雅黑", 22, "bold"),
                            width=3, height=1, bg=Theme.BG_CARD, fg=Theme.TEXT,
                            relief=tk.FLAT, cursor="hand2", bd=2,
                            command=lambda idx=i: on_click(idx))
            btn.grid(row=i // 3, column=i % 3, padx=4, pady=4)
            buttons.append(btn)

        def restart():
            for i in range(9):
                board[i] = ""
                buttons[i].config(text="")
            state["turn"] = "X"
            state["over"] = False
            status_var.set("⚫ X 回合")

        tk.Button(win, text="🔄 重新开始", command=restart, font=("微软雅黑", 10, "bold"),
                  bg=Theme.BG_CARD, fg=Theme.TEXT, relief=tk.FLAT, cursor="hand2",
                  padx=16, pady=6).pack(pady=16)
    ###################################
    #🐦 Flappy Bird 像素鸟
    ###################################
    def play_flappy(self):
        """🐦 像素鸟：空格/点击起飞，穿过水管间隙才加分"""
        win = self.main_app.register_window(tk.Toplevel(self.parent))
        win.title("🐦 Flappy Bird")
        win.geometry("400x560")
        win.configure(bg="#70c5ce")
        win.resizable(False, False)

        W, H, GROUND = 400, 560, 60
        PLAY_H = H - GROUND
        BX, BR = 70, 14
        GRAVITY, JUMP, SPEED = 0.42, -7.2, 4.2
        FRAME, PIPE_EVERY, PIPE_GAP = 16, 1450, 150

        canvas = tk.Canvas(win, width=W, height=H, bg="#70c5ce", highlightthickness=0)
        canvas.pack()

        # 地面和云（纯装饰）
        canvas.create_rectangle(0, PLAY_H, W, H, fill="#ded895", outline="")
        canvas.create_rectangle(0, PLAY_H, W, PLAY_H + 8, fill="#c9c069", outline="")
        for cx, cy, r in ((80, 80, 34), (300, 132, 26), (196, 58, 20)):
            canvas.create_oval(cx - r, cy - r * 0.6, cx + r, cy + r * 0.6,
                               fill="#9fd8e0", outline="")

        state = {"y": PLAY_H // 2, "vy": 0, "score": 0, "best": 0,
                 "alive": True, "started": False, "over": False,
                 "pipes": [], "job": None, "spawn": None}

        bird = canvas.create_oval(BX - BR, state["y"] - BR, BX + BR, state["y"] + BR,
                                  fill="#FFD700", outline="#FF8C00", width=2,
                                  tags=("bird",))
        score_id = canvas.create_text(W // 2, 76, text="0", fill="#ffffff",
                                      font=("微软雅黑", 28, "bold"), tags=("hud",))
        canvas.create_text(W // 2, PLAY_H // 2 + 52,
                           text="按空格 / 点击开始", fill="#0b4f6c",
                           font=("微软雅黑", 13, "bold"), tags=("hint", "hud"))
        canvas.flappy_state = state

        def setup_bird():
            canvas.coords(bird, BX - BR, state["y"] - BR, BX + BR, state["y"] + BR)
            canvas.tag_raise("hud")

        def bird_box():
            # 内缩 2px，手感比视觉宽容一点点
            return (BX - BR + 2, state["y"] - BR + 2, BX + BR - 2, state["y"] + BR - 2)

        def hit(rect):
            if not rect:
                return False
            bx1, by1, bx2, by2 = bird_box()
            return bx1 < rect[2] and bx2 > rect[0] and by1 < rect[3] and by2 > rect[1]

        def stop_jobs():
            for key in ("job", "spawn"):
                jid = state.get(key)
                if jid:
                    try:
                        win.after_cancel(jid)
                    except Exception:
                        pass
                state[key] = None

        def die(reason):
            state["alive"] = False
            state["over"] = True
            stop_jobs()
            state["best"] = max(state["best"], state["score"])
            canvas.delete("overlay")
            canvas.create_rectangle(52, 168, W - 52, 352, fill="#0b2b33",
                                    outline="#ffffff", width=2, tags=("overlay",))
            canvas.create_text(W // 2, 212, text="游戏结束", fill="#ffd700",
                               font=("微软雅黑", 22, "bold"), tags=("overlay",))
            canvas.create_text(W // 2, 254, text=reason, fill="#ffffff",
                               font=("微软雅黑", 11), tags=("overlay",))
            canvas.create_text(W // 2, 288,
                               text=f"得分 {state['score']}    最高 {state['best']}",
                               fill="#7fe7ff", font=("微软雅黑", 12, "bold"),
                               tags=("overlay",))
            canvas.create_text(W // 2, 322, text="点击 / 空格 再来一局",
                               fill="#ffffff", font=("微软雅黑", 11),
                               tags=("overlay",))

        def tick():
            state["job"] = None
            try:
                if not win.winfo_exists() or not state["alive"]:
                    return
            except Exception:
                return

            state["vy"] = min(state["vy"] + GRAVITY, 13)
            state["y"] += state["vy"]
            setup_bird()

            if state["y"] - BR <= 0:
                state["y"] = BR
                setup_bird()
                die("飞太高，撞到屏幕顶了")
                return
            if state["y"] + BR >= PLAY_H:
                state["y"] = PLAY_H - BR
                setup_bird()
                die("掉到地上了")
                return

            for p in list(state["pipes"]):
                canvas.move(p["top"], -SPEED, 0)
                canvas.move(p["bottom"], -SPEED, 0)
                if hit(canvas.coords(p["top"])) or hit(canvas.coords(p["bottom"])):
                    die("撞到水管了")
                    return
                if canvas.coords(p["top"])[2] < 0:
                    canvas.delete(p["top"])
                    canvas.delete(p["bottom"])
                    state["pipes"].remove(p)
                    state["score"] += 1
                    canvas.itemconfig(score_id, text=str(state["score"]))

            state["job"] = win.after(FRAME, tick)

        def spawn():
            state["spawn"] = None
            try:
                if not win.winfo_exists() or not state["alive"]:
                    return
            except Exception:
                return
            gy = random.randint(70, PLAY_H - 70 - PIPE_GAP)
            top = canvas.create_rectangle(W, -20, W + 54, gy,
                                          fill="#2ecc71", outline="#27ae60", width=2)
            bot = canvas.create_rectangle(W, gy + PIPE_GAP, W + 54, PLAY_H,
                                          fill="#2ecc71", outline="#27ae60", width=2)
            canvas.tag_lower(top, "bird")
            canvas.tag_lower(bot, "bird")
            canvas.tag_raise("hud")
            state["pipes"].append({"top": top, "bottom": bot})
            state["spawn"] = win.after(PIPE_EVERY, spawn)

        def reset():
            stop_jobs()
            for p in state["pipes"]:
                canvas.delete(p["top"])
                canvas.delete(p["bottom"])
            state["pipes"].clear()
            canvas.delete("overlay")
            state.update({"y": PLAY_H // 2, "vy": 0, "score": 0,
                          "alive": True, "started": False, "over": False})
            canvas.itemconfig(score_id, text="0")
            canvas.create_text(W // 2, PLAY_H // 2 + 52,
                               text="按空格 / 点击开始", fill="#0b4f6c",
                               font=("微软雅黑", 13, "bold"), tags=("hint", "hud"))
            setup_bird()

        def press(event=None):
            try:
                if not win.winfo_exists():
                    return
            except Exception:
                return
            if state["over"]:
                # 死后一点就直接重开并起飞，不用点两次
                reset()
                state["started"] = True
                canvas.delete("hint")
                state["vy"] = JUMP
                tick()
                spawn()
                return
            if not state["started"]:
                state["started"] = True
                canvas.delete("hint")
                state["vy"] = JUMP
                tick()
                spawn()
                return
            state["vy"] = JUMP

        # canvas 盖住了窗口，只绑 win 的话点屏幕根本不会跳
        for w in (win, canvas):
            w.bind("<space>", press)
            w.bind("<Button-1>", press)

        def on_destroy(event=None):
            if event is not None and getattr(event, "widget", None) is not win:
                return
            state["alive"] = False
            stop_jobs()

        win.bind("<Destroy>", on_destroy)
        try:
            win.focus_force()
        except Exception:
            pass


    # ==========================================
    # ☠️ 趣味模拟病毒
    # ==========================================
    # ==========================================
    # 🧰 实用工具（单位换算 / 密码 / 番茄钟 / 待办 / 系统信息 / 世界时钟）
    # ==========================================
    UNIT_TABLE = {
        "长度": {"米": 1.0, "千米": 1000.0, "厘米": 0.01, "毫米": 0.001,
                 "英寸": 0.0254, "英尺": 0.3048, "码": 0.9144, "英里": 1609.344},
        "重量": {"千克": 1.0, "克": 0.001, "吨": 1000.0, "斤": 0.5,
                 "磅": 0.45359237, "盎司": 0.028349523},
        "面积": {"平方米": 1.0, "平方千米": 1e6, "公顷": 10000.0,
                 "亩": 666.666667, "平方英尺": 0.09290304, "英亩": 4046.856422},
        "体积": {"升": 1.0, "毫升": 0.001, "立方米": 1000.0, "美制加仑": 3.785411784},
        "速度": {"米/秒": 1.0, "千米/时": 0.277777778, "英里/时": 0.44704,
                 "节": 0.514444444},
        "数据": {"字节": 1.0, "KB": 1024.0, "MB": 1048576.0,
                 "GB": 1073741824.0, "TB": 1099511627776.0},
        "温度": {"摄氏度": 1.0, "华氏度": 1.0, "开尔文": 1.0},
    }

    WORLD_CITIES = [
        ("北京", "Asia/Shanghai", 8),
        ("东京", "Asia/Tokyo", 9),
        ("悉尼", "Australia/Sydney", 10),
        ("迪拜", "Asia/Dubai", 4),
        ("莫斯科", "Europe/Moscow", 3),
        ("巴黎", "Europe/Paris", 1),
        ("伦敦", "Europe/London", 0),
        ("纽约", "America/New_York", -5),
        ("洛杉矶", "America/Los_Angeles", -8),
    ]

    def _tool_window(self, title, w, h):
        win = self.main_app.register_window(tk.Toplevel(self.parent))
        win.title(title)
        win.geometry(f"{w}x{h}")
        win.configure(bg=Theme.BG_MAIN)
        win.resizable(False, False)
        return win

    def _tool_button(self, parent, text, cmd, color=None, width=9):
        return tk.Button(parent, text=text, command=cmd,
                         font=("微软雅黑", 10, "bold"),
                         bg=color or Theme.BG_CARD, fg=Theme.TEXT,
                         activebackground=Theme.BG_HOVER,
                         activeforeground=Theme.TEXT,
                         relief=tk.FLAT, cursor="hand2", padx=10, pady=5,
                         width=width)

    # ---------- 🧮 单位换算 ----------
    def tool_unit(self):
        win = self._tool_window("🧮 单位换算", 720, 420)

        cats = list(self.UNIT_TABLE)
        cat_var = tk.StringVar(value=cats[0])
        in_var = tk.StringVar(value="1")
        out_var = tk.StringVar(value="1")
        unit_state = {"from": None, "to": None}

        # 类别
        cat_box = tk.Frame(win, bg=Theme.BG_MAIN)
        cat_box.pack(fill=tk.X, padx=20, pady=(16, 6))
        for i, c in enumerate(cats):
            tk.Radiobutton(cat_box, text=c, variable=cat_var, value=c,
                           command=lambda: rebuild(),
                           font=("微软雅黑", 9), bg=Theme.BG_MAIN,
                           fg=Theme.TEXT, activebackground=Theme.BG_MAIN,
                           activeforeground=Theme.ACCENT,
                           selectcolor=Theme.BG_CARD,
                           indicatoron=0, relief=tk.FLAT, padx=10, pady=3
                           ).pack(side=tk.LEFT, padx=3)

        unit_row = tk.Frame(win, bg=Theme.BG_MAIN)
        unit_row.pack(fill=tk.X, padx=20, pady=8)

        def make_option(parent, var, units):
            om = tk.OptionMenu(parent, var, *units,
                               command=lambda _=None: calc())
            om.config(font=("微软雅黑", 10), bg=Theme.BG_CARD, fg=Theme.TEXT,
                      activebackground=Theme.BG_HOVER, relief=tk.FLAT,
                      highlightthickness=0, width=12, anchor="w")
            try:
                om["menu"].config(bg=Theme.BG_CARD, fg=Theme.TEXT,
                                  activebackground=Theme.BG_HOVER,
                                  activeforeground=Theme.TEXT,
                                  font=("微软雅黑", 9))
            except Exception:
                pass
            return om

        input_row = tk.Frame(win, bg=Theme.BG_MAIN)
        input_row.pack(fill=tk.X, padx=20, pady=(4, 6))
        tk.Label(input_row, text="数值", font=("微软雅黑", 9),
                 bg=Theme.BG_MAIN, fg=Theme.TEXT_DIM).pack(side=tk.LEFT, padx=(0, 8))
        ent = tk.Entry(input_row, textvariable=in_var, font=("Consolas", 14),
                       bg=Theme.BG_CARD, fg=Theme.TEXT, insertbackground=Theme.TEXT,
                       relief=tk.FLAT, justify="center")
        ent.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=6)

        result_box = tk.Frame(win, bg=Theme.BG_PANEL, height=64)
        result_box.pack(fill=tk.X, padx=20, pady=(4, 10))
        result_box.pack_propagate(False)
        tk.Label(result_box, textvariable=out_var, font=("Consolas", 22, "bold"),
                 bg=Theme.BG_PANEL, fg=Theme.ACCENT).pack(expand=True)

        tip = tk.Label(win, text="输入数值即时换算，支持负数与小数",
                       font=("微软雅黑", 9), bg=Theme.BG_MAIN, fg=Theme.TEXT_DIM)
        tip.pack(pady=(0, 12))

        def fmt(v):
            if v == 0:
                return "0"
            if abs(v) >= 1e15 or abs(v) < 1e-6:
                return f"{v:.6e}"
            s = f"{v:,.6f}".rstrip("0").rstrip(".")
            return s if s not in ("", "-") else "0"

        def calc(*_):
            cat = cat_var.get()
            a, b = unit_state["from"].get(), unit_state["to"].get()
            try:
                val = float(in_var.get().replace(",", "").strip())
            except Exception:
                out_var.set("请输入数字")
                return
            try:
                if cat == "温度":
                    c = {"摄氏度": val,
                         "华氏度": (val - 32) * 5 / 9,
                         "开尔文": val - 273.15}[a]
                    res = {"摄氏度": c,
                           "华氏度": c * 9 / 5 + 32,
                           "开尔文": c + 273.15}[b]
                else:
                    t = self.UNIT_TABLE[cat]
                    res = val * t[a] / t[b]
                out_var.set(f"{fmt(res)}  {b}")
            except Exception as e:
                out_var.set(f"换算失败：{e}")

        def rebuild():
            for w in unit_row.winfo_children():
                w.destroy()
            units = list(self.UNIT_TABLE[cat_var.get()])
            unit_state["from"] = tk.StringVar(value=units[0])
            unit_state["to"] = tk.StringVar(
                value=units[1] if len(units) > 1 else units[0])
            make_option(unit_row, unit_state["from"], units).pack(side=tk.LEFT)
            tk.Label(unit_row, text="→", font=("Microsoft YaHei", 14, "bold"),
                     bg=Theme.BG_MAIN, fg=Theme.ACCENT).pack(side=tk.LEFT, padx=12)
            make_option(unit_row, unit_state["to"], units).pack(side=tk.LEFT)
            calc()

        ent.bind("<KeyRelease>", calc)

        rebuild()

    # ---------- 🔑 密码生成器 ----------
    def tool_password(self):
        win = self._tool_window("🔑 密码生成器", 460, 430)

        alphabet = {
            "大写字母": "ABCDEFGHJKLMNPQRSTUVWXYZ",
            "小写字母": "abcdefghijkmnopqrstuvwxyz",
            "数字": "23456789",
            "符号": "!@#$%^&*()-_=+[]{}?",
        }
        flips = {k: tk.BooleanVar(value=True) for k in alphabet}

        length_var = tk.IntVar(value=16)
        result_var = tk.StringVar(value="")
        tip_var = tk.StringVar(value="点「生成」创建密码")

        tk.Label(win, text="长度", font=("微软雅黑", 10),
                 bg=Theme.BG_MAIN, fg=Theme.TEXT).pack(anchor="w", padx=24, pady=(18, 2))
        row_len = tk.Frame(win, bg=Theme.BG_MAIN)
        row_len.pack(fill=tk.X, padx=24)
        scale = tk.Scale(row_len, from_=6, to=48, orient=tk.HORIZONTAL,
                         variable=length_var, showvalue=True,
                         bg=Theme.BG_MAIN, fg=Theme.TEXT,
                         troughcolor=Theme.BG_CARD, highlightthickness=0,
                         activebackground=Theme.ACCENT, length=380)
        scale.pack(side=tk.LEFT)

        row_flip = tk.Frame(win, bg=Theme.BG_MAIN)
        row_flip.pack(fill=tk.X, padx=24, pady=10)
        for i, (name, var) in enumerate(flips.items()):
            tk.Checkbutton(row_flip, text=name, variable=var,
                           bg=Theme.BG_MAIN, fg=Theme.TEXT,
                           selectcolor=Theme.BG_CARD,
                           activebackground=Theme.BG_MAIN,
                           activeforeground=Theme.TEXT,
                           font=("微软雅黑", 9)
                           ).grid(row=i // 2, column=i % 2, sticky="w", padx=4, pady=4)

        res = tk.Entry(win, textvariable=result_var, font=("Consolas", 13),
                       bg=Theme.BG_PANEL, fg=Theme.ACCENT,
                       insertbackground=Theme.TEXT, relief=tk.FLAT,
                       justify="center", state="readonly")
        res.pack(fill=tk.X, padx=24, ipady=8)

        tk.Label(win, textvariable=tip_var, font=("微软雅黑", 9),
                 bg=Theme.BG_MAIN, fg=Theme.TEXT_DIM).pack(pady=6)

        btn_row = tk.Frame(win, bg=Theme.BG_MAIN)
        btn_row.pack(pady=6)

        def gen():
            pools = [alphabet[k] for k, v in flips.items() if v.get()]
            if not pools:
                tip_var.set("⚠️ 至少勾选一类字符")
                return
            n = max(6, int(length_var.get()))
            pwd = [random.choice(p) for p in pools]
            allchars = "".join(pools)
            pwd += [random.choice(allchars)
                    for _ in range(max(0, n - len(pools)))]
            random.shuffle(pwd)
            pwd = "".join(pwd[:n])
            result_var.set(pwd)
            score = (len(pools) * 2 + min(n, 32) / 8)
            tip_var.set(f"长度 {n} · {len(pools)} 类字符 · "
                        + ("强度不错 ✅" if score >= 9 else "偏弱，建议加长或加类别"))

        def copy():
            pwd = result_var.get()
            if not pwd:
                gen()
                pwd = result_var.get()
            try:
                win.clipboard_clear()
                win.clipboard_append(pwd)
                self.main_app.toast("密码已复制到剪贴板", icon="📋")
            except Exception:
                self.main_app.toast("复制失败", icon="⚠️")

        self._tool_button(btn_row, "生成", gen, Theme.BTN_PRIMARY, 8).pack(side=tk.LEFT, padx=6)
        self._tool_button(btn_row, "复制", copy, Theme.BTN_SUCCESS, 8).pack(side=tk.LEFT, padx=6)
        gen()

    # ---------- 🍅 番茄钟 ----------
    def tool_pomodoro(self):
        win = self._tool_window("🍅 番茄钟", 420, 400)

        state = {"work": 25, "rest": 5, "mode": "work",
                 "left": 25 * 60, "running": False, "job": None}
        mode_var = tk.StringVar(value="🍅 专注中")
        time_var = tk.StringVar(value="25:00")

        tk.Label(win, textvariable=mode_var, font=("微软雅黑", 12, "bold"),
                 bg=Theme.BG_MAIN, fg=Theme.TEXT).pack(pady=(26, 4))
        tk.Label(win, textvariable=time_var, font=("Consolas", 40, "bold"),
                 bg=Theme.BG_MAIN, fg=Theme.GOLD).pack()

        canvas = tk.Canvas(win, width=320, height=26, bg=Theme.BG_PANEL,
                           highlightthickness=0)
        canvas.pack(pady=14)
        canvas.create_rectangle(6, 6, 314, 22, fill=Theme.BG_MAIN, outline="")
        bar = canvas.create_rectangle(6, 6, 6, 22, fill=Theme.BTN_SUCCESS, outline="")

        cfg_row = tk.Frame(win, bg=Theme.BG_MAIN)
        cfg_row.pack(pady=4)
        tk.Label(cfg_row, text="专注", font=("微软雅黑", 9),
                 bg=Theme.BG_MAIN, fg=Theme.TEXT_DIM).pack(side=tk.LEFT)
        w_spin = tk.Spinbox(cfg_row, from_=1, to=90, width=4,
                            font=("Consolas", 10), bg=Theme.BG_CARD,
                            fg=Theme.TEXT, relief=tk.FLAT, justify="center")
        w_spin.delete(0, "end")
        w_spin.insert(0, "25")
        w_spin.pack(side=tk.LEFT, padx=4)
        tk.Label(cfg_row, text="分钟   休息", font=("微软雅黑", 9),
                 bg=Theme.BG_MAIN, fg=Theme.TEXT_DIM).pack(side=tk.LEFT)
        r_spin = tk.Spinbox(cfg_row, from_=1, to=60, width=4,
                            font=("Consolas", 10), bg=Theme.BG_CARD,
                            fg=Theme.TEXT, relief=tk.FLAT, justify="center")
        r_spin.delete(0, "end")
        r_spin.insert(0, "5")
        r_spin.pack(side=tk.LEFT, padx=4)
        tk.Label(cfg_row, text="分钟", font=("微软雅黑", 9),
                 bg=Theme.BG_MAIN, fg=Theme.TEXT_DIM).pack(side=tk.LEFT)

        btn_row = tk.Frame(win, bg=Theme.BG_MAIN)
        btn_row.pack(pady=16)

        def total():
            return max(1, (state["work"] if state["mode"] == "work"
                           else state["rest"])) * 60

        def redraw():
            mm, ss = divmod(max(0, state["left"]), 60)
            time_var.set(f"{mm:02d}:{ss:02d}")
            mode_var.set("🍅 专注中" if state["mode"] == "work" else "☕ 休息中")
            frac = 1 - state["left"] / total()
            frac = max(0.0, min(1.0, frac))
            canvas.coords(bar, 6, 6, 6 + 308 * frac, 22)
            canvas.itemconfig(bar, fill=Theme.BTN_SUCCESS if state["mode"] == "work"
                              else Theme.ACCENT)

        def ring():
            def play():
                try:
                    import winsound
                    for _ in range(3):
                        winsound.Beep(880, 180)
                except Exception:
                    pass
            try:
                import threading
                threading.Thread(target=play, daemon=True).start()
            except Exception:
                pass

        def alive():
            try:
                return win.winfo_exists()
            except Exception:
                return False

        def finish():
            was_work = state["mode"] == "work"
            state["running"] = False
            state["job"] = None
            try:
                ring()
            except Exception:
                pass
            self.main_app.toast(
                "专注结束，休息一下吧 ☕" if was_work else "休息结束，继续干活 🍅",
                icon="🍅")
            state["mode"] = "rest" if was_work else "work"
            state["left"] = total()
            redraw()

        def tick():
            state["job"] = None
            if not alive() or not state["running"]:
                return
            state["left"] -= 1
            if state["left"] <= 0:
                finish()
                return
            redraw()
            state["job"] = win.after(1000, tick)

        def toggle():
            if not state["running"]:
                state["running"] = True
                tick()
                start_btn.config(text="⏸ 暂停")
            else:
                state["running"] = False
                if state["job"]:
                    try:
                        win.after_cancel(state["job"])
                    except Exception:
                        pass
                state["job"] = None
                start_btn.config(text="▶ 开始")

        def reset():
            state["running"] = False
            if state["job"]:
                try:
                    win.after_cancel(state["job"])
                except Exception:
                    pass
            state["job"] = None
            try:
                state["work"] = max(1, int(w_spin.get()))
                state["rest"] = max(1, int(r_spin.get()))
            except Exception:
                state["work"], state["rest"] = 25, 5
            state["mode"] = "work"
            state["left"] = total()
            start_btn.config(text="▶ 开始")
            redraw()

        start_btn = self._tool_button(btn_row, "▶ 开始", toggle, Theme.BTN_PRIMARY, 8)
        start_btn.pack(side=tk.LEFT, padx=6)
        self._tool_button(btn_row, "重置", reset, Theme.BTN_DEFAULT, 8).pack(side=tk.LEFT, padx=6)

        tipv = tk.StringVar(value="专注时段结束会自动切到休息")
        tk.Label(win, textvariable=tipv, font=("微软雅黑", 9),
                 bg=Theme.BG_MAIN, fg=Theme.TEXT_DIM).pack(pady=(2, 0))
        redraw()

    # ---------- ✅ 待办清单 ----------
    def tool_todo(self):
        base = os.path.dirname(os.path.abspath(__file__))
        path = os.path.join(base, "todo_data.json")

        items = []
        try:
            if os.path.exists(path):
                raw = json.load(open(path, encoding="utf-8"))
                if isinstance(raw, list):
                    for it in raw:
                        if isinstance(it, dict) and "text" in it:
                            items.append({"text": str(it["text"]),
                                          "done": bool(it.get("done"))})
        except Exception:
            items = []

        win = self._tool_window("✅ 待办清单", 470, 540)
        cnt_var = tk.StringVar(value="")

        row_add = tk.Frame(win, bg=Theme.BG_MAIN)
        row_add.pack(fill=tk.X, padx=16, pady=(14, 8))
        entry = tk.Entry(row_add, font=("微软雅黑", 11), bg=Theme.BG_CARD,
                         fg=Theme.TEXT, insertbackground=Theme.TEXT,
                         relief=tk.FLAT)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=5)

        wrap = tk.Frame(win, bg=Theme.BG_PANEL)
        wrap.pack(fill=tk.BOTH, expand=True, padx=16)
        canvas = tk.Canvas(wrap, bg=Theme.BG_PANEL, highlightthickness=0)
        sb = tk.Scrollbar(wrap, orient=tk.VERTICAL, command=canvas.yview)
        inner = tk.Frame(canvas, bg=Theme.BG_PANEL)
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=sb.set)
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        sb.pack(side=tk.RIGHT, fill=tk.Y)

        def refresh_scroll(_=None):
            canvas.configure(scrollregion=canvas.bbox("all"))

        inner.bind("<Configure>", refresh_scroll)

        def save():
            try:
                json.dump(items, open(path, "w", encoding="utf-8"),
                          ensure_ascii=False, indent=2)
            except Exception:
                pass

        def count():
            done = sum(1 for i in items if i["done"])
            cnt_var.set(f"共 {len(items)} 项 · 已完成 {done} 项")

        def render():
            for w in inner.winfo_children():
                w.destroy()
            if not items:
                tk.Label(inner, text="还没有待办，上面输入框加一条吧",
                         font=("微软雅黑", 10), bg=Theme.BG_PANEL,
                         fg=Theme.TEXT_DIM).pack(pady=40)
            for idx, it in enumerate(items):
                row = tk.Frame(inner, bg=Theme.BG_PANEL)
                row.pack(fill=tk.X, pady=1, padx=4)
                var = tk.BooleanVar(value=it["done"])

                def on_toggle(i=idx, v=var):
                    items[i]["done"] = bool(v.get())
                    save()
                    count()

                cb = tk.Checkbutton(row, text=it["text"], variable=var,
                                    command=on_toggle,
                                    font=("微软雅黑", 10),
                                    bg=Theme.BG_PANEL,
                                    fg=Theme.TEXT_DIM if it["done"] else Theme.TEXT,
                                    selectcolor=Theme.BG_CARD,
                                    activebackground=Theme.BG_PANEL,
                                    activeforeground=Theme.TEXT,
                                    anchor="w", justify="left")
                cb.pack(side=tk.LEFT, fill=tk.X, expand=True)

                def on_del(i=idx):
                    if 0 <= i < len(items):
                        items.pop(i)
                        save()
                        render()

                tk.Button(row, text="×", command=on_del,
                          font=("微软雅黑", 10, "bold"),
                          bg=Theme.BG_PANEL, fg=Theme.ACCENT2,
                          activebackground=Theme.BG_HOVER,
                          activeforeground=Theme.TEXT,
                          relief=tk.FLAT, cursor="hand2", width=2,
                          bd=0).pack(side=tk.RIGHT)
            count()
            refresh_scroll()

        def add():
            t = entry.get().strip()
            if not t:
                return
            items.append({"text": t, "done": False})
            save()
            entry.delete(0, tk.END)
            render()
            canvas.yview_moveto(1.0)

        def clear_done():
            n = sum(1 for i in items if i["done"])
            if not n:
                self.main_app.toast("没有已完成的条目", icon="ℹ️")
                return
            items[:] = [i for i in items if not i["done"]]
            save()
            render()
            self.main_app.toast(f"清掉了 {n} 条已完成", icon="🧹")

        add_btn = self._tool_button(row_add, "添加", add, Theme.BTN_PRIMARY, 6)
        add_btn.pack(side=tk.LEFT, padx=(8, 0))
        entry.bind("<Return>", lambda e: add())

        foot = tk.Frame(win, bg=Theme.BG_MAIN)
        foot.pack(fill=tk.X, padx=16, pady=10)
        tk.Label(foot, textvariable=cnt_var, font=("微软雅黑", 9),
                 bg=Theme.BG_MAIN, fg=Theme.TEXT_DIM).pack(side=tk.LEFT)
        self._tool_button(foot, "清空已完成", clear_done, Theme.BTN_DEFAULT, 10
                          ).pack(side=tk.RIGHT)

        render()

    # ---------- 📊 系统信息 ----------
    def tool_sysinfo(self):
        win = self._tool_window("📊 系统信息", 520, 470)
        fields = ["系统版本", "机器架构", "处理器", "CPU 核心",
                  "物理内存", "磁盘空间", "Python 版本",
                  "屏幕分辨率", "主机名", "当前用户"]
        vars_map = {f: tk.StringVar(value="…") for f in fields}

        body = tk.Frame(win, bg=Theme.BG_PANEL)
        body.pack(fill=tk.BOTH, expand=True, padx=16, pady=14)
        for i, f in enumerate(fields):
            tk.Label(body, text=f, font=("微软雅黑", 9),
                     bg=Theme.BG_PANEL, fg=Theme.TEXT_DIM,
                     width=12, anchor="w").grid(row=i, column=0, sticky="w",
                                                padx=(12, 6), pady=5)
            tk.Label(body, textvariable=vars_map[f], font=("Consolas", 10),
                     bg=Theme.BG_PANEL, fg=Theme.TEXT, anchor="w",
                     justify="left", wraplength=330).grid(
                row=i, column=1, sticky="w", pady=5)

        def mem_gb():
            try:
                import ctypes

                class MS(ctypes.Structure):
                    _fields_ = [("dwLength", ctypes.c_ulong),
                                ("dwMemoryLoad", ctypes.c_ulong),
                                ("ullTotalPhys", ctypes.c_ulonglong),
                                ("ullAvailPhys", ctypes.c_ulonglong),
                                ("ullTotalPageFile", ctypes.c_ulonglong),
                                ("ullAvailPageFile", ctypes.c_ulonglong),
                                ("ullTotalVirtual", ctypes.c_ulonglong),
                                ("ullAvailVirtual", ctypes.c_ulonglong),
                                ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
                m = MS()
                m.dwLength = ctypes.sizeof(MS)
                ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
                return m.ullTotalPhys / 1024 ** 3, m.ullAvailPhys / 1024 ** 3
            except Exception:
                return None

        def collect():
            import platform
            import shutil
            import sys
            import getpass
            vars_map["系统版本"].set(f"{platform.system()} {platform.release()}")
            vars_map["机器架构"].set(platform.machine() or "未知")
            vars_map["处理器"].set((platform.processor() or "未知")[:48])
            vars_map["CPU 核心"].set(f"{os.cpu_count()} 个逻辑核心")
            g = mem_gb()
            if g:
                vars_map["物理内存"].set(f"{g[0]:.1f} GB（可用 {g[1]:.1f} GB）")
            else:
                vars_map["物理内存"].set("读取失败")
            try:
                du = shutil.disk_usage(os.path.dirname(os.path.abspath(__file__)))
                vars_map["磁盘空间"].set(
                    f"总共 {du.total / 1024 ** 3:.1f} GB · "
                    f"可用 {du.free / 1024 ** 3:.1f} GB")
            except Exception:
                vars_map["磁盘空间"].set("读取失败")
            vars_map["Python 版本"].set(platform.python_version()
                                        + f"（{sys.executable.split(os.sep)[-1]}）")
            try:
                vars_map["屏幕分辨率"].set(
                    f"{win.winfo_screenwidth()} x {win.winfo_screenheight()}")
            except Exception:
                vars_map["屏幕分辨率"].set("未知")
            vars_map["主机名"].set(platform.node() or "未知")
            try:
                vars_map["当前用户"].set(getpass.getuser())
            except Exception:
                vars_map["当前用户"].set("未知")

        foot = tk.Frame(win, bg=Theme.BG_MAIN)
        foot.pack(fill=tk.X, padx=16, pady=(0, 12))
        self._tool_button(foot, "刷新", lambda: (collect(),
                                                self.main_app.toast("信息已刷新", icon="📊")),
                          Theme.BTN_PRIMARY, 8).pack(side=tk.RIGHT)
        collect()

    # ---------- 🕐 世界时钟 ----------
    def tool_worldclock(self):
        win = self._tool_window("🕐 世界时钟", 480, 500)
        import datetime as dt

        def now_in(tz_name, off):
            try:
                from zoneinfo import ZoneInfo
                return dt.datetime.now(ZoneInfo(tz_name))
            except Exception:
                return dt.datetime.now(
                    dt.timezone(dt.timedelta(hours=off)))

        rows = []
        for i, (city, tz_name, off) in enumerate(self.WORLD_CITIES):
            card = tk.Frame(win, bg=Theme.BG_PANEL)
            card.pack(fill=tk.X, padx=16, pady=3)
            tk.Label(card, text=city, font=("微软雅黑", 10),
                     bg=Theme.BG_PANEL, fg=Theme.TEXT, width=6,
                     anchor="w").pack(side=tk.LEFT, padx=(12, 0), pady=6)
            t_lbl = tk.Label(card, text="--:--:--", font=("Consolas", 15, "bold"),
                             bg=Theme.BG_PANEL, fg=Theme.ACCENT)
            t_lbl.pack(side=tk.LEFT, padx=8)
            d_lbl = tk.Label(card, text="", font=("微软雅黑", 8),
                             bg=Theme.BG_PANEL, fg=Theme.TEXT_DIM)
            d_lbl.pack(side=tk.RIGHT, padx=12)
            rows.append((tz_name, off, t_lbl, d_lbl))

        local = tk.Label(win, text="", font=("微软雅黑", 9),
                         bg=Theme.BG_MAIN, fg=Theme.TEXT_DIM)
        local.pack(pady=(6, 10))

        def alive():
            try:
                return win.winfo_exists()
            except Exception:
                return False

        def tick():
            if not alive():
                return
            for tz_name, off, t_lbl, d_lbl in rows:
                n = now_in(tz_name, off)
                t_lbl.config(text=n.strftime("%H:%M:%S"))
                d_lbl.config(text=n.strftime("%m-%d"))
            local.config(text="本机时间 " + dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                         + " · 每秒刷新")
            win.after(1000, tick)

        tick()

    def execute_virus(self):
        ans = messagebox.askyesno("⚠️ 严重警告",
                                  "您确定要运行【极恶病毒】吗？\n\n这可能会让您的系统崩溃！",
                                  icon="warning", parent=self.window)
        if not ans:
            return

        # tkinter 不是线程安全的：所有窗口一律在主线程用 after 错开生成。
        # 以前用 threading.Thread 建窗口，会让 Tcl 解释器直接崩掉（即"炸了"）。
        def spawn_failure_window(i):
            try:
                if not self.parent.winfo_exists():
                    return
                w = self.main_app.register_window(tk.Toplevel(self.parent))
                w.title("☠️ SYSTEM FAILURE")
                w.geometry("300x150")
                w.geometry(f"+{random.randint(100, 800)}+{random.randint(100, 600)}")
                w.configure(bg="red")
                w.attributes("-topmost", True)
                tk.Label(w, text="⚠️ 您的系统已被入侵！", font=("微软雅黑", 12, "bold"),
                         bg="red", fg="white").pack(pady=20)
                tk.Label(w, text=f"错误代码: 0x{i}F8A2", font=("Consolas", 10),
                         bg="red", fg="yellow").pack()
                w.after(2500, lambda: w._on_close() if w.winfo_exists() else None)
            except Exception:
                pass

        for i in range(8):
            self.parent.after(i * 90, lambda i=i: spawn_failure_window(i))

        bsod = self.main_app.register_window(tk.Toplevel(self.parent))
        bsod.attributes("-fullscreen", True)
        bsod.configure(bg="#0000aa")
        bsod.attributes("-topmost", True)

        tk.Label(bsod, text=":(", font=("Segoe UI", 80),
                 bg="#0000aa", fg="white").pack(anchor="w", padx=100, pady=(100, 20))
        bsod_text = ("您的电脑遇到问题，需要重新启动。\n"
                     "我们只收集某些错误信息...\n\n"
                     "CRITICAL_PROCESS_DIED\n极恶病毒: v6.6.6")
        tk.Label(bsod, text=bsod_text, font=("微软雅黑", 18),
                 bg="#0000aa", fg="white", justify="left").pack(anchor="w", padx=100, pady=20)

        progress_var = tk.StringVar(value="0% 完成")
        tk.Label(bsod, textvariable=progress_var, font=("微软雅黑", 18),
                 bg="#0000aa", fg="white").pack(anchor="w", padx=100)

        def close_bsod():
            try:
                if bsod.winfo_exists():
                    handler = getattr(bsod, "_on_close", None)
                    if callable(handler):
                        handler()
                    else:
                        bsod.destroy()
            except Exception:
                pass

        def fake_progress(val=0):
            if not bsod.winfo_exists():
                return
            try:
                if val <= 100:
                    progress_var.set(f"{val}% 完成")
                    bsod.after(100, fake_progress, val + 10)
                else:
                    close_bsod()
                    self._virus_aftermath()
            except Exception:
                close_bsod()

        # 兜底：不管中间出什么事，蓝屏最多停留 6 秒，防止全屏窗口把系统挡住
        bsod.after(6000, close_bsod)
        fake_progress()

    def _virus_aftermath(self):
        """蓝屏结束后：清场、弹黑客留言、把病毒从已安装列表里摘掉"""
        try:
            self.main_app.close_all_windows()
        except Exception:
            pass

        try:
            fake_error = self.main_app.register_window(tk.Toplevel(self.parent))
            fake_error.title("☠️ 黑客留言")
            fake_error.geometry("500x200")
            fake_error.configure(bg="black")
            fake_error.geometry(
                f"+{self.parent.winfo_screenwidth() // 2 - 250}"
                f"+{self.parent.winfo_screenheight() // 2 - 100}")
            fake_error.attributes("-topmost", True)

            label = tk.Label(fake_error, text="", font=("Consolas", 14, "bold"),
                             bg="black", fg="#00ff00", justify="left")
            label.pack(pady=30, padx=30)
            msg = ("> 哈哈，被你骗到了！\n"
                   "> 这只是一个模拟病毒。\n"
                   "> 你的文件很安全。\n"
                   "> 欢迎来到 MiniOS！")

            def type_text(i=0):
                if not fake_error.winfo_exists():
                    return
                if i < len(msg):
                    label.config(text=msg[:i + 1] + "█")
                    fake_error.after(80, type_text, i + 1)
                else:
                    label.config(text=msg)
                    fake_error.after(3000, lambda: fake_error._on_close()
                                     if fake_error.winfo_exists() else None)

            type_text()
        except Exception:
            pass

        try:
            if "virus" in self.installed_apps:
                self.installed_apps.remove("virus")
            if "virus" in self.desktop_apps:
                self.desktop_apps.remove("virus")
            self.save_installed()
            self.render_list()
            self.main_app.refresh_desktop_icons()
        except Exception:
            pass

