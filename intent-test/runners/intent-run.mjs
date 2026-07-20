#!/usr/bin/env node
/**
 * 编译并执行意图测试：Midscene UI + Tunnel 抓包验收（单端，默认 Android）
 */

import { resolveInputs, findSourceById, runIntentPlatform } from './intent-run-lib.mjs';

function main() {
  const cliArgs = process.argv.slice(2);
  let { paths, filterId } = resolveInputs(cliArgs);
  let sources = paths;

  if (filterId) {
    const source = findSourceById(filterId);
    if (!source) {
      console.error(`[intent-run] catalog 中未找到: ${filterId}`);
      process.exit(1);
    }
    sources = [source];
  }

  const platform = process.env.INTENT_PLATFORM?.toLowerCase() || 'android';
  const result = runIntentPlatform({
    platform,
    sources,
    filterId,
    skipDataPrep: process.env.INTENT_SKIP_DATA_PREP === '1',
    writeResultJson: false,
    usePlatformSubdir: false,
  });

  if (result.skipped && !result.runs?.length) {
    console.error('[intent-run] 无待执行用例');
    process.exit(1);
  }
  process.exit(result.exitCode ?? 0);
}

main();
