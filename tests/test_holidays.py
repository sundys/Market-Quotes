"""法定节假日休市判断测试（AGENTS.md 第 13 节补充）。"""
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from app.services.market import akshare_service  # noqa: E402
from app.services.market.holidays import is_cn_holiday, is_us_holiday  # noqa: E402
from app.services.market.market_service import us_market_open  # noqa: E402


def test_us_market_closed_on_us_holiday():
    # 2026-01-19 周一 MLK 日：交易时段内也应视为休市
    assert datetime(2026, 1, 19, 14, 0).date().isoformat() == "2026-01-19"
    assert us_market_open(datetime(2026, 1, 19, 14, 0)) is False


def test_us_market_open_on_normal_trading_monday():
    assert us_market_open(datetime(2026, 1, 26, 14, 0)) is True


def test_us_market_closed_outside_hours_and_weekend():
    assert us_market_open(datetime(2026, 1, 26, 8, 0)) is False
    assert us_market_open(datetime(2026, 1, 24, 14, 0)) is False  # 周六


def test_cn_holiday_table():
    assert is_cn_holiday(datetime(2026, 10, 1).date()) is True   # 国庆
    assert is_cn_holiday(datetime(2026, 2, 17).date()) is True   # 春节
    assert is_cn_holiday(datetime(2026, 3, 5).date()) is False


def test_sge_closed_on_cn_holiday():
    # 2026-10-01 周四 国庆：交易时段内也应视为休市
    assert akshare_service.current_sge_trade_session_open(
        datetime(2026, 10, 1, 10, 0)) is False
    # 正常交易日的开盘时段
    assert akshare_service.current_sge_trade_session_open(
        datetime(2026, 3, 5, 10, 0)) is True
