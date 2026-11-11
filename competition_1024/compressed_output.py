# -*- coding: utf-8 -*-
"""O.O 方案：将 demands JSON 压成 3 Token 级别的固定片段（词表扩展用）。"""

from __future__ import annotations

import json
from typing import Any

from competition_1024.constants import (
    CANONICAL_POINTS,
    CAR_TYPES,
    FIXED_REQUIRED_CARS,
    FIXED_TRIP_SECONDS,
)

EMPTY_DEMANDS_JSON = '{"demands":[]}'

# 通用开头：陌生地点时先出此 Token，再拼地点子串，最后接车型尾 Token
GENERIC_POINT_PREFIX = '{"demands":[{"point":"'

CAR_TYPE_SUFFIX: dict[str, str] = {
    ct: f'","car_type":"{ct}","required_cars":{FIXED_REQUIRED_CARS},"trip_seconds":{FIXED_TRIP_SECONDS}]}}'
    for ct in CAR_TYPES
}


def point_header_token(point: str) -> str:
    """常见 15 点：整段 `{\"demands\":[{\"point\":\"<点>` 为一个专用 Token。"""
    return f'{{"demands":[{{"point":"{point}'


def build_point_header_tokens() -> list[str]:
    return [point_header_token(p) for p in CANONICAL_POINTS]


def build_car_suffix_tokens() -> list[str]:
    return list(CAR_TYPE_SUFFIX.values())


def build_special_token_list() -> list[str]:
    tokens = build_point_header_tokens() + build_car_suffix_tokens() + [EMPTY_DEMANDS_JSON, GENERIC_POINT_PREFIX]
    return tokens


def demands_to_compressed_json(demand: dict[str, Any] | None) -> str:
    """单条或空需求 → 对外 JSON（required_cars / trip_seconds 固定为 1）。"""
    if demand is None:
        return EMPTY_DEMANDS_JSON
    out = {
        "point": demand["point"],
        "car_type": demand["car_type"],
        "required_cars": FIXED_REQUIRED_CARS,
        "trip_seconds": FIXED_TRIP_SECONDS,
    }
    return json.dumps({"demands": [out]}, ensure_ascii=False, separators=(",", ":"))


def decode_from_point_and_car(point: str, car_type: str) -> str:
    if car_type not in CAR_TYPE_SUFFIX:
        raise ValueError(f"unknown car_type: {car_type}")
    if point not in CANONICAL_POINTS:
        suffix = CAR_TYPE_SUFFIX[car_type]
        return GENERIC_POINT_PREFIX + point + suffix
    return point_header_token(point) + CAR_TYPE_SUFFIX[car_type]
