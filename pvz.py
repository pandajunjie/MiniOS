"""
MiniOS Lite v2.0 - 植物大战僵尸（独立模块）

相对原来内嵌在 app_store 里的版本，补上了三件事：
  1. 僵尸会真的啃植物：植物有血量，被啃光就消失，僵尸继续往前走
  2. 5 种植物：向日葵 / 豌豆射手 / 寒冰射手 / 坚果墙 / 樱桃炸弹
  3. 3 个关卡 + 无尽模式，波数、僵尸血量与速度逐关递增

用法：from pvz import open_game; open_game(main_app, parent_window)
"""

import random
import tkinter as tk
from tkinter import messagebox

try:
    from main_os import Theme
except ImportError:                      # 单独跑时用同一套配色
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

# ---------------- 节奏参数（单位：tick，1 tick = TICK_MS 毫秒） ----------------
TICK_MS = 50
SUN_INTERVAL = 140          # 每 7 秒天上掉一朵阳光
SUNFLOWER_INTERVAL = 160    # 向日葵每 8 秒产一朵
WAVE_INTERVAL = 380         # 两波之间约 19 秒
EAT_TICKS = 8               # 僵尸每 0.4 秒咬一口
SHOOT_INTERVAL = 40         # 豌豆射手每 2 秒一发
CHERRY_FUSE = 30            # 樱桃 1.5 秒后爆炸
PEA_SPEED = 7
PEA_DAMAGE = 25
ICE_DAMAGE = 18
SLOW_TICKS = 300            # 寒冰减速持续 15 秒

PLANTS = {
    "sunflower": {"name": "向日葵", "icon": "🌻", "cost": 50, "hp": 30,
                  "color": "#FFD700", "desc": "定时产出阳光"},
    "peashooter": {"name": "豌豆射手", "icon": "🌱", "cost": 100, "hp": 40,
                   "color": "#2ECC71", "desc": "向前发射豌豆"},
    "ice": {"name": "寒冰射手", "icon": "❄️", "cost": 150, "hp": 40,
            "color": "#66D9FF", "desc": "豌豆附带减速"},
    "wall": {"name": "坚果墙", "icon": "🥜", "cost": 75, "hp": 240,
             "color": "#D2A679", "desc": "高血量肉盾"},
    "cherry": {"name": "樱桃炸弹", "icon": "🍒", "cost": 200, "hp": 1,
               "color": "#E74C3C", "desc": "放下即爆，清一圈僵尸"},
}
PLANT_ORDER = ("sunflower", "peashooter", "ice", "wall", "cherry")

ZOMBIES = {
    "normal": {"icon": "🧟", "hp": 100, "speed": 1.5, "damage": 12, "name": "普通僵尸"},
    "fast": {"icon": "🏃", "hp": 80, "speed": 2.6, "damage": 10, "name": "快速僵尸"},
    "bucket": {"icon": "🪣", "hp": 280, "speed": 1.2, "damage": 18, "name": "铁桶僵尸"},
}

# 每关解锁一种新植物：第 1 关只有豌豆射手，越往后越多
LEVELS = [
    {"waves": [1], "hp": 1.0, "speed": 0.9, "types": ["normal"],
     "plants": ["peashooter"], "sun": 100},
    {"waves": [2, 3], "hp": 1.0, "speed": 1.0, "types": ["normal"],
     "plants": ["peashooter", "sunflower"], "sun": 150},
    {"waves": [3, 4, 4], "hp": 1.05, "speed": 1.0,
     "types": ["normal", "fast"],
     "plants": ["peashooter", "sunflower", "wall"], "sun": 160},
    {"waves": [3, 4, 4, 5], "hp": 1.15, "speed": 1.05,
     "types": ["normal", "fast"],
     "plants": ["peashooter", "sunflower", "wall", "ice"], "sun": 170},
    {"waves": [4, 4, 5, 5], "hp": 1.3, "speed": 1.1,
     "types": ["normal", "fast", "bucket"],
     "plants": ["peashooter", "sunflower", "wall", "ice", "cherry"],
     "sun": 180},
]


