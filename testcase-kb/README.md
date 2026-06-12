# testcase-kb · 用例知识库

> **特权 VIP**：[`特权VIP.md`](特权VIP.md)
> **历史 Bug 归档**：[`../bug-kb/README.md`](../bug-kb/README.md)
> **线上问题归档**：[`../online-kb/README.md`](../online-kb/README.md)

由**钉钉目录中的版本测试用例 Excel** 提炼为**产品规则 / 验收要点**知识库（非逐条执行用例）；**同父类型合并为单个 md**；**独立功能单独成库**。

**版本号**：每个功能点下的场景会保留 `> **版本**：\`vX.Y.Z\``（及可选 `摘录自` 钉钉表格名），对应该条规则**同步时的来源版本**；同主题冲突合并时**保留较新版本条目**。若显示 `—`，说明当前正文已无来源元数据，需重新跑同步脚本。

**人员信息**：同一场景块在版本行下方可选保留 `> **人员**：设计 \`张三\` · 测试 \`李四\``（及可选产品、开发），从用例表 **表头上方**（「设计人」「测试人」等行）自动提取；目录标题仍会去掉负责人后缀，但正文元数据会保留。

与 `documents/` 下业务参考文档的关系：`documents/` 为模块说明与 PRD 对齐入口；**本目录**为从版本用例表汇总的大模块验收知识库。

## 同步来源（钉钉，推荐）

模块文档：[`DingTalk/README.md`](../DingTalk/README.md)、[`DingTalk/使用方法.md`](../DingTalk/使用方法.md)
Agent 技能：[`dingtalk-folder-list`](../.cursor/skills/dingtalk-folder-list/SKILL.md)

默认目录配置见 [`DingTalk/config/kb.json`](../DingTalk/config/kb.json)（当前为团队用例目录节点）。

```bash
# 列举目录下全部表格链接（144 个等，导出 JSON/CSV）
python3 DingTalk/collect_execute.py --only-spreadsheet
python3 DingTalk/collect_execute.py --output ~/Documents/cursor-mcp/dingExcel/folder-links.json

# 列举目录内可同步的版本 Excel（不写库）
python3 DingTalk/kb_sync_execute.py --list-only

# 全量同步 → testcase-kb/，并按版本升序覆盖；结束后自动跑优化流水线
python3 DingTalk/kb_sync_execute.py

# 指定目录或单个表格
python3 DingTalk/kb_sync_execute.py --folder-url "https://alidocs.dingtalk.com/i/nodes/XXXX"
python3 DingTalk/kb_sync_execute.py --workbook-url "https://alidocs.dingtalk.com/i/nodes/YYYY"

# 仅同步某一版本
python3 DingTalk/kb_sync_execute.py --only-version 2.5.2

# 不同步后优化（仅增量写入时）
python3 DingTalk/kb_sync_execute.py --no-optimize
```

**鉴权**（与 MCP 相同，读 `.cursor/mcp.json`）：

| 用途 | 变量 / MCP |
|------|------------|
| 列举目录 | `dingtalk-doc` → `DINGTALK_COOKIE` |
| 读取表格 | `dingtalk-excel-read` → `DINGTALK_AEGIS_*` / `DINGTALK_WORKID` |

**冲突规则**：按文件名解析 `vX.Y.Z`，**从小到大**依次处理；同名「功能模块」块由**较新版本覆盖**。全量同步结束后 `kb_optimize_pipeline.py` 会做跨块去重与矛盾合并（仍取较新来源）。

本地 xlsx 回退（可选）：`python3 scripts/xlsx_kb_sync.py --file /path/to/2.5.2版本用例.xlsx`

## 文件列表（25 个）

### 独立功能（跨模块抽取，强相关才拆出）

| 文件 | 说明 |
|------|------|
| [`特权VIP.md`](特权VIP.md) | 特权 VIP 等级、成长值、专属特权、定制头像框/座驾、VIP 客服 |
| `神秘人.md` | 神秘人身份、特权页、资料卡、语音变声 |
| `贵族.md` | 贵族等级、特权、贵族礼物与展示 |
| `财富等级.md` | 财富/魅力等级、等级改版与进度 |
| `收藏展馆.md` | 收藏展馆、成就收藏、礼物收集挑战 |
| `注册登录.md` | 注册、登录、注销、账号绑定、密码、黑名单与白名单 |
| [`CP好友关系.md`](CP好友关系.md) | CP/好友关系、亲密度、关系空间、关系特权、关系外显 |
| [`个人主页.md`](个人主页.md) | 个人主页（profile）、资料页、资料编辑/修改、靓号、资料页背景 |
| [`装扮.md`](装扮.md) | 装扮商城、我的装扮、装扮购买与佩戴/使用 |

### 房间切片

| 文件 | 说明 |
|------|------|
| `房间红包.md` | 红包与宝箱（强相关） |
| `房间成员.md` | 成员与等级（强相关） |

### 业务父模块

| 文件 | 说明 |
|------|------|
| `房间.md` | 麦位、进房等（红包/成员已切片） |
| `房间PK.md` | PK / 跨房 PK |
| `礼物.md` | 面板送礼、勋章、背包等 |
| `消息.md` | IM、私聊群聊、关系链等 |
| `币商.md` | 币商身份、押金、商户榜单、币商运营位等强相关 |
| `充值提现转账.md` | 充值、提现、转账、钻石明细、钱包转账等 |
| `家族.md` | 创建加入、成员、任务等级等 |
| `主题房.md` | 主题活动 |
| `动态.md` | 发布浏览 |
| `客服.md` | 客服系统、券包、快捷回复、评价等 |
| `超管.md` | 超管后台、审核、设备拉黑、工单等 |
| `游戏.md` | 游戏 |
| `公会.md` | 公会、公会长、预提等 |
| `榜单与活动.md` | 榜单与活动 |
| `人脸认证.md` | 真人认证 |
| [`测试机.md`](测试机.md) | 团队测试机台账（mmuid/mmuidv3、资产编号、持有人；数据源为 `test_devices.json`） |

## 文档结构

```
# 父模块名
> 文档类型 / 说明表
## 目录
## {业务主题}                 ← 原 Excel Sheet 或业务域主题
### {功能点}
> **版本** / **人员**（可选）
**{场景}** + 规则要点列表
```

体例改写：`python3 scripts/kb_knowledge_style.py`（同步后由 `kb_optimize_pipeline.py` 自动应用）。

## 维护命令

```bash
python3 DingTalk/kb_sync_execute.py          # 推荐：钉钉目录 → testcase-kb
python3 scripts/kb_optimize_pipeline.py      # 单独重跑：重分类 + 去重/矛盾 + 标题清理

python3 scripts/kb_merge_parents.py
python3 scripts/kb_extract_features.py
python3 scripts/kb_reclassify.py
python3 scripts/kb_clean_toc_titles.py
python3 scripts/kb_unify_modules.py
python3 scripts/kb_optimize_all.py
python3 scripts/kb_filter_locales.py
python3 scripts/kb_filter_version_compat.py

python3 scripts/sync_test_devices_kb.py --xlsx <外部xlsx>  # 测试机台账（独立）
```
