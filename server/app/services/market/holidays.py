"""法定节假日表（AGENTS.md 第 13 节补充）。

内置 2025/2026 年休市日，用于让采集器在法定节假日（工作日）也按休市降频。
- CN：中国法定节假日落在工作日的日期（上金所/国内市场休市）
- US：美股全天休市日（NYSE 日历，东财指数与 COMEX 外盘适用）

数据每年由交易所公告更新；可在 server/config/holidays.json 放置
{"cn": ["2027-01-01", ...], "us": [...]} 覆盖/追加，无需改代码。
"""
from __future__ import annotations

import json
import logging
import os
from datetime import date

logger = logging.getLogger("market.holidays")

# ---- 中国：落在工作日的休市日（不含周末） ----
CN_HOLIDAYS = frozenset({
    # 2025
    "2025-01-01",
    "2025-01-28", "2025-01-29", "2025-01-30", "2025-01-31",
    "2025-02-03", "2025-02-04",
    "2025-04-04",
    "2025-05-01", "2025-05-02", "2025-05-05",
    "2025-06-02",
    "2025-10-01", "2025-10-02", "2025-10-03",
    "2025-10-06", "2025-10-07", "2025-10-08",
    # 2026
    "2026-01-01", "2026-01-02",
    "2026-02-16", "2026-02-17", "2026-02-18", "2026-02-19", "2026-02-20",
    "2026-04-06",
    "2026-05-01", "2026-05-04", "2026-05-05",
    "2026-06-19",
    "2026-09-25",
    "2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06", "2026-10-07",
})

# ---- 美股：全天休市日（NYSE 日历） ----
US_HOLIDAYS = frozenset({
    # 2025
    "2025-01-01", "2025-01-09", "2025-01-20", "2025-02-17",
    "2025-04-18", "2025-05-26", "2025-06-19", "2025-07-04",
    "2025-09-01", "2025-11-27", "2025-12-25",
    # 2026
    "2026-01-01", "2026-01-19", "2026-02-16",
    "2026-04-03", "2026-05-25", "2026-06-19", "2026-07-03",
    "2026-09-07", "2026-11-26", "2026-12-25",
})

# 可选的外部覆盖文件（每年交易所公告后更新即可，无需改代码）
_OVERRIDE_FILE = os.getenv(
    "HOLIDAYS_FILE", os.path.join("config", "holidays.json"))


def _load_override() -> None:
    global CN_HOLIDAYS, US_HOLIDAYS
    try:
        with open(_OVERRIDE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        cn = frozenset(data.get("cn", []))
        us = frozenset(data.get("us", []))
        if cn or us:
            CN_HOLIDAYS = CN_HOLIDAYS | cn
            US_HOLIDAYS = US_HOLIDAYS | us
            logger.info("holidays override loaded: cn=%d us=%d", len(cn), len(us))
    except FileNotFoundError:
        pass
    except Exception as exc:  # noqa: BLE001
        logger.warning("holidays override load failed: %s", exc)


_load_override()


def is_cn_holiday(d: date) -> bool:
    """中国法定节假日（工作日休市日）。"""
    return d.isoformat() in CN_HOLIDAYS


def is_us_holiday(d: date) -> bool:
    """美股全天休市日。"""
    return d.isoformat() in US_HOLIDAYS
