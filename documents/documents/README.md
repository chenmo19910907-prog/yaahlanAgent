# documents/documents · 版本用例知识库

> **特权 VIP 用例库**：[`特权VIP.md`](特权VIP.md)

由 xlsx 汇总；**同父类型合并为单个 md**；**独立功能单独成库**。

## 文件列表（21 个）

### 独立功能（跨模块抽取，强相关才拆出）

| 文件 | 说明 |
|------|------|
| [`特权VIP.md`](特权VIP.md) | 特权 VIP 等级、成长值、专属特权、定制头像框/座驾、VIP 客服 |
| `神秘人.md` | 神秘人身份、特权页、资料卡、语音变声 |
| `贵族.md` | 贵族等级、特权、贵族礼物与展示 |
| `财富等级.md` | 财富/魅力等级、等级改版与进度 |
| `收藏展馆.md` | 收藏展馆、成就收藏、礼物收集挑战 |
| `注册登录.md` | 注册、登录、注销、账号绑定、密码、黑名单与白名单 |

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
| `币商.md` | 充值、提现、商户等 |
| `家族.md` | 创建加入、成员、任务等级等 |
| `主题房.md` | 主题活动 |
| `动态.md` | 发布浏览 |
| `其他模块.md` | 分区、活动等 |
| `客服.md` | 客服系统、券包、快捷回复、评价等 |
| `超管.md` | 超管后台、审核、设备拉黑、工单等 |
| `游戏.md` | 游戏 |
| `公会.md` | 公会、公会长、预提等 |
| `榜单与活动.md` | 榜单与活动 |
| `人脸认证.md` | 真人认证 |

## 文档结构

```
# 父模块名
## 目录
## {子域}·{Excel Sheet 名}    ← 子域来自原拆分文件前缀
### {功能模块}
```

## 维护命令

```bash
python3 scripts/kb_optimize_pipeline.py  # 推荐：重分类 + 去重/矛盾 + 标题清理 + 房间切片

python3 scripts/kb_merge_parents.py      # 同类型合并为父模块
python3 scripts/kb_extract_features.py   # 拆出 特权VIP/神秘人/贵族/财富等级/收藏展馆
python3 scripts/kb_reclassify.py         # 修正误分类
python3 scripts/kb_clean_toc_titles.py  # 清理目录/Sheet 标题中的人名与括号
python3 scripts/kb_unify_modules.py      # 子域拆分/唯一命名
python3 scripts/kb_optimize_all.py       # 去重、跨文件重复、Sheet 规范化
python3 scripts/kb_filter_locales.py       # 移除土语/俄语
python3 scripts/kb_filter_version_compat.py  # 移除老版本/兼容
```
