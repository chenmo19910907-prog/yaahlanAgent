#!/usr/bin/env node
/**
 * 从 temporary_testcase Markdown 四列表生成意图 YAML 草稿
 *
 * 用法:
 *   node runners/md-to-intent.mjs ../temporary_testcase/xxx.md
 *   node runners/md-to-intent.mjs ../temporary_testcase/xxx.md --out intents/草稿/
 */

import { readFileSync, writeFileSync, mkdirSync } from 'fs';
import { dirname, resolve, basename } from 'path';
import { fileURLToPath } from 'url';
import { stringify } from 'yaml';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');

function parseMdTable(text) {
  const rows = [];
  for (const line of text.split('\n')) {
    const t = line.trim();
    if (!t.startsWith('|') || !t.endsWith('|')) continue;
    if (/^\|[\s:\-|]+\|$/.test(t)) continue;
    const cells = t.slice(1, -1).split('|').map((c) => c.trim());
    rows.push(cells);
  }
  if (rows.length < 2) return null;
  const header = rows[0];
  const idx = {
    module: header.findIndex((h) => h.includes('功能模块')),
    step: header.findIndex((h) => h.includes('测试步骤')),
    expect: header.findIndex((h) => h.includes('预期')),
    point: header.findIndex((h) => h.includes('测试点')),
  };
  if (idx.step < 0 || idx.expect < 0) {
    throw new Error('表头需含 测试步骤、预期结果');
  }
  return rows.slice(1).map((r) => ({
    module: r[idx.module] ?? '未分类',
    step: r[idx.step] ?? '',
    expect: r[idx.expect] ?? '',
    point: r[idx.point] ?? '',
  }));
}

function slug(s) {
  return s.replace(/[^\w\u4e00-\u9fff-]+/g, '-').replace(/^-|-$/g, '').slice(0, 40) || 'intent';
}

function rowToIntent(row, seq, fileStem) {
  if (row.step === '↑' || row.step === '同上') return null;
  const id = `IT-${slug(fileStem).toUpperCase().slice(0, 12)}-${String(seq).padStart(3, '0')}`;
  return {
    id,
    name: row.point || row.step.slice(0, 40),
    module: row.module,
    platform: 'android',
    priority: 'P1',
    tags: [row.module.split('-')[0] ?? 'misc'],
    preconditions: ['见手工用例前置数据'],
    setup: { launchApp: false },
    intent: {
      action: row.step,
      expected: [row.expect],
    },
    timeoutMs: 120000,
  };
}

function main() {
  const args = process.argv.slice(2);
  const mdPath = resolve(process.cwd(), args[0]);
  const outIdx = args.indexOf('--out');
  const outDir = outIdx !== -1
    ? resolve(process.cwd(), args[outIdx + 1])
    : resolve(ROOT, 'intents/草稿');

  const text = readFileSync(mdPath, 'utf8');
  const rows = parseMdTable(text);
  if (!rows) {
    console.error('[md-to-intent] 未找到 Markdown 表格');
    process.exit(1);
  }

  mkdirSync(outDir, { recursive: true });
  const stem = basename(mdPath, '.md');
  const docs = [];
  let seq = 0;
  for (const row of rows) {
    seq += 1;
    const doc = rowToIntent(row, seq, stem);
    if (doc) docs.push(doc);
  }

  const outPath = resolve(outDir, `${stem}.intent.yaml`);
  const body = docs.map((d) => stringify(d)).join('\n---\n\n');
  writeFileSync(outPath, `# 由 ${basename(mdPath)} 自动生成，请人工精简 action/expected\n\n${body}`, 'utf8');
  console.log(`[md-to-intent] ✓ ${docs.length} 条 → ${outPath}`);
}

main();
