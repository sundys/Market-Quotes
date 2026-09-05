"""429 退避/冷却策略测试（AGENTS.md 第 7/31 节）。"""
import time

from app.services.market.rate_limiter import SourceHealth


def test_backoff_delay_grows_exponentially():
    h = SourceHealth(backoff_base=5, backoff_max=120, max_retries=5)
    h.on_rate_limit()
    first = h.backoff_delay()
    h.on_rate_limit()
    second = h.backoff_delay()
    # 第1次约 5~7.5s，第2次约 10~12.5s（含 jitter）
    assert 5 <= first <= 8
    assert 10 <= second <= 13


def test_backoff_delay_capped():
    h = SourceHealth(backoff_base=5, backoff_max=120, max_retries=3)
    for _ in range(10):
        h.on_rate_limit()
    assert h.backoff_delay() <= 120 + 2.5


def test_rate_limit_triggers_cooldown():
    h = SourceHealth()
    assert not h.in_cooldown()
    h.on_rate_limit()
    assert h.in_cooldown()
    assert h.cooldown_remaining() > 0


def test_success_resets_state():
    h = SourceHealth()
    h.on_rate_limit()
    h.on_rate_limit()
    assert h.consecutive_failures == 2
    h.on_success()
    assert h.consecutive_failures == 0
    assert not h.in_cooldown()
    assert h.last_error is None


def test_stats_counters():
    h = SourceHealth()
    h.on_request()
    h.on_rate_limit()
    s = h.stats()
    assert s["total_requests"] == 1
    assert s["rate_limit_count"] == 1
    assert s["failed_requests"] == 1
    assert s["last_error"] == "rate_limited(429)"
