"""集中配置：全部来自环境变量，参考 AGENTS.md 第 33 节。"""
from __future__ import annotations

import os


def _int_env(name: str, default: int) -> int:
    try:
        return int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


def _float_env(name: str, default: float) -> float:
    try:
        return float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        return default


class Settings:
    def __init__(self) -> None:
        self.app_env: str = os.getenv("APP_ENV", "development")
        self.cache_ttl: int = _int_env("CACHE_TTL", 60)

        # 美股指数（东方财富）采集器
        self.yf_min_interval: int = _int_env("YF_MIN_INTERVAL", 45)
        self.yf_max_retries: int = _int_env("YF_MAX_RETRIES", 3)
        self.yf_backoff_base: int = _int_env("YF_BACKOFF_BASE", 5)
        self.yf_backoff_max: int = _int_env("YF_BACKOFF_MAX", 120)

        # COMEX 期金（新浪外盘）与上海黄金交易所采集器
        self.gc_refresh_interval: int = _int_env("GC_REFRESH_INTERVAL", 30)
        self.sge_refresh_interval: int = _int_env("SGE_REFRESH_INTERVAL", 30)

        # 休市时的降频采集间隔
        self.closed_market_interval: int = _int_env("CLOSED_MARKET_INTERVAL", 300)

        # 单次抓取超时（会被自动压到“小于采集间隔”）；抖动比例；SGE 日线缓存 TTL
        self.fetch_timeout: float = _float_env("FETCH_TIMEOUT", 10)
        self.fetch_jitter: float = _float_env("FETCH_JITTER", 0.1)
        self.sge_hist_ttl: int = _int_env("SGE_HIST_TTL", 3600)
        self.sparkline_refresh_interval: int = _int_env("SPARKLINE_REFRESH_INTERVAL", 3600)

        # 磁盘快照最小写盘间隔、第三方 SDK 默认 socket 超时
        self.disk_save_min_interval: float = _float_env("DISK_SAVE_MIN_INTERVAL", 5)
        self.socket_timeout: int = _int_env("SOCKET_TIMEOUT", 15)

        self.api_timeout: int = _int_env("API_TIMEOUT", 15)

        # 测试专用：模拟数据源一直返回 429，验证退避/冷却/缓存降级
        self.yf_force_429: bool = os.getenv("YF_FORCE_429", "0") == "1"

        # 磁盘缓存目录
        self.data_dir: str = os.getenv("DATA_DIR", os.path.join("cache"))


settings = Settings()
