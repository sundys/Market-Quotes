"""历史走势服务：详情页 天/周/月/半年/年 走势（AGENTS.md 第 29 节）。

数据源全部为 AKShare 生态：
- 美股指数：东方财富 K 线（em_service，分钟/日线）
- COMEX 黄金：新浪外盘日线（akshare futures_foreign_hist）+ 东财分钟线
- SGE：日线来自 spot_hist_sge；当日走势用采集器累积的采样点

每个数据点带日期标签（labels 与 points 一一对应），供详情页十字线查看。
内存缓存按 (key, period) 带 TTL；请求失败时返回最近缓存并标 is_stale。
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


def _sanitize_pairs(pairs: List[Tuple[str, float]]) -> Tuple[List[str], List[float]]:
    """过滤无效点并等距抽样，返回 (labels, points)，两列始终对齐。"""
    clean = [(str(lb), round(float(c), 4))
             for lb, c in pairs if c is not None and math.isfinite(c) and c > 0]
    if len(clean) > _MAX_POINTS:
        step = math.ceil(len(clean) / _MAX_POINTS)
        clean = clean[::step]
    labels = [lb for lb, _ in clean]
    points = [p for _, p in clean]
    return labels, points


class HistoryService:
    def __init__(self) -> None:
        self._cache = {}  # (key, period) -> (缓存时间, labels, points)
        self._sge_daily: Optional[Tuple[float, List[Tuple[str, float]]]] = None
        self._gc_daily: Optional[Tuple[float, List[Tuple[str, float]]]] = None

    def _cached_or(self, key: str, period: str):
        cached = self._cache.get((key, period))
        if cached is not None and time.time() - cached[0] < _TTL[period]:
            return cached[1], cached[2]
        return None

    @staticmethod
    def _acquire(lock, timeout: float = 10.0) -> bool:
        """限时获取数据源锁；拿不到说明采集线程正在抓取/挂起，调用方应走缓存快速返回。

        注意：历史接口运行在线程池中，绝不能无限等待数据源锁，
        否则锁被采集线程占用时会拖垮请求。
        """
        return lock.acquire(timeout=timeout)

    def _store(self, key: str, period: str, labels: List[str], points: List[float]) -> None:
        self._cache[(key, period)] = (time.time(), labels, points)

    @staticmethod
    def _result(quote_id: str, period: str, labels: List[str],
                points: List[float], stale: bool) -> dict:
        return {
            "id": quote_id,
            "period": period,
            "points": points,
            "labels": labels,
            "count": len(points),
            "is_stale": stale,
            "server_time": time.time(),
        }

    # ---- 东财 K 线（美股指数 + COMEX 黄金分钟线） ----
    def em_history(self, quote_id: str, secid: str, period: str, lock) -> dict:
        klt, lmt = _EM_RANGE[period]
        cache_key = f"{secid}:{klt}"
        cached = self._cached_or(cache_key, period)
        if cached is not None:
            return self._result(quote_id, period, cached[0], cached[1], stale=False)
        if not self._acquire(lock):
            return self._result(quote_id, period, [], [], stale=True)
        try:
            labels, points = em_service.fetch_kline(secid, klt, lmt)
        except Exception as exc:  # noqa: BLE001
            logger.warning("em history %s %s failed: %s", secid, period, exc)
            stale_cache = self._cache.get((cache_key, period))
            if stale_cache is not None:
                return self._result(quote_id, period, stale_cache[1], stale_cache[2], stale=True)
            return self._result(quote_id, period, [], [], stale=True)
        finally:
            lock.release()
        labels, points = _sanitize_pairs(list(zip(labels, points)))
        self._store(cache_key, period, labels, points)
        return self._result(quote_id, period, labels, points, stale=False)

    def index_history(self, quote_id: str, secid: str, period: str, lock) -> dict:
        return self.em_history(quote_id, secid, period, lock)

    def gc_history(self, period: str, lock) -> dict:
        """COMEX 黄金：1d 用东财分钟线，其余用新浪日线切片。"""
        if period == "1d":
            return self.em_history("gold_global", em_service.GOLD_SECID, "1d", lock)
        cache_key = "GC:daily"
        cached = self._cached_or(cache_key, "1y")
        if cached is not None:
            labels, points = cached
        else:
            if not self._acquire(lock):
                return self._result("gold_global", period, [], [], stale=True)
            try:
                labels, points = akshare_service.fetch_gc_daily_closes()
            except Exception as exc:  # noqa: BLE001
                logger.warning("gc daily history failed: %s", exc)
                labels, points = [], []
            finally:
                lock.release()
            if points:
                labels, points = _sanitize_pairs(list(zip(labels, points)))
                self._store(cache_key, "1y", labels, points)
            elif self._gc_daily is not None:
                labels, points = zip(*self._gc_daily[1])
                labels, points = list(labels), list(points)
            else:
                return self._result("gold_global", period, [], [], stale=True)
        return self._result("gold_global", period,
                            labels[-_DAILY_SLICE[period]:], points[-_DAILY_SLICE[period]:],
                            stale=False)

    # ---- SGE ----
    def sge_history(self, period: str, samples: List[Tuple[float, str]], lock) -> dict:
        """samples 为采集器累积的 (价格, 时间标签) 序列。"""
        quote_id = "gold_cn"
        if period == "1d":
            labels, points = _sanitize_pairs([(lb, p) for p, lb in samples])
            return self._result(quote_id, period, labels, points, stale=False)

        today = time.time() // 86400
        if self._sge_daily is None or self._sge_daily[0] != today:
            if not self._acquire(lock):
                # 锁被占用：先用内存兜底，避免拖垮请求
                if self._sge_daily is not None:
                    self._sge_daily = (self._sge_daily[0], list(self._sge_daily[1]))
                else:
                    return self._result(quote_id, period, [], [], stale=True)
            else:
                try:
                    labels, points = akshare_service.fetch_sge_daily_closes()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("sge daily history failed: %s", exc)
                    labels, points = [], []
                finally:
                    lock.release()
                if points:
                    labels, points = _sanitize_pairs(list(zip(labels, points)))
                    self._sge_daily = (today, list(zip(labels, points)))

        # 切片统一从权威内存取，避免缓存命中路径变量未定义
        pairs = self._sge_daily[1]
        labels = [lb for lb, _ in pairs]
        points = [p for _, p in pairs]
        return self._result(quote_id, period,
                            labels[-_DAILY_SLICE[period]:], points[-_DAILY_SLICE[period]:],
                            stale=False)


history_service = HistoryService()
