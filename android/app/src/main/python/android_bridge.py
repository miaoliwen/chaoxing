# -*- coding: utf-8 -*-
"""Android 桥接层：Kotlin(Chaquopy) <-> Python 核心（core.zip 内的 api/ + main.py）。

职责：
1. 启动时把 core.zip 挂到 sys.path（zipimport），chdir 到 App filesDir；
2. 接管 stdout/stderr，把 print/loguru/tqdm 输出推给 Java 回调；
3. 接管 input()，交互问题自动取默认值（避免后台线程挂起）；
4. 提供 fetch_courses / write_config / start_task 三个入口给 Kotlin 调。
"""
from __future__ import annotations

import configparser
import io
import os
import re
import sys
import threading
import time
import zipfile
from pathlib import Path

_HERE = os.path.dirname(os.path.abspath(__file__))
_CORE_ZIP = os.path.join(_HERE, "core.zip")
_ANSI_RE = re.compile(r"\x1b\[[0-9;]*m")

# Kotlin 侧注入的日志回调（com.chaquo.python.PyObject）
_log_callback = None
_initialized = False
_init_lock = threading.Lock()


class _StreamProxy(io.TextIOBase):
    """把 print / tqdm / loguru 的输出按行推给 Java 回调。"""

    def __init__(self, stream_name: str) -> None:
        super().__init__()
        self._name = stream_name
        self._buf = ""
        self._lock = threading.Lock()

    @property
    def encoding(self) -> str:
        return "utf-8"

    def isatty(self) -> bool:
        return False

    def writable(self) -> bool:
        return True

    def _emit(self, kind: str, text: str) -> None:
        cb = _log_callback
        if cb is None:
            return
        try:
            cb.accept(kind, _ANSI_RE.sub("", text))
        except Exception:
            pass  # 回调异常绝不能打断业务线程

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
                        self._emit("line", line)
                else:
                    seg, self._buf = self._buf[:r], self._buf[r + 1:]
                    if seg.strip():
                        self._emit("progress", seg.strip())
            if len(self._buf) > 8192:
                self._emit("line", self._buf[-2000:])
                self._buf = ""
        return len(s)

    def flush(self) -> None:
        pass


def _default_input(prompt: str = "") -> str:
    """接管交互输入：大模型连接检查等 Y/n 问题一律取'继续'。"""
    print(f"[Android] 交互输入自动确认: {prompt}")
    return "y"


def init(work_dir: str, log_callback) -> None:
    """Kotlin 启动时调用：加载核心、设置工作目录与流接管。"""
    global _log_callback, _initialized
    with _init_lock:
        if _initialized:
            _log_callback = log_callback
            return
        _log_callback = log_callback
        os.makedirs(work_dir, exist_ok=True)
        os.chdir(work_dir)
        # core.zip 解压到工作目录后挂 sys.path
        # （Chaquopy 的导入钩子不认 zipimport，必须用真实目录走 FileFinder；
        #   每次无条件重解压，保证核心代码随 APK 更新）
        core_dir = os.path.join(work_dir, "python_core")
        with zipfile.ZipFile(_CORE_ZIP) as zf:
            zf.extractall(core_dir)
        if core_dir not in sys.path:
            sys.path.insert(0, core_dir)
        # 字体映射表解到工作目录（cxsecret_font.resource_path 走 cwd 相对路径）
        res_file = Path(work_dir) / "resource" / "font_map_table.json"
        if not res_file.exists():
            try:
                with zipfile.ZipFile(_CORE_ZIP) as zf:
                    zf.extract("resource/font_map_table.json", work_dir)
            except Exception as exc:  # noqa: BLE001
                print(f"[Bridge] 字体映射表解压失败: {exc}")
        # 接管标准流与 input
        sys.stdout = _StreamProxy("stdout")
        sys.stderr = _StreamProxy("stderr")
        import builtins

        builtins.input = _default_input
        _initialized = True
        print(f"[Bridge] Python 核心就绪 work_dir={work_dir}")


def _new_parser() -> configparser.ConfigParser:
    return configparser.ConfigParser(interpolation=None)


