"""
MiniOS 系统更新模块
------------------------------------------------------------------
从 GitHub 仓库拉取 update.json，比对版本 -> 下载变更文件 -> 备份 -> 替换。
只允许覆盖白名单里的 .py 文件，且必须全部下载成功才动现有代码。

仓库侧需要放两个东西：
    update.json     版本清单（用 tools/make_update.py 生成）
    main_os.py 等    被更新的源文件

设计要点：
- 网络请求全部走标准库 urllib，带超时和重试（国内访问 GitHub 经常半路断）
- 下载先落 .part 临时文件，校验通过才 rename，避免半截文件覆盖源码
- 替换前把旧文件整份复制到 updates/backup/<时间戳>/
- 主程序重启后新代码才生效，所以更新完提示「重启生效」
"""

import base64
import datetime
import hashlib
import json
import os
import queue
import shutil
import threading
import time
import tkinter as tk
from tkinter import messagebox
import urllib.error
import urllib.request

# ---------------- 可配置 ----------------
DEFAULT_REPO = "Pandajunjie/MiniOS"
DEFAULT_BRANCH = "main"
DEFAULT_BASE = "https://raw.githubusercontent.com/{repo}/{branch}/{name}"

MANIFEST_NAME = "update.json"
# 备份/临时/状态目录都锚在程序目录，不随启动目录变
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
BACKUP_ROOT = os.path.join(BASE_DIR, "updates", "backup")
TMP_ROOT = os.path.join(BASE_DIR, "updates", "tmp")
STATE_PATH = os.path.join(BASE_DIR, "updates", "state.json")

# 只允许下发程序目录下的 .py 文件（见 Installer._target）。
# 数据文件（installed_apps.json / settings.json / userdata.txt）永远不会被覆盖。
MAX_FILE_BYTES = 8 * 1024 * 1024      # 单文件 8MB 上限，够用且防止被塞大文件


def base_url(repo=DEFAULT_REPO, branch=DEFAULT_BRANCH):
    """测试时可以指向本地 http 服务，例如 http://127.0.0.1:8000/{name}"""
    override = os.environ.get("MINIOS_UPDATE_BASE")
    if override:
        return override
    # 这里要留着 {name} 给后面拼文件名，所以不能用 str.format
    return DEFAULT_BASE.replace("{repo}", repo).replace("{branch}", branch)


# 国内访问 raw.githubusercontent.com 经常 SSL 握手超时，所以准备多条通道。
# 顺序按实测可达性排：jsDelivr（按 commit 锁定，不会读到 CDN 旧缓存）→ 代理 → 官方 raw。
# {rev} 可以是分支名，也可以是某个 commit sha —— 后者用于回滚到任意历史版本。
JSDELIVR_BASE = "https://cdn.jsdelivr.net/gh/{repo}@{rev}/{name}"
PROXY_REV = "https://ghfast.top/https://raw.githubusercontent.com/{repo}/{rev}/{name}"
RAW_REV = "https://raw.githubusercontent.com/{repo}/{rev}/{name}"
COMMITS_API = "https://api.github.com/repos/{repo}/commits?per_page={limit}&sha={branch}"
CONTENTS_API = "https://api.github.com/repos/{repo}/contents/{path}?ref={rev}"

_NO_REV = object()   # 未解析过的哨兵


def ver_tuple(text):
    """把 'v2.0' / '2.1.3' 变成可比较的元组"""
    parts = []
    for p in str(text or "").strip().lstrip("vV").replace("_", ".").replace("-", ".").split("."):
        digits = "".join(ch for ch in p if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:3])


