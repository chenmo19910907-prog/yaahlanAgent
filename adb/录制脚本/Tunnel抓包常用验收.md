# Tunnel 抓包常用验收

> 本文件由 `adb/scripts/generate_tunnel_capture_doc.py` 根据 `adb/config/tunnel_capture_catalog.json` 自动生成。

Tunnel 抓包常用验收索引：触发操作、URL 关键字、验收字段与可执行命令。Agent 用 adb tunnel capture list/show/run。

## CLI

```bash
# 列出全部
python3 adb/adb_execute.py tunnel capture list

# 查看单项
python3 adb/adb_execute.py tunnel capture show gift_send

# 执行验收（须先完成 trigger 操作）
python3 adb/adb_execute.py tunnel capture run gift_send --momoid <userId>
python3 adb/adb_execute.py tunnel capture run gift_backpack --momoid <userId> --set baseProductId=2005001494 --set num=10
```

底层索引：`adb/config/tunnel_capture_catalog.json`

## 动态

### `feed_publish` · 发布动态

- **触发**：发布图文/视频动态点发布
- **关键字**：`feed/publish`
- **成功**：`response.ec` = 200
- **命令**：`python3 adb/adb_execute.py tunnel wait --momoid <userId> --keyword feed/publish --since 30 --wait 25 --expect-ec 200`
- **备注**：
  - P1 自动化用例常用

## 家族PK

### `family_pk_page` · 家族PK对战列表

- **触发**：家族 PK 页切换到指定日期 tab 并刷新
- **关键字**：`getFamilyPkPage`
- **URL**：`getFamilyPkPage`
- **读取**：`response.data`
- **命令**：`python3 Tunnel/tunnel_execute.py --momoid <userId> --keyword getFamilyPkPage --since <sinceSeconds> --output json`
- **备注**：
  - 工作流 family-pk-config-match-verify
  - 须 request.date=pkDate

## 弹窗

### `popup_login` · 登录后弹窗信号

- **触发**：登录进首页后
- **关键字**：`sign/signInList`
- **命令**：`python3 adb/adb_execute.py popup analyze --scene login --momoid <userId> --since <sinceSeconds>`
- **备注**：
  - 见 弹窗抓包信号.json
  - 抓包不覆盖的 UI 弹窗须 capture 读图

### `popup_me` · Me页弹窗信号

- **触发**：底栏进 Me
- **关键字**：`personalHomePageUserInfo`
- **命令**：`python3 adb/adb_execute.py popup analyze --scene me --momoid <userId> --since <sinceSeconds>`
- **备注**：
  - 众测/Account Security 等

### `popup_room` · 进房弹窗信号

- **触发**：进入他人语音房
- **关键字**：`entranceV3`
- **命令**：`python3 adb/adb_execute.py popup analyze --scene room --momoid <userId> --since <sinceSeconds>`
- **备注**：
  - Mic invitation、Lucky Wish 等

## 房间

### `room_heartbeat` · 房内心跳(进房佐证)

- **触发**：在语音房内停留
- **关键字**：`room/heart/heartbeat`
- **成功**：`response.ec` = 200
- **命令**：`python3 adb/adb_execute.py tunnel last --momoid <userId> --keyword heartbeat --since <sinceSeconds>`
- **备注**：
  - 有 heartbeat 不表示无弹窗

### `room_entrance` · 房间挂件入口

- **触发**：进入语音房
- **关键字**：`entranceV3`
- **读取**：`response.data.entranceList`
- **命令**：`python3 adb/adb_execute.py tunnel last --momoid <userId> --keyword entranceV3 --since <sinceSeconds>`
- **备注**：
  - Lucky Wish、Gift Challenge 等运营入口

## 用户

### `profile_update` · 保存个人资料

