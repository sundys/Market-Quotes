"""API 路由：只读缓存，不直接访问第三方数据源（AGENTS.md 第 23/26 节）。"""
from __future__ import annotations

from fastapi import APIRouter

from app.services.market.market_service import MarketService

router = APIRouter(prefix="/api")
root_router = APIRouter()

_service: MarketService | None = None


def init_router(service: MarketService) -> None:
    global _service
    _service = service


def get_service() -> MarketService:
    assert _service is not None, "MarketService not initialized"
    return _service


@router.get("/market/overview")
def market_overview():
    """一次返回首页全部行情（读缓存，毫秒级响应）。"""
    return get_service().overview()


@router.get("/market/{quote_id}/history")
async def market_history(quote_id: str, period: str = "1m"):
    """详情页历史走势：period ∈ 1d/1w/1m/6m/1y（读缓存，失败返回最近缓存并标 stale）。

    历史抓取可能等待数据源锁/网络，放到线程执行，避免阻塞事件循环拖垮其它请求。
    """
    import asyncio

    from fastapi import HTTPException

    from app.services.market.history_service import PERIODS

    if period not in PERIODS:
        raise HTTPException(status_code=400, detail=f"period must be one of {PERIODS}")
    return await asyncio.to_thread(get_service().history, quote_id, period)


@root_router.get("/health")
def health():
    """供监控/人工检查：数据源健康、429 计数、缓存命中、最后成功时间。"""
    return get_service().health()
