"""MarketService 单元测试：涨跌幅计算、stale 标记、数据源隔离（AGENTS.md 第 9/11/12/20 节）。"""
from datetime import datetime, timedelta

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
    svc.set_gc_monthly([4400.0, 4450.0, 4477.2])  # 月线就绪时作为卡片行情线
    svc.apply_gold_quote({"name": "COMEX黄金", "price": 4477.2,
                          "prev_settlement": 4520.3, "timestamp": datetime(2026, 9, 5, 12, 0)})
    item = svc.cache.get_quote("gold_global")
    assert item["name"] == "国际黄金期货"
    assert "期金" in item["source"]
    assert abs(item["change"] - (-43.1)) < 1e-9
    assert item["currency"] == "USD"
    assert item["sparkline"] == [4400.0, 4450.0, 4477.2]


def test_sge_change_uses_previous_close(tmp_path):
    svc = make_service(tmp_path)
    svc.cache.set_previous_close("Au99.99", 752.70)
    svc.set_sge_monthly([740.0, 745.0, 750.0, 755.0])  # 月线就绪时优先于当日采样
    svc.apply_sge({"price": 755.0, "timestamp": datetime(2026, 9, 5, 12, 0),
                   "open": 753.0, "high": 756.0, "low": 751.0})
    item = svc.cache.get_quote("gold_cn")
    assert item["currency"] == "CNY"
    assert item["unit"] == "g"
    assert abs(item["change"] - 2.30) < 1e-9
    assert abs(item["change_percent"] - (2.30 / 752.70 * 100)) < 1e-9
    assert "sparkline" in item and item["sparkline"] == [740.0, 745.0, 750.0, 755.0]
    assert item["open"] == 753.0 and item["high"] == 756.0 and item["low"] == 751.0
    assert item["prev_close"] == 752.70


def test_sources_are_isolated(tmp_path):
    """任一数据源失败不影响其它行情（AGENTS.md 第 20 节）。"""
    svc = make_service(tmp_path)
    now = datetime.now()
    svc.apply_index_quotes({"nasdaq100": {"name": "x", "price": 23000.0,
                                          "prev_close": 22900.0, "timestamp": now}})
    svc.apply_gold_quote({"price": 4477.2, "prev_settlement": 4520.3, "timestamp": now})
    svc.cache.set_previous_close("Au99.99", 752.70)
    svc.set_sge_monthly([740.0, 745.0, 750.0, 755.0])  # 月线就绪时优先于当日采样
    svc.apply_sge({"price": 755.0, "timestamp": now,
                   "open": 753.0, "high": 756.0, "low": 751.0})

    svc.mark_em_stale("connection error")
    overview = svc.overview()
    by_id = {i["id"]: i for i in overview["items"]}
    assert by_id["nasdaq100"]["is_stale"] is True
    assert by_id["gold_global"]["is_stale"] is False
    assert by_id["gold_cn"]["is_stale"] is False


def test_overview_marks_stale_when_market_open_but_quote_old(tmp_path, monkeypatch):
    """交易中却长时间没有新数据 → 必须标 stale，不能继续冒充实时（AGENTS.md 第 9/39 节）。"""
    from app.services.market import market_service as ms

    monkeypatch.setattr(ms, "comex_open", lambda now=None: True)
    svc = make_service(tmp_path)
    svc.apply_gold_quote({"price": 4477.2, "prev_settlement": 4520.3,
                          "timestamp": datetime.now() - timedelta(hours=2)})

    item = {i["id"]: i for i in svc.overview()["items"]}["gold_global"]
    assert item["is_stale"] is True


def test_overview_keeps_fresh_quote_not_stale(tmp_path, monkeypatch):
    from app.services.market import market_service as ms

    monkeypatch.setattr(ms, "comex_open", lambda now=None: True)
    svc = make_service(tmp_path)
    svc.apply_gold_quote({"price": 4477.2, "prev_settlement": 4520.3,
                          "timestamp": datetime.now()})

    item = {i["id"]: i for i in svc.overview()["items"]}["gold_global"]
    assert item["is_stale"] is False


