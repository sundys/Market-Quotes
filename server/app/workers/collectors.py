"""后台采集任务（AGENTS.md 第 6/27/31 节）。数据源全部为 AKShare 生态：

- 东方财富：美股三大指数实时（一次请求）
- 新浪外盘：COMEX 黄金实时（一次请求，不再抓 hf.html 映射页）
- 上海黄金交易所：Au99.99 实时（一次请求拿全量）+ 日线（TTL 共享缓存）

设计要点（相对旧实现）：
- 统一调度器：到期时间 + 抖动，避免固定相位尖峰；周期按“抓取开始”计，不累积漂移。
- 单次超时 < 采集间隔；上一轮仍在飞时只跳过（busy 不记失败、不进冷却）。
- 月线（首页行情线）与实时采集解耦：GC / SGE 各有一个低频任务，且用独立锁，
  不再借 em_lock 拖慢指数实时采集；SGE 日线只在跨日时进入实时链路（刷新涨跌基准）。
- 采集循环永不退出：任何未预期异常都记日志后继续。
"""
from __future__ import annotations

import asyncio
import logging
import random
import threading
import time
from dataclasses import dataclass
from datetime import date
from typing import Any, Callable, List

from app.config import settings
from app.services.market import akshare_service, em_service, registry, sina_client, sge_client
from app.services.market.market_service import MarketService, comex_open, us_market_open

logger = logging.getLogger("market.workers")


class FetchBusy(Exception):
    """上一次请求仍在执行，本轮跳过（不记失败）。"""


@dataclass
class CollectorSpec:
    """一个数据源的采集规格；把循环体与具体数据源解耦，便于单测。"""

    name: str
    group: str
    source_key: str          # em / gc / sge，用于延迟统计
    lock: threading.Lock
    health: Any
    fetch: Callable[[], Any]
    apply: Callable[[Any], None]
    interval: Callable[[], int]


# ---- 刷新节奏（休市降频） ----
def _index_interval() -> int:
    return settings.yf_min_interval if us_market_open() else settings.closed_market_interval


def _comex_interval() -> int:
    return settings.gc_refresh_interval if comex_open() else settings.closed_market_interval


def _sge_interval() -> int:
    return (settings.sge_refresh_interval
            if akshare_service.current_sge_trade_session_open()
            else settings.closed_market_interval)


def _jittered(interval: float) -> float:
    """±jitter 的间隔，避免多个部署/重试同时打同一个源。"""
    ratio = max(0.0, min(settings.fetch_jitter, 0.5))
    return interval * random.uniform(1.0 - ratio, 1.0 + ratio)


def _timeout_for(interval: int) -> float:
    """单次抓取超时必须小于采集间隔，否则慢请求会让下一轮永远 busy。"""
    return max(3.0, min(float(settings.fetch_timeout), interval - 2.0))


def _log_fetch(source: str, symbol: str, status: str, latency_ms: int, extra: str = "") -> None:
    logger.info("source=%s symbol=%s status=%s latency=%dms %s", source, symbol, status, latency_ms, extra)


async def run_fetch_guarded(fn, timeout: float, lock) -> Any:
    """带在飞保护的线程执行；超时抛 TimeoutError，占用中抛 FetchBusy。"""
    if not lock.acquire(blocking=False):
        raise FetchBusy()

    def wrapped():
        try:
            return fn()
        finally:
            lock.release()

    try:
        return await asyncio.wait_for(asyncio.to_thread(wrapped), timeout=timeout)
    except asyncio.TimeoutError:
        raise TimeoutError(f"fetch timed out after {timeout:.0f}s")


# ---- 数据源抓取 ----
def _apply_sge_daily(service: MarketService, daily: akshare_service.SgeDaily) -> bool:
    """把日线结果落到缓存：跨日刷新涨跌基准 + 更新首页月线。

    关键点：判断“是否需要刷新”比较的是**抓取日**（fetched_on），不是交易日。
    以前拿上一交易日的日期和今天比，永远不相等，于是每 30 秒拉一次全量历史。
    """
    today = date.today().isoformat()
    updated = False
    if (daily.prev_close is not None
            and service.cache.previous_close_fetched_on("Au99.99") != today):
        service.cache.set_previous_close(
            "Au99.99", daily.prev_close, trade_date=daily.trade_date)
        logger.info("sge previous close updated: %s (trade_date=%s)",
                    daily.prev_close, daily.trade_date)
        updated = True
    if len(daily.closes) >= 2:
        service.set_sge_monthly([float(c) for c in daily.closes[-22:]])
    return updated


