"""多级缓存：一级内存、二级磁盘 JSON 快照（AGENTS.md 第 8 节）。

线程安全；磁盘快照在进程重启后恢复最近一次有效数据。
磁盘落盘做了最小间隔节流：三个采集器同相位成功时不会连续写盘。
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
import time
from collections import deque
from datetime import date
from typing import Deque, Dict, List, Optional, Tuple

logger = logging.getLogger("market.cache")


class CacheService:
    def __init__(self, data_dir: str, min_save_interval: float = 5.0) -> None:
        self._lock = threading.RLock()
        self._data_dir = data_dir
        self._quotes: Dict[str, dict] = {}
        # symbol -> {"close": float, "trade_date": str|None, "fetched_on": str|None}
        # fetched_on 记录“哪一天抓到的”，用于判断是否需要跨日刷新涨跌基准
        self._previous_close: Dict[str, dict] = {}
        # SGE 实时接口只给现价，日内走势靠采集器逐点累积（含时间标签，AGENTS.md 第 12/55 节）
        self._sge_samples: Deque[Tuple[float, str]] = deque(maxlen=80)
        self._snapshot_file = os.path.join(data_dir, "market_cache.json")
        self._min_save_interval = min_save_interval
        self._last_save = 0.0
        self.stats = {
            "cache_hits": 0,
            "cache_misses": 0,
            "em_last_success": None,
            "gc_last_success": None,
            "sge_last_success": None,
        }
        os.makedirs(data_dir, exist_ok=True)
        self._load_disk()

    # ---- 内存缓存 ----
    def set_quote(self, quote_id: str, payload: dict) -> None:
        with self._lock:
            self._quotes[quote_id] = payload

    def set_previous_close(self, symbol: str, close: Optional[float],
                           trade_date: Optional[str] = None,
                           fetched_on: Optional[date] = None) -> None:
        """持久化涨跌基准：必须记录抓取日，否则跨日无法判断是否需要刷新。"""
        with self._lock:
            self._previous_close[symbol] = {
                "close": close,
                "trade_date": str(trade_date) if trade_date is not None else None,
                "fetched_on": (fetched_on or date.today()).isoformat(),
            }

    def get_previous_close(self, symbol: str) -> Optional[float]:
        with self._lock:
            entry = self._previous_close.get(symbol)
            return entry.get("close") if isinstance(entry, dict) else entry

    def previous_close_fetched_on(self, symbol: str) -> Optional[str]:
        with self._lock:
            entry = self._previous_close.get(symbol)
            return entry.get("fetched_on") if isinstance(entry, dict) else None

    def get_quote(self, quote_id: str) -> Optional[dict]:
        with self._lock:
            payload = self._quotes.get(quote_id)
            if payload is None:
                self.stats["cache_misses"] += 1
                return None
            self.stats["cache_hits"] += 1
            return dict(payload)

    def append_sge_point(self, price: float, ts_label: str) -> None:
        """累积当日采样点；同一时间标签只保留最新价，避免收盘后出现重复点。"""
        with self._lock:
            point = (round(price, 2), ts_label)
            if self._sge_samples and self._sge_samples[-1][1] == ts_label:
                self._sge_samples[-1] = point
            else:
                self._sge_samples.append(point)
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
    def save_disk(self, force: bool = False) -> None:
        """写盘节流：非强制时最小间隔内直接跳过（内存数据仍然是最新的）。"""
        now = time.time()
        with self._lock:
            if not force and now - self._last_save < self._min_save_interval:
                return
            self._last_save = now
            snapshot = {
                "quotes": self._quotes,
                "previous_close": self._previous_close,
                "sge_samples": [list(s) for s in self._sge_samples],
                "saved_at": now,
            }
        try:
            fd, tmp_path = tempfile.mkstemp(dir=self._data_dir, suffix=".tmp")
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(snapshot, f, ensure_ascii=False)
            os.replace(tmp_path, self._snapshot_file)
        except OSError as exc:
            # 磁盘写入失败不应当影响内存缓存服务
            logger.warning("cache snapshot write failed: %s", exc)

    def _load_disk(self) -> None:
        try:
            with open(self._snapshot_file, "r", encoding="utf-8") as f:
                snapshot = json.load(f)
        except (OSError, ValueError):
            return
        self._quotes = snapshot.get("quotes", {}) or {}
        raw_prev = snapshot.get("previous_close", {}) or {}
        self._previous_close = {
            symbol: (value if isinstance(value, dict) else {"close": value})
            for symbol, value in raw_prev.items()
        }
        # 新格式 sge_samples（带时间标签）；兼容旧格式 sge_sparkline（仅价格）
        samples = snapshot.get("sge_samples") or snapshot.get("sge_sparkline") or []
        self._set_sge_samples(samples)
