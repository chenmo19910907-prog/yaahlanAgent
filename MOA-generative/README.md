# MOA-generative

把 **Tunnel 抓包（HTTP 客户端请求）** 转成 **MSE MOA 代理可调用的 payload**，用于本地复现签到、点赞等端上接口。

与 `MOA/templates/` 里现成后门/测试接口不同：这里记录的是「看抓包 + 看调用链 → 套壳生成」的通用方法。

## 核心规律

| 步骤 | 做什么 |
|------|--------|
| 1. Tunnel 抓 HTTP | 得到 `url` 最后一段 ≈ `method`，以及 request body |
| 2. 打开该请求的调用链 | 取真正落地的 **ServiceUrl**（不能靠猜路径） |
| 3. 套壳 | body **同时**写入 `header`（JSON 字符串）和 `params[0]`（`type=json`） |
| 4. `moa_execute` 试跑 | 业务拒绝（已签到/已点赞）也算调通；`No address` / `Method not found` 再改 url/method |

## 已验证映射

| HTTP | MOA `url` | `method` |
|------|-----------|----------|
| `/yaahlan/sign/signIn` | `/service/yaahlan-trick/external/app-task` | `signIn` |
| `/yaahlan/feed-interact/likeContent` | `/service/feed/external/feed-interact-stage` | `likeContent` |
| `/yaahlan/user/intimate/acceptIntimateInvitation` | `/service/yaahlan/user/intimate-api` | `acceptIntimateInvitation` |

详见 [使用方法.md](./使用方法.md)（能力清单 / 提示词 / 命令）、[mappings.md](./mappings.md)、[USAGE.md](./USAGE.md)（英文摘要）。

## 目录

```
MOA-generative/
├── README.md
├── 使用方法.md          # 能力清单（registry 自动生成）
├── USAGE.md             # 英文摘要
├── mappings.md
├── config/registry.json
├── templates/
│   ├── payload.shell.json
│   ├── example-signIn.json / example-signIn.body.json
│   └── example-likeContent.json / example-likeContent.body.json
└── scripts/
    ├── generate_index.py      # 刷新 使用方法.md + 工具台 catalog
    ├── build_payload.py       # 仅生成 payload
    ├── run_generative_moa.py  # 生成 + 执行（工作流入口）
    └── form_intimate_pair.py  # 结挚友：Gift 发起 + MOA 同意
```

## 推荐：工作流复用

```bash
python3 workflow/workflow_execute.py run moa-generative-run \
  --service-url /service/yaahlan-trick/external/app-task \
  --method signIn \
  --body-file MOA-generative/templates/example-signIn.body.json

# 点赞示例
python3 workflow/workflow_execute.py run moa-generative-run \
  --service-url /service/feed/external/feed-interact-stage \
  --method likeContent \
  --body-file /path/to/like_capture_body.json

# 要求业务真正成功（非「已签到/已点赞」也算过）
python3 workflow/workflow_execute.py run moa-generative-run \
  --service-url /service/... \
  --method likeContent \
  --body-file /path/to/body.json \
  --strict 1
```

默认 `--strict 0`：代理调通即可（业务拒绝仍算成功）。报告在 `.tmp/workflow_runs/`。

## 手动生成并执行

```bash
python3 MOA-generative/scripts/build_payload.py \
  --url /service/feed/external/feed-interact-stage \
  --method likeContent \
  --body-file /tmp/like_req.json \
  --out .tmp/generative_moa_like.json

python3 MOA/moa_execute.py --payload-file .tmp/generative_moa_like.json --timeout-ms 20000
```

一键脚本（与工作流同逻辑）：

```bash
python3 MOA-generative/scripts/run_generative_moa.py \
  --url /service/yaahlan-trick/external/app-task \
  --method signIn \
  --body-file MOA-generative/templates/example-signIn.body.json \
  --strict 0
```
