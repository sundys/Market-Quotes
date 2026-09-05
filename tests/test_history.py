"""历史走势接口测试：缓存、stale 降级、SGE 切片、参数校验。"""
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api import routes  # noqa: E402
from app.services.market import history_service as hs_module  # noqa: E402
from app.services.market import yfinance_service  # noqa: E402
from app.services.market.history_service import HistoryService, _sanitize  # noqa: E402
from app.services.market.cache_service import CacheService  # noqa: E402
from app.services.market.market_service import MarketService  # noqa: E402


@pytest.fixture
def client(tmp_path):
    service = MarketService(CacheService(str(tmp_path)))
    routes.init_router(service)
    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app), service


def test_sanitize_filters_and_downsamples():
    assert _sanitize([1.0, float("nan"), -2.0, 0, 3.5]) == [1.0, 3.5]
    pts = _sanitize([float(i) for i in range(1000)])
    assert len(pts) <= 400


def test_yf_history_caches_and_serves_stale(tmp_path, monkeypatch):
    hs = HistoryService()
    calls = []

    def fake_fetch(symbol, period, interval):
        calls.append(1)
        return [100.0, 101.5, 99.0]

    monkeypatch.setattr(yfinance_service, "fetch_history", fake_fetch)
    r1 = hs.yf_history("^NDX", "1m", threading.Lock(), "nasdaq100")
    assert r1["points"] == [100.0, 101.5, 99.0]
    assert r1["is_stale"] is False
    hs.yf_history("^NDX", "1m", threading.Lock(), "nasdaq100")
    assert len(calls) == 1  # 命中缓存

    # 缓存过期后数据源失败 → 返回最近缓存并标 stale
    def boom(symbol, period, interval):
        raise RuntimeError("429")

    monkeypatch.setattr(yfinance_service, "fetch_history", boom)
    ts, pts = hs._cache[("^NDX", "1m")]
    hs._cache[("^NDX", "1m")] = (ts - 10000, pts)  # 人为使缓存过期
    r2 = hs.yf_history("^NDX", "1m", threading.Lock(), "nasdaq100")
    assert r2["points"] == [100.0, 101.5, 99.0]
    assert r2["is_stale"] is True


def test_sge_history_slices_by_period(monkeypatch):
    hs = HistoryService()
    closes = [float(i + 1) for i in range(200)]
    monkeypatch.setattr(hs_module.akshare_service, "fetch_sge_daily_closes", lambda: closes)

    r_week = hs.sge_history("1w", [], threading.Lock())
    assert r_week["points"] == closes[-5:]
    r_month = hs.sge_history("1m", [], threading.Lock())
    assert len(r_month["points"]) == 22
    # 二次调用命中当日缓存，不再触发数据源
    monkeypatch.setattr(hs_module.akshare_service, "fetch_sge_daily_closes",
                        lambda: (_ for _ in ()).throw(RuntimeError()))
    assert hs.sge_history("6m", [], threading.Lock())["points"] == closes[-130:]


def test_sge_intraday_uses_accumulated_points():
    hs = HistoryService()
    r = hs.sge_history("1d", [958.0, 959.2], threading.Lock())
    assert r["points"] == [958.0, 959.2]


def test_history_route_validates_period(client):
    http, _ = client
    assert http.get("/api/market/nasdaq100/history", params={"period": "2y"}).status_code == 400
    resp = http.get("/api/market/nasdaq100/history", params={"period": "1m"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "nasdaq100" and "points" in body


def test_history_route_gold_uses_active_symbol(client):
    """黄金详情接口以缓存中实际使用的 symbol 为准（现货缺失时为期货）。"""
    from datetime import datetime

    http, service = client
    from app.services.market.yfinance_service import SymbolSnapshot

    snap = SymbolSnapshot(price=3520.0, previous_close=3495.0,
                          timestamp=datetime(2026, 9, 5, 12, 0), sparkline=[])
    service.apply_yfinance_snapshot("GC=F", snap)
    seen = {}

    def fake_fetch(symbol, period, interval):
        seen["symbol"] = symbol
        return [1.0, 2.0]

    import app.services.market.yfinance_service as yf_mod
    original = yf_mod.fetch_history
    yf_mod.fetch_history = fake_fetch
    try:
        resp = http.get("/api/market/gold_global/history", params={"period": "1m"})
    finally:
        yf_mod.fetch_history = original
    assert resp.status_code == 200
    assert seen["symbol"] == "GC=F"
