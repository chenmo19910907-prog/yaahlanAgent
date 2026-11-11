# -*- coding: utf-8 -*-
"""无训练权重时的启发式解析（仅 dev 自测）；正式赛需用 SFT 模型替换。"""

from __future__ import annotations

import re
from typing import Any

from competition_1024.constants import CANONICAL_POINTS, CANCEL_PHRASES
from competition_1024.data_prep import pick_single_demand

_CAR_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"六座.*(商务|MPV)|静音商务"), "business_6"),
    (re.compile(r"载物|防震|后备箱"), "luggage_2"),
    (re.compile(r"标准轿车|普通四座|四座出租"), "standard_4"),
]

_POINT_ALIASES: list[tuple[str, str]] = [
    ("南广场一号候车区", "南侧广场1号点"),
    ("南广场二号候车区", "南侧广场2号点"),
    ("北侧步道1号点", "北侧步道1号点"),
    ("北步道一号候车区", "北侧步道1号点"),
    ("北步道二号候车区", "北侧步道2号点"),
    ("北侧步道2号点", "北侧步道2号点"),
    ("东车道一号候车区", "东侧车道1号点"),
    ("东车道二号候车区", "东侧车道2号点"),
    ("西道路一号候车区", "西侧道路1号点"),
    ("西北角入口", "西北门"),
    ("正北入口", "北门"),
    ("大厦西南门", "西南门"),
    ("大厦东北门", "东北门"),
    ("大厦南门", "南门"),
]


def _segment_cancelled(seg: str) -> bool:
    return any(p in seg for p in CANCEL_PHRASES)


def _resolve_point(seg: str) -> str | None:
    for alias, canon in _POINT_ALIASES:
        if alias in seg:
            return canon
    for p in CANONICAL_POINTS:
        if p in seg:
            return p
    # 短名门
    for short, full in (
        ("东北门", "东北门"),
        ("东南门", "东南门"),
        ("西南门", "西南门"),
        ("西北门", "西北门"),
        ("东门", "东门"),
        ("南门", "南门"),
        ("西门", "西门"),
        ("北门", "北门"),
    ):
        if short in seg:
            return full
    return None


def _resolve_car_type(seg: str) -> str | None:
    for pat, code in _CAR_RULES:
        if pat.search(seg):
            return code
    return None


def _trip_seconds(seg: str) -> int:
    m = re.search(r"车程\s*(\d+)|行程约?\s*(\d+)\s*秒", seg)
    if not m:
        return 0
    return int(m.group(1) or m.group(2))


def _required_cars(seg: str) -> int:
    m = re.search(r"共\s*(\d+)\s*人.*?每\s*(\d+)\s*人", seg)
    if m:
        total, per = int(m.group(1)), int(m.group(2))
        return (total + per - 1) // per if per else 1
    m = re.search(r"(\d+)\s*名.*?每\s*(\d+)\s*人", seg)
    if m:
        total, per = int(m.group(1)), int(m.group(2))
        return (total + per - 1) // per if per else 1
    return 1


def parse_segments(text: str) -> list[dict[str, Any]]:
    parts = re.split(r"[。；\n]", text)
    out: list[dict[str, Any]] = []
    for seg in parts:
        seg = seg.strip()
        if not seg or _segment_cancelled(seg):
            continue
        # 「真正要走的是」优先段
        car_type = _resolve_car_type(seg)
        point = _resolve_point(seg)
        if not car_type or not point:
            continue
        out.append(
            {
                "point": point,
                "car_type": car_type,
                "required_cars": _required_cars(seg),
                "trip_seconds": _trip_seconds(seg),
            }
        )
    return out


def parse_broadcast(text: str) -> dict[str, Any]:
    """返回与比赛一致的 demands JSON 结构（单条 + 固定 1,1 由 compressed 层处理）。"""
    demands = pick_single_demand(parse_segments(text))
    from competition_1024.compressed_output import demands_to_compressed_json

    return {
        "demands": demands,
        "model_output": demands_to_compressed_json(demands[0] if demands else None),
    }