- **触发**：编辑资料页点 Save
- **关键字**：`updateUserBase`
- **成功**：`response.ec` = 200
- **命令**：`python3 adb/adb_execute.py tunnel wait --momoid <userId> --keyword updateUserBase --since 30 --wait 25 --expect-ec 200`
- **备注**：
  - 提交表单优先抓包，不以 Toast 为准

## 礼物

### `gift_send` · 送礼接口验收

- **触发**：礼物面板点 Send；Room All 须再点 Confirm
- **关键字**：`gift/send`
- **URL**：`v2/gift/send`
- **成功**：`response.ec` = 200
- **失败读**：`response.em`
- **命令**：`python3 adb/adb_execute.py tunnel last --momoid <userId> --keyword gift/send --since <sinceSeconds>`
- **等待命令**：`python3 adb/adb_execute.py tunnel wait --momoid <userId> --keyword gift/send --since 30 --wait 25 --expect-ec 200`
- **备注**：
  - 勿用 sendGift 关键字
  - 未抓到 gift/send ≠ 业务成功

### `gift_panel_tabs` · 礼物面板 Tab 列表

- **触发**：房内点橙色礼物盒打开面板
- **关键字**：`getGiftTabListV3`
- **URL**：`giftPanel/getGiftTabListV3`
- **成功**：`response.data.gift_list` = 
- **命令**：`python3 adb/adb_execute.py gift panel analyze --momoid <userId> --since <sinceSeconds>`
- **备注**：
  - hash 缓存命中时无 gift_list，须重开面板
  - Customize Tab 排序见 gift_list[].tab_name=Customize

### `gift_panel_find` · 礼物面板按价查找

- **触发**：打开礼物面板后
- **关键字**：`getGiftTabListV3`
- **命令**：`python3 adb/adb_execute.py gift panel find --momoid <userId> --price <price> --tab <tabName> --since <sinceSeconds>`
- **备注**：
  - 返回 index 与上下滑提示，供 macro 点选

### `gift_backpack` · 背包礼物数量验收

- **触发**：MOA 下发后打开礼物面板 → 背包 Tab
- **关键字**：`getGiftTabListV3`
- **URL**：`tab_name=背包`
- **成功**：`gift_list[].package.remain` = 
- **命令**：`python3 MOA/scripts/package_gift_backpack_tunnel_verify.py --user-id <userId> --bid <baseProductId> --expect-remain <num> --since <sinceSeconds>`
- **备注**：
  - bid=baseProductId；propPackageList 仅道具不含礼物
  - 工作流 package-gift-backpack-verify

### `gift_send_check` · 送礼前校验(CP/等级)

- **触发**：打开礼物面板后出现
- **关键字**：`sendCheckInfo`
- **URL**：`giftPanel/sendCheckInfo`
- **读取**：`response.data.cpUserId`, `response.data.buddyUserIdSet`
- **命令**：`python3 adb/adb_execute.py tunnel last --momoid <userId> --keyword sendCheckInfo --since <sinceSeconds>`
- **备注**：
  - cpUserId=null 不可送 CP 礼物

### `gift_custom_rank` · 自定义礼物周榜

- **触发**：礼物面板 Customize 相关页切换本周/上周
- **关键字**：`getTotalCustomGiftRankList`
- **读取**：`response.data.list`
- **命令**：`python3 Tunnel/tunnel_execute.py --momoid <userId> --keyword getTotalCustomGiftRankList --since <sinceSeconds> --output json`
- **备注**：
  - request.cycle=1 本周，2 上周

## 通用

### `tunnel_list` · 原始抓包列表

- **触发**：任意操作后
- **命令**：`python3 Tunnel/tunnel_execute.py --momoid <userId> --since <sinceSeconds>`
- **备注**：
  - 加 --keyword 过滤；--output json 给 Agent 解析

## 相关

- [礼物面板抓包.md](./礼物面板抓包.md)
- [弹窗抓包信号.json](./弹窗抓包信号.json)
- `Tunnel/使用方法.md`
- 技能 `adb-tunnel-verify`
