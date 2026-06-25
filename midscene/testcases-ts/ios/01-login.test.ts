import { agentFromWebDriverAgent, IOSAgent } from '@midscene/ios';
import { describe, it, beforeAll, afterAll, expect } from 'vitest';
import { config, AI_ACTION_CONTEXT, sleep } from '../../utils/env';

let agent: IOSAgent;

describe('SoulChill iOS - 登录模块', () => {
  beforeAll(async () => {
    agent = await agentFromWebDriverAgent({
      wdaHost: config.wdaHost,
      wdaPort: config.wdaPort,
      aiActionContext: AI_ACTION_CONTEXT,
    });
    // 启动 App（冷启动）
    await agent.page.launch(`soulchill://`);
    await sleep(3000);
  });

  afterAll(async () => {
    await agent.page.destroy();
  });

  it('应显示登录页面的关键元素', async () => {
    await agent.aiWaitFor('页面中出现登录相关内容，如手机号输入框或登录按钮', { timeoutMs: 15000 });
    await agent.aiAssert('当前页面是 SoulChill 登录或注册页面');
  });

  it('应能用手机号完成登录', async () => {
    // 进入手机号登录
    await agent.aiAct('如果有"手机号登录"或"密码登录"选项，点击它');
    await sleep(1000);

    // 输入手机号
    await agent.aiAct(`在手机号输入框中输入 "${config.testPhone}"`);
    await sleep(500);

    // 获取验证码
    await agent.aiAct('点击"获取验证码"或"发送验证码"按钮');
    await sleep(1000);

    // 输入验证码（测试环境使用固定验证码）
    await agent.aiAct(`在验证码输入框中输入 "${config.testVerifyCode}"`);
    await sleep(500);

    // 点击登录
    await agent.aiAct('点击"登录"或"确认"按钮完成登录');

    // 等待登录成功，进入首页
    await agent.aiWaitFor('登录成功，页面跳转到 SoulChill 首页，显示底部导航栏', { timeoutMs: 30000 });
    await agent.aiAssert('当前在 SoulChill 首页，底部导航栏可见');
  });

  it('应能退出登录后重新登录', async () => {
    // 进入"我的"页面
    await agent.aiAct('点击底部导航栏最右侧的"我的"或个人头像');
    await sleep(1000);

    // 进入设置
    await agent.aiAct('点击页面右上角的设置图标或"设置"入口');
    await sleep(1000);

    await agent.aiAct('向下滑动找到"退出登录"或"注销"按钮并点击');
    await sleep(1000);

    await agent.aiAct('如果出现确认退出弹窗，点击确认');
    await sleep(2000);

    await agent.aiWaitFor('已退出登录，返回登录页面');
    await agent.aiAssert('当前显示登录页面');
  });
});
