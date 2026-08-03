# Yaahlan 智能工具平台 · 全量能力导出

- 导出时间（UTC）：2026-07-27T04:00:15Z
- 模块数：**10**
- 能力项：**218**
- Playbook：**0**
- 导入格式：`agent_capabilities_bundle.json`（schema_version 1.0）

## 模块清单

| 模块 | 环境 | 能力数 | 入口 |
|------|------|--------|------|
| yaahlan后台 | test | 32 | `python3 Admin/admin_execute.py` |
| MOA | test | 100 | `python3 MOA/moa_execute.py` |
| MOA-generative | test | 17 | `python3 MOA-generative/scripts/run_generative_moa.py` |
| MSE配置 | test | 9 | `python3 MSE/mse_execute.py` |
| Stage送礼 | test | 7 | `python3 Gift/gift_execute.py` |
| 风险控制 | test | 11 | `python3 Risk/risk_execute.py` |
| Tunnel抓包 | test | 6 | `python3 Tunnel/tunnel_execute.py` |
| 线上环境能力 | online | 5 | `python3 online/online_execute.py` |
| 钉钉文档 | tool | 13 | `python3 DingTalk/lookup_execute.py` |
| 工作流 | tool | 18 | `python3 workflow/workflow_execute.py` |

## 能力明细（按模块）

### yaahlan后台（32 项）

| id | 名称 | 分类 | 提示语数 |
|----|------|------|----------|
| query_user_detail | 用户-查询详情 | 用户（yaahlan-admin） | 3 |
| query_user_feed_list | 用户-查询动态列表 | 用户（yaahlan-admin） | 3 |
| query_user_history_device_list | 用户-查询历史登录设备 | 用户（yaahlan-admin） | 3 |
| query_history_user_list_by_device_id | 用户-查询设备历史登录账号 | 用户（yaahlan-admin） | 3 |
| query_device_current_account | 设备-查询当前登录账号 | 用户（yaahlan-admin） | 4 |
| query_user_profile_list | 用户-查询列表 | 用户（mdp-nova / userAdmin） | 4 |
| batch_mutual_friends_from_user_list | 用户-批量互关结好友 | 用户（mdp-nova / userAdmin + MOA） | 3 |
| cancel_user | 用户-注销账号 | 用户（mdp-nova / userAdmin） | 3 |
| query_prop_info | 道具-查询配置列表 | 道具（mdp-nova / propAdmin） | 5 |
| query_gift_list | 礼物-查询列表 | 礼物（mdp-nova / giftAdmin） | 5 |
| query_custom_gift_list | 定制礼物-查询列表 | 定制礼物（melon-gateway） | 3 |
| reset_custom_gift_upload | 定制礼物-重置上传时间 | 定制礼物（yaahlan-admin） | 3 |
| reset_custom_vehicle_cooldown | 定制座驾-重置上传冷却 | 定制座驾（yaahlan-admin） | 5 |
| reset_custom_prop_cooldown | 定制头像框-重置上传冷却 | 定制道具（yaahlan-admin） | 5 |
| query_family | 家族-查询信息 | 家族（melon-gateway） | 3 |
| list_all_families | 家族-查询全部列表 | 家族（melon-gateway） | 3 |
| add_family_member | 家族-增加成员 | 家族（melon-gateway） | 3 |
| add_guild_member | 公会-用户加入 | 公会（melon-gateway / cms/anchor） | 3 |
| remove_guild_member | 公会-用户移除 | 公会（melon-gateway / cms/anchor） | 3 |
| change_guild_member | 公会-用户转移 | 公会（melon-gateway / cms/anchor） | 3 |
| query_guild | 公会-查询信息 | 公会（melon-gateway / cms/anchor） | 3 |
| query_cs_data | 客服-查询账号列表 | 客服（melon-gateway / cms/customerservice） | 3 |
| save_cs_data | 客服-新增/编辑账号 | 客服（melon-gateway / cms/customerservice） | 3 |
| change_cs_taking_order | 客服-修改接单状态 | 客服（melon-gateway / cms/customerservice） | 3 |
| query_activity_lottery_list | 活动-查询奖池配置列表 | 活动（melon-gateway / cms/activity） | 4 |
| schedule_im_message_types | 活动-IM六种消息类型定时下发 | 活动（melon-gateway / cms/activity） | 4 |
| query_im_list | 活动-查询IM配置任务列表 | 活动（melon-gateway / cms/activity） | 4 |
| delete_im_task | 活动-删除IM配置任务 | 活动（melon-gateway / cms/activity） | 4 |
| query_app_store_review_version | 版本-查询 App Store 审核版本 | 版本（melon-gateway / backend/pangu） | 4 |
| update_app_store_review_version | 版本-设置 App Store 审核版本 | 版本（melon-gateway / backend/pangu） | 3 |
| setup_custom_avatar_frame | 定制头像框-开通流程 | 定制装扮工作流（MOA + Admin） | 3 |
| setup_custom_vehicle | 定制座驾-开通流程 | 定制装扮工作流（MOA + Admin） | 3 |

