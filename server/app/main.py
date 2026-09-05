"""FastAPI 入口。

启动：
    uvicorn app.main:app --host 0.0.0.0 --port 8000
"""
from __future__ import annotations

import logging
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
    cache = CacheService(settings.data_dir)
    service = MarketService(cache)
    routes.init_router(service)
    tasks = collectors.start_collectors(service)
    logging.getLogger("market").info("backend started (env=%s, data_dir=%s)", settings.app_env, settings.data_dir)
    yield
    for task in tasks:
        task.cancel()


def create_app() -> FastAPI:
    app = FastAPI(title="Market Quotes Backend", version="0.1.0", lifespan=lifespan)
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
