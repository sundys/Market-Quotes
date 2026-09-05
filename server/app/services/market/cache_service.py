"""多级缓存：一级内存、二级磁盘 JSON 快照（AGENTS.md 第 8 节）。

线程安全；磁盘快照在进程重启后恢复最近一次有效数据。
"""
from __future__ import annotations

import json
import os
import tempfile
import threading
import time
from collections import deque
from typing import Deque, Dict, List, Optional


class CacheService:
    def __init__(self, data_dir: str) -> None:
        self._lock = threading.RLock()
        self._data_dir = data_dir
        self._quotes: Dict[str, dict] = {}
        self._previous_close: Dict[str, Optional[float]] = {}
        # SGE 实时接口只给现价，日内走势靠采集器逐点累积（AGENTS.md 第 12/55 节）
        self._sge_sparkline: Deque[float] = deque(maxlen=80)
        self._snapshot_file = os.path.join(data_dir, "market_cache.json")
        self.stats = {
            "cache_hits": 0,
            "cache_misses": 0,
            "yfinance_last_success": None,
            "sge_last_success": None,
        }
        os.makedirs(data_dir, exist_ok=True)
        self._load_disk()

    # ---- 内存缓存 ----
    def set_quote(self, quote_id: str, payload: dict) -> None:
        with self._lock:
            self._quotes[quote_id] = payload

    def set_previous_close(self, symbol: str, prev_close: Optional[float]) -> None:
        with self._lock:
            self._previous_close[symbol] = prev_close

    def get_previous_close(self, symbol: str) -> Optional[float]:
        with self._lock:
            return self._previous_close.get(symbol)

    def get_quote(self, quote_id: str) -> Optional[dict]:
        with self._lock:
            payload = self._quotes.get(quote_id)
            if payload is None:
                self.stats["cache_misses"] += 1
                return None
            self.stats["cache_hits"] += 1
            return dict(payload)

    def append_sge_point(self, price: float) -> None:
        with self._lock:
            self._sge_sparkline.append(round(price, 2))
            self._quotes.setdefault("gold_cn", {})["sparkline"] = list(self._sge_sparkline)

    def set_sge_sparkline(self, points: List[float]) -> None:
        with self._lock:
            self._sge_sparkline.clear()
            self._sge_sparkline.extend(points[-80:])
            if "gold_cn" in self._quotes:
                self._quotes["gold_cn"]["sparkline"] = list(self._sge_sparkline)

    def mark_success(self, source: str) -> None:
        with self._lock:
            self.stats[f"{source}_last_success"] = time.time()

    def has_any_data(self) -> bool:
        with self._lock:
            return bool(self._quotes)

    # ---- 二级磁盘缓存 ----
    def save_disk(self) -> None:
        with self._lock:
            snapshot = {
                "quotes": self._quotes,
                "previous_close": self._previous_close,
                "sge_sparkline": list(self._sge_sparkline),
                "saved_at": time.time(),
            }
        try:
            fd, tmp_path = tempfile.mkstemp(dir=self._data_dir, suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, ensure_ascii=False)
            os.replace(tmp_path, self._snapshot_file)
        except OSError:
            # 磁盘写入失败不应当影响内存缓存服务
            pass

    def _load_disk(self) -> None:
        try:
            with open(self._snapshot_file, "r", encoding="utf-8") as f:
                snapshot = json.load(f)
        except (OSError, ValueError):
            return
        self._quotes = snapshot.get("quotes", {})
        self._previous_close = snapshot.get("previous_close", {})
        self.set_sge_sparkline(snapshot.get("sge_sparkline", []))