### MOA（100 项）

| id | 名称 | 分类 | 提示语数 |
|----|------|------|----------|
| room_exp_add | 房间经验值-增加 | 房间经验值（voga-mts-room-backdoor） | 1 |
| room_level_upgrade | 房间等级-升级到目标等级 | 房间经验值（voga-mts-room-backdoor） | 2 |
| room_query_current | 房间经验值-查询当前等级经验 | 房间经验值（voga-mts-room-backdoor） | 2 |
| room_set_level | 房间-设置等级 | 房间测试（room/internal/room-test-stage） | 2 |
| room_add_bots | 房间-增加机器人 | 房间经验值（voga-mts-room-backdoor） | 2 |
| room_online | 房间-增加在线人数 | 房间经验值（voga-mts-room-backdoor） | 2 |
| pk_rank_settle | PK榜-周结算发奖 | 全服榜单（room/external/room-admin-handle） | 3 |
| pk_rank_query | PK榜-查询数值 | 全服榜单（room/external/room-admin-handle） | 3 |
| pk_rank_value_add | PK榜-增加PK值 | 全服榜单（room/external/room-admin-handle） | 3 |
| room_hourly_top1_broadcast | 房间-下发小时榜全服通知 | 全服榜单（room/external/room-admin-handle） | 2 |
| user_rank_dispatch | 用户榜单-奖励下发（贡献/魅力 周榜/日榜/月榜） | 全服榜单（room/external/room-admin-handle） | 9 |
| contrib_day_rank_dispatch | 贡献日榜-奖励下发 | 全服榜单（room/external/room-admin-handle） | 3 |
| charm_day_rank_dispatch | 魅力日榜-奖励下发 | 全服榜单（room/external/room-admin-handle） | 3 |
| room_day_rank_dispatch | 房间日榜-奖励下发 | 全服榜单（room/external/room-admin-handle） | 3 |
| room_member_lv_exp_add | 房间成员-增加陪伴值 | 房间成员等级（room-user-active-stage） | 2 |
| room_member_add | 房间成员-快速添加 | 房间成员（voga-mts-room-backdoor） | 3 |
| room_member_lv_level_upgrade | 房间成员-升级到目标等级 | 房间成员等级（room-user-active-stage） | 2 |
| vip_exp_add | VIP经验值-增加 | VIP 经验值（voga-mts-user-vip-stage） | 2 |
| vip_level_upgrade | VIP等级-升级到目标等级 | VIP 经验值（voga-mts-user-vip-stage） | 4 |
| vip_query_current | VIP经验值-查询当前等级经验 | VIP 经验值（voga-mts-user-vip-stage） | 2 |
| vip_delete_info | VIP等级-清除VIP信息 | VIP 经验值（voga-mts-user-vip-stage） | 2 |
| vip_try_dispatch | VIP体验卡-下发 | VIP 经验值（voga-mts-user-vip-stage） | 3 |
| cp_ferris_wheel_set_tier | CP摩天轮-设置档位 | CP摩天轮（vas/external/cp-stage） | 3 |
| cp_ferris_wheel_distribute_bonus | CP摩天轮-发放档位积分返奖 | CP摩天轮（vas/external/cp-stage） | 3 |
| cp_ferris_wheel_week_prize | CP摩天轮-发放周榜奖励 | CP摩天轮（vas/external/cp-stage） | 3 |
| custom_gift_reset_upload | 定制礼物-重置上传次数 | 定制礼物（voga-components/gateway/custom-gift-stage） | 2 |
| custom_gift_rank_active_add | 定制礼物榜单-增加活跃值 | 定制礼物榜单（room/internal/room-rank-list-stage） | 3 |
| custom_gift_rank_delete | 定制礼物榜单-清除数据 | 定制礼物榜单（room/internal/room-rank-list-stage） | 3 |
| noble_exp_add | 贵族-增加月消费值 | 贵族（voga-mts-user-wealth-charm-level-stage） | 2 |
| noble_level_upgrade | 贵族-升级到目标等级 | 贵族（voga-mts-user-wealth-charm-level-stage） | 2 |
| family_exp_add | 家族-增加声望值 | 家族（internal/user/family-moa） | 2 |
| family_exp_decrease | 家族-衰减声望值 | 家族（internal/user/family-moa） | 2 |
| family_fund_tier_set | 家族-设置基金档位 | 家族（internal/user/family-moa） | 2 |
| family_fund_reward_setup | 家族-设置基金返奖钻石 | 家族（internal/user/family-moa） | 2 |
| family_fund_contrib_add | 家族-增加基金贡献值 | 家族（internal/user/family-moa） | 2 |
| family_fund_contrib_query | 家族-查询基金贡献值 | 家族（internal/user/family-moa） | 2 |
| family_fund_clear | 家族-清除基金贡献值 | 家族（internal/user/family-moa） | 2 |
| family_member_fund_contrib_add | 家族-成员增加基金贡献值 | 家族（internal/user/family-moa） | 2 |
| family_level_upgrade | 家族-升级到目标等级 | 家族（internal/user/family-moa） | 2 |
| family_query_current | 家族-查询当前声望值 | 家族（internal/user/family-moa） | 2 |
| family_query_members | 家族-查询成员userId | 家族（internal/user/family-moa） | 3 |
| family_query_create_time | 家族-查询创建时间 | 家族（internal/user/family-moa） | 3 |
| family_query_joined_by_user | 家族-按userId查家族id | 家族（internal/user/family-moa） | 3 |
| family_detail_by_id | 家族-按familyId查详情 | 家族（internal/user/family-moa） | 3 |
| family_detail_by_user | 家族-按userId查详情 | 家族（internal/user/family-moa） | 3 |
| id_auth_query_real_person_record | 实名认证-查询认证记录 | 实名认证（internal/user/id-auth-api） | 2 |
| id_auth_fix_failure_by_reason | 实名认证-解决认证失败（清 reason 关联账号） | 实名认证（internal/user/id-auth-api） | 2 |
| id_auth_reset_relation_expire_time | 实名认证-设置认证过期时间 | 实名认证（internal/user/id-auth-api） | 2 |
| id_auth_del_relation_by_scene | 实名认证-按场景删除真人认证 | 实名认证（internal/user/id-auth-api） | 4 |
| id_auth_delete_person | 实名认证-清除认证信息 | 实名认证（internal/user/id-auth-api） | 2 |
| user_login_query_by_phone | 用户-按手机号查 userId | 用户登录（yaahlan/mdp-user-login） | 3 |
| ip_find | IP-查询归属地 | 用户后门（voga-mts-user-backdoor） | 3 |
| user_home_country_update | 用户-修改注册国家 | 用户后门（voga-mts-user-backdoor） | 3 |
| user_set_reg_time | 用户-设置注册时间 | 用户后门（voga-mts-user-backdoor） | 3 |
| user_reg_time_query | 用户-查询注册时间 | 用户后门（voga-mts-user-backdoor） | 3 |
| user_cancel_real | 用户-注销账号 | 用户后门（voga-mts-user-backdoor） | 4 |
| charm_query_current | 魅力-查询等级 | 用户后门（voga-mts-user-backdoor） | 3 |
| wealth_query_current | 财富-查询等级 | 用户后门（voga-mts-user-backdoor） | 3 |
| user_area_change | 用户-修改大区 | 用户大区（yaahlan/components/callback/user-area） | 3 |
| diamond_query_account | 钻石-查询余额 | 钻石（voga-base-service-middle-pay-stage） | 2 |
| diamond_provide | 钻石-发放 | 钻石（voga-base-service-middle-pay-stage） | 2 |
| pay_test_query_all | 送礼限制-查询测试账号 | 支付测试（pay-middle/test） | 3 |
| package_gift_add | 背包礼物-下发 | 背包礼物（voga-base-service-middle-gift-stage） | 3 |
| package_gift_send | 背包礼物-送礼 | 背包礼物（voga-base-service-middle-gift-stage） | 3 |
| gift_panel_backpack_view | 礼物面板-查看背包 | 礼物面板（yh-components/gift-panel） | 3 |
| gift_panel_backpack_gifts | 礼物面板-查看背包礼物 | 礼物面板（yh-components/gift-panel） | 3 |
| gift_panel_backpack_props | 礼物面板-查看背包道具 | 礼物面板（yh-components/gift-panel） | 2 |
| package_gift_backpack_verify | 背包礼物-Tunnel背包验收 | 背包礼物（voga-base-service-middle-gift-stage） | 3 |
| anniversary_egg_mystery_count | 3周年砸金蛋-查神秘保底计数 | 活动（3周年砸金蛋） | 2 |
| anniversary_egg_smash_record | 3周年砸金蛋-造数并记录钉钉表 | 活动（3周年砸金蛋） | 2 |
| anniversary_egg_mse_to_workbook | 3周年砸金蛋-MSE配置同步钉钉表 | 活动（3周年砸金蛋） | 2 |
| anniversary_egg_lottery_to_workbook | 3周年砸金蛋-奖池配置同步钉钉表 | 活动（3周年砸金蛋） | 2 |
| anniversary_egg_multi_account_verify | 3周年砸金蛋-多账号批量验收落表 | 活动（3周年砸金蛋） | 2 |
| anniversary_egg_smash_test | 3周年-砸金蛋测试 | 活动（3周年砸金蛋） | 3 |
| user_active_days_query | 用户-查询登录天数 | 用户活跃（yaahlan/user/internal/area-moa） | 2 |
| user_app_language_query | 用户-查看 app 语言 | 用户资料（voga-mts-user-profile-stage） | 2 |
| user_prop_query_own | 装扮-查询用户拥有道具 | 用户装扮（mdp-prop/user-prop-api-service-test） | 3 |
| activity_mock_gift | 活动-模拟送礼 | 活动（vas/gift-call-back） | 2 |
| family_member_leave | 家族-移除成员 | 家族（external/user/family-api） | 3 |
| family_kick_member | 家族-踢出成员 | 家族（external/user/family-api） | 3 |
| family_pk_member_contrib_list | 家族PK-成员贡献列表 | 家族PK（vas/activity/family-pk-v2-api） | 3 |
| family_pk_request_page | 家族PK-请求页面 | 家族PK（vas/activity/family-pk-v2-api） | 3 |
| family_pk_modify_receive_daily_rank | 家族PK-修改收礼日榜 | 家族PK（vas/internal/family-pk-moa） | 3 |
| family_pk_query_receive_daily_rank | 家族PK-查询收礼日榜 | 家族PK（vas/internal/family-pk-moa） | 3 |
| family_pk_incr_score | 家族PK-增加PK值 | 家族PK（vas/internal/family-pk-moa） | 3 |
| family_pk_run_match_task | 家族PK-结算发奖匹配 | 家族PK（vas/internal/family-pk-moa） | 4 |
| family_pk_delete_match_data | 家族PK-清除匹配数据 | 家族PK（vas/internal/family-pk-moa） | 4 |
| user_follow_friend | 用户-关注好友 | 用户关系（voga-mts-user-relation-stage） | 2 |
| family_delete | 家族-解散家族 | 家族（external/user/family-api） | 3 |
| family_pk_delete_member_pk_rank_data | 家族PK-删除全部PK值 | 家族PK（vas/internal/family-pk-moa） | 4 |
| family_pk_query_receive_daily_rank_2 | 家族PK-查询收礼日榜 | 家族PK（vas/internal/family-pk-moa） | 3 |
| family_pk_reset_settle_data | 家族PK-清除结算奖励 | 家族PK（vas/internal/family-pk-moa） | 4 |
| anniversary_year3_exchange_item | 3周年-兑换道具 | 活动（3周年） | 3 |
| feed_publish_comment | 动态-帖子评论 | 动态（feed-comment-stage） | 3 |
| 房间成员_同意申请 | 房间成员-同意申请 | 房间（room-member-stage） | 1 |
| 房间成员_申请加入 | 房间成员-申请加入 | 房间（room-member-stage） | 1 |
| feed_like_comment | 动态-评论点赞 | 动态（feed-interact-stage） | 3 |
| feed_gift_send | 动态-帖子送礼 | 动态（/v2/gift/send · Stage HTTP） | 3 |
| user_batch_send_p2p_message | 用户-批量发消息 | 用户工具（voga-mts-user-tool-stage） | 3 |
| user_batch_send_greeting_message | 用户-批量发招呼消息 | 用户工具（voga-mts-user-tool-stage） | 3 |