def sha256_of(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def current_version(root_dir):
    """当前版本优先从 main_os.py 里的 SYS_NAME 读，保证跟界面显示一致"""
    try:
        path = os.path.join(root_dir, "main_os.py")
        with open(path, encoding="utf-8") as f:
            for line in f:
                if line.startswith("SYS_NAME"):
                    text = line.split("=")[-1].strip().strip('"').strip("'")
                    token = text.split()[-1] if text.split() else text
                    return token.lstrip("vV")
    except Exception:
        pass
    return "2.0"


# ==================== 网络层 ====================

class Net:
    def __init__(self, repo=DEFAULT_REPO, branch=DEFAULT_BRANCH, timeout=12, retries=2):
        self.repo = repo
        self.branch = branch
        self.timeout = timeout
        self.retries = retries
        self.base = base_url(repo, branch)
        self.override = bool(os.environ.get("MINIOS_UPDATE_BASE"))
        self._rev = _NO_REV
        self.last_source = None      # 记录最后成功的通道，窗口里能显示

    # ---------- 通道选择 ----------
    def head_rev(self):
        """取分支最新 commit sha，只请求一次。取不到就返回 None（退回按分支名拉）。"""
        if self._rev is not _NO_REV:
            return self._rev
        self._rev = None
        if self.override:
            return None
        try:
            req = urllib.request.Request(
                COMMITS_API.format(repo=self.repo, limit=1, branch=self.branch),
                headers={
                    "User-Agent": "MiniOS-Updater/1.0",
                    "Accept": "application/vnd.github+json",
                },
            )
            with urllib.request.urlopen(req, timeout=8) as resp:
                data = json.loads(resp.read(1 << 20).decode("utf-8"))
            sha = None
            if isinstance(data, list) and data:
                sha = data[0].get("sha")
            elif isinstance(data, dict):
                sha = data.get("sha")
            if isinstance(sha, str) and len(sha) >= 7:
                self._rev = sha
        except Exception:
            pass
        return self._rev

    def urls_for(self, name, rev=None):
        """该文件的候选地址，按可达性排序。rev 给定时锁定到那个 commit。"""
        if self.override:
            base = self.base
            return [base.format(name=name) if "{name}" in base else base + name]
        tag = rev or self.head_rev() or self.branch
        return [
            JSDELIVR_BASE.format(repo=self.repo, rev=tag, name=name),
            PROXY_REV.format(repo=self.repo, rev=tag, name=name),
            RAW_REV.format(repo=self.repo, rev=tag, name=name),
        ]

    # ---------- 下载 ----------
    def get_bytes(self, name, rev=None):
        last = None
        for url in self.urls_for(name, rev):
            for attempt in range(self.retries + 1):
                try:
                    req = urllib.request.Request(
                        url,
                        headers={
                            "User-Agent": "MiniOS-Updater/1.0",
                            "Cache-Control": "no-cache",
                        },
                    )
                    with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                        data = resp.read(MAX_FILE_BYTES + 1)
                    if len(data) > MAX_FILE_BYTES:
                        raise ValueError(f"{name} 超过 {MAX_FILE_BYTES // 1024 // 1024}MB 上限")
                    self.last_source = url
                    return data
                except urllib.error.HTTPError as e:
                    last = e
                    if e.code in (401, 403, 404):
                        # 这个通道没有该文件，换下一条通道试试
                        last = RuntimeError(
                            f"{name} 返回 {e.code}：仓库不存在、未公开，或文件名写错（{url}）"
                        )
                        break
                    time.sleep(0.6 * (attempt + 1))
                except Exception as e:
                    last = e
                    time.sleep(0.6 * (attempt + 1))
        raise RuntimeError(f"下载 {name} 失败（已尝试所有通道）：{last}")

    def get_manifest(self):
        raw = self.get_bytes(MANIFEST_NAME)
        try:
            data = json.loads(raw.decode("utf-8-sig"))
        except Exception as e:
            raise RuntimeError(f"update.json 不是合法 JSON：{e}")
        if not isinstance(data.get("files"), (dict, list)):
            raise RuntimeError("update.json 里缺少 files 字段")
        return data


# ==================== 安装层 ====================

class Installer:
    """下载 -> 校验 -> 备份 -> 替换，全流程围绕 root_dir（默认程序目录）"""

    def __init__(self, root_dir):
        self.root = os.path.abspath(root_dir)
        # 注意：这里必须用相对片段再 join self.root，
        # 不能 join 上面那几个「锚在程序目录」的绝对常量 ——
        # os.path.join("D:\\x", "D:\\y\\z") 会直接丢掉第一个参数，
        # 结果就是不管传什么 root_dir，备份都写到真实程序目录去（踩过）。
        self.tmp = os.path.join(self.root, "updates", "tmp")
        self.backup_root = os.path.join(self.root, "updates", "backup")
        self.state_path = os.path.join(self.root, "updates", "state.json")

    def _target(self, name):
        """只放行程序目录下的 .py 文件：数据文件（.json/.txt）永远不碰。

        以前这里比对写死的小名单，一改结构（比如把 main_os 拆成几个模块）
        旧客户端就会因为「清单里有不认识的文件」整次中止。改成规则校验后，
        以后怎么拆分模块都不用再改更新器。
        """
        if not isinstance(name, str) or not name.strip():
            raise RuntimeError("清单里的文件名不合法")
        if os.path.basename(name) != name:
            raise RuntimeError(f"文件名不能带路径：{name}")
        if not name.endswith(".py") or name.startswith("_"):
            raise RuntimeError(f"只允许下发 .py 文件：{name}")
        return os.path.join(self.root, name)

    def download_all(self, manifest, net, progress=None, rev=None):
        """先把所有文件下到 tmp，任何一个失败就整体中止（不动现有代码）。
        rev 给定时锁定到某个 commit（回滚历史版本用）。"""
        os.makedirs(self.tmp, exist_ok=True)
        files = manifest["files"]
        items = list(files.items()) if isinstance(files, dict) else [(f["name"], f) for f in files]
        results = []
        total = len(items)
        for idx, (name, meta) in enumerate(items, start=1):
            target = self._target(name)
            part = os.path.join(self.tmp, name + ".part")
            data = net.get_bytes(name, rev)
            with open(part, "wb") as f:
                f.write(data)

            expect = (meta or {}).get("sha256") if isinstance(meta, dict) else None
            if expect:
                got = sha256_of(part)
                if got.lower() != str(expect).lower():
                    os.remove(part)
                    raise RuntimeError(f"{name} 校验失败：哈希不匹配（文件可能被截断）")
            results.append((name, part, len(data), target))
            if progress:
                progress(idx, total, name, len(data))
        return results

    def backup(self, names):
        stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        bdir = os.path.join(self.backup_root, stamp)
        os.makedirs(bdir, exist_ok=True)
        saved = []
        for name in names:
            src = self._target(name)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(bdir, name))
                saved.append(name)
        return bdir, saved

    def apply(self, downloaded):
        names = [n for n, _, _, _ in downloaded]
        bdir, saved = self.backup(names)
        for name, part, _, target in downloaded:
            shutil.move(part, target)
        return bdir, saved

    def write_state(self, manifest, backup_dir):
        os.makedirs(os.path.dirname(self.state_path), exist_ok=True)
        # 备份目录通常在程序目录下，存相对路径便于整体搬迁；
        # 但万一不在同一个盘（relpath 会抛 ValueError），就老实存绝对路径。
        try:
            backup_ref = os.path.relpath(backup_dir, self.root)
        except ValueError:
            backup_ref = os.path.abspath(backup_dir)
        state = {
            "pending_restart": True,
            "installed_version": manifest.get("version", ""),
            "installed_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "backup_dir": backup_ref,
            "files": sorted(manifest["files"].keys()
                            if isinstance(manifest["files"], dict)
                            else [f["name"] for f in manifest["files"]]),
        }
        with open(self.state_path, "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)
        return state

    def read_state(self):
        try:
            with open(self.state_path, encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def latest_backup(self):
        if not os.path.isdir(self.backup_root):
            return None
        dirs = sorted(d for d in os.listdir(self.backup_root)
                      if os.path.isdir(os.path.join(self.backup_root, d)))
        return os.path.join(self.backup_root, dirs[-1]) if dirs else None

    def rollback(self):
        bdir = self.latest_backup()
        if not bdir:
            raise RuntimeError("没有找到任何备份，无法回滚")
        restored = []
        for name in sorted(os.listdir(bdir)):
            # 与 _target 同一套规则：备份里有什么 .py 就恢复什么
            if not name.endswith(".py") or name.startswith("_"):
                continue
            src = os.path.join(bdir, name)
            if not os.path.isfile(src):
                continue
            shutil.copy2(src, self._target(name))
            restored.append(name)
        if not restored:
            raise RuntimeError("最近那份备份里没有可恢复的文件")
        try:
            if os.path.exists(self.state_path):
                os.remove(self.state_path)
        except Exception:
            pass
        return restored, bdir


# ==================== 历史版本 ====================

class History:
    """把 GitHub 的 commit 历史当版本库：一个 commit 就是一个可回滚的版本点。

    不需要在仓库里额外建 versions/ 目录重复存文件 —— commit 本身就是快照，
    按 sha 取文件永远是那个版本的原始内容，不受 CDN 缓存影响。
    """

    def __init__(self, repo=DEFAULT_REPO, branch=DEFAULT_BRANCH, limit=12, net=None,
                 cache_path=None):
        self.repo = repo
        self.branch = branch
        self.limit = max(1, min(int(limit or 12), 30))
        self.net = net or Net()
        self.cache_path = cache_path
        self._cache = None
        self._stamp = None

    # ---------- 本地缓存 ----------
    # 一次列表要打十来个 API 请求（1 次提交列表 + 每个 commit 查一次 update.json），
    # 未登录每小时只有 60 次，所以默认读缓存，只有明确点「刷新」才真去拉。
    def cached_at(self):
        if self._stamp is None:
            self._read_cache()
        return self._stamp

    def _read_cache(self):
        self._stamp = None
        if not self.cache_path or not os.path.isfile(self.cache_path):
            return None
        try:
            with open(self.cache_path, encoding="utf-8") as f:
                data = json.load(f)
            if data.get("repo") != self.repo or data.get("branch") != self.branch:
                return None
            entries = data.get("entries") or []
            if not isinstance(entries, list) or not entries:
                return None
            self._stamp = data.get("fetched_at")
            return entries
        except Exception:
            return None

    def _write_cache(self, entries):
        if not self.cache_path:
            return
        try:
            os.makedirs(os.path.dirname(self.cache_path), exist_ok=True)
            stamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
            with open(self.cache_path, "w", encoding="utf-8") as f:
                json.dump({"repo": self.repo, "branch": self.branch,
                           "fetched_at": stamp, "entries": entries},
                          f, ensure_ascii=False, indent=2)
            self._stamp = stamp
        except Exception:
            pass

    def _api(self, url, timeout=12):
        req = urllib.request.Request(url, headers={
            "User-Agent": "MiniOS-Updater/1.0",
            "Accept": "application/vnd.github+json",
        })
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read(1 << 20).decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 403:
                raise RuntimeError(
                    "GitHub 接口限流了（未登录状态下每小时 60 次）。"
                    "等十几分钟再点刷新，或先用「检查更新」就够了。")
            raise

    def _manifest_at(self, sha):
        try:
            info = self._api(CONTENTS_API.format(repo=self.repo, path=MANIFEST_NAME, rev=sha))
            content = info.get("content")
            if not content:
                return None
            return json.loads(base64.b64decode(content).decode("utf-8-sig"))
        except Exception:
            return None

    def _py_at(self, sha):
        try:
            items = self._api(f"https://api.github.com/repos/{self.repo}/contents/?ref={sha}")
            return {i["name"]: {} for i in items
                    if i.get("type") == "file" and i["name"].endswith(".py")}
        except Exception:
            return {}

    def entries(self, force=False):
        """返回 [{'sha','short','date','message','version','files','notes'}]，新的在前

        默认先看本地缓存；force=True 才真的去打 GitHub 接口并把结果写回缓存。
        """
        if not force:
            if self._cache is not None:
                return self._cache
            cached = self._read_cache()
            if cached:
                self._cache = cached
                return cached
        commits = self._api(COMMITS_API.format(
            repo=self.repo, limit=self.limit, branch=self.branch))
        if isinstance(commits, dict):
            commits = [commits]
        out = []
        for c in commits:
            sha = c.get("sha")
            if not sha:
                continue
            m = self._manifest_at(sha)
            files, notes, ver = None, [], None
            if m and isinstance(m.get("files"), dict) and "main_os.py" in m["files"]:
                files = m["files"]
                ver = m.get("version")
                notes = m.get("notes") or []
            else:
                files = self._py_at(sha)
                if "main_os.py" not in files:
                    continue          # 没有主程序的 commit 不能当版本回滚
            out.append({
                "sha": sha,
                "short": sha[:8],
                "date": (c.get("commit", {}).get("committer", {}) or {}).get("date", ""),
                "message": ((c.get("commit", {}) or {}).get("message") or "").splitlines()[0][:60],
                "version": ver,
                "files": files,
                "notes": notes,
            })
        self._cache = out
        if out:
            self._write_cache(out)
        return out

    def restore(self, entry, installer, net=None, progress=None):
        """把程序换成 entry 这个版本的内容"""
        net = net or self.net
        manifest = {"version": entry.get("version") or entry["short"], "files": entry["files"]}
        got = installer.download_all(manifest, net, progress, rev=entry["sha"])
        bdir, saved = installer.apply(got)
        installer.write_state(manifest, bdir)
        return bdir, saved


# ==================== 界面层 ====================

class UpdateWindow:
    def __init__(self, main_app):
        from main_os import Theme
        self.T = Theme
        self.main_app = main_app
        self.root_dir = os.path.dirname(os.path.abspath(
            __import__("main_os").__file__))
        self.installer = Installer(self.root_dir)
        self.net = Net()
        self.q = queue.Queue()
        self.manifest = None
        self.busy = False

        win = main_app.register_window(tk.Toplevel(main_app.root))
        self.win = win
        win.title("🔄 系统更新")
        win.geometry("640x660")
        win.configure(bg=Theme.BG_MAIN)
        win.resizable(False, False)

        header = tk.Frame(win, bg=Theme.BG_CARD, height=56)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text="🔄 系统更新", font=("微软雅黑", 16, "bold"),
                 bg=Theme.BG_CARD, fg=Theme.TEXT).pack(side=tk.LEFT, padx=18, pady=12)
        tk.Label(header, text="从 GitHub 拉取最新代码", font=("微软雅黑", 9),
                 bg=Theme.BG_CARD, fg=Theme.TEXT_DIM).pack(side=tk.RIGHT, padx=18)

        body = tk.Frame(win, bg=Theme.BG_MAIN)
        body.pack(fill=tk.BOTH, expand=True, padx=18, pady=12)

        # ---- 版本对比 ----
        ver_box = tk.Frame(body, bg=Theme.BG_PANEL)
        ver_box.pack(fill=tk.X)
        self.cur_var = tk.StringVar(value=current_version(self.root_dir))
        self.new_var = tk.StringVar(value="--")
        self._ver_row(ver_box, "当前版本", self.cur_var, Theme.TEXT)
        self._ver_row(ver_box, "远程版本", self.new_var, Theme.ACCENT)

        # ---- 状态文本 ----
        tk.Label(body, text="更新日志", font=("微软雅黑", 9, "bold"),
                 bg=Theme.BG_MAIN, fg=self.T.TEXT_DIM,
                 anchor="w").pack(fill=tk.X, pady=(12, 4))
        text_box = tk.Frame(body, bg=Theme.BG_PANEL)
        text_box.pack(fill=tk.BOTH, expand=True)
        self.log = tk.Text(text_box, height=9, bg=Theme.BG_PANEL,
                           fg=Theme.TEXT, bd=0, relief=tk.FLAT,
                           font=("微软雅黑", 9), wrap="word",
                           insertbackground=Theme.TEXT)
        sb = tk.Scrollbar(text_box, command=self.log.yview)
        self.log.configure(yscrollcommand=sb.set)
        self.log.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(8, 0), pady=6)
        sb.pack(side=tk.RIGHT, fill=tk.Y, pady=6)
        self.log.insert("1.0", "点「检查更新」开始。\n")
        self.log.configure(state="disabled")

        # ---- 进度条 ----
        self.bar = tk.Canvas(body, height=10, bg=Theme.BG_PANEL,
                             highlightthickness=0)
        self.bar.pack(fill=tk.X, pady=(10, 4))
        self.bar_fill = self.bar.create_rectangle(0, 0, 0, 10,
                                                  fill=Theme.BTN_SUCCESS, outline="")

        self.status = tk.StringVar(value="就绪")
        tk.Label(body, textvariable=self.status, font=("微软雅黑", 9),
                 bg=Theme.BG_MAIN, fg=self.T.TEXT_DIM, anchor="w").pack(fill=tk.X)

        # ---- 按钮 ----
        bar_row = tk.Frame(body, bg=Theme.BG_MAIN)
        bar_row.pack(fill=tk.X, pady=(10, 0))
        self.check_btn = self._btn(bar_row, "检查更新", self.check, Theme.BTN_PRIMARY, 9)
        self.check_btn.pack(side=tk.LEFT)
        self.apply_btn = self._btn(bar_row, "下载并安装", self.apply, Theme.BTN_SUCCESS, 10)
        self.apply_btn.pack(side=tk.LEFT, padx=8)
        self.apply_btn.config(state=tk.DISABLED)
        self._btn(bar_row, "回滚上一版", self.rollback, Theme.BTN_WARNING, 10).pack(side=tk.LEFT)
        self._btn(bar_row, "📚 历史版本",
                  lambda: open_versions(self.main_app), Theme.BTN_PURPLE, 11).pack(side=tk.LEFT, padx=(8, 0))
        self._btn(bar_row, "关闭", lambda: win._on_close(), Theme.BTN_DANGER, 6).pack(side=tk.RIGHT)

        tk.Label(body, text=f"源：{self.net.base.split('{')[0]}...（仓库 {self.net.repo}）",
                 font=("微软雅黑", 8), bg=Theme.BG_MAIN,
                 fg=self.T.TEXT_DIM, anchor="w").pack(fill=tk.X, pady=(8, 0))

        # 启动时把上一次更新结果读出来
        state = self.installer.read_state()
        if state.get("pending_restart"):
            self._write(f"上次更新到 v{state.get('installed_version', '?')}，"
                        f"备份在 {state.get('backup_dir', 'updates/backup')}，重启后生效。\n")

        self.win.after(80, self._pump)

    # ---- 小部件 ----
    def _ver_row(self, parent, label, var, color):
        row = tk.Frame(parent, bg=self.T.BG_PANEL)
        row.pack(fill=tk.X, padx=14, pady=6)
        tk.Label(row, text=label, font=("微软雅黑", 9),
                 bg=self.T.BG_PANEL, fg=self.T.TEXT_DIM, width=8,
                 anchor="w").pack(side=tk.LEFT)
        tk.Label(row, textvariable=var, font=("Consolas", 13, "bold"),
                 bg=self.T.BG_PANEL, fg=color, anchor="w").pack(side=tk.LEFT)

    def _btn(self, parent, text, cmd, color, width):
        return tk.Button(parent, text=text, command=cmd,
                         font=("微软雅黑", 10, "bold"),
                         bg=color, fg="#ffffff",
                         activebackground=self.T.BG_HOVER,
                         activeforeground=self.T.TEXT,
                         relief=tk.FLAT, bd=0, cursor="hand2",
                         width=width, pady=6)

    def _write(self, text, newline=True):
        self.log.configure(state="normal")
        self.log.insert("end", text + ("\n" if newline else ""))
        self.log.see("end")
        self.log.configure(state="disabled")

    def _progress(self, frac):
        w = max(1, self.bar.winfo_width())
        self.bar.coords(self.bar_fill, 0, 0, int(w * max(0, min(1, frac))), 10)

    def _alive(self):
        try:
            return bool(self.win.winfo_exists())
        except Exception:
            return False

    # ---- 后台任务 ----
    def _run(self, fn):
        if self.busy:
            return
        self.busy = True
        self._set_buttons(False)

        def wrapper():
            try:
                fn()
            except Exception as e:
                self.q.put(("error", str(e)))
            finally:
                self.q.put(("idle", None))

        threading.Thread(target=wrapper, daemon=True).start()

    def _set_buttons(self, enable):
        state = tk.NORMAL if enable else tk.DISABLED
        self.check_btn.config(state=state)
        if not enable:
            self.apply_btn.config(state=tk.DISABLED)
        elif self.manifest and self._has_new():
            self.apply_btn.config(state=tk.NORMAL)

    def _has_new(self):
        try:
            return ver_tuple(self.manifest.get("version")) > ver_tuple(current_version(self.root_dir))
        except Exception:
            return False

    def _pump(self):
        if not self._alive():
            return
        while True:
            try:
                kind, payload = self.q.get_nowait()
            except queue.Empty:
                break
            if kind == "log":
                self._write(payload)
            elif kind == "status":
                self.status.set(payload)
            elif kind == "progress":
                self._progress(payload)
            elif kind == "manifest":
                self.manifest = payload
                self.new_var.set(payload.get("version", "?"))
            elif kind == "error":
                self._write("✗ " + payload)
                self.status.set("失败")
                self._progress(0)
            elif kind == "idle":
                self.busy = False
                self._set_buttons(True)
        self.win.after(80, self._pump)

    def _log(self, text):
        self.q.put(("log", text))

    def _st(self, text):
        self.q.put(("status", text))

    def _pg(self, frac):
        self.q.put(("progress", frac))

    # ---- 动作 ----
    def check(self):
        self.manifest = None
        self._write("● 正在读取 update.json ...")

        def work():
            self._st("连接中…")
            m = self.net.get_manifest()
            self.q.put(("manifest", m))
            local = current_version(self.root_dir)
            remote = m.get("version", "?")
            if ver_tuple(remote) > ver_tuple(local):
                files = m["files"]
                n = len(files) if hasattr(files, "__len__") else 0
                self._log(f"✓ 发现新版本 {remote}（本地 {local}），共 {n} 个文件")
                for note in (m.get("notes") or [])[:6]:
                    self._log(f"   · {note}")
                self._st(f"有新版本 {remote}")
            elif ver_tuple(remote) == ver_tuple(local):
                self._log(f"= 已是最新（{local}）")
                self._st("已是最新")
                self._pg(1)
            else:
                self._log(f"本地 {local} 比远程 {remote} 还新，不处理")
                self._st("本地版本更新")
                self._pg(1)

        # 检查完成后，idle 分支会按结果自动放开「下载并安装」
        self._run(work)

    def apply(self):
        if not self.manifest:
            return
        if not self._has_new():
            return
        self._write("● 开始下载…")

        def work():
            net = Net(timeout=15, retries=2)

            def progress(i, total, name, size):
                size_txt = f"{size / 1024:.1f} KB" if size >= 1024 else f"{size} B"
                self._log(f"   ↓ {name}  {size_txt}  ({i}/{total})")
                self._pg(i / (total + 2.0))
                self._st(f"下载中 {i}/{total}")

            got = self.installer.download_all(self.manifest, net, progress)
            self._st("备份旧文件…")
            bdir, saved = self.installer.apply(got)
            self._pg(0.95)
            self.installer.write_state(self.manifest, bdir)
            self._pg(1.0)
            self._log(f"✓ 已更新到 {self.manifest.get('version')}")
            self._log(f"   备份：{os.path.relpath(bdir, self.root_dir)}（{len(saved)} 个文件）")
            self._log("   重启 MiniOS 后新代码生效。")
            self._st("完成，重启生效")
            self.manifest = None

        self._run(work)

    def rollback(self):
        self._write("● 回滚上一版…")
        try:
            restored, bdir = self.installer.rollback()
        except Exception as e:
            self._write("✗ " + str(e))
            self._st("回滚失败")
            return
        self._log(f"✓ 已从 {os.path.basename(bdir)} 恢复 {len(restored)} 个文件")
        self._log("   重启 MiniOS 后生效。")
        self._st("已回滚，重启生效")
        self.cur_var.set(current_version(self.root_dir))


