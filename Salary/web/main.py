# -*- coding: utf-8 -*-
"""
Yaahlan 算薪自动化测试可视化后台（FastAPI MVP）。

启动:
  python3 -m uvicorn web.main:app --host 0.0.0.0 --port 8088
或:
  bash scripts/run_web_dashboard.sh
"""
from __future__ import annotations

import mimetypes
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.responses import FileResponse, HTMLResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles

from utils.env_utils import load_env_file
from web.auth import verify_dashboard_access
from web.config import PROJECT_ROOT, SUITES, auth_required, dashboard_port
from web.models import ApiMessage, HealthResponse, ReportItem, RunJobRequest, RunJobStatus, SuiteDetail, SuiteSummary
from web.services.cases import get_suite_detail, list_suites
from web.services.reports import list_reports, resolve_report_file
from web.services.runner import job_runner

load_env_file(str(PROJECT_ROOT))

app = FastAPI(
    title="Yaahlan 算薪测试后台",
    description="数据驱动 pytest 用例浏览、触发执行与报告查看（MVP）",
    version="0.1.0",
)

STATIC_DIR = Path(__file__).resolve().parent / "static"
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.get("/", response_class=HTMLResponse, include_in_schema=False)
def index_page():
    index_path = STATIC_DIR / "index.html"
    return HTMLResponse(index_path.read_text(encoding="utf-8"))


@app.get("/api/health", response_model=HealthResponse)
def health():
    return HealthResponse(
        status="ok",
        project_root=str(PROJECT_ROOT),
        auth_mode="token" if auth_required() else "localhost-only",
        suites=[s.id for s in SUITES],
        running_job_id=job_runner.running_job_id,
    )


@app.get("/api/suites", response_model=list[SuiteSummary])
def api_list_suites(_: None = Depends(verify_dashboard_access)):
    return list_suites()


@app.get("/api/suites/{suite_id}", response_model=SuiteDetail)
def api_get_suite(suite_id: str, _: None = Depends(verify_dashboard_access)):
    detail = get_suite_detail(suite_id)
    if not detail:
        raise HTTPException(status_code=404, detail=f"套件不存在: {suite_id}")
    return detail


@app.get("/api/reports", response_model=list[ReportItem])
def api_list_reports(
    suite_id: str | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
    _: None = Depends(verify_dashboard_access),
):
    return list_reports(suite_id=suite_id, limit=limit)


@app.get("/api/reports/files/{file_path:path}")
def api_get_report_file(file_path: str, _: None = Depends(verify_dashboard_access)):
    abs_path = resolve_report_file(file_path)
    if not abs_path:
        raise HTTPException(status_code=404, detail="报告文件不存在或无权访问")
    media_type, _ = mimetypes.guess_type(abs_path)
    return FileResponse(abs_path, media_type=media_type or "application/octet-stream")


@app.get("/api/jobs", response_model=list[RunJobStatus])
def api_list_jobs(
    limit: int = Query(default=30, ge=1, le=100),
    _: None = Depends(verify_dashboard_access),
):
    return job_runner.list_jobs(limit=limit)


@app.get("/api/jobs/{job_id}", response_model=RunJobStatus)
def api_get_job(job_id: str, _: None = Depends(verify_dashboard_access)):
    job = job_runner.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"任务不存在: {job_id}")
    return job


@app.get("/api/jobs/{job_id}/log", response_class=PlainTextResponse)
def api_get_job_log(
    job_id: str,
    tail: int = Query(default=400, ge=50, le=5000),
    _: None = Depends(verify_dashboard_access),
):
    if not job_runner.get_job(job_id):
        raise HTTPException(status_code=404, detail=f"任务不存在: {job_id}")
    return PlainTextResponse(job_runner.read_log(job_id, tail_lines=tail))


@app.post("/api/jobs/run", response_model=RunJobStatus)
def api_run_job(body: RunJobRequest, _: None = Depends(verify_dashboard_access)):
    try:
        return job_runner.submit(
            suite_id=body.suite_id,
            case_names=body.case_names,
            generate_report=body.generate_report,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post("/api/jobs/{job_id}/cancel", response_model=ApiMessage)
def api_cancel_job(job_id: str, _: None = Depends(verify_dashboard_access)):
    # MVP 暂不支持强制终止 subprocess，避免 DB/MOA 半状态
    job = job_runner.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail=f"任务不存在: {job_id}")
    if job.status in ("passed", "failed", "error"):
        return ApiMessage(message="任务已结束，无需取消")
    return ApiMessage(message="MVP 暂不支持取消运行中的任务，请等待 pytest 结束")


def main():
    import uvicorn

    uvicorn.run("web.main:app", host="0.0.0.0", port=dashboard_port(), reload=False)


if __name__ == "__main__":
    main()