### MOA-generative（17 项）

| id | 名称 | 分类 | 提示语数 |
|----|------|------|----------|
| moa_generative_workflow_run | 生成式MOA-工作流执行 | 生成式MOA（抓包转MOA） | 3 |
| moa_generative_run_script | 生成式MOA-一键脚本 | 生成式MOA（抓包转MOA） | 2 |
| moa_generative_build_only | 生成式MOA-仅生成payload | 生成式MOA（抓包转MOA） | 2 |
| moa_generative_signin_example | 生成式MOA-签到示例 | 生成式MOA（已验证示例） | 2 |
| moa_generative_like_example | 生成式MOA-点赞示例 | 生成式MOA（已验证示例） | 2 |
| moa_generative_accept_intimate_example | 生成式MOA-同意亲密申请 | 生成式MOA（已验证示例） | 2 |
| moa_generative_buddy_form | 生成式MOA-结挚友一键 | 生成式MOA（已验证示例） | 3 |
| moa_generative_cp_form | 生成式MOA-结CP一键 | 生成式MOA（已验证示例） | 3 |
| moa_generative_family_pk_member_list | 生成式MOA-家族PK成员贡献列表 | 生成式MOA（已验证示例） | 3 |
| moa_generative_family_pk_page | 生成式MOA-家族PK请求页面 | 生成式MOA（已验证示例） | 3 |
| moa_generative_room_member_apply | 生成式MOA-房间成员申请 | 生成式MOA（已验证示例） | 2 |
| moa_generative_room_member_agree | 生成式MOA-同意房间成员申请 | 生成式MOA（已验证示例） | 2 |
| moa_generative_gift_panel_backpack_gifts | 生成式MOA-礼物面板背包礼物 | 生成式MOA（抓包转MOA） | 3 |
| moa_generative_gift_panel_backpack_props | 生成式MOA-礼物面板背包道具 | 生成式MOA（抓包转MOA） | 2 |
| moa_generative_room_member_quick_add | 生成式MOA-快速添加房间成员 | 生成式MOA（已验证示例） | 3 |
| moa_generative_feed_publish_comment | 生成式MOA-帖子评论 | 生成式MOA（已验证示例） | 3 |
| moa_generative_cp_love_chest_homepage | 生成式MOA-CP爱意宝箱主页 | 生成式MOA（抓包转MOA） | 3 |

