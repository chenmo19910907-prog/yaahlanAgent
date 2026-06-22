# Recharge offer返奖活动

- 钉钉源 URL: https://alidocs.dingtalk.com/i/nodes/Gl6Pm2Db8D3xKamahZQQdOpXJxLq0Ee4
- Sheet: Recharge offer返奖活动
- 导出时间: 2026-06-22
- 表头映射: 功能模块 / 用例步骤描述 / 预期结果（自动识别）

## 功能模块：Recharge offer返奖活动

| 功能模块 | 用例步骤描述 | 预期结果 |
|---------|------------|---------|
| Recharge offer返奖活动 | 入口 | 房间页banner |
| Recharge offer返奖活动 | 入口 | 钱包页banner |
| Recharge offer返奖活动 | 入口 | 开屏 |
| Recharge offer返奖活动 | 入口 | IM消息 |
| Recharge offer返奖活动 | 入口 | 点击banner跳转至H5页面 |
| Recharge offer返奖活动 | 活动开始时间 | 周充值:沙特时间周一00:00-暂定<br>月充值:自然月00:00 |
| Recharge offer返奖活动 | 活动结束时间 | 周充值:周日23:59:59<br>月充值:自然月最后一天<br>不取消展示 |
| Recharge offer返奖活动 | 具体玩法说明 | 通过特定渠道充值获得返利 |
| Recharge offer返奖活动 | 具体玩法说明 | 分为周充值和月充值 |
| Recharge offer返奖活动 | 具体玩法说明 | 充值累计到对应钻石获得奖励 |
| Recharge offer返奖活动 | 具体玩法说明 | 页面展示累计数据 |
| Recharge offer返奖活动 | UI逻辑交互 | 进入活动H5页面,页面顶部有头图 |
| Recharge offer返奖活动 | UI逻辑交互 | 左上角返回按钮点击返回上一级页面 |
| Recharge offer返奖活动 | UI逻辑交互 | 右上角是规则入口,点击唤起规则说明弹窗,点击空白处收起 |
| Recharge offer返奖活动 | UI逻辑交互 | 头图下方展示周充值tab和月充值tab,支持切换,默认展示在周充值tab上 |
| Recharge offer返奖活动 | UI逻辑交互 | tab下方展示时间,格式:DD:HH:MM:SS |
| Recharge offer返奖活动 | UI逻辑交互 | 活动结束展示00:00:00:00 |
| Recharge offer返奖活动 | UI逻辑交互 | 结束后再次进入活动页toast提示活动已结束 |
| Recharge offer返奖活动 | UI逻辑交互 | 时间下方展示充值的钻石数,切换tab,变更文案 |
| Recharge offer返奖活动 | UI逻辑交互 | 区分上一周/上一月、这一周/这一月 |
| Recharge offer返奖活动 | UI逻辑交互 | 返奖板块卡片title展示宝箱+文案:Recharge progress,下方有具体进度:X/达标钻石数+💎。X为充值的钻石数,默认为0 |
| Recharge offer返奖活动 | UI逻辑交互 | 卡片区域展示返奖奖品,包含icon+文字描述 |
| Recharge offer返奖活动 | UI逻辑交互 | 不同档位返奖不同 |
| Recharge offer返奖活动 | UI逻辑交互 | 卡片吸底有按钮,支持点击,不同根据完成度展示不同的文案,未完成展示去充值,已完成点击去领取 |
| Recharge offer返奖活动 | 充值有效规则 | 通过钱包页充值-原生、三方充值成功算有效 |
| Recharge offer返奖活动 | 充值有效规则 | 首充、充值转盘充值的不累计 |
| Recharge offer返奖活动 | 充值有效规则 | 通过语音房送礼充值和水果机下注充值、礼物墙、1v1送礼充值、个人页谁看过我、装扮商城算有效充值 |
| Recharge offer返奖活动 | 充值有效规则 | 不累计:通过金币兑换钻石、签到、邀请好友加入APP、榜单TOP3奖励钻石、有奖征集、水果机下注获得奖励钻石、以及转盘抽奖和活动奖励下发获得奖励钻石 |
| Recharge offer返奖活动 | 充值有效规则 | vip充值保级充值算有效累计,币商这种渠道除外 |
| Recharge offer返奖活动 | 玩法规则-周充值 | 进入活动页展示周充值的页面数据,点击右上角规则弹出周规则的说明 |
| Recharge offer返奖活动 | 玩法规则-周充值 | 下方卡片展示周充值的返奖卡片,未完成底部按钮展示去充值,点击跳转至钱包页展示充值。 |
| Recharge offer返奖活动 | 玩法规则-周充值 | 充值完之后回到活动页,卡片上title的钻石数会自增。 |
| Recharge offer返奖活动 | 切换tab | 切换tab,进度共享么?周充值月充值同时满足获得双倍返奖么? |
| Recharge offer返奖活动 | 返奖规则 | 充值满足多个返奖门槛,支持点击领取 |
| Recharge offer返奖活动 | 领取状态 | 当前充值达标了,卡片下的按钮文案变为领取。点击触发领取,按钮变为已领取且置灰 |
| Recharge offer返奖活动 | 玩法规则-月充值 | 进入活动页,切换到月充值展示月充值的数据 |
| Recharge offer返奖活动 | 玩法规则-月充值 | 下方卡片展示月充值的返奖卡片,未完成底部按钮展示去充值,点击跳转至钱包页展示充值。 |
| Recharge offer返奖活动 | 玩法规则-月充值 | 充值完之后回到活动页,卡片上title的钻石数会自增。 |
| Recharge offer返奖活动 | 玩法规则-月充值 | 存在币商和充值都有的时候,只统计充值的部分 |
| Recharge offer返奖活动 | IM下发 | 充值达标,下发站内信,小助手自动下发 |
| Recharge offer返奖活动 | IM下发 | 文案:恭喜您获得充值奖励!包括奖励A、奖励B、奖励C<br>奖励A为奖励名称 |
| Recharge offer返奖活动 | IM下发 | 如果获得的是钻石奖励,明细中展示文案:充值奖励 |
| Recharge offer返奖活动 | IM下发 | IM消息支持点击? |
| Recharge offer返奖活动 | IM下发 | 如果获得的是道具奖励,领取自动下发到我的装扮页,相同的奖励自动累加天数,支持佩戴 |
| Recharge offer返奖活动 | 道具奖励策略 | 如果是房间背景、座驾、入场动效等,佩戴上进入语音房应生效。 |
| Recharge offer返奖活动 | 道具奖励策略 | 如果是头像框,获得之后不会自动佩戴,在我的装扮上点击佩戴即生效 |
| Recharge offer返奖活动 | 道具奖励策略 | 在我的资料页、mini资料卡、语音房上麦麦位、榜单、在线列表、榜单页「房间list榜单」、房间内PK、小时榜、魅力榜、房间榜等要展示头像框 |
| Recharge offer返奖活动 | 后台 | 后台可以配置周充值、月充值奖励 |
| Recharge offer返奖活动 | 后台 | 修改提交后,区分周充值和月充值 |
| Recharge offer返奖活动 | 后台 | 周充值修改提交后,下周生效<br>月充值修改提交后,下个月生效 |
| Recharge offer返奖活动 | 风控 | 不接入风控,控制库存即可。 |
| Recharge offer返奖活动 | 活动结束未领取 | 用户达标未领取,活动结束后,点击领取提示活动已结束。 |
| Recharge offer返奖活动 | 异常场景-边缘时间 | 在充值期间,活动结束,充值成功的记录累计上,如果达标了,领取是否有效? |
| Recharge offer返奖活动 | 前后台/小窗 | 用户在活动页充值前后台切换/语音房小窗进入活动页充值成功,下次进入活动更新数据 |
| Recharge offer返奖活动 | 前后台/小窗 | 页面不自动刷新 |
| Recharge offer返奖活动 | 小屏手机 | 小屏手机在活动页展示正常,卡片奖励能正常展示 |
| Recharge offer返奖活动 | 弱网 | 弱网页面加载失败,正常提示网络问题,请求到数据展示正常展示 |
| Recharge offer返奖活动 | 镜像 | 切换阿语,页面展示镜像+阿语,注意镜像的数据显示 |
