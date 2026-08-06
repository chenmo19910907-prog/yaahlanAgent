#!/usr/bin/env python3
"""多项目：AGENT_PROJECT=example 与 yaahlan 行为差异冒烟。"""

from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

PLATFORM_DIR = Path(__file__).resolve().parents[1]
REPO_ROOT = PLATFORM_DIR.parent
sys.path.insert(0, str(PLATFORM_DIR))


class SecondProjectTest(unittest.TestCase):
    def _switch(self, project_id: str) -> None:
        os.environ["AGENT_PROJECT"] = project_id
        os.environ["PROJECT"] = project_id
        from project.loader import get_project_config, web_agent_title, web_login_pattern

        get_project_config.cache_clear()
        web_login_pattern.cache_clear()

    def tearDown(self) -> None:
        os.environ.pop("AGENT_PROJECT", None)
        os.environ.pop("PROJECT", None)
        from project.loader import get_project_config, web_login_pattern

        get_project_config.cache_clear()
        web_login_pattern.cache_clear()

    def test_example_project_branding_differs(self) -> None:
        from project.loader import web_agent_title

        self._switch("yaahlan")
        yaahlan_title = web_agent_title()
        self._switch("example")
        example_title = web_agent_title()
        self.assertIn("Yaahlan", yaahlan_title)
        self.assertIn("Example", example_title)
        self.assertNotEqual(yaahlan_title, example_title)

    def test_example_temporary_testcase_path(self) -> None:
        from project.loader import temporary_testcase_dir

        self._switch("example")
        path = temporary_testcase_dir()
        self.assertEqual(path, REPO_ROOT / "projects/example/temporary_testcase")

    def test_example_admin_config_isolated(self) -> None:
        from project.loader import admin_config_path, testcase_kb_root

        self._switch("example")
        admin_cfg = admin_config_path()
        kb = testcase_kb_root()
        self.assertEqual(admin_cfg, REPO_ROOT / "projects/example/config/admin.json")
        self.assertTrue(admin_cfg.is_file())
        self.assertEqual(kb, REPO_ROOT / "projects/example/knowledge/testcase-kb")

    def test_moa_library_respects_project(self) -> None:
        sys.path.insert(0, str(REPO_ROOT / "MOA"))
        self._switch("example")
        from moa.project_paths import moa_template, moa_service_url

        tpl = moa_template("钻石-查询余额.json")
        self.assertTrue(tpl.is_file())
        url = moa_service_url("cpMoa", "/fallback")
        self.assertIn("cp-moa", url)

    def test_example_moa_runtime_stays_shared(self) -> None:
        from project.repo_paths import moa_execute_path, moa_template, moa_templates_dir

        self._switch("example")
        self.assertEqual(
            moa_execute_path(),
            REPO_ROOT / "MOA/moa_execute.py",
        )
        self.assertTrue(moa_execute_path().is_file())
        self.assertEqual(
            moa_templates_dir(),
            REPO_ROOT / "projects/example/moa/templates",
        )
        self.assertTrue(moa_template("钻石-查询余额.json").is_file())

    def test_catalog_module_registry_resolution(self) -> None:
        from project.catalog_paths import module_registry_path

        self._switch("example")
        moa_reg = module_registry_path("moa", "MOA/config/registry.json")
        self.assertEqual(moa_reg, REPO_ROOT / "projects/example/moa/config/registry.json")
        self.assertTrue(moa_reg.is_file())
        admin_reg = module_registry_path("admin", "Admin/config/registry.json")
        self.assertEqual(admin_reg, REPO_ROOT / "projects/example/config/admin-registry.json")
        self.assertTrue(admin_reg.is_file())
        wf_reg = module_registry_path("workflow", "workflow/config/registry.json")
        self.assertTrue(wf_reg.is_file())
        gen_reg = module_registry_path("moa-generative", "MOA-generative/config/registry.json")
        self.assertTrue(gen_reg.is_file())
        tunnel_reg = module_registry_path("tunnel", "Tunnel/config/registry.json")
        self.assertTrue(tunnel_reg.is_file())

    def test_example_workflow_and_generative_paths(self) -> None:
        from project.loader import moa_generative_root, moa_registry_path, workflow_root
        from project.repo_paths import workflow_execute_path, workflow_runtime_dir

        self._switch("example")
        self.assertEqual(workflow_root(), REPO_ROOT / "projects/example/workflow")
        self.assertEqual(moa_generative_root(), REPO_ROOT / "projects/example/moa-generative")
        self.assertEqual(
            moa_registry_path(),
            REPO_ROOT / "projects/example/moa/config/registry.json",
        )
        self.assertEqual(workflow_execute_path(), REPO_ROOT / "workflow/workflow_execute.py")
        self.assertTrue(workflow_execute_path().is_file())
        self.assertEqual(workflow_runtime_dir(), REPO_ROOT / "workflow")

    def test_moa_script_paths_import(self) -> None:
        sys.path.insert(0, str(REPO_ROOT / "MOA" / "scripts"))
        self._switch("example")
        from moa_script_paths import (
            moa_execute_path,
            moa_template,
            moa_template_repo_rel,
            moa_templates_repo_rel,
        )

        self.assertTrue(moa_template("家族PK-清除匹配数据.json").is_file())
        self.assertTrue(moa_execute_path().is_file())
        self.assertEqual(moa_templates_repo_rel(), "projects/example/moa/templates")
        self.assertEqual(
            moa_template_repo_rel("钻石-查询余额.json"),
            "projects/example/moa/templates/钻石-查询余额.json",
        )

    def test_runtime_env_merge(self) -> None:
        from project.runtime_env import ensure_project_env, merge_project_env

        ensure_project_env(project_id="example")
        env = merge_project_env()
        self.assertEqual(env.get("AGENT_PROJECT"), "example")

    def test_example_adb_scripts_root(self) -> None:
        from project.loader import adb_autotest_root, adb_scripts_root

        self._switch("yaahlan")
        self.assertEqual(adb_scripts_root(), REPO_ROOT / "adb/录制脚本")
        self.assertEqual(adb_autotest_root(), REPO_ROOT / "adb/自动化用例")

        self._switch("example")
        self.assertEqual(
            adb_scripts_root(),
            REPO_ROOT / "projects/example/adb/scripts",
        )
        self.assertEqual(
            adb_autotest_root(),
            REPO_ROOT / "projects/example/adb/autotest",
        )

    def test_adb_resolve_app_target_from_project(self) -> None:
        sys.path.insert(0, str(REPO_ROOT / "adb"))
        self._switch("example")
        from adb.apps import resolve_app_target

        target = resolve_app_target()
        self.assertEqual(target["package"], "com.immomo.biz.yaahlan")

        self._switch("yaahlan")
        yaahlan = resolve_app_target()
        self.assertEqual(yaahlan["package"], "com.immomo.biz.yaahlan")

    def test_adb_script_paths_import(self) -> None:
        sys.path.insert(0, str(REPO_ROOT / "adb" / "scripts"))
        self._switch("example")
        from adb_script_paths import adb_scripts_root

        root = adb_scripts_root()
        self.assertTrue((root / "索引.json").is_file())


if __name__ == "__main__":
    raise SystemExit(unittest.main())
