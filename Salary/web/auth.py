# -*- coding: utf-8 -*-
"""简单 Token 鉴权（内网后台）。"""
from __future__ import annotations

from fastapi import Header, HTTPException, Request

from web.config import auth_required, dashboard_token


def verify_dashboard_access(
    request: Request,
    x_dashboard_token: str | None = Header(default=None, alias="X-Dashboard-Token"),
) -> None:
    token = dashboard_token()
    if not token:
        client_host = request.client.host if request.client else ""
        if client_host not in ("127.0.0.1", "::1", "localhost"):
            raise HTTPException(
                status_code=403,
                detail="未配置 DASHBOARD_TOKEN，仅允许本机访问。请在 .env 中设置 DASHBOARD_TOKEN。",
            )
        return
    if x_dashboard_token != token:
        raise HTTPException(status_code=401, detail="无效的 Dashboard Token")
