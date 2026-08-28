#!/usr/bin/env python3
"""线上 VIP 申请钉钉通知。"""

from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

GATEWAY_DIR = Path(__file__).resolve().parents[1] / "dingtalk_gateway"
WEB_AGENT_DIR = Path(__file__).resolve().parent
for path in (GATEWAY_DIR, WEB_AGENT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

from online_vip_notify import (  # noqa: E402
    build_online_vip_notify_markdown,
    classify_account_identifier,
    looks_like_online_vip_request,
    notify_online_vip_request,
    online_vip_handoff_reply,
    parse_online_vip_request,
    resolve_online_vip_notify_staff_ids,
)


class OnlineVipNotifyTest(unittest.TestCase):
    def test_detect_online_vip_upgrade(self) -> None:
        self.assertTrue(looks_like_online_vip_request("线上账号107427060，升级VIP3"))
        self.assertTrue(looks_like_online_vip_request("线上环境 给用户 100465989 加 VIP6"))

    def test_stage_vip_not_detected(self) -> None:
        self.assertFalse(looks_like_online_vip_request("100465989升级 VIP3"))
        self.assertFalse(looks_like_online_vip_request("线上环境查用户 107427060"))

    def test_parse_user_and_level(self) -> None:
        parsed = parse_online_vip_request("线上账号107427060，升级VIP3")
        self.assertEqual(parsed["rawIdentifier"], "107427060")
        self.assertEqual(parsed["accountType"], "userId")
        self.assertEqual(parsed["userId"], "107427060")
        self.assertEqual(parsed["vipLevel"], "3")

    def test_parse_phone_number(self) -> None:
        parsed = parse_online_vip_request("线上环境13311111111添加vip8")
        self.assertEqual(parsed["rawIdentifier"], "13311111111")
        self.assertEqual(parsed["accountType"], "phone")
        self.assertEqual(parsed["phone"], "13311111111")
        self.assertEqual(parsed["vipLevel"], "8")

    def test_classify_phone_vs_user_id(self) -> None:
        self.assertEqual(classify_account_identifier("13311111111", ""), "phone")
        self.assertEqual(classify_account_identifier("107427060", ""), "userId")
        self.assertEqual(
            classify_account_identifier("107427060", "线上查userId 107427060"),
            "userId",
        )

    def test_default_recipient_is_sun_xiaodong(self) -> None:
        with patch.dict("os.environ", {}, clear=True):
            self.assertEqual(
                resolve_online_vip_notify_staff_ids(),
                ["01302434415723305026"],
            )

    def test_build_markdown_contains_key_fields(self) -> None:
        body = build_online_vip_notify_markdown(
            message="线上账号107427060，升级VIP3",
            requester_staff_id="staff123",
            requester_name="张三",
            raw_identifier="107427060",
            account_type="userId",
            user_id="107427060",
            vip_level="3",
            user_summary={"nickname": "tester", "vipLevel": 1, "fullPhone": "+966123"},
        )
        self.assertIn("- **提问人**：张三", body)
        self.assertNotIn("staff123", body)
        self.assertIn("107427060", body)
        self.assertIn("userId", body)
        self.assertIn("VIP3", body)
        self.assertIn("tester", body)
        self.assertIn("当前 VIP1", body)

    @patch("online_vip_notify._query_online_user_summary")
    @patch("online_vip_notify._query_online_user_by_phone")
    @patch("online_vip_notify._web_agent_import")
    @patch("online_vip_notify._gateway_import")
    def test_notify_phone_resolves_then_queries(
        self,
        mock_gateway_import: unittest.mock.MagicMock,
        mock_web_import: unittest.mock.MagicMock,
        mock_phone_query: unittest.mock.MagicMock,
        mock_user_query: unittest.mock.MagicMock,
    ) -> None:
        sent: list[tuple[str, str, str]] = []

        def _fake_gateway_import(module: str, name: str) -> object:  # noqa: ANN001
            if module == "dingtalk_private_message" and name == "send_robot_private_markdown":
                def _send(staff_id: str, title: str, body: str, **kwargs: object) -> None:  # noqa: ANN001
                    del kwargs
                    sent.append((staff_id, title, body))

                return _send
            if module == "online_env_guard" and name == "looks_like_online_env_request":
                from online_env_guard import looks_like_online_env_request

                return looks_like_online_env_request
            raise AssertionError(f"unexpected gateway import {module}.{name}")

        def _fake_web_import(name: str) -> object:
            if name == "prepare_push_text":
                return lambda text: text
            if name == "prepare_push_title":
                return lambda text: "线上 VIP 申请"
            if name == "_enhance_markdown_for_dingtalk":
                return lambda text: text
            raise AssertionError(f"unexpected web import {name}")

        mock_gateway_import.side_effect = _fake_gateway_import
        mock_web_import.side_effect = _fake_web_import
        mock_phone_query.return_value = {"registered": True, "userId": "100465989"}
        mock_user_query.return_value = {"nickname": "phone_user", "vipLevel": 2}

        message = "线上环境13311111111添加vip8"
        result = notify_online_vip_request(
            message=message,
            requester_staff_id="req001",
            requester_name="李四",
        )

        self.assertTrue(result.get("ok"))
        mock_phone_query.assert_called_once_with("13311111111")
        mock_user_query.assert_called_once_with("100465989")
        self.assertEqual(len(sent), 1)
        self.assertIn("13311111111", sent[0][2])
        self.assertIn("100465989", sent[0][2])
        self.assertIn("phone_user", sent[0][2])
        self.assertIn("- **提问人**：李四", sent[0][2])
        self.assertNotIn("req001", sent[0][2])

    @patch("online_vip_notify._query_online_user_summary")
    @patch("online_vip_notify._web_agent_import")
    @patch("online_vip_notify._gateway_import")
    def test_notify_sends_each_request(
        self,
        mock_gateway_import: unittest.mock.MagicMock,
        mock_web_import: unittest.mock.MagicMock,
        mock_query: unittest.mock.MagicMock,
    ) -> None:
        sent: list[tuple[str, str, str]] = []

        def _fake_gateway_import(module: str, name: str) -> object:  # noqa: ANN001
            if module == "dingtalk_private_message" and name == "send_robot_private_markdown":
                def _send(staff_id: str, title: str, body: str, **kwargs: object) -> None:  # noqa: ANN001
                    del kwargs
                    sent.append((staff_id, title, body))

                return _send
            if module == "online_env_guard" and name == "looks_like_online_env_request":
                from online_env_guard import looks_like_online_env_request

                return looks_like_online_env_request
            raise AssertionError(f"unexpected gateway import {module}.{name}")

        def _fake_web_import(name: str) -> object:
            if name == "prepare_push_text":
                return lambda text: text
            if name == "prepare_push_title":
                return lambda text: "线上 VIP 申请"
            if name == "_enhance_markdown_for_dingtalk":
                return lambda text: text
            raise AssertionError(f"unexpected web import {name}")

        mock_gateway_import.side_effect = _fake_gateway_import
        mock_web_import.side_effect = _fake_web_import
        mock_query.return_value = {"nickname": "n1", "vipLevel": 2}

        message = "线上账号107427060，升级VIP3"
        first = notify_online_vip_request(
            message=message,
            requester_staff_id="req001",
            requester_name="李四",
        )
        second = notify_online_vip_request(
            message=message,
            requester_staff_id="req001",
            requester_name="李四",
        )

        self.assertTrue(first.get("ok"))
        self.assertEqual(first.get("sent_count"), 1)
        self.assertTrue(second.get("ok"))
        self.assertEqual(second.get("sent_count"), 1)
        self.assertEqual(len(sent), 2)
        self.assertEqual(sent[0][0], "01302434415723305026")
        self.assertEqual(sent[1][0], "01302434415723305026")

    @patch("online_vip_notify.resolve_online_vip_account")
    @patch("online_vip_notify.notify_online_vip_request")
    def test_handoff_reply_on_success(
        self,
        mock_notify: unittest.mock.MagicMock,
        mock_resolve: unittest.mock.MagicMock,
    ) -> None:
        mock_resolve.return_value = {
            "rawIdentifier": "13311111111",
            "accountType": "phone",
            "phone": "13311111111",
            "userId": "100465989",
            "vipLevel": "8",
            "userSummary": {"nickname": "tester", "vipLevel": 1},
            "resolveError": "",
        }
        mock_notify.return_value = {"ok": True, "sent_count": 1}
        reply = online_vip_handoff_reply(
            message="线上环境13311111111添加vip8",
            requester_staff_id="req001",
        )
        self.assertIn("孙晓东", reply)
        self.assertIn("不会", reply)
        self.assertIn("13311111111", reply)
        self.assertIn("100465989", reply)
        self.assertIn("VIP8", reply)
        self.assertIn("tester", reply)
        mock_resolve.assert_called_once()
        mock_notify.assert_called_once()

    @patch("online_vip_notify.resolve_online_vip_account")
    @patch("online_vip_notify.notify_online_vip_request")
    def test_handoff_reply_on_failure(
        self,
        mock_notify: unittest.mock.MagicMock,
        mock_resolve: unittest.mock.MagicMock,
    ) -> None:
        mock_resolve.return_value = {
            "rawIdentifier": "13311111111",
            "accountType": "phone",
            "userId": "",
            "vipLevel": "8",
            "userSummary": {},
            "resolveError": "",
        }
        mock_notify.return_value = {"ok": False, "error": "钉钉发送失败"}
        reply = online_vip_handoff_reply(
            message="线上环境13311111111添加vip8",
            requester_staff_id="req001",
        )
        self.assertIn("通知失败", reply)
        self.assertIn("钉钉发送失败", reply)


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(OnlineVipNotifyTest)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.wasSuccessful():
        print("[PASS] verify_online_vip_notify")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
