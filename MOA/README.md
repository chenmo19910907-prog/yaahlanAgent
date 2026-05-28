# MOA 调用脚本（Cursor 可运行）

这个目录用于在本地（Cursor 终端）复现 MOA 的 `execute` 调用：把 MOA 页面里的一段请求 JSON 作为 body，POST 到 httpproxy 接口，由后端执行目标 service 的 `execute`。

## 1) 准备环境变量（必需）

- `MOA_ENTRY_URL`: httpproxy 入口完整 URL  
  例（你抓包里真实请求）：`https://mse.wemomo.com/apirest/httpproxy/moa/test`
- `MOA_COOKIE`: 从浏览器/MOA 页面复制的整段 Cookie（敏感信息，不要提交到仓库）

推荐做法：把这些变量写入 `MOA/.env.local`（已加入 `.gitignore`，不会被提交），脚本会自动加载。

你可以先复制模板：

```bash
cp MOA/.env.example MOA/.env.local
```

然后把 `MOA/.env.local` 里的 `MOA_COOKIE=...` 替换成你自己的 Cookie。

示例：

```bash
export MOA_ENTRY_URL='https://mse.wemomo.com/apirest/httpproxy/moa/test'
export MOA_COOKIE='JSESSIONID=...; tunnel_login_session=...; auth_cookie=...'
```

可选但建议（与你抓到的请求头对齐，部分环境会校验这些字段）：

- `MOA_ORIGIN`: `https://mse.wemomo.com`
- `MOA_REFERER`: `https://mse.wemomo.com/`
- `MOA_USER_AGENT`: 浏览器 UA（可简化成 `Mozilla/5.0`）
- `MOA_REQUEST_SOURCE`: `moaProxy`

```bash
export MOA_ORIGIN='https://mse.wemomo.com'
export MOA_REFERER='https://mse.wemomo.com/'
export MOA_USER_AGENT='Mozilla/5.0'
export MOA_REQUEST_SOURCE='moaProxy'
```

## 2) 直接执行（传入完整 JSON）

把你在 MOA 里看到/导出的请求 JSON 保存成文件（比如 `payload.json`），然后运行：

```bash
python3 MOA/moa_execute.py --payload-file payload.json
```

或者直接把 JSON 作为参数（适合短 payload）：

```bash
python3 MOA/moa_execute.py --payload '{"type":"moa","url":"/service/xxx","method":"execute","params":[...]}'
```

## 2.1) 一条命令复现「你抓包里的 MOA」

你抓到的请求入口与 body（不含 Cookie）是：

- 入口：`https://mse.wemomo.com/apirest/httpproxy/moa/test`
- body 里核心字段：`url=/service/voga-mts-room-backdoor`、`method=execute`

所以最短运行方式是（roomId/exp 可替换）：

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/payload.example.json \
  --service-url /service/voga-mts-room-backdoor \
  --moa-method execute \
  --room-id 31668628 \
  --exp 11
```

## 3) 便捷模式：只改表达式（可选）

如果你只想快速替换 `params[0].value`，可以用：

```bash
python3 MOA/moa_execute.py \
  --payload-file payload.json \
  --expr 'context.getBean("roomProfileDao").addRoomActiveValue("31668628",10000000D)'
```

或者用便捷参数生成「给房间增加经验值」的表达式（会覆盖 `params[0].value/txt`）：

```bash
python3 MOA/moa_execute.py \
  --payload-file payload.json \
  --room-id 31668628 \
  --exp 10000000
```

## 房间等级经验值阈值（配置文件）

阈值已迁移到 `MOA/config.json` 的 `room_level_exp_thresholds` 字段；后续类似“规则/映射表”都统一沉淀到该配置文件。

### 只说等级的用法（脚本按阈值算增量）

注意：MOA 方法是 `addRoomActiveValue`（增量增加），所以需要“当前经验值”来计算要加多少。

现在脚本在 `--level` 模式下会**自动先查询当前经验值（0D）**，再补差值；通常不需要你再传 `--current-exp`。

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/payload.example.json \
  --service-url /service/voga-mts-room-backdoor \
  --moa-method execute \
  --room-id 31668628 \
  --level 3
```

