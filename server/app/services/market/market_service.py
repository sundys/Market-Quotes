"""MarketService：统一编排缓存、数据源与开闭市状态（AGENTS.md 第 10/13/20/23 节）。

- 路由只调用本服务，禁止直接访问 yfinance/AKShare。
- 单个数据源失败只把对应行情标记 stale，不影响其它行情。
"""
from __future__ import annotations

import logging
import time
import zoneinfo
from datetime import datetime
from typing import Dict, Optional

from app.config import settings
from app.models.quote import MarketQuote, compute_change
from app.services.market.cache_service import CacheService
from app.services.market.rate_limiter import SourceHealth

logger = logging.getLogger("market.service")

TZ_CN = zoneinfo.ZoneInfo("Asia/Shanghai")
TZ_US = zoneinfo.ZoneInfo("America/New_York")

YF_SYMBOLS = {
    "XAUUSD=X": ("gold_global", "国际黄金", "USD", "oz"),
    "^NDX": ("nasdaq100", "纳斯达克100", "USD", None),
    "^GSPC": ("sp500", "标普500", "USD", None),
}


def us_market_open(now: Optional[datetime] = None) -> bool:
    """美股 9:30-16:00 ET，周一至周五（不含节假日，第一阶段简化）。"""
    now = now or datetime.now(TZ_US)
    if now.weekday() >= 5:
        return False
    minutes = now.hour * 60 + now.minute
    return 9 * 60 + 30 <= minutes <= 16 * 60


def is_us_market_symbol(symbol: str) -> bool:
    return symbol in ("^NDX", "^GSPC")


class MarketService:
    def __init__(self, cache: CacheService) -> None:
        self.cache = cache
        self.yf_health = SourceHealth(
            backoff_base=settings.yf_backoff_base,
            backoff_max=settings.yf_backoff_max,
            max_retries=settings.yf_max_retries,
        )
        self.sge_health = SourceHealth(
            backoff_base=settings.yf_backoff_base,
            backoff_max=settings.yf_backoff_max,
            max_retries=settings.yf_max_retries,
        )

    # ---- 写入（由后台采集器调用） ----
    def apply_yfinance_snapshot(self, symbol: str, snapshot) -> None:
        quote_id, name, currency, unit = YF_SYMBOLS[symbol]
        ts = snapshot.timestamp
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=TZ_CN)
        change, change_percent = compute_change(snapshot.price, snapshot.previous_close)
        quote = MarketQuote(
            id=quote_id,
            name=name,
            symbol=symbol,
            price=snapshot.price,
            change=change,
            change_percent=change_percent,
            currency=currency,
            unit=unit,
            source="yfinance",
            timestamp=ts.isoformat(),
            market_status="open" if (us_market_open() if is_us_market_symbol(symbol) else True) else "closed",
            is_stale=False,
            sparkline=snapshot.sparkline,
        )
        if not quote.is_valid():
            logger.warning("drop invalid quote %s: %s", symbol, quote.to_dict())
            return
        self.cache.set_previous_close(symbol, snapshot.previous_close)
        self.cache.set_quote(quote_id, quote.to_dict())
        self.cache.mark_success("yfinance")

    def apply_sge(self, price: float, ts: datetime, prev_close: Optional[float], prev_date=None) -> None:
        if prev_close is not None and prev_date is not None:
            cached_ts = ts
            # 只有交易日切换后才更新 previous close（AGENTS.md 第 12 节）
            if prev_date >= cached_ts.date():
                prev_close = None
        self.cache.set_previous_close("Au99.99", prev_close)
        change, change_percent = compute_change(price, prev_close)
        quote = MarketQuote(
            id="gold_cn",
            name="上海黄金 Au99.99",
            symbol="Au99.99",
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

    def mark_yfinance_stale(self, error: str) -> None:
        """yfinance 失败：保留最后一次有效数据并标记 stale（AGENTS.md 第 9.2 节）。"""
        _record_failure(self.yf_health, error)
        for quote_id in YF_SYMBOLS.values():
            payload = self.cache.get_quote(quote_id[0])
            if payload:
                payload["is_stale"] = True
                self.cache.set_quote(quote_id[0], payload)

    def mark_sge_stale(self, error: str) -> None:
        _record_failure(self.sge_health, error)
        payload = self.cache.get_quote("gold_cn")
        if payload:
            payload["is_stale"] = True
            self.cache.set_quote("gold_cn", payload)

    # ---- 读取（API 路由调用，只返回缓存） ----
    def overview(self) -> dict:
        items = []
        for quote_id, name, currency, unit in YF_SYMBOLS.values():
            payload = self.cache.get_quote(quote_id)
            if payload:
                payload["market_status"] = _refresh_market_status(payload)
                items.append(payload)
        sge = self.cache.get_quote("gold_cn")
        if sge:
            sge["market_status"] = _refresh_market_status(sge)
            items.append(sge)

        order = {"gold_global": 0, "nasdaq100": 1, "sp500": 2, "gold_cn": 3}
        items.sort(key=lambda x: order.get(x["id"], 99))
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
            "yfinance": self.yf_health.stats(),
            "sge": self.sge_health.stats(),
            "cache": {
                "cache_hits": self.cache.stats["cache_hits"],
                "cache_misses": self.cache.stats["cache_misses"],
                "yfinance_last_success": self.cache.stats["yfinance_last_success"],
                "sge_last_success": self.cache.stats["sge_last_success"],
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
    if symbol in ("^NDX", "^GSPC"):
        return "open" if us_market_open() else "closed"
    if symbol == "Au99.99":
        return "open" if _sge_open(datetime.now(TZ_CN)) else "closed"
    # 国际黄金近乎全天交易
    return "open"
