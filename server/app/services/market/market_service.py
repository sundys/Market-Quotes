"""MarketService：统一编排缓存、数据源与开闭市状态（AGENTS.md 第 10/13/20/23 节）。

数据源全部为开源 AKShare 生态（AGENTS.md 第 4 节调整，替换 Yahoo Finance）：
- 美股三大指数：东方财富全球指数实时（em_service）
- 国际黄金：COMEX 黄金期货实时与日线（新浪外盘，经 AKShare）
- 上海黄金：上海黄金交易所（AKShare spot_quotations_sge / spot_hist_sge）

- 路由只调用本服务。
- 单个数据源失败只把对应行情标记 stale，不影响其它行情。
"""
from __future__ import annotations

import logging
import threading
import time
import zoneinfo
from datetime import datetime
from typing import Optional

from app.config import settings
from app.models.quote import MarketQuote, compute_change
from app.services.market.cache_service import CacheService
from app.services.market.rate_limiter import SourceHealth

logger = logging.getLogger("market.service")

TZ_CN = zoneinfo.ZoneInfo("Asia/Shanghai")
TZ_US = zoneinfo.ZoneInfo("America/New_York")

# 各行情的定义；symbol 为对应数据源代码
SYMBOLS = {
    "gold_global": ("国际黄金期货", "GC", "USD", "oz"),
    "nasdaq100": ("纳斯达克100", "100.NDX", "USD", None),
    "sp500": ("标普500", "100.SPX", "USD", None),
    "dowjones": ("道琼斯", "100.DJIA", "USD", None),
    "gold_cn": ("上海黄金 Au99.99", "Au99.99", "CNY", "g"),
}

OVERVIEW_ORDER = ["gold_global", "nasdaq100", "sp500", "dowjones", "gold_cn"]

YF_SYMBOLS = SYMBOLS  # 兼容旧引用


def us_market_open(now: Optional[datetime] = None) -> bool:
    """美股 9:30-16:00 ET，周一至周五（不含节假日，第一阶段简化）。"""
    now = now or datetime.now(TZ_US)
    if now.weekday() >= 5:
        return False
    minutes = now.hour * 60 + now.minute
    return 9 * 60 + 30 <= minutes <= 16 * 60


