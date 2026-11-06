#!/usr/bin/env python3
"""操作记录重跑：registry 匹配与参数映射单测。"""

from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch


class CallLogReplayTests(unittest.TestCase):
    def test_find_moa_capability_by_operation_name(self) -> None:
        from web_call_log_replay import find_capability_for_entry

        entry = {
            "source": "moa",
            "environment": "test",
            "operation": "用户-按手机号查 userId",
            "serviceUrl": "/service/yaahlan/mdp-user-login",
            "method": "queryLoginStatusV2",
            "paramsSummary": "thirdUid=13311111166",
        }
        cap = find_capability_for_entry(entry)
        self.assertIsNotNone(cap)
        assert cap is not None
        self.assertEqual(cap.module_id, "moa")

    def test_build_substitute_user_id(self) -> None:
        from web_call_log_replay import _build_substitute_params, find_capability_for_entry

        entry = {
            "source": "admin",
            "environment": "test",
            "operation": "Admin 查询用户 100299850 详情",
            "serviceUrl": "/admin/user/queryUserDetail",
            "method": "POST",
            "paramsSummary": "userId=100299850",
        }
        cap = find_capability_for_entry(entry)
        self.assertIsNotNone(cap)
        assert cap is not None
        sub = _build_substitute_params(cap, {"userId": "100299850"})
        self.assertTrue(any(v == "100299850" for v in sub.values()))

    def test_find_diamond_query_by_semantic_operation_title(self) -> None:
        from web_call_log_replay import find_capability_for_entry, params_rows_for_entry

        entry = {
            "source": "moa",
            "environment": "test",
            "operation": "100218396 等 6 个账号 查询钻石余额",
            "serviceUrl": "/service/voga-base-service-middle-pay-stage",
            "method": "queryUserAccount",
            "paramsSummary": "1=100218396（共 6 个账号，不逐一列出）",
            "accountSummary": "100218396 等 6 个账号",
            "callCount": 6,
        }
        cap = find_capability_for_entry(entry)
        self.assertIsNotNone(cap)
        assert cap is not None
        self.assertEqual(cap.name, "钻石-查询余额")
        rows = params_rows_for_entry(entry, cap)
        by_key = {r["key"]: r for r in rows}
        self.assertEqual(by_key["userId"]["value"], "100218396")
        self.assertNotIn("1", by_key)

    def test_batch_record_replay_uses_first_account_only(self) -> None:
        from web_call_log_replay import (
            _build_substitute_params,
            _raw_params_from_entry,
            find_capability_for_entry,
            params_rows_for_entry,
        )

        entry = {
            "source": "moa",
            "environment": "test",
            "operation": "100299850 等 6 个账号 查询钻石余额",
            "serviceUrl": "/service/voga-base-service-middle-pay-stage",
            "method": "queryUserAccount",
            "paramsSummary": "userId=100299850",
            "accountSummary": "100299850 等 6 个账号",
            "callCount": 6,
        }
        raw = _raw_params_from_entry(entry)
        self.assertEqual(raw.get("userId"), "100299850")
        cap = find_capability_for_entry(entry)
        assert cap is not None
        rows = params_rows_for_entry(entry, cap)
        self.assertEqual(len([r for r in rows if r["key"] == "userId"]), 1)
        sub = _build_substitute_params(cap, raw)
        self.assertEqual(sub.get("userId"), "100299850")

    def test_execute_replay_records_to_call_log(self) -> None:
        from web_agent_audit_context import BATCH_KEY_ENV, RUN_ID_ENV
        from web_call_log_replay import execute_replay

        with tempfile.TemporaryDirectory() as tmp:
            log_path = Path(tmp) / "moa_call_log.json"
            log_path.write_text("[]\n", encoding="utf-8")
            entry = {
                "id": "abc123deadbeef",
                "source": "moa",
                "environment": "test",
                "operation": "100299850 查询钻石余额",
                "serviceUrl": "/service/voga-base-service-middle-pay-stage",
                "method": "queryUserAccount",
                "paramsSummary": "userId=100299850",
                "accountSummary": "100299850",
            }
            log_path.write_text(f"[{__import__('json').dumps(entry, ensure_ascii=False)}]\n", encoding="utf-8")

            captured_env: dict[str, str] = {}

            def fake_run_argv(argv, *, timeout_sec=120, env=None):
                captured_env.update(env or {})
                return {"ok": False, "exit_code": 1, "stdout": "", "stderr": "boom", "argv": argv}

            with patch("web_moa_call_log.LOG_PATH", log_path):
                with patch("web_call_log_replay.run_argv", side_effect=fake_run_argv):
                    out = execute_replay(
                        entry_id="abc123deadbeef",
                        params_rows=[],
                        operator_staff_id="staff1",
                        operator_name="测试员",
                    )
            self.assertFalse(out["ok"])
            self.assertEqual(captured_env.get(BATCH_KEY_ENV), captured_env[BATCH_KEY_ENV])
            self.assertTrue(captured_env.get(RUN_ID_ENV))
            rows = __import__("json").loads(log_path.read_text(encoding="utf-8"))
            self.assertEqual(len(rows), 2)
            latest = rows[-1]
            self.assertEqual(latest.get("operatorStaffId"), "staff1")
            self.assertEqual(latest.get("operatorName"), "测试员")
            self.assertIn("失败", str(latest.get("resultSummary") or ""))

    def test_replay_result_view_prefers_stdout_json(self) -> None:
        from web_call_log_replay import _build_replay_result_view

        run = {
            "ok": True,
            "stdout": json.dumps(
                {
                    "areaCode": "86",
                    "mobile": "13311111111",
                    "fullNumber": "+8613311111111",
                    "registered": True,
                    "userId": "100414599",
                },
                ensure_ascii=False,
            ),
            "stderr": '请求信息: entry_url="https://example.com", method="queryLoginStatusV2"',
            "data": json.loads(
                '{"areaCode":"86","mobile":"13311111111","registered":true,"userId":"100414599"}'
            ),
        }
        view = _build_replay_result_view(run, ok=True, fallback_summary="成功")
        self.assertIn("100414599", view["displaySummary"])
        labels = [r["label"] for r in view["resultRows"]]
        self.assertIn("userId", labels)

    def test_room_add_bots_chinese_param_labels(self) -> None:
        from web_call_log_replay import find_capability_for_entry, params_rows_for_entry

        entry = {
            "source": "moa",
            "environment": "test",
            "operation": "房间-增加机器人",
            "serviceUrl": "/service/voga-mts-room-backdoor",
            "method": "addOnlineUsersToRoom",
            "paramsSummary": "roomId=80949067，总数=1，麦上数=0",
        }
        cap = find_capability_for_entry(entry)
        self.assertIsNotNone(cap)
        assert cap is not None
        rows = params_rows_for_entry(entry, cap)
        by_key = {r["key"]: r for r in rows}
        self.assertEqual(by_key["roomId"]["value"], "80949067")
        self.assertEqual(by_key["total"]["value"], "1")
        self.assertEqual(by_key["onMic"]["value"], "0")
        self.assertNotIn("总数", by_key)
        self.assertNotIn("麦上数", by_key)


if __name__ == "__main__":
    unittest.main()
