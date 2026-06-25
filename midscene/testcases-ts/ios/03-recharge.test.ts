import { agentFromWebDriverAgent, IOSAgent } from '@midscene/ios';
import { describe, it, beforeAll, afterAll } from 'vitest';
import { config, AI_ACTION_CONTEXT, sleep } from '../../utils/env';

let agent: IOSAgent;

describe('SoulChill iOS - 充值钱包模块', () => {
  beforeAll(async () => {
    agent = await agentFromWebDriverAgent({
      wdaHost: config.wdaHost,
      wdaPort: config.wdaPort,
      aiActionContext: AI_ACTION_CONTEXT,
    });
    await agent.page.launch('soulchill://login');
    await sleep(3000);
    await agent.aiWaitFor('首页底部导航栏可见', { timeoutMs: 20000 });
  });

  afterAll(async () => {
    await agent.page.destroy();
  });

  it('应能进入我的钱包页面', async () => {
    await agent.aiAct('点击底部导航栏的"我的"Tab 或个人头像');
    await sleep(1000);

    await agent.aiAct('点击"我的钱包"或"余额"入口');
    await sleep(1500);

    await agent.aiWaitFor('钱包页面加载完成', { timeoutMs: 15000 });
    await agent.aiAssert('当前在钱包页面，可以看到余额或充值选项');
  });

  it('应显示充值档位列表', async () => {
    await agent.aiAct('如果有充值按钮或"充值"入口，点击它');
    await sleep(1500);

    await agent.aiWaitFor('充值页面加载，显示充值金额档位', { timeoutMs: 15000 });

    const packages = await agent.aiQuery(
      '{ amount: string, bonus: string }[], 获取充值页面中所有充值档位的金额和赠送信息',
    );
    console.log('[充值档位]', JSON.stringify(packages, null, 2));
    await agent.aiAssert('页面中至少显示一个充值金额档位');
  });

  it('应能查看当前余额', async () => {
    await agent.aiAct('返回到钱包主页面');
    await sleep(1000);

    const walletInfo = await agent.aiQuery(
      '{ balance: string, currency: string }, 获取钱包页面显示的余额金额和货币单位',
    );
    console.log('[当前余额]', JSON.stringify(walletInfo, null, 2));
    await agent.aiAssert('钱包页面显示了余额数字');
  });

  it('消费账单应能正常加载', async () => {
    await agent.aiAct('找到并点击"消费记录"、"账单"或"明细"入口');
    await sleep(1500);

    await agent.aiWaitFor('账单页面加载完成', { timeoutMs: 15000 });
    await agent.aiAssert('账单页面正常显示，无报错');
  });
});
