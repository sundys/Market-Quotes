"""MarketService：统一编排缓存、数据源与开闭市状态（AGENTS.md 第 10/13/20/23 节）。

数据源全部为开源 AKShare 生态（AGENTS.md 第 4 节调整，替换 Yahoo Finance）：
- 美股三大指数：东方财富全球指数实时（em_service，一次请求）
- 国际黄金：COMEX 黄金期货实时（新浪外盘，sina_client，一次请求）
- 上海黄金：上海黄金交易所（sge_client 实时 + akshare_service 日线）

- 路由只调用本服务，只读缓存。
- 单个数据源失败只把对应行情标记 stale，不影响其它行情。
- 涨跌基准（previous close）由采集器写入缓存并持久化，跨日刷新。
"""
from __future__ import annotations

import logging
import threading
import time
import zoneinfo
from datetime import datetime
from typing import Dict, Optional

from app.config import settings
from app.models.quote import MarketQuote, compute_change
from app.services.market import registry
from app.services.market.cache_service import CacheService
from app.services.market.rate_limiter import SourceHealth

logger = logging.getLogger("market.service")

TZ_CN = zoneinfo.ZoneInfo("Asia/Shanghai")
TZ_US = zoneinfo.ZoneInfo("America/New_York")

# 行情“按龄 stale”的下限：低于这个年龄一律不算过期，避免正常抖动误报
MIN_STALE_AGE = 120.0


def us_market_open(now: Optional[datetime] = None) -> bool:
    """美股 9:30-16:00 ET，周一至周五，扣除美股法定假日（第一阶段不含半日市）。"""
    now = now or datetime.now(TZ_US)
    from app.services.market.holidays import is_us_holiday

    if now.weekday() >= 5 or is_us_holiday(now.date()):
        return False
    minutes = now.hour * 60 + now.minute
    return 9 * 60 + 30 <= minutes <= 16 * 60


def comex_open(now: Optional[datetime] = None) -> bool:
    """COMEX 期金（Globex）：周日 18:00 ET 开盘，周五 17:00 ET 收盘，每日 17:00-18:00 维护。"""
    now = now or datetime.now(TZ_US)
    from app.services.market.holidays import is_us_holiday

    weekday = now.weekday()
    minutes = now.hour * 60 + now.minute
    if weekday == 5:                      # 周六全天休市
        return False
    if weekday == 6:                      # 周日 18:00 ET 开盘
        return minutes >= 18 * 60
    if is_us_holiday(now.date()):
        return False
    if weekday == 4:                      # 周五 17:00 ET 收盘
        return minutes < 17 * 60
    return not (17 * 60 <= minutes < 18 * 60)   # 每日维护窗口


def _current_interval(group: str) -> int:
    """当前该组行情应有的刷新间隔（用于判断“数据是不是已经不新鲜了”）。"""
    if group == registry.GROUP_US_INDEX:
        return settings.yf_min_interval if us_market_open() else settings.closed_market_interval
    if group == registry.GROUP_COMEX:
        return settings.gc_refresh_interval if comex_open() else settings.closed_market_interval
    from app.services.market.akshare_service import current_sge_trade_session_open

    return (settings.sge_refresh_interval
            if current_sge_trade_session_open(datetime.now(TZ_CN))
            else settings.closed_market_interval)


