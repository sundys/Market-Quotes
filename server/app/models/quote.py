"""统一数据模型 MarketQuote（AGENTS.md 第 25 节）。

后端内部与 API 输出都使用该模型，更换数据源不影响 Flutter。
"""
from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from typing import List, Optional


def _clean(value):
    if isinstance(value, float) and not math.isfinite(value):
        return None
    return value


@dataclass
class MarketQuote:
    id: str
    name: str
    symbol: str
    price: Optional[float] = None
    change: Optional[float] = None
    change_percent: Optional[float] = None
    currency: str = "USD"
    unit: Optional[str] = None
    source: str = ""
    timestamp: Optional[str] = None
    market_status: str = "unknown"
    is_stale: bool = False
    sparkline: List[float] = field(default_factory=list)
    # 盘面明细（指数详情页展示；无数据的源为 None）
    open: Optional[float] = None
    high: Optional[float] = None
    low: Optional[float] = None
    prev_close: Optional[float] = None
    volume: Optional[float] = None

    def is_valid(self) -> bool:
        """数据质量检查（AGENTS.md 第 22 节）。"""
        if self.price is None or not math.isfinite(self.price) or self.price <= 0:
            return False
        if self.timestamp is None:
            return False
        if self.change is not None and not math.isfinite(self.change):
            return False
        if self.change_percent is not None and not math.isfinite(self.change_percent):
            return False
        return True

    def to_dict(self) -> dict:
        data = asdict(self)
        return {k: _clean(v) for k, v in data.items()}


def compute_change(price: float, previous_close: Optional[float]):
    """统一涨跌幅计算（AGENTS.md 第 11 节）。"""
    if previous_close is None or previous_close <= 0:
        return None, None
    change = price - previous_close
    change_percent = change / previous_close * 100.0
    if not math.isfinite(change) or not math.isfinite(change_percent):
        return None, None
    return change, change_percent
