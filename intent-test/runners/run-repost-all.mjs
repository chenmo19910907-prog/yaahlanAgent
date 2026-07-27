#!/usr/bin/env node
/**
 * 转发动态全量意图测试：跑全部 YAML → auto-fix → 多轮重跑 → 合并总报告
 *
 * 用法: node runners/run-repost-all.mjs [--max-rounds 3]
 */

import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';
import { runIntentPlatform } from './intent-run-lib.mjs';
import { generateReport, mergeResultsFromDisk } from './generate-report.mjs';
import { autoFixAfterRun } from './auto-fix-assertions.mjs';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');

const REPOST_SOURCES = [
  'intents/动态/转发动态/repost-entry.yaml',
  'intents/动态/转发动态/repost-editor.yaml',
  'intents/动态/转发动态/repost-publish.yaml',
  'intents/动态/转发动态/repost-feed.yaml',
  'intents/动态/转发动态/repost-restrictions.yaml',
  'intents/动态/转发动态/repost-unavailable.yaml',
  'intents/动态/转发动态/repost-profile.yaml',
].map((p) => resolve(ROOT, p));

const REPORT_OPTS = {
  moduleName: '转发动态（v2.5.8 全量）',
  reportSlug: '转发动态',
  platformLabel: 'Android',
};

function parseArgs() {
  const args = process.argv.slice(2);
  const idx = args.indexOf('--max-rounds');
  return { maxRounds: idx !== -1 ? Number(args[idx + 1]) : 3 };
}

function countMergedStats() {
  const merged = mergeResultsFromDisk(REPOST_SOURCES, []);
  const pass = merged.filter((r) => r.passed).length;
  const skip = merged.filter((r) => r.skipped).length;
  const timeout = merged.filter((r) => r.timedOut).length;
  const fail = merged.length - pass - skip - timeout;
  return { merged, pass, skip, timeout, fail };
}

function writeCombinedReport() {
  const { merged, pass, skip, timeout, fail } = countMergedStats();
  console.log(
    `[repost-all] 总报告: ${merged.length} 条 → 通过 ${pass} / 失败 ${fail} / 超时 ${timeout} / 跳过 ${skip}`,
  );
  return generateReport(REPOST_SOURCES, merged, REPORT_OPTS);
}

function main() {
  const { maxRounds } = parseArgs();
  let round = 0;
  let lastExit = 0;

  while (round < maxRounds) {
    round += 1;
    console.log(`\n[repost-all] ===== 第 ${round}/${maxRounds} 轮全量跑批 =====`);
    const result = runIntentPlatform({
      platform: 'android',
      sources: REPOST_SOURCES,
      filterId: null,
      skipDataPrep: process.env.INTENT_SKIP_DATA_PREP === '1',
      writeResultJson: false,
      usePlatformSubdir: false,
      skipSummaryReport: true,
    });
    lastExit = result.exitCode ?? 1;

    try {
      autoFixAfterRun(REPOST_SOURCES, mergeResultsFromDisk(REPOST_SOURCES, result.results ?? []));
    } catch (e) {
      console.error(`[repost-all] auto-fix 异常: ${e.message}`);
    }

    const { fail } = countMergedStats();
    if (fail === 0) {
      console.log('[repost-all] 全量通过（含 merge-latest 历史通过），结束重跑');
      break;
    }
    console.log(`[repost-all] 仍有 ${fail} 条未通过`);
    if (round >= maxRounds) {
      console.log('[repost-all] 已达最大轮次，生成总报告后退出');
    }
  }

  const reportPath = writeCombinedReport();
  console.log(`\n[repost-all] 📊 总测试报告: ${reportPath}`);
  process.exit(lastExit === 0 ? 0 : 1);
}

main();
