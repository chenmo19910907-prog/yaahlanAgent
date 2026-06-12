# Yaahlan-2.2.9版本需求.adoc

> **文档类型**：产品需求文档（PRD）
> **来源**：[Yaahlan-2.2.9版本需求.adoc](https://alidocs.dingtalk.com/i/nodes/lyQod3RxJK3gjMmMhdMqq6RmJkb4Mw9r)
> **版本**：`v2.2.9`
> **同步时间**：2026-06-12 14:27:41 +0800

## 正文

每日、每周奖励配置
1、房间内大贴片
支持可领取状态和普通状态显示；
普通状态点击打开活动页面【cp 摩天轮】tab；可领取状态点击打开“每日奖励”tab
2/3/4、礼物栏、房间列表、活动中心 banner 配置；点击默认锚定到“周榜”tab
3：房间列表，需要在后台配置为 cp 榜单样式 banner，显示 周榜top1 双方头像
1、奖励展示
做循环轮播，点击无交互；奖励类型为钻石、道具
钻石名称：具体钻石数量
道具显示：icon、名称
2、每日奖励
统计纬度：1钻石=10进度值（cp 等级礼物额外加成不计算在榜单内）
统计当天 cp 双方互相赠送礼物增加的进度值，达到指定值可领取奖励；次日重置
cp 双方的进度值在活动页面是同步增加的
交互
奖励的排序，前端需要根据设计稿按顺序排，不要乱选
区分已领取、可领取、未解锁 3 个状态；并显示所需进度值
点击已领取/未解锁状态的图标，无交互
点击可领取状态的图标，领取奖励，并展示奖励领取弹窗【2.1】；点击确认及关闭按钮关闭
达到进度值后，cp 双方均解锁奖励领取，双方各自获得1次奖励领取机会；主态显示的是自己的领取状态
奖励配置
后台配置 5 个奖池 id，每次领取时，在对应奖池开出 1 个奖品
奖励类型：钻石（显示获得数量）、道具（显示名称，过长换行）
3、吸底
主态没有 cp
显示主态头像、cp 空头像，点击打开客户端的关系邀请列表
文案“成为 CP 限时低价”
主态有 cp
显示双方头像、当日进度值
点击头像打开双方资料页；显示动态头像、头像框
1、周榜奖金
配置中心配置流水梯度奖金（与 PK 奖池一样），周榜结算后，按照排名规则发放
奖励为对应名次的 2 个人均分
获奖名次为 1-10 名，奖励类型为钻石、道具；前端做奖励轮播
2、异形周榜
榜单统计 top10cp 用户，区分黄金（展示 1-5 名）、幸福（展示 6-10 名）
若用户上榜，则定位到所在榜单的 tab；若不在榜，则定位到黄金 tab
榜单显示名次、双方名称、cp 榜单值、当前排名可获得的奖励
头像支持动态头像，不显示头像框
点击头像打开对方关系空间
上榜信息
榜单值≥x（100000=10000 钻石） 登上摩天轮
周榜倒计时 hh:mm:ss
榜单效果
根据设计动画做旋转
cp 解散说明
若上榜用户解除了 cp，则榜单值清除，排名补位
3、切换上周榜单
切换到昨日榜单后不显示吸底；
中间倒计时改为“上周”
榜单用户为上周 top10，显示上周的榜单值、下发的奖励
cp 奖励为上周最终的奖金值
4、吸底
主态没有 cp
显示主态头像、cp 空头像，点击打开 cp 组建页面
文案“成为 CP 限时低价”
主态有 cp
显示双方头像、榜单cp 值（本周）、排名、送礼按钮
排名信息
第 1 名：排名 1，文案显示“领先第2 名 💗x”
2-10 名：排名 x，文案显示“距上一名需要💗x”
未上榜：显示为未上榜，文案“上榜需要💗x”
点击头像打开双方资料页；显示动态头像、头像框
点击“送礼”交互
若主态在房间内
关闭页面，打开礼物面板，收礼用户带入主态 cp 的 uid
若主态不在房间内
打开主态自己的 cp 空间，并自动调起礼物面板
1v1 和群聊也是打开 cp 空间
5、奖励详情弹窗
标题：奖励
显示奖励icon、名称、道具显示天数
1-3 名钻石显示 “x% 钻石”；4-10 名显示“随机钻石”
点击确认及关闭按钮关闭
补充：cp 关系隐藏
1、CP榜单的头像（A&B），如果A设置了隐藏关系，则B的头像在榜单上不显示；
2、如果2个人都设置了隐藏，则 AB 头像都不显示
3、AB 自己查看榜单，榜单上头像隐藏，吸底状态不需要隐藏，正常显示
1、邀请交互
活动页面吸底点击邀请，打开邀请列表，覆盖在 h5 页面上，选择“邀请”后打开h5组建页面
2、低价组建关系说明
新增2个组建关系的礼物（好友、cp 各 1 个），在活动上线期间只显示 500、1500、2999 这 3 个价格的礼物；活动结束后恢复 1500、2999、5200三个价格
500 钻礼物需要显示标签“限时优惠”
1、「连麦特效」奖励说明
资源类型改为道具下发，日榜抽中该奖励的用户，获得该道具，并自动佩戴；
装扮商场不需要显示该道具 tab
2、「铭牌」说明
cp 铭牌描述文案“CP 活动获得”，无需跳转；
根据配置的 top1、2、3、 top10 显示 4 个铭牌
1、周榜结算后，发送系统消息，文案“恭喜你在上周 CP摩天轮中获得第x 名，奖励{💎数量}”
2、若触发风控，则系统消息文案为“当前账号存在风险，CP奖励发放失败”；无需跳转
对照翻译文档

1、自定义表情：
排序放在第二个；1v1、群聊场景也增加
2、添加
点击打开系统相册；不需要 显示拍照/相册上传 选项
添加的格式除了现有的图片格式外，额外支持 webp、gif；不支持视频格式
选择图片后，支持调整图片尺寸，750x750
1、空态显示
显示默认文案“点击”+”上传表情”
2、首次添加表情后引导
上传的表情≥1个时，出现引导“文案如图”，引导显示5 秒或用户触发长按后消失
若用户已触发过，删除所有表情再添加，则不会触发
长按后，显示【2.1】,可以选择多个表情进行删除； 该状态，点击“添加”按钮无交互，按钮置灰效果；
审核状态的表情也在该页面显示；可以对审核中的表情进行删除，删除后，即使审核通过，也不显示在用户的表情数据中；
3、表情审核
添加表情后，需要提交机审，审核通过前，表情显示“审核中”，点击无法发送，没有交互
审核不通过，则表情在面板删除
每次拉起面板时，更新审核状态
4、发送表情
点击发送时，若用户房间成员等级＜2，则显示弹窗，点击“加入”按钮，打开加入成员页面；≥2 则直接发送
注意：1V1 和群聊场景，不受成员等级限制，可以随意发送
问题备注：
1.动态格式要不要支持 webp（跟头像保持一致）
2.上传个数限制（服务端控制，本次先100个）、大小限制（按房间发送图片的大小限制）
1、公屏自定义表情
自定义表情在公屏的尺寸与其它表情相同
自定义表情不需要显示+1 按钮；且无论发送方是在麦上/麦下，均在公屏显示，自定义表情不会在麦上显示
需要判断点击的图片是自定义表情还是图片，如果是自定义表情，则不支持点击查看大图
若发送的是webp、gif 等动态格式的表情，则显示动态
问题备注：老版本不显示
1、1v1 点击表情时打开的表情面板高度，与房间内高度保持一致

国家tab新增卡塔尔，展示位置在沙特阿拉伯后，国家房间列表展示展示内容和交互与之前一致。国家排序更新，法国调整到最末尾，一共18个国家，排序：埃及、土耳其、叙利亚、黎巴嫩、伊拉克、德国、也门、约旦、沙特阿拉伯、卡塔尔、阿尔及利亚、摩洛哥、荷兰、利比亚、英国、美国、突尼斯、法国

新活动-幸运VISA

1、

位置
游戏房间记录
搜索类型
房主 ID（已有）
房间 ID（新增）
新增「导出」
国王slots接入
cash express重新上线

左图为平台已有的转账卡片
设计原则
「游戏额外钻石奖励」参考平台已有转账类卡片，以保持风格、样式一致
区别于「主播给币商转账卡片」
转账后直接接收，无需接收人确认
区别于「当前钻石到账通知」，新增
到账时间
时间戳
跳转至钱包明细
卡片背景
卡片展示区别
用户侧：展示完整卡片
客服侧：不展示「去钱包」按钮
发送人：主账号
消息类型：普通消息
特殊情况说明
关单后，
客服仍停留在会话页，则无法直接收到该卡片
客服刷新/退出该页面，则可以收到该卡片
聊天卡片外部展示
展示「游戏额外奖励钻到账通知」
有红点
点击「去钱包」按钮后
跳转至该笔钻石明细的弹窗
关闭弹窗后停留在钱包页

Optimization Goal: Ensure consistent operations between the APP and desktop backend
优化目标：保持APP与电脑后台操作一致
Original Logic原逻辑：
Enter the 「User ID」 and click 「Search」 to directly generate query data. Regardless of whether diamonds are successfully issued, the 「User Revenue」 within the query time range will be reset (cleared/zeroed out).
输入「用户ID」并点击「搜索」，直接生成查询数据；无论钻石是否下发成功，查询时间范围内的「用户收益」均会被重置（清空/归零）。
New Logic新逻辑：
Enter the 「User ID」 and click 「Search」 to only display data. Add two columns: 「Operation 1」 and 「Operation 2」 (corresponding to the 「Issue」 and 「Reset」 buttons respectively); 「User Revenue」 serves as the reward base (calculation method: User Revenue × Game Extra Diamond Rewards Ratio by Game Level = Game Extra Diamond Rewards). If the 「Reset」 button is not clicked, the 「User Revenue」 within the query time range remains unchanged and will not be cleared or zeroed out.
输入「用户ID」点击「搜索」仅展示数据，新增「操作1」「操作2」两列（分别对应「下发」「重置」按钮）；「用户收益」为奖励基数（计算方式：用户收益×等级对应额外奖励钻石比例=额外奖励钻石数），未点击「重置」按钮时，查询时间范围内的「用户收益」保持不变，不会被清空或归零。
When the user's game level is ≥ 4当用户游戏等级≥4：
◦ If 「User Revenue」 ≤ -10,000 diamonds (meets the issuance criteria): 「Operation 1」 displays an enabled 「Issue」 button, and 「Operation 2」 shows no button; clicking 「Issue」 adds a record to the 「Historical Additional Reward Diamond Issuance Records」 and pops up a system notification: 「Diamonds have been successfully issued」.
若「用户收益」≤-10000钻（符合下发条件）：「操作1」显示点亮的「下发」按钮，「操作2」无按钮；点击「下发」，在「历史额外奖励钻石下发记录」新增一条数据，弹出提示「钻石已成功下发」。
◦ If 「User Revenue」 > -10,000 diamonds (does not meet the issuance criteria): 「Operation 1」 displays a grayed-out (disabled) 「Issue」 button, and 「Operation 2」 displays an enabled 「Reset」 button; clicking the grayed-out (disabled) 「Issue」 button shows a prompt: 「Due to the user's loss not reaching 10,000 diamonds within the current time range, diamonds cannot be issued💎」; clicking 「Reset」 adds a record to the 「Historical Additional Reward Diamond Issuance Records」, pops up a system notification: 「Reset successful」, and resets (clears/zeroes out) the 「User Revenue」 within the query time range.
若「用户收益」＞-10000钻（不符合下发条件）：「操作1」显示置灰「下发」按钮，「操作2」显示点亮的「重置」按钮；点击置灰「下发」提示「由于当前时间范围内，该用户亏损未达-10000钻，无法下发💎」；点击「重置」，在「历史额外奖励钻石下发记录」新增一条数据，弹出提示「重置成功」，且查询时间范围内「用户收益」重置（清空/归零）。
When the user's game level is 0-3: Other data is displayed normally, no buttons are shown in 「Operation 1」 and 「Operation 2」, and no records are generated in the 「Historical Additional Reward Diamond Issuance Records」.当用户游戏等级0-3：正常展示其他数据，「操作1」「操作2」均无按钮，且不在「历史额外奖励钻石下发记录」生成数据。
The 「Historical Additional Reward Diamond Issuance Records」 only displays data and no operation buttons.「历史额外奖励钻石下发记录」仅展示数据，不显示任何操作按钮。

1
双端房主进房消息、用户侧底部进房消息，标签和名称ui 需要对齐
2
家族成员列表，过滤已注销用户，且在家族人数中减掉
3
1、送礼引导二次确认弹窗
点击赠送按钮，若用户钻石余额＞礼物价格，则展示二次确认弹窗，二次确认后送出
若＜礼物价格，则调起充值
4
1、用户不在房间内收到的礼物，不发送 1v1 私聊；礼物消息聚合到“超级喜欢 list”礼物消息类型
5
注册页&资料页国家列表国家名&区号修正，见文档，涉及英语、阿语名称、区号修正，剔除港澳台不展示。
