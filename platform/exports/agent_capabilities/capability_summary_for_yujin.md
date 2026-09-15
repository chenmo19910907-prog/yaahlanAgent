# Yaahlan 智能工具 Agent · 能力清单

## 提供形式

- **自然语言对话**：Web Agent / 钉钉私聊 / 钉钉群 @Agent，用口语描述需求即可
- **工具台目录**：`python3 platform/open_catalog.py` → http://127.0.0.1:18765/catalog.html，搜索能力名/分类，点击「执行」填入 Cursor
- **CLI 脚本**：各模块 `*_execute.py`，registry 登记 command 可直接跑
- **工作流**：`python3 workflow/workflow_execute.py run <流程名> --param key=value`
- **Skills**：`.cursor/skills/` 下专项技能，Agent 对话时自动匹配触发
- **服务端 Agent**（可选）：查后端源码/MOA 注册/接口定义

## 模块总览（共 **309** 项）

| 模块 | 环境 | 能力数 | Playbook | 入口 |
|------|------|--------|----------|------|
| yaahlan后台 | test | 41 | 0 | `python3 Admin/admin_execute.py` |
| MOA | test | 154 | 0 | `python3 MOA/moa_execute.py` |
| MOA-generative | test | 25 | 0 | `python3 MOA-generative/scripts/run_generative_moa.py` |
| MSE配置 | test | 9 | 0 | `python3 MSE/mse_execute.py` |
| Stage送礼 | test | 7 | 0 | `python3 Gift/gift_execute.py` |
| 风险控制 | test | 12 | 0 | `python3 Risk/risk_execute.py` |
| Tunnel抓包 | test | 11 | 0 | `python3 Tunnel/tunnel_execute.py` |
| 线上环境能力 | online | 5 | 0 | `python3 online/online_execute.py` |
| 钉钉文档 | tool | 13 | 0 | `python3 DingTalk/lookup_execute.py` |
| 工作流 | tool | 25 | 4 | `python3 workflow/workflow_execute.py` |
| Web Agent | tool | 3 | 0 | `python3 platform/web_agent/open_web_agent.py` |

## yaahlan后台（41 项）

### 公会（melon-gateway / cms/anchor）（4）
- 公会-用户加入
- 公会-用户移除
- 公会-用户转移
- 公会-查询信息

### 大R用户管理（yaahlan-admin）（8）
- 大R-列出API
- 大R-查询列表
- 大R-用户明细
- 大R-冒烟验收
- 大R-生成可视化报告
- 大R-校验排序
- 大R-校验搜索
- 大R-造数导入

### 定制座驾（yaahlan-admin）（1）
- 定制座驾-重置上传冷却

### 定制礼物（melon-gateway）（1）
- 定制礼物-查询列表

### 定制礼物（yaahlan-admin）（1）
- 定制礼物-重置上传时间

### 定制装扮工作流（MOA + Admin）（2）
- 定制头像框-开通流程
- 定制座驾-开通流程

### 定制道具（yaahlan-admin）（1）
- 定制头像框-重置上传冷却

### 客服（melon-gateway / cms/customerservice）（3）
- 客服-查询账号列表
- 客服-新增/编辑账号
- 客服-修改接单状态

### 家族（melon-gateway）（3）
- 家族-查询信息
- 家族-查询全部列表
- 家族-增加成员

### 活动（melon-gateway / cms/activity）（4）
- 活动-查询奖池配置列表
- 活动-IM六种消息类型定时下发
- 活动-查询IM配置任务列表
- 活动-删除IM配置任务

### 活动（melon-gateway / cms/backend/banner）（1）
- 活动-查询Banner列表

### 版本（melon-gateway / backend/pangu）（2）
- 版本-查询 App Store 审核版本
- 版本-设置 App Store 审核版本

### 用户（mdp-nova / userAdmin + MOA）（1）
- 用户-批量互关结好友

### 用户（mdp-nova / userAdmin）（2）
- 用户-查询列表
- 用户-注销账号

### 用户（yaahlan-admin）（5）
- 用户-查询详情
- 用户-查询动态列表
- 用户-查询历史登录设备
- 用户-查询设备历史登录账号
- 设备-查询当前登录账号

### 礼物（mdp-nova / giftAdmin）（1）
- 礼物-查询列表

### 道具（mdp-nova / propAdmin）（1）
- 道具-查询配置列表


## MOA（154 项）

