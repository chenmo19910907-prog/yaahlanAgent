#!/usr/bin/env python3
import unittest

from version_case_workbook_naming import (
    build_version_case_workbook_title,
    compose_feature_overview,
    parse_feature_overview_from_rows,
    proposed_workbook_title,
    summarize_name_parts,
    workbook_name_has_feature_suffix,
)


class VersionCaseWorkbookNamingTests(unittest.TestCase):
    def test_overview_from_sheet1(self) -> None:
        rows = [["版本", "2.6.4"], ["功能概况", "家族 PK、提款机"]]
        self.assertEqual(parse_feature_overview_from_rows(rows), "家族 PK、提款机")

    def test_proposed_title(self) -> None:
        title = proposed_workbook_title(
            "2.6.4版本用例",
            sheet_names=["Sheet1", "家族PK", "提款机"],
            sheet1_rows=[["功能概况：", "家族 PK、提款机"]],
        )
        self.assertEqual(title, "2.6.4版本用例（家族 PK、提款机）")

    def test_skip_already_suffixed(self) -> None:
        self.assertTrue(workbook_name_has_feature_suffix("2.5.0版本用例（家族活动）"))
        self.assertIsNone(
            proposed_workbook_title("2.5.0版本用例（家族活动）", sheet_names=["A"])
        )

    def test_fallback_sheet_names(self) -> None:
        ov = compose_feature_overview(sheet_names=["Sheet1", "家族PK", "优化需求"])
        self.assertEqual(ov, "家族PK")

    def test_no_empty_parens(self) -> None:
        self.assertIsNone(
            proposed_workbook_title("2.6.5版本用例.axls", sheet_names=["Sheet1"])
        )

    def test_summarize_shared_prefix(self) -> None:
        sheets = [
            "跨房PK吃鸡-PK面板",
            "跨房PK吃鸡-房间展示",
            "跨房PK吃鸡-箱子掉落领奖",
            "跨房PK-老功能回测",
            "新用户行为引导",
        ]
        ov = compose_feature_overview(sheet_names=["Sheet1", *sheets])
        self.assertIn("跨房PK吃鸡", ov)
        self.assertNotIn("跨房PK吃鸡-PK面板", ov)
        self.assertIn("跨房PK-老功能回测", ov)
        self.assertLessEqual(len(ov), 80)
        self.assertEqual(
            summarize_name_parts(sheets[:3]),
            ["跨房PK吃鸡"],
        )


if __name__ == "__main__":
    unittest.main()
