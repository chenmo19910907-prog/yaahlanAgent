#!/usr/bin/env python3
"""钉钉用户资料（头像）解析单测。"""

from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

GATEWAY_DIR = Path(__file__).resolve().parent
if str(GATEWAY_DIR) not in sys.path:
    sys.path.insert(0, str(GATEWAY_DIR))

import dingtalk_user_profile as profile  # noqa: E402


class DingtalkUserProfileTest(unittest.TestCase):
    def setUp(self) -> None:
        profile.clear_profile_cache()

    def test_format_sender_context_with_avatar(self) -> None:
        text = profile.format_sender_context(
            profile.UserProfile(
                staff_id="32274159141215328",
                display_name="陈墨",
                avatar_url="https://example.com/a.jpg",
            )
        )
        self.assertIn("陈墨", text)
        self.assertIn("32274159141215328", text)
        self.assertIn("https://example.com/a.jpg", text)

    def test_should_attach_sender_avatar(self) -> None:
        self.assertTrue(profile.should_attach_sender_avatar("现在你能获取到我的头像吗"))
        self.assertFalse(profile.should_attach_sender_avatar("查用户 100465989"))

    def test_resolve_user_profile_uses_cache(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profile.PROFILE_CACHE_PATH = Path(tmp) / "profiles.json"
            profile.PROFILE_CACHE_PATH.write_text(
                json.dumps(
                    {
                        "u1": {
                            "displayName": "缓存名",
                            "avatarUrl": "https://cdn.example/1.jpg",
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            profile.clear_profile_cache()
            resolved = profile.resolve_user_profile("u1", known_name="群昵称", try_api=False)
            self.assertEqual(resolved.display_name, "群昵称")
            self.assertEqual(resolved.avatar_url, "https://cdn.example/1.jpg")

    @patch.object(profile, "_fetch_profile_from_api")
    def test_resolve_user_profile_uses_cache_without_ttl_refresh(self, mock_fetch) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            profile.PROFILE_CACHE_PATH = Path(tmp) / "profiles.json"
            profile.PROFILE_CACHE_PATH.write_text(
                json.dumps(
                    {
                        "u3": {
                            "displayName": "旧名",
                            "avatarUrl": "https://cdn.example/old.jpg",
                            "updatedAt": str(time.time() - 99999),
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            profile.clear_profile_cache()
            resolved = profile.resolve_user_profile("u3", try_api=True)
            self.assertEqual(resolved.display_name, "旧名")
            self.assertEqual(resolved.avatar_url, "https://cdn.example/old.jpg")
            mock_fetch.assert_not_called()

    @patch.object(profile, "_fetch_profile_from_api")
    def test_resolve_user_profile_fetches_when_missing_avatar(self, mock_fetch) -> None:
        mock_fetch.return_value = profile.UserProfile(
            staff_id="u2",
            display_name="真实名",
            avatar_url="https://cdn.example/2.jpg",
        )
        with tempfile.TemporaryDirectory() as tmp:
            profile.PROFILE_CACHE_PATH = Path(tmp) / "profiles.json"
            profile.clear_profile_cache()
            resolved = profile.resolve_user_profile("u2", known_name="群昵称", try_api=True)
            self.assertEqual(resolved.display_name, "真实名")
            self.assertEqual(resolved.avatar_url, "https://cdn.example/2.jpg")
            mock_fetch.assert_called_once_with("u2")


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(DingtalkUserProfileTest)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.wasSuccessful():
        print("[PASS] verify_dingtalk_user_profile")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
