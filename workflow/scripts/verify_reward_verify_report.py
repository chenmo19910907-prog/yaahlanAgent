#!/usr/bin/env python3
"""verify_reward_verify_report：奖励验收 Markdown 报告单元测试。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

_REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_REPO / "workflow" / "scripts"))

from reward_verify import (  # noqa: E402
    _enrich_gift_diff_entry,
    _enrich_nameplate_diff_entry,
    _enrich_prop_diff_entry,
    _issued_gifts_from_diff,
    _issued_nameplates_from_diff,
    _issued_props_from_diff,
    format_diff_report,
)


def _sample_diff() -> dict:
    path = _REPO / ".tmp" / "cp_chest_100486375_diff.json"
    return json.loads(path.read_text(encoding="utf-8"))


def test_enrich_gift_has_price_and_validity() -> None:
    entry = {
        "giftId": "2005058134",
        "name": "My beloved rose",
        "remainDelta": 1,
        "price": 100.0,
        "expireAfter": 1786204740,
    }
    enriched = _enrich_gift_diff_entry(entry, reference_ts=1785144533)
    assert enriched["issued"] is True
    assert enriched["totalDiamondValue"] == 100.0
    assert enriched.get("validityDays") is not None
    assert enriched.get("expireAfterLabel")


def test_enrich_prop_new_vs_changed() -> None:
    new_item = _enrich_prop_diff_entry(
        {
            "propId": "30006429",
            "propName": "CP宝箱上麦特效",
            "status": "new",
            "expireTimeAfter": "2026-08-26 15:15:19 +0800",
        },
        reference_ts=1785144533,
    )
    assert new_item["issued"] is True
    assert new_item.get("actualIssuedDays") is not None

    changed_item = _enrich_prop_diff_entry(
        {
            "propId": "30006045",
            "propName": "CP LV.7",
            "status": "changed",
            "expireTimeBefore": "2026-06-25 19:07:16 +0800",
            "expireTimeAfter": "2026-08-11 17:28:33 +0800",
        },
        reference_ts=1785144533,
    )
    assert changed_item["issued"] is True
    # 发奖前已过期，应按 reference→expireAfter 计约 15 天，而非日历差 46.93
    assert changed_item.get("actualIssuedDays") == 15.0

    extend_item = _enrich_prop_diff_entry(
        {
            "propId": "30006421",
            "propName": "CP麦位声波test",
            "status": "changed",
            "expireTimeBefore": "2026-12-24 15:15:19 +0800",
            "expireTimeAfter": "2027-01-08 15:15:19 +0800",
        },
        reference_ts=1785144533,
    )
    assert extend_item.get("actualIssuedDays") == 15.0


def test_enrich_prop_renew_after_expired_cp_lv9() -> None:
    item = _enrich_prop_diff_entry(
        {
            "propId": "30006049",
            "propName": "CP LV.9",
            "status": "changed",
            "expireTimeBefore": "2026-06-30 14:52:55 +0800",
            "expireTimeAfter": "2026-08-12 11:54:52 +0800",
        },
        reference_ts=1785210946,
    )
    assert item.get("actualIssuedDays") == 15.0


def test_enrich_nameplate_new_unlock() -> None:
    item = _enrich_nameplate_diff_entry(
        {
            "nameplateId": "1138",
            "title": "sweet CP",
            "newlyUnlocked": True,
            "unlockedAfter": True,
            "unlockTimeAfter": 1785144513,
            "remainTimeAfter": 1_294_335,
            "remainDaysAfter": 14.98,
        },
        reference_ts=1785144533,
    )
    assert item["issued"] is True
    assert item.get("actualIssuedDays") == 14.98
    assert item.get("expireAfterLabel")
    assert item.get("unlockTimeAfterLabel")


def test_enrich_nameplate_extension() -> None:
    item = _enrich_nameplate_diff_entry(
        {
            "nameplateId": "1138",
            "title": "sweet CP",
            "newlyUnlocked": False,
            "unlockedAfter": True,
            "unlockTimeBefore": 1785144513,
            "unlockTimeAfter": 1785144513,
            "remainTimeBefore": 864_000,
            "remainTimeAfter": 1_728_000,
            "remainDaysBefore": 10.0,
            "remainDaysAfter": 20.0,
        },
        reference_ts=1785144533,
    )
    assert item["issued"] is True
    assert item.get("actualIssuedDays") == 10.0


def test_report_includes_nameplates() -> None:
    diff = _sample_diff()
    diff["nameplates"] = [
        {
            "nameplateId": "1138",
            "title": "sweet CP",
            "newlyUnlocked": True,
            "unlockedAfter": True,
            "unlockTimeAfter": 1785144513,
            "remainTimeAfter": 1_294_335,
            "remainDaysAfter": 14.98,
        }
    ]
    plates = _issued_nameplates_from_diff(diff)
    assert len(plates) == 1
    assert plates[0].get("actualIssuedDays") == 14.98

    md = format_diff_report(diff, user_label="100486375")
    assert "## 铭牌（实际下发）" in md
    assert "1138" in md
    assert "sweet CP" in md
    assert "实际下发有效期" in md


def test_report_lists_issued_gifts_and_props() -> None:
    diff = _sample_diff()
    gifts = _issued_gifts_from_diff(diff)
    props = _issued_props_from_diff(diff)
    assert len(gifts) == 6
    assert all(g.get("price") is not None for g in gifts)
    assert all(g.get("validityDays") is not None or g.get("expireDaysAfter") is not None for g in gifts)
    assert len(props) >= 10

    md = format_diff_report(diff, user_label="100486375")
    assert "## 个人装扮（实际下发）" in md
    assert "## 礼物背包（实际下发）" in md
    assert "30006429" in md
    assert "2005058134" in md
    assert "单价(钻)" in md
    assert "实际下发有效期" in md
    assert "My beloved rose" in md


def main() -> int:
    test_enrich_gift_has_price_and_validity()
    test_enrich_prop_new_vs_changed()
    test_enrich_prop_renew_after_expired_cp_lv9()
    test_enrich_nameplate_new_unlock()
    test_enrich_nameplate_extension()
    test_report_includes_nameplates()
    test_report_lists_issued_gifts_and_props()
    print("verify_reward_verify_report: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
