# -*- coding: utf-8 -*-
"""Nuxt2 SSR payload 解析器（纯 Python，无第三方依赖）。

背景
----
Nuxt2 的 SSR 页面会把整页数据压进一个立即执行函数（IIFE）里：

    window.__NUXT__=(function(a,b,c,...){return {layout:"default",data:[{...}]}}
                     (231,"xxx",{...},...))

为了减小 HTML 体积，打包时把重复出现的值抽成函数**形参**，正文里只留最短的
标识符引用：

    {goodsNo:"PW2MGN2", price:f, gameId:a, title:"..."}

其中 `f` 是第 6 个形参，对应调用时传入的第 6 个实参（比如 1999）。
所以想拿到准确值，必须建立「形参名 -> 实参值」的映射表（var_map），
取值时遇到标识符就查表。

本模块做的事
------------
1. 从 HTML 里切出 `window.__NUXT__=` 后面的表达式
2. 解析 IIFE：提取形参名列表 + 实参文本列表
3. 用递归下降解析器把函数体（一个 JS 对象字面量）转成 Python 对象
   - 字符串 / 数字 / 布尔 / null 直接转
   - 标识符查 var_map
   - 对象 / 数组递归
   - 函数、运算表达式等无法静态求值的部分返回 None
4. 提供按路径取值（"data.0.goodsList.0.price"）的便捷接口

不依赖 node、不依赖浏览器，服务器上只要有 Python 就能跑。
"""
import json
import re

__all__ = ["Nuxt2Payload", "extract_payload_expr", "parse_iife", "PayloadError"]

_ESCAPE_RE = re.compile(r"\\(u[0-9a-fA-F]{4}|.)")


class PayloadError(RuntimeError):
    """payload 结构异常（找不到 __NUXT__、IIFE 不完整等）。"""


# ---------------------------------------------------------------- 基础工具
def decode_js_string(raw):
    """把 JS 字符串字面量内容解码成 Python str（处理 \\u002F、\\n、\\" 等）。"""
    try:
        return json.loads('"' + raw + '"')
    except Exception:  # noqa: BLE001
        def repl(m):
            seq = m.group(1)
            if seq.startswith("u"):
                return chr(int(seq[1:], 16))
            return {"n": "\n", "t": "\t", "r": "\r", '"': '"', "'": "'", "\\": "\\"}.get(seq, seq)

        return _ESCAPE_RE.sub(repl, raw)


def extract_payload_expr(html):
    """从 HTML 里切出 `window.__NUXT__=` 后面的表达式文本。"""
    idx = html.find("window.__NUXT__=")
    if idx < 0:
        raise PayloadError("页面里没有 window.__NUXT__（不是 Nuxt2 SSR，或者被 CSR 化了）")
    start = idx + len("window.__NUXT__=")
    end = html.find("</script>", start)
    if end < 0:
        end = len(html)
    expr = html[start:end].strip()
    if expr.endswith(";"):
        expr = expr[:-1].rstrip()
    if not expr:
        raise PayloadError("window.__NUXT__ 是空的")
    return expr


def _slice_balanced(text, start, open_ch="{", close_ch="}"):
    """从 start（指向 open_ch）做括号配对，返回 (内部文本, 结束后下标)。"""
    depth = 0
    i = start
    in_str = None
    n = len(text)
    while i < n:
        ch = text[i]
        if in_str:
            if ch == "\\":
                i += 2
                continue
            if ch == in_str:
                in_str = None
            i += 1
            continue
        if ch in ('"', "'", "`"):
            in_str = ch
            i += 1
            continue
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return text[start + 1:i], i + 1
        i += 1
    return text[start + 1:], n


def _split_top_level(text, sep=","):
    """按顶层分隔符切分（跳过字符串与嵌套括号内部）。"""
    parts = []
    depth = 0
    in_str = None
    buf = []
    i = 0
    n = len(text)
    while i < n:
        ch = text[i]
        if in_str:
            buf.append(ch)
            if ch == "\\":
                if i + 1 < n:
                    buf.append(text[i + 1])
                    i += 2
                    continue
            elif ch == in_str:
                in_str = None
            i += 1
            continue
        if ch in ('"', "'", "`"):
            in_str = ch
            buf.append(ch)
        elif ch in "{([":
            depth += 1
            buf.append(ch)
        elif ch in "})]":
            depth -= 1
            buf.append(ch)
        elif ch == sep and depth == 0:
            parts.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
        i += 1
    tail = "".join(buf)
    if tail.strip():
        parts.append(tail)
    return parts


_NUM_RE = re.compile(r"^-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?$")
_IDENT_RE = re.compile(r"^[A-Za-z_$][\w$]*$")
_IDENT_START_RE = re.compile(r"[A-Za-z_$]")


