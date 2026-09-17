#!/usr/bin/env python3
"""钉钉头像本地缓存单测。"""

from __future__ import annotations

import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

GATEWAY_DIR = Path(__file__).resolve().parent
WEB_AGENT_DIR = GATEWAY_DIR.parent / "web_agent"
for path in (GATEWAY_DIR, WEB_AGENT_DIR):
    if str(path) not in sys.path:
        sys.path.insert(0, str(path))

import dingtalk_avatar_cache as cache  # noqa: E402
import dingtalk_user_lookup as lookup  # noqa: E402
import dingtalk_user_profile as profile  # noqa: E402


class DingtalkAvatarCacheTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        tmp = Path(self._tmpdir.name)
        cache.AVATAR_CACHE_DIR = tmp / "avatar_cache"
        profile.PROFILE_CACHE_PATH = tmp / "profiles.json"
        profile.clear_profile_cache()
        cache._refresh_last_attempt.clear()
        cache._refresh_inflight.clear()

    def tearDown(self) -> None:
        self._tmpdir.cleanup()
        profile.clear_profile_cache()

    @patch.object(cache, "_download_avatar")
    def test_ensure_avatar_cached_writes_file(self, mock_download) -> None:
        mock_download.return_value = (b"\xff\xd8\xff", "image/jpeg")
        path = cache.ensure_avatar_cached("u1", "https://cdn.example/1.jpg")
        self.assertIsNotNone(path)
        assert path is not None
        self.assertTrue(path.is_file())
        again = cache.ensure_avatar_cached("u1", "https://cdn.example/1.jpg")
        self.assertEqual(path, again)
        mock_download.assert_called_once()

    @patch.object(cache, "_download_avatar")
    def test_local_avatar_url_for_staff_uses_mtime(self, mock_download) -> None:
        mock_download.return_value = (b"\xff\xd8\xff", "image/jpeg")
        cache.ensure_avatar_cached("u1", "https://cdn.example/1.jpg")
        url = cache.local_avatar_url_for_staff("u1", "https://cdn.example/1.jpg")
        self.assertTrue(url.startswith("/api/dingtalk/avatar/u1?v="))

    @patch.object(profile, "refresh_user_avatar_cache")
    def test_touch_avatar_cache_debounces(self, mock_refresh) -> None:
        with patch.object(cache, "avatar_refresh_debounce_sec", return_value=600):
            cache.touch_avatar_cache("u1", background=False)
            cache.touch_avatar_cache("u1", background=False)
        self.assertEqual(mock_refresh.call_count, 1)

    def _transparent_png_bytes(self) -> bytes:
        from PIL import Image
        import io

        buf = io.BytesIO()
        Image.new("RGBA", (8, 8), (0, 0, 0, 0)).save(buf, format="PNG")
        return buf.getvalue()

    def test_placeholder_avatar_is_rejected(self) -> None:
        transparent_png = self._transparent_png_bytes()
        self.assertTrue(cache._is_placeholder_avatar_image(transparent_png, "image/png"))
        self.assertFalse(cache._is_placeholder_avatar_image(b"\xff\xd8\xff\xe0", "image/jpeg"))

    @patch.object(cache, "_download_avatar")
    def test_ensure_avatar_cached_skips_placeholder(self, mock_download) -> None:
        transparent_png = self._transparent_png_bytes()
        mock_download.return_value = (transparent_png, "image/png")
        path = cache.ensure_avatar_cached("u-placeholder", "https://cdn.example/p.png")
        self.assertIsNone(path)
        self.assertFalse((cache.AVATAR_CACHE_DIR / "u-placeholder.png").is_file())

    @patch.object(profile, "resolve_user_profile")
    @patch.object(cache, "local_avatar_url_for_staff")
    def test_resolve_user_avatars_returns_local_url(
        self,
        mock_local_url,
        mock_resolve,
    ) -> None:
        mock_resolve.return_value = profile.UserProfile(
            staff_id="u1",
            display_name="甲",
            avatar_url="https://cdn.example/1.jpg",
        )
        mock_local_url.return_value = "/api/dingtalk/avatar/u1"
        result = lookup.resolve_user_avatars(["u1"], try_api=True)
        self.assertEqual(result, {"u1": "/api/dingtalk/avatar/u1"})


def main() -> int:
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(DingtalkAvatarCacheTest)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if result.wasSuccessful():
        print("[PASS] verify_dingtalk_avatar_cache")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
