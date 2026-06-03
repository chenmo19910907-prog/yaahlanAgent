# MOA 本地调用

通过 MSE httpproxy 在本地（Cursor 终端）复现 MOA 请求。

> 首次使用或换电脑：请先阅读 [docs/新手上手.md](../docs/新手上手.md) 配置 `MOA/.env.local`。

## 目录结构

```
MOA/
├── README.md                 # 本文件
├── moa_execute.py            # CLI 入口
├── .env.example / .env.local # 环境变量（Cookie 不入库）
├── config/
│   ├── registry.json         # 能力登记（提示词 + 命令）
│   └── thresholds.json       # 等级阈值、家族基金档位等规则
├── 使用方法.md                # 能力清单（自动生成）
├── scripts/
│   ├── generate_index.py     # 生成 使用方法.md
│   └── test_all.py           # 批量自测全部模板
├── templates/                # MOA 请求 JSON 模板（扁平存放）
│   ├── VIP-增加经验值.json
│   ├── 钻石-查询余额.json
│   └── ...
└── moa/                      # Python 实现
    ├── cli.py                # 命令行入口
    ├── client.py             # httpproxy 客户端
    ├── payload.py            # payload 构造与 CLI 参数映射
    ├── flows.py              # 复合流程（升级、返奖等）
    └── paths.py              # 目录路径常量
```

## 快速开始

```bash
python3 -m venv MOA/.venv
MOA/.venv/bin/pip install -r MOA/requirements.txt

cp MOA/.env.example MOA/.env.local
# 编辑 MOA/.env.local，填入 MOA_ENTRY_URL、MOA_COOKIE

# 可选：YAML 团队默认配置（见 MOA/config/moa.yaml.example）
cp MOA/config/moa.yaml.example MOA/config/moa.yaml
# 若启用 redis.enabled，Cookie 可从 Redis 键 moa:cookie 读取

MOA/.venv/bin/python MOA/moa_execute.py --help
```

> 依赖 **redis**、**PyYAML**（见 `requirements.txt`）。未创建 `moa.yaml` 时仍可用 `.env.local` 运行。

### 直接执行模板

```bash
MOA/.venv/bin/python MOA/moa_execute.py --payload-file "MOA/templates/钻石-查询余额.json"
MOA/.venv/bin/python MOA/moa_execute.py --payload-file "MOA/templates/查询用户登录天数.json" --expr 100465989
```

### 带 CLI 参数

```bash
python3 MOA/moa_execute.py \
  --payload-file "MOA/templates/VIP-增加经验值.json" \
  --vip-user-id 100465989 \
  --vip-query-current
```

完整口令与命令见 **[使用方法.md](使用方法.md)**。

## 维护

| 操作 | 命令 |
|------|------|
| 刷新能力清单 | `python3 MOA/scripts/generate_index.py` |
| 批量自测 | `python3 MOA/scripts/test_all.py` |

### 新增 MOA 能力

1. 在 **`templates/`** 新增 JSON 模板（须含 `key` 字段）
2. 如需参数化，扩展 **`moa/`** 包中的 CLI 逻辑
3. 规则/映射写入 **`config/thresholds.json`**
4. 登记 **`config/registry.json`**
5. 运行 `python3 MOA/scripts/generate_index.py`

## 相关文档

- [使用方法.md](使用方法.md) — 全部能力口令与命令
- [docs/新手上手.md](../docs/新手上手.md) — 新机器配置引导
