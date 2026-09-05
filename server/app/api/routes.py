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


@root_router.get("/health")
def health():
    """供监控/人工检查：数据源健康、429 计数、缓存命中、最后成功时间。"""
    return get_service().health()
