#!/usr/bin/env node
/**
 * 按 game.env/games.list 中的顺序，依次执行 testcases-yaml/ios/game-* 下匹配的 .yaml。
 * 无对应用例的游戏名称会跳过；单个用例失败则停止后续执行。
 *
 * 前提：WDA 已启动；设备已在「游戏中心」页面。
 *
 * 用法：
 *   node game.env/run-ios-games-from-list.mjs
 *   node game.env/run-ios-games-from-list.mjs --from=Mines   # 从指定游戏起继续（含该项）
 *   npm run yaml:ios:games-from-list
 */

import { existsSync, readFileSync, readdirSync } from 'fs';
import { dirname, resolve } from 'path';
import { fileURLToPath } from 'url';
import { spawn } from 'child_process';

const scriptDir = dirname(fileURLToPath(import.meta.url));
const root = resolve(scriptDir, '..');
const gamesListPath = resolve(scriptDir, 'games.list');
const iosDir = resolve(root, 'testcases-yaml/ios');

/** games.list 归一化键 → YAML slug 归一化键（拼写/业务别名） */
const GAME_TO_SLUG_KEY = {
  fortunejewles: 'fortunejewels',
  crazygems: 'crzaygems',
  spinx: 'sphinx',
};

function normalizeKey(value) {
  return value.toLowerCase().replace(/[^a-z0-9]/g, '');
}

