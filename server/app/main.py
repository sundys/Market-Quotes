"""FastAPI 入口。

启动：
    uvicorn app.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import asyncio
import logging
import socket
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api import routes
from app.config import settings
from app.services.market.cache_service import CacheService
from app.services.market.market_service import MarketService
from app.workers import collectors

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # AKShare 内部的 requests 调用没有传 timeout，挂起会永久占住采集线程的锁；
    # 这里设置进程级默认超时作为兜底（本项目自己的请求都显式带 timeout）。
    socket.setdefaulttimeout(settings.socket_timeout)

    cache = CacheService(settings.data_dir, min_save_interval=settings.disk_save_min_interval)
    service = MarketService(cache)
    routes.init_router(service)
    tasks = collectors.start_collectors(service)
    logging.getLogger("market").info(
        "backend started (env=%s, data_dir=%s, has_cache=%s)",
        settings.app_env, settings.data_dir, cache.has_any_data(),
    )
    try:
        yield
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        # 退出前强制落盘，避免节流窗口内的最后一条行情丢失
        cache.save_disk(force=True)


def create_app() -> FastAPI:
    app = FastAPI(title="Market Quotes Backend", version="0.2.0", lifespan=lifespan)
    # 允许同机调试/局域网真机访问
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(routes.router)
    app.include_router(routes.root_router)
    return app


app = create_app()
