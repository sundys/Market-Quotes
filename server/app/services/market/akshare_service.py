"""AKShare 上海黄金交易所采集服务（AGENTS.md 第 5/12/24 节）。

- 实时：ak.spot_quotations_sge(symbol="Au99.99") —— 只有现价。
- 历史：ak.spot_hist_sge(symbol="Au99.99") —— 提供前一交易日收盘价。
- AKShare 的中文字段不允许泄漏到 Flutter，全部转换成统一模型。
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime
from typing import Optional, Tuple

logger = logging.getLogger("market.akshare")


@dataclass
class SgeQuote:
    price: float
    timestamp: datetime


@dataclass
class SgePrevClose:
    trade_date: date
    close: float


_CANDIDATE_NAME_COLS = ("品种", "品种名称", "合约", "名称")
_CANDIDATE_PRICE_COLS = ("最新价", "现价", "价格", "收盘价", "最新")
_CANDIDATE_TIME_COLS = ("更新时间", "时间", "报价时间", "日期")


def _pick_column(df, candidates):
    for col in df.columns:
        if str(col).strip() in candidates:
            return col
    return None


def fetch_sge_quote(symbol: str = "Au99.99") -> SgeQuote:
    """获取 SGE 实时现价。返回空数据/字段缺失时抛 ValueError。"""
    import akshare as ak

    df = ak.spot_quotations_sge(symbol=symbol)
    if df is None or df.empty:
        raise ValueError("spot_quotations_sge returned empty dataframe")

    name_col = _pick_column(df, _CANDIDATE_NAME_COLS)
    price_col = _pick_column(df, _CANDIDATE_PRICE_COLS)
    time_col = _pick_column(df, _CANDIDATE_TIME_COLS)
    if price_col is None:
        raise ValueError(f"unexpected sge columns: {list(df.columns)}")

    row = df
    if name_col is not None:
        matched = df[df[name_col].astype(str).str.contains(symbol.replace(" ", ""), na=False)]
        if not matched.empty:
            row = matched

    price = float(row.iloc[0][price_col])
    if price <= 0:
        raise ValueError(f"invalid sge price: {price}")

    ts_raw = None
    if time_col is not None:
        ts_raw = row.iloc[0][time_col]
    ts = _parse_ts(ts_raw)
    return SgeQuote(price=price, timestamp=ts)


def _parse_ts(ts_raw) -> datetime:
    if ts_raw is None or str(ts_raw).strip() in ("", "nan", "NaT"):
        return datetime.now()
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(str(ts_raw).strip(), fmt)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(str(ts_raw))
    except ValueError:
        return datetime.now()


def fetch_sge_prev_close(symbol: str = "Au99.99") -> Optional[SgePrevClose]:
    """取最近一个有效交易日的收盘价作为 previous close（不含当日）。"""
    import akshare as ak

    df = ak.spot_hist_sge(symbol=symbol)
    if df is None or df.empty:
        return None
    date_col = _pick_column(df, ("date", "日期"))
    close_col = _pick_column(df, ("close", "收盘", "收盘价"))
    if date_col is None or close_col is None:
        logger.warning("unexpected sge hist columns: %s", list(df.columns))
        return None
    today = date.today()
    rows = [(d, float(c)) for d, c in zip(df[date_col], df[close_col]) if float(c) > 0]
    rows = [(d, c) for d, c in rows if d < today]
    if not rows:
        return None
    last_date, last_close = max(rows, key=lambda x: x[0])
    if isinstance(last_date, str):
        last_date = datetime.strptime(last_date[:10], "%Y-%m-%d").date()
    return SgePrevClose(trade_date=last_date, close=last_close)


def fetch_sge_daily_closes(symbol: str = "Au99.99") -> list:
    """SGE 日线收盘价序列（时间升序），供详情页 周/月/半年/年 走势。"""
    import akshare as ak

    df = ak.spot_hist_sge(symbol=symbol)
    if df is None or df.empty:
        return []
    date_col = _pick_column(df, ("date", "日期"))
    close_col = _pick_column(df, ("close", "收盘", "收盘价"))
    if date_col is None or close_col is None:
        logger.warning("unexpected sge hist columns: %s", list(df.columns))
        return []
    rows = []
    for d, c in zip(df[date_col], df[close_col]):
        c = float(c)
        if c > 0:
            rows.append((str(d), c))
    rows.sort(key=lambda x: x[0])
    return [c for _, c in rows]


def fetch_gc_realtime() -> dict:
    """COMEX 黄金期货实时（新浪外盘，经 AKShare）。含昨日结算价。"""
    import akshare as ak

    df = ak.futures_foreign_commodity_realtime(symbol="GC")
    if df is None or df.empty:
        raise ValueError("GC realtime returned empty")
    row = df.iloc[0]
    price = float(row["最新价"])
    if price <= 0:
        raise ValueError(f"invalid GC price: {price}")
    ts_raw = f"{row.get('日期', '')} {row.get('行情时间', '')}".strip()
    ts = _parse_ts(ts_raw if ts_raw.strip() else None)
    prev = row.get("昨日结算价")
    return {
        "name": str(row.get("名称", "COMEX黄金")),
        "price": price,
        "prev_settlement": float(prev) if prev not in (None, "-", 0) else None,
        "timestamp": ts,
    }


def fetch_gc_daily_closes(symbol: str = "GC") -> list:
    """COMEX 黄金日线收盘序列（时间升序），供详情页走势。"""
    import akshare as ak

    df = ak.futures_foreign_hist(symbol=symbol)
    if df is None or df.empty:
        return []
    if "close" not in df.columns:
        logger.warning("unexpected GC hist columns: %s", list(df.columns))
        return []
    return [float(c) for c in df["close"] if float(c) > 0]


def current_sge_trade_session_open(now: Optional[datetime] = None) -> bool:
    """SGE 日盘约 09:00-15:30（简化处理，不含夜盘）。"""
    now = now or datetime.now()
    if now.weekday() >= 5:
        return False
    minutes = now.hour * 60 + now.minute
    return 9 * 60 <= minutes <= 15 * 60 + 30
