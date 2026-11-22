"""MiniOS 内置应用集合（记事本 / 计算器 / 画图 / 游戏 / 文件管理器 / 任务管理器）。

这些窗口原本都写在 main_os.py 的 MiniOSGUI 里，拆出来是为了让主程序只留
窗口管理、桌面外壳和系统级功能。通过 AppMixin 继承进 MiniOSGUI，调用方式不变。
"""

import os
import re
import random
import datetime
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog, scrolledtext, colorchooser, filedialog

from minios_ui import Theme, HoverButton


class AppMixin:
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
                with open(os.path.join(self.DISK_PATH, fn), "w", encoding="utf-8") as f:
                    f.write(text.get("1.0", tk.END))
                win._modified = False
                title_var.set(fn)
                messagebox.showinfo("成功", "文件已保存", parent=win)
            except Exception as e:
                messagebox.showerror("错误", str(e), parent=win)

        def open_doc():
            try: flist = os.listdir(self.DISK_PATH)
            except Exception: flist = []
            if not flist:
                messagebox.showinfo("提示", "暂无文件", parent=win)
                return
            sel = simpledialog.askstring("打开文件", "现有文件：\n" + "\n".join(flist) + "\n\n输入文件名", parent=win)
            if sel and sel in flist:
                try:
                    cur_file.set(sel)
                    title_var.set(sel)
                    with open(os.path.join(self.DISK_PATH, sel), "r", encoding="utf-8") as f:
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
                for f in os.listdir(self.DISK_PATH):
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
            if os.path.exists(os.path.join(self.DISK_PATH, n)):
                messagebox.showwarning("提示", f"{n} 已存在", parent=win)
                return
            try:
                open(os.path.join(self.DISK_PATH, n), "w", encoding="utf-8").close()
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
            if os.path.exists(os.path.join(self.DISK_PATH, new)):
                messagebox.showwarning("提示", f"{new} 已存在", parent=win)
                return
            try:
                os.rename(os.path.join(self.DISK_PATH, old),
                          os.path.join(self.DISK_PATH, new))
                refresh()
            except Exception as e:
                messagebox.showerror("错误", str(e), parent=win)

        def del_file():
            name = get_selected()
            if not name: return
            if messagebox.askyesno("删除", f"确认删除 {name}？", parent=win):
                try:
                    os.remove(os.path.join(self.DISK_PATH, name))
                    refresh()
                except Exception as e:
                    messagebox.showerror("错误", str(e), parent=win)

        def open_file():
            name = get_selected()
            if not name: return
            fp = os.path.join(self.DISK_PATH, name)

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
                    if title != self.SYS_NAME:
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
