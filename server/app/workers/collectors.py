"""后台采集任务（AGENTS.md 第 6/27 节）。

- yfinance：正常运行每 30~60 秒一次，批量请求；休市时降频。
- SGE：每 15~30 秒一次；休市时降频。
- 429/失败进入冷却：暂停主动请求，冷却结束后再试，禁止无限重试。
- 采集在独立线程执行并带硬超时：yfinance 内部没有可靠的请求超时，
  网络被墙/挂起时不能让采集循环永久卡死。
- 在飞保护：上一次请求仍未返回时不发起新请求，避免线程堆积。
"""
from __future__ import annotations

import asyncio
import logging
import threading
import time
from datetime import datetime

from app.config import settings
from app.services.market import akshare_service, yfinance_service
from app.services.market.market_service import MarketService, us_market_open

logger = logging.getLogger("market.workers")

YF_SYMBOLS = ["XAUUSD=X", "GC=F", "^NDX", "^GSPC"]


class FetchBusy(Exception):
    """上一次请求仍在执行，本轮跳过。"""


def _wrap_with_lock(fn, lock: threading.Lock):
    def wrapped(*args):
        try:
            return fn(*args)
        finally:
            lock.release()
    return wrapped


async def run_fetch_guarded(fn, *args, timeout: float, lock: threading.Lock):
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


def _any_recent_gold_activity() -> bool:
    """国际黄金(XAUUSD=X)几乎全天交易，工作日按活跃处理。"""
    return datetime.now().weekday() < 5


async def yfinance_collector(service: MarketService) -> None:
    lock = threading.Lock()
    while True:
        interval = settings.yf_min_interval
        if not us_market_open() and not _any_recent_gold_activity():
            # 休市期间自动降低请求频率（AGENTS.md 第 27 节）
            interval = settings.closed_market_interval

        if service.yf_health.in_cooldown():
            remaining = service.yf_health.cooldown_remaining()
            logger.info("yfinance cooling down %.0fs", remaining)
            await asyncio.sleep(min(remaining, 30))
            continue

        service.yf_health.on_request()
        started = time.perf_counter()
        try:
            snapshots = await run_fetch_guarded(
                yfinance_service.fetch_batch, YF_SYMBOLS,
                timeout=_fetch_timeout(), lock=lock,
            )
            latency = int((time.perf_counter() - started) * 1000)
            if "XAUUSD=X" not in snapshots and "GC=F" in snapshots:
                logger.info("XAUUSD=X 无数据，国际黄金回退为期货 GC=F")
            service.apply_yfinance_snapshots(snapshots)
            service.yf_health.on_success()
            _log_fetch("yfinance", ",".join(snapshots.keys()), "ok", latency)
            service.cache.save_disk()
            await asyncio.sleep(interval)
        except yfinance_service.RateLimitError as exc:
            latency = int((time.perf_counter() - started) * 1000)
            service.mark_yfinance_stale(str(exc))
            _log_fetch("yfinance", "batch", "429", latency)
            service.cache.save_disk()
            await asyncio.sleep(min(service.yf_health.backoff_delay(), 120))
        except FetchBusy:
            service.yf_health.on_failure("previous fetch still in flight")
            _log_fetch("yfinance", "batch", "busy", 0)
            await asyncio.sleep(interval)
        except Exception as exc:  # noqa: BLE001
            latency = int((time.perf_counter() - started) * 1000)
            service.mark_yfinance_stale(str(exc))
            _log_fetch("yfinance", "batch", "fail", latency, str(exc))
            service.cache.save_disk()
            await asyncio.sleep(min(service.yf_health.backoff_delay(), 120))


async def sge_collector(service: MarketService) -> None:
    from app.services.market.akshare_service import current_sge_trade_session_open

    lock = threading.Lock()
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
            quote = await run_fetch_guarded(
                akshare_service.fetch_sge_quote, "Au99.99",
                timeout=_fetch_timeout(), lock=lock,
            )
            latency = int((time.perf_counter() - started) * 1000)

            # 每天首次采集时刷新 previous close（最近交易日收盘价）
            today = datetime.now().date()
            if prev_close is None or prev_date != today:
                try:
                    hist = await run_fetch_guarded(
                        akshare_service.fetch_sge_prev_close, "Au99.99",
                        timeout=_fetch_timeout(), lock=lock,
                    )
                    if hist is not None:
                        prev_close = hist.close
                        prev_date = hist.trade_date
                except Exception as exc:  # noqa: BLE001
                    logger.warning("sge prev_close fetch failed: %s", exc)

            service.apply_sge(quote.price, quote.timestamp, prev_close, prev_date)
            service.sge_health.on_success()
            _log_fetch("akshare", "Au99.99", "ok", latency)
            service.cache.save_disk()
            await asyncio.sleep(interval)
        except FetchBusy:
            service.sge_health.on_failure("previous fetch still in flight")
            _log_fetch("akshare", "Au99.99", "busy", 0)
            await asyncio.sleep(interval)
        except Exception as exc:  # noqa: BLE001
            latency = int((time.perf_counter() - started) * 1000)
            service.mark_sge_stale(str(exc))
            _log_fetch("akshare", "Au99.99", "fail", latency, str(exc))
            service.cache.save_disk()
            await asyncio.sleep(min(service.sge_health.backoff_delay(), 120))


def start_collectors(service: MarketService) -> list[asyncio.Task]:
    if settings.yf_force_429:
        # 测试模式：不真正请求，仅持续模拟 429，验证退避/冷却/缓存降级（AGENTS.md 第 31 节）
        return [asyncio.create_task(_forced_429_loop(service))]

    return [
        asyncio.create_task(yfinance_collector(service)),
        asyncio.create_task(sge_collector(service)),
    ]


async def _forced_429_loop(service: MarketService) -> None:
    logger.warning("YF_FORCE_429 enabled: simulating permanent rate limit")
    while True:
        service.yf_health.on_request()
        service.mark_yfinance_stale("simulated 429 for testing")
        await asyncio.sleep(min(service.yf_health.backoff_delay(), 30))
