# -*- coding: utf-8 -*-
try:
    import lxml  # noqa: F401
    BS_PARSER = "lxml"
except ImportError:  # 安卓(Chaquopy)环境无 lxml C 扩展，退回内置解析器
    BS_PARSER = "html.parser"


def formatted_output(_status, _text, _data):
    return {"status": _status, "msg": _text, "data": _data}
