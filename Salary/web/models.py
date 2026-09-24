# -*- coding: utf-8 -*-
from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class CaseSummary(BaseModel):
    case_name: str
    case_name_cn: str = ""
    case_name_en: str = ""
    scenario_desc: str = ""
    case_purpose: str = ""
    anchor_id: str | None = None
    period_start: str | None = None


class SuiteSummary(BaseModel):
    id: str
    name: str
    cases_json: str
    test_module: str
    case_count: int
    description: str = ""


class SuiteDetail(SuiteSummary):
    cases: list[CaseSummary]


class ReportItem(BaseModel):
    filename: str
    suite_id: str | None = None
    suite_name: str | None = None
    format: Literal["html", "markdown"]
    size_bytes: int
    modified_at: str
    url_path: str


class RunJobRequest(BaseModel):
    suite_id: str
    case_names: list[str] = Field(default_factory=list)
    generate_report: bool = True


class RunJobStatus(BaseModel):
    job_id: str
    suite_id: str
    suite_name: str
    case_names: list[str]
    status: Literal["pending", "running", "passed", "failed", "error"]
    started_at: str | None = None
    finished_at: str | None = None
    exit_code: int | None = None
    duration_seconds: float | None = None
    command: str = ""
    log_url: str | None = None
    report_html_url: str | None = None
    report_md_url: str | None = None
    error_message: str | None = None


class HealthResponse(BaseModel):
    status: str
    project_root: str
    auth_mode: str
    suites: list[str]
    running_job_id: str | None = None


class ApiMessage(BaseModel):
    message: str
    data: dict[str, Any] | None = None
