"""历史走势接口测试：缓存、stale 降级、日期标签对齐、SGE/GC 切片、参数校验。"""
import sys
import threading
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.api import routes  # noqa: E402
from app.services.market import em_service  # noqa: E402
from app.services.market.cache_service import CacheService  # noqa: E402
from app.services.market.history_service import HistoryService, _sanitize_pairs  # noqa: E402
from app.services.market.market_service import MarketService  # noqa: E402


@pytest.fixture
def client(tmp_path):
    service = MarketService(CacheService(str(tmp_path)))
    routes.init_router(service)
    app = FastAPI()
    app.include_router(routes.router)
    return TestClient(app), service


def test_sanitize_pairs_filters_and_downsamples():
    labels, points = _sanitize_pairs([("a", 1.0), ("b", float("nan")), ("c", -2.0), ("d", 3.5)])
    assert labels == ["a", "d"] and points == [1.0, 3.5]
    labels, points = _sanitize_pairs([(str(i), float(i)) for i in range(1000)])
    assert len(points) <= 400 and len(labels) == len(points)  # 两列始终对齐


def test_em_history_caches_and_serves_stale(monkeypatch):
    hs = HistoryService()
    calls = []

    def fake_kline(secid, klt, lmt):
        calls.append(1)
        return ["2026-09-01", "2026-09-02", "2026-09-03"], [100.0, 101.5, 99.0]

    monkeypatch.setattr(em_service, "fetch_kline", fake_kline)
    r1 = hs.index_history("nasdaq100", "100.NDX", "1m", threading.Lock())
    assert r1["points"] == [100.0, 101.5, 99.0]
    assert r1["labels"] == ["2026-09-01", "2026-09-02", "2026-09-03"]
    assert r1["is_stale"] is False
    hs.index_history("nasdaq100", "100.NDX", "1m", threading.Lock())
    assert len(calls) == 1  # 命中缓存

    # 缓存过期后数据源失败 → 返回最近缓存并标 stale
    def boom(secid, klt, lmt):
        raise RuntimeError("connection aborted")

    monkeypatch.setattr(em_service, "fetch_kline", boom)
    ts, labels, pts = hs._cache[("100.NDX:101", "1m")]
    hs._cache[("100.NDX:101", "1m")] = (ts - 100000, labels, pts)
    r2 = hs.index_history("nasdaq100", "100.NDX", "1m", threading.Lock())
    assert r2["points"] == [100.0, 101.5, 99.0]
    assert r2["labels"] == ["2026-09-01", "2026-09-02", "2026-09-03"]
    assert r2["is_stale"] is True


def test_gc_history_slices_daily_with_labels(monkeypatch):
    from app.services.market import akshare_service

    hs = HistoryService()
    labels = [f"2026-{1 + i // 28:02d}-{1 + i % 28:02d}" for i in range(200)]
    closes = [float(i + 1) for i in range(200)]
    monkeypatch.setattr(akshare_service, "fetch_gc_daily_closes",
                        lambda: (labels, closes))

    r_week = hs.gc_history("1w", threading.Lock())
    assert r_week["points"] == closes[-5:]
    assert r_week["labels"] == labels[-5:]
    assert len(hs.gc_history("1m", threading.Lock())["points"]) == 22


def test_gc_intraday_uses_em_kline(monkeypatch):
    hs = HistoryService()
    monkeypatch.setattr(em_service, "fetch_kline",
                        lambda secid, klt, lmt: (["09-01 10:00", "09-01 10:05"], [4475.9, 4478.3]))
    r = hs.gc_history("1d", threading.Lock())
    assert r["points"] == [4475.9, 4478.3]
    assert r["labels"] == ["09-01 10:00", "09-01 10:05"]
    assert r["id"] == "gold_global"


def test_sge_history_slices_daily_with_labels(monkeypatch):
    from app.services.market import akshare_service

    hs = HistoryService()
    labels = [f"d{i}" for i in range(200)]
    closes = [float(i + 1) for i in range(200)]
    monkeypatch.setattr(akshare_service, "fetch_sge_daily_closes",
                        lambda: (labels, closes))

    r_week = hs.sge_history("1w", [], threading.Lock())
    assert r_week["points"] == closes[-5:]
    assert r_week["labels"] == labels[-5:]


def test_sge_intraday_uses_accumulated_samples():
    hs = HistoryService()
    samples = [(958.0, "09-05 10:00"), (959.2, "09-05 10:05")]
    r = hs.sge_history("1d", samples, threading.Lock())
    assert r["points"] == [958.0, 959.2]
    assert r["labels"] == ["09-05 10:00", "09-05 10:05"]


def test_history_route_validates_period(client):
    http, _ = client
    assert http.get("/api/market/nasdaq100/history", params={"period": "2y"}).status_code == 400
    resp = http.get("/api/market/nasdaq100/history", params={"period": "1m"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == "nasdaq100" and "points" in body and "labels" in body
