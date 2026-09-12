"""后台采集任务（AGENTS.md 第 6/27 节）。数据源全部为 AKShare 生态：
- 东方财富：美股三大指数实时（一次请求）
- 新浪外盘：COMEX 黄金实时
- 上海黄金交易所：Au99.99 实时
- 退避/冷却/in-flight 保护与之前一致；历史走势接口与采集共用请求锁。
"""
from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime

from app.config import settings
from app.services.market import akshare_service, em_service
from app.services.market.market_service import MarketService, us_market_open

logger = logging.getLogger("market.workers")


class FetchBusy(Exception):
    """上一次请求仍在执行，本轮跳过。"""


def _wrap_with_lock(fn, lock):
    def wrapped(*args):
        try:
            return fn(*args)
        finally:
            lock.release()
    return wrapped


async def run_fetch_guarded(fn, *args, timeout: float, lock):
    """带在飞保护的线程执行；超时抛 TimeoutError，占用中抛 FetchBusy。"""
    if not lock.acquire(blocking=False):
        raise FetchBusy()
    wrapped = _wrap_with_lock(fn, lock)

    async def _runner():
        return await asyncio.to_thread(wrapped, *args)

    try:
        return await asyncio.wait_for(_runner(), timeout=timeout)
    except asyncio.TimeoutError:
        raise TimeoutError(f"fetch timed out after {timeout:.0f}s")


def _log_fetch(source: str, symbol: str, status: str, latency_ms: int, extra: str = "") -> None:
    logger.info("source=%s symbol=%s status=%s latency=%dms %s", source, symbol, status, latency_ms, extra)


def _fetch_timeout() -> float:
    return max(45.0, settings.api_timeout * 3)


async def em_collector(service: MarketService) -> None:
    """东方财富：美股三大指数，一次请求。"""
    while True:
        interval = settings.yf_min_interval
        if not us_market_open():
            interval = settings.closed_market_interval

        if service.em_health.in_cooldown():
            remaining = service.em_health.cooldown_remaining()
            logger.info("eastmoney cooling down %.0fs", remaining)
            await asyncio.sleep(min(remaining, 30))
            continue

        service.em_health.on_request()
        started = time.perf_counter()
        try:
            quotes = await run_fetch_guarded(
                em_service.fetch_global_indices,
                timeout=_fetch_timeout(), lock=service.em_lock,
            )
            latency = int((time.perf_counter() - started) * 1000)
            service.apply_index_quotes(quotes)
            service.em_health.on_success()
            _log_fetch("eastmoney", ",".join(quotes.keys()), "ok", latency)
            service.cache.save_disk()
            await asyncio.sleep(interval)
        except FetchBusy:
            service.em_health.on_failure("previous fetch still in flight")
            _log_fetch("eastmoney", "indices", "busy", 0)
            await asyncio.sleep(interval)
        except Exception as exc:  # noqa: BLE001
            latency = int((time.perf_counter() - started) * 1000)
            service.mark_em_stale(str(exc))
            _log_fetch("eastmoney", "indices", "fail", latency, str(exc))
            service.cache.save_disk()
            await asyncio.sleep(min(service.em_health.backoff_delay(), 120))