class VersionWindow:
    """历史版本列表：选中任意一个 commit，就能把程序换成那个版本。"""

    def __init__(self, main_app):
        from main_os import Theme
        self.T = Theme
        self.main_app = main_app
        self.root_dir = os.path.dirname(os.path.abspath(__import__("main_os").__file__))
        self.installer = Installer(self.root_dir)
        self.net = Net()
        self.history = History(net=self.net,
                               cache_path=os.path.join(self.root_dir, "updates", "history.json"))
        self.entries = []
        self.busy = False
        self._job = None

        win = main_app.register_window(tk.Toplevel(main_app.root))
        self.win = win
        win.title("📚 历史版本")
        win.geometry("660x520")
        win.configure(bg=Theme.BG_MAIN)
        win.resizable(False, False)

        header = tk.Frame(win, bg=Theme.BG_CARD, height=56)
        header.pack(fill=tk.X)
        header.pack_propagate(False)
        tk.Label(header, text="📚 历史版本", font=("微软雅黑", 16, "bold"),
                 bg=Theme.BG_CARD, fg=Theme.TEXT).pack(side=tk.LEFT, padx=18, pady=12)
        tk.Label(header, text=f"来源 {self.net.repo} 的提交历史", font=("微软雅黑", 9),
                 bg=Theme.BG_CARD, fg=Theme.TEXT_DIM).pack(side=tk.RIGHT, padx=18)

        body = tk.Frame(win, bg=Theme.BG_MAIN)
        body.pack(fill=tk.BOTH, expand=True, padx=18, pady=12)

        tk.Label(body, text="每行是一个可回滚的版本（双击即恢复）", font=("微软雅黑", 9),
                 bg=Theme.BG_MAIN, fg=Theme.TEXT_DIM, anchor="w").pack(fill=tk.X, pady=(0, 6))

        lb_box = tk.Frame(body, bg=Theme.BG_PANEL)
        lb_box.pack(fill=tk.BOTH, expand=True)
        self.lb = tk.Listbox(lb_box, bg=Theme.BG_PANEL, fg=Theme.TEXT,
                            selectbackground=Theme.BG_HOVER, selectforeground=Theme.TEXT,
                            bd=0, relief=tk.FLAT, font=("Consolas", 10),
                            activestyle="none", highlightthickness=0)
        lb_scroll = tk.Scrollbar(lb_box, command=self.lb.yview)
        self.lb.configure(yscrollcommand=lb_scroll.set)
        self.lb.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10, 0), pady=8)
        lb_scroll.pack(side=tk.RIGHT, fill=tk.Y, pady=8)
        self.lb.bind("<Double-Button-1>", lambda e: self.restore())

        self.status = tk.StringVar(value="正在读取提交历史…")
        tk.Label(body, textvariable=self.status, font=("微软雅黑", 9),
                 bg=Theme.BG_MAIN, fg=Theme.TEXT_DIM, anchor="w").pack(fill=tk.X, pady=(8, 0))

        row = tk.Frame(body, bg=Theme.BG_MAIN)
        row.pack(fill=tk.X, pady=(10, 0))
        self.refresh_btn = tk.Button(row, text="🔄 刷新", command=lambda: self.reload(force=True),
                                     font=("微软雅黑", 10, "bold"), bg=Theme.BTN_DEFAULT,
                                     fg="#fff", relief=tk.FLAT, bd=0, cursor="hand2",
                                     width=8, pady=6)
        self.refresh_btn.pack(side=tk.LEFT)
        self.restore_btn = tk.Button(row, text="↩ 恢复到选中版本", command=self.restore,
                                     font=("微软雅黑", 10, "bold"), bg=Theme.BTN_WARNING,
                                     fg="#fff", relief=tk.FLAT, bd=0, cursor="hand2",
                                     width=16, pady=6, state=tk.DISABLED)
        self.restore_btn.pack(side=tk.LEFT, padx=8)
        tk.Button(row, text="关闭", command=lambda: win._on_close(),
                  font=("微软雅黑", 10, "bold"), bg=Theme.BTN_DANGER, fg="#fff",
                  relief=tk.FLAT, bd=0, cursor="hand2", width=6, pady=6).pack(side=tk.RIGHT)

        self.win.after(120, self.reload)
        self.win.after(120, self._poll)

    # ---------- 基础设施 ----------
    def _st(self, text):
        try:
            self.status.set(text)
        except Exception:
            pass

    def _alive(self):
        try:
            return bool(self.win.winfo_exists())
        except Exception:
            return False

    def _async(self, fn, done):
        if self.busy:
            return
        self.busy = True
        self.refresh_btn.config(state=tk.DISABLED)
        self.restore_btn.config(state=tk.DISABLED)

        def wrapper():
            try:
                self._job = ("ok", fn(), done)
            except Exception as e:
                self._job = ("err", e, done)

        threading.Thread(target=wrapper, daemon=True).start()

    def _poll(self):
        if not self._alive():
            return
        if self._job:
            kind, payload, done = self._job
            self._job = None
            self.busy = False
            try:
                self.refresh_btn.config(state=tk.NORMAL)
                if kind == "ok":
                    done(payload)
                else:
                    self._st("失败：" + str(payload))
            except Exception:
                pass
        self.win.after(150, self._poll)

    # ---------- 读列表 ----------
    def reload(self, force=False):
        self._st("正在读取提交历史…" if force else "正在读取缓存…")
        self.lb.delete(0, tk.END)
        self._async(lambda: self.history.entries(force=force), self._render)

    def _render(self, entries):
        self.entries = entries
        self.lb.delete(0, tk.END)
        if not entries:
            self.lb.insert(tk.END, "（没有读到任何版本，检查网络后点刷新）")
            self._st("没有可用版本")
            return
        for e in entries:
            ver = e["version"] or "未标注"
            date = (e["date"] or "")[:16].replace("T", " ")
            head = f"{('v' + str(ver)) if e['version'] else ver:<10s}  {date}  " \
                   f"{len(e['files']):>2} 个文件  {e['short']}"
            self.lb.insert(tk.END, head)
        stamp = self.history.cached_at()
        if stamp:
            self._st(f"共 {len(entries)} 个版本（缓存于 {stamp}，点「🔄 刷新」拉最新）")
        else:
            self._st(f"共 {len(entries)} 个版本（双击列表项，或按下面的按钮恢复）")
        self.restore_btn.config(state=tk.NORMAL)

    # ---------- 恢复 ----------
    def restore(self):
        if self.busy or not self.entries:
            return
        sel = self.lb.curselection()
        if not sel:
            self._st("先在列表里选一个版本")
            return
        e = self.entries[sel[0]]
        label = ("v" + str(e["version"])) if e["version"] else e["short"]
        cur = current_version(self.root_dir)
        if not messagebox.askyesno(
                "恢复版本",
                f"把程序换回 {label}？\n\n"
                f"当前版本：v{cur}\n目标版本：{label}（{e['short']}）\n"
                f"文件数：{len(e['files'])}\n\n"
                "当前文件会先备份到 updates\\backup，随时能再切回来。\n"
                "恢复后需要重启 MiniOS 才能生效。",
                parent=self.win):
            return

        self._st(f"正在下载 {label} …")

        def work():
            def prog(i, total, name, size):
                self._st(f"下载中 {name}  ({i}/{total})")
            return self.history.restore(e, self.installer, self.net, prog)

        def done(result):
            bdir, saved = result
            self._st(f"✓ 已恢复到 {label}，重启后生效")
            messagebox.showinfo(
                "已恢复",
                f"已换回 {label}（{len(saved)} 个文件已备份）。\n\n"
                f"备份位置：{os.path.relpath(bdir, self.root_dir)}\n"
                "请关闭本窗口并重启 MiniOS，新版本才会生效。",
                parent=self.win)

        self._async(work, done)


def open_versions(main_app):
    return VersionWindow(main_app)


def open_updater(main_app):
    return UpdateWindow(main_app)




def boot_notice(main_app):
    """启动时如果检测到刚更新过，弹一条 Toast 提醒"""
    try:
        root_dir = os.path.dirname(os.path.abspath(__import__("main_os").__file__))
        state = Installer(root_dir).read_state()
        if state.get("pending_restart"):
            text = f"已更新到 v{state.get('installed_version', '?')}，本次启动即为新版本"
            fn = getattr(main_app, "toast", None) or getattr(main_app, "notify", None)
            if callable(fn):
                fn(text, icon="🔄")
            state["pending_restart"] = False
            with open(Installer(root_dir).state_path, "w", encoding="utf-8") as f:
                json.dump(state, f, ensure_ascii=False, indent=2)
    except Exception:
        pass
