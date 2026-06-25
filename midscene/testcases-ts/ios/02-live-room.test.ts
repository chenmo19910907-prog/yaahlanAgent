import { agentFromWebDriverAgent, IOSAgent } from '@midscene/ios';
import { describe, it, beforeAll, afterAll } from 'vitest';
import { config, AI_ACTION_CONTEXT, sleep } from '../../utils/env';

let agent: IOSAgent;

describe('SoulChill iOS - 直播间模块', () => {
  beforeAll(async () => {
    agent = await agentFromWebDriverAgent({
      wdaHost: config.wdaHost,
      wdaPort: config.wdaPort,
      aiActionContext: AI_ACTION_CONTEXT,
    });
    // 通过 deeplink 直接到登录态首页
    await agent.page.launch('soulchill://login');
    await sleep(3000);
    await agent.aiWaitFor('首页底部导航栏可见', { timeoutMs: 20000 });
  });

  afterAll(async () => {
    await agent.page.destroy();
  });

  it('直播列表应正常加载', async () => {
    await agent.aiAct('点击底部导航栏的"直播"或首页 Tab');
    await sleep(2000);
    await agent.aiWaitFor('直播列表加载完成，页面中出现至少一个直播间封面', { timeoutMs: 20000 });

    const rooms = await agent.aiQuery(
      '{ roomName: string, hostName: string }[], 获取当前直播列表中前5个直播间的名称和主播名',
    );
    console.log('[直播列表]', JSON.stringify(rooms, null, 2));
    await agent.aiAssert('直播列表中至少有一个直播间');
  });

  it('应能进入直播间并看到基础功能', async () => {
    await agent.aiAct('点击直播列表中的第一个直播间');
    await sleep(3000);

    await agent.aiWaitFor('直播间已打开，可以看到主播画面或直播间界面', { timeoutMs: 20000 });
    await agent.aiAssert('当前在直播间内，底部有聊天输入框或礼物按钮');
  });

  it('应能发送聊天消息', async () => {
    await agent.aiAct('点击直播间底部的聊天输入框');
    await sleep(1000);
    await agent.aiAct('输入文字 "哈喽主播"');
    await sleep(500);
    await agent.aiAct('点击发送按钮');
    await sleep(1000);

    await agent.aiAssert('聊天消息已发送，消息列表中出现刚才的内容');
  });

  it('应能查看礼物列表', async () => {
    await agent.aiAct('点击直播间底部的礼物图标或礼物按钮');
    await sleep(1000);

    await agent.aiWaitFor('礼物面板已弹出，显示礼物列表', { timeoutMs: 10000 });

    const gifts = await agent.aiQuery(
      '{ giftName: string, price: number }[], 获取礼物面板中前5个礼物的名称和价格',
    );
    console.log('[礼物列表]', JSON.stringify(gifts, null, 2));
    await agent.aiAssert('礼物面板中至少有一个礼物');
  });

  it('应能退出直播间', async () => {
    // 关闭礼物面板
    await agent.aiAct('如果礼物面板还开着，点击空白区域关闭它');
    await sleep(500);

    await agent.aiAct('点击直播间左上角的关闭或返回按钮退出直播间');
    await sleep(1500);

    await agent.aiWaitFor('已退出直播间，回到直播列表页', { timeoutMs: 10000 });
    await agent.aiAssert('当前不在直播间内，已返回列表页或首页');
  });
});
