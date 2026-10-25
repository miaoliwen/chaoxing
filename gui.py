# -*- coding: utf-8 -*-
"""
超星学习通助手 · 图形界面入口

设计要点：
1. 不复制业务逻辑，全部复用 main.main()，通过生成 config.ini + 注入 `-c 参数` 驱动；
2. 打包成无控制台窗口的 exe 后 sys.stdout/sys.stderr 为 None，
   因此必须在 import 业务模块之前接管这两个流，否则 tqdm / loguru 会崩溃；
3. 原程序中的 input() 交互统一接管为 GUI 弹窗，保证不会在后台线程里挂起等待。
"""
from __future__ import annotations

import configparser
import io
import os
import queue
import re
import shutil
import sys
import threading
import time
import traceback
import webbrowser
from pathlib import Path

# ---------------------------------------------------------------------------
# 一、先接管标准输出，再导入业务模块（顺序不可调整）
# ---------------------------------------------------------------------------
LOG_QUEUE: "queue.Queue[tuple[str, str]]" = queue.Queue()
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")
_PCT_RE = re.compile(r"(\d{1,3})%")  # tqdm 进度行里的百分比，用于驱动底部进度条


class _StreamProxy(io.TextIOBase):
    """把 print / tqdm / loguru 的输出转成队列消息，交给 Tk 主线程渲染。

    - 以 \\n 结尾的片段按普通日志行处理；
    - 以 \\r 结尾的片段（tqdm 进度条）作为进度消息处理，避免刷屏。
    """

    def __init__(self) -> None:
        super().__init__()
        self._buf = ""
        self._lock = threading.Lock()

    @property
    def encoding(self) -> str:  # tqdm / loguru 会读取该属性
        return "utf-8"

    def isatty(self) -> bool:
        return False

    def writable(self) -> bool:
        return True

    def write(self, s: str) -> int:  # type: ignore[override]
        if not isinstance(s, str):
            s = str(s)
        with self._lock:
            self._buf += s
            while True:
                n = self._buf.find("\n")
                r = self._buf.find("\r")
                if n == -1 and r == -1:
                    break
                if n != -1 and (r == -1 or n < r):
                    line, self._buf = self._buf[:n], self._buf[n + 1:]
                    if line.strip():
                        LOG_QUEUE.put(("line", _ANSI_RE.sub("", line)))
                else:
                    seg, self._buf = self._buf[:r], self._buf[r + 1:]
                    if seg.strip():
                        LOG_QUEUE.put(("progress", _ANSI_RE.sub("", seg).strip()))
            # 防止无换行的超长输出把内存撑爆
            if len(self._buf) > 8192:
                LOG_QUEUE.put(("line", self._buf[-2000:]))
                self._buf = ""
        return len(s)

    def flush(self) -> None:
        pass


_STREAM = _StreamProxy()
if sys.stdout is None or sys.stderr is None or not sys.stdout:
    sys.stdout = _STREAM
    sys.stderr = _STREAM
else:
    # 源码运行时也接管，保证日志能进 GUI
    sys.stdout = _STREAM
    sys.stderr = _STREAM

import tkinter as tk  # noqa: E402
from tkinter import messagebox, simpledialog, ttk  # noqa: E402

from main import main as run_main  # noqa: E402  必须在流接管之后导入


APP_NAME = "超星学习通助手"
APP_VERSION = "1.0.0"
# GitHub Release 信息（检查更新用）
RELEASE_API = "https://api.github.com/repos/miaoliwen/chaoxing/releases/latest"
RELEASE_PAGE = "https://github.com/miaoliwen/chaoxing/releases/latest"

# 界面配色（浅色页面 + 白色卡片）
PAGE_BG = "#eef1f6"
# 状态圆点颜色：灰=就绪 绿=运行 蓝=正常完成 橙=警告 红=失败
_STATUS_COLORS = {"idle": "#9ca3af", "run": "#16a34a", "ok": "#2563eb",
                  "warn": "#d97706", "error": "#dc2626"}


# ---------------------------------------------------------------------------
# 二、路径与工作目录
# ---------------------------------------------------------------------------
def resolve_app_dir() -> str:
    """程序所在目录（打包后为 exe 所在目录）。"""
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def resolve_work_dir(app_dir: str) -> str:
    """配置 / cookies / 日志的落盘目录，优先程序目录，不可写时退回用户目录。"""
    try:
        probe = (Path(app_dir) / ".write_test").resolve()
        # 写前校验：探测文件必须落在程序目录内，防止路径被拼接出 ../
        if not probe.is_relative_to(Path(app_dir).resolve()):
            raise OSError(f"探测路径越界: {probe}")
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
        return app_dir
    except OSError:
        base = os.environ.get("LOCALAPPDATA") or os.path.expanduser("~")
        path = os.path.join(base, "ChaoxingGUI")
        os.makedirs(path, exist_ok=True)
        return path


APP_DIR = resolve_app_dir()
WORK_DIR = resolve_work_dir(APP_DIR)
CONFIG_PATH = os.path.join(WORK_DIR, "config.ini")
TEMPLATE_PATH = os.path.join(APP_DIR, "config_template.ini")

try:
    os.chdir(WORK_DIR)  # 让 cookies.txt / chaoxing.log / 缓存都落在同一目录
except OSError:
    pass


# ---------------------------------------------------------------------------
# 三、配置读写
# ---------------------------------------------------------------------------
def new_parser() -> configparser.ConfigParser:
    # interpolation=None：密码或 token 中可能含 %，否则 configparser 会抛异常
    return configparser.ConfigParser(interpolation=None)


def load_raw_config() -> configparser.ConfigParser:
    """读取现有 config.ini；不存在则从模板初始化。"""
    cp = new_parser()
    if os.path.exists(CONFIG_PATH):
        cp.read(CONFIG_PATH, encoding="utf-8")
    elif os.path.exists(TEMPLATE_PATH):
        cp.read(TEMPLATE_PATH, encoding="utf-8")
    for section in ("common", "tiku", "notification"):
        if not cp.has_section(section):
            cp.add_section(section)
    return cp


def cfg_get(cp: configparser.ConfigParser, section: str, key: str, default: str = "") -> str:
    try:
        value = cp.get(section, key)
    except (configparser.NoSectionError, configparser.NoOptionError):
        return default
    return default if value is None else value.strip()


def cfg_bool(cp: configparser.ConfigParser, section: str, key: str, default: bool = False) -> bool:
    raw = cfg_get(cp, section, key, "true" if default else "false")
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


