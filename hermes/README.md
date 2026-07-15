# Hermes × Yaahlan 知识库接入（试用）

把本仓库的 **用例知识库 + 用例生成流程 + Midscene 意图测试** 暴露给 [Hermes Agent](https://hermes-agent.nousresearch.com/)：Hermes 只做编排，业务仍走仓库现有脚本。

## 已落地

| 路径 | 作用 |
|------|------|
| `.hermes.md` | Hermes 进仓库时自动加载的项目上下文 |
| `hermes/skills/yaahlan-gen-testcase/` | `/yaahlan-gen-testcase` 用例生成 Skill |
| `hermes/skills/yaahlan-intent/` | `/yaahlan-intent` Midscene 意图 Skill |
| `hermes/scripts/smoke.sh` | 无模型冒烟（KB + catalog + compile） |
| `hermes/scripts/setup.sh` | 安装 Hermes（若缺）并写入 `external_dirs` |

## 1. 先冒烟（不用模型）

```bash
bash hermes/scripts/smoke.sh
```

## 2. 接入 Hermes

```bash
bash hermes/scripts/setup.sh
# 若刚装完，新开终端或：
source ~/.zshrc

# 推荐：复用 midscene 已配好的火山方舟（写入 ~/.hermes）
bash hermes/scripts/sync_ark_from_midscene.sh

# 或手动：hermes model（Nous / OpenRouter / 其它自定义 endpoint）
cd /path/to/auto-generate-testcase
hermes                # 必须在仓库根目录启动，才会读 .hermes.md
```

`setup.sh` 会把 `hermes/skills` 配进 `~/.hermes/config.yaml` 的 `skills.external_dirs`，并 symlink 到 `~/.hermes/skills/yaahlan/`。

`sync_ark_from_midscene.sh` 会把 `midscene/.env` 的 `MIDSCENE_MODEL_*` 同步为 `custom:volcengine-ark`。

## 3. 对话里怎么试

```text
/yaahlan-gen-testcase 根据 testcase-kb/注册登录.md 生成 3 条 P1 样例用例到 temporary_testcase，并跑 check

/yaahlan-intent 列出意图；编译 intents/动态/text-moment-publish.yaml（先不跑真机）

/yaahlan-intent doctor 通过后跑一条 intents/动态/text-moment-publish.yaml
```

## 架构

```text
Hermes CLI / Gateway
  ├─ /yaahlan-gen-testcase → suggest_kb → 读 KB → temporary_testcase → check_testcase_md
  └─ /yaahlan-intent       → intent-test doctor / md2intent / compile / intent
```

## 说明

- 技能源码在本仓库，改完无需拷贝到 `~/.hermes/skills`（走 external_dirs）。
- 真机执行依赖 `midscene/.env` 与设备；冒烟只做 compile。
- 钉钉 Gateway、Cron 等可之后再开；先 CLI 验证即可。
- 官方简介也可参考 [菜鸟教程 Hermes Agent](https://www.runoob.com/ai-agent/hermes-agent.html)。
