#!/usr/bin/env python3
"""worker_process_hygiene 单元测试。"""

from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

WEB_AGENT_DIR = Path(__file__).resolve().parent
GATEWAY_DIR = WEB_AGENT_DIR.parent / "dingtalk_gateway"
sys.path.insert(0, str(GATEWAY_DIR))
sys.path.insert(0, str(WEB_AGENT_DIR))

from web_run_store import RUN_STATUS_DONE, RUN_STATUS_RUNNING, RunMeta, WebRunStore  # noqa: E402

import worker_process_hygiene as hygiene  # noqa: E402


class WorkerProcessHygieneTests(unittest.TestCase):
    def test_parse_run_id_from_cmdline(self) -> None:
        cmd = "/venv/bin/python3 run_worker.py --run-id abc123def"
        self.assertEqual(hygiene._parse_run_id_from_cmdline(cmd), "abc123def")

    def test_etime_exceeds(self) -> None:
        self.assertFalse(hygiene._etime_exceeds("01:30", 240.0))
        self.assertTrue(hygiene._etime_exceeds("05:00", 240.0))
        self.assertTrue(hygiene._etime_exceeds("1-02:00:00", 240.0))

    def test_is_orphan_when_run_done(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = WebRunStore(root=Path(tmp) / "runs")
            meta = RunMeta(
                run_id="r1",
                session_id="s1",
                message="hi",
                display_message="hi",
                model="",
                enabled_external_agents=[],
                author_id="",
                author_label="",
                image_paths=[],
                file_paths=[],
                attachment_names=[],
                worker_pid=100,
                status=RUN_STATUS_DONE,
                started_at=1.0,
            )
            store.create_run(meta)
            self.assertTrue(
                hygiene._is_orphan_worker("r1", 200, meta, store=store),
            )

    def test_is_not_orphan_when_pid_matches(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = WebRunStore(root=Path(tmp) / "runs")
            meta = RunMeta(
                run_id="r2",
                session_id="s2",
                message="hi",
                display_message="hi",
                model="",
                enabled_external_agents=[],
                author_id="",
                author_label="",
                image_paths=[],
                file_paths=[],
                attachment_names=[],
                worker_pid=4242,
                status=RUN_STATUS_RUNNING,
                started_at=1.0,
            )
            store.create_run(meta)
            self.assertFalse(
                hygiene._is_orphan_worker("r2", 4242, meta, store=store),
            )

    def test_sweep_orphan_kills_stale_pid(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            store = WebRunStore(root=Path(tmp) / "runs")
            meta = RunMeta(
                run_id="r3",
                session_id="s3",
                message="hi",
                display_message="hi",
                model="",
                enabled_external_agents=[],
                author_id="",
                author_label="",
                image_paths=[],
                file_paths=[],
                attachment_names=[],
                worker_pid=50,
                status=RUN_STATUS_DONE,
                started_at=1.0,
            )
            store.create_run(meta)
            with mock.patch.object(
                hygiene,
                "iter_run_worker_processes",
                return_value=[(999, "r3")],
            ), mock.patch.object(hygiene, "_terminate_tree") as kill_mock, mock.patch(
                "web_run_store.get_run_store",
                return_value=store,
            ):
                count = hygiene.sweep_orphan_run_workers(kill=True)
            self.assertEqual(count, 1)
            kill_mock.assert_called_once_with(999)


if __name__ == "__main__":
    unittest.main()
