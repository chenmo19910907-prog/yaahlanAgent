"""MSE 配置保存与发布编排。"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass
from typing import Any

from .client import (
    all_publish_by_record,
    complete_publish_record,
    create_publish_record,
    get_config_by_id_and_cluster,
    get_publish_check_by_cluster,
    get_session_user,
    save_or_update_config_model,
    skip_grey_publish,
)


@dataclass
class PublishResult:
    config_id: int
    record_id: int | None
    saved: bool
    published: bool
    completed: bool
    changes: list[str]


def _cluster_config_entry(item: dict[str, Any], config_value: str) -> dict[str, Any]:
    active_name = str(item.get("activeName") or "json")
    combine_list = item.get("combineStringList")
    if combine_list is None:
        combine_list = "[]"
    elif not isinstance(combine_list, str):
        combine_list = json.dumps(combine_list, ensure_ascii=False)
    value_symbol = item.get("valueSymbol")
    try:
        value_symbol_int = int(value_symbol)
    except (TypeError, ValueError):
        value_symbol_int = 0
    return {
        "activeName": active_name,
        "configValue": config_value,
        "valueSymbol": value_symbol_int,
        "combineSymbol": str(item.get("combineSymbol") or ""),
        "combineStringList": combine_list,
    }


def _build_config_info_model(
    item: dict[str, Any],
    *,
    config_value: str,
    momo_id: str,
    momo_name: str,
) -> dict[str, Any]:
    active_name = str(item.get("activeName") or "json")
    cluster = str(item.get("region") or "stage")
    cluster_values = item.get("clusterValues")
    if not isinstance(cluster_values, list) or not cluster_values:
        cluster_values = [{"cluster": cluster, "value": config_value, "activeName": active_name}]

    combine_list = item.get("combineStringList")
    if combine_list is None:
        combine_list = "[]"
    elif not isinstance(combine_list, str):
        combine_list = json.dumps(combine_list, ensure_ascii=False)

    return {
        "id": item["id"],
        "configKey": item["configKey"],
        "configDesc": item.get("configDesc") or "",
        "configType": item.get("configType") or "NORMAL_CONFIG",
        "source": item.get("configSource") or item.get("source") or "PANGU",
        "appKey": item["appKey"],
        "nameSpace": item["nameSpace"],
        "mutiRegion": bool(item.get("mutiRegion")),
        "activeName": active_name,
        "combineSymbol": str(item.get("combineSymbol") or ""),
        "valueSymbol": str(item.get("valueSymbol") or "0"),
        "combineStringList": combine_list,
        "momoId": momo_id,
        "momoName": momo_name,
        "clusterValues": cluster_values,
        "advancedCheck": bool(item.get("advancedCheck")),
        "configValue": json.dumps({cv["cluster"]: cv.get("value", config_value) for cv in cluster_values}, ensure_ascii=False)
        if isinstance(cluster_values, list) and cluster_values
        else json.dumps({cluster: config_value}, ensure_ascii=False),
    }


def save_config_value(
    *,
    base_url: str,
    cookie: str,
    region: str,
    env: str,
    cluster: str,
    app_key: str,
    config_id: int,
    config_value: str,
    timeout_s: float = 30.0,
) -> dict[str, Any]:
    item = get_config_by_id_and_cluster(
        base_url=base_url,
        cookie=cookie,
        region=region,
        env=env,
        cluster=cluster,
        app_key=app_key,
        config_id=config_id,
        timeout_s=timeout_s,
    )
    session = get_session_user(base_url=base_url, cookie=cookie, timeout_s=timeout_s)
    momo_id = str(session.get("userId") or "")
    momo_name = str(session.get("userCnName") or session.get("userName") or "")
    if not momo_id:
        raise RuntimeError("无法从 MSE session 获取操作人 userId")

    config_info = _build_config_info_model(item, config_value=config_value, momo_id=momo_id, momo_name=momo_name)
    payload = {"configInfoModel": config_info, "advancedCheck": {}, "degradeTimePeriod": None}
    return save_or_update_config_model(
        base_url=base_url,
        cookie=cookie,
        region=region,
        env=env,
        cluster=cluster,
        payload=payload,
        timeout_s=timeout_s,
    )


def publish_config_value(
    *,
    base_url: str,
    cookie: str,
    region: str,
    env: str,
    cluster: str,
    app_key: str,
    config_id: int,
    config_value: str,
    skip_grey: bool = True,
    wait_check: bool = True,
    check_interval_s: float = 2.0,
    check_max_attempts: int = 5,
    timeout_s: float = 30.0,
) -> int:
    item = get_config_by_id_and_cluster(
        base_url=base_url,
        cookie=cookie,
        region=region,
        env=env,
        cluster=cluster,
        app_key=app_key,
        config_id=config_id,
        timeout_s=timeout_s,
    )
    publish_json = {
        "appKey": item["appKey"],
        "nameSpace": item["nameSpace"],
        "configKey": item["configKey"],
        "configValues": {cluster: _cluster_config_entry(item, config_value)},
        "configId": item["id"],
    }
    record_id = create_publish_record(
        base_url=base_url,
        cookie=cookie,
        region=region,
        env=env,
        cluster=cluster,
        payload=publish_json,
        timeout_s=timeout_s,
    )

    if skip_grey:
        skip_grey_publish(
            base_url=base_url,
            cookie=cookie,
            region=region,
            env=env,
            cluster=cluster,
            record_id=record_id,
            timeout_s=timeout_s,
        )
    else:
        raise RuntimeError("灰度发布尚未实现，请省略 --with-grey（默认跳过灰度全量发布）")

    all_publish_by_record(
        base_url=base_url,
        cookie=cookie,
        region=region,
        env=env,
        cluster=cluster,
        record_id=record_id,
        clear_part={cluster: True},
        timeout_s=timeout_s,
    )

    if wait_check:
        for _ in range(max(1, check_max_attempts)):
            result = get_publish_check_by_cluster(
                base_url=base_url,
                cookie=cookie,
                region=region,
                env=env,
                cluster=cluster,
                record_id=record_id,
                timeout_s=timeout_s,
            )
            instances = result.get(cluster) if isinstance(result, dict) else None
            if isinstance(instances, list) and instances:
                break
            time.sleep(max(0.5, check_interval_s))

    complete_publish_record(
        base_url=base_url,
        cookie=cookie,
        region=region,
        env=env,
        cluster=cluster,
        record_id=record_id,
        timeout_s=timeout_s,
    )
    return record_id
