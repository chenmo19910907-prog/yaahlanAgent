#!/usr/bin/env python3
"""Web Agent Open API 单元测试（无网络、无真实 Agent 任务）。"""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from http.server import BaseHTTPRequestHandler
from io import BytesIO
from pathlib import Path
from unittest import mock

WEB_AGENT_DIR = Path(__file__).resolve().parent
if str(WEB_AGENT_DIR) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(WEB_AGENT_DIR))

import web_agent_open_api as open_api  # noqa: E402
import web_agent_open_api_user_tokens as user_tokens  # noqa: E402


class _FakeHandler(BaseHTTPRequestHandler):
    def __init__(self, headers: dict[str, str]) -> None:
        self.headers = headers  # type: ignore[misc]
        self.rfile = BytesIO()
        self.wfile = BytesIO()
        self.path = "/api/open/v1/task/submit"

    def log_message(self, format: str, *args: object) -> None:
        return


class OpenApiAuthTests(unittest.TestCase):
    def test_map_run_status(self) -> None:
        self.assertEqual(open_api.map_run_status_to_open_api("done"), "completed")
        self.assertEqual(open_api.map_run_status_to_open_api("running"), "running")
        self.assertEqual(open_api.map_run_status_to_open_api("interrupted"), "cancelled")

    def test_build_task_query_completed(self) -> None:
        data = open_api.build_task_query_data(
            task_id="abc123456789",
            session_id="sess1",
            run_status="done",
            final_text="hello",
            error_text=None,
        )
        self.assertEqual(data["status"], "completed")
        self.assertEqual(data["result"], "hello")
        self.assertNotIn("retry_after_ms", data)

    def test_build_task_query_running_progress(self) -> None:
        data = open_api.build_task_query_data(
            task_id="abc123456789",
            session_id="sess1",
            run_status="running",
            final_text="",
            error_text=None,
            phase_line="Agent 执行中…",
            last_markdown="正在查询配置",
        )
        self.assertEqual(data["status"], "running")
        self.assertEqual(data["phase"], "Agent 执行中…")
        self.assertEqual(data["progress_preview"], "正在查询配置")
        self.assertEqual(data["retry_after_ms"], open_api.OPEN_API_QUERY_RETRY_AFTER_MS)

    @mock.patch.object(open_api, "normalize_open_api_callback_url", return_value=None)
    def test_normalize_callback_invalid(self, _mock: mock.Mock) -> None:
        self.assertIsNone(open_api.normalize_open_api_callback_url("http://127.0.0.1:9/nope"))

    def test_task_record_callback_fields(self) -> None:
        record = open_api.OpenApiTaskRecord(
            task_id="abcd1234",
            run_id="abcd1234",
            session_id="s1",
            client_key="ck",
            message_preview="hi",
            created_at=1.0,
            callback_url="https://example.test/cb",
        )
        loaded = open_api.OpenApiTaskRecord.from_dict(record.as_dict())
        self.assertEqual(loaded.callback_url, "https://example.test/cb")

    @mock.patch.dict(os.environ, {"WEB_AGENT_OPEN_API_TOKEN": "test-token-secret"}, clear=False)
    def test_authenticate_success(self) -> None:
        handler = _FakeHandler({"Authorization": "Bearer test-token-secret"})
        client_key, err, status = open_api.authenticate(handler)
        self.assertIsNone(err)
        self.assertEqual(status, 200)
        self.assertEqual(len(client_key or ""), 32)

    @mock.patch.dict(os.environ, {"WEB_AGENT_OPEN_API_TOKEN": "test-token-secret"}, clear=False)
    def test_authenticate_wrong_token(self) -> None:
        handler = _FakeHandler({"Authorization": "Bearer wrong"})
        _key, err, status = open_api.authenticate(handler)
        self.assertIsNotNone(err)
        self.assertEqual(status, 401)
        assert err is not None
        self.assertEqual(err.get("code"), "UNAUTHORIZED")

    def test_task_register_and_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            task_dir = Path(tmp)
            with mock.patch.object(open_api, "TASK_DIR", task_dir):
                record = open_api.OpenApiTaskRecord(
                    task_id="deadbeef1234",
                    run_id="deadbeef1234",
                    session_id="sess99",
                    client_key="ck",
                    message_preview="hi",
                    created_at=1.0,
                )
                open_api.register_open_api_task(record)
                loaded = open_api.get_open_api_task("deadbeef1234")
                self.assertIsNotNone(loaded)
                assert loaded is not None
                self.assertEqual(loaded.session_id, "sess99")

    def test_is_open_api_path(self) -> None:
        self.assertTrue(open_api.is_open_api_path("/api/open/v1/task/submit"))
        self.assertFalse(open_api.is_open_api_path("/api/chat"))

    def test_user_token_authenticate(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            token_path = Path(tmp) / "tokens.json"
            with mock.patch.object(user_tokens, "USER_TOKENS_PATH", token_path):
                with mock.patch.dict(os.environ, {}, clear=False):
                    os.environ.pop("WEB_AGENT_OPEN_API_TOKEN", None)
                    os.environ.pop("YAAHLAN_WEB_AGENT_OPEN_API_TOKEN", None)
                    plaintext, _meta = user_tokens.generate_user_token("staff_001")
                    handler = _FakeHandler({"Authorization": f"Bearer {plaintext}"})
                    client_key, err, status = open_api.authenticate(handler)
                    self.assertIsNone(err)
                    self.assertEqual(status, 200)
                    self.assertEqual(client_key, open_api.client_key_for_staff("staff_001"))
                    self.assertEqual(open_api.open_api_owner_id(client_key or ""), "staff_001")

    def test_open_api_owner_id_staff(self) -> None:
        key = open_api.client_key_for_staff("u123")
        self.assertEqual(open_api.open_api_owner_id(key), "u123")

    def test_open_api_message_source_tag(self) -> None:
        self.assertEqual(open_api.OPEN_API_MESSAGE_SOURCE_TAG, "API")

    def test_resolve_submit_identity_service_token_with_caller(self) -> None:
        body = {
            "message": "hi",
            "caller": {"work_id": "WB0111", "name": "陈墨", "momoid": "15350957303"},
        }
        service_key = open_api.client_key_from_token("shared-secret")
        ident = open_api.resolve_submit_identity(body, service_key)
        self.assertEqual(ident.owner_id, "WB0111")
        self.assertEqual(ident.owner_label, "陈墨")
        self.assertEqual(ident.session_client_key, open_api.client_key_for_staff("WB0111"))
        self.assertEqual(ident.caller_momoid, "15350957303")

    def test_resolve_submit_identity_personal_token_prefers_staff(self) -> None:
        staff_key = open_api.client_key_for_staff("32274159141215328")
        body = {
            "caller": {"work_id": "WB0111", "name": "陈墨"},
        }
        ident = open_api.resolve_submit_identity(body, staff_key)
        self.assertEqual(ident.owner_id, "32274159141215328")
        self.assertEqual(ident.owner_label, "陈墨")
        self.assertEqual(ident.session_client_key, staff_key)

    def test_resolve_submit_identity_personal_token_no_caller(self) -> None:
        staff_key = open_api.client_key_for_staff("32274159141215328")
        ident = open_api.resolve_submit_identity({"message": "hi"}, staff_key)
        self.assertEqual(ident.owner_id, "32274159141215328")
        self.assertEqual(ident.session_client_key, staff_key)

    def test_resolve_submit_identity_service_token_no_caller(self) -> None:
        service_key = open_api.client_key_from_token("shared-secret")
        ident = open_api.resolve_submit_identity({"message": "hi"}, service_key)
        self.assertEqual(ident.owner_id, open_api.open_api_owner_id(service_key))
        self.assertEqual(ident.session_client_key, service_key)

    def test_parse_open_api_attachments_merges_images(self) -> None:
        body = {
            "message": "看这张图",
            "images": [{"data_base64": "abc", "mime": "image/png", "name": "a.png"}],
            "attachments": [{"data_base64": "def", "mime": "text/plain", "name": "b.txt"}],
        }
        items = open_api.parse_open_api_submit_attachment_items(body)
        self.assertEqual(len(items), 2)

    def test_submit_title_hint_images_only(self) -> None:
        hint = open_api.submit_title_hint("", [{"name": "x.png"}])
        self.assertIn("附件", hint)


if __name__ == "__main__":
    unittest.main()