async def gc_collector(service: MarketService) -> None:
    """新浪外盘：COMEX 黄金实时。"""
    while True:
        # 外盘期货接近全天交易，固定间隔即可；周末降频
        interval = settings.sge_refresh_interval
        if datetime.now().weekday() >= 5:
            interval = settings.closed_market_interval

        if service.gc_health.in_cooldown():
            remaining = service.gc_health.cooldown_remaining()
            logger.info("gc cooling down %.0fs", remaining)
            await asyncio.sleep(min(remaining, 30))
            continue

        service.gc_health.on_request()
        started = time.perf_counter()
        try:
            snap = await run_fetch_guarded(
                akshare_service.fetch_gc_realtime,
                timeout=_fetch_timeout(), lock=service.gc_lock,
            )
            latency = int((time.perf_counter() - started) * 1000)
            service.apply_gold_quote(snap)
            service.gc_health.on_success()
            _log_fetch("sina-gc", "GC", "ok", latency)
            service.cache.save_disk()
            await asyncio.sleep(interval)
        except FetchBusy:
            service.gc_health.on_failure("previous fetch still in flight")
            _log_fetch("sina-gc", "GC", "busy", 0)
            await asyncio.sleep(interval)
        except Exception as exc:  # noqa: BLE001
            latency = int((time.perf_counter() - started) * 1000)
            service.mark_gc_stale(str(exc))
            _log_fetch("sina-gc", "GC", "fail", latency, str(exc))
            service.cache.save_disk()
            await asyncio.sleep(min(service.gc_health.backoff_delay(), 120))


async def sge_collector(service: MarketService) -> None:
    """上海黄金交易所：Au99.99 实时 + 最近交易日收盘基准。"""
    from app.services.market.akshare_service import current_sge_trade_session_open

    prev_close = service.cache.get_previous_close("Au99.99")
    prev_date = None

    while True:
        interval = settings.sge_refresh_interval
        if not current_sge_trade_session_open():
            interval = settings.closed_market_interval

        if service.sge_health.in_cooldown():
            remaining = service.sge_health.cooldown_remaining()
            logger.info("sge cooling down %.0fs", remaining)
            await asyncio.sleep(min(remaining, 30))
            continue

        service.sge_health.on_request()
        started = time.perf_counter()
        try:
            snap = await run_fetch_guarded(
                akshare_service.fetch_sge_quote, "Au99.99",
                timeout=_fetch_timeout(), lock=service.sge_lock,
            )
            latency = int((time.perf_counter() - started) * 1000)

            # 每天首次采集时刷新 previous close（最近交易日收盘价）
            today = datetime.now().date()
            if prev_close is None or prev_date != today:
                try:
                    hist = await run_fetch_guarded(
                        akshare_service.fetch_sge_prev_close, "Au99.99",
                        timeout=_fetch_timeout(), lock=service.sge_lock,
                    )
                    if hist is not None:
                        prev_close = hist.close
                        prev_date = hist.trade_date
                except Exception as exc:  # noqa: BLE001
                    logger.warning("sge prev_close fetch failed: %s", exc)

            service.apply_sge(snap)
            service.sge_health.on_success()
            _log_fetch("akshare-sge", "Au99.99", "ok", latency)
            service.cache.save_disk()
            await asyncio.sleep(interval)
        except FetchBusy:
            service.sge_health.on_failure("previous fetch still in flight")
            _log_fetch("akshare-sge", "Au99.99", "busy", 0)
            await asyncio.sleep(interval)
        except Exception as exc:  # noqa: BLE001
            latency = int((time.perf_counter() - started) * 1000)
            service.mark_sge_stale(str(exc))
            _log_fetch("akshare-sge", "Au99.99", "fail", latency, str(exc))
            service.cache.save_disk()
            await asyncio.sleep(min(service.sge_health.backoff_delay(), 120))


def start_collectors(service: MarketService) -> list[asyncio.Task]:
    if settings.yf_force_429:
        # 测试模式：模拟全部外部源失败，验证退避/冷却/缓存降级（AGENTS.md 第 31 节）
        return [asyncio.create_task(_forced_fail_loop(service))]

    return [
        asyncio.create_task(em_collector(service)),
        asyncio.create_task(gc_collector(service)),
        asyncio.create_task(sge_collector(service)),
    ]


async def _forced_fail_loop(service: MarketService) -> None:
    logger.warning("YF_FORCE_429 enabled: simulating permanent source failure")
    while True:
        service.em_health.on_request()
        service.mark_em_stale("simulated failure for testing")
        service.mark_gc_stale("simulated failure for testing")
        await asyncio.sleep(min(service.em_health.backoff_delay(), 30))
