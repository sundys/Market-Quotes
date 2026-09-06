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
from typing import Deque, Dict, List, Optional, Tuple


class CacheService:
    def __init__(self, data_dir: str) -> None:
        self._lock = threading.RLock()
        self._data_dir = data_dir
        self._quotes: Dict[str, dict] = {}
        self._previous_close: Dict[str, Optional[float]] = {}
        # SGE 实时接口只给现价，日内走势靠采集器逐点累积（含时间标签，AGENTS.md 第 12/55 节）
        self._sge_samples: Deque[Tuple[float, str]] = deque(maxlen=80)
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

    def append_sge_point(self, price: float, ts_label: str) -> None:
        with self._lock:
            self._sge_samples.append((round(price, 2), ts_label))
            self._quotes.setdefault("gold_cn", {})["sparkline"] = [p for p, _ in self._sge_samples]

    def get_sge_sparkline(self) -> List[float]:
        with self._lock:
            return [p for p, _ in self._sge_samples]

    def get_sge_samples(self) -> List[Tuple[float, str]]:
        with self._lock:
            return list(self._sge_samples)

    def _set_sge_samples(self, samples: List) -> None:
        with self._lock:
            self._sge_samples.clear()
            for item in samples:
                if isinstance(item, (list, tuple)) and len(item) == 2:
                    self._sge_samples.append((float(item[0]), str(item[1])))
                else:
                    # 旧格式：只有价格，无时间标签
                    self._sge_samples.append((float(item), ""))

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
                "sge_samples": [list(s) for s in self._sge_samples],
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
        # 新格式 sge_samples（带时间标签）；兼容旧格式 sge_sparkline（仅价格）
        samples = snapshot.get("sge_samples") or snapshot.get("sge_sparkline") or []
        self._set_sge_samples(samples)