def write_config(values: dict, work_dir: str) -> str:
    """按 gui.py _write_config 同款键位生成 config.ini，返回路径。"""
    cp = _new_parser()
    config_path = (Path(work_dir) / "config.ini").resolve()
    # 写前校验：配置必须落在工作目录内，防止路径拼接越界
    if not config_path.is_relative_to(Path(work_dir).resolve()):
        raise OSError(f"配置路径越界: {config_path}")
    path = str(config_path)
    if config_path.exists():
        cp.read(path, encoding="utf-8")
    for section in ("common", "tiku", "notification"):
        if not cp.has_section(section):
            cp.add_section(section)

    def setv(section: str, key: str, value) -> None:
        cp.set(section, key, str(value))

    setv("common", "use_cookies", "true" if values.get("use_cookies") else "false")
    setv("common", "username", values.get("username") or "xxx")
    setv("common", "password", values.get("password") or "xxx")
    setv("common", "course_list", values.get("course_list") or "")
    setv("common", "speed", values.get("speed") or "1.0")
    setv("common", "jobs", values.get("jobs") or "4")
    setv("common", "notopen_action", values.get("notopen") or "retry")
    setv("common", "retry_interval", values.get("retry_interval") or "1.0")
    setv("common", "work_redo_enabled", "true" if values.get("redo_enabled") else "false")
    setv("common", "work_max_retries", values.get("redo_times") or "3")
    setv("common", "add_learning_count", "true" if values.get("add_count") else "false")
    setv("common", "target_count", values.get("target_count") or "100")

    setv("tiku", "provider", values.get("provider") or "")
    setv("tiku", "tokens", values.get("tokens") or "")
    setv("tiku", "submit", "true" if values.get("submit") else "false")
    setv("tiku", "cover_rate", values.get("cover_rate") or "0.9")
    setv("tiku", "delay", values.get("delay") or "1.0")
    setv("tiku", "endpoint", values.get("endpoint") or "")
    setv("tiku", "key", values.get("key") or "")
    setv("tiku", "model", values.get("model") or "")
    setv("tiku", "siliconflow_key", values.get("siliconflow_key") or "")
    setv("tiku", "url", values.get("url") or "")

    setv("notification", "provider", values.get("notify_provider") or "")
    setv("notification", "url", values.get("notify_url") or "")
    setv("notification", "tg_chat_id", values.get("tg_chat_id") or "")

    # 与 gui.py 相同的默认键补齐，避免旧配置缺项
    defaults = {
        "check_llm_connection": "false",  # 安卓无 openai SDK，跳过连接检查
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

    with config_path.open("w", encoding="utf-8") as fp:
        cp.write(fp)
    return path


def fetch_courses(username: str, password: str) -> str:
    """登录并拉取课程列表（阻塞，Kotlin 侧放 IO 线程）。返回 JSON 数组字符串。"""
    import json

    from api.answer import DummyTiku
    from api.base import Account, Chaoxing

    tiku = DummyTiku()
    tiku.DISABLE = True
    chaoxing = Chaoxing(account=Account(username, password), tiku=tiku)
    state = chaoxing.login(login_with_cookies=False)
    if not state.get("status"):
        raise RuntimeError(state.get("msg") or "登录失败")
    courses = chaoxing.get_course_list()
    data = [
        {
            "title": str(c.get("title", "")),
            "clazz": str(c.get("clazz", "")),
            "courseId": str(c.get("courseId", "")),
            "clazzId": str(c.get("clazzId", "")),
        }
        for c in courses
    ]
    return json.dumps(data, ensure_ascii=False)


def start_task(config_path: str) -> str:
    """运行 main.main()（阻塞，前台服务线程调用）。返回结束码描述。"""
    sys.argv = ["chaoxing-android", "-c", config_path]
    try:
        from main import main as run_main

        run_main()
        return "ok"
    except SystemExit as exc:
        return f"exit:{exc.code}"
    except BaseException:
        import traceback

        print("[Bridge] 任务异常栈:\n" + traceback.format_exc())
        raise