### CP·MOA（yaahlan/user/cp-moa）（1）
- CP总恩爱值-增加

### CP·摩天轮（vas/external/cp-stage）（4）
- CP摩天轮-设置档位
- CP摩天轮-发放档位积分返奖
- CP摩天轮-发放周榜奖励
- CP摩天轮-增加周期值

### PK提款机（room/internal/room-pk）（1）
- PK提款机-0点公屏活动卡片

### PK榜（room/external/room-admin-handle）（3）
- PK榜-周结算发奖
- PK榜-查询数值
- PK榜-增加PK值

### VIP 经验值（voga-mts-user-vip-stage）（5）
- VIP经验值-增加
- VIP等级-升级到目标等级
- VIP经验值-查询当前等级经验
- VIP等级-清除VIP信息
- VIP体验卡-下发

### 全服榜单（room/external/room-admin-handle）（5）
- 房间-下发小时榜全服通知
- 用户榜单-奖励下发（贡献/魅力 周榜/日榜/月榜）
- 贡献日榜-奖励下发
- 魅力日榜-奖励下发
- 房间日榜-奖励下发

### 公会（yaahlan-anchor-recruit-moa-stage）（1）
- 用户-查所属公会

### 动态（/v2/gift/send · Stage HTTP）（1）
- 动态-帖子送礼

### 动态（feed-comment-stage）（1）
- 动态-帖子评论

### 动态（feed-interact-stage）（1）
- 动态-评论点赞

### 动态（feed-stage）（1）
- 动态-发布

### 奖励排查（通用）（2）
- 奖励未下发-拦截排查
- 奖励下发-风控预检

### 奖励验收（通用）（4）
- 星礼包-查询配置
- 奖励验收-用户资产快照
- 奖励验收-发奖前后求差
- 奖励验收-对照期望配置

### 定制礼物榜单（room/internal/room-rank-list-stage）（2）
- 定制礼物榜单-增加活跃值
- 定制礼物榜单-清除数据

### 定制礼物（voga-components/gateway/custom-gift-stage）（1）
- 定制礼物-重置上传次数

### 宝藏猎人（vas/external/treasure-hunter-stage · dispatchRankPrize）（1）
- 宝藏猎人-下发榜单奖励

### 宝藏猎人（vas/external/treasure-hunter-stage · prizeDraw）（1）
- 宝藏猎人-翻牌抽奖

### 实名认证（internal/user/id-auth-api）（5）
- 实名认证-查询认证记录
- 实名认证-解决认证失败（清 reason 关联账号）
- 实名认证-设置认证过期时间
- 实名认证-按场景删除真人认证
- 实名认证-清除认证信息

### 客服（/v2/report/submit · Stage HTTP）（1）
- 用户-举报用户

### 家族PK（vas/activity/family-pk-v2-api）（2）
- 家族PK-成员贡献列表
- 家族PK-请求页面

### 家族PK（vas/internal/family-pk-moa）（8）
- 家族PK-修改收礼日榜
- 家族PK-查询收礼日榜
- 家族PK-增加PK值
- 家族PK-结算发奖匹配
- 家族PK-清除匹配数据
- 家族PK-删除全部PK值
- 家族PK-查询收礼日榜
- 家族PK-清除结算奖励

### 家族怪兽（vas/internal/family-monster · getMonsterDetail）（1）
- 家族怪兽-查当前等级血量

### 家族怪兽（vas/internal/family-monster）（1）
- 家族怪兽-重置进度

### 家族怪兽（yh-components/gift-panel · getGiftPanel）（1）
- 家族怪兽-查房间伤害

### 家族（external/user/family-api）（3）
- 家族-移除成员
- 家族-踢出成员
- 家族-解散家族

### 家族（internal/user/family-moa）（18）
- 家族-增加声望值
- 家族-衰减声望值
- 家族-设置基金档位
- 家族基金-清除档位缓存
- 家族-设置基金返奖钻石
- 家族基金-奖励下发
- 家族基金-清除奖励下发记录
- 家族-增加基金贡献值
- … 等共 18 项

### 房间PK（room/external/room-pk-api）（11）
- 跨房PK-指定邀请
- 跨房PK-随机匹配
- 跨房PK-接受邀请
- 跨房PK-结束PK
- PK提款机-PK结束返钻弹窗
- PK提款机-提款排名
- 乱斗PK-创建
- 1V1PK-创建
- … 等共 11 项

