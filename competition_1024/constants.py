# -*- coding: utf-8 -*-
"""2026-1024 候车广播派车赛 · 常量（与官方 train 标注一致）。"""

from __future__ import annotations

CANONICAL_POINTS: tuple[str, ...] = (
    "东侧车道1号点",
    "东侧车道2号点",
    "东北门",
    "东南门",
    "东门",
    "北侧步道1号点",
    "北侧步道2号点",
    "北门",
    "南侧广场1号点",
    "南侧广场2号点",
    "南门",
    "西侧道路1号点",
    "西北门",
    "西南门",
    "西门",
)

CAR_TYPES: tuple[str, ...] = ("standard_4", "luggage_2", "business_6")

FIXED_REQUIRED_CARS = 1
FIXED_TRIP_SECONDS = 1

DEFAULT_API_BASE = "https://1024.wemomo.com"

# 训练标签里「取消/不必派车」常见表述（启发式解析用）
CANCEL_PHRASES: tuple[str, ...] = (
    "原本想叫",
    "不需要派车",
    "不需要出租车",
    "取消用车",
    "不用叫车",
    "不用叫",
    "步行离开",
    "改乘地铁",
    "改坐",
    "班车",
    "夜班公交",
    "共享单车",
    "线上开会",
    "顺路带走",
    "同事开车",
)
