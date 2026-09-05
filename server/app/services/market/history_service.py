"""历史走势服务：详情页 天/周/月/半年/年 走势（AGENTS.md 第 29 节）。

- yfinance 标的：按周期映射 period/interval 单标的下载。
- SGE：日线来自 spot_hist_sge；当日走势用采集器累积的采样点。
- 内存缓存按 (symbol, period) 带 TTL；请求失败时返回最近缓存并标 is_stale。
- points 只含收盘价序列：走势图不画坐标轴刻度（AGENTS.md 第 55 节）。
"""
from __future__ import annotations

import logging
import math
import time
from typing import List, Optional, Tuple

from app.services.market import akshare_service, yfinance_service

logger = logging.getLogger("market.history")

PERIODS = ("1d", "1w", "1m", "6m", "1y")

# period -> (yfinance period, interval)
_YF_RANGE = {
    "1d": ("1d", "5m"),
    "1w": ("5d", "30m"),
    "1m": ("1mo", "1d"),
    "6m": ("6mo", "1d"),
    "1y": ("1y", "1d"),
}

# 缓存 TTL（秒）：日内数据新鲜度要求高，日线一天更新一次
_TTL = {"1d": 60, "1w": 300, "1m": 900, "6m": 900, "1y": 3600}

_MAX_POINTS = 400

# SGE 各周期取最近 N 个交易日收盘
_SGE_SLICE = {"1w": 5, "1m": 22, "6m": 130, "1y": 250}


def _sanitize(points: List[float]) -> List[float]:
    clean = [round(float(p), 4) for p in points if p is not None and math.isfinite(p) and p > 0]
    if len(clean) > _MAX_POINTS:
        step = math.ceil(len(clean) / _MAX_POINTS)
        clean = clean[::step]
    return clean


class HistoryService:
    def __init__(self) -> None:
        # (symbol, period) -> (缓存时间, points)
        self._cache = {}
        self._sge_daily: Optional[Tuple[float, List[float]]] = None  # (日期戳, 收盘序列)

    # ---- yfinance 标的 ----
    def yf_history(self, symbol: str, period: str, lock, quote_id: str) -> dict:
        key = (symbol, period)
        cached = self._cache.get(key)
        if cached is not None and time.time() - cached[0] < _TTL[period]:
            return self._result(quote_id, period, cached[1], stale=False)

        yf_period, interval = _YF_RANGE[period]
        try:
            with lock:
                points = yfinance_service.fetch_history(symbol, yf_period, interval)
        except Exception as exc:  # noqa: BLE001
            logger.warning("history %s %s failed: %s", symbol, period, exc)
            if cached is not None:
                return self._result(quote_id, period, cached[1], stale=True)
            return self._result(quote_id, period, [], stale=True)

        points = _sanitize(points)
        self._cache[key] = (time.time(), points)
        return self._result(quote_id, period, points, stale=False)

    # ---- SGE ----
    def sge_history(self, period: str, intraday: List[float], lock) -> dict:
        quote_id = "gold_cn"
        if period == "1d":
            # 当日走势：采集器累积的采样点（后端重启后重新累积）
            return self._result(quote_id, period, _sanitize(intraday), stale=False)

        today = time.time() // 86400
        if self._sge_daily is None or self._sge_daily[0] != today:
            try:
                with lock:
                    closes = akshare_service.fetch_sge_daily_closes()
            except Exception as exc:  # noqa: BLE001
                logger.warning("sge daily history failed: %s", exc)
                closes = None
            if closes:
                self._sge_daily = (today, closes)
            elif self._sge_daily is not None:
                closes = self._sge_daily[1]
            else:
                return self._result(quote_id, period, [], stale=True)

        closes = self._sge_daily[1]
        return self._result(quote_id, period, _sanitize(closes[-_SGE_SLICE[period]:]), stale=False)

    @staticmethod
    def _result(quote_id: str, period: str, points: List[float], stale: bool) -> dict:
        return {
            "id": quote_id,
            "period": period,
            "points": points,
            "count": len(points),
            "is_stale": stale,
            "server_time": time.time(),
        }


history_service = HistoryService()
