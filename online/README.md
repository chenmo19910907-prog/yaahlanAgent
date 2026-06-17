# online · 线上环境（Admin / MOA / Tunnel）

Yaahlan **线上/生产** 后台、MOA、Tunnel 抓包的统一调用模块，与测试环境（`Admin/`、`MOA/`、`Tunnel/` 默认 alpha）完全隔离。

**命令速查**：[使用方法.md](使用方法.md)（提示词 ↔ 可执行命令，与 Admin/MOA/Tunnel 同风格）。

> 能力清单由 `online/config/registry.json` 自动生成，执行 `python3 online/scripts/generate_index.py` 可刷新。

## 何时使用

- 用户提示词含关键词 **「线上环境」**
- 查线上用户详情、手机号 userId、overseas 抓包等

**无「线上环境」关键词时禁止调用本模块。**

## 目录结构

```
online/
├── online_execute.py       # 统一入口
├── config.json             # Admin + MOA + Tunnel 配置
├── .env.example / .env.local
├── config/registry.json    # 能力登记
├── templates/              # MOA 模板（overseas）
├── scripts/generate_index.py
├── 使用方法.md
├── env.py                  # 环境变量加载
├── config.py               # 配置读取
├── cli.py                  # 子命令分发
└── paths.py
```

## 环境配置

```bash
cp online/.env.example online/.env.local
# 填入 ADMIN_ONLINE_*、MOA_ONLINE_*、TUNNEL_ONLINE_*
```

| 变量前缀 | 用途 |
|----------|------|
| `ADMIN_ONLINE_*` | yaahlan-admin.wemomo.com |
| `MOA_ONLINE_*` | MSE httpproxy overseas |
| `TUNNEL_ONLINE_*` | tunnel.wemomo.com，`g_env=overseas` |

> 兼容旧文件 `Admin/.env.online.local` 等；优先读 `online/.env.local`。

## 调用示例

```bash
python3 online/online_execute.py admin --query-user-id 101352646
python3 online/online_execute.py moa --query-user-by-phone 19900001111
python3 online/online_execute.py tunnel --momoid 107427060 --since 3600
```

## 维护

```bash
python3 online/scripts/generate_index.py
```

## 与测试环境的关系

| 能力 | 测试环境 | 线上环境 |
|------|----------|----------|
| 用户详情 | `Admin/admin_execute.py` | `online/online_execute.py admin` |
| 手机号→userId | `MOA/moa_execute.py`（区号 86） | `online/... moa`（区号 966） |
| 抓包 | `Tunnel/tunnel_execute.py`（alpha） | `online/... tunnel`（overseas） |
