# 动态支持视频发布

Yaahlan 2.3.6 · 动态模块支持发布视频（相册选片、预览、发布、列表浏览等）。

## 目录

```
动态支持视频发布/
├── README.md           # 本文件
├── catalog.json        # 本需求套件登记（P0/P1/P2）
├── registry.json       # 手工表 115 条全量映射
├── cases/              # 可执行自动化用例 JSON
└── docs/               # 需求映射说明
    ├── 自动化全量映射.md
    └── P0自动化映射.md
```

## 链接

| 项 | 地址 |
|----|------|
| PRD | [Yaahlan-2.3.6 版本需求](https://alidocs.dingtalk.com/i/nodes/NZQYprEoWoe2owrwTrjwQnmZJ1waOeDk) |
| 手工用例 Excel | [动态支持发布视频](https://alidocs.dingtalk.com/i/nodes/N7dx2rn0JbZQqA9ACQgRM0D3JMGjLRb3) |
| 本地 PRD 摘录 | `documents/moments/video.md` |

## 命令

```bash
# 本需求
python3 adb/adb_execute.py autotest list --requirement req-动态支持视频发布
python3 adb/adb_execute.py autotest map --requirement req-动态支持视频发布
python3 adb/adb_execute.py autotest run --requirement req-动态支持视频发布
python3 adb/adb_execute.py autotest run --suite req-动态支持视频发布-p0

# 生成新用例到本目录
python3 adb/adb_execute.py autotest generate \
  --requirement req-动态支持视频发布 \
  --id P1-动态-示例 --name "..." --module 动态 --account familyLeader --macros "..."
```

`req-动态-发布视频` 为兼容别名，仍指向本文件夹。
