#!/usr/bin/env node
/**
 * 单平台 worker（供 intent-run-dual 或手动按平台执行）
 *
 * 用法:
 *   node runners/intent-run-platform.mjs --platform android intents/动态/...
 *   node runners/intent-run-platform.mjs --platform ios --module 动态
 */

import { resolveInputs, findSourceById, runIntentPlatform } from './intent-run-lib.mjs';

function main() {
  const args = process.argv.slice(2);
  const platIdx = args.indexOf('--platform');
  if (platIdx === -1 || !args[platIdx + 1]) {
    console.error('用法: intent-run-platform.mjs --platform android|ios <intent.yaml> | --module <名> | --id <ID>');
    process.exit(1);
  }
  const platform = String(args[platIdx + 1]).toLowerCase();
  const cliArgs = args.filter((_, i) => i !== platIdx && i !== platIdx + 1);

  let { paths, filterId } = resolveInputs(cliArgs);
  let sources = paths;

  if (filterId && sources.length === 0) {
    const source = findSourceById(filterId);
    if (!source) {
      console.error(`[intent-run:${platform}] catalog 中未找到: ${filterId}`);
      process.exit(1);
    }
    sources = [source];
  }

  const result = runIntentPlatform({
    platform,
    sources,
    filterId,
    skipDataPrep: process.env.INTENT_SKIP_DATA_PREP === '1',
    writeResultJson: true,
    usePlatformSubdir: true,
  });

  process.exit(result.exitCode ?? (result.skipped ? 0 : 1));
}

main();
