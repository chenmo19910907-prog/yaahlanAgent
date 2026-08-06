#!/usr/bin/env python3
"""多项目配置 loader 单测。"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

PLATFORM_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = PLATFORM_DIR.parent
sys.path.insert(0, str(PLATFORM_DIR))

from project.loader import (  # noqa: E402
    admin_config_path,
    app_id,
    catalog_export_basename,
    cmdb_instances_url,
    gateway_agent_name,
    get_project_config,
    get_project_id,
    gift_cp_love_config_path,
    list_projects,
    load_sources,
    moa_templates_dir,
    moa_thresholds_path,
    mse_config_path,
    online_config_path,
    risk_config_path,
    sources_path,
    testcase_kb_root,
    tunnel_mock_base_url,
    web_login_pattern,
    web_login_phrase,
)


class ProjectLoaderTest(unittest.TestCase):
    def setUp(self) -> None:
        os.environ.pop("AGENT_PROJECT", None)
        os.environ.pop("PROJECT", None)
        get_project_config.cache_clear()
        web_login_pattern.cache_clear()

    def test_default_project_is_yaahlan(self) -> None:
        self.assertEqual(get_project_id(), "yaahlan")
        cfg = get_project_config()
        self.assertEqual(cfg["id"], "yaahlan")
        title = cfg["agent"]["title"]
        self.assertIn("Yaahlan", title)

    def test_web_login_phrase_and_pattern(self) -> None:
        phrase = web_login_phrase()
        self.assertIn("Yaahlan", phrase)
        pat = web_login_pattern()
        self.assertTrue(pat.match("  请求访问 Yaahlan 智能工具 Agent  "))
        self.assertFalse(pat.match("网页登录"))

    def test_sources_path_points_to_project(self) -> None:
        path = sources_path()
        self.assertEqual(path, REPO_ROOT / "projects/yaahlan/sources.json")
        sources = load_sources()
        self.assertIsInstance(sources.get("modules"), list)
        self.assertGreater(len(sources["modules"]), 0)

    def test_gateway_and_catalog_branding(self) -> None:
        self.assertIn("Yaahlan", gateway_agent_name())
        self.assertIn("Yaahlan", catalog_export_basename())

    def test_list_projects_includes_yaahlan(self) -> None:
        projects = list_projects()
        self.assertIn("yaahlan", projects)
        self.assertNotIn("_template", projects)

    def test_module_config_paths(self) -> None:
        self.assertEqual(admin_config_path(), REPO_ROOT / "Admin/config.json")
        self.assertEqual(online_config_path(), REPO_ROOT / "online/config.json")
        self.assertEqual(moa_thresholds_path(), REPO_ROOT / "MOA/config/thresholds.json")
        self.assertEqual(moa_templates_dir(), REPO_ROOT / "MOA/templates")
        self.assertEqual(mse_config_path(), REPO_ROOT / "MSE/config.json")
        self.assertEqual(risk_config_path(), REPO_ROOT / "Risk/config.json")
        self.assertEqual(gift_cp_love_config_path(), REPO_ROOT / "Gift/config/cp_love_gift.json")
        self.assertEqual(testcase_kb_root(), REPO_ROOT / "testcase-kb")
        self.assertEqual(app_id(), 2005)
        self.assertIn("yaahlan-web", cmdb_instances_url())
        self.assertIn("yaahlan.fun", tunnel_mock_base_url())

    def test_api_endpoints(self) -> None:
        from project.loader import (
            api_endpoint,
            api_family_pk_h5_path,
            api_stage_gateway_base,
            stage_gateway_url,
        )

        self.assertIn("melon-gateway", api_stage_gateway_base())
        self.assertIn("wallet-api", api_endpoint("diamondHistoryService", ""))
        self.assertIn("family-pk", api_family_pk_h5_path())
        url = stage_gateway_url("anchorList", "/yaahlan/cms/anchor/anchorList/anchorList")
        self.assertIn("anchorList", url)

    def test_repo_paths(self) -> None:
        from project.repo_paths import (
            admin_execute_path,
            moa_execute_path,
            moa_template,
        )

        self.assertTrue(moa_execute_path().is_file())
        self.assertTrue(admin_execute_path().is_file())
        self.assertTrue(moa_template("钻石-查询余额.json").is_file())


if __name__ == "__main__":
    raise SystemExit(unittest.main())