class MarketService:
    def __init__(self, cache: CacheService) -> None:
        self.cache = cache
        # 每个数据源独立健康状态与请求锁：
        # - em_lock：东财 clist 实时（采集器）
        # - kline_lock：东财 K 线（详情页历史 + 黄金月线），与实时互不阻塞
        # - gc_lock：新浪外盘；sge_lock：上海黄金
        self.em_health = SourceHealth(
            backoff_base=settings.yf_backoff_base,
            backoff_max=settings.yf_backoff_max,
            max_retries=settings.yf_max_retries,
        )
        self.gc_health = SourceHealth(
            backoff_base=settings.yf_backoff_base,
            backoff_max=settings.yf_backoff_max,
            max_retries=settings.yf_max_retries,
        )
        self.sge_health = SourceHealth(
            backoff_base=settings.yf_backoff_base,
            backoff_max=settings.yf_backoff_max,
            max_retries=settings.yf_max_retries,
        )
        self.em_lock = threading.Lock()
        self.kline_lock = threading.Lock()
        self.gc_lock = threading.Lock()
        self.sge_lock = threading.Lock()
        self.latencies: Dict[str, Optional[int]] = {"em": None, "gc": None, "sge": None}
        # 首页行情线：月线（最近 22 个交易日收盘），由低频任务刷新
        self.sge_monthly: list = []
        self.gc_monthly: list = []

    def set_sge_monthly(self, points: list) -> None:
        self.sge_monthly = points

    def set_gc_monthly(self, points: list) -> None:
        self.gc_monthly = points

    def record_latency(self, source: str, latency_ms: int) -> None:
        self.latencies[source] = latency_ms

    def refresh_sparkline(self, quote_id: str) -> None:
        """月线就绪后立刻补到已缓存的行情上，不必等下一次实时采集。"""
        points = self.gc_monthly if quote_id == "gold_global" else self.sge_monthly
        if len(points) < 2:
            return
        payload = self.cache.get_quote(quote_id)
        if not payload:
            return
        payload["sparkline"] = list(points)
        self.cache.set_quote(quote_id, payload)

    # ---- 写入（由后台采集器调用） ----
    def apply_index_quotes(self, quotes: dict) -> None:
        """应用美股指数实时快照：{quote_id: {name, price, prev_close, ...}}。

        部分成功时，缺失的标的必须标 stale —— 否则旧价会继续冒充实时。
        """
        for defn in registry.by_group(registry.GROUP_US_INDEX):
            snap = quotes.get(defn.id)
            if snap is None:
                self._mark_one_stale(defn.id)
                continue
            change, change_percent = compute_change(snap["price"], snap["prev_close"])
            quote = MarketQuote(
                id=defn.id,
                name=defn.name,
                symbol=defn.symbol,
                price=snap["price"],
                change=change,
                change_percent=change_percent,
                currency=defn.currency,
                unit=defn.unit,
                source=defn.source,
                timestamp=snap["timestamp"].replace(tzinfo=TZ_CN).isoformat(),
                market_status="open" if us_market_open() else "closed",
                is_stale=False,
                sparkline=snap.get("sparkline", []),
                open=snap.get("open"),
                high=snap.get("high"),
                low=snap.get("low"),
                prev_close=snap.get("prev_close"),
                volume=snap.get("volume"),
            )
            if not quote.is_valid():
                logger.warning("drop invalid index quote %s: %s", defn.id, quote.to_dict())
                continue
            self.cache.set_quote(defn.id, quote.to_dict())
        self.cache.mark_success("em")

    def apply_gold_quote(self, snap: dict) -> None:
        """应用 COMEX 黄金期货实时快照（名称与来源明确标注期货）。"""
        defn = registry.get("gold_global")
        assert defn is not None
        change, change_percent = compute_change(snap["price"], snap.get("prev_settlement"))
        quote = MarketQuote(
            id=defn.id,
            name=defn.name,
            symbol=defn.symbol,
            price=snap["price"],
            change=change,
            change_percent=change_percent,
            currency=defn.currency,
            unit=defn.unit,
            source=defn.source,
            timestamp=snap["timestamp"].replace(tzinfo=TZ_CN).isoformat(),
            market_status="open" if comex_open() else "closed",
            is_stale=False,
            sparkline=self.gc_monthly if len(self.gc_monthly) >= 2 else snap.get("sparkline", []),
            open=snap.get("open"),
            high=snap.get("high"),
            low=snap.get("low"),
            prev_close=snap.get("prev_settlement"),
        )
        if not quote.is_valid():
            logger.warning("drop invalid gold quote: %s", quote.to_dict())
            return
        self.cache.set_quote(defn.id, quote.to_dict())
        self.cache.mark_success("gc")

    def apply_sge(self, snap: dict) -> None:
        """应用 SGE 实时快照；涨跌基准为缓存中持久化的最近交易日收盘价。"""
        defn = registry.get("gold_cn")
        assert defn is not None
        price = snap["price"]
        ts = snap["timestamp"]
        prev_close = self.cache.get_previous_close(defn.symbol)
        change, change_percent = compute_change(price, prev_close)
        # 行情线优先级：月线 > 数据源当日分钟线 > 采集器累积采样
        if len(self.sge_monthly) >= 2:
            sparkline = self.sge_monthly
        else:
            sparkline = snap.get("sparkline") or self.cache.get_sge_sparkline()
        quote = MarketQuote(
            id=defn.id,
            name=defn.name,
            symbol=defn.symbol,
            price=price,
            change=change,
            change_percent=change_percent,
            currency=defn.currency,
            unit=defn.unit,
            source=defn.source,
            timestamp=ts.replace(tzinfo=TZ_CN).isoformat(),
            market_status="open" if _sge_open(datetime.now(TZ_CN)) else "closed",
            is_stale=False,
            open=snap.get("open"),
            high=snap.get("high"),
            low=snap.get("low"),
            prev_close=prev_close,
            sparkline=sparkline,
        )
        if not quote.is_valid():
            logger.warning("drop invalid sge quote: %s", quote.to_dict())
            return
        # 先存当日采样点（详情页“天”走势用），再写入 quote
        self.cache.append_sge_point(price, ts.strftime("%m-%d %H:%M"))
        self.cache.set_quote(defn.id, quote.to_dict())
        self.cache.mark_success("sge")

    # ---- stale 标记 ----
    def _mark_one_stale(self, quote_id: str) -> None:
        payload = self.cache.get_quote(quote_id)
        if payload and not payload.get("is_stale"):
            payload["is_stale"] = True
            self.cache.set_quote(quote_id, payload)
            logger.warning("quote %s marked stale", quote_id)

    def _mark_stale(self, quote_ids: list, health: SourceHealth, error: str) -> None:
        health.record_error(error)
        for quote_id in quote_ids:
            self._mark_one_stale(quote_id)

    def mark_quotes_stale(self, group: str) -> None:
        """只翻 stale 标记，不动健康计数（采集器自己记失败，避免重复计数）。"""
        for quote_id in registry.ids_for_group(group):
            self._mark_one_stale(quote_id)

    def mark_em_stale(self, error: str) -> None:
        self._mark_stale(registry.ids_for_group(registry.GROUP_US_INDEX), self.em_health, error)

    def mark_gc_stale(self, error: str) -> None:
        self._mark_stale(registry.ids_for_group(registry.GROUP_COMEX), self.gc_health, error)

    def mark_sge_stale(self, error: str) -> None:
        self._mark_stale(registry.ids_for_group(registry.GROUP_SGE), self.sge_health, error)

    # ---- 详情页历史走势 ----
    def history(self, quote_id: str, period: str) -> dict:
        from app.services.market.history_service import history_service

        defn = registry.get(quote_id)
        if defn is None:
            return {"id": quote_id, "period": period, "points": [], "labels": [], "count": 0,
                    "is_stale": True, "server_time": time.time()}
        if defn.group == registry.GROUP_SGE:
            return history_service.sge_history(period, self.cache.get_sge_samples(), self.sge_lock)
        if defn.group == registry.GROUP_COMEX:
            return history_service.gc_history(period, self.kline_lock)
        return history_service.index_history(quote_id, defn.symbol, period, self.kline_lock)

    # ---- 读取（API 路由调用，只返回缓存） ----
    def overview(self) -> dict:
        now = datetime.now(TZ_CN)
        items = []
        for quote_id in registry.ORDER:
            payload = self.cache.get_quote(quote_id)
            if not payload:
                continue
            payload["market_status"] = _refresh_market_status(payload)
            if not payload.get("is_stale") and _stale_by_age(payload, now):
                payload["is_stale"] = True
            items.append(payload)
        updated_at = max((i.get("timestamp") or "" for i in items), default="") or None
        return {
            "updated_at": updated_at,
            "count": len(items),
            "items": items,
            "server_time": now.isoformat(),
        }

    def health(self) -> dict:
        return {
            "status": "ok",
            "has_data": self.cache.has_any_data(),
            "eastmoney": _stats(self.em_health, self.latencies["em"]),
            "gc_sina": _stats(self.gc_health, self.latencies["gc"]),
            "sge": _stats(self.sge_health, self.latencies["sge"]),
            "cache": {
                "cache_hits": self.cache.stats["cache_hits"],
                "cache_misses": self.cache.stats["cache_misses"],
                "em_last_success": self.cache.stats.get("em_last_success"),
                "gc_last_success": self.cache.stats.get("gc_last_success"),
                "sge_last_success": self.cache.stats.get("sge_last_success"),
            },
            "server_time": datetime.now(TZ_CN).isoformat(),
        }


