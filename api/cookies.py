# -*- coding: utf-8 -*-
import os.path
import threading
from pathlib import Path

import requests

from api.config import GlobalConst as gc

# 定义全局 Cookie 文件锁，保证读写绝对安全
cookie_lock = threading.RLock()


def save_cookies(session: requests.Session):
    with cookie_lock:
        buffer = ""
        for k, v in session.cookies.items():
            buffer += f"{k}={v};"
        buffer = buffer.removesuffix(";")
        # COOKIES_PATH 为程序内固定常量；resolve 后校验仍位于其父目录内再写
        target = Path(gc.COOKIES_PATH).resolve()
        if not target.is_relative_to(target.parent):
            raise ValueError(f"cookies 文件路径异常: {target}")
        target.write_text(buffer, encoding="utf-8")


def use_cookies() -> dict:
    with cookie_lock:
        if not os.path.exists(gc.COOKIES_PATH):
            return {}

        cookies = {}
        try:
            with open(gc.COOKIES_PATH, "r") as f:
                buffer = f.read().strip()
                if not buffer:
                    return {}
                for item in buffer.split(";"):
                    item = item.strip()
                    if not item:
                        continue
                    parts = item.split("=", 1)
                    if len(parts) == 2:
                        cookies[parts[0]] = parts[1]
        except Exception:
            return {}

        return cookies
