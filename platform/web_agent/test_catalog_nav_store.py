"""catalog_nav cap 节点解析（缺 catIndex 时按 registryId 补全）。"""

from __future__ import annotations

import json
import re
import sys
import unittest
from pathlib import Path

WEB_AGENT_DIR = Path(__file__).resolve().parent
if str(WEB_AGENT_DIR) not in sys.path:
    sys.path.insert(0, str(WEB_AGENT_DIR))

from catalog_nav_store import reconcile_nav_tree  # noqa: E402


def _load_catalog_modules() -> list[dict]:
    html = (WEB_AGENT_DIR.parent / "catalog.html").read_text(encoding="utf-8")
    match = re.search(r'<script id="catalog-data"[^>]*>(.*?)</script>', html, re.S)
    if not match:
        raise RuntimeError("catalog-data not found")
    data = json.loads(match.group(1))
    modules = data.get("modules")
    if not isinstance(modules, list):
        raise RuntimeError("invalid catalog modules")
    return modules


class CatalogNavCapResolveTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.modules = _load_catalog_modules()

    def test_missing_cat_index_resolved_by_registry(self) -> None:
        tree = [
            {
                "kind": "folder",
                "id": "test-folder",
                "label": "测试",
                "children": [
                    {
                        "kind": "cap",
                        "moduleId": "公会",
                        "label": "公会-强制修改等级",
                        "sourceId": "moa",
                        "registryId": "guild_force_update_trade_level",
                    }
                ],
            }
        ]
        out = reconcile_nav_tree(tree, self.modules, include_playbook=False)
        folder = next(n for n in out if n.get("id") == "test-folder")
        cap = folder["children"][0]
        self.assertEqual(cap["kind"], "cap")
        self.assertEqual(cap["catIndex"], 1)
        self.assertEqual(cap["registryId"], "guild_force_update_trade_level")

    def test_wrong_cat_index_corrected_by_registry(self) -> None:
        tree = [
            {
                "kind": "cap",
                "moduleId": "公会",
                "catIndex": 99,
                "label": "公会-强制修改等级",
                "sourceId": "moa",
                "registryId": "guild_force_update_trade_level",
            }
        ]
        out = reconcile_nav_tree(tree, self.modules, include_playbook=False)
        cap = next(n for n in out if n.get("kind") == "cap")
        self.assertEqual(cap["catIndex"], 1)


if __name__ == "__main__":
    unittest.main()
