# -*- coding: utf-8 -*-
"""MiniOS 天气预报应用（数据源 Open-Meteo，免费、无需 key）

作为一个独立的 mixin 存在，主程序只需在类继承里加一个 WeatherMixin，
不用往 apps_basic.py 里再堆代码。数据缓存 30 分钟，避免每次开窗都发请求。
"""

import datetime
import json
import os
import threading
import time
import urllib.parse
import urllib.request
import tkinter as tk

from minios_ui import Theme, HoverButton

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_PATH = os.path.join(BASE_DIR, "weather_cache.json")
CACHE_TTL = 30 * 60          # 30 分钟
DEFAULT_CITY = "北京"

# WMO 天气代码 -> (图标, 中文)
WMO = {
    0: ("☀️", "晴"), 1: ("🌤️", "晴间多云"), 2: ("⛅", "多云"), 3: ("☁️", "阴"),
    45: ("🌫️", "雾"), 48: ("🌫️", "雾凇"),
    51: ("🌦️", "细毛雨"), 53: ("🌦️", "毛雨"), 55: ("🌧️", "大毛雨"),
    56: ("🌧️", "冻毛雨"), 57: ("🌧️", "强冻毛雨"),
    61: ("🌦️", "小雨"), 63: ("🌧️", "中雨"), 65: ("🌧️", "大雨"),
    66: ("🌧️", "冻雨"), 67: ("🌧️", "强冻雨"),
    71: ("🌨️", "小雪"), 73: ("🌨️", "中雪"), 75: ("❄️", "大雪"), 77: ("❄️", "米雪"),
    80: ("🌦️", "阵雨"), 81: ("🌧️", "强阵雨"), 82: ("⛈️", "暴雨"),
    85: ("🌨️", "阵雪"), 86: ("❄️", "强阵雪"),
    95: ("⛈️", "雷阵雨"), 96: ("⛈️", "雷雨冰雹"), 99: ("⛈️", "强雷雨冰雹"),
}


def wmo(code):
    try:
        return WMO.get(int(code), ("🌡️", "未知"))
    except (TypeError, ValueError):
        return ("🌡️", "未知")