function loadEnv() {
  try {
    const lines = readFileSync(resolve(root, '.env'), 'utf8').split('\n');
    for (const line of lines) {
      const trimmed = line.trim();
      if (!trimmed || trimmed.startsWith('#')) continue;
      const idx = trimmed.indexOf('=');
      if (idx === -1) continue;
      const key = trimmed.slice(0, idx).trim();
      const val = trimmed.slice(idx + 1).trim().replace(/\s*#.*$/, '').trim();
      if (key && process.env[key] === undefined) process.env[key] = val;
    }
  } catch {
    /* no .env */
  }
}

function readGamesList() {
  const raw = readFileSync(gamesListPath, 'utf8');
  return raw
    .split(/[,，]/)
    .map((s) => s.trim())
    .filter(Boolean);
}

/** 解析 --from=GameName，从该游戏起执行（含） */
function parseFromArg() {
  const arg = process.argv.find((a) => a.startsWith('--from='));
  if (!arg) return null;
  const value = arg.slice('--from='.length).trim();
  return value || null;
}

function slicePlanFrom(plan, fromGame) {
  const fromKey = normalizeKey(fromGame);
  const idx = plan.findIndex(
    (p) =>
      normalizeKey(p.game) === fromKey ||
      normalizeKey(p.game).includes(fromKey) ||
      fromKey.includes(normalizeKey(p.game)),
  );
  if (idx === -1) {
    console.error(
      `[games-from-list] ❌ --from=${fromGame} 未在可执行列表中找到，请检查名称`,
    );
    process.exit(1);
  }
  return { plan: plan.slice(idx), startIndex: idx };
}

function extractSlug(filename) {
  const spinBet = filename.match(/^game-center-(.+?)-(?:spin|bet)-p1\.yaml$/);
  if (spinBet) return spinBet[1];
  const plain = filename.match(/^game-center-(.+?)-p1\.yaml$/);
  if (plain) return plain[1];
  return null;
}

/** 扫描 ios 下名称包含 game 的子目录，建立 slug → yaml 路径索引 */
function buildYamlIndex() {
  const index = new Map();

  const entries = readdirSync(iosDir, { withFileTypes: true });
  for (const entry of entries) {
    if (!entry.isDirectory() || !entry.name.includes('game')) continue;

    const dirPath = resolve(iosDir, entry.name);
    for (const file of readdirSync(dirPath)) {
      if (!file.endsWith('.yaml')) continue;
      const slug = extractSlug(file);
      if (!slug) continue;

      const key = normalizeKey(slug);
      const fullPath = resolve(dirPath, file);
      if (!index.has(key)) {
        index.set(key, fullPath);
      }
    }
  }

  return index;
}

function findYamlForGame(gameName, index) {
  let key = normalizeKey(gameName);
  if (GAME_TO_SLUG_KEY[key]) {
    key = GAME_TO_SLUG_KEY[key];
  }

  if (index.has(key)) {
    return index.get(key);
  }

  // 模糊：slug 键与游戏键互为子串时取最长 slug 匹配
  let best = null;
  let bestLen = 0;
  for (const [slugKey, yamlPath] of index) {
    if (slugKey.includes(key) || key.includes(slugKey)) {
      if (slugKey.length > bestLen) {
        bestLen = slugKey.length;
        best = yamlPath;
      }
    }
  }
  return best;
}

async function checkWda() {
  const host = process.env.WDA_HOST || 'localhost';
  const port = process.env.WDA_PORT || '8100';
  try {
    const res = await fetch(`http://${host}:${port}/status`, {
      signal: AbortSignal.timeout(3000),
    });
    return { ok: res.ok, host, port };
  } catch {
    return { ok: false, host, port };
  }
}

function runMidscene(yamlPath) {
  return new Promise((resolveExit) => {
    const child = spawn(
      'node',
      ['scripts/midscene-run.mjs', '--platform=ios', yamlPath],
      {
        stdio: 'inherit',
        env: process.env,
        cwd: root,
        shell: true,
      },
    );
    child.on('close', resolveExit);
  });
}

async function main() {
  loadEnv();

  if (!existsSync(gamesListPath)) {
    console.error(`[games-from-list] ❌ 未找到 ${gamesListPath}`);
    process.exit(1);
  }

  const { ok, host, port } = await checkWda();
  if (!ok) {
    console.error(
      `[games-from-list] ❌ WDA 未运行（http://${host}:${port}/status 无响应）`,
    );
    process.exit(1);
  }
  console.log(`[games-from-list] ✓ WDA 运行正常（http://${host}:${port}）`);

  const games = readGamesList();
  const index = buildYamlIndex();
  const plan = [];
  const skipped = [];

  for (const game of games) {
    const yamlPath = findYamlForGame(game, index);
    if (yamlPath) {
      plan.push({ game, yamlPath });
    } else {
      skipped.push(game);
    }
  }

  console.log(`[games-from-list] games.list 共 ${games.length} 项，匹配 ${plan.length} 个用例`);
  if (skipped.length) {
    console.log(`[games-from-list] 跳过（无匹配 YAML）${skipped.length} 项：`);
    for (const g of skipped) console.log(`  - ${g}`);
  }

  if (!plan.length) {
    console.error('[games-from-list] 没有可执行的用例');
    process.exit(1);
  }

  const fromGame = parseFromArg();
  let runPlan = plan;
  let planOffset = 0;
  if (fromGame) {
    const sliced = slicePlanFrom(plan, fromGame);
    runPlan = sliced.plan;
    planOffset = sliced.startIndex;
    console.log(
      `[games-from-list] 从「${fromGame}」继续，跳过前 ${planOffset} 个已匹配用例`,
    );
  }

  if (!runPlan.length) {
    console.error('[games-from-list] 没有可执行的用例');
    process.exit(1);
  }

  console.log(`[games-from-list] 本次将执行 ${runPlan.length} 个用例：`);
  for (const { game, yamlPath } of runPlan) {
    console.log(`  - ${game} → ${yamlPath.replace(`${root}/`, '')}`);
  }

  for (let i = 0; i < runPlan.length; i++) {
    const { game, yamlPath } = runPlan[i];
    const label = yamlPath.split('/').pop();
    const seq = planOffset + i + 1;
    console.log(
      `\n[games-from-list] (${seq}/${plan.length}) ${game} → 开始：${label}`,
    );
    const exitCode = await runMidscene(yamlPath);
    if (exitCode !== 0) {
      console.error(
        `[games-from-list] ❌ 失败：${game}（${label}），退出码 ${exitCode}，后续用例不再执行`,
      );
      process.exit(exitCode ?? 1);
    }
    console.log(`[games-from-list] ✓ 完成：${game}`);
  }

  console.log(
    fromGame
      ? '\n[games-from-list] 🎉 本次续跑用例全部执行成功'
      : '\n[games-from-list] 🎉 全部匹配用例执行成功',
  );
}

main().catch((err) => {
  console.error('[games-from-list] 错误:', err.message);
  process.exit(1);
});
