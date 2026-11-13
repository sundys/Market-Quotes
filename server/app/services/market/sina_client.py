"""新浪外盘（COMEX 期金）实时行情客户端：一次请求。

背景：akshare 的 `futures_foreign_commodity_realtime` 每次调用都会先抓一遍
`finance.sina.com.cn/money/future/hf.html`（实测 66KB HTML，224ms）来构造
静态的“代码 → 中文名”映射表，然后再请求一次 hq.sinajs.cn。映射表是常量，
每 30 秒重抓一次纯属浪费（每小时 120 次额外请求）。

这里直接请求行情脚本（实测 121 字节 / 214ms），字段含义与 akshare 一致：
0 最新价, 4 最高, 5 最低, 6 时间, 7 昨结算, 8 今开, 12 日期, 13 名称。
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Optional

import requests

logger = logging.getLogger("market.sina")

HQ_URL = "https://hq.sinajs.cn/list=hf_{code}"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://finance.sina.com.cn/",
}

_LINE_RE = re.compile(r'="([^"]*)"')


def _to_float(value) -> Optional[float]:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f or f <= 0:
        return None
    return f


def parse_payload(text: str) -> dict:
    """解析新浪外盘行情脚本（纯函数，便于测试）。"""
    m = _LINE_RE.search(text or "")
    if not m or not m.group(1).strip():
        raise ValueError("empty sina quote payload")
    fields = m.group(1).split(",")
    if len(fields) < 14:
        raise ValueError(f"unexpected sina field count: {len(fields)}")

    price = _to_float(fields[0])
    if price is None:
        raise ValueError(f"invalid sina price: {fields[0]!r}")

    ts = None
    try:
        ts = datetime.strptime(f"{fields[12]} {fields[6]}", "%Y-%m-%d %H:%M:%S")
    except ValueError:
        logger.warning("sina timestamp unparsable: %r %r", fields[12], fields[6])

    return {
        "name": fields[13].strip(),
        "price": price,
        "prev_settlement": _to_float(fields[7]),
        "open": _to_float(fields[8]),
        "high": _to_float(fields[4]),
        "low": _to_float(fields[5]),
        "timestamp": ts or datetime.now(),
    }


class SinaClient:
    """复用连接的行情客户端；请求带超时，避免线程永久持锁。"""

    def __init__(self, timeout: float = 6.0) -> None:
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(HEADERS)

    def fetch_quote(self, code: str = "GC", timeout: Optional[float] = None) -> dict:
        r = self._session.get(HQ_URL.format(code=code), timeout=timeout or self.timeout)
        r.raise_for_status()
        # 新浪返回 GBK 编码；不显式解码会得到乱码名称
        text = r.content.decode("gbk", errors="replace")
        return parse_payload(text)


_client = SinaClient()


def fetch_quote(code: str = "GC", timeout: Optional[float] = None) -> dict:
    """模块级入口：复用同一个 Session 连接池。"""
    return _client.fetch_quote(code, timeout=timeout)
