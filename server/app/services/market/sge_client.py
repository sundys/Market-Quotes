"""上海黄金交易所实时行情客户端：一次请求拿到全部字段。

背景：akshare 的 `spot_quotations_sge` 与这里请求的是同一个公开接口
（https://www.sge.com.cn/graph/quotations），但它只保留 品种/时间/现价/更新时间，
把同一份响应里的 max / min / data（当日分钟序列）丢掉了；项目里为了拿开高低
又直连了一次同一个 URL，等于每 30 秒打两次同一接口，还额外多一次
`spot_hist_sge`（2402 行）。

现在改为直接解析该接口的原始响应，一次请求即可得到：
现价、今开（首个有效价）、最高、最低、**真实行情时间**（delaystr）、日内序列。

akshare 仍然负责日线历史（`spot_hist_sge`），见 akshare_service。
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import List, Optional

import requests

logger = logging.getLogger("market.sge")

QUOTATIONS_URL = "https://www.sge.com.cn/graph/quotations"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.sge.com.cn/",
    "X-Requested-With": "XMLHttpRequest",
}

# 首页/详情只需要趋势，序列下采样到 60 点，避免响应体膨胀
MAX_SPARKLINE_POINTS = 60

_DELAY_RE = re.compile(
    r"(\d{4})\s*[年\-/]\s*(\d{1,2})\s*[月\-/]\s*(\d{1,2})\s*日?\s+"
    r"(\d{1,2}):(\d{2})(?::(\d{2}))?"
)


def parse_delaystr(raw) -> Optional[datetime]:
    """解析 "2026年11月13日 15:45:00" / "2026-11-13 15:45:00"；失败返回 None。

    这是数据源给出的行情时间，必须优先于服务器当前时间使用
    （AGENTS.md 第 9/39 节：不能把采集时间当成行情时间）。
    """
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    m = _DELAY_RE.search(text)
    if m:
        year, month, day, hour, minute, second = m.groups()
        try:
            return datetime(int(year), int(month), int(day),
                            int(hour), int(minute), int(second or 0))
        except ValueError:
            return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return datetime.strptime(text, fmt)
        except ValueError:
            continue
    return None


def _to_float(value) -> Optional[float]:
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if f != f or f <= 0:  # NaN / 非正数一律视为缺失
        return None
    return f


def _downsample(values: List[float], limit: int = MAX_SPARKLINE_POINTS) -> List[float]:
    """等距下采样，保留首尾点，保证趋势形状不变。"""
    if len(values) <= limit:
        return list(values)
    step = len(values) / float(limit)
    picked = [values[int(i * step)] for i in range(limit)]
    picked[-1] = values[-1]
    return picked


def parse_payload(payload: dict, now: Optional[datetime] = None) -> dict:
    """把 SGE 原始响应解析成内部快照（纯函数，便于测试）。"""
    if not isinstance(payload, dict):
        raise ValueError("unexpected sge payload type")

    series: List[float] = []
    for raw in payload.get("data") or []:
        price = _to_float(raw)
        if price is not None:
            series.append(price)
    if not series:
        raise ValueError("sge payload has no valid price")

    ts = parse_delaystr(payload.get("delaystr"))
    if ts is None:
        # 极端情况下数据源没给时间：退化为抓取时间，但只作为兜底
        logger.warning("sge delaystr missing/unparsable: %r", payload.get("delaystr"))
        ts = now or datetime.now()

    return {
        "price": series[-1],
        "open": series[0],
        "high": _to_float(payload.get("max")),
        "low": _to_float(payload.get("min")),
        "timestamp": ts,
        "sparkline": _downsample(series),
        "point_count": len(series),
    }


class SgeClient:
    """复用连接的 SGE 客户端；所有请求都带超时，避免线程永久持锁。"""

    def __init__(self, timeout: float = 6.0) -> None:
        self.timeout = timeout
        self._session = requests.Session()
        self._session.headers.update(HEADERS)

    def fetch_snapshot(self, symbol: str = "Au99.99", timeout: Optional[float] = None) -> dict:
        r = self._session.get(
            QUOTATIONS_URL,
            data={"instid": symbol},
            timeout=timeout or self.timeout,
        )
        r.raise_for_status()
        return parse_payload(r.json())


_client = SgeClient()


def fetch_snapshot(symbol: str = "Au99.99", timeout: Optional[float] = None) -> dict:
    """模块级入口：复用同一个 Session 连接池。"""
    return _client.fetch_snapshot(symbol, timeout=timeout)