def _get_json(url, timeout=12):
    req = urllib.request.Request(url, headers={"User-Agent": "MiniOS-Weather/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def geocode(city):
    """城市名 -> 经纬度。支持中文名。"""
    q = urllib.parse.quote(city.strip())
    data = _get_json(
        "https://geocoding-api.open-meteo.com/v1/search"
        f"?name={q}&count=1&language=zh&format=json")
    results = data.get("results") or []
    if not results:
        raise RuntimeError(f"找不到城市「{city}」，换个写法试试")
    r = results[0]
    region = " ".join(str(x) for x in (r.get("admin1"), r.get("country")) if x)
    return {
        "name": r.get("name") or city,
        "region": region,
        "lat": float(r["latitude"]),
        "lon": float(r["longitude"]),
    }


def fetch_forecast(lat, lon, days=7):
    url = (
        f"https://api.open-meteo.com/v1/forecast?latitude={lat:.4f}&longitude={lon:.4f}"
        "&current=temperature_2m,relative_humidity_2m,apparent_temperature,"
        "weather_code,wind_speed_10m"
        f"&daily=weather_code,temperature_2m_max,temperature_2m_min,"
        f"precipitation_probability_max&timezone=auto&forecast_days={days}"
    )
    return _get_json(url, timeout=15)


def load_cache():
    try:
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_cache(data):
    try:
        with open(CACHE_PATH, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


class WeatherMixin:
    """主程序通过继承获得 self.weather()"""

    def weather(self):
        win = self.register_window(tk.Toplevel(self.root))
        win.title("🌤️ 天气预报")
        win.geometry("540x660")
        win.configure(bg=Theme.BG_MAIN)
        win.resizable(False, False)

        cache = load_cache()
        city_name = (cache.get("city") or {}).get("name") or DEFAULT_CITY

        # ---------- 头部 ----------
        header = tk.Frame(win, bg=Theme.BG_CARD, height=56)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text="🌤️ 天气预报", font=("微软雅黑", 16, "bold"),
                 bg=Theme.BG_CARD, fg=Theme.TEXT).pack(side=tk.LEFT, padx=18, pady=12)
        tk.Label(header, text="数据源 Open-Meteo", font=("微软雅黑", 9),
                 bg=Theme.BG_CARD, fg=Theme.TEXT_DIM).pack(side=tk.RIGHT, padx=18)

        body = tk.Frame(win, bg=Theme.BG_MAIN)
        body.pack(fill=tk.BOTH, expand=True, padx=18, pady=12)

        # ---------- 城市输入 ----------
        row = tk.Frame(body, bg=Theme.BG_MAIN)
        row.pack(fill=tk.X)
        city_var = tk.StringVar(value=city_name)
        entry = tk.Entry(row, textvariable=city_var, font=("微软雅黑", 11),
                         bg=Theme.BG_PANEL, fg=Theme.TEXT,
                         insertbackground=Theme.ACCENT, relief=tk.FLAT, bd=0)
        entry.pack(side=tk.LEFT, fill=tk.X, expand=True, ipady=7)
        query_btn = HoverButton(row, text="🌍 查询", color=Theme.BTN_PRIMARY, width=8)
        query_btn.pack(side=tk.LEFT, padx=(8, 0))

        # ---------- 当前天气卡 ----------
        card = tk.Frame(body, bg=Theme.BG_PANEL)
        card.pack(fill=tk.X, pady=(12, 0))
        card_inner = tk.Frame(card, bg=Theme.BG_PANEL)
        card_inner.pack(fill=tk.X, padx=16, pady=14)

        icon_lbl = tk.Label(card_inner, text="🌡️", font=("Segoe UI Emoji", 40),
                            bg=Theme.BG_PANEL, fg=Theme.TEXT)
        icon_lbl.pack(side=tk.LEFT, padx=(0, 14))

        temp_box = tk.Frame(card_inner, bg=Theme.BG_PANEL)
        temp_box.pack(side=tk.LEFT, fill=tk.X, expand=True)
        temp_var = tk.StringVar(value="--°")
        tk.Label(temp_box, textvariable=temp_var, font=("Segoe UI", 30, "bold"),
                 bg=Theme.BG_PANEL, fg=Theme.ACCENT, anchor="w").pack(fill=tk.X)
        desc_var = tk.StringVar(value="等待数据")
        tk.Label(temp_box, textvariable=desc_var, font=("微软雅黑", 11),
                 bg=Theme.BG_PANEL, fg=Theme.TEXT, anchor="w").pack(fill=tk.X)
        detail_var = tk.StringVar(value="")
        tk.Label(temp_box, textvariable=detail_var, font=("微软雅黑", 9),
                 bg=Theme.BG_PANEL, fg=Theme.TEXT_DIM, anchor="w").pack(fill=tk.X, pady=(4, 0))

        # ---------- 未来几天 ----------
        tk.Label(body, text="未来 7 天", font=("微软雅黑", 9, "bold"),
                 bg=Theme.BG_MAIN, fg=Theme.TEXT_DIM, anchor="w").pack(fill=tk.X, pady=(14, 6))
        days_frame = tk.Frame(body, bg=Theme.BG_PANEL)
        days_frame.pack(fill=tk.BOTH, expand=True)

        status_var = tk.StringVar(value="")
        tk.Label(body, textvariable=status_var, font=("微软雅黑", 8),
                 bg=Theme.BG_MAIN, fg=Theme.TEXT_DIM, anchor="w").pack(fill=tk.X, pady=(8, 0))

        # ---------- 渲染 ----------
        def render(city, data):
            cur = data.get("current") or {}
            code = cur.get("weather_code")
            emoji, text = wmo(code)
            icon_lbl.config(text=emoji)
            t = cur.get("temperature_2m")
            temp_var.set("--°" if t is None else f"{round(float(t))}°")
            desc_var.set(f"{text}　{city.get('name', '')}")
            bits = []
            if cur.get("apparent_temperature") is not None:
                bits.append(f"体感 {round(float(cur['apparent_temperature']))}°")
            if cur.get("relative_humidity_2m") is not None:
                bits.append(f"湿度 {round(float(cur['relative_humidity_2m']))}%")
            if cur.get("wind_speed_10m") is not None:
                bits.append(f"风 {round(float(cur['wind_speed_10m']))} km/h")
            if city.get("region"):
                bits.append(city["region"])
            detail_var.set("　".join(bits))

            for w in days_frame.winfo_children():
                w.destroy()
            daily = data.get("daily") or {}
            times = daily.get("time") or []
            wk = "一二三四五六日"
            for i, day in enumerate(times):
                try:
                    d = datetime.date.fromisoformat(day)
                    left = f"{'周' + wk[d.weekday()]}  {d.month:02d}-{d.day:02d}"
                except Exception:
                    left = str(day)
                de, dt = wmo((daily.get("weather_code") or [])[i] if i < len(daily.get("weather_code") or []) else None)
                hi = (daily.get("temperature_2m_max") or [None])[i]
                lo = (daily.get("temperature_2m_min") or [None])[i]
                rain = (daily.get("precipitation_probability_max") or [None])[i]
                bg = Theme.BG_CARD if i % 2 else Theme.BG_PANEL
                line = tk.Frame(days_frame, bg=bg)
                line.pack(fill=tk.X)
                tk.Label(line, text=left, font=("Consolas", 10), bg=bg,
                         fg=Theme.TEXT_DIM, width=13, anchor="w").pack(side=tk.LEFT, padx=(12, 4), pady=6)
                tk.Label(line, text=de, font=("Segoe UI Emoji", 13), bg=bg,
                         fg=Theme.TEXT, width=3).pack(side=tk.LEFT)
                tk.Label(line, text=dt, font=("微软雅黑", 10), bg=bg,
                         fg=Theme.TEXT, width=9, anchor="w").pack(side=tk.LEFT)
                temp_txt = "--" if hi is None or lo is None else \
                    f"{round(float(lo))}° / {round(float(hi))}°"
                tk.Label(line, text=temp_txt, font=("Consolas", 10, "bold"), bg=bg,
                         fg=Theme.ACCENT, width=11, anchor="e").pack(side=tk.LEFT)
                rain_txt = "" if rain is None else f"💧{round(float(rain))}%"
                tk.Label(line, text=rain_txt, font=("微软雅黑", 9), bg=bg,
                         fg=Theme.TEXT_DIM, width=7, anchor="e").pack(side=tk.RIGHT, padx=(0, 12))

        # ---------- 加载 ----------
        state = {"busy": False, "result": None}

        def poll():
            try:
                if not win.winfo_exists():
                    return
            except Exception:
                return
            if state["result"]:
                kind, payload = state["result"]
                state["result"] = None
                state["busy"] = False
                query_btn.config(state=tk.NORMAL)
                if kind == "ok":
                    city, data = payload
                    render(city, data)
                    status_var.set(
                        "更新于 " + datetime.datetime.now().strftime("%H:%M") +
                        "　缓存 30 分钟，想立刻刷新就再点一次查询")
                else:
                    status_var.set("✗ " + str(payload))
            win.after(150, poll)

        def load(city, force=False):
            if state["busy"]:
                return
            state["busy"] = True
            query_btn.config(state=tk.DISABLED)
            status_var.set(f"正在查询「{city}」…")

            def work():
                try:
                    c = geocode(city)
                    data = fetch_forecast(c["lat"], c["lon"])
                    save_cache({"city": c, "data": data, "ts": time.time()})
                    state["result"] = ("ok", (c, data))
                except Exception as e:
                    state["result"] = ("err", str(e))

            threading.Thread(target=work, daemon=True).start()

        def on_query(event=None):
            city = city_var.get().strip()
            if not city:
                status_var.set("先输入城市名")
                return
            load(city, force=True)

        query_btn.config(command=on_query)
        entry.bind("<Return>", on_query)

        # 先用缓存顶上，缓存超过 30 分钟或没有就后台拉一次
        if cache.get("data") and cache.get("city"):
            render(cache["city"], cache["data"])
            age = time.time() - float(cache.get("ts") or 0)
            if age < CACHE_TTL:
                status_var.set(
                    "缓存来自 " + datetime.datetime.fromtimestamp(
                        float(cache.get("ts") or 0)).strftime("%m-%d %H:%M") +
                    "，点查询可强制刷新")
                win.after(150, poll)
                return win
            status_var.set("缓存已过期，正在刷新…")
        win.after(150, poll)
        win.after(60, lambda: load(city_name, force=True))

        return win