### MSE配置（9 项）

| id | 名称 | 分类 | 提示语数 |
|----|------|------|----------|
| list_voga_common | 配置-列出 voga-common | MSE 服务配置 | 3 |
| get_config_key | 配置-按 key 读取 | MSE 服务配置 | 3 |
| grep_config_key | 配置-关键字过滤 | MSE 服务配置 | 2 |
| list_voga_activity | 配置-列出 voga-activity | MSE 服务配置 | 4 |
| grep_voga_activity | 配置-voga-activity 关键字过滤 | MSE 服务配置 | 3 |
| get_voga_activity_config_key | 配置-voga-activity 按 key 读取 | MSE 服务配置 | 3 |
| list_application | 配置-列出 Application（私有） | MSE 服务配置 | 4 |
| grep_application | 配置-Application 关键字过滤 | MSE 服务配置 | 3 |
| get_application_config_key | 配置-Application 按 key 读取 | MSE 服务配置 | 3 |

### Stage送礼（7 项）

| id | 名称 | 分类 | 提示语数 |
|----|------|------|----------|
| stage_gift_chatroom | Stage送礼-房间内 | Stage HTTP 送礼（/v2/gift/send） | 3 |
| stage_gift_private | Stage送礼-私聊 | Stage HTTP 送礼（/v2/gift/send） | 2 |
| stage_gift_group | Stage送礼-群组 | Stage HTTP 送礼（/v2/gift/send） | 2 |
| stage_gift_room_all | Stage送礼-全房间 | Stage HTTP 送礼（/v2/gift/send） | 2 |
| stage_gift_intimate_invite | Stage送礼-亲密关系申请 | Stage HTTP 送礼（/v2/gift/send） | 3 |
| stage_gift_probe | Stage送礼-探测 | Stage HTTP 送礼（/v2/gift/send） | 2 |
| stage_gift_dry_run | Stage送礼-预演 | Stage HTTP 送礼（/v2/gift/send） | 2 |

