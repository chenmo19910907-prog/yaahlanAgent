#!/usr/bin/env python3
"""admin_call_labels：Admin 路径 → registry 中文标题。"""

from __future__ import annotations

import unittest
from pathlib import Path

WEB_AGENT_DIR = Path(__file__).resolve().parent
if str(WEB_AGENT_DIR) not in __import__("sys").path:
    __import__("sys").path.insert(0, str(WEB_AGENT_DIR))

from admin_call_labels import (  # noqa: E402
    admin_call_meta,
    admin_operation_label_from_entry,
)


class AdminCallLabelsTests(unittest.TestCase):
    def test_banner_list_paths_use_registry_name(self) -> None:
        body = {"bannerId": "", "page": 1, "perPage": 10, "status": -1}
        for path in (
            "/admin/banner/getBannerList",
            "/yaahlan/cms/backend/banner/getBannerList",
        ):
            op, _, _, _ = admin_call_meta(
                f"https://yaahlan-admin-alpha.wemomo.com{path}",
                body,
                http_method="POST",
            )
            self.assertEqual(op, "Admin 活动-查询Banner列表", path)

    def test_repair_raw_path_operation_on_list(self) -> None:
        label = admin_operation_label_from_entry(
            service_url="/admin/banner/getBannerList",
            operation="Admin /admin/banner/getBannerList",
            params_summary="bannerId=，page=1，perPage=5，status=-1",
        )
        self.assertEqual(label, "Admin 活动-查询Banner列表")

    def test_user_detail_still_semantic(self) -> None:
        op, account, params, _ = admin_call_meta(
            "https://admin/user/queryUserDetail",
            {"userId": "100465989"},
            http_method="POST",
        )
        self.assertEqual(op, "Admin 查询用户 100465989 详情")
        self.assertEqual(account, "100465989")
        self.assertIn("userId=100465989", params)


if __name__ == "__main__":
    unittest.main()
