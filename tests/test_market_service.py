"""MarketService 单元测试：涨跌幅计算、stale 标记、数据源隔离（AGENTS.md 第 9/11/12/20 节）。"""
from datetime import datetime

from app.models.quote import MarketQuote, compute_change
from app.services.market.cache_service import CacheService
from app.services.market.market_service import MarketService
from app.services.market.yfinance_service import SymbolSnapshot


def make_service(tmp_path):
    return MarketService(CacheService(str(tmp_path)))


def test_compute_change_basic():
    change, pct = compute_change(105.0, 100.0)
    assert change == 5.0
    assert abs(pct - 5.0) < 1e-9


def test_compute_change_no_prev_close():
    change, pct = compute_change(105.0, None)
    assert change is None and pct is None


def test_quote_rejects_bad_price():
    q = MarketQuote(id="x", name="x", symbol="x", price=-1, timestamp="t")
    assert not q.is_valid()
    q2 = MarketQuote(id="x", name="x", symbol="x", price=float("nan"), timestamp="t")
    assert not q2.is_valid()


def test_yfinance_snapshot_applied(tmp_path):
    svc = make_service(tmp_path)
    snap = SymbolSnapshot(price=3500.0, previous_close=3480.0,
                          timestamp=datetime(2026, 9, 5, 12, 0), sparkline=[1, 2, 3])
    svc.apply_yfinance_snapshot("XAUUSD=X", snap)
    item = svc.cache.get_quote("gold_global")
    assert item["price"] == 3500.0
    assert item["change"] == 20.0
    assert abs(item["change_percent"] - 0.5747126436781609) < 1e-9
    assert item["is_stale"] is False


def test_yfinance_failure_marks_stale_but_keeps_data(tmp_path):
    svc = make_service(tmp_path)
    snap = SymbolSnapshot(price=3500.0, previous_close=3480.0,
                          timestamp=datetime(2026, 9, 5, 12, 0), sparkline=[])
    svc.apply_yfinance_snapshot("XAUUSD=X", snap)
    svc.mark_yfinance_stale("429 too many requests")
    item = svc.cache.get_quote("gold_global")
    assert item["is_stale"] is True
    assert item["price"] == 3500.0  # 保留最后一次有效数据


def test_sge_change_uses_previous_close(tmp_path):
    svc = make_service(tmp_path)
    svc.apply_sge(price=755.0, ts=datetime(2026, 9, 5, 12, 0),
                  prev_close=752.70, prev_date=datetime(2026, 9, 4).date())
    item = svc.cache.get_quote("gold_cn")
    assert item["currency"] == "CNY"
    assert item["unit"] == "g"
    assert abs(item["change"] - 2.30) < 1e-9
    assert abs(item["change_percent"] - (2.30 / 752.70 * 100)) < 1e-9
    assert "sparkline" in item and len(item["sparkline"]) == 1


def test_sge_source_isolated_from_yfinance(tmp_path):
    """yfinance 挂了不影响 SGE 正常返回（AGENTS.md 第 20 节）。"""
    svc = make_service(tmp_path)
    snap = SymbolSnapshot(price=23000.0, previous_close=22900.0,
                          timestamp=datetime(2026, 9, 5, 12, 0), sparkline=[])
    svc.apply_yfinance_snapshot("^NDX", snap)
    svc.apply_sge(price=755.0, ts=datetime(2026, 9, 5, 12, 0),
                  prev_close=752.7, prev_date=datetime(2026, 9, 4).date())
    svc.mark_yfinance_stale("timeout")
    overview = svc.overview()
    by_id = {i["id"]: i for i in overview["items"]}
    assert by_id["nasdaq100"]["is_stale"] is True
    assert by_id["gold_cn"]["is_stale"] is False


def test_gold_falls_back_to_futures_when_spot_missing(tmp_path):
    """XAUUSD=X 无数据时回退 GC=F，且必须明确标注期货（AGENTS.md 第 4.1 节）。"""
    svc = make_service(tmp_path)
    spot_snap = SymbolSnapshot(price=3500.0, previous_close=3480.0,
                               timestamp=datetime(2026, 9, 5, 12, 0), sparkline=[])
    fut_snap = SymbolSnapshot(price=3520.0, previous_close=3495.0,
                              timestamp=datetime(2026, 9, 5, 12, 0), sparkline=[])
    # 现货优先
    svc.apply_yfinance_snapshots({"XAUUSD=X": spot_snap, "GC=F": fut_snap})
    item = svc.cache.get_quote("gold_global")
    assert item["name"] == "国际黄金"
    assert item["symbol"] == "XAUUSD=X"
    assert item["price"] == 3500.0
    # 现货缺失 → 期货，且名称/来源明确标注
    svc2 = make_service(tmp_path)
    svc2.apply_yfinance_snapshots({"GC=F": fut_snap})
    item2 = svc2.cache.get_quote("gold_global")
    assert item2["name"] == "国际黄金期货"
    assert item2["symbol"] == "GC=F"
    assert "期货" in item2["source"]
    assert item2["price"] == 3520.0


def test_overview_empty_returns_empty_items(tmp_path):
    svc = make_service(tmp_path)
    overview = svc.overview()
    assert overview["items"] == []
    assert overview["server_time"] is not None
