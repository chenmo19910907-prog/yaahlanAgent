#!/usr/bin/env python3
"""web_moa_call_log 单测：合并批量、倒序列表。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

WEB_AGENT_DIR = Path(__file__).resolve().parent
if str(WEB_AGENT_DIR) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(WEB_AGENT_DIR))

from web_moa_call_log import (  # noqa: E402
    _extract_account_hint,
    _operation_label,
    beautify_account_summary,
    format_account_summary_display,
    beautify_params_summary,
    extract_params_summary_from_payload,
    list_moa_call_entries,
    record_moa_call,
    build_semantic_operation_summary,
    collapse_batch_params_summary,
    format_operation_display,
    resolve_operation_display,
)


class WebMoaCallLogTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.log_path = Path(self.tmp.name) / "moa_call_log.json"

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def _patch_log(self):
        return patch("web_moa_call_log.LOG_PATH", self.log_path)

    def test_merge_same_run_and_operation(self) -> None:
        payload = {"url": "/service/foo", "method": "bar", "params": []}
        ok_resp = {"ec": 200, "result": {"ec": 0}}
        fail_resp = {"ec": 200, "result": {"ec": 500}}
        with self._patch_log():
            record_moa_call(
                payload=payload,
                response=ok_resp,
                run_id="run1",
                operator_staff_id="s1",
                operator_name="测试员",
            )
            record_moa_call(
                payload=payload,
                response=ok_resp,
                run_id="run1",
                operator_name="测试员",
            )
            record_moa_call(
                payload=payload,
                response=fail_resp,
                run_id="run1",
                operator_name="测试员",
            )
            payload2 = list_moa_call_entries(limit=10)
        self.assertEqual(payload2["total"], 1)
        entry = payload2["entries"][0]
        self.assertEqual(entry["callCount"], 3)
        self.assertEqual(entry["successCount"], 2)
        self.assertEqual(entry["failCount"], 1)
        self.assertIn("成功 2/3", entry["resultSummary"])

    def test_vip_params_use_semantic_names(self) -> None:
        payload = {
            "method": "addVipValue",
            "params": [
                {"title": "参数1", "name": "1", "value": "100465989", "type": "string"},
                {"title": "参数2", "name": "2", "value": "1", "type": "int"},
            ],
        }
        summary = extract_params_summary_from_payload(payload)
        self.assertIn("userId=100465989", summary)
        self.assertIn("value=1", summary)
        self.assertNotIn("1=100465989", summary)

    def test_semantic_operation_summary(self) -> None:
        self.assertEqual(
            build_semantic_operation_summary(
                "queryLoginStatusV2",
                "loginType=MOBILE，thirdUid=13311111111，areaCode=86",
            ),
            "查询手机号 13311111111 对应 userId",
        )
        self.assertEqual(
            build_semantic_operation_summary(
                "addVipValue",
                "userId=100465989，value=1",
            ),
            "用户 100465989 增加 1 VIP经验值",
        )
        self.assertEqual(
            format_operation_display(
                "用户-按手机号查userId",
                method="queryLoginStatusV2",
                params_summary="thirdUid=13311111112，areaCode=86",
            ),
            "查询手机号 13311111112 对应 userId",
        )
        self.assertEqual(
            build_semantic_operation_summary(
                "provideDiamond",
                "userId=100465989，num=100",
                account_summary="100465989 等 5 个账号",
                call_count=5,
            ),
            "100465989 等 5 个账号各发放 100 钻石",
        )
        self.assertEqual(
            build_semantic_operation_summary(
                "provideDiamond",
                "每账号 num=100（共 5 个账号，不逐一列出）",
                account_summary="100465989 等 5 个账号",
                call_count=5,
            ),
            "100465989 等 5 个账号各发放 100 钻石",
        )
        collapsed = collapse_batch_params_summary(
            "userId=100465989，num=100；userId=100486375，num=100",
            method="provideDiamond",
            call_count=100,
            account_summary="100465989 等 100 个账号",
        )
        self.assertIn("每账号 num=100", collapsed)
        self.assertIn("共 100 个账号", collapsed)
        self.assertNotIn("100486375", collapsed)

    def test_get_vip_info_operation_label(self) -> None:
        label = _operation_label(
            payload_file="MOA/templates/VIP-增加经验值.json",
            service_url="/service/voga-mts-user-vip-stage",
            method="getVipInfo",
        )
        self.assertEqual(label, "VIP经验值-查询当前等级经验")
        self.assertEqual(
            resolve_operation_display("VIP-增加经验值", method="getVipInfo"),
            "VIP经验值-查询当前等级经验",
        )

    def test_account_hint_omits_momo_id(self) -> None:
        payload = {
            "momoId": "df4c6f364f9fcae3",
            "params": [{"name": "1", "value": "100465989"}],
        }
        self.assertEqual(_extract_account_hint(payload), "100465989")

    def test_beautify_account_strips_momo_id(self) -> None:
        self.assertEqual(
            beautify_account_summary("100465989、df4c6f364f9fcae3"),
            "100465989",
        )

    def test_account_display_includes_environment(self) -> None:
        self.assertEqual(
            format_account_summary_display("100465989", environment="test"),
            "测试 · 100465989",
        )
        self.assertEqual(
            format_account_summary_display("100465989", environment="online"),
            "线上 · 100465989",
        )

    def test_beautify_legacy_numeric_keys(self) -> None:
        raw = "1=100465989，2=1"
        fixed = beautify_params_summary(raw, method="addVipValue")
        self.assertEqual(fixed, "userId=100465989，value=1")

    def test_list_newest_first(self) -> None:
        payload = {"url": "/service/a", "method": "m", "params": []}
        resp = {"ec": 0}
        with self._patch_log():
            record_moa_call(
                payload=payload,
                response=resp,
                run_id="r1",
                payload_file="模板A.json",
                operator_name="测试员",
            )
            record_moa_call(
                payload={"url": "/service/b", "method": "m", "params": []},
                response=resp,
                run_id="r2",
                operator_name="测试员",
            )
            rows = list_moa_call_entries(limit=10)["entries"]
        self.assertEqual(len(rows), 2)
        self.assertTrue(rows[0]["timeBj"] >= rows[1]["timeBj"] or rows[0]["ts"] >= rows[1]["ts"])


if __name__ == "__main__":
    raise SystemExit(unittest.main())
