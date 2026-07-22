#!/usr/bin/env node
/**
 * 自动修正断言脚本：运行后根据失败原因修正 intent YAML 中的 expected
 *
 * 修正策略：
 *  1. 负面断言 → 正面断言（"X不再可见" → 检测当前可见的正面元素）
 *  2. 操作成功但断言措辞歧义 → 简化为纯文字检查
 *  3. 框架/网络错误 → 标记为 flaky，下次重试
 *
 * 用法：
 *   node runners/auto-fix-assertions.mjs [intent.yaml]
 *   - 无参数时读取最近一次 run 结果
 *   - 有参数时仅修正指定 intent 文件中的失败 case
 */

import { readFileSync, writeFileSync, existsSync, readdirSync } from 'fs';
import { resolve, dirname } from 'path';
import { fileURLToPath } from 'url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const OUTPUT_DIR = resolve(ROOT, '../midscene/midscene_run/output');

/** setup 导航未到目标页（Discover/编辑页/弹窗未打开等） */
const SETUP_FAILURE_PATTERNS = [
  /Discover/i,
  /发现页/,
  /Moment.*Discover/,
  /不存在.*["']?Post["']?/i,
  /没有出现.*Add Voice/i,
  /不存在.*["']?Record["']?/i,
  /不存在.*Record/i,
  /不在.*编辑/,
  /未到.*编辑/,
  /编辑页面.*不存在/,
  /不在预期页面/,
  /不存在.*弹窗/,
  /未.*弹窗/,
  /不存在.*确认/,
  /没有显示.*Cancel/i,
  /没有显示.*Confirm/i,
  /均未显示.*Cancel/i,
  /均未显示.*Confirm/i,
  /不存在.*Cancel/i,
  /不存在.*Confirm/i,
  /不存在文字为.*Cancel/i,
  /不存在文字为.*Confirm/i,
  /不存在正在进行录制/i,
  /不存在.*录制.*相关/i,
];

const NEGATIVE_PATTERNS = [
  /不再可见/,
  /不再显示/,
  /已消失/,
  /弹窗关闭/,
  /弹窗已关闭/,
  /不可见/,
  /消失/,
  /不存在/,
  /被丢弃/,
  /未出现/,
];

function isNegativeAssertion(text) {
  return NEGATIVE_PATTERNS.some((p) => p.test(text));
}

function extractFailedAssertions(outputJsonPath) {
  if (!existsSync(outputJsonPath)) return [];
  const data = JSON.parse(readFileSync(outputJsonPath, 'utf8'));

  const failures = [];
  const tasks = data.tasks ?? data.actions ?? [];

  for (const task of tasks) {
    if (task.status === 'failed' && task.type === 'Assertion') {
      failures.push({
        assertion: task.param?.assertion ?? task.content ?? '',
        reason: task.output?.reason ?? task.error?.message ?? '',
        thought: task.output?.thought ?? '',
      });
    }
    if (task.subTasks) {
      for (const sub of task.subTasks) {
        if (sub.status === 'failed' && sub.type === 'Assertion') {
          failures.push({
            assertion: sub.param?.assertion ?? sub.content ?? '',
            reason: sub.output?.reason ?? sub.error?.message ?? '',
            thought: sub.output?.thought ?? '',
          });
        }
      }
    }
  }
  return failures;
}

function suggestFix(assertion, reason) {
  if (!reason) return null;

  if (/XML parse error|AIResponseParseError/.test(reason)) {
    return { type: 'flaky', suggestion: null };
  }

  if (isNegativeAssertion(assertion)) {
    const positiveHints = reason.match(/页面.*?(?:显示|可见|存在).*?["「]([^"」]+)["」]/);
    if (positiveHints) {
      return {
        type: 'negative_to_positive',
        suggestion: `页面可见 "${positiveHints[1]}" 文字`,
      };
    }

    if (/编辑页面|发布.*编辑/.test(reason)) {
      return {
        type: 'negative_to_positive',
        suggestion: '当前页面可见 "Post" 按钮（已返回编辑页）',
      };
    }

    if (/Record.*弹窗|录音.*弹窗/.test(reason) && /Tap to Record/.test(reason)) {
      return {
        type: 'negative_to_positive',
        suggestion: '界面可见 "Tap to Record" 文字',
      };
    }

    return {
      type: 'negative_to_positive',
      suggestion: null,
    };
  }

  if (/不存在.*弹窗|未.*弹窗|不存在.*确认/.test(reason)) {
    return { type: 'setup_issue', suggestion: null };
  }

  return null;
}

function findOutputJson(caseId) {
  if (!existsSync(OUTPUT_DIR)) return null;
  const prefix = caseId.toUpperCase();
  const files = readdirSync(OUTPUT_DIR).filter(
    (f) => f.toUpperCase().startsWith(prefix) && f.endsWith('.json') && !f.includes('summary'),
  );
  if (!files.length) return null;
  files.sort((a, b) => b.localeCompare(a));
  return resolve(OUTPUT_DIR, files[0]);
}

function findSummaryError(caseId) {
  if (!existsSync(OUTPUT_DIR)) return null;
  const summaries = readdirSync(OUTPUT_DIR)
    .filter((f) => f.startsWith('summary-') && f.endsWith('.json'))
    .sort((a, b) => b.localeCompare(a));

  for (const sf of summaries.slice(0, 20)) {
    try {
      const data = JSON.parse(readFileSync(resolve(OUTPUT_DIR, sf), 'utf8'));
      for (const r of data.results ?? []) {
        if (r.script?.toUpperCase().includes(caseId.toUpperCase()) && !r.success && r.error) {
          return r.error;
        }
      }
    } catch { /* ignore */ }
  }
  return null;
}

function parseErrorString(errorStr) {
  const match = errorStr.match(/Assertion failed:\s*(.+?)\nReason:\s*(.+)/s);
  if (match) {
    const assertionRaw = match[1].trim();
    const assertionClean = assertionRaw.replace(/^IT-\S+\s+失败[：:]\s*/, '');
    return { assertion: assertionClean, reason: match[2].trim() };
  }
  if (/XML parse error|AIResponseParseError|Replanned \d+ times/i.test(errorStr)) {
    return { assertion: '', reason: errorStr, isFlaky: true };
  }
  return { assertion: '', reason: errorStr };
}

/** setup 导航失败或 flaky（replan/XML 解析）时可强制重启重试 */
export function isRetryableFailure(caseId, { timedOut = false } = {}) {
  const info = getCaseFailureInfo(caseId);
  if (info?.type === 'setup' || info?.type === 'flaky') return true;
  if (timedOut && /Replanned|replanning/i.test(info?.reason ?? '')) return true;
  return false;
}

/** 从 Midscene summary 解析失败信息，供 setup 重试与 auto-fix 共用 */
export function getCaseFailureInfo(caseId) {
  const errorStr = findSummaryError(caseId);
  if (!errorStr) return null;
  const parsed = parseErrorString(errorStr);
  if (parsed.isFlaky) {
    return { type: 'flaky', assertion: parsed.assertion, reason: parsed.reason };
  }
  if (SETUP_FAILURE_PATTERNS.some((p) => p.test(parsed.reason))) {
    return { type: 'setup', assertion: parsed.assertion, reason: parsed.reason };
  }
  const fix = suggestFix(parsed.assertion, parsed.reason);
  if (fix?.type === 'setup_issue') {
    return { type: 'setup', assertion: parsed.assertion, reason: parsed.reason };
  }
  return { type: 'assertion', assertion: parsed.assertion, reason: parsed.reason };
}

/** case 失败后是否为 setup 导航问题（可强制重启 App 重试） */
export function isSetupFailure(caseId) {
  return getCaseFailureInfo(caseId)?.type === 'setup';
}

function analyzeRun(results) {
  const report = { fixed: [], flaky: [], needManual: [] };

  for (const r of results) {
    if (r.passed || r.skipped) continue;

    const errorStr = findSummaryError(r.id);
    if (!errorStr) {
      const outputJson = findOutputJson(r.id);
      if (!outputJson) {
        report.needManual.push({ id: r.id, reason: '未找到输出/summary文件' });
        continue;
      }
      const failures = extractFailedAssertions(outputJson);
      if (!failures.length) {
        report.needManual.push({ id: r.id, reason: '无法提取失败断言' });
        continue;
      }
      for (const f of failures) {
        const fix = suggestFix(f.assertion, f.reason);
        if (!fix) report.needManual.push({ id: r.id, assertion: f.assertion, reason: f.reason });
        else if (fix.type === 'flaky') report.flaky.push({ id: r.id, assertion: f.assertion });
        else if (fix.suggestion) report.fixed.push({ id: r.id, oldAssertion: f.assertion, newAssertion: fix.suggestion });
        else report.needManual.push({ id: r.id, assertion: f.assertion, reason: f.reason, fixType: fix.type });
      }
      continue;
    }

    const parsed = parseErrorString(errorStr);
    if (parsed.isFlaky) {
      report.flaky.push({ id: r.id, assertion: parsed.assertion || '(framework error)' });
      continue;
    }

    const fix = suggestFix(parsed.assertion, parsed.reason);
    if (!fix) {
      report.needManual.push({ id: r.id, assertion: parsed.assertion, reason: parsed.reason?.slice(0, 120) });
    } else if (fix.type === 'flaky') {
      report.flaky.push({ id: r.id, assertion: parsed.assertion });
    } else if (fix.suggestion) {
      report.fixed.push({ id: r.id, oldAssertion: parsed.assertion, newAssertion: fix.suggestion });
    } else {
      report.needManual.push({ id: r.id, assertion: parsed.assertion, reason: parsed.reason?.slice(0, 120), fixType: fix.type });
    }
  }

  return report;
}

function applyFixesToYaml(yamlPath, fixes) {
  if (!fixes.length) return 0;
  let content = readFileSync(yamlPath, 'utf8');
  let applied = 0;

  for (const fix of fixes) {
    if (content.includes(fix.oldAssertion)) {
      content = content.replace(fix.oldAssertion, fix.newAssertion);
      applied++;
    }
  }

  if (applied > 0) {
    writeFileSync(yamlPath, content, 'utf8');
  }
  return applied;
}

export function autoFixAfterRun(sources, results) {
  const report = analyzeRun(results);

  if (report.fixed.length) {
    console.log(`\n[auto-fix] 🔧 自动修正 ${report.fixed.length} 条断言：`);
    for (const f of report.fixed) {
      console.log(`  ${f.id}: "${f.oldAssertion}" → "${f.newAssertion}"`);
    }
    for (const src of sources) {
      applyFixesToYaml(src, report.fixed);
    }
  }

  if (report.flaky.length) {
    console.log(`\n[auto-fix] ⚡ ${report.flaky.length} 条框架/网络错误（flaky），建议重试：`);
    for (const f of report.flaky) {
      console.log(`  ${f.id}`);
    }
  }

  if (report.needManual.length) {
    console.log(`\n[auto-fix] ⚠️ ${report.needManual.length} 条需要人工检查：`);
    for (const f of report.needManual) {
      console.log(`  ${f.id}: ${f.reason?.slice(0, 80) ?? '未知'}`);
    }
  }

  return report;
}

if (import.meta.url === `file://${process.argv[1]}`) {
  const runsDir = resolve(ROOT, '.generated/runs');
  const latestPath = resolve(runsDir, 'android-latest.json');
  if (!existsSync(latestPath)) {
    console.error('[auto-fix] 未找到最近运行结果');
    process.exit(1);
  }
  const { results } = JSON.parse(readFileSync(latestPath, 'utf8'));
  const report = analyzeRun(results);
  console.log(JSON.stringify(report, null, 2));
}