### 房间PK（room/internal/room-pk）（1）
- 跨房PK-周榜结算

### 房间成员等级（room-user-active-stage）（2）
- 房间成员-增加陪伴值
- 房间成员-升级到目标等级

### 房间成员（voga-mts-room-backdoor）（1）
- 房间成员-快速添加

### 房间测试（room/internal/room-test-stage）（1）
- 房间-设置等级

### 房间经验值（voga-mts-room-backdoor）（10）
- 房间经验值-增加
- 房间等级-升级到目标等级
- 房间经验值-查询当前等级经验
- 房间-房主未回房触发降级
- 房间-房主未回房真实降级（含弹窗标记）
- 房间-房主未回房降级（保持当前等级）
- 房间-查询等级页衰减弹窗
- 房间-等级页衰减弹窗Mock
- … 等共 10 项

### 房间（room-member-stage）（2）
- 房间成员-同意申请
- 房间成员-申请加入

### 房间（room/external/room-share-stage）（2）
- 房间-发红包
- 房间-抢红包

### 房间（room/internal/room-notice-stage）（1）
- 房间-发言飘屏（内部）

### 房间（voga-mts-room-backdoor）（1）
- 房间-等级页衰减弹窗-Mock说明

### 房间（yaahlan/room/external/room-im-api）（1）
- 房间-发言飘屏（对外）

### 支付测试（pay-middle/test）（1）
- 送礼限制-查询测试账号

### 活动（3周年砸金蛋）（6）
- 3周年砸金蛋-查神秘保底计数
- 3周年砸金蛋-造数并记录钉钉表
- 3周年砸金蛋-MSE配置同步钉钉表
- 3周年砸金蛋-奖池配置同步钉钉表
- 3周年砸金蛋-多账号批量验收落表
- 3周年-砸金蛋测试

### 活动（3周年）（1）
- 3周年-兑换道具

### 活动（Ultra Recharge / 充值返利）（4）
- 充值返利-模拟充值
- 充值返利-增加流水
- 充值返利-添加黑名单
- 充值返利-删除黑名单

### 活动（vas/gift-call-back）（1）
- 活动-模拟送礼

### 消息（voga-base-service-im-stage）（2）
- 私聊-发送消息
- 用户-联系客服发消息

### 用户关系（voga-mts-user-relation-stage）（3）
- 用户-关注好友
- 用户-手机号段全互关
- 用户-批量互关好友（用户列表）

### 用户后门（voga-mts-user-backdoor）（7）
- IP-查询归属地
- 用户-修改注册国家
- 用户-设置注册时间
- 用户-查询注册时间
- 用户-注销账号
- 魅力-查询等级
- 财富-查询等级

### 用户大区（yaahlan/components/callback/user-area）（1）
- 用户-修改大区

### 用户工具（voga-mts-user-tool-stage）（2）
- 用户-批量发消息
- 用户-批量发招呼消息

### 用户活跃（yaahlan/user/internal/area-moa）（1）
- 用户-查询登录天数

### 用户登录（yaahlan/mdp-user-login）（1）
- 用户-按手机号查 userId

### 用户装扮（mdp-prop/user-prop-api-service-test）（1）
- 装扮-查询用户拥有道具

### 用户资料（voga-mts-user-profile-stage）（1）
- 用户-查看 app 语言

### 礼物统计（vas/internal/gift-statistics-stage）（4）
- 财富-增加
- 魅力-增加
- 财富-减少
- 魅力-减少

### 礼物面板（yh-components/gift-panel）（3）
- 礼物面板-查看背包
- 礼物面板-查看背包礼物
- 礼物面板-查看背包道具

### 背包礼物（voga-base-service-middle-gift-stage）（3）
- 背包礼物-下发
- 背包礼物-送礼
- 背包礼物-Tunnel背包验收

### 贵族（voga-mts-user-wealth-charm-level-stage）（2）
- 贵族-增加月消费值
- 贵族-升级到目标等级

### 钻石（voga-base-service-middle-pay-stage）（2）
- 钻石-查询余额
- 钻石-发放


## 工作流（25 项）

### 3周年活动（2）
- 3周年砸金蛋-造数并记录
- 3周年砸金蛋数据测试（六步总览）

### CP·亲密关系（2）
- 亲密关系-结挚友
- 亲密关系-结CP

### CP·爱意宝箱（1）
- CP爱意宝箱-奖励下发验收

