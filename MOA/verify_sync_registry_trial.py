#!/usr/bin/env python3
"""sync_registry 须试跑验收后才入库新模板。"""

from __future__ import annotations

import json
import os
import sys
import tempfile
import unittest
from unittest import mock

_SCRIPTS = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _SCRIPTS)
sys.path.insert(0, os.path.join(_SCRIPTS, "scripts"))

import sync_registry as sync_mod  # noqa: E402
from moa.trial_verified import mark_template_trial_verified  # noqa: E402


class TestSyncRegistryTrialGate(unittest.TestCase):
    def test_unverified_template_not_synced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            templates = os.path.join(tmp, "templates")
            config = os.path.join(tmp, "config")
            os.makedirs(templates)
            os.makedirs(config)
            tpl = "试跑门控-未验收.json"
            with open(os.path.join(templates, tpl), "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "type": "moa",
                        "url": "/service/demo",
                        "method": "demoMethod",
                        "_registry": {"name": "试跑门控-未验收"},
                    },
                    f,
                )
            registry = {"items": []}
            reg_path = os.path.join(config, "registry.json")
            verified_path = os.path.join(config, "trial_verified_templates.json")
            with open(reg_path, "w", encoding="utf-8") as f:
                json.dump(registry, f)

            with (
                mock.patch.object(sync_mod, "registry_path", return_value=reg_path),
                mock.patch.object(sync_mod, "templates_dir", return_value=templates),
                mock.patch("moa.trial_verified._verified_path", return_value=verified_path),
            ):
                added = sync_mod.sync_registry(dry_run=True)
            self.assertEqual(added, [])

    def test_verified_template_synced(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            templates = os.path.join(tmp, "templates")
            config = os.path.join(tmp, "config")
            os.makedirs(templates)
            os.makedirs(config)
            tpl = "试跑门控-已验收.json"
            with open(os.path.join(templates, tpl), "w", encoding="utf-8") as f:
                json.dump(
                    {
                        "type": "moa",
                        "url": "/service/demo",
                        "method": "demoMethod",
                        "_registry": {"name": "试跑门控-已验收"},
                    },
                    f,
                )
            registry = {"items": []}
            reg_path = os.path.join(config, "registry.json")
            verified_path = os.path.join(config, "trial_verified_templates.json")
            with open(reg_path, "w", encoding="utf-8") as f:
                json.dump(registry, f)
            with mock.patch("moa.trial_verified._verified_path", return_value=verified_path):
                mark_template_trial_verified(tpl)

            with (
                mock.patch.object(sync_mod, "registry_path", return_value=reg_path),
                mock.patch.object(sync_mod, "templates_dir", return_value=templates),
                mock.patch("moa.trial_verified._verified_path", return_value=verified_path),
            ):
                added = sync_mod.sync_registry(dry_run=True, template=tpl)
            self.assertEqual(len(added), 1)
            self.assertEqual(added[0]["name"], "试跑门控-已验收")


if __name__ == "__main__":
    raise SystemExit(unittest.main())
