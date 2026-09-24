# -*- coding: utf-8 -*-
"""公会进步奖档位查表（金额与 202512/202608 共用表一致）。

增长列按左闭右开区间匹配：
[500,1000)→500列，[1000,2000)→1000列，…，>=100000→100000列。
增长 < 500 → $0。

表中 `/`（代码里记 0）按位置读：
- 行首（该行左边还没有数字）：还没开始发奖 → $0
- 行尾（该行已经有过奖励之后）：封顶为该行最高有奖金额（如 1000 以下最高 $130）
"""
from __future__ import annotations

import math

GROWTH_BOUNDS = [
    (500, 1000),
    (1000, 2000),
    (2000, 3000),
    (3000, 5000),
    (5000, 10000),
    (10000, 20000),
    (20000, 30000),
    (30000, 40000),
    (40000, 60000),
    (60000, 80000),
    (80000, 100000),
    (100000, math.inf),
]

# 纵轴：[min, max) ；最后一档 200000+ 的 max 为 inf
BRACKET_BOUNDS = [
    (0, 1000),
    (1000, 5000),
    (5000, 10000),
    (10000, 15000),
    (15000, 20000),
    (20000, 30000),
    (30000, 40000),
    (40000, 50000),
    (50000, 70000),
    (70000, 90000),
    (90000, 110000),
    (110000, 140000),
    (140000, 170000),
    (170000, 200000),
    (200000, math.inf),
]

# 与 docs/yaahlan_salary/公会进步奖档位表.md 单元格一一对应；0 表示 /
REWARDS = [
    [25, 60, 130, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [25, 60, 130, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 60, 130, 170, 0, 0, 0, 0, 0, 0, 0, 0],
    [0, 0, 130, 170, 300, 600, 0, 0, 0, 0, 0, 0],
    [0, 0, 130, 170, 300, 600, 1200, 0, 0, 0, 0, 0],
    [0, 0, 130, 170, 300, 600, 1200, 1800, 0, 0, 0, 0],
    [0, 0, 130, 170, 300, 600, 1200, 1800, 2400, 0, 0, 0],
    [0, 0, 0, 170, 300, 600, 1200, 1800, 2400, 3600, 0, 0],
    [0, 0, 0, 170, 300, 600, 1200, 1800, 2400, 3600, 4800, 6000],
    [0, 0, 0, 170, 300, 600, 1200, 1800, 2400, 3600, 4800, 6000],
    [0, 0, 0, 0, 300, 600, 1200, 1800, 2400, 3600, 4800, 6000],
    [0, 0, 0, 0, 300, 600, 1200, 1800, 2400, 3600, 4800, 6000],
    [0, 0, 0, 0, 0, 600, 1200, 1800, 2400, 3600, 4800, 6000],
    [0, 0, 0, 0, 0, 600, 1200, 1800, 2400, 3600, 4800, 6000],
    [0, 0, 0, 0, 0, 0, 1200, 1800, 2400, 3600, 4800, 6000],
]


def _index_in_bounds(value: float, bounds: list[tuple[float, float]]) -> int | None:
    for i, (low, high) in enumerate(bounds):
        if low <= value < high:
            return i
    return None


def lookup_motivation(base_salary: float, current_salary: float) -> float:
    """按基准薪资档位 × 绝对增长值查表，返回美元奖励。

    行首 `/` 保持 0；行尾 `/` 封顶为该行已出现的最高奖励。
    """
    growth = float(current_salary) - float(base_salary)
    if growth < 500:
        return 0.0
    row = _index_in_bounds(float(base_salary), BRACKET_BOUNDS)
    if row is None:
        return 0.0
    best = 0.0
    for i, (low, _high) in enumerate(GROWTH_BOUNDS):
        if growth < low:
            break
        best = max(best, float(REWARDS[row][i]))
    return best


def prev_period(period: str) -> str:
    year = int(period[:4])
    month = int(period[4:6])
    day = int(period[6:8])
    if day == 16:
        return f"{year:04d}{month:02d}01"
    month -= 1
    if month == 0:
        year -= 1
        month = 12
    return f"{year:04d}{month:02d}16"


def previous_periods(period: str, count: int) -> list[str]:
    out = []
    cur = period
    for _ in range(count):
        cur = prev_period(cur)
        out.append(cur)
    return out


def baseline_from_history(mode: str, current_period: str, history: dict[str, float]) -> float:
    """history: salary_period -> union_total_salary。"""
    if mode == "zero":
        return 0.0
    if mode == "prev_period":
        return float(history.get(prev_period(current_period), 0.0))
    if mode == "six_period_max":
        window = previous_periods(current_period, 6)
        values = [float(history[p]) for p in window if p in history]
        return max(values) if values else 0.0
    if mode == "since_register_max":
        values = [float(v) for p, v in history.items() if str(p) != str(current_period)]
        return max(values) if values else 0.0
    raise ValueError(f"未知 baseline_mode: {mode}")
