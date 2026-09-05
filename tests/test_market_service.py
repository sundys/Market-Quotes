"""MarketService 单元测试：涨跌幅计算、stale 标记、数据源隔离（AGENTS.md 第 9/11/12/20 节）。"""
from datetime import datetime

from app.models.quote import MarketQuote, compute_change
from app.services.market.cache_service import CacheService
from app.services.market.market_service import MarketService


def make_service(tmp_path):
    return MarketService(CacheService(str(tmp_path)))


def index_snap(price, prev):
    return {"name": "x", "price": price, "prev_close": prev,
            "timestamp": datetime(2026, 9, 5, 12, 0)}


def test_compute_change_basic():
    change, pct = compute_change(105.0, 100.0)
    assert change == 5.0
    assert abs(pct - 5.0) < 1e-9


def test_compute_change_no_prev_close():
    change, pct = compute_change(105.0, None)
    assert change is None and pct is None


def test_quote_rejects_bad_price():
    q = MarketQuote(id="x", name="x", symbol="x", price=-1, timestamp="t", source="")
    assert not q.is_valid()
    q2 = MarketQuote(id="x", name="x", symbol="x", price=float("nan"), timestamp="t", source="")
    assert not q2.is_valid()


def test_index_snapshot_applied(tmp_path):
    svc = make_service(tmp_path)
    svc.apply_index_quotes({"nasdaq100": index_snap(23000.0, 22900.0)})
    item = svc.cache.get_quote("nasdaq100")
    assert item["price"] == 23000.0
    assert item["change"] == 100.0
    assert abs(item["change_percent"] - (100 / 22900 * 100)) < 1e-9
    assert item["source"] == "AKShare/东财"
    assert item["is_stale"] is False


def test_index_failure_marks_stale_but_keeps_data(tmp_path):
    svc = make_service(tmp_path)
    svc.apply_index_quotes({"nasdaq100": index_snap(23000.0, 22900.0)})
    svc.mark_em_stale("connection aborted")
    item = svc.cache.get_quote("nasdaq100")
    assert item["is_stale"] is True
    assert item["price"] == 23000.0  # 保留最后一次有效数据


def test_gold_quote_labeled_as_futures(tmp_path):
    """COMEX 期金作为国际黄金数据源时，名称/来源必须明确标注期货（AGENTS.md 第 4.1 节）。"""
    svc = make_service(tmp_path)
    svc.apply_gold_quote({"name": "COMEX黄金", "price": 4477.2,
                          "prev_settlement": 4520.3, "timestamp": datetime(2026, 9, 5, 12, 0)})
    item = svc.cache.get_quote("gold_global")
    assert item["name"] == "国际黄金期货"
    assert "期金" in item["source"]
    assert abs(item["change"] - (-43.1)) < 1e-9
    assert item["currency"] == "USD"


def test_sge_change_uses_previous_close(tmp_path):
    svc = make_service(tmp_path)
    svc.cache.set_previous_close("Au99.99", 752.70)
    svc.apply_sge(price=755.0, ts=datetime(2026, 9, 5, 12, 0))
    item = svc.cache.get_quote("gold_cn")
    assert item["currency"] == "CNY"
    assert item["unit"] == "g"
    assert abs(item["change"] - 2.30) < 1e-9
    assert abs(item["change_percent"] - (2.30 / 752.70 * 100)) < 1e-9
    assert "sparkline" in item and len(item["sparkline"]) == 1


def test_sources_are_isolated(tmp_path):
    """任一数据源失败不影响其它行情（AGENTS.md 第 20 节）。"""
    svc = make_service(tmp_path)
    svc.apply_index_quotes({"nasdaq100": index_snap(23000.0, 22900.0)})
    svc.apply_gold_quote({"price": 4477.2, "prev_settlement": 4520.3,
                          "timestamp": datetime(2026, 9, 5, 12, 0)})
    svc.cache.set_previous_close("Au99.99", 752.70)
    svc.apply_sge(price=755.0, ts=datetime(2026, 9, 5, 12, 0))

    svc.mark_em_stale("connection error")
    overview = svc.overview()
    by_id = {i["id"]: i for i in overview["items"]}
    assert by_id["nasdaq100"]["is_stale"] is True
    assert by_id["gold_global"]["is_stale"] is False
    assert by_id["gold_cn"]["is_stale"] is False


def test_overview_empty_returns_empty_items(tmp_path):
    svc = make_service(tmp_path)
    overview = svc.overview()
    assert overview["items"] == []
    assert overview["server_time"] is not None