### PK提款机（1）
- PK提款机-跨房PK造数验收

### 奖励验收（5）
- 奖励验收-用户资产快照
- 奖励验收-前后快照求差
- 奖励验收-前后快照对比
- 奖励验收-生成测试报告
- 奖励验收-装扮有效期天数

### 家族（1）
- 家族基金-测试数据准备

### 家族PK（12）
- 家族PK配置-新建测试钉钉表
- 家族PK配置-MSE同步到钉钉参数表
- 家族PK配置-后台家族成员写入钉钉
- 家族PK配置-收礼榜造数与档位测算
- 家族PK配置-重匹配与验收写入钉钉
- 家族PK配置-成员PK造数与发钻测算
- 家族PK配置-发奖与验收
- 家族PK配置-测试结果汇总
- … 等共 12 项

### 房间（1）
- 房间成员-快速添加

### 抓包（1）
- Tunnel 抓包常用验收

### 抓包转MOA（1）
- MOA-generative-抓包转MOA执行

### 背包礼物（2）
- 背包礼物-Tunnel背包验收
- 背包礼物-下发与Tunnel验收

## Agent Skills（21 个）

- **adb-page-learn**：真机页面学习、沉淀 ADB 片段
- **adb-screen-mcp**：MCP 实时读屏 observe/tap
- **adb-screenshot**：无线 ADB 截屏
- **adb-tunnel-verify**：ADB + Tunnel 抓包验收
- **autotest-p0**：P0 自动化用例生成与执行
- **complaint-analysis**：客诉 Excel 统计分析
- **device-current-account**：查测试机当前登录账号
- **dingtalk-doc-read**：读钉钉需求文档
- **dingtalk-folder-list**：列举钉钉目录/同步知识库
- **intent-test**：AI 视觉意图测试
- **platform-catalog**：打开工具台目录
- **prd-review**：PRD 评审理解
- **stage-gift-send**：测试环境 HTTP 送礼
- **testcase-generator**：从 PRD 生成测试用例
- **testcase-handwritten-excel-style**：手写用例 xlsx 风格
- **testcase-to-excel**：用例写入钉钉 Excel
- **testpoints-to-testcases**：测试点扩写用例
- **tunnel-mock**：Tunnel Mock 接口返回
- **tunnel-read**：Tunnel 查抓包
- **user-testcase-style-shortphrase**：短语两段式用例风格
- **workflow-record**：工作流录制与复用

## 工作流（25 个可执行流程）

