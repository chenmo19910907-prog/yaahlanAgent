#!/usr/bin/env node
/**
 * Android + iOS 并行执行 intent 用例（按 YAML platform 字段分流）
 *
 * 用法:
 *   npm run intent:dual -- intents/动态/moment-discover-common.yaml
 *   npm run intent:dual:module -- 动态
 */

import { spawn } from 'child_process';
import { dirname, resolve } from 'path';
import { fileURLToPath } from 'url';
import { applyBaseProfileEnv } from './load-base-profile.mjs';
import { ensureIntentData } from './ensure-intent-data.mjs';
import {
  resolveInputs,
  findSourceById,
  readRunResult,
  ROOT,
} from './intent-run-lib.mjs';
import { generateDualReport } from './generate-report-dual.mjs';

const WORKER = resolve(dirname(fileURLToPath(import.meta.url)), 'intent-run-platform.mjs');

function spawnWorker(platform, forwardArgs) {
  return new Promise((resolvePromise) => {
    const child = spawn(
      process.execPath,
      [WORKER, '--platform', platform, ...forwardArgs],
      {
        stdio: 'inherit',
        cwd: ROOT,
        env: {
          ...process.env,
          INTENT_SKIP_DATA_PREP: '1',
        },
      },
    );
    child.on('close', (code) => resolvePromise(code ?? 1));
  });
}

async function main() {
  applyBaseProfileEnv();
  const cliArgs = process.argv.slice(2);
  let { paths, filterId } = resolveInputs(cliArgs);
  let sources = paths;

  if (filterId) {
    const source = findSourceById(filterId);
    if (!source) {
      console.error(`[intent-dual] catalog 中未找到: ${filterId}`);
      process.exit(1);
    }
    sources = [source];
  }

  if (!process.env.INTENT_SKIP_DATA_PREP) {
    const dataPrep = ensureIntentData({ sources, filterId });
    if (dataPrep.fatal) {
      process.exit(1);
    }
  }

  console.log('[intent-dual] 并行启动 Android + iOS worker…');
  const forwardArgs = filterId ? ['--id', filterId] : cliArgs;

  const [androidCode, iosCode] = await Promise.all([
    spawnWorker('android', forwardArgs),
    spawnWorker('ios', forwardArgs),
  ]);

  const androidResult = readRunResult('android');
  const iosResult = readRunResult('ios');

  try {
    const reportPath = generateDualReport({
      sources,
      android: androidResult,
      ios: iosResult,
    });
    console.log(`[intent-dual] 📊 双端聚合报告: ${reportPath}`);
  } catch (e) {
    console.error(`[intent-dual] 双端报告生成失败: ${e.message}`);
  }

  const exitCode = androidCode !== 0 || iosCode !== 0 ? 1 : 0;
  if (exitCode) {
    console.error(
      `[intent-dual] 完成 — Android exit=${androidCode}, iOS exit=${iosCode}`,
    );
  } else {
    console.log('[intent-dual] 双端全部通过');
  }
  process.exit(exitCode);
}

main();