### 风险控制（11 项）

| id | 名称 | 分类 | 提示语数 |
|----|------|------|----------|
| list_test_devices | 测试机-列出知识库 | 测试机（testcase-kb/test_devices.json） | 3 |
| release_test_device | 测试机-解除设备风控 | 测试机（testcase-kb/test_devices.json） | 3 |
| release_device | 设备风控-解除（手动 mmuid） | 设备风控（mmuid 白名单） | 3 |
| release_device_from_file | 设备风控-批量解除（文件） | 设备风控（mmuid 白名单） | 2 |
| release_phone | 手机号风控-解除 | 手机号风控（phone 白名单） | 3 |
| release_online_login_device | 线上-解除最近登录手机/设备风控并落库 | 线上环境（手机号 → 最近登录设备） | 3 |
| add_recharge_risk | 充值风控-添加 | 充值风控（user_id 黑名单） | 2 |
| release_recharge_risk | 充值风控-解除 | 充值风控（user_id 黑名单） | 2 |
| add_activity_risk | 活动风控-添加 | 活动风控（user_id 黑名单） | 2 |
| release_activity_risk | 活动风控-解除 | 活动风控（user_id 黑名单） | 2 |
| generic_menu_operate | 通用名单-操作 | 通用名单（/open/menu/operate） | 2 |

