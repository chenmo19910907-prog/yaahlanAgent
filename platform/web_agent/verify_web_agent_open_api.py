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


if __name__ == "__main__":
    unittest.main()
