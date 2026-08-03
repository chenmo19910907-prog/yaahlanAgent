# Yaahlan 能力全量导出包（含依赖脚本与 JSON）

## 目录

- `capabilities/` — 218 项能力 bundle（schema 1.0）
- `runtime/<模块>/` — Admin/MOA/… 共 10 模块脚本、registry、templates、workflows
- `platform/config/sources.json` — 模块登记
- `platform/dingtalk_gateway/` — 工作流依赖的部分导出脚本与 config（非全量网关）
- `MANIFEST.json` — 文件统计

## 注意

- **不含** `.env.local` / 鉴权 token，目标环境需自行配置
- MOA/Admin 等需 `pip install -r requirements.txt` 后按 bundle 中 command 执行
