"""钉钉网关：活动 IM 指定用户下发（addIm whiteList，勿 xlsx 附件）。"""

from __future__ import annotations


def gateway_im_whitelist_rule_line() -> str:
    return (
        "**活动 IM 指定用户/白名单下发**：用 `Admin/admin_execute.py --add-im-task`（addIm），"
        "`userType=3` + `whiteList` 填逗号分隔 userId；**禁止**生成 xlsx/csv 或 `send_group_file` 附件。"
        "消息类型 `--im-send-type`：0 活动通知 / 1 活动奖励 / 2~5 见 Admin/im_activity.py。"
        "示例：`python3 Admin/admin_execute.py --add-im-task --im-task-name <名称> --im-send-type 1 "
        "--im-user-ids <userId> --im-area MENA`。"
    )
