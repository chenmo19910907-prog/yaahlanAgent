# testcase-kb · 用例知识库

> **特权 VIP**：[`特权VIP.md`](特权VIP.md)
> **发版回归用例**：[`../regression-kb/README.md`](../regression-kb/README.md)
> **历史 Bug 归档**：[`../bug-kb/README.md`](../bug-kb/README.md)
> **线上问题归档**：[`../online-kb/README.md`](../online-kb/README.md)

由版本需求 xlsx 提炼为**产品规则 / 验收要点**知识库（非逐条执行用例）；**同父类型合并为单个 md**；**独立功能单独成库**。

**版本号**：每个功能点下的场景会保留 `> **版本**：\`vX.Y.Z\``（及可选 `摘录自` xlsx 文件名），对应该条规则**上传/同步时的来源版本**；同主题冲突合并时保留较新条目，但版本标注不丢。若显示 `—`，说明当前正文已无来源元数据，需用 `scripts/xlsx_kb_sync.py` 从版本用例 xlsx 重新同步。

与 `documents/` 下业务参考文档的关系：`documents/` 为模块说明与 PRD 对齐入口；**本目录**为从用例 xlsx 汇总的大模块验收知识库。

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
**{场景}** + 规则要点列表      ← 原「步骤 / 预期」已改写为知识库体例
```

体例改写：`python3 scripts/kb_knowledge_style.py`（重分类流水线也会在生成时自动应用）。

## 维护命令

```bash
python3 scripts/kb_optimize_pipeline.py  # 推荐：重分类 + 去重/矛盾 + 标题清理 + 房间切片
python3 scripts/kb_knowledge_style.py   # 步骤/预期 → 知识库体例（已并入生成逻辑时可省略）

python3 scripts/kb_merge_parents.py      # 同类型合并为父模块
python3 scripts/kb_extract_features.py   # 拆出 特权VIP/神秘人/贵族/财富等级/收藏展馆/CP好友关系/个人主页/装扮
python3 scripts/kb_reclassify.py         # 修正误分类
python3 scripts/kb_clean_toc_titles.py  # 清理目录/Sheet 标题中的人名与括号
python3 scripts/kb_unify_modules.py      # 子域拆分/唯一命名
python3 scripts/kb_optimize_all.py       # 去重、跨文件重复、Sheet 规范化
python3 scripts/kb_filter_locales.py       # 移除土语/俄语
python3 scripts/kb_filter_version_compat.py  # 移除老版本/兼容

# 测试机台账（独立 xlsx，非版本用例库）
python3 scripts/sync_test_devices_kb.py --xlsx <外部xlsx>  # 可选：从 xlsx 更新 test_devices.json / 测试机.md

# 发版回归用例（桌面发版回归 case xlsx）
python3 scripts/regression_kb_from_xlsx.py   # → regression-kb/发版回归用例.md
python3 scripts/export_regression_case_review_xlsx.py  # → ~/Desktop/发版回归case_评审导出.xlsx
```
