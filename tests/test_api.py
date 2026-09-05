"""API 层测试：不触发 lifespan（不启动真实采集器），只验证路由读取缓存行为。"""
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api import routes  # noqa: E402
from app.services.market.cache_service import CacheService  # noqa: E402
from app.services.market.market_service import MarketService  # noqa: E402


@pytest.fixture
def client(tmp_path):
    service = MarketService(CacheService(str(tmp_path)))
    routes.init_router(service)
    app = FastAPI()
    app.include_router(routes.router)
    app.include_router(routes.root_router)
    # 不使用 with 语法，避免触发 lifespan 启动真实采集器
    return TestClient(app, raise_server_exceptions=True), service


def test_overview_returns_cached_quotes(client):
    http, service = client
    service.apply_index_quotes({"sp500": {"name": "标普500", "price": 6487.32,
                                          "prev_close": 6499.77,
                                          "timestamp": datetime(2026, 9, 5, 12, 30)}})
    resp = http.get("/api/market/overview")
    assert resp.status_code == 200
    data = resp.json()
    assert data["items"][0]["id"] == "sp500"
    assert data["items"][0]["price"] == 6487.32
    assert data["updated_at"] is not None


def test_overview_without_data(client):
    http, _ = client
    resp = http.get("/api/market/overview")
    assert resp.status_code == 200
    assert resp.json()["items"] == []


def test_health_endpoint(client):
    http, service = client
    service.mark_em_stale("simulated failure for testing")
    resp = http.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["eastmoney"]["failed_requests"] >= 1