class _ToolTip:
    """轻量悬停提示：纯 tkinter 实现，显示在控件右侧。"""

    def __init__(self, widget: tk.Widget, text: str) -> None:
        self._widget = widget
        self._text = text
        self._tip: tk.Toplevel | None = None
        widget.bind("<Enter>", self._show, add="+")
        widget.bind("<Leave>", self._hide, add="+")
        widget.bind("<ButtonPress>", self._hide, add="+")

    def _show(self, _event: object = None) -> None:
        if self._tip is not None:
            return
        x = self._widget.winfo_rootx() + self._widget.winfo_width() + 8
        y = self._widget.winfo_rooty() + max(self._widget.winfo_height() // 2 - 14, 0)
        self._tip = tk.Toplevel(self._widget)
        self._tip.wm_overrideredirect(True)
        self._tip.attributes("-topmost", True)
        tk.Label(self._tip, text=self._text, justify="left",
                 bg="#1f2937", fg="#f9fafb", padx=9, pady=5,
                 font=("Microsoft YaHei UI", 8)).pack()
        self._tip.wm_geometry(f"+{x}+{y}")

    def _hide(self, _event: object = None) -> None:
        if self._tip is not None:
            self._tip.destroy()
            self._tip = None


# ---------------------------------------------------------------------------
# 四、主窗口
# ---------------------------------------------------------------------------
class ChaoxingGUI:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.running = False
        self._orig_input = None
        self._run_started_at: float | None = None
        self._pb_indeterminate = False

        self._init_style()
        self._init_vars()

        self._build_header()
        self._build_body()
        self._build_footer()

        self._load_config_into_form()
        self._install_input_hook()
        self._bind_shortcuts()
        # 启动后延迟静默检查更新（后台线程，失败不打扰）
        self.root.after(2500, lambda: self._check_update_async(silent=True))

        self.root.protocol("WM_DELETE_WINDOW", self._on_close)
        self.root.after(120, self._poll_log)

    # -- 外观 ---------------------------------------------------------------
    def _init_style(self) -> None:
        self.root.title(f"{APP_NAME} v{APP_VERSION}")
        # 启动时居中（略偏上，视觉更稳）
        w, h = 940, 720
        sw, sh = self.root.winfo_screenwidth(), self.root.winfo_screenheight()
        self.root.geometry(f"{w}x{h}+{max((sw - w) // 2, 0)}+{max((sh - h) // 3, 0)}")
        self.root.minsize(880, 620)
        self.root.configure(background=PAGE_BG)
        # 窗口图标：打包后从解包目录读，源码运行从 resource/ 读
        icon_path = None
        if getattr(sys, "frozen", False):
            cand = os.path.join(getattr(sys, "_MEIPASS", ""), "icon.ico")
            icon_path = cand if os.path.exists(cand) else None
        if icon_path is None:
            cand = os.path.join(APP_DIR, "resource", "icon.ico")
            icon_path = cand if os.path.exists(cand) else None
        if icon_path:
            try:
                self.root.iconbitmap(default=icon_path)
            except Exception:
                pass

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass

        base_font = ("Microsoft YaHei UI", 9)
        bold_font = ("Microsoft YaHei UI", 9, "bold")
        style.configure(".", font=base_font, background=PAGE_BG, foreground="#1f2937")
        style.configure("TFrame", background=PAGE_BG)
        style.configure("TLabel", background=PAGE_BG, foreground="#1f2937", font=base_font)

        style.configure("TButton", font=base_font, padding=(12, 5),
                        background="#ffffff", foreground="#374151", borderwidth=1)
        style.map("TButton",
                  background=[("pressed", "#e2e8f0"), ("active", "#f5f7fa"),
                              ("disabled", "#f3f4f6")],
                  foreground=[("disabled", "#9ca3af")],
                  bordercolor=[("!disabled", "#cbd5e1"), ("disabled", "#e5e7eb")])
        style.configure("Accent.TButton", foreground="#2563eb")
        style.map("Accent.TButton",
                  background=[("active", "#eff6ff"), ("disabled", "#f3f4f6")],
                  bordercolor=[("!disabled", "#93c5fd")])

        style.configure("TEntry", padding=(6, 4))
        style.configure("TCombobox", padding=(6, 4))
        style.configure("TSpinbox", padding=(6, 4))

        style.configure("TNotebook", background=PAGE_BG, borderwidth=0, tabmargins=(10, 8, 10, 0))
        style.configure("TNotebook.Tab", padding=(18, 9), font=base_font,
                        background="#dde3ec", foreground="#5b6472", borderwidth=0)
        style.map("TNotebook.Tab",
                  background=[("selected", "#ffffff"), ("active", "#e8edf4")],
                  foreground=[("selected", "#1d4ed8"), ("active", "#374151")])

        style.configure("TLabelframe", background="#ffffff", borderwidth=1, relief="solid",
                        bordercolor="#e2e8f0")
        style.configure("TLabelframe.Label", background="#ffffff", foreground="#1e3a8a",
                        font=bold_font)
        style.configure("Card.TFrame", background="#ffffff")
        style.configure("Card.TLabel", background="#ffffff")
        style.configure("Card.TCheckbutton", background="#ffffff")
        style.configure("CardHint.TLabel", background="#ffffff", foreground="#6b7280",
                        font=base_font)
        style.configure("Hint.TLabel", foreground="#6b7280", font=base_font)
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 13, "bold"),
                        foreground="#ffffff", background="#1e3a8a")
        style.configure("Sub.TLabel", font=base_font,
                        foreground="#c7d2fe", background="#1e3a8a")

        style.configure("Primary.TButton", font=("Microsoft YaHei UI", 10, "bold"),
                        padding=(18, 8))
        style.map("Primary.TButton",
                  background=[("!disabled", "#2563eb"), ("active", "#1d4ed8"),
                              ("disabled", "#cbd5e1")],
                  foreground=[("!disabled", "#ffffff"), ("disabled", "#ffffff")])
        style.configure("Danger.TButton", font=base_font, padding=(14, 7))
        style.map("Danger.TButton",
                  background=[("!disabled", "#dc2626"), ("active", "#b91c1c"),
                              ("disabled", "#f3f4f6")],
                  foreground=[("!disabled", "#ffffff"), ("disabled", "#9ca3af")])

        style.configure("Treeview", rowheight=26, font=base_font, background="#ffffff",
                        fieldbackground="#ffffff", foreground="#1f2937", borderwidth=0)
        style.configure("Treeview.Heading", font=bold_font, background="#f1f5f9",
                        foreground="#475569", padding=(6, 6), relief="flat")
        style.map("Treeview.Heading", background=[("active", "#e2e8f0")])
        style.map("Treeview", background=[("selected", "#bfdbfe")],
                  foreground=[("selected", "#1e3a8a")])

        style.configure("TScrollbar", troughcolor=PAGE_BG, background="#cbd5e1",
                        borderwidth=0, arrowsize=12)
        style.map("TScrollbar", background=[("active", "#94a3b8")])
        style.configure("Slim.Horizontal.TProgressbar", troughcolor="#e2e8f0",
                        background="#2563eb", borderwidth=0, thickness=6)

    def _init_vars(self) -> None:
        # 账号
        self.var_username = tk.StringVar()
        self.var_password = tk.StringVar()
        self.var_use_cookies = tk.BooleanVar(value=False)
        self.var_show_password = tk.BooleanVar(value=False)
        # 课程
        self.var_course_ids = tk.StringVar()
        self.var_all_courses = tk.BooleanVar(value=False)
        self.var_finish_notify = tk.BooleanVar(value=False)
        self.var_course_count = tk.StringVar(value="未选择课程")
        # 学习参数
        self.var_speed = tk.StringVar(value="1.0")
        self.var_jobs = tk.StringVar(value="4")
        self.var_notopen = tk.StringVar(value="retry")
        self.var_retry_interval = tk.StringVar(value="1.0")
        self.var_redo_enabled = tk.BooleanVar(value=False)
        self.var_redo_times = tk.StringVar(value="3")
        self.var_add_count = tk.BooleanVar(value=False)
        self.var_target_count = tk.StringVar(value="100")
        # 题库
        self.var_provider = tk.StringVar(value="TikuYanxi")
        self.var_tokens = tk.StringVar()
        self.var_submit = tk.BooleanVar(value=False)
        self.var_cover_rate = tk.StringVar(value="0.9")
        self.var_delay = tk.StringVar(value="1.0")
        self.var_endpoint = tk.StringVar()
        self.var_key = tk.StringVar()
        self.var_model = tk.StringVar()
        self.var_sf_key = tk.StringVar()
        self.var_tiku_url = tk.StringVar()
        # 通知
        self.var_notify_provider = tk.StringVar(value="ServerChan")
        self.var_notify_url = tk.StringVar()
        self.var_tg_chat = tk.StringVar()
        # 状态
        self.var_status = tk.StringVar(value="就绪")
        self.var_progress = tk.StringVar(value="")
        self.var_elapsed = tk.StringVar(value="")
        self.var_autoscroll = tk.BooleanVar(value=True)

    # -- 布局 ---------------------------------------------------------------
    def _build_header(self) -> None:
        header = tk.Frame(self.root, bg="#1e3a8a", height=64)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text=f"  {APP_NAME}", bg="#1e3a8a", fg="#ffffff",
                 font=("Microsoft YaHei UI", 14, "bold")).pack(side="left", pady=14)
        tk.Label(header, text=f"v{APP_VERSION}   ·   图形界面版", bg="#1e3a8a",
                 fg="#c7d2fe", font=("Microsoft YaHei UI", 9)).pack(side="right", padx=18)

    def _build_body(self) -> None:
        container = ttk.Frame(self.root, padding=(14, 12, 14, 6))
        container.pack(fill="both", expand=True)

        self.notebook = ttk.Notebook(container)
        self.notebook.pack(fill="both", expand=True)

        self.tab_account = ttk.Frame(self.notebook, padding=12)
        self.tab_study = ttk.Frame(self.notebook, padding=12)
        self.tab_tiku = ttk.Frame(self.notebook, padding=12)
        self.tab_log = ttk.Frame(self.notebook, padding=12)

        self.notebook.add(self.tab_account, text="账号与课程")
        self.notebook.add(self.tab_study, text="学习设置")
        self.notebook.add(self.tab_tiku, text="题库与通知")
        self.notebook.add(self.tab_log, text="运行日志")

        self._build_tab_account()
        self._build_tab_study()
        self._build_tab_tiku()
        self._build_tab_log()

    # ---- Tab 1: 账号与课程 -----------------------------------------------
    def _build_tab_account(self) -> None:
        box = self._card(self.tab_account, "登录信息")
        box.pack(fill="x")

        grid = ttk.Frame(box, style="Card.TFrame")
        grid.pack(fill="x", padx=14, pady=(4, 12))
        grid.columnconfigure(1, weight=1)

        ttk.Label(grid, text="手机号", style="Card.TLabel").grid(row=0, column=0, sticky="w", pady=6)
        self.ent_username = ttk.Entry(grid, textvariable=self.var_username)
        self.ent_username.grid(row=0, column=1, sticky="ew", padx=(10, 0), pady=6)

        ttk.Label(grid, text="密码", style="Card.TLabel").grid(row=1, column=0, sticky="w", pady=6)
        self.ent_password = ttk.Entry(grid, textvariable=self.var_password, show="*")
        self.ent_password.grid(row=1, column=1, sticky="ew", padx=(10, 0), pady=6)
        ttk.Checkbutton(grid, text="显示", variable=self.var_show_password,
                        style="Card.TCheckbutton",
                        command=self._toggle_password).grid(row=1, column=2, sticky="w", padx=(10, 0))

        chk = ttk.Checkbutton(grid, text="使用 cookies.txt 登录（勾选后忽略手机号与密码）",
                              variable=self.var_use_cookies, style="Card.TCheckbutton",
                              command=self._toggle_cookie_mode)
        chk.grid(row=2, column=1, sticky="w", padx=(10, 0), pady=(2, 0))
        _ToolTip(chk, "勾选后读取程序目录下的 cookies.txt 会话登录，忽略手机号与密码；"
                      "cookies 可从浏览器登录学习通后导出")

        # 课程
        box2 = self._card(self.tab_account, "课程选择")
        box2.pack(fill="both", expand=True, pady=(12, 0))

        toolbar = ttk.Frame(box2, style="Card.TFrame")
        toolbar.pack(fill="x", padx=14, pady=(2, 8))

        self.btn_fetch = ttk.Button(toolbar, text="⟳  获取课程列表", style="Accent.TButton",
                                    command=self._fetch_courses)
        self.btn_fetch.pack(side="left")
        ttk.Button(toolbar, text="全选", command=lambda: self._select_all_courses(True)).pack(side="left", padx=6)
        ttk.Button(toolbar, text="清空选择", command=lambda: self._select_all_courses(False)).pack(side="left")
        chk_all = ttk.Checkbutton(toolbar, text="学习全部课程", variable=self.var_all_courses,
                                  style="Card.TCheckbutton")
        chk_all.pack(side="left", padx=(16, 0))
        _ToolTip(chk_all, "不手动选课时，学习账号下全部课程")
        ttk.Label(toolbar, textvariable=self.var_course_count,
                  style="Card.TLabel").pack(side="right")

        tree_wrap = ttk.Frame(box2, style="Card.TFrame")
        tree_wrap.pack(fill="both", expand=True, padx=14)
        columns = ("title", "clazz", "course_id", "clazz_id")
        self.course_tree = ttk.Treeview(tree_wrap, columns=columns, show="headings", height=8,
                                        selectmode="extended")
        headings = {"title": "课程名称", "clazz": "班级", "course_id": "courseId", "clazz_id": "clazzId"}
        widths = {"title": 380, "clazz": 220, "course_id": 110, "clazz_id": 110}
        for col in columns:
            self.course_tree.heading(col, text=headings[col])
            self.course_tree.column(col, width=widths[col], anchor="w", stretch=(col == "title"))
        self.course_tree.tag_configure("odd", background="#f8fafc")
        self.course_tree.bind("<<TreeviewSelect>>", lambda _e: self._update_course_count())
        vbar = ttk.Scrollbar(tree_wrap, orient="vertical", command=self.course_tree.yview)
        self.course_tree.configure(yscrollcommand=vbar.set)
        self.course_tree.pack(side="left", fill="both", expand=True)
        vbar.pack(side="right", fill="y")

        manual = ttk.Frame(box2, style="Card.TFrame")
        manual.pack(fill="x", padx=14, pady=(8, 12))
        ttk.Label(manual, text="手动填写课程 ID（逗号分隔，可留空）", style="Card.TLabel").pack(side="left")
        ttk.Entry(manual, textvariable=self.var_course_ids).pack(side="left", fill="x", expand=True, padx=(10, 0))
        ttk.Label(box2, text="提示：列表中多选即可指定课程；若既不选择也不勾选“学习全部课程”，将无法开始。",
                  style="CardHint.TLabel").pack(anchor="w", padx=14, pady=(0, 10))

    # ---- Tab 2: 学习设置 --------------------------------------------------
    def _build_tab_study(self) -> None:
        box = self._card(self.tab_study, "播放与并发")
        box.pack(fill="x")
        grid = ttk.Frame(box, style="Card.TFrame")
        grid.pack(fill="x", padx=14, pady=(4, 12))
        grid.columnconfigure(1, weight=1)
        grid.columnconfigure(3, weight=1)

        ttk.Label(grid, text="视频倍速", style="Card.TLabel").grid(row=0, column=0, sticky="w", pady=6)
        ttk.Combobox(grid, textvariable=self.var_speed, width=8,
                     values=["1.0", "1.25", "1.5", "1.75", "2.0"]).grid(row=0, column=1, sticky="w", padx=(10, 24))

        ttk.Label(grid, text="同时进行章节数", style="Card.TLabel").grid(row=0, column=2, sticky="w", pady=6)
        ttk.Spinbox(grid, from_=1, to=16, textvariable=self.var_jobs, width=8).grid(row=0, column=3, sticky="w", padx=(10, 0))

        ttk.Label(grid, text="章节关闭时的处理", style="Card.TLabel").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Combobox(grid, textvariable=self.var_notopen, width=10, state="readonly",
                     values=["retry", "continue"]).grid(row=1, column=1, sticky="w", padx=(10, 24))

        ttk.Label(grid, text="失败重试间隔（秒）", style="Card.TLabel").grid(row=1, column=2, sticky="w", pady=6)
        ttk.Entry(grid, textvariable=self.var_retry_interval, width=10).grid(row=1, column=3, sticky="w", padx=(10, 0))

        # 章节检测
        box2 = self._card(self.tab_study, "章节检测（测验）")
        box2.pack(fill="x", pady=(12, 0))
        g2 = ttk.Frame(box2, style="Card.TFrame")
        g2.pack(fill="x", padx=14, pady=(4, 12))
        g2.columnconfigure(3, weight=1)

        ttk.Checkbutton(g2, text="答错后自动重做（仅适用于允许多次作答的课程）",
                        variable=self.var_redo_enabled, style="Card.TCheckbutton").grid(
            row=0, column=0, columnspan=3, sticky="w", pady=4)
        ttk.Label(g2, text="最大重做次数", style="Card.TLabel").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Spinbox(g2, from_=0, to=10, textvariable=self.var_redo_times, width=8).grid(
            row=1, column=1, sticky="w", padx=(10, 0))

        # 学习次数
        box3 = self._card(self.tab_study, "章节学习次数")
        box3.pack(fill="x", pady=(12, 0))
        g3 = ttk.Frame(box3, style="Card.TFrame")
        g3.pack(fill="x", padx=14, pady=(4, 12))
        ttk.Checkbutton(g3, text="刷完任务点后增加章节学习次数", variable=self.var_add_count,
                        style="Card.TCheckbutton").grid(row=0, column=0, columnspan=3, sticky="w", pady=4)
        ttk.Label(g3, text="目标总次数", style="Card.TLabel").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Spinbox(g3, from_=1, to=9999, textvariable=self.var_target_count, width=8).grid(
            row=1, column=1, sticky="w", padx=(10, 0))

    # ---- Tab 3: 题库与通知 -----------------------------------------------
    def _build_tab_tiku(self) -> None:
        box = self._card(self.tab_tiku, "题库来源")
        box.pack(fill="x")
        g = ttk.Frame(box, style="Card.TFrame")
        g.pack(fill="x", padx=14, pady=(4, 12))
        g.columnconfigure(1, weight=1)
        g.columnconfigure(3, weight=1)

        ttk.Label(g, text="题库 provider", style="Card.TLabel").grid(row=0, column=0, sticky="w", pady=6)
        ttk.Combobox(g, textvariable=self.var_provider, width=16,
                     values=["TikuYanxi", "TikuGo", "TikuLike", "TikuAdapter",
                             "AI", "SiliconFlow", "TikuManual", ""]).grid(
            row=0, column=1, sticky="w", padx=(10, 24))
        ttk.Label(g, text="查询间隔（秒）", style="Card.TLabel").grid(row=0, column=2, sticky="w", pady=6)
        ttk.Entry(g, textvariable=self.var_delay, width=8).grid(row=0, column=3, sticky="w", padx=(10, 0))

        ttk.Label(g, text="题库 Token", style="Card.TLabel").grid(row=1, column=0, sticky="w", pady=6)
        ent_tokens = ttk.Entry(g, textvariable=self.var_tokens)
        ent_tokens.grid(row=1, column=1, columnspan=3, sticky="ew", padx=(10, 0), pady=6)
        _ToolTip(ent_tokens, "题库网站的查询 Token，多个用英文逗号分隔；留空则无法自动答题")

        chk_submit = ttk.Checkbutton(g, text="自动提交答案（未达覆盖率时只保存不提交）",
                                     variable=self.var_submit, style="Card.TCheckbutton")
        chk_submit.grid(row=2, column=0, columnspan=2, sticky="w", pady=(6, 2))
        _ToolTip(chk_submit, "答案命中率达到「最低覆盖率」才提交；不勾选则只填写不提交")
        ttk.Label(g, text="最低覆盖率", style="Card.TLabel").grid(row=3, column=0, sticky="w", pady=6)
        ent_rate = ttk.Entry(g, textvariable=self.var_cover_rate, width=8)
        ent_rate.grid(row=3, column=1, sticky="w", padx=(10, 0))
        _ToolTip(ent_rate, "0 ~ 1 之间，例如 0.9 表示答案覆盖 90% 的题目才提交")

        box2 = self._card(self.tab_tiku, "大模型 / 云题库参数")
        box2.pack(fill="x", pady=(12, 0))
        g2 = ttk.Frame(box2, style="Card.TFrame")
        g2.pack(fill="x", padx=14, pady=(4, 12))
        g2.columnconfigure(1, weight=1)

        rows = [
            ("API Endpoint（AI）", self.var_endpoint, False),
            ("API Key（AI）", self.var_key, True),
            ("模型名称（AI）", self.var_model, False),
            ("硅基流动 Key", self.var_sf_key, True),
            ("TikuAdapter 地址", self.var_tiku_url, False),
        ]
        for i, (label, var, secret) in enumerate(rows):
            ttk.Label(g2, text=label, style="Card.TLabel").grid(row=i, column=0, sticky="w", pady=5)
            ttk.Entry(g2, textvariable=var, show="*" if secret else "").grid(
                row=i, column=1, sticky="ew", padx=(10, 0), pady=5)

        box3 = self._card(self.tab_tiku, "完成通知（可选）")
        box3.pack(fill="x", pady=(12, 0))
        g3 = ttk.Frame(box3, style="Card.TFrame")
        g3.pack(fill="x", padx=14, pady=(4, 12))
        g3.columnconfigure(1, weight=1)
        g3.columnconfigure(3, weight=1)

        ttk.Label(g3, text="通知 provider", style="Card.TLabel").grid(row=0, column=0, sticky="w", pady=6)
        ttk.Combobox(g3, textvariable=self.var_notify_provider, width=14,
                     values=["ServerChan", "Qmsg", "Bark", "Telegram", ""]).grid(
            row=0, column=1, sticky="w", padx=(10, 24))
        ttk.Label(g3, text="Telegram chat_id", style="Card.TLabel").grid(row=0, column=2, sticky="w", pady=6)
        ttk.Entry(g3, textvariable=self.var_tg_chat, width=14).grid(row=0, column=3, sticky="w", padx=(10, 0))

        ttk.Label(g3, text="推送 URL", style="Card.TLabel").grid(row=1, column=0, sticky="w", pady=6)
        ttk.Entry(g3, textvariable=self.var_notify_url).grid(row=1, column=1, columnspan=3,
                                                             sticky="ew", padx=(10, 0), pady=6)

    # ---- Tab 4: 日志 ------------------------------------------------------
    def _build_tab_log(self) -> None:
        top = ttk.Frame(self.tab_log)
        top.pack(fill="x")
        ttk.Label(top, text="当前进度").pack(side="left")
        ttk.Label(top, textvariable=self.var_progress, style="Hint.TLabel").pack(
            side="left", padx=(8, 0), fill="x", expand=True, anchor="w")
        ttk.Checkbutton(top, text="自动滚动", variable=self.var_autoscroll).pack(
            side="right", padx=(0, 8))
        ttk.Button(top, text="复制日志", command=self._copy_log).pack(side="right")
        ttk.Button(top, text="清空日志", command=self._clear_log).pack(side="right", padx=(0, 8))

        wrap = ttk.Frame(self.tab_log)
        wrap.pack(fill="both", expand=True, pady=(8, 0))
        self.log_text = tk.Text(wrap, wrap="none", font=("Consolas", 9), bg="#0f172a",
                                fg="#e2e8f0", insertbackground="#e2e8f0", relief="flat",
                                padx=10, pady=8)
        ybar = ttk.Scrollbar(wrap, orient="vertical", command=self.log_text.yview)
        xbar = ttk.Scrollbar(wrap, orient="horizontal", command=self.log_text.xview)
        self.log_text.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
        ybar.pack(side="right", fill="y")
        xbar.pack(side="bottom", fill="x")
        self.log_text.pack(side="left", fill="both", expand=True)

        self.log_text.tag_configure("info", foreground="#e2e8f0")
        self.log_text.tag_configure("success", foreground="#4ade80")
        self.log_text.tag_configure("warning", foreground="#fbbf24")
        self.log_text.tag_configure("error", foreground="#f87171")
        self.log_text.tag_configure("time", foreground="#64748b")
        self.log_text.configure(state="disabled")

    # ---- 底部 -------------------------------------------------------------
    def _build_footer(self) -> None:
        footer = ttk.Frame(self.root, padding=(14, 6, 14, 12))
        footer.pack(fill="x")

        self.progress_bar = ttk.Progressbar(footer, style="Slim.Horizontal.TProgressbar",
                                            mode="determinate", maximum=100)
        self.progress_bar.pack(fill="x", pady=(2, 10))

        self.btn_start = ttk.Button(footer, text="▶  开始任务", style="Primary.TButton",
                                    command=self._start)
        self.btn_start.pack(side="right")
        self.btn_stop = ttk.Button(footer, text="■  停止", style="Danger.TButton",
                                   command=self._stop, state="disabled")
        self.btn_stop.pack(side="right", padx=(0, 10))

        ttk.Button(footer, text="保存配置", command=self._save_only).pack(side="right", padx=(0, 10))
        ttk.Button(footer, text="打开所在目录", command=self._open_folder).pack(side="left")
        ttk.Button(footer, text="检查更新",
                   command=lambda: self._check_update_async(silent=False)).pack(side="left", padx=(10, 0))

        self.status_dot = tk.Label(footer, text="●", fg="#9ca3af", bg=PAGE_BG,
                                   font=("Microsoft YaHei UI", 10, "bold"))
        self.status_dot.pack(side="left", padx=(12, 5))
        ttk.Label(footer, textvariable=self.var_status, style="Hint.TLabel").pack(side="left")
        ttk.Label(footer, textvariable=self.var_elapsed, style="Hint.TLabel").pack(
            side="left", padx=(12, 0))

    def _card(self, parent: tk.Misc, title: str) -> ttk.LabelFrame:
        frame = ttk.LabelFrame(parent, text="  " + title + "  ", padding=(10, 6))
        return frame

    # -- 配置 <-> 表单 -------------------------------------------------------
    def _load_config_into_form(self) -> None:
        cp = load_raw_config()
        self.var_username.set(cfg_get(cp, "common", "username", ""))
        self.var_password.set(cfg_get(cp, "common", "password", ""))
        self.var_use_cookies.set(cfg_bool(cp, "common", "use_cookies", False))

        course_list = cfg_get(cp, "common", "course_list", "")
        if course_list and "xxx" not in course_list:
            self.var_course_ids.set(course_list)

        self.var_speed.set(cfg_get(cp, "common", "speed", "1.0") or "1.0")
        self.var_jobs.set(cfg_get(cp, "common", "jobs", "4") or "4")
        notopen = cfg_get(cp, "common", "notopen_action", "retry")
        self.var_notopen.set("continue" if notopen == "continue" else "retry")
        self.var_retry_interval.set(cfg_get(cp, "common", "retry_interval", "1.0") or "1.0")
        self.var_redo_enabled.set(cfg_bool(cp, "common", "work_redo_enabled", False))
        self.var_redo_times.set(cfg_get(cp, "common", "work_max_retries", "3") or "3")
        self.var_add_count.set(cfg_bool(cp, "common", "add_learning_count", False))
        self.var_target_count.set(cfg_get(cp, "common", "target_count", "100") or "100")

        provider = cfg_get(cp, "tiku", "provider", "TikuYanxi")
        self.var_provider.set("" if provider in {"xxx", None} else provider)
        self.var_tokens.set(cfg_get(cp, "tiku", "tokens", ""))
        self.var_submit.set(cfg_bool(cp, "tiku", "submit", False))
        self.var_cover_rate.set(cfg_get(cp, "tiku", "cover_rate", "0.9") or "0.9")
        self.var_delay.set(cfg_get(cp, "tiku", "delay", "1.0") or "1.0")
        self.var_endpoint.set(cfg_get(cp, "tiku", "endpoint", ""))
        self.var_key.set(cfg_get(cp, "tiku", "key", ""))
        self.var_model.set(cfg_get(cp, "tiku", "model", ""))
        self.var_sf_key.set(cfg_get(cp, "tiku", "siliconflow_key", ""))
        self.var_tiku_url.set(cfg_get(cp, "tiku", "url", ""))

        self.var_notify_provider.set(cfg_get(cp, "notification", "provider", "ServerChan"))
        self.var_notify_url.set(cfg_get(cp, "notification", "url", ""))
        self.var_tg_chat.set(cfg_get(cp, "notification", "tg_chat_id", ""))

        self._toggle_cookie_mode()

    def _toggle_cookie_mode(self) -> None:
        state = "disabled" if self.var_use_cookies.get() else "normal"
        self.ent_username.configure(state=state)
        self.ent_password.configure(state=state)

    def _toggle_password(self) -> None:
        self.ent_password.configure(show="" if self.var_show_password.get() else "*")

    def _collect_config(self) -> dict:
        return {
            "username": self.var_username.get().strip(),
            "password": self.var_password.get(),
            "use_cookies": self.var_use_cookies.get(),
            "course_ids": self._resolve_course_ids(),
            "speed": self.var_speed.get().strip() or "1.0",
            "jobs": self.var_jobs.get().strip() or "4",
            "notopen": self.var_notopen.get(),
            "retry_interval": self.var_retry_interval.get().strip() or "1.0",
            "redo_enabled": self.var_redo_enabled.get(),
            "redo_times": self.var_redo_times.get().strip() or "3",
            "add_count": self.var_add_count.get(),
            "target_count": self.var_target_count.get().strip() or "100",
            "provider": self.var_provider.get().strip(),
            "tokens": self.var_tokens.get().strip(),
            "submit": self.var_submit.get(),
            "cover_rate": self.var_cover_rate.get().strip() or "0.9",
            "delay": self.var_delay.get().strip() or "1.0",
        }

    def _resolve_course_ids(self) -> str:
        """返回写入配置的 course_list 字符串；空字符串表示学习全部课程。"""
        selected = self.course_tree.selection()
        ids: list[str] = []
        for item in selected:
            values = self.course_tree.item(item, "values")
            if len(values) >= 3:
                cid = str(values[2]).strip()
                if cid and cid not in ids:
                    ids.append(cid)
        if ids:
            return ",".join(ids)
        manual = self.var_course_ids.get().strip()
        if manual:
            return manual
        if self.var_all_courses.get():
            # main.filter_courses 识别 "all" 为全部课程，避免走 input() 交互
            return "all"
        return ""

    def _write_config(self) -> str:
        """把表单写回 config.ini，保留模板中的注释与未在界面暴露的键。"""
        cp = load_raw_config()

        def setv(section: str, key: str, value) -> None:
            if not cp.has_section(section):
                cp.add_section(section)
            cp.set(section, key, str(value))

        cfg = self._collect_config()
        setv("common", "use_cookies", "true" if cfg["use_cookies"] else "false")
        setv("common", "username", cfg["username"] or "xxx")
        setv("common", "password", cfg["password"] or "xxx")
        setv("common", "course_list", cfg["course_ids"])
        setv("common", "speed", cfg["speed"])
        setv("common", "jobs", cfg["jobs"])
        setv("common", "notopen_action", cfg["notopen"])
        setv("common", "retry_interval", cfg["retry_interval"])
        setv("common", "work_redo_enabled", "true" if cfg["redo_enabled"] else "false")
        setv("common", "work_max_retries", cfg["redo_times"])
        setv("common", "add_learning_count", "true" if cfg["add_count"] else "false")
        setv("common", "target_count", cfg["target_count"])

        setv("tiku", "provider", cfg["provider"])
        setv("tiku", "tokens", cfg["tokens"])
        setv("tiku", "submit", "true" if cfg["submit"] else "false")
        setv("tiku", "cover_rate", cfg["cover_rate"])
        setv("tiku", "delay", cfg["delay"])
        setv("tiku", "endpoint", self.var_endpoint.get().strip())
        setv("tiku", "key", self.var_key.get().strip())
        setv("tiku", "model", self.var_model.get().strip())
        setv("tiku", "siliconflow_key", self.var_sf_key.get().strip())
        setv("tiku", "url", self.var_tiku_url.get().strip())

        setv("notification", "provider", self.var_notify_provider.get().strip())
        setv("notification", "url", self.var_notify_url.get().strip())
        setv("notification", "tg_chat_id", self.var_tg_chat.get().strip())

        # 补齐代码中必读的键，避免用户的旧配置缺项导致 KeyError
        defaults = {
            "check_llm_connection": "true",
            "likeapi_search": "false",
            "likeapi_vision": "true",
            "likeapi_model": "glm-4.5-air",
            "likeapi_retry": "true",
            "likeapi_retry_times": "3",
            "go_authorization": "",
            "go_min_interval": "1.0",
            "go_retry_times": "3",
            "go_retry_backoff": "1.2",
            "min_interval_seconds": "3",
            "http_proxy": "",
            "siliconflow_model": "deepseek-ai/DeepSeek-V3",
            "siliconflow_endpoint": "https://api.siliconflow.cn/v1/chat/completions",
            "manual_mode_default": "batch",
            "manual_mode_separator": ";",
            "true_list": "正确,对,√,是",
            "false_list": "错误,错,×,否,不对,不正确",
        }
        for key, value in defaults.items():
            if not cp.has_option("tiku", key):
                cp.set("tiku", key, value)

        config_path = Path(CONFIG_PATH).resolve()
        # 写前校验：配置必须落在工作目录内，防止路径被拼接出 ../
        if not config_path.is_relative_to(Path(WORK_DIR).resolve()):
            raise OSError(f"配置路径越界: {config_path}")
        with config_path.open("w", encoding="utf-8") as fp:
            cp.write(fp)
        return CONFIG_PATH

    # -- 课程列表 -----------------------------------------------------------
    def _fetch_courses(self) -> None:
        if self.running:
            messagebox.showinfo("提示", "任务运行中，暂不能获取课程列表。", parent=self.root)
            return
        if self.var_use_cookies.get():
            messagebox.showinfo("提示", "Cookie 登录模式下暂不支持拉取课程列表，请手动填写课程 ID，\n"
                                        "或取消勾选后使用手机号密码获取。", parent=self.root)
            return
        username = self.var_username.get().strip()
        password = self.var_password.get()
        if not username or not password:
            messagebox.showwarning("缺少信息", "请先填写手机号与密码。", parent=self.root)
            return

        self.btn_fetch.configure(state="disabled")
        self._set_status("正在登录并获取课程列表…", "run")
        self._append_log(">>> 正在登录并获取课程列表…")

        threading.Thread(target=self._fetch_worker, args=(username, password), daemon=True).start()

    def _fetch_worker(self, username: str, password: str) -> None:
        try:
            from api.answer import DummyTiku
            from api.base import Account, Chaoxing

            tiku = DummyTiku()
            tiku.DISABLE = True
            chaoxing = Chaoxing(account=Account(username, password), tiku=tiku)
            state = chaoxing.login(login_with_cookies=False)
            if not state.get("status"):
                raise RuntimeError(state.get("msg") or "登录失败")
            courses = chaoxing.get_course_list()
            self.root.after(0, lambda: self._fill_courses(courses))
        except BaseException as exc:  # noqa: BLE001
            detail = f"{type(exc).__name__}: {exc}"
            self.root.after(0, lambda: self._fetch_failed(detail))

    def _fill_courses(self, courses: list) -> None:
        for item in self.course_tree.get_children():
            self.course_tree.delete(item)
        for i, course in enumerate(courses):
            self.course_tree.insert(
                "", "end",
                values=(course.get("title", ""), course.get("clazz", ""),
                        course.get("courseId", ""), course.get("clazzId", "")),
                tags=("odd",) if i % 2 else (),
            )
        self._update_course_count()
        self.btn_fetch.configure(state="normal")
        self._set_status(f"课程列表已加载，共 {len(courses)} 条", "ok")
        self._append_log(f">>> 课程列表加载完成，共 {len(courses)} 条，请在列表中多选要学习的课程。", "success")

    def _fetch_failed(self, detail: str) -> None:
        self.btn_fetch.configure(state="normal")
        self._set_status("获取课程列表失败", "error")
        self._append_log(f">>> 获取课程列表失败：{detail}", "error")
        messagebox.showerror("获取失败", f"获取课程列表失败：\n{detail}", parent=self.root)

    def _select_all_courses(self, select: bool) -> None:
        if select:
            self.course_tree.selection_set(self.course_tree.get_children())
        else:
            self.course_tree.selection_remove(self.course_tree.get_children())

    def _update_course_count(self) -> None:
        n = len(self.course_tree.selection())
        self.var_course_count.set(f"已选 {n} 门课程" if n else "未选择课程")

    # -- input() 接管 -------------------------------------------------------
    def _install_input_hook(self) -> None:
        import builtins

        if self._orig_input is not None:
            return
        self._orig_input = builtins.input
        builtins.input = self._gui_input

    def _gui_input(self, prompt: str = "") -> str:
        """后台线程调用 input() 时，切到主线程弹窗并阻塞等待结果。"""
        if threading.current_thread() is threading.main_thread():
            return simpledialog.askstring("需要输入", str(prompt), parent=self.root) or ""

        holder: dict[str, str] = {}
        done = threading.Event()

        def show() -> None:
            try:
                holder["value"] = simpledialog.askstring("需要输入", str(prompt), parent=self.root) or ""
            except Exception:
                holder["value"] = ""
            finally:
                done.set()

        self.root.after(0, show)
        done.wait()
        return holder.get("value", "")

    # -- 任务控制 -----------------------------------------------------------
    def _collect_and_validate(self) -> tuple[bool, str]:
        if not self.var_use_cookies.get():
            if not self.var_username.get().strip() or not self.var_password.get():
                return False, "请填写手机号与密码，或勾选使用 cookies.txt 登录。"
        try:
            speed = float(self.var_speed.get())
            if not 1.0 <= speed <= 2.0:
                return False, "倍速需在 1.0 ~ 2.0 之间。"
        except ValueError:
            return False, "倍速必须是数字。"

        for name, raw, cast in (("同时进行章节数", self.var_jobs.get(), int),
                                ("失败重试间隔", self.var_retry_interval.get(), float),
                                ("最大重做次数", self.var_redo_times.get(), int),
                                ("目标总次数", self.var_target_count.get(), int),
                                ("查询间隔", self.var_delay.get(), float),
                                ("最低覆盖率", self.var_cover_rate.get(), float)):
            try:
                cast(raw)
            except (TypeError, ValueError):
                return False, f"「{name}」填写有误，应为数字。"

        if not self._resolve_course_ids():
            return False, "请选择要学习的课程，或勾选「学习全部课程」。"
        return True, ""

    def _save_only(self) -> None:
        try:
            path = self._write_config()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("保存失败", f"{type(exc).__name__}: {exc}", parent=self.root)
            return
        self._set_status("配置已保存", "ok")
        self._append_log(f">>> 配置已保存到：{path}", "success")
        messagebox.showinfo("已保存", f"配置已保存到：\n{path}", parent=self.root)

    def _start(self) -> None:
        if self.running:
            return
        ok, msg = self._collect_and_validate()
        if not ok:
            messagebox.showwarning("无法开始", msg, parent=self.root)
            return

        try:
            config_path = self._write_config()
        except Exception as exc:  # noqa: BLE001
            messagebox.showerror("配置写入失败", f"{type(exc).__name__}: {exc}", parent=self.root)
            return

        self.running = True
        self.btn_start.configure(state="disabled")
        self.btn_stop.configure(state="normal")
        self.btn_fetch.configure(state="disabled")
        self._set_status("任务运行中…", "run")
        self.var_progress.set("")
        self._run_started_at = time.time()
        self.var_elapsed.set("已运行 00:00")
        self._reset_progressbar()
        self.notebook.select(self.tab_log)
        self._append_log("=" * 60)
        self._append_log(f">>> 任务启动，配置文件：{config_path}", "success")

        threading.Thread(target=self._run_worker, args=(config_path,), daemon=True).start()

    def _run_worker(self, config_path: str) -> None:
        try:
            sys.argv = ["chaoxing-gui", "-c", config_path]
            run_main()
        except SystemExit as exc:  # main() 正常/异常退出都会走到这里
            if exc.code not in (None, 0):
                self._append_log(f">>> 程序退出，返回码：{exc.code}", "warning")
        except BaseException as exc:  # noqa: BLE001
            self._append_log(f">>> 运行出错：{type(exc).__name__}: {exc}", "error")
            self._append_log(traceback.format_exc(), "error")
        finally:
            self.root.after(0, self._on_finished)

    def _on_finished(self) -> None:
        self.running = False
        self.btn_start.configure(state="normal")
        self.btn_stop.configure(state="disabled")
        self.btn_fetch.configure(state="normal")
        self._set_status("已结束", "idle")
        self.var_progress.set("")
        self._run_started_at = None
        self.var_elapsed.set("")
        self._reset_progressbar()
        self._append_log(">>> 任务已结束", "success")

    def _stop(self) -> None:
        if not self.running:
            return
        if not messagebox.askyesno(
            "确认停止",
            "停止会立即结束程序，正在上报的学习进度可能丢失。\n确定要停止吗？",
            parent=self.root,
        ):
            return
        self._append_log(">>> 用户请求停止，正在退出…", "warning")
        os._exit(1)

    def _open_folder(self) -> None:
        try:
            os.startfile(WORK_DIR)  # type: ignore[attr-defined]
        except Exception:
            messagebox.showinfo("目录位置", WORK_DIR, parent=self.root)

    def _on_close(self) -> None:
        if self.running:
            if not messagebox.askyesno("确认退出", "任务仍在运行，退出将中断任务。确定退出吗？",
                                       parent=self.root):
                return
            os._exit(0)
        self.root.destroy()

    # -- 检查更新 -----------------------------------------------------------
    @staticmethod
    def _ver_tuple(version: str) -> tuple[int, ...]:
        """只取前导数字段（v1.2.3-rc1 → (1, 2, 3)），预发布后缀不算更新。"""
        m = re.match(r"\s*v?(\d+(?:\.\d+)*)", version)
        return tuple(int(x) for x in m.group(1).split(".")) if m else (0,)

    def _check_update_async(self, silent: bool = True) -> None:
        if self.running and silent:
            return  # 任务运行中不做启动检查，避免打扰
        if silent:
            self._set_status("正在检查更新…", "idle")
        threading.Thread(target=self._check_update_worker, args=(silent,), daemon=True).start()

    def _check_update_worker(self, silent: bool) -> None:
        """后台查询 GitHub Releases 最新版本；silent 模式下失败完全静默。"""
        try:
            import requests

            resp = requests.get(
                RELEASE_API,
                timeout=8,
                headers={"Accept": "application/vnd.github+json",
                         "User-Agent": f"ChaoxingHelper/{APP_VERSION}"},
            )
            resp.raise_for_status()
            info = resp.json()
            latest = str(info.get("tag_name") or "").lstrip("vV").strip()
            if not latest:
                raise ValueError("发布信息里没有 tag_name")
            self.root.after(0, lambda: self._on_update_checked(silent, latest, info))
        except Exception as exc:  # noqa: BLE001
            if not silent:
                self.root.after(
                    0, lambda e=exc: messagebox.showwarning(
                        "检查更新失败", f"无法获取更新信息：\n{e}", parent=self.root))

    def _on_update_checked(self, silent: bool, latest: str, info: dict) -> None:
        if self._ver_tuple(latest) > self._ver_tuple(APP_VERSION):
            self._set_status(f"发现新版本 v{latest}", "warn")
            self._append_log(f">>> 发现新版本 v{latest}（当前 v{APP_VERSION}），点击「检查更新」获取", "warning")
            notes = (info.get("body") or "").strip()
            if len(notes) > 500:
                notes = notes[:500] + "…"
            if messagebox.askyesno(
                    "发现新版本",
                    f"最新版本 v{latest}（当前 v{APP_VERSION}）\n\n{notes}\n\n是否打开下载页面？",
                    parent=self.root):
                webbrowser.open(info.get("html_url") or RELEASE_PAGE)
        elif silent:
            self._set_status("就绪", "idle")
        else:
            self._set_status(f"已是最新版本 v{APP_VERSION}", "ok")
            messagebox.showinfo("已是最新", f"当前 v{APP_VERSION} 已是最新版本。", parent=self.root)

    # -- 状态与进度 ---------------------------------------------------------
    def _set_status(self, text: str, tone: str = "idle") -> None:
        self.var_status.set(text)
        dot = getattr(self, "status_dot", None)
        if dot is not None:
            dot.configure(foreground=_STATUS_COLORS.get(tone, "#9ca3af"))

    def _reset_progressbar(self) -> None:
        if self._pb_indeterminate:
            self.progress_bar.stop()
            self._pb_indeterminate = False
        self.progress_bar.configure(mode="determinate", value=0)

    def _update_progressbar(self, text: str) -> None:
        """tqdm 行有百分比则显示真实进度，否则转为流动动画。"""
        m = _PCT_RE.search(text)
        if m:
            self._reset_progressbar()
            self.progress_bar.configure(value=int(m.group(1)))
        elif not self._pb_indeterminate:
            self.progress_bar.configure(mode="indeterminate")
            self.progress_bar.start(40)
            self._pb_indeterminate = True

    def _bind_shortcuts(self) -> None:
        self.root.bind("<Control-s>", lambda _e: self._save_only())
        self.root.bind("<Control-Return>", lambda _e: self._start())

    # -- 日志渲染 -----------------------------------------------------------
    def _append_log(self, text: str, level: str | None = None) -> None:
        if level is None:
            upper = text.upper()
            if "ERROR" in upper or "错误" in text or "失败" in text:
                level = "error"
            elif "WARNING" in upper or "警告" in text:
                level = "warning"
            elif "成功" in text or "完成" in text or "SUCCESS" in upper:
                level = "success"
            else:
                level = "info"

        self.log_text.configure(state="normal")
        if text.startswith("="):
            # 分隔线不加时间戳，保持整齐
            self.log_text.insert("end", text + "\n", level)
        else:
            self.log_text.insert("end", time.strftime("%H:%M:%S") + "  ", "time")
            self.log_text.insert("end", text + "\n", level)
        # 限制总行数，避免长时间运行后卡顿
        line_count = int(self.log_text.index("end-1c").split(".")[0])
        if line_count > 4000:
            self.log_text.delete("1.0", f"{line_count - 3000}.0")
        if self.var_autoscroll.get():
            self.log_text.see("end")
        self.log_text.configure(state="disabled")

    def _clear_log(self) -> None:
        self.log_text.configure(state="normal")
        self.log_text.delete("1.0", "end")
        self.log_text.configure(state="disabled")

    def _copy_log(self) -> None:
        content = self.log_text.get("1.0", "end-1c")
        self.root.clipboard_clear()
        self.root.clipboard_append(content)
        self._set_status("日志已复制到剪贴板")

    def _poll_log(self) -> None:
        batch: list[tuple[str, str]] = []
        try:
            while len(batch) < 300:
                batch.append(LOG_QUEUE.get_nowait())
        except queue.Empty:
            pass

        for kind, text in batch:
            if kind == "progress":
                self.var_progress.set(text[-110:])
                self._update_progressbar(text)
            else:
                self._append_log(text)

        if self.running and self._run_started_at is not None:
            secs = int(time.time() - self._run_started_at)
            self.var_elapsed.set(f"已运行 {secs // 60:02d}:{secs % 60:02d}")

        self.root.after(120, self._poll_log)


def main() -> None:
    root = tk.Tk()
    try:
        # 高分屏下避免界面模糊
        from ctypes import windll

        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    ChaoxingGUI(root)
    root.mainloop()


if __name__ == "__main__":
    main()
