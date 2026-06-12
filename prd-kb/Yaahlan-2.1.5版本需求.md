# Yaahlan-2.1.5版本需求.adoc

> **文档类型**：产品需求文档（PRD）
> **来源**：[Yaahlan-2.1.5版本需求.dlink](https://alidocs.dingtalk.com/i/nodes/KGZLxjv9VG349wRwh7p3534qV6EDybno)
> **版本**：`v2.1.5`
> **同步时间**：2026-06-12 14:27:41 +0800

## 正文

处理方式
购买&解锁VIP后，需要后端给客户端实时返回 用户 vip 信息，用户在以下场景无需退出或重进页面，即可解锁 vip 功能
处理场景
1.房间内麦上表情包：
解锁 vip 4 后，不需要退出房间重进；重新打开麦上表情面板，即可解锁并发送
2.个人资料修改靓号：
解锁 vip 3 后，不需要退出编辑资料页重进；再次点击靓号入口，即可进入编辑页面
3.VIP 彩色昵称特权：
解锁 vip 2 后，不需要冷启 app；昵称可以显示 vip 彩色昵称；
用户在麦上，可以处理为重新上麦更新昵称颜色
用户公屏发言，则解锁后的下一次发言更新昵称颜色；且历史消息昵称颜色不需要更改

Yaahlan官网优化
官网：www.yaahlan.fun
区分手机端和Web端，具体见设计稿，文案：
点击跳转：
1.App Store：
2.Google Play：
3. 服务条款：点击去Terms of Service页
4. 隐私政策：点击去Privacy Policy页
5.Facebook: https://www.facebook.com/profile.php?id=61568419767074
6.Instagram: https://www.instagram.com/yaahlan_official
7.X: https://x.com/YaahlanOfficial
8.TikTok: https://www.tiktok.com/@yaahlan_official
9.Youtube: https://www.youtube.com/@YaahlanOfficial/shorts

1
定制资料卡/资料页 皮肤，ios max 机型按钮适配调整
2
非公开房间录屏提醒
在密码房、关闭房有用户录屏时，房间内所有人收到公屏消息提示“X（用户名）正在录屏”，用户名可点击打开mini profile页
过滤超管和客服，不发送公屏消息

完整版链接

备注
Yaahlan两周年庆典-7.23上线
需要客户端小支持：公屏消息+全服飘屏
公屏文案AR-送礼: قام {name} بإرسال هدية الذكرى السنوية الثانية، وحصل على أرباح قدرها %s من الألماس
公屏文案EN-送礼：{name} sent 2nd anniversary celebration gift and received %s diamonds
公屏文案AR-收礼: تلقّى {name} هدية الذكرى السنوية الثانية، وحصل على أرباح قدرها %s من الألماس
公屏文案EN-收礼：{name} receive 2nd anniversary celebration gift and received %s diamonds
全服飘屏文案AR：حصل {avatar} على %s ألماس كمكافأة شحن الذكرى السنوية
全服飘屏文案EN：{avatar} gets %s diamonds from 2nd anniversary！
充值活动-转盘概率优化：
新增隐形充值周榜
隐形充值周榜实时TOP50（名次门槛可配），在抽奖时触发另一套普通转盘+超级转盘的奖池概率
以上情况无论用户选择单次抽奖还是10连抽逻辑统一
抽奖时仅遵循用户点击抽奖那一刻他所处的隐形榜名次触发对应概率池
每周榜单重置无数据时，统一走原有概率池
优化
主播赊账计入薪资兑换钻石活动，不计入充值活动
