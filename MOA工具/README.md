# MOA工具

本目录用于保存临时或常用的 MOA 请求模板。

## 本次保存

- 文件：`查看用户app语言.json`
- key：`momo.pt.toB.cosmos-server.quality-platform.codequality`
- url：`/service/voga-mts-user-profile-stage`
- method：`getUserVersionInfo`
- params：`{"userId":"100357461","lang":"en"}`

## 新增 MOA

- 文件：`查询用户登录天数.json`
- key：`momo.pt.toB.cosmos-server.quality-platform.codequality`
- url：`/service/yaahlan/user/internal/area-moa`
- method：`calcUserActiveDays`
- params1（string）：`100385989`
- params2（string）：`20260510`
- params3（string）：`20260601`

## 执行示例

```bash
python3 MOA/moa_execute.py --payload-file "MOA工具/查看用户app语言.json"
python3 MOA/moa_execute.py --payload-file "MOA工具/查询用户登录天数.json"
```
