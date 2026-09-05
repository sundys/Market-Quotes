"""历史走势服务：详情页 天/周/月/半年/年 走势（AGENTS.md 第 29 节）。

数据源全部为 AKShare 生态：
- 美股指数：东方财富 K 线（em_service，分钟/日线）
- COMEX 黄金：新浪外盘日线（akshare futures_foreign_hist）+ 东财分钟线
- SGE：日线来自 spot_hist_sge；当日走势用采集器累积的采样点

内存缓存按 (symbol, period) 带 TTL；请求失败时返回最近缓存并标 is_stale。
points 只含收盘价序列：走势图不画坐标轴刻度（AGENTS.md 第 55 节）。
"""
from __future__ import annotations

import logging
import math
import time
from typing import List, Optional, Tuple

from app.services.market import akshare_service, em_service

logger = logging.getLogger("market.history")

PERIODS = ("1d", "1w", "1m", "6m", "1y")

# period -> (东财 klt, lmt)
_EM_RANGE = {
    "1d": (5, 100),
    "1w": (30, 80),
    "1m": (101, 25),
    "6m": (101, 130),
    "1y": (101, 260),
}

_TTL = {"1d": 60, "1w": 300, "1m": 900, "6m": 900, "1y": 3600}

_MAX_POINTS = 400

# 纯日线数据源各周期取最近 N 个收盘
_DAILY_SLICE = {"1w": 5, "1m": 22, "6m": 130, "1y": 250}


def _sanitize(points: List[float]) -> List[float]:
    clean = [round(float(p), 4) for p in points if p is not None and math.isfinite(p) and p > 0]
    if len(clean) > _MAX_POINTS:
        step = math.ceil(len(clean) / _MAX_POINTS)
        clean = clean[::step]
    return clean


class HistoryService:
    def __init__(self) -> None:
        self._cache = {}  # (key, period) -> (缓存时间, points)
        self._sge_daily: Optional[Tuple[float, List[float]]] = None  # (日期戳, 收盘序列)
        self._gc_daily: Optional[Tuple[float, List[float]]] = None

    def _cached_or(self, key: str, period: str):
        cached = self._cache.get((key, period))
        if cached is not None and time.time() - cached[0] < _TTL[period]:
            return cached[1]
        return None

    def _store(self, key: str, period: str, points: List[float]) -> None:
        self._cache[(key, period)] = (time.time(), points)

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

    # ---- 东财 K 线（美股指数 + COMEX 黄金分钟线） ----
    def em_history(self, quote_id: str, secid: str, period: str, lock) -> dict:
        klt, lmt = _EM_RANGE[period]
        cache_key = f"{secid}:{klt}"
        points = self._cached_or(cache_key, period)
        if points is None:
            try:
                with lock:
                    points = em_service.fetch_kline_closes(secid, klt, lmt)
            except Exception as exc:  # noqa: BLE001
                logger.warning("em history %s %s failed: %s", secid, period, exc)
                stale_cache = self._cache.get((cache_key, period))
                if stale_cache is not None:
                    return self._result(quote_id, period, stale_cache[1], stale=True)
                return self._result(quote_id, period, [], stale=True)
            points = _sanitize(points)
            self._store(cache_key, period, points)
        return self._result(quote_id, period, points, stale=False)

    def index_history(self, quote_id: str, secid: str, period: str, lock) -> dict:
        return self.em_history(quote_id, secid, period, lock)

    def gc_history(self, period: str, lock) -> dict:
        """COMEX 黄金：1d 用东财分钟线，其余用新浪日线切片。"""
        if period == "1d":
            return self.em_history("gold_global", em_service.GOLD_SECID, "1d", lock)
        cache_key = "GC:daily"
        daily = self._cached_or(cache_key, "1y")
        if daily is None:
            try:
                with lock:
                    daily = akshare_service.fetch_gc_daily_closes()
            except Exception as exc:  # noqa: BLE001
                logger.warning("gc daily history failed: %s", exc)
                daily = None
            if daily:
                daily = _sanitize(daily)
                self._store(cache_key, "1y", daily)
            elif self._gc_daily is not None:
                daily = self._gc_daily[1]
            else:
                return self._result("gold_global", period, [], stale=True)
        self._gc_daily = (time.time(), daily)
        return self._result("gold_global", period, daily[-_DAILY_SLICE[period]:], stale=False)

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
        return self._result(quote_id, period, _sanitize(closes[-_DAILY_SLICE[period]:]), stale=False)


history_service = HistoryService()