class PlantVsZombieGame:
    COLS, ROWS = 9, 5
    CELL_W, CELL_H = 80, 90
    OFF_X, OFF_Y = 100, 50

    def __init__(self, main_app, parent):
        self.main_app = main_app
        self.parent = parent

        self.running = True
        self.afters = []
        self.tick = 0
        self.round_on = False

        self.settings = dict(self._default_settings())

        self.plants = []
        self.zombies = []
        self.suns = []
        self.projectiles = []

        self.win = main_app.register_window(tk.Toplevel(parent))
        self.win.title("🌻 植物大战僵尸")
        self.win.geometry("900x600")
        self.win.configure(bg=Theme.BG_MAIN)
        self.win.resizable(False, False)

        self.sun_var = tk.StringVar(value="☀️ 150")
        self.info_var = tk.StringVar(value="第 1 关")
        self.status_var = tk.StringVar(value="把卡片拖到草坪上种植")

        self.cards = {}
        self.drag = {"on": False, "plant": None, "ghost": None}

        self._build_ui()
        self._start_round()
        self._loop()

    # ====================== 基础 ======================
    @staticmethod
    def _default_settings():
        return {"level": 0, "sun": 150, "sun_timer": 0, "wave_timer": 0,
                "wave_queue": [], "wave_index": 0, "total_waves": 0}

    def _later(self, ms, fn):
        if not self.running:
            return None
        aid = self.win.after(ms, fn)
        self.afters.append(aid)
        return aid

    def close(self):
        self.running = False
        for aid in self.afters:
            try:
                self.win.after_cancel(aid)
            except Exception:
                pass
        self.afters.clear()
        handler = getattr(self.win, "_on_close", None)
        try:
            if callable(handler):
                handler()
            else:
                self.win.destroy()
        except Exception:
            pass

    # ====================== 界面 ======================
    def _build_ui(self):
        top = tk.Frame(self.win, bg=Theme.BG_PANEL, height=78)
        top.pack(fill=tk.X)
        top.pack_propagate(False)

        left = tk.Frame(top, bg=Theme.BG_PANEL)
        left.pack(side=tk.LEFT, padx=(14, 4), pady=8)
        tk.Label(left, textvariable=self.sun_var, font=("微软雅黑", 15, "bold"),
                 bg=Theme.BG_PANEL, fg=Theme.GOLD).pack(anchor="w")
        tk.Label(left, textvariable=self.info_var, font=("微软雅黑", 9),
                 bg=Theme.BG_PANEL, fg=Theme.TEXT_DIM).pack(anchor="w")

        self.card_row = tk.Frame(top, bg=Theme.BG_PANEL)
        self.card_row.pack(side=tk.LEFT, padx=8, pady=6)
        self._refresh_cards()

        self.canvas = tk.Canvas(self.win, width=900, height=500, bg="#4CAF50",
                                highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        bar = tk.Frame(self.win, bg=Theme.BG_CARD, height=26)
        bar.pack(fill=tk.X)
        bar.pack_propagate(False)
        tk.Label(bar, textvariable=self.status_var, font=("微软雅黑", 9),
                 bg=Theme.BG_CARD, fg=Theme.TEXT_DIM).pack(side=tk.LEFT, padx=12)
        tk.Label(bar, text="拖动卡片到草坪种植 · 点阳光收集", font=("微软雅黑", 9),
                 bg=Theme.BG_CARD, fg=Theme.TEXT_DIM).pack(side=tk.RIGHT, padx=12)

    def _unlocked_plants(self):
        """本关允许种哪些植物（按卡片固定顺序返回）"""
        allowed = self._level_cfg().get("plants")
        if allowed is None:
            return list(PLANT_ORDER)
        return [k for k in PLANT_ORDER if k in allowed]

    def _unlock_level(self, key):
        """这种植物在第几关解锁"""
        for i, lv in enumerate(LEVELS):
            if key in lv.get("plants", []):
                return i + 1
        return len(LEVELS) + 1

    def _refresh_cards(self):
        """重画卡片槽：没解锁的植物显示成灰锁"""
        for w in self.card_row.winfo_children():
            w.destroy()
        self.cards = {}
        for key in self._unlocked_plants():
            self.cards[key] = self._make_card(self.card_row, key)

    def _make_card(self, parent, key):
        info = PLANTS[key]
        locked = key not in self._unlocked_plants()
        bg = "#232336" if locked else Theme.BG_CARD
        fg = "#5a5a70" if locked else Theme.TEXT
        tip = "arrow" if locked else "hand2"
        card = tk.Frame(parent, bg=bg, cursor=tip, highlightthickness=2,
                        highlightbackground="#2b2b44" if locked else info["color"])
        card.pack(side=tk.LEFT, padx=3)

        icon = tk.Label(card, text="🔒" if locked else info["icon"],
                        font=("Segoe UI Emoji", 15), bg=bg, fg=fg, cursor=tip)
        icon.pack(pady=(4, 0))
        name = tk.Label(card, text=info["name"], font=("微软雅黑", 7),
                        bg=bg, fg=fg, cursor=tip)
        name.pack()
        price = tk.Label(card, text="未解锁" if locked else f"{info['cost']}☀️",
                         font=("微软雅黑", 7), bg=bg,
                         fg=fg if locked else Theme.GOLD, cursor=tip)
        price.pack(pady=(0, 4))

        if locked:
            for wg in (card, icon, name, price):
                wg.bind("<Button-1>", lambda e, k=key: self._flash_status(
                    f"{PLANTS[k]['name']}要在第 {self._unlock_level(k)} 关解锁"))
        else:
            for wg in (card, icon, name, price):
                wg.bind("<ButtonPress-1>", lambda e, k=key: self._drag_start(e, k))
                wg.bind("<B1-Motion>", self._drag_move)
                wg.bind("<ButtonRelease-1>", self._drag_end)
        card.price_label = price
        return card

    def _draw_grid(self):
        self.canvas.delete("all")
        for r in range(self.ROWS):
            for c in range(self.COLS):
                x1 = self.OFF_X + c * self.CELL_W
                y1 = self.OFF_Y + r * self.CELL_H
                fill = "#5CD65C" if (r + c) % 2 == 0 else "#4CAF50"
                self.canvas.create_rectangle(x1, y1, x1 + self.CELL_W,
                                             y1 + self.CELL_H,
                                             fill=fill, outline="#388E3C")

    # ====================== 拖拽种植 ======================
    def _to_canvas(self, event):
        return (event.x_root - self.canvas.winfo_rootx(),
                event.y_root - self.canvas.winfo_rooty())

    def _drag_start(self, event, key):
        if not self.running:
            return
        if key not in self._unlocked_plants():
            self._flash_status(f"{PLANTS[key]['name']}还没解锁")
            return
        self.drag["on"] = True
        self.drag["plant"] = key
        x, y = self._to_canvas(event)
        try:
            self.canvas.delete(self.drag["ghost"])
        except Exception:
            pass
        self.drag["ghost"] = self.canvas.create_text(
            x, y, text=PLANTS[key]["icon"], font=("Segoe UI Emoji", 28),
            tags=("ghost",))

    def _drag_move(self, event):
        if not self.drag["on"] or self.drag["ghost"] is None:
            return
        x, y = self._to_canvas(event)
        try:
            self.canvas.coords(self.drag["ghost"], x, y)
        except Exception:
            pass

    def _drag_end(self, event):
        if not self.drag["on"]:
            return
        self.drag["on"] = False
        key = self.drag["plant"]
        self.drag["plant"] = None
        try:
            self.canvas.delete(self.drag["ghost"])
        except Exception:
            pass
        self.drag["ghost"] = None

        x, y = self._to_canvas(event)
        if x < self.OFF_X or y < self.OFF_Y:
            return
        c = int((x - self.OFF_X) // self.CELL_W)
        r = int((y - self.OFF_Y) // self.CELL_H)
        if not (0 <= r < self.ROWS and 0 <= c < self.COLS):
            return
        self._plant(r, c, key)

    # ====================== 种植 ======================
    def _cell_center(self, r, c):
        return (self.OFF_X + c * self.CELL_W + self.CELL_W / 2,
                self.OFF_Y + r * self.CELL_H + self.CELL_H / 2)

    def _plant(self, r, c, key):
        if not self.round_on:
            return
        if key not in self._unlocked_plants():
            self._flash_status(f"{PLANTS[key]['name']}还没解锁")
            return
        if any(p["row"] == r and p["col"] == c for p in self.plants):
            self._flash_status("这一格已经有植物了")
            return
        info = PLANTS[key]
        if self.settings["sun"] < info["cost"]:
            self._flash_status("阳光不够，先收集金色阳光")
            return

        self.settings["sun"] -= info["cost"]
        x, y = self._cell_center(r, c)
        cid = self.canvas.create_text(x, y, text=info["icon"],
                                      font=("Segoe UI Emoji", 32))
        self.plants.append({
            "type": key, "row": r, "col": c, "cid": cid,
            "hp": info["hp"], "max_hp": info["hp"],
            "born": self.tick, "last": self.tick,
        })
        self._update_sun_label()

    def _remove_plant(self, plant):
        if plant in self.plants:
            self.plants.remove(plant)
        try:
            self.canvas.delete(plant["cid"])
        except Exception:
            pass

    # ====================== 阳光 ======================
    def _drop_sun(self, x, y):
        sid = self.canvas.create_oval(x - 20, y - 20, x + 20, y + 20,
                                      fill="#FFD700", outline="#FF8C00",
                                      tags=("sun_obj",))
        self.canvas.tag_bind(sid, "<Button-1>",
                             lambda e, s=sid: self._collect_sun(s))
        self.suns.append({"cid": sid, "born": self.tick})

    def _collect_sun(self, cid):
        self.settings["sun"] += 25
        self._update_sun_label()
        try:
            self.canvas.delete(cid)
        except Exception:
            pass
        self.suns = [s for s in self.suns if s["cid"] != cid]

    def _update_sun_label(self):
        self.sun_var.set(f"☀️ {self.settings['sun']}")

    # ====================== 僵尸 ======================
    def _level_cfg(self):
        lv = self.settings["level"]
        if lv < len(LEVELS):
            return dict(LEVELS[lv], extra=0)
        extra = lv - len(LEVELS) + 1
        return {"waves": [5 + extra + i for i in range(5)],
                "hp": 1.3 + extra * 0.25,
                "speed": 1.1 + extra * 0.08,
                "types": ["normal", "fast", "bucket"],
                "plants": list(PLANT_ORDER), "sun": 180,
                "extra": extra}

    def _spawn_wave(self, count):
        cfg = self._level_cfg()
        for i in range(count):
            kind = random.choice(cfg["types"])
            base = ZOMBIES[kind]
            r = random.randint(0, self.ROWS - 1)
            y = self.OFF_Y + r * self.CELL_H + self.CELL_H / 2
            x = 890 + i * random.randint(15, 55)
            zid = self.canvas.create_text(x, y, text=base["icon"],
                                          font=("Segoe UI Emoji", 38),
                                          tags=("zombie",))
            self.zombies.append({
                "id": zid, "row": r, "kind": kind,
                "hp": base["hp"] * cfg["hp"],
                "damage": base["damage"],
                "speed": base["speed"] * cfg["speed"],
                "eat": 0, "slow_until": 0,
            })

    def _zombie_x(self, z):
        coords = self.canvas.coords(z["id"])
        return coords[0] if coords else None

    def _plant_under_zombie(self, row, x):
        """僵尸前面（同一行、紧贴左侧）的那株植物"""
        best = None
        for p in self.plants:
            if p["row"] != row:
                continue
            px = self.OFF_X + p["col"] * self.CELL_W + self.CELL_W / 2
            if 0 < x - px <= 48:
                if best is None or px > self.OFF_X + best["col"] * self.CELL_W:
                    best = p
        return best

    def _update_zombies(self):
        for z in list(self.zombies):
            x = self._zombie_x(z)
            if x is None:
                self.zombies.remove(z)
                continue

            target = self._plant_under_zombie(z["row"], x)
            if target:
                z["eat"] += 1
                if z["eat"] >= EAT_TICKS:
                    z["eat"] = 0
                    target["hp"] -= z["damage"]
                    self._flash_plant(target)
                    if target["hp"] <= 0:
                        self._remove_plant(target)
                continue

            z["eat"] = 0
            step = z["speed"]
            if self.tick < z.get("slow_until", 0):
                step *= 0.45
            self.canvas.move(z["id"], -step, 0)
            nx = self._zombie_x(z)
            if nx is not None and nx < self.OFF_X - 12:
                self._restart_level("🧟 僵尸吃掉了你的脑子！")
                return

    def _flash_plant(self, plant):
        """被啃的时候变红一下，方便看出它在掉血"""
        try:
            self.canvas.itemconfig(plant["cid"], fill="#FF5252")
            self._later(120, lambda c=plant["cid"]:
                        self._restore_plant_color(c))
        except Exception:
            pass

    def _restore_plant_color(self, cid):
        for p in self.plants:
            if p["cid"] == cid:
                try:
                    self.canvas.itemconfig(cid, fill="")
                except Exception:
                    pass

    # ====================== 植物行为 ======================
    def _zombie_ahead(self, plant):
        px = self.OFF_X + plant["col"] * self.CELL_W + self.CELL_W / 2
        best = None
        for z in self.zombies:
            if z["row"] != plant["row"]:
                continue
            x = self._zombie_x(z)
            if x is None or x <= px:
                continue
            if best is None or x < self._zombie_x(best):
                best = z
        return best

    def _update_plants(self):
        for p in list(self.plants):
            kind = p["type"]
            if kind == "sunflower":
                if self.tick - p["last"] >= SUNFLOWER_INTERVAL:
                    p["last"] = self.tick
                    x, y = self._cell_center(p["row"], p["col"])
                    self._drop_sun(x, y + 20)
            elif kind in ("peashooter", "ice"):
                if self._zombie_ahead(p) and self.tick - p["last"] >= SHOOT_INTERVAL:
                    p["last"] = self.tick
                    self._shoot(p, kind)
            elif kind == "cherry":
                if self.tick - p["born"] >= CHERRY_FUSE:
                    self._explode(p)

    def _shoot(self, plant, kind):
        x, y = self._cell_center(plant["row"], plant["col"])
        px = x + 26
        pid = self.canvas.create_oval(px, y - 6, px + 14, y + 6,
                                      fill="#00FF00" if kind == "peashooter" else "#7FE7FF",
                                      tags=("pea",))
        self.projectiles.append({"id": pid, "row": plant["row"], "kind": kind})

    def _explode(self, plant):
        cx, cy = self._cell_center(plant["row"], plant["col"])
        x1, y1 = cx - self.CELL_W, cy - self.CELL_H
        x2, y2 = cx + self.CELL_W, cy + self.CELL_H
        boom = self.canvas.create_text(cx, cy, text="💥",
                                       font=("Segoe UI Emoji", 54))
        self._later(400, lambda: self._safe_delete(boom))
        for z in list(self.zombies):
            zx = self._zombie_x(z)
            zy = self.canvas.coords(z["id"])
            if zx is None or not zy:
                continue
            if x1 <= zx <= x2 and y1 <= zy[1] <= y2:
                self._kill_zombie(z)
        self._remove_plant(plant)

    def _safe_delete(self, cid):
        try:
            self.canvas.delete(cid)
        except Exception:
            pass

    def _kill_zombie(self, z):
        try:
            self.canvas.delete(z["id"])
        except Exception:
            pass
        if z in self.zombies:
            self.zombies.remove(z)

    def _update_projectiles(self):
        for pea in list(self.projectiles):
            coords = self.canvas.coords(pea["id"])
            if not coords:
                self.projectiles.remove(pea)
                continue
            self.canvas.move(pea["id"], PEA_SPEED, 0)
            pc = self.canvas.coords(pea["id"])
            if not pc:
                self.projectiles.remove(pea)
                continue
            if pc[0] > 905:
                self._safe_delete(pea["id"])
                self.projectiles.remove(pea)
                continue
            for z in list(self.zombies):
                zc = self.canvas.coords(z["id"])
                if not zc or z["row"] != pea["row"]:
                    continue
                if abs(zc[0] - pc[0]) < 34:
                    dmg = PEA_DAMAGE if pea["kind"] == "peashooter" else ICE_DAMAGE
                    if pea["kind"] == "ice":
                        z["slow_until"] = self.tick + SLOW_TICKS
                    z["hp"] -= dmg
                    self._safe_delete(pea["id"])
                    if pea in self.projectiles:
                        self.projectiles.remove(pea)
                    if z["hp"] <= 0:
                        self._kill_zombie(z)
                    break

    def _update_suns(self):
        self.settings["sun_timer"] += 1
        if self.settings["sun_timer"] >= SUN_INTERVAL:
            self.settings["sun_timer"] = 0
            x = random.randint(self.OFF_X + 30,
                               self.OFF_X + self.COLS * self.CELL_W - 30)
            y = random.randint(self.OFF_Y + 30,
                               self.OFF_Y + self.ROWS * self.CELL_H - 30)
            self._drop_sun(x, y)
        for s in list(self.suns):
            if self.tick - s["born"] >= 240:
                self._safe_delete(s["cid"])
                self.suns.remove(s)

    # ====================== 波次与关卡 ======================
    def _update_waves(self):
        if not self.round_on:
            return
        if self.settings["wave_queue"]:
            self.settings["wave_timer"] -= 1
            if self.settings["wave_timer"] <= 0:
                count = self.settings["wave_queue"].pop(0)
                self.settings["wave_index"] += 1
                self._spawn_wave(count)
                self.settings["wave_timer"] = WAVE_INTERVAL
        elif not self.zombies:
            self._level_clear()

    def _update_info(self):
        lv = self.settings["level"]
        name = f"第 {lv + 1} 关" if lv < len(LEVELS) else f"无尽 {lv - len(LEVELS) + 1}"
        wave = self.settings["wave_index"]
        total = self.settings["total_waves"]
        self.info_var.set(f"{name} · 第 {min(wave, total)}/{total} 波 · 僵尸 {len(self.zombies)}")

    def _start_round(self):
        cfg = self._level_cfg()
        self._draw_grid()
        self.plants.clear()
        self.zombies.clear()
        self.suns.clear()
        self.projectiles.clear()
        self.drag["on"] = False
        self.drag["plant"] = None
        self.drag["ghost"] = None

        self.settings["sun"] = cfg.get("sun", 180)
        self.settings["sun_timer"] = 0
        self.settings["wave_queue"] = list(cfg["waves"])
        self.settings["total_waves"] = len(self.settings["wave_queue"])
        self.settings["wave_index"] = 0
        self.settings["wave_timer"] = 110
        self.round_on = True
        self._refresh_cards()
        self._update_sun_label()
        self._update_info()
        self.status_var.set("拖动卡片到草坪上种植")

    def _restart_level(self, reason=""):
        self.round_on = False
        if reason:
            messagebox.showerror("游戏结束", reason + "\n\n本关重新开始。", parent=self.win)
        self._start_round()

    def _level_clear(self):
        self.round_on = False
        lv = self.settings["level"]
        if lv < len(LEVELS):
            title = "🎉 过关！"
            msg = f"第 {lv + 1} 关通过，进入第 {lv + 2} 关。"
        else:
            title = "🎉 又撑过一关！"
            msg = "无尽模式继续，难度递增。"
        messagebox.showinfo(title, msg, parent=self.win)
        self.settings["level"] += 1
        self._start_round()

    def _flash_status(self, text):
        self.status_var.set(text)
        self._later(1500, lambda: self.status_var.set("拖动卡片到草坪上种植"))

    # ====================== 主循环 ======================
    def _loop(self):
        if not self.running:
            return
        self.tick += 1
        if self.round_on:
            self._update_waves()
            if self.round_on:
                self._update_suns()
                self._update_plants()
                self._update_zombies()
                self._update_projectiles()
                self._update_info()
        if self.running:
            self._later(TICK_MS, self._loop)


def open_game(main_app, parent):
    """给 app_store 用：打开一局植物大战僵尸"""
    return PlantVsZombieGame(main_app, parent)