def _needs_daily_refresh(service: MarketService) -> bool:
    """涨跌基准是否需要在今天刷新（跨日/首次启动为 True）。"""
    return service.cache.previous_close_fetched_on("Au99.99") != date.today().isoformat()


def _fetch_sge(service: MarketService) -> dict:
    """SGE 实时：一次请求拿全量（现价/今开/最高/最低/行情时间/日内序列）。

    日线只在“今天还没刷新过涨跌基准”时拉取，且强制绕过 TTL：跨日那一刻必须拿到
    新的上一交易日收盘价。其余时间的月线刷新交给独立低频任务，避免实时 tick
    被历史接口拖慢。
    """
    snap = sge_client.fetch_snapshot("Au99.99", timeout=settings.fetch_timeout)

    if _needs_daily_refresh(service):
        daily = akshare_service.fetch_sge_daily("Au99.99", ttl=0)
        if daily is not None:
            _apply_sge_daily(service, daily)
    return snap


def _fetch_gold() -> dict:
    """COMEX 期金 + 伦敦金现货：同一主机、一次请求取两个品种。"""
    return sina_client.fetch_quotes(("GC", "XAU"), timeout=settings.fetch_timeout)


def build_specs(service: MarketService) -> List[CollectorSpec]:
    return [
        CollectorSpec(
            name="eastmoney", group=registry.GROUP_US_INDEX, source_key="em",
            lock=service.em_lock, health=service.em_health,
            fetch=em_service.fetch_global_indices, apply=service.apply_index_quotes,
            interval=_index_interval,
        ),
        CollectorSpec(
            name="sina-gold", group=registry.GROUP_COMEX, source_key="gc",
            lock=service.gc_lock, health=service.gc_health,
            fetch=_fetch_gold, apply=service.apply_gold_quotes,
            interval=_comex_interval,
        ),
        CollectorSpec(
            name="sge", group=registry.GROUP_SGE, source_key="sge",
            lock=service.sge_lock, health=service.sge_health,
            fetch=lambda: _fetch_sge(service), apply=service.apply_sge,
            interval=_sge_interval,
        ),
    ]


# ---- 调度 ----
async def collect_once(service: MarketService, spec: CollectorSpec) -> str:
    """执行一轮采集，返回 ok / busy / fail / cooldown。"""
    if spec.health.in_cooldown():
        return "cooldown"

    interval = spec.interval()
    spec.health.on_request()
    started = time.perf_counter()
    try:
        result = await run_fetch_guarded(spec.fetch, _timeout_for(interval), spec.lock)
        spec.apply(result)
        spec.health.on_success()
        latency = int((time.perf_counter() - started) * 1000)
        service.record_latency(spec.source_key, latency)
        _log_fetch(spec.name, spec.group, "ok", latency)
        service.cache.save_disk()
        return "ok"
    except FetchBusy:
        # 上一轮还在跑：本轮只是跳过，不能算失败（否则会误进冷却、误标 stale）
        _log_fetch(spec.name, spec.group, "busy", 0)
        return "busy"
    except Exception as exc:  # noqa: BLE001
        latency = int((time.perf_counter() - started) * 1000)
        spec.health.record_error(str(exc))
        service.mark_quotes_stale(spec.group)
        _log_fetch(spec.name, spec.group, "fail", latency, str(exc))
        service.cache.save_disk()
        return "fail"


async def run_collector(service: MarketService, spec: CollectorSpec) -> None:
    while True:
        started = time.monotonic()
        try:
            status = await collect_once(service, spec)
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            # 采集任务绝不允许退出：退出意味着这个源再也不会恢复
            logger.exception("collector %s crashed: %s", spec.name, exc)
            status = "fail"

        if status == "cooldown":
            await asyncio.sleep(min(max(spec.health.cooldown_remaining(), 1.0), 30.0))
            continue
        if status == "busy":
            await asyncio.sleep(3.0)
            continue
        if status == "fail":
            await asyncio.sleep(min(spec.health.backoff_delay(), 120.0))
            continue

        elapsed = time.monotonic() - started
        await asyncio.sleep(max(0.0, _jittered(spec.interval()) - elapsed))


