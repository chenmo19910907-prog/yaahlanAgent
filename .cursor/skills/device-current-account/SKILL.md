---
name: device-current-account
description: 通过 Admin 后台查询测试机当前登录的 userId。按设备名（如红米12）、资产编号或 mmuidv3，从 test_devices.json 取设备标识，再查设备历史登录账号与 queryUserDetail 校验。在用户问「某台设备当前登录什么账号」「后台查设备登录用户」「这台手机登录的是谁」时使用。
---

# 设备当前登录账号（Admin 后台）

## 何时使用

- 用户问某台测试机**当前登录**的 userId / 昵称 / 手机号
- 真机未连 ADB，或需用**后台**而非读屏确认账号
- 切换账号后验收「当前会话是谁」

## 前置条件

- `Admin/.env.local` 已配置（`ADMIN_SSO_TOKEN`、`ADMIN_YAAHLAN_JWT`）
- 设备在 `testcase-kb/test_devices.json` 有台账（含 **mmuidv3**；iOS 仅有 mmuid 时见下文）

## 执行步骤

### 1. 解析设备 → mmuidv3

在 `testcase-kb/test_devices.json` 按 **设备名称**（如「红米12」）、**设备品牌**、**资产编号** 匹配：

| 平台 | 后台查询用字段 |
|------|----------------|
| Android / 鸿蒙 | `mmuidv3` |
| iOS | `mmuid`（设备历史接口若不支持则改走 Tunnel / ADB） |

示例（红米12）：

- `mmuid`：`c59874d00a8b3599df3bbccc6b853e47572e2854`
- `mmuidv3`：`125476e669d6577d0c04aff83c1eec3ec6c22fac6e9dde4cadba2056b0c80e71f8`
- 机型 UA 常见：`23077RABDC`（与 `adb/录制脚本/设备适配/档案/mi_23077rabdc.json` 对应）

### 2. 查设备历史登录账号（取最近一条）

列表按 **`updateTime` 降序**，第一条通常为该设备**最近登录**账号：

```bash
python3 Admin/admin_execute.py \
  --query-device-history-users \
  --history-device-mmuidv3 <mmuidv3> \
  --output json
```

关注 `data.list[0]` 的 `userId`、`nickName`、`updateTime`。

### 3. 用 queryUserDetail 校验「当前登录设备」

对候选 `userId` 查详情，核对 `loginDevice.mmuidv3`（或 iOS 的 `mmuid`）与台账一致：

```bash
python3 Admin/admin_execute.py --query-user-id <userId>
```

判定依据：

- `loginDevice.mmuidv3` === 台账 `mmuidv3` → 该账号在此设备上的**最近登录会话**
- `onlineStatus === 1` → 当前在线（辅助判断）
- `loginDevice.ua` 含机型（如 `23077RABDC`）→ 与设备型号一致

### 4.（可选）Tunnel 交叉验证

若账号近期有 App 请求，可用抓包确认 `deviceId` / `model`：

```bash
python3 Tunnel/tunnel_execute.py --momoid <userId> --keyword heartbeat --since 3600 --output json
```

核对 `request.deviceId`（mmuid）与 `request.model` 是否匹配目标机。

## 输出格式

向用户汇报：

| 字段 | 说明 |
|------|------|
| 设备 | 品牌 + 名称 + 资产编号 |
| userId | 当前登录账号 |
| 昵称 | nickName |
| 手机号 | queryUserDetail 的 fullPhone（如有） |
| 在线 | onlineStatus |
| 最近登录时间 | loginDevice.loginTime |
| 依据 | 设备历史 updateTime + loginDevice 校验（+ Tunnel 如有） |

## 注意

- `queryHistoryUserListByDeviceId` 是**设备维度历史**，列表第一条 = 最近登录，**不是**「仅当前在线」接口；须用 **步骤 3** 校验 `loginDevice`。
- 同一设备可能登录过多个账号（历史列表 `total` 可达数十）；勿只报列表而不校验 loginDevice。
- 勿提交 `Admin/.env.local` 或 Cookie。

## 示例（红米12）

1. 台账 → mmuidv3 `125476e6…e71f8`
2. 设备历史 → 最近 `100486375` / C2…
3. queryUserDetail → `loginDevice.mmuidv3` 匹配红米12，`onlineStatus=1`
4. Tunnel → `deviceId=c59874d0…`，`model=23077RABDC`

**结论**：红米12 当前登录 **100486375**（+86 13311111112）。

## 相关文档

- [Admin/使用方法.md](../../../Admin/使用方法.md) — `query_history_user_list_by_device_id`、`query_user_detail`
- [testcase-kb/test_devices.json](../../../testcase-kb/test_devices.json) — 测试机 mmuid/mmuidv3
- [tunnel-read](../tunnel-read/SKILL.md) — 抓包交叉验证