# ---------------------------------------------------------------- IIFE 解析
def parse_iife(expr):
    """解析 `(function(a,b,...){...}(arg1,arg2,...))` 结构。

    返回 (body_text, var_map)：
        body_text  函数体文本（通常是 `return {...}`）
        var_map    形参名 -> 实参原始文本 的字典
    """
    m = re.search(r"function\s*\(([^)]*)\)\s*\{", expr)
    if not m:
        # 少数页面直接是对象字面量，没有包 IIFE
        return expr, {}
    params = [p.strip() for p in m.group(1).split(",") if p.strip()]
    body_open = expr.index("{", m.end() - 1)
    body, body_end = _slice_balanced(expr, body_open, "{", "}")
    if not params:
        return body, {}

    rest = expr[body_end:]
    am = re.match(r"\s*\(", rest)
    if not am:
        return body, {}
    args_open = body_end + am.end() - 1
    args_text, _ = _slice_balanced(expr, args_open, "(", ")")
    parts = _split_top_level(args_text)

    var_map = {}
    for name, raw in zip(params, parts):
        var_map[name] = raw
    return body, var_map


# ---------------------------------------------------------------- 递归下降解析
class _Parser(object):
    """把 JS 字面量文本解析成 Python 对象。

    只处理"静态可求值"的部分：字面量、对象、数组、标识符（查 var_map）。
    遇到函数、运算、三元表达式等无法静态确定的，直接跳过并返回 None。
    """

    def __init__(self, text, var_map):
        self.text = text
        self.i = 0
        self.n = len(text)
        self.var_map = var_map or {}
        self._depth = 0

    # ---------- 位置工具 ----------
    def _skip_ws(self):
        while self.i < self.n and self.text[self.i] in " \t\r\n":
            self.i += 1

    def _peek(self):
        return self.text[self.i] if self.i < self.n else ""

    def _at_end(self):
        return self.i >= self.n

    # ---------- 各类型 ----------
    def parse_value(self):
        self._skip_ws()
        if self._at_end():
            return None
        ch = self._peek()
        if ch == "{":
            return self.parse_object()
        if ch == "[":
            return self.parse_array()
        if ch in ('"', "'", "`"):
            return self.parse_string()
        if ch == "-" or ch.isdigit():
            return self.parse_number()
        if _IDENT_START_RE.match(ch):
            return self.parse_identifier()
        # 其他（函数、运算等）：整段跳过
        self._skip_expression()
        return None

    def parse_string(self):
        quote = self.text[self.i]
        i = self.i + 1
        n = self.n
        start = i
        while i < n:
            ch = self.text[i]
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                raw = self.text[start:i]
                self.i = i + 1
                return decode_js_string(raw) if quote != "`" else raw
            i += 1
        self.i = n
        return None

    def parse_number(self):
        start = self.i
        while self.i < self.n and self.text[self.i] in "0123456789+-.eE":
            self.i += 1
        raw = self.text[start:self.i]
        if _NUM_RE.match(raw):
            try:
                f = float(raw)
                return int(f) if f == int(f) else f
            except ValueError:
                return None
        return None

    def parse_identifier(self):
        start = self.i
        while self.i < self.n and (self.text[self.i].isalnum() or self.text[self.i] in "_$"):
            self.i += 1
        name = self.text[start:self.i]

        # 关键字
        if name == "true":
            return True
        if name == "false":
            return False
        if name in ("null", "undefined"):
            return None
        if name == "void":
            self._skip_ws()
            if self._peek().isdigit():
                self.parse_number()
            return None

        # 后面跟 ( 或 . 或 [ 说明是函数调用/成员访问，静态求不了
        save = self.i
        self._skip_ws()
        if self._peek() in "(.=[":
            self.i = save
            return None
        self.i = save

        # 查形参映射
        raw = self.var_map.get(name)
        if raw is None:
            return None
        return _evaluate_literal(raw, self.var_map, depth=self._depth + 1)

    def parse_object(self):
        self.i += 1  # 跳过 {
        obj = {}
        while True:
            self._skip_ws()
            if self._at_end():
                break
            if self._peek() == "}":
                self.i += 1
                break
            key = self.parse_key()
            self._skip_ws()
            if self._peek() == ":":
                self.i += 1
            value = self.parse_value()
            if key is not None:
                obj[key] = value
            self._skip_ws()
            if self._peek() == ",":
                self.i += 1
            elif self._peek() == "}":
                self.i += 1
                break
            else:
                self._skip_expression()
                if self._peek() == "}":
                    self.i += 1
                    break
        return obj

    def parse_key(self):
        self._skip_ws()
        ch = self._peek()
        if ch in ('"', "'", "`"):
            return self.parse_string()
        if _IDENT_START_RE.match(ch):
            start = self.i
            while self.i < self.n and (self.text[self.i].isalnum() or self.text[self.i] in "_$"):
                self.i += 1
            return self.text[start:self.i]
        if ch.isdigit():
            return str(self.parse_number())
        self.i += 1
        return None

    def parse_array(self):
        self.i += 1  # 跳过 [
        arr = []
        while True:
            self._skip_ws()
            if self._at_end():
                break
            if self._peek() == "]":
                self.i += 1
                break
            arr.append(self.parse_value())
            self._skip_ws()
            if self._peek() == ",":
                self.i += 1
            elif self._peek() == "]":
                self.i += 1
                break
            else:
                self._skip_expression()
                if self._peek() == "]":
                    self.i += 1
                    break
        return arr

    def _skip_expression(self):
        """跳过一个无法静态求值的表达式（到顶层 , } ] 为止）。"""
        depth = 0
        in_str = None
        while self.i < self.n:
            ch = self.text[self.i]
            if in_str:
                if ch == "\\":
                    self.i += 2
                    continue
                if ch == in_str:
                    in_str = None
                self.i += 1
                continue
            if ch in ('"', "'", "`"):
                in_str = ch
            elif ch in "{([":
                depth += 1
            elif ch in "})]":
                if depth == 0:
                    return
                depth -= 1
            elif ch == "," and depth == 0:
                return
            self.i += 1


