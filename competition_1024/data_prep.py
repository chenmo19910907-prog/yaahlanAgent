# -*- coding: utf-8 -*-
"""官方多需求标签 → O.O 单条贪心标签（最长 trip_seconds）。"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Iterator

from competition_1024.compressed_output import demands_to_compressed_json
from competition_1024.constants import FIXED_REQUIRED_CARS, FIXED_TRIP_SECONDS


def iter_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    with path.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def pick_single_demand(demands: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not demands:
        return []
    best = max(demands, key=lambda d: int(d.get("trip_seconds") or 0))
    return [best]


def slim_label_demand(d: dict[str, Any]) -> dict[str, Any]:
    """训练目标：只保留 point / car_type，数字字段固定 1（模型侧输出）。"""
    return {
        "point": d["point"],
        "car_type": d["car_type"],
        "required_cars": FIXED_REQUIRED_CARS,
        "trip_seconds": FIXED_TRIP_SECONDS,
    }


def transform_record(record: dict[str, Any]) -> dict[str, Any]:
    text = record["text"]
    picked = pick_single_demand(record.get("demands") or [])
    demands = [slim_label_demand(d) for d in picked]
    return {
        "text": text,
        "demands": demands,
        "model_output": demands_to_compressed_json(picked[0] if picked else None),
    }


def write_jsonl(records: Iterator[dict[str, Any]], out_path: Path) -> int:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    n = 0
    with out_path.open("w", encoding="utf-8") as f:
        for rec in records:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            n += 1
    return n


def prepare_from_files(train_in: Path, dev_in: Path, out_dir: Path) -> dict[str, int]:
    out_dir.mkdir(parents=True, exist_ok=True)
    counts = {}
    for name, src in ("train", train_in), ("dev", dev_in):
        dest = out_dir / f"{name}_single.jsonl"
        counts[name] = write_jsonl((transform_record(r) for r in iter_jsonl(src)), dest)
    tokens_path = out_dir / "special_tokens.txt"
    from competition_1024.compressed_output import build_special_token_list

    tokens_path.write_text("\n".join(build_special_token_list()) + "\n", encoding="utf-8")
    counts["special_tokens"] = len(build_special_token_list())
    return counts
