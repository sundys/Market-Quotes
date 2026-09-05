"""数据源健康状态与 429 退避/冷却（AGENTS.md 第 6/7 节）。

- 指数退避 + 随机抖动，禁止无限重试。
- 连续失败/429 后进入冷却：暂停主动请求，期间继续返回最近缓存。
"""
from __future__ import annotations

import random
import time
from typing import Optional


class SourceHealth:
    def __init__(self, backoff_base: int = 5, backoff_max: int = 120, max_retries: int = 3) -> None:
        self.backoff_base = backoff_base
        self.backoff_max = backoff_max
        self.max_retries = max_retries

        self.consecutive_failures = 0
        self.cooldown_until: float = 0.0
        self.last_error: Optional[str] = None
        self.total_requests = 0
        self.successful_requests = 0
        self.failed_requests = 0
        self.rate_limit_count = 0

    # ---- 退避计算 ----
    def backoff_delay(self) -> float:
        """delay = min(base * 2^retry, max) + jitter。第1次失败等待 base 秒。"""
        retry = min(max(self.consecutive_failures - 1, 0), self.max_retries)
        delay = min(self.backoff_base * (2 ** retry), self.backoff_max)
        jitter = random.uniform(0, self.backoff_base / 2.0)
        return delay + jitter

    def enter_cooldown(self, delay: float) -> None:
        self.cooldown_until = max(self.cooldown_until, time.time() + delay)

    def in_cooldown(self) -> bool:
        return time.time() < self.cooldown_until

    def cooldown_remaining(self) -> float:
        return max(0.0, self.cooldown_until - time.time())

    # ---- 状态流转 ----
    def on_request(self) -> None:
        self.total_requests += 1

    def on_success(self) -> None:
        self.successful_requests += 1
        self.consecutive_failures = 0
        self.cooldown_until = 0.0
        self.last_error = None

    def on_rate_limit(self) -> None:
        self.rate_limit_count += 1
        self.failed_requests += 1
        self.consecutive_failures += 1
        self.last_error = "rate_limited(429)"
        self.enter_cooldown(self.backoff_delay())

    def on_failure(self, error: str) -> None:
        self.failed_requests += 1
        self.consecutive_failures += 1
        self.last_error = error[:200]
        self.enter_cooldown(self.backoff_delay())

    def stats(self) -> dict:
        return {
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "rate_limit_count": self.rate_limit_count,
            "consecutive_failures": self.consecutive_failures,
            "in_cooldown": self.in_cooldown(),
            "cooldown_remaining": round(self.cooldown_remaining(), 1),
            "last_error": self.last_error,
        }
