#!/usr/bin/env python3
"""验收 theme.js 自动模式：北京时间 08:00 白天、17:00 夜间。"""

from __future__ import annotations

import subprocess
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent
THEME_JS = ROOT / "theme.js"

NODE_SNIPPET = r"""
const fs = require('fs');
const vm = require('vm');
const { setTimeout, clearTimeout } = require('timers');
const code = fs.readFileSync(process.argv[1], 'utf8');
const RealDate = Date;
let fixedNow = new RealDate('2026-10-22T08:00:00+08:00');
function setBeijingMinutes(totalMin) {
  const h = Math.floor(totalMin / 60) % 24;
  const m = totalMin % 60;
  fixedNow = new RealDate(
    `2026-10-22T${String(h).padStart(2, '0')}:${String(m).padStart(2, '0')}:00+08:00`,
  );
}
const MockDate = class extends RealDate {
  constructor(...args) {
    if (args.length === 0) super(fixedNow.getTime());
    else super(...args);
  }
  static now() {
    return fixedNow.getTime();
  }
};
const sandbox = {
  window: {},
  document: {
    documentElement: { setAttribute() {} },
    readyState: 'loading',
    addEventListener() {},
    querySelectorAll() { return []; },
    getElementById() { return null; },
  },
  localStorage: {
    _m: {},
    getItem(k) { return this._m[k] ?? null; },
    setItem(k, v) { this._m[k] = v; },
    removeItem(k) { delete this._m[k]; },
  },
  navigator: {},
  addEventListener() {},
  setTimeout,
  clearTimeout,
  Date: MockDate,
};
sandbox.window = sandbox;
vm.runInNewContext(code, sandbox);
const T = sandbox.WebAgentTheme;
const checks = [
  [7 * 60 + 59, 'dark'],
  [8 * 60, 'light'],
  [16 * 60 + 59, 'light'],
  [17 * 60, 'dark'],
  [23 * 60, 'dark'],
];
for (const [mins, want] of checks) {
  setBeijingMinutes(mins);
  const got = T.resolveAutoTheme();
  if (got !== want) {
    console.error('FAIL at', mins, 'got', got, 'want', want);
    process.exit(1);
  }
}
console.log('OK', checks.length);
"""


class TestWebThemeAuto(unittest.TestCase):
    def test_beijing_fixed_auto_boundaries_in_node(self) -> None:
        proc = subprocess.run(
            ["node", "-e", NODE_SNIPPET, str(THEME_JS)],
            capture_output=True,
            text=True,
            cwd=str(ROOT),
            check=False,
        )
        self.assertEqual(proc.returncode, 0, proc.stderr or proc.stdout)
        self.assertIn("OK", proc.stdout)

    def test_theme_js_documents_beijing_schedule(self) -> None:
        text = THEME_JS.read_text(encoding="utf-8")
        self.assertIn("08:00", text)
        self.assertIn("17:00", text)


if __name__ == "__main__":
    unittest.main()