### Tunnel抓包（6 项）

| id | 名称 | 分类 | 提示语数 |
|----|------|------|----------|
| list_requests | 抓包-查询用户请求列表 | Tunnel 抓包 | 3 |
| list_requests_keyword | 抓包-按关键字过滤 | Tunnel 抓包 | 3 |
| request_detail | 抓包-单条请求详情 | Tunnel 抓包 | 2 |
| list_requests_json | 抓包-完整 JSON 输出 | Tunnel 抓包 | 2 |
| tunnel_capture_list | 抓包-常用验收目录 | Tunnel 抓包 | 3 |
| tunnel_capture_run | 抓包-执行常用验收 | Tunnel 抓包 | 3 |

### 线上环境能力（5 项）

| id | 名称 | 分类 | 提示语数 |
|----|------|------|----------|
| admin_query_user_detail | Admin-查询用户详情 | Admin（yaahlan-admin） | 3 |
| moa_query_user_by_phone | MOA-按手机号查 userId | MOA（mdp-user-login · overseas） | 3 |
| tunnel_list_requests | Tunnel-查询用户请求列表 | Tunnel 抓包 | 2 |
| tunnel_list_requests_keyword | Tunnel-按关键字过滤 | Tunnel 抓包 | 2 |
| tunnel_list_requests_json | Tunnel-完整 JSON 输出 | Tunnel 抓包 | 2 |

