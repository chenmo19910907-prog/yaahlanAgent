# -*- coding: utf-8 -*-
"""pytest 执行任务调度（单任务队列，避免 MOA 并发冲突）。"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
import uuid
from datetime import datetime
from pathlib import Path

from web.config import JOBS_DIR, PROJECT_ROOT, suite_by_id
from web.models import RunJobStatus
from web.services.cases import pytest_node_id, validate_case_names


class JobRunner:
    def __init__(self):
        self._lock = threading.Lock()
        self._jobs: dict[str, RunJobStatus] = {}
        self._running_job_id: str | None = None
        JOBS_DIR.mkdir(parents=True, exist_ok=True)

    @property
    def running_job_id(self) -> str | None:
        with self._lock:
            return self._running_job_id

    def list_jobs(self, limit: int = 30) -> list[RunJobStatus]:
        with self._lock:
            jobs = list(self._jobs.values())
        jobs.sort(key=lambda j: j.started_at or "", reverse=True)
        return jobs[: max(1, limit)]

    def get_job(self, job_id: str) -> RunJobStatus | None:
        with self._lock:
            return self._jobs.get(job_id)

    def submit(self, suite_id: str, case_names: list[str], generate_report: bool = True) -> RunJobStatus:
        suite = suite_by_id(suite_id)
        if not suite:
            raise ValueError(f"未知套件: {suite_id}")
        invalid = validate_case_names(suite_id, case_names)
        if invalid:
            raise ValueError(f"未知用例: {', '.join(invalid)}")

        with self._lock:
            if self._running_job_id:
                running = self._jobs.get(self._running_job_id)
                raise RuntimeError(
                    f"已有任务执行中: {self._running_job_id} ({running.suite_name if running else ''})"
                )
            job_id = uuid.uuid4().hex[:12]
            job = RunJobStatus(
                job_id=job_id,
                suite_id=suite.id,
                suite_name=suite.name,
                case_names=list(case_names),
                status="pending",
                log_url=f"/api/jobs/{job_id}/log",
            )
            self._jobs[job_id] = job
            self._running_job_id = job_id

        thread = threading.Thread(
            target=self._run_job,
            args=(job_id, suite, case_names, generate_report),
            daemon=True,
        )
        thread.start()
        return job

    def _run_job(self, job_id: str, suite, case_names: list[str], generate_report: bool) -> None:
        started = datetime.now()
        log_path = JOBS_DIR / f"{job_id}.log"
        meta_path = JOBS_DIR / f"{job_id}.json"
        pytest_args = [sys.executable, "-m", "pytest", "-v", "--tb=short"]
        # 当前 conftest 报告钩子仅绑定 cycle_salary 用例表
        effective_report = generate_report and suite.id == "cycle_salary"
        if effective_report:
            pytest_args.append("--salary-report")

        if case_names:
            for name in case_names:
                pytest_args.append(pytest_node_id(suite, name))
        else:
            pytest_args.append(suite.test_module)

        command = " ".join(pytest_args)
        env = os.environ.copy()
        if effective_report:
            env["GENERATE_SALARY_REPORT"] = "1"

        self._update_job(
            job_id,
            status="running",
            started_at=started.strftime("%Y-%m-%d %H:%M:%S"),
            command=command,
        )

        exit_code = 1
        error_message = None
        try:
            with open(log_path, "w", encoding="utf-8") as log_file:
                log_file.write(f"# Job {job_id}\n# Command: {command}\n# Started: {started.isoformat()}\n\n")
                log_file.flush()
                proc = subprocess.Popen(
                    pytest_args,
                    cwd=str(PROJECT_ROOT),
                    stdout=log_file,
                    stderr=subprocess.STDOUT,
                    env=env,
                )
                exit_code = proc.wait()
        except OSError as exc:
            exit_code = 1
            error_message = str(exc)

        finished = datetime.now()
        duration = (finished - started).total_seconds()
        status = "passed" if exit_code == 0 else "failed"
        if error_message:
            status = "error"

        report_html_url, report_md_url = self._detect_latest_report(suite.report_dir, started.timestamp())

        result = self._update_job(
            job_id,
            status=status,
            finished_at=finished.strftime("%Y-%m-%d %H:%M:%S"),
            exit_code=exit_code,
            duration_seconds=round(duration, 2),
            report_html_url=report_html_url,
            report_md_url=report_md_url,
            error_message=error_message,
        )
        meta_path.write_text(json.dumps(result.model_dump(), ensure_ascii=False, indent=2), encoding="utf-8")

        with self._lock:
            if self._running_job_id == job_id:
                self._running_job_id = None

    def _detect_latest_report(self, report_dir: str, since_ts: float) -> tuple[str | None, str | None]:
        abs_dir = PROJECT_ROOT / report_dir
        if not abs_dir.is_dir():
            return None, None
        html_path = None
        md_path = None
        for path in abs_dir.iterdir():
            if not path.is_file() or path.stat().st_mtime < since_ts - 5:
                continue
            suffix = path.suffix.lower()
            rel = path.relative_to(PROJECT_ROOT).as_posix()
            if suffix == ".html":
                html_path = f"/api/reports/files/{rel}"
            elif suffix == ".md":
                md_path = f"/api/reports/files/{rel}"
        return html_path, md_path

    def _update_job(self, job_id: str, **fields) -> RunJobStatus:
        with self._lock:
            job = self._jobs[job_id]
            data = job.model_dump()
            data.update({k: v for k, v in fields.items() if v is not None})
            updated = RunJobStatus(**data)
            self._jobs[job_id] = updated
            return updated

    def read_log(self, job_id: str, tail_lines: int = 400) -> str:
        log_path = JOBS_DIR / f"{job_id}.log"
        if not log_path.is_file():
            return ""
        lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
        if tail_lines > 0 and len(lines) > tail_lines:
            lines = ["... (日志截断，仅显示末尾) ..."] + lines[-tail_lines:]
        return "\n".join(lines)


job_runner = JobRunner()
