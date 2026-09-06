"""东方财富行情服务（替代 Yahoo Finance，AGENTS.md 第 4 节调整）。

注意：akshare 官方的 index_global_spot_em / index_global_hist_em 不带
Referer 头，部分网络出口会被 push2.eastmoney.com 直接断连；这里带
User-Agent + Referer 请求相同的公开接口，只取本项目需要的标的。
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Dict, List, Tuple

import requests

logger = logging.getLogger("market.em")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://quote.eastmoney.com/",
}

LIST_URL = "https://push2.eastmoney.com/api/qt/clist/get"
KLINE_URL = "https://push2his.eastmoney.com/api/qt/stock/kline/get"

# 东财存在多个编号镜像节点，单节点会间歇性断连；失败自动轮换 host 重试
_LIST_HOSTS = [
    "push2.eastmoney.com",
    "23.push2.eastmoney.com",
    "64.push2.eastmoney.com",
    "push2delay.eastmoney.com",
]
_KLINE_HOSTS = [
    "push2his.eastmoney.com",
    "23.push2his.eastmoney.com",
    "64.push2his.eastmoney.com",
]

INDEX_SECIDS = {"nasdaq100": "100.NDX", "sp500": "100.SPX", "dowjones": "100.DJIA"}
GOLD_SECID = "101.GC00Y"  # COMEX 黄金主力连续


class EastmoneyError(Exception):
    """东财接口失败（连接断开/数据缺失）。"""


def _get_hosts(path: str, params: dict, hosts: List[str], timeout: int = 6) -> dict:
    """依次尝试多个东财节点，任一成功即返回；全部失败抛 EastmoneyError。"""
    last: Optional[Exception] = None
    for host in hosts:
        try:
            r = requests.get(f"https://{host}{path}", params=params, headers=HEADERS,
                             timeout=timeout)
            r.raise_for_status()
            return r.json()
        except Exception as exc:  # noqa: BLE001
            last = exc
            continue
    raise EastmoneyError(str(last))


def fetch_global_indices() -> Dict[str, dict]:
    """一次请求三大美股指数实时行情。

    返回 {quote_id: {name, price, prev_close, timestamp(datetime)}}。
    东财返回价格为实际值 x100（fltt=1），此处统一换算。
    """
    params = {
        "np": "2", "fltt": "1", "invt": "2",
        "fs": ",".join(f"i:{secid}" for secid in INDEX_SECIDS.values()),
        "fields": "f12,f14,f2,f3,f4,f18,f124",
        "fid": "f3", "pn": "1", "pz": "10", "po": "1", "dect": "1",
        "wbp2u": "|0|0|0|web",
    }
    data = _get_hosts("/api/qt/clist/get", params, _LIST_HOSTS).get("data") or {}
    diff = (data.get("diff") or {})
    by_code = {v.get("f12"): v for v in diff.values()} if isinstance(diff, dict) else {}
    result: Dict[str, dict] = {}
    for quote_id, secid in INDEX_SECIDS.items():
        code = secid.split(".", 1)[1]
        row = by_code.get(code)
        if not row or row.get("f2") in ("-", None):
            continue
        ts_raw = row.get("f124")
        result[quote_id] = {
            "name": row.get("f14"),
            "price": float(row["f2"]) / 100.0,
            "prev_close": float(row["f18"]) / 100.0,
            "timestamp": datetime.fromtimestamp(int(ts_raw)),
        }
    if not result:
        raise EastmoneyError("global indices returned empty")
    return result


def fetch_kline(secid: str, klt: int, lmt: int) -> Tuple[List[str], List[float]]:
    """东财 K 线（时间升序），返回 (日期标签, 收盘价) 两列。klt: 5/30=分钟, 101=日线。"""
    params = {
        "secid": secid, "klt": str(klt), "fqt": "0",
        "lmt": str(lmt), "end": "20500101",
        "fields1": "f1,f2,f3", "fields2": "f51,f53",
    }
    data = _get_hosts("/api/qt/stock/kline/get", params, _KLINE_HOSTS).get("data") or {}
    klines = data.get("klines") or []
    labels: List[str] = []
    closes: List[float] = []
    for x in klines:
        parts = x.split(",")
        label = parts[0][:16].strip()  # "2026-09-05 14:30" 或 "2026-09-05"
        close = float(parts[1])
        labels.append(label)
        closes.append(close)
    if not closes:
        raise EastmoneyError(f"empty klines for {secid} klt={klt}")
    return labels, closes
