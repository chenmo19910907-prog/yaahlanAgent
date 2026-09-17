#!/usr/bin/env python3
"""钉钉头像批量解析单测。"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

WEB_AGENT_DIR = Path(__file__).resolve().parent
GATEWAY_DIR = WEB_AGENT_DIR.parent / "dingtalk_gateway"
for path in (WEB_AGENT_DIR, GATEWAY_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import dingtalk_user_lookup as lookup  # noqa: E402
import dingtalk_user_profile as profile  # noqa: E402


class DingtalkUserAvatarsTest(unittest.TestCase):
    def setUp(self) -> None:
        profile.clear_profile_cache()

    @patch.object(lookup, "resolve_user_avatars")
    def test_resolve_user_avatars_batch(self, mock_resolve) -> None:
        mock_resolve.return_value = {"u1": "/api/dingtalk/avatar/u1"}
        result = lookup.resolve_user_avatars(["u1", "u2", "u1"], try_api=True)
        self.assertEqual(result, {"u1": "/api/dingtalk/avatar/u1"})

    @patch.object(lookup, "resolve_user_avatars")
    def test_enrich_sessions_with_avatars(self, mock_resolve) -> None:
        mock_resolve.return_value = {
            "32274159141215328": "/api/dingtalk/avatar/32274159141215328",
        }
        rows = [
            {
                "id": "s1",
                "source": "dingtalk",
                "dingtalk_owner_id": "32274159141215328",
            },
        ]
        lookup.enrich_sessions_with_avatars(rows)
        self.assertEqual(
            rows[0]["owner_avatar_url"],
            "/api/dingtalk/avatar/32274159141215328",
        )

    @patch("dingtalk_avatar_cache.local_avatar_url_for_staff")
    def test_resolve_user_avatars_from_cache_file(self, mock_local_url) -> None:
        mock_local_url.return_value = "/api/dingtalk/avatar/32274159141215328"
        with tempfile.TemporaryDirectory() as tmp:
            profile.PROFILE_CACHE_PATH = Path(tmp) / "profiles.json"
            profile.PROFILE_CACHE_PATH.write_text(
                json.dumps(
                    {
                        "32274159141215328": {
                            "displayName": "陈墨",
                            "avatarUrl": "https://cdn.example/chenmo.jpg",
                        }
                    },
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
            profile.clear_profile_cache()
            result = lookup.resolve_user_avatars(
                ["32274159141215328"],
                try_api=False,
            )
            self.assertEqual(
                result["32274159141215328"],
                "/api/dingtalk/avatar/32274159141215328",
            )


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(DingtalkUserAvatarsTest)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.wasSuccessful():
        print("[PASS] verify_dingtalk_user_avatars")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
