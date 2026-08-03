"""用户关系 MOA（addUserRelation）— Stage Redis 直连调用。"""

from __future__ import annotations

import os
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Callable

USER_RELATION_SERVICE = "/service/voga-mts-user-relation-stage"
ADD_USER_RELATION_METHOD = "addUserRelation"


def _repo_root() -> str:
    return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def _call_moa(service_uri: str, method: str, args: list[Any]) -> Any:
    gift_dir = os.path.join(_repo_root(), "Gift")
    if gift_dir not in sys.path:
        sys.path.insert(0, gift_dir)
    from gift.send_stage import call_moa

    return call_moa(service_uri, method, args)


def add_user_relation(uid: str, remote_uid: str, *, relation_type: int = 1) -> tuple[bool, str | None]:
    body = {"uid": str(uid).strip(), "remoteUid": str(remote_uid).strip(), "relationType": relation_type}
    result = _call_moa(USER_RELATION_SERVICE, ADD_USER_RELATION_METHOD, [body])
    if not isinstance(result, dict):
        raise RuntimeError(f"addUserRelation 返回非 object: {result!r}")
    ec = result.get("ec")
    if ec == 200:
        em = result.get("em")
        return True, str(em) if em is not None else None
    em = result.get("em")
    return False, str(em) if em is not None else None


@dataclass
class MutualFollowResult:
    target_user_id: str
    friend_user_id: str
    ok: bool
    forward_em: str | None = None
    reverse_em: str | None = None


@dataclass
class BatchMutualFollowResult:
    target_user_id: str
    requested: int
    success: int
    failed: int
    results: list[MutualFollowResult] = field(default_factory=list)


def mutual_follow_pair(
    target_user_id: str,
    friend_user_id: str,
    *,
    sleep_seconds: float = 1.2,
    retry_sleep_seconds: float = 2.0,
    log: Callable[[str], None] | None = None,
) -> MutualFollowResult:
    target_user_id = str(target_user_id).strip()
    friend_user_id = str(friend_user_id).strip()
    if target_user_id == friend_user_id:
        raise ValueError("target 与 friend userId 不能相同")

    def _log(msg: str) -> None:
        if log is not None:
            log(msg)

    _log(f"互关: {target_user_id} <-> {friend_user_id}")
    ok1, em1 = add_user_relation(target_user_id, friend_user_id)
    if not ok1 and em1 and "频繁" in em1:
        time.sleep(retry_sleep_seconds)
        ok1, em1 = add_user_relation(target_user_id, friend_user_id)
    time.sleep(sleep_seconds)

    ok2, em2 = add_user_relation(friend_user_id, target_user_id)
    if not ok2 and em2 and "频繁" in em2:
        time.sleep(retry_sleep_seconds)
        ok2, em2 = add_user_relation(friend_user_id, target_user_id)
    time.sleep(sleep_seconds)

    return MutualFollowResult(
        target_user_id=target_user_id,
        friend_user_id=friend_user_id,
        ok=ok1 and ok2,
        forward_em=em1,
        reverse_em=em2,
    )


def batch_mutual_follow(
    target_user_id: str,
    friend_user_ids: list[str],
    *,
    sleep_seconds: float = 1.2,
    retry_sleep_seconds: float = 2.0,
    log: Callable[[str], None] | None = None,
) -> BatchMutualFollowResult:
    results: list[MutualFollowResult] = []
    success = 0
    for friend_id in friend_user_ids:
        item = mutual_follow_pair(
            target_user_id,
            friend_id,
            sleep_seconds=sleep_seconds,
            retry_sleep_seconds=retry_sleep_seconds,
            log=log,
        )
        results.append(item)
        if item.ok:
            success += 1
    requested = len(friend_user_ids)
    return BatchMutualFollowResult(
        target_user_id=str(target_user_id).strip(),
        requested=requested,
        success=success,
        failed=requested - success,
        results=results,
    )
