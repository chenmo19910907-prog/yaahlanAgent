# Yaahlan-1.22.0版本需求.adoc

> **文档类型**：产品需求文档（PRD）
> **来源**：[Yaahlan-1.22.0版本需求.dlink](https://alidocs.dingtalk.com/i/nodes/R1zknDm0WR3AZLeLhaPajv2NVBQEx5rG)
> **版本**：`v1.22.0`
> **同步时间**：2026-06-12 14:27:41 +0800

## 正文

礼物面板运营位样式升级（如图），所有礼物面板均做调整
礼物选择框若选中有礼物介绍的礼物（如幸运礼物），则运营位展示描述文案，超长时进行循环滚动播放，用户可手动滑动切换至下一张运营图
若礼物选择框选中的是非说明类礼物，则正常展示运营banner，多个时，3秒自动轮播
运营位配置后台增加“礼物面板”运营位类型

流量卡售卖H5页面，静态展示页面，文案：主标题【导流卡】、【5999】【有效期7天】、【原价：9999】、按钮【立即购买】、【功能介绍】、【购买后流量卡将放置在你的礼物背包中】、【在喜欢的房间里赠送流量卡，你的房间将在推荐列表2号位固定展示展示10分钟，为房间带来大量真实观众（若用多个房间同时使用，将随机出现）】、提示文案【注：为保证导流效果，传送门礼物有30分钟冷却期，若30分钟内房间收到过该礼物，则需等待30分钟后才能赠送。】
交互：点击【立即购买】按钮，弹窗二次确认【温馨提示】、【你将花费5999钻石购买“流量卡”道具，购买后有效期为7天】【确定】【取消】，页面滑过购买按钮后吸底展示购买入口，文案【当前：】、【原价】、【购买】
逻辑：用户购买流量卡后为用户下发特定背包礼物（ID：待补充），用户在房间内使用该背包礼物后，冷启任务弹窗则均（10分钟）跳转至该房间（有多个房间使用，则多个房间随机跳转），同时，在语音房推荐列表二号位固定展示该房间（新增特殊样式标识），有多个房间使用则随机出（对于房主和使用者则只出他们使用道具的那个房间）
预埋：在所有房间的右下角、语音房推荐帧右下角预埋一个传送入口，用户点击该入口跳转至对应房间（服务端控制落地房间），该入口我为动效展示，动效时间为5秒，由服务端控制下发给哪些用户
特殊情况提示文案：
30分钟内仅可送一次频控【当前尚在冷却中，x分钟后可赠送】
一次送多个【一次仅可赠送一个】
房间外使用【该礼物仅限房间内赠送】
测试环境
礼物ID：2005002235
category：2005002240
source：2005000189
signKey:60258b4d4e7940d58f10b4858e8b84f9
正式环境
礼物ID：2005002650
category：2005002653
source：2005000051
signKey:6fff4d6e20744f2591baf2589e9ba541

房间面板增加房间icon展示，可点击查看大图，大图模式下普通用户展示【返回】按钮，点击关闭大图；房主展示“编辑按钮”和【返回】，点击编辑按钮关闭大图并打开房间编辑模式，唤起头像上传选择半弹窗（动图、相册、取消那个弹窗）；巡查展示“编辑按钮”和返回，点重置进行弹窗二次确认【温馨提示】【你正在将该房间头像重置为房主头像，该操作不可逆，请谨慎确认是否有违规行为】【取消】【确定】，点击确定，将该房间头像重置为房主当前头像，并为房主下发处罚IM通知【你的房间头像因涉嫌违规，已被管理员删除，请认真遵守平台规则，谨慎操作】【去看看>>】点击跳转至个人语音房设置页
房间面板增加房间粉丝数量，放置在成员行下发，不可点击，房间在线人数移至房间icon右侧，可点击，点击唤起房间在线用户半弹窗

C：普通用户
B：有打赏倾向用户：无充值有消耗
A：有付费潜力人群：渠道(是买量和自然量) campaign 包含purchase 或者 是-1 或是空
S：有付费行为人群：用充值有消耗
S-：vip小于等于2
S+：vip大于2
N:新户 3天内新户
levelB  素人主播：
C：无打赏
B：打赏1$以下
A：1-5$
S：5$+
levelA  工会主播：
C：无打赏
B：打赏1$以下
A：1-5$
S：5$+
N：7日内新主播
1号位：固定客服房
2号位：流量卡推荐房（多个房间时随机出）
3号位：小时榜第一房间
从4号位开始，房间进行推荐排序：
排序分值计算：（麦上人数*0.8+围观人数*0.2+当日有打赏行为的在房人数*0.4）同国家*1.2
强过滤：空房间、关闭房、密码房、满房
房间分为三类：推荐、强插、扶持（新房）

N:
7：2：1
v1：
zczh_grouplevelA_A
zczh_grouplevelA_B
zczh_grouplevelA_C
zczh_grouplevelB_A
zczh_grouplevelB_B
v2：
zczh_grouplevelA_B
zczh_grouplevelA_C
zczh_grouplevelA_N
zczh_grouplevelB_B
zczh_grouplevelB_C
v1：
zczh_grouplevelA_N
zczh_grouplevelA_S
zczh_grouplevelB_S
v2：
zczh_grouplevelA_A
zczh_grouplevelA_S
zczh_grouplevelB_S
zczh_grouplevelB_A
S+
v1:
7：2：1
v1:
zczh_grouplevelA_S
zczh_grouplevelA_A
zczh_grouplevelB_S
zczh_grouplevelB_A
v1:
zczh_grouplevelA_N
zczh_grouplevelA_B
zczh_grouplevelA_C
zczh_grouplevelB_B
S-
6：3：1
zczh_grouplevelA_S
zczh_grouplevelA_A
zczh_grouplevelA_B
zczh_grouplevelB_S
zczh_grouplevelB_A
zczh_grouplevelA_C
zczh_grouplevelA_N
zczh_grouplevelB_B
A
6：3：1
v1:
zczh_grouplevelA_S
zczh_grouplevelA_A
zczh_grouplevelA_B
zczh_grouplevelA_N
zczh_grouplevelB_A
v2:
zczh_grouplevelA_S
zczh_grouplevelA_A
zczh_grouplevelA_B
zczh_grouplevelA_N
v3:
zczh_grouplevelA_S
zczh_grouplevelA_A
zczh_grouplevelA_B
zczh_grouplevelA_N
zczh_grouplevelB_B
V4：
zczh_grouplevelA_B
zczh_grouplevelA_N
zczh_grouplevelB_A
zczh_grouplevelB_B
zczh_grouplevelB_C
v1:
zczh_grouplevelA_C
zczh_grouplevelB_S
zczh_grouplevelB_B
v2:
zczh_grouplevelB_S
zczh_grouplevelB_A
zczh_grouplevelB_B
v3:
zczh_grouplevelB_S
zczh_grouplevelB_A
v4：
zczh_grouplevelA_S
zczh_grouplevelA_A
zczh_grouplevelA_C
zczh_grouplevelB_S
B
7：1：2
zczh_grouplevelA_A
zczh_grouplevelA_B
zczh_grouplevelA_C
zczh_grouplevelA_N
zczh_grouplevelB_B
zczh_grouplevelA_S
zczh_grouplevelB_S
zczh_grouplevelB_A
zczh_grouplevelB_C
C
7：1：2
zczh_grouplevelA_B
zczh_grouplevelA_C
zczh_grouplevelA_N
zczh_grouplevelB_B
zczh_grouplevelB_C
zczh_grouplevelA_A

钱包页、重置半弹窗增加checkout充值档位，档位图标和档位文案（需与payermax渠道的visa支付方式的文案有所区别）应该是中台侧下发（需确认）
在该充值渠道下，点充值，跳转至卡信息填写页（这部分逻辑复用SC，已开通代码权限，排期时，前端需有1人日的调研成本）

接入技术文档
接入位置消息帧的激励视频广告、动态详情的贴片广告（游戏内暂不处理）
接入后平台内的一半用户从三方广告聚合平台进行广告请求

1
mini-profile 昵称后面增加房主/管理/成员图标（去掉麦位上的这三个图标），已关注用户的mini-profile为左下角为“聊天”按钮
2
App icon 增加未读消息气泡外显数值为消息帧未读气泡数+我帧未读消息气泡数之和
3
头像框支持apng格式
4
语音房麦上展示表情包
5
星光计划奖励下发IM通知消息，文案【恭喜你，在Yaahlan STAR中获得x，快去看看你的成绩吧】【去看看】点击，跳转至星光计划上一周期页面（x为获得的主播段位名称）
6
礼物连送，连送结束后再开始播放礼物动效
7
私聊/动态 送收礼计入到全服榜单计算中
8
主播工作数据，后台实时导表
9
增加预下单流程，判断是否首充过，点击档位先走预下单，预下单通过，唤起google/apple支付的收银台
10
游戏漏斗统一ID

活动需求
幸运之王活动三期
上线时间：5.1~5.7
谁是大赢家二期（无改动）
上线时间：4.26~4.30
充值转盘活动奖励替换
新增活动奖励类型：水果机券（需要立兵确认三方接口支持并提供水果机券icon）
普通转盘奖励替换：
入场特效改为：水果机券*1钻*10张
VIP转盘奖励替换：
200钻改为：水果机券*200钻*1张
上线时间：4.30
“铭牌”可作为活动奖励支持手动下发指定UID，并配置下发有效期
铭牌页展示：活动开始时配置展示在铭牌页，「obtain」跳转为活动URL，点击可跳转活动页；活动结束后未获得用户不再展示，获得用户在有效期内展示（状态点亮解锁），并增加倒计时展示，失效后取消展示
