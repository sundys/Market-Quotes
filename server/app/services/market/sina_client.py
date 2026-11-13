"""新浪外盘（COMEX 期金 / 伦敦金现货）行情客户端：一次请求取全部品种。

背景：akshare 的 `futures_foreign_commodity_realtime` 每次调用都会先抓一遍
`finance.sina.com.cn/money/future/hf.html`（实测 66KB HTML，224ms）来构造
静态的“代码 → 中文名”映射表，然后再请求一次 hq.sinajs.cn。映射表是常量，
每 30 秒重抓一次纯属浪费（每小时 120 次额外请求）。

这里直接请求行情脚本（实测 121 字节 / 214ms），支持一次拉多个品种：
`list=hf_GC,hf_XAU`。字段含义与 akshare 一致：
0 最新价, 4 最高, 5 最低, 6 时间, 7 昨收/昨结算, 8 今开, 12 日期, 13 名称。
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from typing import Dict, List, Optional, Tuple

import requests

logger = logging.getLogger("market.sina")

HQ_URL = "https://hq.sinajs.cn/list={codes}"
MINLINE_URL = ("https://stock2.finance.sina.com.cn/futures/api/jsonp.php/"
               "var%20_{code}=/GlobalFuturesService.getGlobalFuturesMinLine?symbol={code}")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://finance.sina.com.cn/",
}

_LINE_RE = re.compile(r'var hq_str_hf_([A-Za-z0-9]+)="([^"]*)"')
_HHMM_RE = re.compile(r"^\d{1,2}:\d{2}$")


def _to_float(value) -> Optional[float]:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f or f <= 0:
        return None
    return f


def _parse_fields(fields: List[str]) -> dict:
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


def parse_payload(text: str) -> dict:
    """解析单条行情脚本（纯函数，便于测试）。"""
    m = _LINE_RE.search(text or "")
    if not m or not m.group(2).strip():
        raise ValueError("empty sina quote payload")
    return _parse_fields(m.group(2).split(","))


def parse_multi(text: str) -> Dict[str, dict]:
    """解析一次请求返回的多条行情：{code: snapshot}；坏行跳过不影响其它品种。"""
    out: Dict[str, dict] = {}
    for code, payload in _LINE_RE.findall(text or ""):
        if not payload.strip():
            continue
        try:
            out[code.upper()] = _parse_fields(payload.split(","))
        except ValueError as exc:
            logger.warning("skip sina quote %s: %s", code, exc)
    return out


def parse_minline(text: str) -> Tuple[List[str], List[float]]:
    """解析当日分钟线（`minLine_1d`），返回 (时间标签, 价格)。

    行格式有两种：首行 10 列（含日期/交易所），其余 6 列（时间, 价格, …, 均价, 时间戳）。
    """
    start, end = (text or "").find("("), (text or "").rfind(")")
    if start < 0 or end <= start:
        raise ValueError("unexpected sina minline payload")
    data = json.loads(text[start + 1:end])
    rows = data.get("minLine_1d") or []

    labels: List[str] = []
    points: List[float] = []
    for row in rows:
        if not isinstance(row, list) or len(row) < 6:
            continue
        label = row[0] if _HHMM_RE.match(str(row[0])) else str(row[4])
        price = _to_float(row[1] if len(row) == 6 else row[5])
        if price is None:
            continue
        labels.append(label)
        points.append(price)
    if not points:
        raise ValueError("empty sina minline")
    return labels, points


class SinaClient:
    """复用连接的行情客户端；请求带超时，避免线程永久持锁。"""

    def __init__(self, timeout: float = 6.0) -> None:
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(HEADERS)

    def fetch_quotes(self, codes, timeout: Optional[float] = None) -> Dict[str, dict]:
        """一次请求拉多个品种（同一主机、同一响应）。"""
        codes = [str(c).upper() for c in codes]
        r = self._session.get(
            HQ_URL.format(codes=",".join(f"hf_{c}" for c in codes)),
            timeout=timeout or self.timeout,
        )
        r.raise_for_status()
        # 新浪返回 GBK 编码；不显式解码会得到乱码名称
        return parse_multi(r.content.decode("gbk", errors="replace"))

    def fetch_quote(self, code: str = "GC", timeout: Optional[float] = None) -> dict:
        quotes = self.fetch_quotes([code], timeout=timeout)
        snap = quotes.get(code.upper())
        if snap is None:
            raise ValueError(f"empty sina quote for {code}")
        return snap

    def fetch_minline(self, code: str = "XAU", timeout: Optional[float] = None) -> Tuple[List[str], List[float]]:
        r = self._session.get(MINLINE_URL.format(code=code.upper()),
                              timeout=timeout or self.timeout)
        r.raise_for_status()
        return parse_minline(r.content.decode("gbk", errors="replace"))


_client = SinaClient()


def fetch_quote(code: str = "GC", timeout: Optional[float] = None) -> dict:
    """模块级入口：复用同一个 Session 连接池。"""
    return _client.fetch_quote(code, timeout=timeout)


def fetch_quotes(codes, timeout: Optional[float] = None) -> Dict[str, dict]:
    return _client.fetch_quotes(codes, timeout=timeout)


def fetch_minline(code: str = "XAU", timeout: Optional[float] = None) -> Tuple[List[str], List[float]]:
    return _client.fetch_minline(code, timeout=timeout)
