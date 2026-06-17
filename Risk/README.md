# 海外风控开放接口（Risk）

在本地复现 Postman 中的风控名单操作：`POST /open/menu/operate`。

> 能力口令与可复制命令见 **[使用方法.md](使用方法.md)**（由 `Risk/config/registry.json` 自动生成）。

参考：[风控文档（钉钉）](https://alidocs.dingtalk.com/i/nodes/qnYMoO1rWxDKo2l2IkoDajmzW47Z3je9)

## 1) 准备环境

```bash
cp Risk/.env.example Risk/.env.local
```

在 `Risk/.env.local` 可选填入：

- `SEC_RISK_TOKEN`：开放接口 token（默认 `sec_risk_IHAH`）
- `SEC_RISK_BASE_URL`：默认 `https://sec-risk-admin-oversea.wemomo.com`
- `SEC_RISK_COOKIE`：可选；开放接口 `/open/menu/operate` 通常**不需要** Cookie，仅需 body 中的 `token`
- `RISK_TEST_DEVICE_KB`：团队测试机知识库 JSON 路径（默认 `testcase-kb/test_devices.json`）

## 2) 解除设备风控（mmuid / mmuidv3 加白）

**业务说明：** 将设备加入白名单，解除设备风控。

| 平台 | 取值字段 | dimension（接口固定） |
|------|----------|----------------------|
| iOS | `mmuid`（E 列） | `mmuid` |
| Android / 鸿蒙 | `mmuidv3`（F 列） | `mmuid` |

**限制：** 每次请求最多 **5 个** element；超过 5 个时脚本默认**自动分批**请求。

| 字段 | 值 |
|------|-----|
| `menu_event` | `8af999b5-73e7-4dab-9950-9b28bc4b6962` |
| `menu_type` | `white` |
| `action` | `add` |

### 推荐：从团队测试机知识库解除（自动选 dimension）

默认读取项目内 `testcase-kb/test_devices.json`，也可通过 `RISK_TEST_DEVICE_KB` 或 `--device-kb` 指定路径。

**列出测试机及对应解除维度：**

```bash
python3 Risk/risk_execute.py --list-test-devices
```

**按资产编号解除（Android 自动用 mmuidv3，iOS 自动用 mmuid）：**

```bash
python3 Risk/risk_execute.py \
  --release-test-device \
  --device-asset "GZ3025010018" \
  --reason 测试
```

**多台设备（逗号分隔，按 dimension 自动分组并分批）：**

```bash
python3 Risk/risk_execute.py \
  --release-test-device \
  --device-asset "GZ3025010018,GZ3021090008" \
  --reason 测试
```

**按设备名称模糊匹配：**

```bash
python3 Risk/risk_execute.py \
  --release-test-device \
  --device-name "GalaxyA80" \
  --reason 测试
```

### 手动指定 mmuid（iOS 或通用）

```bash
python3 Risk/risk_execute.py \
  --release-device \
  --mmuid "e4770cace4e2534c256c6b8f75ecbd1904c59d8fd8495e203bc2aec07908abd20f,22a2c3afd232144b378d278fbd6730301dda3aaca32743a910f332a9a1877cb94c" \
  --reason 测试
```

### 手动指定 Android mmuidv3 值

```bash
python3 Risk/risk_execute.py \
  --release-device \
  --mmuid "e75bd8f8d89459a58fb16cda276e17d4d563bc6f58d70bc8ae3ff855cf4649fb53" \
  --reason 测试
```

### 从文件批量（超过 5 个自动分批）

```bash
python3 Risk/risk_execute.py \
  --release-device \
  --element-file Risk/device_mmuid.example.txt \
  --reason 测试
```

### 完整 payload 文件

```bash
python3 Risk/risk_execute.py \
  --payload-file Risk/menu_operate_payload.example.json
```

### 严格模式（超过 5 个直接报错）

```bash
python3 Risk/risk_execute.py \
  --release-device \
  --mmuid "uid1,uid2,uid3,uid4,uid5,uid6" \
  --strict-limit
```

## 3) 解除手机号风控（phone 加白）

**业务说明：** 将手机号加入白名单，解除手机号风控。

**限制：** 每次请求最多 **5 个**手机号（与设备相同，超过自动分批）。

| 字段 | 值 |
|------|-----|
| `menu_event` | `a5d5630a-fb68-47c3-9f13-2f98d43ba0d2` |
| `menu_type` | `white` |
| `dimension` | `phone` |
| `action` | `add` |

### 推荐：快捷命令

```bash
python3 Risk/risk_execute.py \
  --release-phone \
  --phone "13311111117" \
  --reason 测试
```

### 多个手机号（逗号分隔，超过 5 个自动分批）

```bash
python3 Risk/risk_execute.py \
  --release-phone \
  --phone "13311111117,13322222228" \
  --reason 测试
```

### 完整 payload 文件（与 Postman 截图一致）

```bash
python3 Risk/risk_execute.py \
  --payload-file Risk/phone_risk_release_payload.example.json
```

## 3.1) 线上环境：解除最近登录手机 + 设备风控并落库

**业务说明：** 按线上 `--phone` 或 `--user-id` 查 Admin `loginDevice`，解除设备风控（有手机号时一并解除）；若 `testcase-kb/test_devices.json` 无记录或 mmuid/mmuidv3 不全，**自动补录**。

```bash
# 按 userId（Google 等无手机号账号）
python3 Risk/risk_execute.py \
  --release-online-login-device \
  --user-id 108990429 \
  --reason 线上环境测试

# 按手机号
python3 Risk/risk_execute.py \
  --release-online-login-device \
  --phone 19900007777 \
  --reason 线上环境测试
```

跳过知识库落库时加 `--skip-record-kb`。

## 4) 充值风控（user_id 黑名单）

**业务说明：** 对用户 `user_id` 操作充值风控黑名单。

| 操作 | `action` | 说明 |
|------|----------|------|
| 添加充值风控 | `add` | 加入黑名单 |
| 解除充值风控 | `delete` | 从黑名单移除 |

| 字段 | 值 |
|------|-----|
| `menu_event` | `2cbed5b4-7cbb-4da5-bb47-048108dcdf75` |
| `menu_type` | `black` |
| `dimension` | `user_id` |

### 添加充值风控

```bash
python3 Risk/risk_execute.py \
  --add-recharge-risk \
  --user-id "100465989" \
  --reason 测试
```

或与 Postman 截图一致：

```bash
python3 Risk/risk_execute.py \
  --payload-file Risk/recharge_risk_add_payload.example.json
```

### 解除充值风控

```bash
python3 Risk/risk_execute.py \
  --release-recharge-risk \
  --user-id "100465989" \
  --reason 测试
```

```bash
python3 Risk/risk_execute.py \
  --payload-file Risk/recharge_risk_release_payload.example.json
```

### 多个 user_id（超过 5 个自动分批）

```bash
python3 Risk/risk_execute.py \
  --add-recharge-risk \
  --user-id "100465989,100465990" \
  --reason 测试
```

## 5) 活动风控（user_id 黑名单）

**业务说明：** 对用户 `user_id` 操作活动风控黑名单。

| 操作 | `action` | 说明 |
|------|----------|------|
| 添加活动风控 | `add` | 加入黑名单 |
| 解除活动风控 | `delete` | 从黑名单移除 |

| 字段 | 值 |
|------|-----|
| `menu_event` | `cf6bdc74-7be7-474a-b10d-1859f056e1b9` |
| `menu_type` | `black` |
| `dimension` | `user_id` |

### 添加活动风控

```bash
python3 Risk/risk_execute.py \
  --add-activity-risk \
  --user-id "100465989" \
  --reason 测试
```

### 解除活动风控

```bash
python3 Risk/risk_execute.py \
  --release-activity-risk \
  --user-id "100465989" \
  --reason 测试
```

与 Postman 截图一致：

```bash
python3 Risk/risk_execute.py \
  --payload-file Risk/activity_risk_release_payload.example.json
```

## 6) 通用名单操作

| 字段 | 说明 |
|------|------|
| `menu_event` | 名单 event UUID |
| `menu_type` | `white` / `black` |
| `dimension` | 维度，如 `mmuid` |
| `elements` | 元素数组 |
| `action` | `add` / `delete` |
| `reason` | 操作原因 |
| `token` | 开放接口 token |

```bash
python3 Risk/risk_execute.py \
  --menu-key device_risk_release \
  --action add \
  --elements "mmuid1,mmuid2" \
  --reason 测试
```

## 7) 配置 menu_event

在 `Risk/config.json` 的 `menu_events` 中维护各业务名单：

- `device_risk_release`：解除设备风控（iOS / mmuid / white / add）
- `device_risk_release_mmuidv3`：解除 Android 设备风控（dimension=mmuid，element 填 mmuidv3 值）
- `phone_risk_release`：解除手机号风控（phone / white / add）
- `recharge_risk_control`：充值风控（user_id / black / add 或 delete）
- `activity_risk_control`：活动风控（user_id / black / add 或 delete）

## 8) 调试

```bash
python3 Risk/risk_execute.py \
  --release-device \
  --mmuid "mmuid1" \
  --dump-body
```

## 维护

| 操作 | 命令 |
|------|------|
| 刷新能力清单 | `python3 Risk/scripts/generate_index.py` |

新增 Risk 能力后，登记 `Risk/config/registry.json` 并执行上述命令，更新 [使用方法.md](使用方法.md)。