如果你明确知道当前经验值，也可以传 `--current-exp` 跳过查询（适用于批量操作/减少一次请求）。

## 查询房间当前经验值与等级

可以通过“增加 0 经验值”的方式拿到当前经验值（你提到的做法），然后脚本会按阈值计算等级：

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/payload.example.json \
  --service-url /service/voga-mts-room-backdoor \
  --moa-method execute \
  --room-id 89333567 \
  --query-current
```

如果 MOA 页面里选择了具体实例（例如右上角显示 `10.247.244.119:29584`），通常需要把它写进 `settings.host`，可以用：

```bash
python3 MOA/moa_execute.py \
  --payload-file payload.json \
  --host 10.247.244.119:29584 \
  --room-id 31668628 \
  --exp 10000000
```

## VIP：增加 VIP 经验值 / 按 VIP 等级补差

你抓包的 VIP MOA：

- `url`: `/service/voga-mts-user-vip-stage`
- `method`: `addVipValue`
- `params[0]`: 用户ID（string）
- `params[1]`: 增加的 VIP 经验值（int）

### 给用户增加指定 VIP 经验值

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/vip_payload.example.json \
  --vip-user-id 100066819 \
  --vip-exp 10
```

### 只说目标 VIP 等级（自动先查当前 VIP 经验，再补差）

VIP 等级阈值已迁移到 `MOA/config.json` 的 `vip_level_exp_thresholds`。

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/vip_payload.example.json \
  --vip-user-id 100066819 \
  --vip-level 4
```

### 查询当前 VIP 经验值与等级

```bash
python3 MOA/moa_execute.py \
  --payload-file MOA/vip_payload.example.json \
  --vip-user-id 100066819 \
  --vip-query-current
```

如果返回 `ec=300` 但 MOA 页面同操作能成功，优先怀疑这几个字段与你页面不一致（常见：`yoga`/`voga` 拼写、超时太短）：

```bash
python3 MOA/moa_execute.py \
  --payload-file payload.json \
  --host 10.247.244.119:29584 \
  --service-url /service/yoga-mts-room-backdoor \
  --moa-time 5000 \
  --room-id 34760986 \
  --exp 10000000
```

## 4) 输出与成功判定

脚本会把服务返回 JSON 原样打印，并尝试提取：

- `ec`: 0 代表成功（如果返回体包含该字段）
- `em`: 文本信息
- `result`: 业务返回值

当检测到 `ec != 0` 时脚本会以非 0 退出码退出，方便在流水线/批处理里判断失败。

## 5) （可选）用 curl 直接运行

适合验证“是不是脚本问题”，不适合长期复用（容易把 Cookie 留在历史记录里）。

```bash
curl -sS "$MOA_ENTRY_URL" \
  -X POST \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/plain, */*' \
  -H "Cookie: $MOA_COOKIE" \
  -H "Origin: ${MOA_ORIGIN:-https://mse.wemomo.com}" \
  -H "Referer: ${MOA_REFERER:-https://mse.wemomo.com/}" \
  -H 'request-source: moaProxy' \
  --data-raw '{"type":"moa","url":"/service/voga-mts-room-backdoor","method":"execute","header":"","params":[{"title":"参数1","name":"1","txt":"context.getBean(\"roomProfileDao\").addRoomActiveValue(\"31668628\",11D)","json":"","type":"string","value":"context.getBean(\"roomProfileDao\").addRoomActiveValue(\"31668628\",11D)"}],"settings":{"time":"2000","group":"default","host":"","headerType":"TXT"},"region":"alpha","env":"alpha","cluster":"stage","server":"config","momoId":"df4c6f364f9fcae3","momoName":"e88aa376b29864ad"}'
```

