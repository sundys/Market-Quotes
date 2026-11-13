"""实时行情客户端解析测试：一次请求拿到全部字段（SGE / 新浪外盘）。

回归背景：
- SGE 以前每 30 秒打两次同一接口（akshare 一次 + 自己再取一次 OHLC），
  并且丢掉了响应里的真实行情时间（delaystr），把采集时刻当成行情时间。
- 新浪 COMEX 以前每次都要先抓 66KB 的 hf.html 映射页。
"""
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))

from app.services.market import sina_client, sge_client  # noqa: E402

SGE_PAYLOAD = {
    "times": ["09:00", "09:01", "15:30"],
    "min": "829",
    "max": "857",
    "data": ["851.33", "851.33", "837.5"],
    "heyue": "Au",
    "now": "17:33",
    "delaystr": "2026年11月13日 15:45:00",
}

SINA_LINE = (
    'var hq_str_hf_GC="3901.088,,3902.700,3902.900,3927.200,3879.100,17:36:26,'
    '3885.300,3883.300,0,2,1,2026-11-13,纽约黄金,0";'
)


# ---- SGE ----
def test_sge_single_request_yields_all_fields():
    snap = sge_client.parse_payload(SGE_PAYLOAD)
    assert snap["price"] == 837.5
    assert snap["open"] == 851.33
    assert snap["high"] == 857.0
    assert snap["low"] == 829.0
    assert snap["sparkline"] == [851.33, 851.33, 837.5]
    assert snap["point_count"] == 3


def test_sge_timestamp_comes_from_delaystr_not_fetch_time():
    snap = sge_client.parse_payload(SGE_PAYLOAD)
    assert snap["timestamp"] == datetime(2026, 11, 13, 15, 45)


def test_sge_parse_skips_zero_and_bad_values():
    payload = dict(SGE_PAYLOAD, data=["0", "", "800.5", None, "801"])
    snap = sge_client.parse_payload(payload)
    assert snap["price"] == 801.0
    assert snap["open"] == 800.5


def test_sge_parse_empty_raises():
    with pytest.raises(ValueError):
        sge_client.parse_payload({"data": []})
    with pytest.raises(ValueError):
        sge_client.parse_payload("not a dict")


def test_sge_delaystr_formats():
    expected = datetime(2026, 11, 13, 15, 45)
    assert sge_client.parse_delaystr("2026年11月13日 15:45:00") == expected
    assert sge_client.parse_delaystr("2026-11-13 15:45:00") == expected
    assert sge_client.parse_delaystr("") is None
    assert sge_client.parse_delaystr(None) is None


def test_sge_downsample_keeps_first_and_last():
    values = [float(i) for i in range(1000)]
    out = sge_client._downsample(values, 60)
    assert len(out) == 60
    assert out[0] == 0.0 and out[-1] == 999.0


# ---- 新浪外盘 ----
def test_sina_single_request_yields_all_fields():
    snap = sina_client.parse_payload(SINA_LINE)
    assert snap["price"] == 3901.088
    assert snap["high"] == 3927.2
    assert snap["low"] == 3879.1
    assert snap["prev_settlement"] == 3885.3
    assert snap["open"] == 3883.3
    assert snap["timestamp"] == datetime(2026, 11, 13, 17, 36, 26)
    assert snap["name"] == "纽约黄金"


def test_sina_parse_empty_raises():
    with pytest.raises(ValueError):
        sina_client.parse_payload('var hq_str_hf_GC="";')
    with pytest.raises(ValueError):
        sina_client.parse_payload("")


def test_sina_parse_bad_price_raises():
    bad = 'var hq_str_hf_GC="0,,,,,,,,,,,2026-11-13,x,0";'
    with pytest.raises(ValueError):
        sina_client.parse_payload(bad)
