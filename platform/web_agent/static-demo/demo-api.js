/**
 * GitHub Pages 静态演示：拦截 /api/* 与 SSE，使用假数据，不依赖服务端。
 */
(function initWebAgentDemoApi(global) {
  'use strict';

  if (global.__WEB_AGENT_DEMO_API__) return;
  global.__WEB_AGENT_DEMO_API__ = true;
  global.__WEB_AGENT_DEMO__ = true;

  const FIXTURES = global.__WEB_AGENT_FIXTURES__ || null;

  /** @type {import('./demo-api-types').DemoState | null} */
  let state = null;
  let fixturesReady;

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function nowIso() {
    return new Date().toISOString();
  }

  function randomHex(bytes) {
    let out = '';
    for (let i = 0; i < bytes; i += 1) {
      out += Math.floor(Math.random() * 256).toString(16).padStart(2, '0');
    }
    return out;
  }

  function jsonResponse(body, status = 200) {
    return new Response(JSON.stringify(body), {
      status,
      headers: { 'Content-Type': 'application/json; charset=utf-8' },
    });
  }

  function parseBody(init) {
    if (!init || !init.body) return {};
    try {
      return JSON.parse(String(init.body));
    } catch {
      return {};
    }
  }

  function ensureState() {
    if (state) return state;
    if (!FIXTURES) {
      throw new Error('演示 fixtures 未加载');
    }
    const sessions = clone(FIXTURES.sessions || []);
    const messages = clone(FIXTURES.messages || {});
    state = {
      meta: clone(FIXTURES.meta || {}),
      authStatus: clone(FIXTURES.authStatus || {}),
      catalog: clone(FIXTURES.catalog || {}),
      webDocs: clone(FIXTURES.webDocs || {}),
      messageBoard: clone(FIXTURES.messageBoard || { messages: [] }),
      webUsers: clone(FIXTURES.webUsers || { users: [], groups: [], total: 0 }),
      sessions,
      messages,
      runs: new Map(),
      activeBySession: new Map(),
    };
    return state;
  }

  function getSession(sessionId) {
    return ensureState().sessions.find((item) => item.id === sessionId) || null;
  }

  function relativeTime() {
    return '刚刚';
  }

  function touchSession(sessionId) {
    const session = getSession(sessionId);
    if (!session) return;
    const now = nowIso();
    session.updated_at = now;
    session.relative_time = relativeTime();
    const msgs = ensureState().messages[sessionId] || [];
    session.message_count = msgs.length;
    const last = msgs[msgs.length - 1];
    if (last && last.content) {
      session.latest_preview = String(last.content).replace(/\s+/g, ' ').slice(0, 80);
    }
  }

  function sortSessions(items) {
    return items.slice().sort((a, b) => {
      const ap = a.pinned ? 1 : 0;
      const bp = b.pinned ? 1 : 0;
      if (ap !== bp) return bp - ap;
      return String(b.updated_at).localeCompare(String(a.updated_at));
    });
  }

  function buildDemoReply(message) {
    const text = String(message || '').trim();
    if (/stage|送礼/i.test(text)) {
      return (
        '## Stage 送礼验收（演示模式）\n\n'
        + '已模拟完成 Stage 房间送礼流程：\n\n'
        + '| 步骤 | 状态 |\n| --- | --- |\n'
        + '| 参数校验 | ✅ |\n'
        + '| 调用 `/gift/send` | ✅ |\n'
        + '| ec/em 核对 | `0 / success` |\n\n'
        + '> 完整能力需连接内网 Web Agent 与 Stage 环境。'
      );
    }
    if (/prd|用例|测试点/i.test(text)) {
      return (
        '## 用例生成（演示模式）\n\n'
        + '已根据你的描述生成示例测试点：\n\n'
        + '1. 正常上传 PRD 并生成用例\n'
        + '2. 空文档与格式错误提示\n'
        + '3. 导出 Excel 与钉钉同步\n\n'
        + '内网版本将读取真实钉钉文档并写入表格。'
      );
    }
    if (/moa|userid|手机号|查数/i.test(text)) {
      return (
        '## MOA 查数（演示模式）\n\n'
        + '- 查询条件：`' + (text || '（未提供）') + '`\n'
        + '- 模拟结果 userId：`100465989`\n'
        + '- 环境：`stage`\n\n'
        + '连接内网后可执行真实 MOA 模板。'
      );
    }
    if (/tunnel|抓包|ec\/em/i.test(text)) {
      return (
        '## Tunnel 抓包（演示模式）\n\n'
        + '模拟最近 1 小时 `/gift/send` 请求：\n\n'
        + '```json\n'
        + '{ "ec": 0, "em": "success", "giftId": 2005004592 }\n'
        + '```\n\n'
        + '内网版本将拉取真实 Tunnel 日志。'
      );
    }
    return (
      '## 演示模式回复\n\n'
      + '> 当前页面为 **GitHub Pages 静态演示**，使用假数据，不连接服务端。\n\n'
      + '你发送的内容：\n\n'
      + '> ' + (text || '（空消息）') + '\n\n'
      + '可尝试快捷提示中的 **Stage 送礼**、**MOA 查数**、**用例生成** 等场景。'
    );
  }

  function buildStreamEvents(fullMarkdown) {
    const events = [
      { type: 'ack', line: '收到（演示模式）' },
      { type: 'status', phase_line: 'Agent 已启动…', elapsed_line: '0s' },
    ];
    const chunks = fullMarkdown.match(/[\s\S]{1,28}/g) || [fullMarkdown];
    let acc = '';
    for (const chunk of chunks) {
      acc += chunk;
      events.push({ type: 'delta', markdown: acc });
    }
    events.push({ type: 'done', text: fullMarkdown });
    return events;
  }

  function startRun(sessionId, userMessage) {
    const st = ensureState();
    const runId = randomHex(16);
    const reply = buildDemoReply(userMessage);
    const events = buildStreamEvents(reply);
    const run = {
      runId,
      sessionId,
      events,
      index: 0,
      done: false,
      finalText: reply,
      lastMarkdown: reply,
      lastAckLine: '收到（演示模式）',
      phaseLine: 'Agent 已启动…',
      elapsedLine: '1s',
    };
    st.runs.set(runId, run);
    st.activeBySession.set(sessionId, runId);
    const session = getSession(sessionId);
    if (session) session.running = true;
    return run;
  }

  function finishRun(runId) {
    const st = ensureState();
    const run = st.runs.get(runId);
    if (!run || run.done) return;
    run.done = true;
    st.activeBySession.delete(run.sessionId);
    const session = getSession(run.sessionId);
    if (session) session.running = false;
    const msgs = st.messages[run.sessionId] || (st.messages[run.sessionId] = []);
    msgs.push({
      role: 'assistant',
      content: run.finalText,
      timestamp: nowIso(),
    });
    touchSession(run.sessionId);
  }

  function activeRunPayload(runId) {
    const run = ensureState().runs.get(runId);
    if (!run || run.done) return { active: false };
    return {
      active: true,
      run_id: runId,
      ack_line: run.lastAckLine,
      phase_line: run.phaseLine,
      elapsed_line: run.elapsedLine,
      markdown: run.lastMarkdown,
    };
  }

  function handleApi(pathname, method, init) {
    const st = ensureState();
    const methodUpper = (method || 'GET').toUpperCase();
    const body = parseBody(init);

    if (pathname === '/api/meta' && methodUpper === 'GET') {
      return jsonResponse(st.meta);
    }
    if (pathname === '/api/auth/status' && methodUpper === 'GET') {
      return jsonResponse(st.authStatus);
    }
    if (pathname === '/api/auth/logout' && methodUpper === 'POST') {
      st.authStatus = { ...st.authStatus, loggedIn: false, user: undefined };
      return jsonResponse({ ok: true });
    }
    if (pathname === '/api/catalog' && methodUpper === 'GET') {
      return jsonResponse(st.catalog);
    }
    if (pathname === '/api/web-docs' && methodUpper === 'GET') {
      return jsonResponse(st.webDocs);
    }
    if (pathname === '/api/message-board' && methodUpper === 'GET') {
      return jsonResponse(st.messageBoard);
    }
    if (pathname === '/api/message-board' && methodUpper === 'POST') {
      const entry = {
        id: randomHex(16),
        author: st.authStatus.user?.displayName || '演示用户',
        content: String(body.content || '').trim(),
        created_at: nowIso(),
      };
      st.messageBoard.messages = [entry, ...(st.messageBoard.messages || [])];
      return jsonResponse({ message: entry }, 201);
    }
    if (pathname.startsWith('/api/message-board/') && methodUpper === 'DELETE') {
      const messageId = decodeURIComponent(pathname.split('/').pop() || '');
      st.messageBoard.messages = (st.messageBoard.messages || []).filter((m) => m.id !== messageId);
      return jsonResponse({ ok: true });
    }
    if (pathname === '/api/web-users' && methodUpper === 'GET') {
      return jsonResponse(st.webUsers);
    }
    if (pathname === '/api/analytics/event' && methodUpper === 'POST') {
      return new Response(null, { status: 204 });
    }
    if (pathname === '/api/bookmarks/metadata' && methodUpper === 'GET') {
      return jsonResponse({ title: '演示站点', description: 'GitHub Pages 静态演示' });
    }
    if (pathname === '/api/bookmarks' && (methodUpper === 'POST' || methodUpper === 'PUT')) {
      if (body && body.categories) st.meta.bookmarks = body;
      return jsonResponse({ bookmarks: st.meta.bookmarks });
    }
    if (pathname === '/api/bookmarks/import-legacy' && methodUpper === 'POST') {
      return jsonResponse({ imported: 0 });
    }
    if (pathname === '/api/admin/apply' && methodUpper === 'POST') {
      return jsonResponse({ status: 'approved', isAdmin: true });
    }
    if (pathname === '/api/messages/forward' && methodUpper === 'POST') {
      return jsonResponse({ ok: true, forwarded: 0 });
    }

    if (pathname === '/api/sessions' && methodUpper === 'GET') {
      const items = sortSessions(st.sessions).map((session) => ({ ...session }));
      return jsonResponse({ sessions: items, query: '', scope: 'all' });
    }

    if (pathname === '/api/sessions' && methodUpper === 'POST') {
      const id = randomHex(16);
      const now = nowIso();
      const session = {
        id,
        title: String(body.title || '新对话'),
        auto_title: String(body.title || '新对话'),
        created_at: now,
        updated_at: now,
        message_count: 0,
        relative_time: relativeTime(),
        source: 'web',
        web_owner: st.authStatus.user?.displayName || '演示用户',
        web_owner_label: st.authStatus.user?.displayName || '演示用户',
        web_owner_id: st.authStatus.user?.staffId || 'demo-user',
        is_mine: true,
        can_manage_collaborators: true,
        pinned: false,
      };
      st.sessions.unshift(session);
      st.messages[id] = [];
      return jsonResponse(session, 201);
    }

    let match = pathname.match(/^\/api\/sessions\/([a-z0-9]+)$/);
    if (match && methodUpper === 'DELETE') {
      const sessionId = match[1];
      st.sessions = st.sessions.filter((s) => s.id !== sessionId);
      delete st.messages[sessionId];
      return jsonResponse({ ok: true });
    }

    match = pathname.match(/^\/api\/sessions\/([a-z0-9]+)\/messages$/);
    if (match && methodUpper === 'GET') {
      const sessionId = match[1];
      if (!getSession(sessionId)) return jsonResponse({ error: 'session not found' }, 404);
      return jsonResponse({ messages: st.messages[sessionId] || [] });
    }

    match = pathname.match(/^\/api\/sessions\/([a-z0-9]+)\/active-run$/);
    if (match && methodUpper === 'GET') {
      const sessionId = match[1];
      const runId = st.activeBySession.get(sessionId);
      if (!runId) return jsonResponse({ active: false });
      return jsonResponse(activeRunPayload(runId));
    }

    match = pathname.match(/^\/api\/sessions\/([a-z0-9]+)\/pin$/);
    if (match && methodUpper === 'PUT') {
      const session = getSession(match[1]);
      if (!session) return jsonResponse({ error: 'session not found' }, 404);
      session.pinned = Boolean(body.pinned);
      session.pinned_at = session.pinned ? nowIso() : '';
      touchSession(session.id);
      return jsonResponse(session);
    }

    match = pathname.match(/^\/api\/sessions\/([a-z0-9]+)\/title$/);
    if (match && methodUpper === 'PUT') {
      const session = getSession(match[1]);
      if (!session) return jsonResponse({ error: 'session not found' }, 404);
      const title = String(body.title || '').trim() || session.title;
      session.title = title;
      session.custom_title = title;
      touchSession(session.id);
      return jsonResponse(session);
    }

    match = pathname.match(/^\/api\/sessions\/([a-z0-9]+)\/collaborators$/);
    if (match && methodUpper === 'PUT') {
      const session = getSession(match[1]);
      if (!session) return jsonResponse({ error: 'session not found' }, 404);
      const ids = Array.isArray(body.collaborator_ids) ? body.collaborator_ids.map(String) : [];
      session.web_collaborator_ids = ids;
      session.web_collaborators = ids.map((staffId) => ({
        staffId,
        displayName: staffId === 'demo-peer' ? '测试同学' : '协作者',
      }));
      return jsonResponse(session);
    }

    if (pathname === '/api/chat' && methodUpper === 'POST') {
      const sessionId = String(body.session_id || '').trim();
      const message = String(body.message || '').trim();
      if (!sessionId || !message) {
        return jsonResponse({ error: 'session_id required; message or attachments required' }, 400);
      }
      if (!getSession(sessionId)) return jsonResponse({ error: 'session not found' }, 404);
      const msgs = st.messages[sessionId] || (st.messages[sessionId] = []);
      msgs.push({ role: 'user', content: message, timestamp: nowIso() });
      touchSession(sessionId);
      const run = startRun(sessionId, message);
      return jsonResponse({ run_id: run.runId, session_id: sessionId });
    }

    if (pathname === '/api/chat/cancel' && methodUpper === 'POST') {
      const sessionId = String(body.session_id || '').trim();
      const runId = st.activeBySession.get(sessionId);
      if (runId) finishRun(runId);
      return jsonResponse({ ok: true });
    }

    return jsonResponse({ error: `演示模式未实现: ${methodUpper} ${pathname}` }, 404);
  }

  const originalFetch = global.fetch.bind(global);
  global.fetch = function demoFetch(input, init) {
    const url = typeof input === 'string' ? input : input.url;
    const method = (init && init.method) || (typeof input !== 'string' && input.method) || 'GET';
  return Promise.resolve()
      .then(() => fixturesReady)
      .then(() => {
        let pathname = url;
        try {
          pathname = new URL(url, global.location.href).pathname;
        } catch {
          /* keep raw */
        }
        if (pathname.startsWith('/api/') || String(url).startsWith('/api/')) {
          return handleApi(pathname, method, init);
        }
        return originalFetch(input, init);
      });
  };

  class MockEventSource extends EventTarget {
    constructor(url) {
      super();
      this.url = url;
      this.readyState = 0;
      this.CONNECTING = 0;
      this.OPEN = 1;
      this.CLOSED = 2;
      queueMicrotask(() => this._open());
    }

    _open() {
      fixturesReady.then(() => {
        const match = String(this.url).match(/\/api\/chat\/stream\/([a-f0-9]+)/);
        const runId = match && match[1];
        const run = runId ? ensureState().runs.get(runId) : null;
        if (!run) {
          this.readyState = 2;
          this.dispatchEvent(new Event('error'));
          return;
        }
        this.readyState = 1;
        const emitNext = () => {
          if (this.readyState === 2) return;
          const event = run.events[run.index];
          if (!event) {
            this.readyState = 2;
            return;
          }
          run.index += 1;
          if (event.type === 'ack') run.lastAckLine = event.line || '';
          if (event.type === 'status') {
            if (event.phase_line) run.phaseLine = event.phase_line;
            if (event.elapsed_line) run.elapsedLine = event.elapsed_line;
          }
          if (event.type === 'delta' && event.markdown) run.lastMarkdown = event.markdown;
          this.dispatchEvent(new MessageEvent('message', { data: JSON.stringify(event) }));
          if (event.type === 'done' || event.type === 'error') {
            finishRun(run.runId);
            this.readyState = 2;
            return;
          }
          const delay = event.type === 'delta' ? 35 : 90;
          setTimeout(emitNext, delay);
        };
        setTimeout(emitNext, 60);
      }).catch(() => {
        this.readyState = 2;
        this.dispatchEvent(new Event('error'));
      });
    }

    close() {
      this.readyState = 2;
    }
  }
  MockEventSource.CONNECTING = 0;
  MockEventSource.OPEN = 1;
  MockEventSource.CLOSED = 2;
  global.EventSource = MockEventSource;

  fixturesReady = Promise.resolve().then(() => {
    ensureState();
  });
})(window);
