#!/usr/bin/env node
import { readFileSync } from 'fs';
import { dirname, resolve } from 'path';
import { fileURLToPath } from 'url';

const ROOT = resolve(dirname(fileURLToPath(import.meta.url)), '..');
const catalog = JSON.parse(readFileSync(resolve(ROOT, 'intents/catalog.json'), 'utf8'));

console.log('意图测试 catalog\n');
for (const [mod, info] of Object.entries(catalog.modules ?? {})) {
  console.log(`## ${mod}`);
  for (const p of info.intents ?? []) {
    console.log(`  - ${p}`);
  }
  console.log('');
}
