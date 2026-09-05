"""yfinance 采集服务（AGENTS.md 第 4/6/23 节）。

- 批量请求合并：一次 yf.download 同时取 XAUUSD=X / ^NDX / ^GSPC。
- 复用 yfinance 自带的 curl_cffi Session，不人为禁用 Cookie/Crumb 管理。
- 路由层禁止直接调用本模块；统一走 MarketService。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, List, Optional

logger = logging.getLogger("market.yfinance")


class RateLimitError(Exception):
    """yfinance 触发 Yahoo 429 限速。"""


@dataclass
class SymbolSnapshot:
    price: Optional[float]
    previous_close: Optional[float]
    timestamp: Optional[datetime]
    sparkline: List[float]


def _detect_rate_limit(exc: Exception) -> bool:
    try:
        from yfinance.exceptions import YFRateLimitError  # noqa: F401

        if isinstance(exc, YFRateLimitError):
            return True
    except ImportError:
        pass
    text = f"{type(exc).__name__}: {exc}".lower()
    return "429" in text or "too many requests" in text or "ratelimit" in text


def _daily_closes(dates, closes) -> Dict[str, float]:
    """按本地日期聚合出每日最新收盘价。"""
    daily: Dict[str, float] = {}
    for dt, close in zip(dates, closes):
        if close is None:
            continue
        key = dt.date().isoformat()
        daily[key] = float(close)
    return daily


def _parse_symbol(df_slice) -> Optional[SymbolSnapshot]:
    closes = df_slice["Close"].dropna() if "Close" in df_slice else df_slice.dropna()
    if closes.empty:
        return None
    daily = _daily_closes(closes.index, closes.values)
    if not daily:
        return None
    dates_sorted = sorted(daily.keys())
    last_date = dates_sorted[-1]
    price = daily[last_date]
    previous_close = daily[dates_sorted[-2]] if len(dates_sorted) >= 2 else None
    sparkline = [round(float(v), 4) for v in closes.tail(60).values if v is not None]
    ts = closes.index[-1].to_pydatetime()
    return SymbolSnapshot(
        price=price,
        previous_close=previous_close,
        timestamp=ts,
        sparkline=sparkline,
    )


def fetch_history(symbol: str, period: str, interval: str) -> List[float]:
    """单标的历史收盘序列（详情页走势）。429/空数据抛 RateLimitError。"""
    import yfinance as yf

    try:
        df = yf.download(
            tickers=symbol,
            period=period,
            interval=interval,
            group_by="ticker",
            auto_adjust=False,
            progress=False,
            threads=False,
        )
    except Exception as exc:  # noqa: BLE001
        if _detect_rate_limit(exc):
            raise RateLimitError(str(exc)) from exc
        raise

    if df is None or df.empty:
        raise RateLimitError(f"no history for {symbol} {period}/{interval}")
    closes = df["Close"].dropna() if "Close" in df.columns else df.dropna()
    if closes.empty:
        raise RateLimitError(f"no history for {symbol} {period}/{interval}")
    return [float(v) for v in closes.values]


def fetch_batch(symbols: List[str], period: str = "5d", interval: str = "15m") -> Dict[str, SymbolSnapshot]:
    """批量获取多个标的，返回 symbol -> SymbolSnapshot。任何 429 抛 RateLimitError。"""
    import yfinance as yf

    try:
        df = yf.download(
            tickers=symbols,
            period=period,
            interval=interval,
            group_by="ticker",
            auto_adjust=False,
            progress=False,
            threads=True,
        )
    except Exception as exc:  # noqa: BLE001
        if _detect_rate_limit(exc):
            raise RateLimitError(str(exc)) from exc
        raise

    if df is None or df.empty:
        # yfinance 在部分限速场景不抛异常而是返回空数据，同样按失败处理
        raise RateLimitError("yfinance returned empty dataframe (possible rate limit)")

    result: Dict[str, SymbolSnapshot] = {}
    for symbol in symbols:
        try:
            if isinstance(df.columns, __import__("pandas").MultiIndex):
                if symbol not in df.columns.get_level_values(0):
                    continue
                snapshot = _parse_symbol(df[symbol])
            else:
                snapshot = _parse_symbol(df)
        except Exception as exc:  # noqa: BLE001
            logger.warning("parse %s failed: %s", symbol, exc)
            continue
        if snapshot is not None:
            result[symbol] = snapshot
    return result