class MarketService:
    def __init__(self, cache: CacheService) -> None:
        self.cache = cache
        # 每个数据源独立健康状态与请求锁（采集器与详情页历史共用锁）
        self.em_health = SourceHealth(  # 东方财富：美股指数
            backoff_base=settings.yf_backoff_base,
            backoff_max=settings.yf_backoff_max,
            max_retries=settings.yf_max_retries,
        )
        self.gc_health = SourceHealth(  # 新浪外盘：COMEX 黄金
            backoff_base=settings.yf_backoff_base,
            backoff_max=settings.yf_backoff_max,
            max_retries=settings.yf_max_retries,
        )
        self.sge_health = SourceHealth(  # 上海黄金交易所
            backoff_base=settings.yf_backoff_base,
            backoff_max=settings.yf_backoff_max,
            max_retries=settings.yf_max_retries,
        )
        self.em_lock = threading.Lock()
        self.gc_lock = threading.Lock()
        self.sge_lock = threading.Lock()

    # ---- 写入（由后台采集器调用） ----
    def apply_index_quotes(self, quotes: dict) -> None:
        """应用美股指数实时快照：{quote_id: {name, price, prev_close, timestamp}}。"""
        for quote_id, snap in quotes.items():
            name, _, currency, unit = SYMBOLS[quote_id]
            change, change_percent = compute_change(snap["price"], snap["prev_close"])
            quote = MarketQuote(
                id=quote_id,
                name=name,
                symbol=SYMBOLS[quote_id][1],
                price=snap["price"],
                change=change,
                change_percent=change_percent,
                currency=currency,
                unit=unit,
                source="AKShare/东财",
                timestamp=snap["timestamp"].replace(tzinfo=TZ_CN).isoformat(),
                market_status="open" if us_market_open() else "closed",
                is_stale=False,
                sparkline=snap.get("sparkline", []),
            )
            if not quote.is_valid():
                logger.warning("drop invalid index quote %s: %s", quote_id, quote.to_dict())
                continue
            self.cache.set_quote(quote_id, quote.to_dict())
        self.cache.mark_success("em")

    def apply_gold_quote(self, snap: dict) -> None:
        """应用 COMEX 黄金期货实时快照（名称与来源明确标注期货）。"""
        change, change_percent = compute_change(snap["price"], snap["prev_settlement"])
        quote = MarketQuote(
            id="gold_global",
            name=SYMBOLS["gold_global"][0],
            symbol=SYMBOLS["gold_global"][1],
            price=snap["price"],
            change=change,
            change_percent=change_percent,
            currency="USD",
            unit="oz",
            source="AKShare/新浪外盘(期金)",
            timestamp=snap["timestamp"].replace(tzinfo=TZ_CN).isoformat(),
            market_status="open",
            is_stale=False,
            sparkline=snap.get("sparkline", []),
        )
        if not quote.is_valid():
            logger.warning("drop invalid gold quote: %s", quote.to_dict())
            return
        self.cache.set_quote("gold_global", quote.to_dict())
        self.cache.mark_success("gc")

    def apply_sge(self, price: float, ts: datetime) -> None:
        """应用 SGE 实时快照；涨跌基准为缓存中的最近交易日收盘价。"""
        prev_close = self.cache.get_previous_close("Au99.99")
        change, change_percent = compute_change(price, prev_close)
        quote = MarketQuote(
            id="gold_cn",
            name=SYMBOLS["gold_cn"][0],
            symbol=SYMBOLS["gold_cn"][1],
            price=price,
            change=change,
            change_percent=change_percent,
            currency="CNY",
            unit="g",
            source="AKShare/SGE",
            timestamp=ts.replace(tzinfo=TZ_CN).isoformat(),
            market_status="open" if _sge_open(ts) else "closed",
            is_stale=False,
        )
        if not quote.is_valid():
            logger.warning("drop invalid sge quote: %s", quote.to_dict())
            return
        self.cache.set_quote("gold_cn", quote.to_dict())
        self.cache.append_sge_point(price)
        self.cache.mark_success("sge")

    # ---- stale 标记 ----
    def _mark_stale(self, quote_ids: list, health: SourceHealth, error: str) -> None:
        _record_failure(health, error)
        for quote_id in quote_ids:
            payload = self.cache.get_quote(quote_id)
            if payload:
                payload["is_stale"] = True
                self.cache.set_quote(quote_id, payload)

    def mark_em_stale(self, error: str) -> None:
        self._mark_stale(["nasdaq100", "sp500", "dowjones"], self.em_health, error)

    def mark_gc_stale(self, error: str) -> None:
        self._mark_stale(["gold_global"], self.gc_health, error)

    def mark_sge_stale(self, error: str) -> None:
        self._mark_stale(["gold_cn"], self.sge_health, error)

    # ---- 详情页历史走势 ----
    def history(self, quote_id: str, period: str) -> dict:
        from app.services.market.history_service import history_service

        if quote_id == "gold_cn":
            return history_service.sge_history(period, self.cache.get_sge_sparkline(), self.sge_lock)
        if quote_id == "gold_global":
            return history_service.gc_history(period, self.gc_lock)
        if quote_id in ("nasdaq100", "sp500", "dowjones"):
            secid = SYMBOLS[quote_id][1]
            return history_service.index_history(quote_id, secid, period, self.em_lock)
        return {"id": quote_id, "period": period, "points": [], "count": 0,
                "is_stale": True, "server_time": time.time()}

    # ---- 读取（API 路由调用，只返回缓存） ----
    def overview(self) -> dict:
        items = []
        for quote_id in OVERVIEW_ORDER:
            payload = self.cache.get_quote(quote_id)
            if payload:
                payload["market_status"] = _refresh_market_status(payload)
                items.append(payload)
        updated_at = max((i["timestamp"] for i in items), default=None)
        return {
            "updated_at": updated_at,
            "items": items,
            "server_time": datetime.now(TZ_CN).isoformat(),
        }

    def health(self) -> dict:
        return {
            "status": "ok",
            "has_data": self.cache.has_any_data(),
            "eastmoney": self.em_health.stats(),
            "gc_sina": self.gc_health.stats(),
            "sge": self.sge_health.stats(),
            "cache": {
                "cache_hits": self.cache.stats["cache_hits"],
                "cache_misses": self.cache.stats["cache_misses"],
                "em_last_success": self.cache.stats.get("em_last_success"),
                "gc_last_success": self.cache.stats.get("gc_last_success"),
                "sge_last_success": self.cache.stats.get("sge_last_success"),
            },
            "server_time": datetime.now(TZ_CN).isoformat(),
        }


def _record_failure(health: SourceHealth, error: str) -> None:
    """429 走限速计数并冷却，其它异常走普通失败（同样退避冷却）。"""
    text = str(error).lower()
    if "429" in text or "too many requests" in text or "ratelimit" in text:
        health.on_rate_limit()
    else:
        health.on_failure(error)


def _sge_open(now: datetime) -> bool:
    from app.services.market.akshare_service import current_sge_trade_session_open

    return current_sge_trade_session_open(now)


def _refresh_market_status(payload: dict) -> str:
    """快照时按当前时间重算市场状态，不依赖采集时刻。"""
    symbol = payload.get("symbol", "")
    if symbol in ("100.NDX", "100.SPX", "100.DJIA"):
        return "open" if us_market_open() else "closed"
    if symbol == "Au99.99":
        return "open" if _sge_open(datetime.now(TZ_CN)) else "closed"
    # COMEX 期金接近全天交易
    return "open"
