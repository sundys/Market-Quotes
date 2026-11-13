"""AKShare 上海黄金交易所 / COMEX 黄金历史数据服务（AGENTS.md 第 5/12/24 节）。

职责收敛为“日线历史 + 交易时段判断”：
- 实时行情分别由 sge_client（SGE）与 sina_client（COMEX）一次请求取全量；
- 日线历史仍走 AKShare（spot_hist_sge / futures_foreign_hist），符合数据源约定。

日线结果带 TTL 进程内缓存：采集器的涨跌基准、首页月线、详情页历史三处共用
同一次请求，避免以前“每 30 秒拉一次 2402 行历史”的浪费。

AKShare 的中文字段不允许泄漏到 Flutter，全部转换成统一模型。
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Dict, List, Optional, Tuple

from app.config import settings

logger = logging.getLogger("market.akshare")

# 日线历史进程内缓存：(抓取时间戳, 数据)；失败也短暂缓存，避免故障时打爆数据源
_daily_cache: Dict[str, Tuple[float, Optional["SgeDaily"]]] = {}
_daily_lock = threading.Lock()
_FAILURE_TTL = 60


@dataclass
class SgeDaily:
    """SGE 日线：最近交易日收盘（涨跌基准）+ 完整收盘序列（月线/历史）。"""

    trade_date: Optional[date] = None
    prev_close: Optional[float] = None
    labels: List[str] = field(default_factory=list)
    closes: List[float] = field(default_factory=list)


@dataclass
class SgePrevClose:
    """兼容旧接口：仅取最近交易日收盘。"""

    trade_date: date
    close: float


def _pick_column(df, candidates):
    for col in df.columns:
        if str(col).strip() in candidates:
            return col
    return None


def fetch_sge_daily(symbol: str = "Au99.99", ttl: Optional[int] = None) -> Optional[SgeDaily]:
    """SGE 日线（含涨跌基准），默认 TTL 1 小时；同一进程内只请求一次。"""
    ttl = settings.sge_hist_ttl if ttl is None else ttl
    now = time.time()
    with _daily_lock:
        cached = _daily_cache.get(symbol)
        if cached is not None:
            fetched_at, data = cached
            effective_ttl = ttl if data is not None else min(ttl, _FAILURE_TTL)
            if now - fetched_at < effective_ttl:
                return data
        try:
            data = _load_sge_daily(symbol)
        except Exception as exc:  # noqa: BLE001
            logger.warning("sge daily fetch failed: %s", exc)
            data = None
        _daily_cache[symbol] = (time.time(), data)
        return data


def _load_sge_daily(symbol: str) -> Optional[SgeDaily]:
    import akshare as ak

    df = ak.spot_hist_sge(symbol=symbol)
    if df is None or df.empty:
        return None
    date_col = _pick_column(df, ("date", "日期"))
    close_col = _pick_column(df, ("close", "收盘", "收盘价"))
    if date_col is None or close_col is None:
        logger.warning("unexpected sge hist columns: %s", list(df.columns))
        return None

    rows: List[Tuple[str, float]] = []
    for d, c in zip(df[date_col], df[close_col]):
        try:
            close = float(c)
        except (TypeError, ValueError):
            continue
        if close > 0:
            rows.append((str(d)[:10], close))
    if not rows:
        return None
    rows.sort(key=lambda x: x[0])

    today = date.today().isoformat()
    prev = [(d, c) for d, c in rows if d < today]
    trade_date = None
    prev_close = None
    if prev:
        trade_date = _parse_date(prev[-1][0])
        prev_close = prev[-1][1]

    return SgeDaily(
        trade_date=trade_date,
        prev_close=prev_close,
        labels=[d for d, _ in rows],
        closes=[c for _, c in rows],
    )


def _parse_date(text: str) -> Optional[date]:
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def fetch_sge_daily_closes(symbol: str = "Au99.99") -> Tuple[List[str], List[float]]:
    """SGE 日线（时间升序），返回 (日期标签, 收盘价)；与采集器共用同一份缓存。"""
    data = fetch_sge_daily(symbol)
    if data is None:
        return [], []
    return data.labels, data.closes


def fetch_sge_prev_close(symbol: str = "Au99.99") -> Optional[SgePrevClose]:
    """取最近一个有效交易日的收盘价作为 previous close（不含当日）。"""
    data = fetch_sge_daily(symbol)
    if data is None or data.prev_close is None or data.trade_date is None:
        return None
    return SgePrevClose(trade_date=data.trade_date, close=data.prev_close)


def fetch_gc_daily_closes(symbol: str = "GC") -> Tuple[List[str], List[float]]:
    """COMEX 黄金日线（时间升序），返回 (日期标签, 收盘价) 两列。"""
    import akshare as ak

    df = ak.futures_foreign_hist(symbol=symbol)
    if df is None or df.empty:
        return [], []
    if "close" not in df.columns or "date" not in df.columns:
        logger.warning("unexpected GC hist columns: %s", list(df.columns))
        return [], []
    labels: List[str] = []
    closes: List[float] = []
    for d, c in zip(df["date"], df["close"]):
        try:
            close = float(c)
        except (TypeError, ValueError):
            continue
        if close > 0:
            labels.append(str(d)[:10])
            closes.append(close)
    return labels, closes


def current_sge_trade_session_open(now: Optional[datetime] = None) -> bool:
    """SGE Au99.99 日盘：09:00-11:30、13:30-15:30（不含夜盘），法定节假日休市。

    午间休市必须识别出来：否则休市期间仍按 30 秒采集，而且“数据不更新”会被
    误判成 stale。
    """
    from app.services.market.holidays import is_cn_holiday

    now = now or datetime.now()
    if now.weekday() >= 5 or is_cn_holiday(now.date()):
        return False
    minutes = now.hour * 60 + now.minute
    morning = 9 * 60 <= minutes <= 11 * 60 + 30
    afternoon = 13 * 60 + 30 <= minutes <= 15 * 60 + 30
    return morning or afternoon