async def _refresh_gold_monthly(service: MarketService, code: str, quote_id: str) -> str:
    """首页黄金卡行情线：GC 优先东财 COMEX 日线（失败退回新浪），XAU 用新浪日线。"""
    closes = []
    if code == "GC":
        try:
            _, closes = await run_fetch_guarded(
                lambda: em_service.fetch_kline(em_service.GOLD_SECID, 101, 22),
                timeout=min(float(settings.fetch_timeout), 20.0),
                lock=service.kline_lock,
            )
        except FetchBusy:
            logger.info("%s monthly refresh skipped: kline busy", quote_id)
            return "busy"
        except Exception as exc:  # noqa: BLE001
            logger.warning("%s monthly (em kline) failed: %s, falling back to sina daily",
                           quote_id, exc)

    if not closes:
        try:
            _, closes = await run_fetch_guarded(
                lambda: akshare_service.fetch_gc_daily_closes(code),
                timeout=min(float(settings.fetch_timeout), 20.0),
                lock=service.kline_lock,
            )
        except FetchBusy:
            logger.info("%s monthly fallback skipped: kline busy", quote_id)
            return "busy"
        except Exception as exc:  # noqa: BLE001
            logger.warning("%s monthly fallback failed: %s", quote_id, exc)
            return "fail"

    if not closes:
        return "fail"
    service.set_monthly(quote_id, [float(c) for c in closes[-22:]])
    service.refresh_sparkline(quote_id)
    logger.info("%s monthly sparkline refreshed (%d pts)", quote_id, len(closes[-22:]))
    return "ok"


async def gold_monthly_refresher(service: MarketService) -> None:
    """期金与现货共用一条低频循环。"""
    while True:
        statuses = [await _refresh_gold_monthly(service, code, quote_id)
                    for code, quote_id in (("GC", "gold_global"), ("XAU", "gold_spot"))]
        if all(s == "ok" for s in statuses):
            await asyncio.sleep(_jittered(settings.sparkline_refresh_interval))
        elif "busy" in statuses:
            await asyncio.sleep(15.0)
        else:
            await asyncio.sleep(120.0)


async def _refresh_sge_monthly(service: MarketService) -> str:
    """首页上海黄金卡行情线：SGE 日线最近 22 个收盘，与实时采集解耦。"""
    try:
        daily = await run_fetch_guarded(
            lambda: akshare_service.fetch_sge_daily("Au99.99"),
            timeout=min(float(settings.fetch_timeout), 20.0),
            lock=service.sge_lock,
        )
        if daily is not None and len(daily.closes) >= 2:
            service.set_sge_monthly([float(c) for c in daily.closes[-22:]])
            service.refresh_sparkline("gold_cn")
            logger.info("sge monthly sparkline refreshed (%d pts)", len(daily.closes[-22:]))
            return "ok"
        return "fail"
    except FetchBusy:
        logger.info("sge monthly refresh skipped: sge busy")
        return "busy"
    except Exception as exc:  # noqa: BLE001
        logger.warning("sge monthly refresh failed: %s", exc)
        return "fail"


async def sge_monthly_refresher(service: MarketService) -> None:
    while True:
        status = await _refresh_sge_monthly(service)
        if status == "ok":
            await asyncio.sleep(_jittered(settings.sparkline_refresh_interval))
        else:
            await asyncio.sleep(15.0 if status == "busy" else 120.0)


def start_collectors(service: MarketService) -> list[asyncio.Task]:
    if settings.yf_force_429:
        # 测试模式：模拟全部外部源失败，验证退避/冷却/缓存降级（AGENTS.md 第 31 节）
        return [asyncio.create_task(_forced_fail_loop(service))]

    tasks = [asyncio.create_task(run_collector(service, spec)) for spec in build_specs(service)]
    tasks.append(asyncio.create_task(gold_monthly_refresher(service)))
    tasks.append(asyncio.create_task(sge_monthly_refresher(service)))
    return tasks


async def _forced_fail_loop(service: MarketService) -> None:
    logger.warning("YF_FORCE_429 enabled: simulating permanent source failure")
    while True:
        service.em_health.on_request()
        service.mark_em_stale("simulated failure for testing")
        service.mark_gc_stale("simulated failure for testing")
        service.mark_sge_stale("simulated failure for testing")
        await asyncio.sleep(min(service.em_health.backoff_delay(), 30))