### 钉钉文档（13 项）

| id | 名称 | 分类 | 提示语数 |
|----|------|------|----------|
| folder_show_registered | 目录-查看已登记目录 | 钉钉目录 | 3 |
| folder_lookup | 目录-按关键词查文件链接 | 钉钉目录 | 3 |
| folder_list_all | 目录-列举全部表格 | 钉钉目录 | 2 |
| collect_links | 目录-列举全部表格链接 | 钉钉目录 | 3 |
| collect_links_export | 目录-导出链接 JSON | 钉钉目录 | 2 |
| kb_sync_list | 知识库-预览可同步版本表 | testcase-kb 同步 | 2 |
| kb_sync_full | 知识库-全量同步 | testcase-kb 同步 | 3 |
| kb_sync_activity | 知识库-同步运营活动用例 | testcase-kb 同步 | 3 |
| kb_sync_workbook | 知识库-单表同步 | testcase-kb 同步 | 2 |
| kb_sync_version | 知识库-按版本同步 | testcase-kb 同步 | 2 |
| prd_sync_full | 需求库-全量同步 PRD | prd-kb 同步 | 3 |
| prd_sync_version | 需求库-按版本同步 PRD | prd-kb 同步 | 2 |
| prd_sync_document | 需求库-单篇同步 | prd-kb 同步 | 2 |

### 工作流（18 项）

| id | 名称 | 分类 | 提示语数 |
|----|------|------|----------|
| family_pk_config_create_workbook | 家族PK配置-新建测试钉钉表 | 家族PK | 2 |
| family_pk_config_mse_to_dingtalk | 家族PK配置-MSE同步到钉钉参数表 | 家族PK | 2 |
| family_pk_config_pk_list_to_dingtalk | 家族PK配置-后台家族成员写入钉钉 | 家族PK | 2 |
| family_pk_config_rank_rematch | 家族PK配置-收礼榜造数与档位测算 | 家族PK | 2 |
| family_pk_config_match_verify | 家族PK配置-重匹配与验收写入钉钉 | 家族PK | 2 |
| family_pk_config_member_pk_reward | 家族PK配置-成员PK造数与发钻测算 | 家族PK | 2 |
| family_pk_config_dispatch_verify | 家族PK配置-发奖与验收 | 家族PK | 2 |
| family_pk_config_test_result | 家族PK配置-测试结果汇总 | 家族PK | 2 |
| family_pk_config_reward_calc | 家族PK配置-档位PK与奖励测算 | 家族PK | 2 |
| family_pk_config_sheet_to_json | 家族PK配置-钉钉参数表生成JSON | 家族PK | 2 |
| family_pk_daily_rematch | 家族PK-重置匹配并下发前日奖励 | 家族PK | 3 |
| package_gift_backpack_verify | 背包礼物-Tunnel背包验收 | 背包礼物 | 2 |
| package_gift_dispatch_verify | 背包礼物-下发与Tunnel验收 | 背包礼物 | 2 |
| anniversary_egg_smash_record | 3周年砸金蛋-造数并记录 | 3周年活动 | 2 |
| moa_generative_run | MOA-generative-抓包转MOA执行 | MOA-generative | 2 |
| intimate_buddy_form | 亲密关系-结挚友 | 亲密关系 | 2 |
| intimate_cp_form | 亲密关系-结CP | 亲密关系 | 2 |
| room_member_quick_add_form | 房间成员-快速添加 | 房间 | 3 |