def _stats(health: SourceHealth, latency_ms: Optional[int]) -> dict:
    data = health.stats()
    data["last_latency_ms"] = latency_ms
    return data


def _sge_open(now: datetime) -> bool:
    from app.services.market.akshare_service import current_sge_trade_session_open

    return current_sge_trade_session_open(now)


def _refresh_market_status(payload: dict) -> str:
    """快照时按当前时间重算市场状态，不依赖采集时刻。"""
    defn = registry.get(payload.get("id") or "")
    if defn is None:
        return payload.get("market_status") or "unknown"
    if defn.group == registry.GROUP_US_INDEX:
        return "open" if us_market_open() else "closed"
    if defn.group == registry.GROUP_SGE:
        return "open" if _sge_open(datetime.now(TZ_CN)) else "closed"
    return "open" if comex_open() else "closed"


def _parse_iso(value) -> Optional[datetime]:
    if not value:
        return None
    try:
        ts = datetime.fromisoformat(str(value))
    except ValueError:
        return None
    return ts if ts.tzinfo is not None else ts.replace(tzinfo=TZ_CN)


def _stale_by_age(payload: dict, now: datetime) -> bool:
    """交易中却长时间没有新数据 → 视为过期（防止数据源“静默返回旧值”）。"""
    if payload.get("market_status") != "open":
        return False
    ts = _parse_iso(payload.get("timestamp"))
    if ts is None:
        return False
    defn = registry.get(payload.get("id") or "")
    interval = _current_interval(defn.group) if defn else settings.sge_refresh_interval
    return (now - ts).total_seconds() > max(3.0 * interval, MIN_STALE_AGE)
