"""标的注册表：项目“一共有哪些行情”的唯一来源。

之前同一个标的集合散落在 SYMBOLS、OVERVIEW_ORDER、em_service.INDEX_SECIDS、
Flutter 首页元数据四处，新增一个标的要改 5 个地方。现在统一在这里定义，
采集器按 group 分组取数、overview 按 ORDER 输出、App 只需按 id 兜底名称。

注意：这里的字段是“静态元数据”，刷新节奏由 config + 开闭市状态决定，
不写死在注册表里（休市降频、jitter 都依赖运行时判断）。
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional

GROUP_US_INDEX = "us_index"   # 东方财富全球指数（一次请求取全部）
GROUP_COMEX = "comex"         # 新浪外盘 COMEX 期金
GROUP_SGE = "sge"             # 上海黄金交易所 Au99.99


@dataclass(frozen=True)
class QuoteDef:
    id: str
    name: str
    symbol: str
    currency: str
    unit: Optional[str]
    source: str
    group: str


_QUOTES = (
    QuoteDef("gold_global", "国际黄金期货", "GC", "USD", "oz",
             "AKShare/新浪外盘(期金)", GROUP_COMEX),
    QuoteDef("nasdaq100", "纳斯达克100", "100.NDX", "USD", None,
             "AKShare/东财", GROUP_US_INDEX),
    QuoteDef("sp500", "标普500", "100.SPX", "USD", None,
             "AKShare/东财", GROUP_US_INDEX),
    QuoteDef("dowjones", "道琼斯", "100.DJIA", "USD", None,
             "AKShare/东财", GROUP_US_INDEX),
    QuoteDef("gold_cn", "上海黄金 Au99.99", "Au99.99", "CNY", "g",
             "AKShare/SGE", GROUP_SGE),
)

QUOTES: Dict[str, QuoteDef] = {q.id: q for q in _QUOTES}

# 首页输出顺序（黄金 → 指数 → 国内黄金）
ORDER = tuple(q.id for q in _QUOTES)


def get(quote_id: str) -> Optional[QuoteDef]:
    return QUOTES.get(quote_id)


def by_group(group: str) -> List[QuoteDef]:
    return [q for q in _QUOTES if q.group == group]


def ids_for_group(group: str) -> List[str]:
    return [q.id for q in _QUOTES if q.group == group]