- **家族PK配置-新建测试钉钉表**：第 0 步（新测试必做）：在配置的 alidocs 目录新建钉钉表格 {pkDate}家族PK数据测试，预建各步骤 Sheet；输出 workbookUrl 供
- **家族PK配置-MSE同步到钉钉参数表**：第一步：从 MSE voga-common 读取 familyPkConfig 最新配置，整理为参数表写入 Sheet「参数表」。merge 模式可在原表上更新
- **家族PK配置-后台家族成员写入钉钉**：第二步：从开发者后台 getAllFamilyList 拉取全部家族 ID/名称，补全成员 userId、手机号并标记族长；族长大区非中东（MENA）的家族剔除
- **家族PK配置-收礼榜造数与档位测算**：第三步：按 Sheet「家族列表」成员数分段随机写入 rankDate 收礼榜（>10 人：20 万~100 万；≤10 人：0~20 万），再按收礼榜+参数表
- **家族PK配置-重匹配与验收写入钉钉**：第四步：清除并重匹配 pkDate 家族 PK → MOA getFamilyPkPage 拉取对战列表 → 按收礼榜区间验收同区间匹配，写入 Sheet「匹配
- **家族PK配置-成员PK造数与发钻测算**：第五步：清除 pkDate 全部成员 PK → 全员随机 PK → 纠偏边界场景 → 测算应得钻石写入「用户发钻测试」（榜单验收在第六步结算后）。
- **家族PK配置-发奖与验收**：第六步：resetSettleDataForTest 清结算 → runFamilyPkMatchTask(次日) 发奖 → 查钻对比应发 vs 实发写入「发钻
- **家族PK配置-测试结果汇总**：第七步：读取各步骤 Sheet 验收摘要，汇总写入「测试结果」（总体验收结论 + 发钻不一致明细）。
- **家族PK配置-档位PK与奖励测算**：辅助：仅按收礼榜与参数表重算各家族档位达标 PK 与钻石，写入 Sheet「家族PK档位」（第三步已内置，可单独重跑）。
- **家族PK配置-钉钉参数表生成JSON**：辅助：读取 Sheet「参数表」中已修改的数值，合并回 MSE 原始结构，写回 configValue_JSON Sheet。改参后执行；勿直接声称已发布到 M
- **家族PK-重置匹配并下发前日奖励**：独立：清除 pkDate 匹配数据 → 结算前一日并发奖 → 重新匹配 pkDate。参数 pkDate、timeoutMs（默认 180000）。
- **背包礼物-Tunnel背包验收**：用户已在 App 打开礼物面板后，Tunnel 抓 getGiftTabListV3 → 背包 Tab 读 package.remain；按 bid 验收数量。
- **背包礼物-下发与Tunnel验收**：MOA addPackageGift 下发 → 用户在 App 打开礼物面板 → Tunnel getGiftTabListV3 背包 Tab 验收 packa
- **3周年砸金蛋-造数并记录**：smashEgg：房间默认自己的房间；每砸一次立即写入钉钉「砸金蛋测试记录」（砸一次写一次）。
- **MOA-generative-抓包转MOA执行**：将 Tunnel 抓包 body + 调用链 ServiceUrl/Method 生成双写 header+params 的 MOA payload 并执行。默认
- **亲密关系-结挚友**：测试环境结挚友：Gift --intimate-invite 发起（默认 gift 2005007129）→ MOA acceptIntimateInvitat
- **亲密关系-结CP**：测试环境结CP：Gift --intimate-invite 发起（默认 cpGiftList 2005004592 Neon Heart）→ MOA acce
- **房间成员-快速添加**：测试环境快速添加房间成员：MOA room-member-stage.apply（申请人）→ agree（房主）。HTTP 对应 /yaahlan/room/m
- **奖励验收-用户资产快照**：发奖前/后各执行一次：钻石余额、diamondHistory 基线、背包礼物（giftId/remain/price/expire）、装扮 props（prop
- **奖励验收-前后快照求差**：对比发奖前后 snapshot JSON，输出钻石余额/钻石记录增量、背包礼物 remain/price/expire 差值、装扮 expireTime 差值、
- **奖励验收-前后快照对比**：对比发奖前后 snapshot JSON 与期望 rewards 配置：钻石增量+钻石记录、背包礼物 giftId+数量+单价(钻)+expire 有效、装扮 
- **奖励验收-生成测试报告**：由 diff JSON 或 before/after 快照生成 Markdown 测试报告：个人装扮/铭牌每个实际下发项的有效期、礼物背包每个礼物的钻石价值与有
- **奖励验收-装扮有效期天数**：MOA queryOwnPropList 查指定 propId 的 expireTime，与配置天数对比（默认 ±1 天容差）。用于活动/宝箱等限时装扮/铭牌验
- **PK提款机-跨房PK造数验收**：2.5.9 PK 提款机完整验收：拉服务配置 → 随机匹配开 PK（双房 applyAcrossRoomPk）→ 给房主送礼 → C7/C6/C8 验收。详见 
- **家族基金-测试数据准备**：v2.4.9 家族基金造数：清本周贡献 → 设档位(A/B/C) → 加家族/成员贡献 → 查询验收；rewardDiamonds>0 时一键返奖档位。

## 其他模块速览

- **MOA-generative**（test，25项）：CP·亲密关系, CP·爱意宝箱, 动态（feed-comment-stage）, 动态（feed-interact-stage）, 家族PK（vas/activity/family-pk-v2-api） …共12类
- **MSE配置**（test，9项）：MSE 服务配置
- **Stage送礼**（test，7项）：CP·亲密关系, Stage送礼（/v2/gift/send）
- **风险控制**（test，12项）：充值风控（user_id 黑名单）, 手机号风控（phone 白名单）, 活动风控（user_id 黑名单）, 测试机（testcase-kb/test_devices.json）, 短信风控（phone 白名单） …共8类
- **Tunnel抓包**（test，11项）：Tunnel Mock, Tunnel 抓包
- **线上环境能力**（online，5项）：Admin（yaahlan-admin）, MOA（mdp-user-login · overseas）, Tunnel 抓包
- **钉钉文档**（tool，13项）：prd-kb 同步, testcase-kb 同步, 钉钉目录
- **Web Agent**（tool，3项）：Web Agent