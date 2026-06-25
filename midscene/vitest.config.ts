import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    globals: true,
    // 每个测试文件独立进程，避免设备连接互相干扰
    pool: 'forks',
    // 单个用例最长等待 3 分钟（AI 操作较慢）
    testTimeout: 180_000,
    hookTimeout: 60_000,
    // 测试失败时不重试，保留现场
    retry: 0,
    // 串行执行，防止多用例同时操作同一设备
    sequence: {
      concurrent: false,
    },
    reporters: ['verbose'],
  },
});
