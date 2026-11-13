"""采集调度测试：busy 不记失败、失败隔离、涨跌基准跨日刷新（AGENTS.md 第 7/12/31 节）。"""
import asyncio
import sys
import threading
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from app.services.market import registry  # noqa: E402
from app.services.market.akshare_service import SgeDaily  # noqa: E402
from app.services.market.cache_service import CacheService  # noqa: E402
from app.services.market.market_service import MarketService  # noqa: E402
from app.services.market.rate_limiter import SourceHealth  # noqa: E402
from app.workers import collectors  # noqa: E402


def make_service(tmp_path):
    return MarketService(CacheService(str(tmp_path)))


def make_spec(fetch, lock=None, apply=None):
    return collectors.CollectorSpec(
        name="test",
        group=registry.GROUP_SGE,
        source_key="sge",
        lock=lock or threading.Lock(),
        health=SourceHealth(),
        fetch=fetch,
        apply=apply or (lambda result: None),
        interval=lambda: 30,
    )


def sge_snap(price=800.0, ts=None):
    return {"price": price, "timestamp": ts or datetime.now(),
            "open": price - 1, "high": price + 1, "low": price - 2}


# ---- 调度语义 ----
def test_collect_once_success_records_latency(tmp_path):
    svc = make_service(tmp_path)
    spec = make_spec(fetch=lambda: {"ok": True})
    assert asyncio.run(collectors.collect_once(svc, spec)) == "ok"
    assert spec.health.successful_requests == 1
    assert spec.health.consecutive_failures == 0
    assert svc.latencies["sge"] is not None


def test_collect_once_busy_is_not_a_failure(tmp_path):
    """上一轮仍在飞：只跳过，不能记失败/进冷却（旧实现会误判数据源故障）。"""
    svc = make_service(tmp_path)
    lock = threading.Lock()
    lock.acquire()
    spec = make_spec(fetch=lambda: {"ok": True}, lock=lock)
    try:
        assert asyncio.run(collectors.collect_once(svc, spec)) == "busy"
    finally:
        lock.release()
    assert spec.health.failed_requests == 0
    assert spec.health.consecutive_failures == 0
    assert not spec.health.in_cooldown()


def test_collect_once_failure_marks_stale_and_backs_off(tmp_path):
    svc = make_service(tmp_path)
    svc.apply_sge(sge_snap())

    def boom():
        raise RuntimeError("connection reset")

    spec = make_spec(fetch=boom)
    assert asyncio.run(collectors.collect_once(svc, spec)) == "fail"
    assert svc.cache.get_quote("gold_cn")["is_stale"] is True
    assert spec.health.failed_requests == 1
    assert spec.health.in_cooldown()


def test_collect_once_cooldown_skips_request(tmp_path):
    svc = make_service(tmp_path)
    spec = make_spec(fetch=lambda: {"ok": True})
    spec.health.enter_cooldown(60)
    assert asyncio.run(collectors.collect_once(svc, spec)) == "cooldown"
    assert spec.health.total_requests == 0


def test_timeout_is_always_shorter_than_interval():
    assert collectors._timeout_for(30) < 30
    assert collectors._timeout_for(5) >= 3


def test_jitter_stays_within_bounds():
    for _ in range(50):
        assert 27 <= collectors._jittered(30) <= 33


# ---- 涨跌基准 ----
def test_sge_prev_close_refreshes_once_per_day(tmp_path):
    svc = make_service(tmp_path)
    daily = SgeDaily(trade_date=date(2026, 11, 12), prev_close=851.33,
                     labels=["2026-11-12"], closes=[851.33])

    assert collectors._apply_sge_daily(svc, daily) is True
    assert svc.cache.get_previous_close("Au99.99") == 851.33
    assert svc.cache.previous_close_fetched_on("Au99.99") == date.today().isoformat()

    # 同一天再采集：不再刷新（旧实现把“交易日 != 今天”当条件，每 30 秒都重新拉历史）
    assert collectors._apply_sge_daily(svc, daily) is False


def test_sge_daily_refresh_only_needed_on_new_day(tmp_path):
    svc = make_service(tmp_path)
    assert collectors._needs_daily_refresh(svc) is True
    collectors._apply_sge_daily(
        svc, SgeDaily(trade_date=date(2026, 11, 12), prev_close=851.33,
                      labels=[], closes=[]))
    assert collectors._needs_daily_refresh(svc) is False


def test_sge_quote_uses_refreshed_prev_close(tmp_path):
    """回归：涨跌基准必须真正写进缓存，apply_sge 才能算出涨跌幅。"""
    svc = make_service(tmp_path)
    collectors._apply_sge_daily(
        svc, SgeDaily(trade_date=date(2026, 11, 12), prev_close=800.0,
                      labels=[], closes=[]))
    svc.apply_sge(sge_snap(price=808.0))

    item = svc.cache.get_quote("gold_cn")
    assert item["prev_close"] == 800.0
    assert abs(item["change"] - 8.0) < 1e-9
    assert abs(item["change_percent"] - 1.0) < 1e-9


def test_sge_quote_timestamp_is_source_time(tmp_path):
    svc = make_service(tmp_path)
    svc.apply_sge(sge_snap(price=837.5, ts=datetime(2026, 11, 13, 15, 30)))
    assert svc.cache.get_quote("gold_cn")["timestamp"].startswith("2026-11-13T15:30")


def test_sge_prev_close_persists_across_restart(tmp_path):
    svc = make_service(tmp_path)
    collectors._apply_sge_daily(
        svc, SgeDaily(trade_date=date(2026, 11, 12), prev_close=851.33,
                      labels=[], closes=[]))
    svc.cache.save_disk(force=True)

    restarted = CacheService(str(tmp_path))
    assert restarted.get_previous_close("Au99.99") == 851.33
    assert restarted.previous_close_fetched_on("Au99.99") == date.today().isoformat()


def test_sge_session_excludes_lunch_break():
    """午间休市不采集：否则既浪费请求，又会把“数据没变”误判成 stale。"""
    from app.services.market.akshare_service import current_sge_trade_session_open as is_open

    assert is_open(datetime(2026, 11, 13, 9, 0)) is True
    assert is_open(datetime(2026, 11, 13, 11, 0)) is True
    assert is_open(datetime(2026, 11, 13, 12, 0)) is False   # 午休
    assert is_open(datetime(2026, 11, 13, 14, 0)) is True
    assert is_open(datetime(2026, 11, 13, 15, 45)) is False  # 已收盘
    assert is_open(datetime(2026, 11, 14, 10, 0)) is False   # 周六


def test_sge_monthly_sparkline_updated_from_daily(tmp_path):
    svc = make_service(tmp_path)
    closes = [float(i) for i in range(30)]
    collectors._apply_sge_daily(
        svc, SgeDaily(trade_date=date(2026, 11, 12), prev_close=1.0,
                      labels=[str(i) for i in range(30)], closes=closes))
    assert svc.sge_monthly == closes[-22:]