def _evaluate_literal(raw, var_map, depth=0):
    """求值一段实参文本（可能还是个标识符引用，要递归查）。"""
    if depth > 8 or raw is None:
        return None
    raw = raw.strip()
    if not raw:
        return None
    # 先处理关键字：这些不是形参引用
    if raw == "true":
        return True
    if raw == "false":
        return False
    if raw in ("null", "undefined", "void 0"):
        return None
    if _IDENT_RE.match(raw):
        nxt = var_map.get(raw)
        if nxt is None or nxt == raw:
            return None
        return _evaluate_literal(nxt, var_map, depth + 1)
    p = _Parser(raw, var_map)
    p._depth = depth
    return p.parse_value()


# ---------------------------------------------------------------- 对外接口
class Nuxt2Payload(object):
    """解析一段 Nuxt2 SSR 页面，提供按路径取值。

    用法::

        from nuxt2_payload import Nuxt2Payload

        p = Nuxt2Payload(html)
        p.get("data.0.goodsList.0.goodsNo")     # -> "PW2MGN2"
        p.get("data.0.goodsList.0.price")       # -> 1999
        p.section("data.0.goodsList")           # -> [ {...}, {...} ]
        p.raw                                   # -> 整个 payload 字典
    """

    def __init__(self, html=None, expr=None, strict=False):
        if expr is None:
            if html is None:
                raise PayloadError("必须给 html 或 expr")
            expr = extract_payload_expr(html)
        self.expr = expr
        self.var_map = {}
        self.raw = None
        self.error = None

        try:
            body, var_map = parse_iife(expr)
            self.var_map = var_map
            self.raw = self._parse_body(body)
        except Exception as exc:  # noqa: BLE001
            self.error = exc
            if strict:
                raise
            self.raw = None

    # ---------- 内部 ----------
    def _parse_body(self, body):
        """函数体一般是 `return {...}`，去掉 return 再解析。

        注意：必须把 var_map 传进解析器，否则形参引用（price:f 这种）解不出来。
        """
        text = body.strip()
        m = re.match(r"return\s+", text)
        if m:
            text = text[m.end():]
        p = _Parser(text, self.var_map)
        return p.parse_value()

    def _resolve(self, path):
        """按 "a.0.b" 这种路径取值。"""
        if self.raw is None:
            return None
        cur = self.raw
        if not path:
            return cur
        for seg in str(path).split("."):
            if seg == "":
                continue
            if isinstance(cur, dict):
                cur = cur.get(seg)
            elif isinstance(cur, (list, tuple)):
                try:
                    cur = cur[int(seg)]
                except (ValueError, IndexError):
                    return None
            else:
                return None
            if cur is None:
                return None
        return cur

    # ---------- 对外 ----------
    def get(self, path, default=None):
        """按路径取一个值，取不到返回 default。"""
        value = self._resolve(path)
        return default if value is None else value

    def section(self, path, default=None):
        """取一段子结构（list 或 dict）。"""
        value = self._resolve(path)
        if isinstance(value, (list, dict)):
            return value
        return default if default is not None else []

    def first(self, path, default=None):
        """取路径下第一个元素（列表场景）。"""
        value = self._resolve(path)
        if isinstance(value, list) and value:
            return value[0]
        return default

    def keys(self):
        return list(self.raw.keys()) if isinstance(self.raw, dict) else []

    def __repr__(self):
        if self.raw is None:
            return "<Nuxt2Payload failed: %s>" % (self.error,)
        return "<Nuxt2Payload keys=%s>" % (",".join(self.keys()[:6]),)
