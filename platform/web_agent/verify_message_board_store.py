#!/usr/bin/env python3
"""message_board_store 单测。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path

WEB_AGENT_DIR = Path(__file__).resolve().parent
if str(WEB_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_AGENT_DIR))

from message_board_store import (  # noqa: E402
    create_message,
    delete_message,
    list_messages_for_viewer,
    load_message_board,
    normalize_create_payload,
    normalize_guest_id,
)


class MessageBoardStoreTest(unittest.TestCase):
    def test_user_only_sees_own_messages(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "message_board.json"
            create_message(
                staff_id="user_a",
                display_name="用户A",
                content="A 的留言",
                show_real_name=True,
                path=path,
            )
            create_message(
                staff_id="user_b",
                display_name="用户B",
                content="B 的留言",
                show_real_name=False,
                path=path,
            )

            mine = list_messages_for_viewer(
                viewer_staff_id="user_a",
                is_admin=False,
                path=path,
            )
            self.assertEqual(len(mine), 1)
            self.assertEqual(mine[0]["content"], "A 的留言")
            self.assertTrue(mine[0]["isMine"])

            admin_view = list_messages_for_viewer(
                viewer_staff_id="admin",
                is_admin=True,
                path=path,
            )
            self.assertEqual(len(admin_view), 2)
            labels = {item["authorLabel"] for item in admin_view}
            self.assertIn("用户A", labels)
            self.assertIn("匿名", labels)

    def test_anonymous_own_label(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "message_board.json"
            create_message(
                staff_id="user_a",
                display_name="用户A",
                content="匿名留言",
                show_real_name=False,
                path=path,
            )
            mine = list_messages_for_viewer(
                viewer_staff_id="user_a",
                is_admin=False,
                path=path,
            )
            self.assertEqual(mine[0]["authorLabel"], "匿名（我）")

    def test_normalize_create_payload(self) -> None:
        self.assertIsNone(normalize_create_payload(None))
        self.assertIsNone(normalize_create_payload({"content": "  "}))
        parsed = normalize_create_payload({"content": " hello ", "showRealName": True})
        self.assertEqual(parsed, ("hello", True))

    def test_load_empty(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "missing.json"
            self.assertEqual(load_message_board(path), {"messages": []})

    def test_delete_own_message(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "message_board.json"
            created = create_message(
                staff_id="user_a",
                display_name="用户A",
                content="待删除",
                show_real_name=False,
                path=path,
            )
            removed = delete_message(
                message_id=created["id"],
                viewer_staff_id="user_a",
                is_admin=False,
                path=path,
            )
            self.assertTrue(removed)
            self.assertEqual(
                list_messages_for_viewer(viewer_staff_id="user_a", is_admin=False, path=path),
                [],
            )

    def test_delete_forbidden_for_other_user(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "message_board.json"
            created = create_message(
                staff_id="user_a",
                display_name="用户A",
                content="不可删",
                show_real_name=False,
                path=path,
            )
            with self.assertRaises(PermissionError):
                delete_message(
                    message_id=created["id"],
                    viewer_staff_id="user_b",
                    is_admin=False,
                    path=path,
                )

    def test_admin_can_delete_any(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "message_board.json"
            created = create_message(
                staff_id="user_a",
                display_name="用户A",
                content="管理员删除",
                show_real_name=False,
                path=path,
            )
            removed = delete_message(
                message_id=created["id"],
                viewer_staff_id="admin",
                is_admin=True,
                path=path,
            )
            self.assertTrue(removed)

    def test_normalize_guest_id(self) -> None:
        self.assertIsNone(normalize_guest_id(""))
        self.assertIsNone(normalize_guest_id("guest_bad"))
        valid = "guest_" + "a" * 32
        self.assertEqual(normalize_guest_id(valid), valid)

    def test_can_delete_flag(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "message_board.json"
            create_message(
                staff_id="user_a",
                display_name="用户A",
                content="我的",
                show_real_name=False,
                path=path,
            )
            mine = list_messages_for_viewer(viewer_staff_id="user_a", is_admin=False, path=path)
            self.assertTrue(mine[0]["canDelete"])
            other = list_messages_for_viewer(viewer_staff_id="user_b", is_admin=False, path=path)
            self.assertEqual(other, [])

    def test_guest_author_label_and_delete(self) -> None:
        guest_id = "guest_" + "c" * 32
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "message_board.json"
            created = create_message(
                staff_id=guest_id,
                display_name="访客",
                content="访客反馈",
                show_real_name=False,
                path=path,
            )
            mine = list_messages_for_viewer(viewer_staff_id=guest_id, is_admin=False, path=path)
            self.assertEqual(len(mine), 1)
            self.assertEqual(mine[0]["authorLabel"], "访客")
            self.assertTrue(mine[0]["isGuestAuthor"])
            self.assertTrue(mine[0]["canDelete"])
            other_guest = "guest_" + "d" * 32
            self.assertEqual(
                list_messages_for_viewer(viewer_staff_id=other_guest, is_admin=False, path=path),
                [],
            )
            removed = delete_message(
                message_id=created["id"],
                viewer_staff_id=guest_id,
                is_admin=False,
                path=path,
            )
            self.assertTrue(removed)


if __name__ == "__main__":
    unittest.main()