def test_partial_index_batch_marks_missing_stale(tmp_path):
    """部分成功：本轮没返回的标的必须标 stale，否则旧价继续冒充实时。"""
    svc = make_service(tmp_path)
    now = datetime.now()
    svc.apply_index_quotes({"sp500": {"name": "x", "price": 6487.32,
                                      "prev_close": 6499.77, "timestamp": now}})
    svc.apply_index_quotes({"nasdaq100": {"name": "x", "price": 23000.0,
                                          "prev_close": 22900.0, "timestamp": now}})

    assert svc.cache.get_quote("sp500")["is_stale"] is True
    assert svc.cache.get_quote("nasdaq100")["is_stale"] is False


def test_overview_reports_quote_count(tmp_path):
    svc = make_service(tmp_path)
    svc.apply_gold_quote({"price": 4477.2, "prev_settlement": 4520.3,
                          "timestamp": datetime.now()})
    assert svc.overview()["count"] == 1


def test_overview_uses_registry_order(tmp_path):
    svc = make_service(tmp_path)
    now = datetime.now()
    svc.apply_sge({"price": 755.0, "timestamp": now, "open": 753.0,
                   "high": 756.0, "low": 751.0})
    svc.apply_gold_quote({"price": 4477.2, "prev_settlement": 4520.3, "timestamp": now})
    ids = [i["id"] for i in svc.overview()["items"]]
    assert ids == ["gold_global", "gold_cn"]


def test_refresh_sparkline_backfills_cached_quote(tmp_path):
    """月线是低频任务，就绪后要立刻补到已缓存行情上，不必等下一轮采集。"""
    svc = make_service(tmp_path)
    svc.apply_gold_quote({"price": 4477.2, "prev_settlement": 4520.3,
                          "timestamp": datetime.now()})
    assert svc.cache.get_quote("gold_global")["sparkline"] == []

    svc.set_gc_monthly([1.0, 2.0, 3.0])
    svc.refresh_sparkline("gold_global")
    assert svc.cache.get_quote("gold_global")["sparkline"] == [1.0, 2.0, 3.0]


def test_gold_batch_applies_futures_and_spot(tmp_path):
    """一次请求同时应用期金与现货；两者涨跌各自按昨结算计算。"""
    svc = make_service(tmp_path)
    now = datetime.now()
    svc.apply_gold_quotes({
        "GC": {"price": 3893.3, "prev_settlement": 3885.3, "timestamp": now,
               "open": 3883.3, "high": 3927.2, "low": 3879.1},
        "XAU": {"price": 3890.1, "prev_settlement": 3877.4, "timestamp": now,
                "open": 3877.2, "high": 3923.0, "low": 3874.9},
    })

    gc = svc.cache.get_quote("gold_global")
    spot = svc.cache.get_quote("gold_spot")
    assert gc["name"] == "国际黄金期货" and "期金" in gc["source"]
    assert spot["name"] == "伦敦金现货" and "现货" in spot["source"]
    assert abs(spot["change"] - (3890.1 - 3877.4)) < 1e-9
    assert spot["currency"] == "USD" and spot["unit"] == "oz"


def test_gold_batch_marks_missing_symbol_stale(tmp_path):
    svc = make_service(tmp_path)
    now = datetime.now()
    svc.apply_gold_quotes({
        "GC": {"price": 3893.3, "prev_settlement": 3885.3, "timestamp": now},
        "XAU": {"price": 3890.1, "prev_settlement": 3877.4, "timestamp": now},
    })
    # 本轮只回了 GC，现货必须标 stale
    svc.apply_gold_quotes({"GC": {"price": 3894.0, "prev_settlement": 3885.3,
                                  "timestamp": now}})
    assert svc.cache.get_quote("gold_spot")["is_stale"] is True
    assert svc.cache.get_quote("gold_global")["is_stale"] is False


def test_spot_uses_own_monthly_sparkline(tmp_path):
    svc = make_service(tmp_path)
    svc.set_monthly("gold_spot", [1.0, 2.0, 3.0])
    svc.set_monthly("gold_global", [9.0, 8.0])
    svc.apply_gold_quotes({
        "GC": {"price": 3893.3, "prev_settlement": 3885.3, "timestamp": datetime.now()},
        "XAU": {"price": 3890.1, "prev_settlement": 3877.4, "timestamp": datetime.now()},
    })
    assert svc.cache.get_quote("gold_spot")["sparkline"] == [1.0, 2.0, 3.0]
    assert svc.cache.get_quote("gold_global")["sparkline"] == [9.0, 8.0]


def test_overview_empty_returns_empty_items(tmp_path):
    svc = make_service(tmp_path)
    overview = svc.overview()
    assert overview["items"] == []
    assert overview["server_time"] is not None
