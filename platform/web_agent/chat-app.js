    const API = '';
    let currentSessionId = '';
    const LEGACY_SESSION_STORAGE_KEY = 'web_agent_session';
    /** @type {{ staffId?: string, displayName?: string, isAdmin?: boolean } | null} */
    let currentAuthUser = null;
    let usageRangeKey = 'day';
    /** @type {{ start: string, end: string } | null} */
    let usageCustomRange = null;
    let usageRankOpen = false;
    /** @type {{ minDate?: string, maxDate?: string, earliestWithData?: string, preloadDays?: number } | null} */
    let usageDateBounds = null;
    const USAGE_MAX_CUSTOM_DAYS = 180;
    const CALL_LOG_MAX_CUSTOM_DAYS = 180;
    /** @type {Record<string, number>} */
    const usageStatsInflightSeq = Object.create(null);
    /** @type {AbortController | null} */
    let usageLoadAbortController = null;
    let otpAuthEnabled = true;
    /** @type {Map<string, { eventSource: EventSource, runId: string, runToken: string, cancelling?: boolean, failed?: boolean, status: { ack: string, lifecycle: string, phase: string, batch: string, external: string, elapsed: string }, shellEl: HTMLElement | null, sentDraft?: { text: string, images: typeof pendingImages } }>} */
    const activeRuns = new Map();
    /** 中断 API + 落盘完成前阻塞同会话 send，避免新 run 复用未 finalize 的 shell。 */
    const sessionCancelFlights = new Map();
    /** sendMessage 正在 await cancelFlight 时为 true，用于发送钮转圈。 */
    let sendAwaitingCancelFlight = false;

    function makeRunToken() {
      return `${Date.now().toString(36)}_${Math.random().toString(36).slice(2, 10)}`;
    }

    function isActiveRun(sessionId, { runToken = '', runId = '' } = {}) {
      const run = activeRuns.get(sessionId);
      if (!run) return false;
      if (runToken && run.runToken !== runToken) return false;
      if (runId && run.runId && run.runId !== runId) return false;
      return true;
    }

    function disposeRunResources(run) {
      if (!run) return;
      if (run.cancelWatchdog) {
        clearTimeout(run.cancelWatchdog);
        run.cancelWatchdog = null;
      }
      if (run.streamPollTimer) {
        clearInterval(run.streamPollTimer);
        run.streamPollTimer = null;
      }
      if (typeof run.streamDetach === 'function') {
        const detach = run.streamDetach;
        run.streamDetach = null;
        run.eventSource = null;
        detach();
        return;
      }
      if (run.eventSource) {
        run.eventSource.close();
        run.eventSource = null;
      }
    }
    const MESSAGES_SCROLL_NEAR_BOTTOM_PX = 80;
    const MESSAGES_LOAD_OLDER_ROOT_MARGIN = '160px 0px 0px 0px';
    const MESSAGES_TAIL_DEFAULT = 20;
    const MESSAGES_OLDER_PAGE = 80;
    const MESSAGES_RENDER_CHUNK = 12;
    const MESSAGES_RENDER_CHUNK_MOBILE = 3;
    const SESSION_LIST_MOBILE_CHUNK = 16;
    const MOBILE_SIDEBAR_LIST_DEFER_MS = 150;
    function mobileSessionListRenderOptions() {
      return isWebAgentMobile() ? { mobileChunked: true } : {};
    }
    function mobileSessionListDomReady() {
      const list = document.getElementById('session-list');
      return !!(list && list.querySelector('.session-item[data-id]'));
    }
    const MESSAGES_FIRST_PAINT_TAIL = 24;
    function messagesRenderChunkSize() {
      return isWebAgentMobile() ? MESSAGES_RENDER_CHUNK_MOBILE : MESSAGES_RENDER_CHUNK;
    }
    function scheduleMessagesRenderYield(fn) {
      if (isWebAgentMobile()) {
        setTimeout(fn, 0);
      } else {
        requestAnimationFrame(fn);
      }
    }
    /** 用户未手动上滑时，流式更新才跟随滚到底；执行完成后强制滚到底 */
    let messagesPinnedToBottom = true;
    let meta = {};
    let catalogPanel = null;
    let catalogPanelInitPromise = null;
    let bookmarksPanel = null;
    let messageBoardPanel = null;
    let aboutPanel = null;
    let moaRecordPanel = null;
    /** 工具台侧栏展开态与历史会话侧栏同键风格持久化；面板内目录/能力仍每次打开或刷新后默认收起 */
    const catalogPref = localStorage.getItem('web_agent_catalog_open');
    let catalogOpen = catalogPref === null ? false : catalogPref === '1';
    const sidebarPref = localStorage.getItem('web_agent_sidebar_open');
    let sidebarOpen = sidebarPref === null ? true : sidebarPref === '1';
    function isWebAgentMobile() {
      return document.documentElement.classList.contains('web-agent-mobile');
    }
    function mobileBootstrapForcedSessionId() {
      if (!isWebAgentMobile()) return '';
      try {
        const params = new URLSearchParams(location.search);
        return (params.get('session') || params.get('sessionId') || '').trim();
      } catch {
        return '';
      }
    }
    function shouldBootstrapRestorePersistedSession() {
      if (isGuestMode()) return false;
      if (isWebAgentMobile()) return !!mobileBootstrapForcedSessionId();
      return true;
    }
    if (isWebAgentMobile()) {
      sidebarOpen = false;
      catalogOpen = false;
    }
    function sessionStorageKey() {
      const staffId = (currentAuthUser?.staffId || '').trim();
      return staffId ? `web_agent_last_session_${staffId}` : LEGACY_SESSION_STORAGE_KEY;
    }

    function readPersistedSessionId() {
      const key = sessionStorageKey();
      const saved = (localStorage.getItem(key) || '').trim();
      if (saved) return saved;
      if (currentAuthUser?.staffId) {
        return (localStorage.getItem(LEGACY_SESSION_STORAGE_KEY) || '').trim();
      }
      return (localStorage.getItem(LEGACY_SESSION_STORAGE_KEY) || '').trim();
    }

    /** 鉴权完成前推断上次会话（与 layout shell 内联脚本一致） */
    function readLikelyPersistedSessionId() {
      const saved = readPersistedSessionId();
      if (saved) return saved;
      if (currentAuthUser?.staffId) return '';
      try {
        for (let i = 0; i < localStorage.length; i += 1) {
          const key = localStorage.key(i);
          if (!key || !key.startsWith('web_agent_last_session_')) continue;
          const value = (localStorage.getItem(key) || '').trim();
          if (value) return value;
        }
      } catch (_) { /* private mode */ }
      return (localStorage.getItem(LEGACY_SESSION_STORAGE_KEY) || '').trim();
    }

    function persistSessionId(id) {
      const sid = String(id || '').trim();
      if (!sid) return;
      localStorage.setItem(sessionStorageKey(), sid);
      if (currentAuthUser?.staffId) {
        localStorage.removeItem(LEGACY_SESSION_STORAGE_KEY);
      }
    }

    function clearPersistedSessionId() {
      localStorage.removeItem(sessionStorageKey());
      localStorage.removeItem(LEGACY_SESSION_STORAGE_KEY);
    }

    function myWritableWebSessions() {
      return sessionsCache.filter((s) => s.source === 'web' && !isSessionReadOnly(s));
    }

    async function activateSession(id, opts = {}) {
      const sessionId = String(id || '').trim();
      if (!sessionId) {
        showEmptyState();
        return false;
      }
      const scrollToTimestamp = (opts.scrollToTimestamp || '').trim();
      if (!opts.force && sessionId === currentSessionId && !scrollToTimestamp) return true;
      const prevSessionId = currentSessionId;
      const switchedSession = !!(prevSessionId && prevSessionId !== sessionId);
      if (switchedSession) {
        resetChatMessageSearch({ clearInput: true });
        saveCurrentSessionScrollState();
        saveSessionInputDraft(prevSessionId);
        clearMessagesDomRendered();
        loadMessagesAbort?.abort();
        sessionMessagesEtags.delete(sessionId);
        const container = getMessagesEl();
        if (container) {
          stopFeatureDemoCarousel();
          container.innerHTML = '';
          ensureLoadOlderButton(container);
          beginSessionMessagesLoading({ overlay: false });
          showMessagesBootstrapLoading();
        }
      }
      pendingScrollToTimestamp = scrollToTimestamp;
      currentSessionId = sessionId;
      /* 同会话 force 刷新勿递增序号，避免进行中的 loadMessages 被误判 stale 后留白 */
      if (switchedSession || scrollToTimestamp || !prevSessionId) {
        activeSessionLoadSeq += 1;
      }
      const loadSeq = activeSessionLoadSeq;
      persistSessionId(sessionId);
      syncSessionReadOnly(sessionId);
      applySessionPushResultPref(sessionId);
      if (!markSessionListActive(sessionId)) renderSessionList();
      updateDingtalkOwnerBar();
      const prefetch = opts.messagesPrefetch
        || startSessionMessagesPrefetch(sessionId);
      await loadMessages({
        force: !!(
          opts.force
          || scrollToTimestamp
          || switchedSession
          || sessionMessagesStaleAgainstIndex(sessionId)
        ),
        progressive: scrollToTimestamp ? false : (opts.progressive !== false),
        messagesPrefetch: prefetch,
        loadSeq,
      });
      restoreSessionInputDraft(sessionId);
      void tryReconnectActiveRun(sessionId);
      return true;
    }

    async function tryRestorePersistedSession(id, opts = {}) {
      const sessionId = String(id || '').trim();
      if (!sessionId) return false;
      const cached = getSessionFromCache(sessionId);
      if (cached) {
        if (cached.source === 'dingtalk' || isSessionReadOnly(cached)) return false;
      } else if (!opts.allowMissingCache) {
        return false;
      }
      return activateSession(sessionId, { force: true, ...opts });
    }

    async function restoreOrCreateInitialSession(opts = {}) {
      if (isGuestMode()) {
        currentSessionId = '';
        showEmptyState();
        return;
      }
      if (isWebAgentMobile()) {
        const forcedId = mobileBootstrapForcedSessionId();
        if (forcedId && await tryRestorePersistedSession(forcedId, opts)) return;
        currentSessionId = '';
        clearMessagesDomRendered();
        showEmptyState({ animate: false });
        return;
      }
      const savedId = readPersistedSessionId();
      if (savedId && await tryRestorePersistedSession(savedId, opts)) return;
      const mine = myWritableWebSessions();
      if (mine.length) {
        await activateSession(mine[0].id, { force: true, ...opts });
        return;
      }
      await createSession({ animate: false });
    }

    let sessionsCache = [];
    let sessionsCacheAll = [];
    let sessionsCacheById = new Map();
    let lastSessionListKey = '';
    let sessionsListEtag = '';
    /** 整页刷新后会话列表 lite 拉取未完成（与 is-page-bootstrapping 解耦，避免对话先就绪时侧栏误显空态） */
    let initialSessionsListPending = false;
    /** 首屏 lite 列表请求（侧栏打开时复用，避免重复拉取） */
    let sessionsListBootstrapPromise = null;
    /** 「我的 / 全部」切换中：侧栏先显加载态，避免同步重绘阻塞按钮与筛选态更新 */
    let sessionScopeSwitchPending = false;
    let mobileSessionScopeSwitchSeq = 0;
    let mobileSidebarListWorkSeq = 0;
    let mobileInputFocusSuspend = false;

    window.__WEB_AGENT_SUSPEND_BG__ = function (on) {
      mobileInputFocusSuspend = !!on;
    };

    function showSessionListLoadingUi(opts = {}) {
      if (opts.paintList !== false) paintSessionListScopeSwitchLoading();
      if (isWebAgentMobile() || opts.forceOverlay) {
        setSessionsManualRefreshStatus('loading');
      }
    }

    function hideSessionListLoadingUi() {
      setSessionsManualRefreshStatus('hidden');
    }

    function startSessionsListBootstrap() {
      const promise = loadSessions({ lite: true, deferRender: true }).catch((err) => {
        console.error('loadSessions bootstrap', err);
        sessionsListBootstrapPromise = null;
      });
      sessionsListBootstrapPromise = promise;
      return promise;
    }

    function ensureSessionsListBootstrapPromise(options = {}) {
      if (sessionsListBootstrapPromise) return sessionsListBootstrapPromise;
      if (isWebAgentMobile() && !options.immediate) {
        sessionsListBootstrapPromise = new Promise((resolve) => {
          const kick = () => resolve(startSessionsListBootstrap());
          runMobileIdleTask(kick, 2800);
        });
        return sessionsListBootstrapPromise;
      }
      return startSessionsListBootstrap();
    }

    function scheduleMobileBackgroundDataWarmup() {
      if (!isWebAgentMobile()) return;
      runMobileIdleTask(() => {
        beginInitialSessionsListLoad();
        void ensureSessionsListLoaded(ensureSessionsListBootstrapPromise({ immediate: true }))
          .catch((err) => console.error('ensureSessionsListLoaded mobile deferred', err));
      }, 2800);
    }

    function mobileInputInteracting() {
      const input = document.getElementById('input');
      return inputComposing || (input && document.activeElement === input);
    }

    function scheduleMobileSessionListChunkYield(fn) {
      if (!isWebAgentMobile()) {
        scheduleMessagesRenderYield(fn);
        return;
      }
      const delay = mobileInputFocusSuspend || mobileInputInteracting() ? 96 : 0;
      setTimeout(fn, delay);
    }

    function beginInitialSessionsListLoad() {
      initialSessionsListPending = true;
    }

    function endInitialSessionsListLoad() {
      initialSessionsListPending = false;
    }

    function sessionListEmptyShowsLoading() {
      if (isWebAgentMobile() && !document.body.classList.contains('sidebar-mobile-open')) {
        return false;
      }
      return document.body.classList.contains('is-page-bootstrapping')
        || initialSessionsListPending
        || sessionScopeSwitchPending;
    }

    function paintSessionListScopeSwitchLoading() {
      const list = document.getElementById('session-list');
      if (!list) return;
      list.innerHTML = '<div class="session-filter-empty">加载中…</div>';
      list.scrollTop = 0;
      updateSessionListScrollToTopBtn();
    }

    function waitNextPaint() {
      return new Promise((resolve) => {
        requestAnimationFrame(() => requestAnimationFrame(resolve));
      });
    }
    let loadMessagesAbort = null;
    /** 每次 activateSession 递增；loadMessages / 渲染须与当前序号一致，避免切换会话后旧加载写 DOM。 */
    let activeSessionLoadSeq = 0;

    function sessionMessagesRenderAllowed(sessionId, loadSeq) {
      const sid = String(sessionId || '').trim();
      if (!sid || sid !== currentSessionId) return false;
      if (loadSeq != null && loadSeq !== activeSessionLoadSeq) return false;
      return true;
    }
    const sessionMessagesCache = new Map();
    const sessionMessagesMetaCache = new Map();
    const sessionMessagesEtags = new Map();
    const activeRunEtags = new Map();
    const sessionScrollStateCache = new Map();
    /** @type {Map<string, { text: string, attachments: typeof pendingAttachments }>} */
    const sessionInputDrafts = new Map();
    const SESSION_MESSAGES_CACHE_LIMIT = 24;
    const SESSION_SCROLL_CACHE_LIMIT = 48;
    const SESSION_IDLE_PREFETCH_COUNT = 5;
    /** @type {Map<string, Promise<string|null>>} */
    const sessionMessagesPrefetch = new Map();

    function upsertSessionCacheById(session) {
      const sid = String(session?.id || '').trim();
      if (!sid) return;
      sessionsCacheById.set(sid, session);
    }

    function rebuildSessionsCacheIndex() {
      sessionsCacheById = new Map();
      for (const s of sessionsCacheAll) {
        upsertSessionCacheById(s);
      }
    }

    function getSessionFromCache(sessionId) {
      const sid = String(sessionId || '').trim();
      if (!sid) return null;
      return sessionsCacheById.get(sid)
        || sessionsCache.find((s) => s.id === sid)
        || null;
    }

    function sessionMessagesMtimeFromList(sessionId) {
      return Number(getSessionFromCache(sessionId)?.messages_mtime || 0);
    }

    /** 侧栏 index 与本地消息缓存不一致时需重新拉取（避免切换会话后仍显示旧 tail / 304 命中）。 */
    function sessionMessagesStaleAgainstIndex(sessionId) {
      const sid = String(sessionId || '').trim();
      if (!sid) return true;
      const sess = getSessionFromCache(sid);
      if (!sess) return false;
      const serverCount = Number(sess.message_count || 0);
      const meta = sessionMessagesMeta(sid);
      const cachedTotal = Number(meta?.total || 0);
      if (serverCount > 0 && cachedTotal > 0 && serverCount !== cachedTotal) return true;
      const serverMtime = Number(sess.messages_mtime || 0);
      const cachedMtime = Number(meta?.mtime || 0);
      if (serverMtime > 0 && cachedMtime > 0 && serverMtime !== cachedMtime) return true;
      const cached = sessionMessagesCache.get(sid) || [];
      if (serverCount > 0 && !cached.length) return true;
      return false;
    }

    function startSessionMessagesPrefetch(sessionId) {
      const sid = String(sessionId || '').trim();
      if (!sid) return null;
      if (sessionMessagesCache.get(sid)?.length && !sessionMessagesStaleAgainstIndex(sid)) return null;
      const inflight = sessionMessagesPrefetch.get(sid);
      if (inflight) return inflight;
      const task = (async () => {
        try {
          const msgHeaders = {};
          const cachedEtag = sessionMessagesEtags.get(sid);
          if (cachedEtag) msgHeaders['If-None-Match'] = cachedEtag;
          let data = await api(
            `/api/sessions/${sid}/messages?tail=${MESSAGES_TAIL_DEFAULT}`,
            { cache: 'no-store', headers: msgHeaders },
          );
          if (data?.__notModified) {
            if (data.__etag) sessionMessagesEtags.set(sid, data.__etag);
            if (sessionMessagesCache.get(sid)?.length) return sid;
            data = await api(
              `/api/sessions/${sid}/messages?tail=${MESSAGES_TAIL_DEFAULT}`,
              { cache: 'no-store' },
            );
            if (data?.__notModified || !Array.isArray(data.messages)) return null;
          }
          if (!Array.isArray(data.messages)) return null;
          const pageMeta = {
            total: data.total,
            has_older: data.has_older,
            offset: data.offset,
            messages_mtime: data.messages_mtime || sessionMessagesMtimeFromList(sid),
          };
          rememberSessionMessages(sid, data.messages, pageMeta);
          if (data.__etag) sessionMessagesEtags.set(sid, data.__etag);
          return sid;
        } catch {
          return null;
        } finally {
          sessionMessagesPrefetch.delete(sid);
        }
      })();
      sessionMessagesPrefetch.set(sid, task);
      return task;
    }

    function scheduleIdleSessionMessagesPrefetch() {
      if (isWebAgentMobile()) return;
      if (sessionSearchQuery.trim()) return;
      const ids = sessionsCache
        .slice(0, SESSION_IDLE_PREFETCH_COUNT)
        .map((s) => s?.id)
        .filter((id) => id && id !== currentSessionId);
      if (!ids.length) return;
      const run = () => {
        for (const id of ids) startSessionMessagesPrefetch(id);
      };
      if (typeof requestIdleCallback === 'function') {
        requestIdleCallback(run, { timeout: 2500 });
      } else {
        window.setTimeout(run, 120);
      }
    }

    let idlePrefetchTimer = null;
    function scheduleIdleSessionMessagesPrefetchDebounced() {
      clearTimeout(idlePrefetchTimer);
      idlePrefetchTimer = window.setTimeout(() => {
        idlePrefetchTimer = null;
        scheduleIdleSessionMessagesPrefetch();
      }, 200);
    }

    function rememberSessionMessages(sessionId, messages, meta = null) {
      const sid = String(sessionId || '').trim();
      if (!sid) return;
      sessionMessagesCache.set(sid, messages);
      if (meta && typeof meta === 'object') {
        const mtime = Number(
          meta.messages_mtime ?? meta.mtime ?? sessionMessagesMtimeFromList(sid) ?? 0,
        );
        sessionMessagesMetaCache.set(sid, {
          total: Number(meta.total || messages.length || 0),
          hasOlder: !!meta.has_older,
          offset: Number(meta.offset || 0),
          mtime,
        });
      }
      while (sessionMessagesCache.size > SESSION_MESSAGES_CACHE_LIMIT) {
        const oldest = sessionMessagesCache.keys().next().value;
        sessionMessagesCache.delete(oldest);
        sessionMessagesMetaCache.delete(oldest);
      }
    }

    function sessionMessagesMeta(sessionId) {
      return sessionMessagesMetaCache.get(String(sessionId || '').trim()) || null;
    }

    function countLoadedMessageElements(container) {
      const el = container || getMessagesEl();
      if (!el) return 0;
      let count = 0;
      el.querySelectorAll('.msg').forEach((node) => {
        if (node.classList.contains('streaming')) return;
        if (node.dataset?.timestamp) count += 1;
      });
      return count;
    }

    function sessionHasOlderMessages(sessionId) {
      const sid = String(sessionId || '').trim();
      if (!sid) return false;
      const meta = sessionMessagesMeta(sid);
      if (meta && meta.hasOlder === false) return false;
      const cached = sessionMessagesCache.get(sid);
      const loaded = cached?.length || 0;
      const sess = getSessionFromCache(sid);
      const total = Number(meta?.total || sess?.message_count || 0);
      if (total > 0 && loaded >= total) {
        if (meta) sessionMessagesMetaCache.set(sid, { ...meta, hasOlder: false });
        return false;
      }
      if (meta?.hasOlder) return true;
      if (total > 0 && loaded < total) return true;
      if (sid === currentSessionId) {
        const domLoaded = countLoadedMessageElements();
        if (total > 0 && domLoaded < total) return true;
      }
      return false;
    }

    function getOldestLoadedMessageEl(container) {
      const el = container || getMessagesEl();
      if (!el) return null;
      for (const node of el.querySelectorAll('.msg')) {
        if (node.classList.contains('streaming')) continue;
        if (node.dataset?.timestamp) return node;
      }
      return null;
    }

    function appendUserMessageToSessionCache(sessionId, userMsg) {
      const sid = String(sessionId || '').trim();
      if (!sid || !userMsg) return;
      const cached = sessionMessagesCache.get(sid) || [];
      sessionMessagesCache.set(sid, [...cached, userMsg]);
      const meta = sessionMessagesMeta(sid);
      const sess = getSessionFromCache(sid);
      const prevTotal = Number(meta?.total || sess?.message_count || cached.length);
      const nextTotal = Math.max(prevTotal + 1, cached.length + 1);
      const nextLoaded = cached.length + 1;
      sessionMessagesMetaCache.set(sid, {
        total: nextTotal,
        hasOlder: !!(meta?.hasOlder || nextTotal > nextLoaded),
        offset: Number(meta?.offset ?? Math.max(0, nextTotal - nextLoaded)),
        mtime: Number(meta?.mtime || sessionMessagesMtimeFromList(sid) || 0),
      });
    }

    function bumpSessionMessagesMetaAfterAppend(sessionId, prevCachedLen, nextCachedLen) {
      const sid = String(sessionId || '').trim();
      const meta = sessionMessagesMeta(sid);
      const sess = getSessionFromCache(sid);
      const prevTotal = Number(meta?.total || sess?.message_count || prevCachedLen);
      const nextTotal = Math.max(prevTotal + (nextCachedLen - prevCachedLen), nextCachedLen);
      sessionMessagesMetaCache.set(sid, {
        total: nextTotal,
        hasOlder: !!(meta?.hasOlder || nextTotal > nextCachedLen),
        offset: Number(meta?.offset ?? Math.max(0, nextTotal - nextCachedLen)),
        mtime: Number(meta?.mtime || sessionMessagesMtimeFromList(sid) || 0),
      });
    }

    function appendAssistantMessageToSessionCache(sessionId, assistantMsg) {
      const sid = String(sessionId || '').trim();
      if (!sid || !assistantMsg) return;
      const cached = sessionMessagesCache.get(sid) || [];
      if (!cached.length || cached[cached.length - 1]?.role !== 'user') return;
      sessionMessagesCache.set(sid, [...cached, assistantMsg]);
      bumpSessionMessagesMetaAfterAppend(sid, cached.length, cached.length + 1);
    }

    /** 中断后已发下一条 user 时，把 assistant 插到对应 user 轮次后（勿挂到最新 user）。 */
    function insertAssistantForUserTurnInCache(sessionId, assistantMsg, userHint) {
      const sid = String(sessionId || '').trim();
      if (!sid || !assistantMsg) return false;
      const hint = String(typeof userHint === 'string' ? userHint : userHint?.text || '').trim();
      const cached = sessionMessagesCache.get(sid) || [];
      if (!cached.length) return false;

      let insertIdx = -1;
      if (hint) {
        for (let i = cached.length - 1; i >= 0; i -= 1) {
          if (cached[i].role !== 'user') continue;
          if (String(cached[i].content || '').trim() !== hint) continue;
          if (cached[i + 1]?.role === 'assistant') return false;
          insertIdx = i + 1;
          break;
        }
      }
      if (insertIdx < 0) {
        if (cached[cached.length - 1]?.role !== 'user') return false;
        insertIdx = cached.length;
      }

      const nextCached = [...cached];
      nextCached.splice(insertIdx, 0, assistantMsg);
      sessionMessagesCache.set(sid, nextCached);
      bumpSessionMessagesMetaAfterAppend(sid, cached.length, nextCached.length);
      return true;
    }

    function sessionMessagesFingerprint(msgs, meta = null) {
      if (!Array.isArray(msgs) || !msgs.length) return '0';
      const last = msgs[msgs.length - 1];
      const total = meta?.total ?? sessionMessagesMeta(currentSessionId)?.total ?? msgs.length;
      const hasOlder = meta?.has_older ?? sessionMessagesMeta(currentSessionId)?.hasOlder ?? false;
      return `${total}:${hasOlder ? 1 : 0}:${msgs.length}:${last.timestamp || ''}:${String(last.content || '').length}`;
    }

    let messagesDomSessionId = '';
    let messagesDomFingerprint = '';

    function markMessagesDomRendered(sessionId, msgs, meta = null) {
      const sid = String(sessionId || '').trim();
      if (!sid) return;
      messagesDomSessionId = sid;
      messagesDomFingerprint = sessionMessagesFingerprint(msgs, meta || sessionMessagesMeta(sid));
    }

    function clearMessagesDomRendered() {
      messagesDomSessionId = '';
      messagesDomFingerprint = '';
    }

    function messagesDomMatchesSession(sessionId) {
      const sid = String(sessionId || '').trim();
      return !!sid && sid === messagesDomSessionId;
    }

    function updateMessagesDomFingerprint(sessionId, msgs, meta = null) {
      const sid = String(sessionId || '').trim();
      if (!sid || sid !== messagesDomSessionId) return;
      messagesDomFingerprint = sessionMessagesFingerprint(msgs, meta || sessionMessagesMeta(sid));
    }

    function findOrphanStreamingShell(sessionId) {
      if (currentSessionId !== sessionId) return null;
      const container = getMessagesEl();
      if (!container) return null;
      const assistants = container.querySelectorAll('.msg.assistant');
      for (let i = assistants.length - 1; i >= 0; i -= 1) {
        const el = assistants[i];
        if (isStreamingShellFinalized(el)) continue;
        if (el.classList.contains('streaming') || !el.dataset.timestamp) {
          return el;
        }
      }
      return null;
    }

    /** SSE 已 finalize 的尾部 shell（finishRun 后 activeRuns 已清，仍须合并落盘 assistant）。 */
    function findFinalizedTailShell(sessionId) {
      if (currentSessionId !== sessionId) return null;
      const container = getMessagesEl();
      if (!container) return null;
      const assistants = container.querySelectorAll('.msg.assistant');
      if (!assistants.length) return null;
      const tail = assistants[assistants.length - 1];
      return isStreamingShellFinalized(tail) ? tail : null;
    }

    function resolveTailMergeShell(sessionId) {
      const run = activeRuns.get(sessionId);
      if (run?.shellEl?.isConnected) return run.shellEl;
      const orphan = findOrphanStreamingShell(sessionId);
      if (orphan) return orphan;
      return findFinalizedTailShell(sessionId);
    }

    function tailAssistantBubbleCount(sessionId) {
      const container = getMessagesEl();
      if (!container) return 0;
      const nodes = [...container.querySelectorAll('.msg')];
      let lastUserIdx = -1;
      for (let i = nodes.length - 1; i >= 0; i -= 1) {
        if (nodes[i].classList.contains('user')) {
          lastUserIdx = i;
          break;
        }
      }
      if (lastUserIdx < 0) return 0;
      let count = 0;
      for (let i = lastUserIdx + 1; i < nodes.length; i += 1) {
        if (nodes[i].classList.contains('assistant')) count += 1;
      }
      return count;
    }

    function assistantContentAlreadyInDom(content) {
      const md = String(content || '').trim();
      if (!md) return false;
      const container = getMessagesEl();
      if (!container) return false;
      const assistants = container.querySelectorAll('.msg.assistant');
      for (let i = assistants.length - 1; i >= 0; i -= 1) {
        const bodyEl = assistants[i].querySelector('.msg-body');
        if (getMessageMarkdown(bodyEl) === md) return true;
      }
      return false;
    }

    function mergeAssistantIntoShell(sessionId, shellEl, assistantMsg) {
      if (!shellEl?.isConnected || !assistantMsg) return false;
      finalizeStreamingShell(sessionId, shellEl, assistantMsg.content, {
        timestamp: assistantMsg.timestamp,
        files: assistantMsg.files || [],
        images: assistantMsg.images || [],
      });
      const run = activeRuns.get(sessionId);
      if (run?.shellEl === shellEl) run.shellEl = null;
      return true;
    }

    function messagesDomStreamingOk(sessionId) {
      const sid = String(sessionId || '').trim();
      const run = activeRuns.get(sessionId);
      const container = getMessagesEl();
      if (!container) return false;
      const cachedMsgs = sessionMessagesCache.get(sessionId) || [];
      const orphanShell = findOrphanStreamingShell(sessionId);
      // 落盘已有 assistant 时仍挂着 shell（含 finishRun 后孤儿 shell），须强制重绘去重
      if (orphanShell && messagesHaveAssistantSinceLastUser(cachedMsgs)) {
        if (run?.shellEl === orphanShell) run.shellEl = null;
        return false;
      }
      if (
        messagesHaveAssistantSinceLastUser(cachedMsgs)
        && tailAssistantBubbleCount(sessionId) > 1
      ) {
        return false;
      }
      if (
        deferredRestartAwaiting.has(sid)
        && !messagesHaveAssistantSinceLastUser(cachedMsgs)
      ) {
        return false;
      }
      if (!run) {
        const tail = findFinalizedTailShell(sid);
        if (
          tail
          && !messagesHaveAssistantSinceLastUser(cachedMsgs)
          && !String(getMessageMarkdown(tail.querySelector('.msg-body')) || '').trim()
        ) {
          return false;
        }
        return !orphanShell;
      }
      if (run.shellEl && messagesHaveAssistantSinceLastUser(cachedMsgs)) {
        run.shellEl = null;
        return false;
      }
      if (run.shellEl) return container.contains(run.shellEl);
      return !!document.getElementById('typing-indicator');
    }

    function canSkipMessagesRender(sessionId, msgs, meta = null) {
      const sid = String(sessionId || '').trim();
      if (!sid || sid !== messagesDomSessionId) return false;
      const fp = sessionMessagesFingerprint(msgs, meta || sessionMessagesMeta(sid));
      if (fp !== messagesDomFingerprint) return false;
      const container = getMessagesEl();
      if (!container) return false;
      const isEmpty = !Array.isArray(msgs) || !msgs.length;
      if (isEmpty) return !!container.querySelector('.empty-state');
      if (container.querySelector('.empty-state')) return false;
      if (countLoadedMessageElements(container) !== msgs.length) return false;
      return messagesDomStreamingOk(sid);
    }

    function ensureMessagesDomPaintedFromCache(sessionId, loadSeq, restoreFromBottom, paintOpts = {}) {
      const sid = String(sessionId || '').trim();
      if (!sid || sid !== currentSessionId || messagesDomHasConversation()) return false;
      const live = sessionMessagesCache.get(sid);
      if (!live?.length) return false;
      const seq = loadSeq ?? activeSessionLoadSeq;
      if (!sessionMessagesRenderAllowed(sid, seq)) return false;
      renderLoadedMessages(sid, live, restoreFromBottom, {
        progressive: false,
        ...paintOpts,
        loadSeq: seq,
      });
      return messagesDomHasConversation();
    }

    /** 主区空白但缓存有消息时强制同步重绘（刷新后偶现空白兜底） */
    function repaintEmptyMessagesFromCache(sessionId) {
      const sid = String(sessionId || '').trim();
      if (!sid || sid !== currentSessionId || messagesDomHasConversation()) return false;
      const live = sessionMessagesCache.get(sid);
      if (!live?.length) return false;
      const scrollState = resolveMessagesScrollState(sid);
      renderLoadedMessages(sid, live, scrollState.fromBottom, {
        progressive: false,
        loadSeq: activeSessionLoadSeq,
      });
      return messagesDomHasConversation();
    }

    function syncMessagesViewChrome(sessionId, restoreFromBottom, options = {}) {
      const { touchScroll = true } = options;
      const container = getMessagesEl();
      if (!container) return;
      if (activeRuns.has(sessionId)) {
        const run = activeRuns.get(sessionId);
        if (run?.shellEl && container.contains(run.shellEl)) {
          renderRunStatusEl(run.shellEl.querySelector('.run-status'), run.status || {});
          refreshStreamingShellFromRun(sessionId);
        }
      }
      ensureDeferredRestartPendingInDom(sessionId, sessionMessagesCache.get(sessionId) || []);
      if (touchScroll) {
        if (pendingScrollToTimestamp) {
          /* 搜索跳转由 loadMessages finally 统一分页定位 */
        } else if (restoreFromBottom != null) {
          restoreMessagesScrollFromBottom(restoreFromBottom);
        } else if (messagesPinnedToBottom) {
          scrollMessagesToBottom({ force: !isCurrentSessionStreaming() });
          scheduleScrollMessagesToBottom({ force: !isCurrentSessionStreaming() });
        }
      } else {
        syncMessagesPinnedState(container);
      }
      updateScrollToBottomBtn();
      updateLoadOlderButton(sessionId);
      syncLoadOlderAutoLoad(container);
    }

    function rememberSessionScrollState(sessionId, state) {
      const sid = String(sessionId || '').trim();
      if (!sid) return;
      const pinnedToBottom = !!state?.pinnedToBottom;
      sessionScrollStateCache.set(sid, {
        pinnedToBottom,
        fromBottom: pinnedToBottom ? null : state?.fromBottom,
      });
      while (sessionScrollStateCache.size > SESSION_SCROLL_CACHE_LIMIT) {
        const oldest = sessionScrollStateCache.keys().next().value;
        sessionScrollStateCache.delete(oldest);
      }
    }

    function saveCurrentSessionScrollState() {
      const sessionId = currentSessionId;
      if (!sessionId) return;
      const container = getMessagesEl();
      if (!container || container.querySelector('.empty-state')) {
        rememberSessionScrollState(sessionId, { pinnedToBottom: true, fromBottom: null });
        return;
      }
      const pinnedToBottom = isMessagesNearBottom(container);
      rememberSessionScrollState(sessionId, {
        pinnedToBottom,
        fromBottom: pinnedToBottom ? null : (container.scrollHeight - container.scrollTop),
      });
    }

    function loadSessionScrollState(sessionId) {
      const saved = sessionScrollStateCache.get(String(sessionId || '').trim());
      if (!saved) return { pinnedToBottom: true, fromBottom: null };
      return { pinnedToBottom: !!saved.pinnedToBottom, fromBottom: saved.fromBottom };
    }

    function captureLiveMessagesScrollState() {
      const container = getMessagesEl();
      if (!container || container.querySelector('.empty-state')) {
        return { pinnedToBottom: true, fromBottom: null };
      }
      const pinnedToBottom = isMessagesNearBottom(container);
      return {
        pinnedToBottom,
        fromBottom: pinnedToBottom ? null : (container.scrollHeight - container.scrollTop),
      };
    }

    function resolveMessagesScrollState(sessionId) {
      const sid = String(sessionId || '').trim();
      const container = getMessagesEl();
      const hasLiveDom = sid === currentSessionId
        && messagesDomMatchesSession(sid)
        && container
        && !container.querySelector('.empty-state')
        && container.querySelector('.msg');
      if (hasLiveDom) return captureLiveMessagesScrollState();
      return loadSessionScrollState(sid);
    }
    let sessionSearchQuery = '';
    let sessionSearchTimer = 0;
    let sessionSearchFetchSeq = 0;
    let chatMessageSearchQuery = '';
    let chatMessageSearchTimer = 0;
    let chatMessageSearchMatches = [];
    let chatMessageSearchIndex = -1;
    let chatMessageSearchSeq = 0;
    let pendingScrollToTimestamp = '';
    function trackEvent(event, props = {}) {
      if (window.WebAgentAnalytics) window.WebAgentAnalytics.track(event, props);
    }
    const SESSION_SCOPE_STORAGE_KEY = 'web_agent_session_scope';
    const SESSION_LIST_SCROLL_STORAGE_PREFIX = 'web_agent_session_list_scroll_v1';
    const sessionListScrollByScope = { mine: 0, all: 0 };
    let sessionScopeFilter = 'all';
    let currentSessionReadOnly = false;
    /** @type {Array<{ id: string, name: string, mime: string, previewUrl: string, data_base64: string }>} */
    /** @type {Array<{ id: string, name: string, mime: string, kind: 'image'|'file', previewUrl?: string, data_base64: string }>} */
    let pendingAttachments = [];
    let inputComposing = false;
    let inputComposeResizePending = false;
    let mobileInputChromeRaf = 0;

    function primeMobileInputInteractive() {
      if (!isWebAgentMobile()) return;
      const input = document.getElementById('input');
      if (input) {
        input.readOnly = false;
        input.disabled = false;
        input.classList.remove('readonly-input');
      }
      document.body.classList.remove('is-page-bootstrapping', 'layout-shell-pending');
      document.body.classList.add('input-interactive', 'layout-ready');
      currentSessionId = '';
      showEmptyState();
      finishPageBootstrapShell();
      updateInputState();
    }

    function scheduleMobileInputChromeUpdate() {
      if (!isWebAgentMobile()) {
        syncCurrentSessionInputDraft();
        updateInputState();
        return;
      }
      if (mobileInputChromeRaf) return;
      mobileInputChromeRaf = requestAnimationFrame(() => {
        mobileInputChromeRaf = 0;
        syncCurrentSessionInputDraft();
        updateInputState();
      });
    }
    const MAX_ATTACHMENTS = 5;
    const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
    const MAX_FILE_BYTES = 15 * 1024 * 1024;
    const DEFAULT_ALLOWED_EXTENSIONS = [
      '.png', '.jpg', '.jpeg', '.gif', '.webp',
      '.txt', '.csv', '.md', '.json', '.pdf', '.zip', '.xlsx', '.xls', '.docx', '.html', '.xml',
    ];

    function maxAttachments() {
      return meta.maxAttachmentsPerMessage || meta.maxImagesPerMessage || MAX_ATTACHMENTS;
    }

    function allowedExtensions() {
      return Array.isArray(meta.allowedFileExtensions) && meta.allowedFileExtensions.length
        ? meta.allowedFileExtensions
        : DEFAULT_ALLOWED_EXTENSIONS;
    }

    function fileExtension(name) {
      const idx = String(name || '').lastIndexOf('.');
      if (idx < 0) return '';
      const ext = name.slice(idx).toLowerCase();
      return ext === '.jpeg' ? '.jpg' : ext;
    }

    function isImageFile(file) {
      return (file.type || '').startsWith('image/') || IMAGE_EXTENSIONS.has(fileExtension(file.name));
    }

    const IMAGE_EXTENSIONS = new Set(['.png', '.jpg', '.jpeg', '.gif', '.webp']);

    function isAllowedAttachment(file) {
      const ext = fileExtension(file.name);
      if (allowedExtensions().includes(ext)) return true;
      return isImageFile(file);
    }

    function formatFileSize(bytes) {
      const n = Number(bytes) || 0;
      if (n < 1024) return `${n} B`;
      if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
      return `${(n / (1024 * 1024)).toFixed(1)} MB`;
    }

    function renderMessageImages(images) {
      const list = (images || []).map((src) => String(src || '').trim()).filter(Boolean);
      if (!list.length) return '';
      return `<div class="msg-images">${list.map(src =>
        `<a href="${escapeHtml(src)}" target="_blank" rel="noopener"><img src="${escapeHtml(src)}" alt="附图" loading="lazy" /></a>`
      ).join('')}</div>`;
    }

    function renderMessageFiles(files) {
      if (!files?.length) return '';
      return `<div class="msg-files">${files.map(file => {
        const url = escapeHtml(file.url || '');
        const name = escapeHtml(file.name || '附件');
        const size = file.size ? ` · ${escapeHtml(formatFileSize(file.size))}` : '';
        return `<a class="msg-file-link" href="${url}" data-download-url="${url}" data-download-name="${name}"><span>📎 ${name}${size}</span></a>`;
      }).join('')}</div>`;
    }

    async function downloadMessageFile(url, name) {
      const target = (url || '').trim();
      if (!target) {
        alert('文件链接无效');
        return;
      }
      try {
        const resp = await fetch(API + target, { credentials: 'same-origin' });
        if (!resp.ok) {
          throw new Error(resp.status === 401 ? '请先登录后再下载' : `下载失败（HTTP ${resp.status}）`);
        }
        const blob = await resp.blob();
        const objectUrl = URL.createObjectURL(blob);
        const link = document.createElement('a');
        link.href = objectUrl;
        link.download = name || 'download';
        link.style.display = 'none';
        document.body.appendChild(link);
        link.click();
        link.remove();
        setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
      } catch (err) {
        alert(err?.message || '下载失败');
      }
    }

    function setupMessageFileDownloads() {
      const container = document.getElementById('messages');
      if (!container || container.dataset.fileDownloadBound === '1') return;
      container.dataset.fileDownloadBound = '1';
      container.addEventListener('click', (event) => {
        const link = event.target.closest('.msg-file-link');
        if (!link) return;
        const url = link.getAttribute('data-download-url') || link.getAttribute('href') || '';
        if (!url || url === '#') {
          event.preventDefault();
          alert('文件尚未就绪，请稍候刷新页面后重试');
          return;
        }
        event.preventDefault();
        const name = link.getAttribute('data-download-name') || 'download';
        downloadMessageFile(url, name);
      });
    }

    function toAbsoluteUrl(url) {
      const target = (url || '').trim();
      if (!target || target.startsWith('data:') || target.startsWith('blob:')) return target;
      try {
        return new URL(target, window.location.origin).href;
      } catch {
        return target;
      }
    }

    function blobToDataUrl(blob) {
      return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result || ''));
        reader.onerror = () => reject(reader.error || new Error('read blob failed'));
        reader.readAsDataURL(blob);
      });
    }

    async function inlineMessageImagesAsDataUrl(rootEl) {
      const imgs = [...(rootEl?.querySelectorAll('img') || [])];
      await Promise.all(imgs.map(async (img) => {
        const src = (img.getAttribute('src') || '').trim();
        if (!src || src.startsWith('data:') || src.startsWith('blob:')) return;
        try {
          const resp = await fetch(toAbsoluteUrl(src), { credentials: 'same-origin' });
          if (!resp.ok) return;
          const blob = await resp.blob();
          img.setAttribute('src', await blobToDataUrl(blob));
        } catch { /* keep absolute url fallback */ }
      }));
    }

    function normalizeMessageCopyClone(rootEl) {
      if (!rootEl) return null;
      const clone = rootEl.cloneNode(true);
      clone.querySelectorAll('.run-status, .msg-actions').forEach((node) => node.remove());
      clone.querySelectorAll('img').forEach((img) => {
        const src = img.getAttribute('src');
        if (src && !src.startsWith('data:') && !src.startsWith('blob:')) {
          img.setAttribute('src', toAbsoluteUrl(src));
        }
      });
      clone.querySelectorAll('a[href]').forEach((link) => {
        const href = link.getAttribute('href');
        if (href && !href.startsWith('#') && !href.startsWith('javascript:')) {
          link.setAttribute('href', toAbsoluteUrl(href));
        }
      });
      return clone;
    }

    function elementMatches(el, selector) {
      if (!el || el.nodeType !== Node.ELEMENT_NODE) return false;
      if (typeof el.matches === 'function') return el.matches(selector);
      return false;
    }

    function formatImagePlainLabel(src, alt) {
      const label = (alt || '图片').trim() || '图片';
      const url = toAbsoluteUrl(src || '');
      if (!url) return `[${label}]`;
      if (url.startsWith('data:') || url.startsWith('blob:')) return `[${label}]`;
      return `[${label}] ${url}`;
    }

    function shareIconHtml() {
      return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><circle cx="18" cy="5" r="3"/><circle cx="6" cy="12" r="3"/><circle cx="18" cy="19" r="3"/><line x1="8.59" y1="13.51" x2="15.42" y2="17.49"/><line x1="15.41" y1="6.51" x2="8.59" y2="10.49"/></svg>`;
    }

    function terminalIconHtml() {
      return `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><polyline points="4 17 10 11 4 5"/><line x1="12" y1="19" x2="20" y2="19"/></svg>`;
    }

    function setMessageMarkdown(bodyEl, markdown) {
      if (!bodyEl) return;
      const md = String(markdown || '').trim();
      if (md) bodyEl.dataset.markdown = md;
      else delete bodyEl.dataset.markdown;
    }

    function stripDurationFooter(text) {
      const lines = String(text || '').replace(/\r\n/g, '\n').split('\n');
      while (lines.length && /^\s*⏱\s*本次耗时\s/.test(lines[lines.length - 1])) {
        lines.pop();
      }
      while (lines.length && !lines[lines.length - 1].trim()) {
        lines.pop();
      }
      return lines.join('\n').trim();
    }

    function getMessageMarkdown(bodyEl) {
      if (!bodyEl) return '';
      const stored = (bodyEl.dataset.markdown || '').trim();
      if (stored) return stripDurationFooter(stored);
      return stripDurationFooter(extractMessagePlainText(bodyEl));
    }

    function findPrecedingUserQuestion(assistantMsgEl) {
      if (!assistantMsgEl) return '';
      let prev = assistantMsgEl.previousElementSibling;
      while (prev) {
        if (prev.classList.contains('user')) {
          const bodyEl = prev.querySelector('.msg-body');
          return bodyEl ? extractMessagePlainText(bodyEl) : '';
        }
        if (prev.classList.contains('assistant')) break;
        prev = prev.previousElementSibling;
      }
      return '';
    }

    function setAssistantMessageBody(msgEl, markdown, opts = {}) {
      const bodyEl = msgEl?.querySelector('.msg-body');
      if (!bodyEl) return;
      const md = String(markdown || '').trim();
      const attachmentHtml = `${renderMessageImages(opts.images || [])}${renderMessageFiles(opts.files || [])}`;
      bodyEl.innerHTML = `${attachmentHtml}${renderMarkdown(md || '（无回复）')}`;
      setMessageMarkdown(bodyEl, md);
    }

    function extractMessagePlainText(bodyEl) {
      if (!bodyEl) return '';
      const parts = [];
      const pushUnique = (value) => {
        const text = String(value || '').trim();
        if (!text || parts[parts.length - 1] === text) return;
        parts.push(text);
      };
      const walk = (node) => {
        if (node.nodeType === Node.TEXT_NODE) {
          const text = node.textContent.replace(/\u00a0/g, ' ').replace(/\s+/g, ' ').trim();
          if (text) pushUnique(text);
          return;
        }
        if (node.nodeType !== Node.ELEMENT_NODE) return;
        const el = node;
        if (elementMatches(el, '.run-status')) return;
        if (elementMatches(el, 'img')) {
          pushUnique(formatImagePlainLabel(el.getAttribute('src') || '', el.getAttribute('alt') || '图片'));
          return;
        }
        if (elementMatches(el, '.msg-file-link')) {
          const name = (el.textContent || '').replace(/^📎\s*/, '').trim() || '附件';
          const url = toAbsoluteUrl(el.getAttribute('href') || el.getAttribute('data-download-url') || '');
          pushUnique(`[附件] ${name}${url && url !== '#' ? ` ${url}` : ''}`);
          return;
        }
        if (elementMatches(el, '.msg-images a[href]') && !el.querySelector('img')) {
          const href = toAbsoluteUrl(el.getAttribute('href') || '');
          if (href && href !== '#') pushUnique(formatImagePlainLabel(href, '附图'));
          return;
        }
        if (elementMatches(el, '.msg-images, .msg-files')) {
          el.querySelectorAll('img, .msg-file-link, a[href]').forEach((child) => walk(child));
          return;
        }
        [...el.childNodes].forEach((child) => walk(child));
      };
      [...bodyEl.childNodes].forEach((child) => walk(child));
      let result = parts.join('\n\n').trim();
      if (!result) {
        bodyEl.querySelectorAll('img').forEach((img) => {
          pushUnique(formatImagePlainLabel(img.getAttribute('src') || '', img.getAttribute('alt') || '图片'));
        });
        bodyEl.querySelectorAll('.msg-images a[href]').forEach((link) => {
          const href = toAbsoluteUrl(link.getAttribute('href') || '');
          if (href && href !== '#') pushUnique(formatImagePlainLabel(href, '附图'));
        });
        bodyEl.querySelectorAll('.msg-file-link').forEach((link) => walk(link));
        result = parts.join('\n\n').trim();
      }
      if (!result) {
        result = (bodyEl.innerText || bodyEl.textContent || '').replace(/\s+/g, ' ').trim();
      }
      return result;
    }

    function messageBodyHasCopyContent(bodyEl) {
      if (!bodyEl) return false;
      if (extractMessagePlainText(bodyEl)) return true;
      if (bodyEl.querySelector('img, .msg-file-link, .markdown-body, pre, code, table, ul, ol, blockquote')) {
        return true;
      }
      return !!(bodyEl.textContent || '').trim();
    }

    function buildMessageCopyHtml(bodyEl) {
      const clone = normalizeMessageCopyClone(bodyEl);
      if (!clone) return '';
      return `<div>${clone.innerHTML}</div>`;
    }

    function copyPlainTextSync(plainText) {
      const text = String(plainText || '').trim();
      if (!text) return false;
      const helper = document.createElement('textarea');
      helper.value = text;
      helper.setAttribute('readonly', '');
      helper.style.position = 'fixed';
      helper.style.left = '-9999px';
      helper.style.top = '0';
      helper.style.opacity = '0';
      document.body.appendChild(helper);
      helper.focus();
      helper.select();
      let ok = false;
      try {
        ok = document.execCommand('copy');
      } catch { /* fallback below */ }
      helper.remove();
      return ok;
    }

    async function writeMessageClipboard(plainText, html) {
      const text = String(plainText || '').trim();
      if (!text) return false;
      const htmlPayload = html || text.replace(/\n/g, '<br>');
      if (navigator.clipboard?.writeText) {
        try {
          await navigator.clipboard.writeText(text);
          if (html && navigator.clipboard?.write && window.ClipboardItem) {
            try {
              await navigator.clipboard.write([
                new ClipboardItem({
                  'text/plain': new Blob([text], { type: 'text/plain' }),
                  'text/html': new Blob([htmlPayload], { type: 'text/html' }),
                }),
              ]);
            } catch { /* plain text already copied */ }
          }
          return true;
        } catch { /* fallback below */ }
      }
      if (html && navigator.clipboard?.write && window.ClipboardItem) {
        try {
          await navigator.clipboard.write([
            new ClipboardItem({
              'text/plain': new Blob([text], { type: 'text/plain' }),
              'text/html': new Blob([htmlPayload], { type: 'text/html' }),
            }),
          ]);
          return true;
        } catch { /* fallback below */ }
      }
      return copyPlainTextSync(text);
    }

    function upgradeMessageClipboardHtml(plainText, bodyEl) {
      const clone = normalizeMessageCopyClone(bodyEl);
      if (!clone) return;
      inlineMessageImagesAsDataUrl(clone).then(async () => {
        const html = `<div>${clone.innerHTML}</div>`;
        if (!navigator.clipboard?.write || !window.ClipboardItem) return;
        try {
          await navigator.clipboard.write([
            new ClipboardItem({
              'text/plain': new Blob([plainText], { type: 'text/plain' }),
              'text/html': new Blob([html], { type: 'text/html' }),
            }),
          ]);
        } catch { /* plain text already copied */ }
      }).catch(() => {});
    }

    async function copyMessageContent(msgEl, bodyOverride = null, plainOverride = '') {
      const bodyEl = bodyOverride || msgEl?.querySelector('.msg-body');
      if (!bodyEl) return false;
      if (!messageBodyHasCopyContent(bodyEl)) return false;
      let plainText = String(plainOverride || '').trim();
      if (!plainText) plainText = extractMessagePlainText(bodyEl);
      if (!plainText) {
        plainText = (bodyEl.innerText || bodyEl.textContent || '').replace(/\s+/g, ' ').trim();
      }
      if (!plainText) return false;
      const clone = normalizeMessageCopyClone(bodyEl);
      const htmlQuick = clone ? `<div>${clone.innerHTML}</div>` : buildMessageCopyHtml(bodyEl);
      // 必须在用户手势有效期内先写入剪贴板；图片转 data URL 的 fetch 会耗掉手势。
      let copied = copyPlainTextSync(plainText);
      if (!copied) copied = await writeMessageClipboard(plainText, htmlQuick);
      if (!copied) return false;
      upgradeMessageClipboardHtml(plainText, bodyEl);
      return true;
    }

    function unwrapAssistantMessageBody(msgEl) {
      const wrap = msgEl?.querySelector(':scope > .msg-body-wrap');
      if (!wrap) return;
      const bodyEl = wrap.querySelector(':scope > .msg-body');
      if (bodyEl) wrap.parentElement.insertBefore(bodyEl, wrap);
      wrap.remove();
    }

    function ensureAssistantMessageBodyWrap(bodyEl) {
      if (!bodyEl) return null;
      const parent = bodyEl.parentElement;
      if (parent?.classList.contains('msg-body-wrap')) return parent;
      const wrap = document.createElement('div');
      wrap.className = 'msg-body-wrap';
      parent.insertBefore(wrap, bodyEl);
      wrap.appendChild(bodyEl);
      return wrap;
    }

    function removeAssistantShareButton(msgEl) {
      msgEl?.querySelector('.msg-actions')?.remove();
      const wrap = msgEl?.querySelector(':scope > .msg-body-wrap');
      if (wrap?.querySelector('.msg-terminal-external')) return;
      unwrapAssistantMessageBody(msgEl);
    }

    function removeAssistantTerminalButton(msgEl) {
      const slot = msgEl?.querySelector('.msg-terminal-external');
      if (slot) slot.hidden = true;
    }

    function ensureAssistantTerminalButton(msgEl) {
      if (!msgEl?.classList?.contains('assistant')) return null;
      const bodyEl = msgEl.querySelector('.msg-body');
      if (!bodyEl) return null;
      const wrap = ensureAssistantMessageBodyWrap(bodyEl);
      let slot = wrap.querySelector(':scope > .msg-terminal-external');
      if (!slot) {
        slot = document.createElement('div');
        slot.className = 'msg-terminal-external';
        slot.hidden = true;
        const btn = document.createElement('button');
        btn.type = 'button';
        btn.className = 'msg-terminal-btn';
        btn.setAttribute('data-terminal-btn', '');
        btn.title = '终端输出';
        btn.setAttribute('aria-label', '终端输出');
        btn.innerHTML = terminalIconHtml();
        slot.appendChild(btn);
        const actions = wrap.querySelector('.msg-actions');
        if (actions) wrap.insertBefore(slot, actions);
        else wrap.appendChild(slot);
      }
      return slot;
    }

    function purgeInlineTerminalButtons(bodyEl) {
      if (!bodyEl) return;
      bodyEl.querySelector('.msg-result-terminal-row')?.remove();
      bodyEl.querySelectorAll('[data-terminal-btn]').forEach((btn) => btn.remove());
    }

    function shouldShowMsgTerminalButton(msgEl, sessionId = '') {
      if (!msgEl?.classList?.contains('assistant')) return false;
      const streaming = msgEl.classList.contains('streaming') && !isStreamingShellFinalized(msgEl);
      const sid = String(sessionId || shellSessionId(msgEl) || '').trim();
      const run = sid ? activeRuns.get(sid) : null;
      if (run?.runId && run.shellEl === msgEl && !msgEl.dataset.runId) {
        msgEl.dataset.runId = String(run.runId);
      }
      if (streaming && run?.shellEl === msgEl) return true;
      const runId = String(msgEl.dataset.runId || run?.runId || '').trim();
      const inlineText = resolveMsgTerminalText(msgEl, sessionId);
      return Boolean(runId || inlineText.trim());
    }

    function ensureAssistantShareButton(msgEl) {
      if (!msgEl || !msgEl.classList.contains('assistant')) return;
      if (msgEl.classList.contains('streaming')) return;
      const bodyEl = msgEl.querySelector('.msg-body');
      if (!bodyEl || !messageBodyHasCopyContent(bodyEl)) {
        removeAssistantShareButton(msgEl);
        return;
      }
      if (msgEl.querySelector('.msg-share-btn')) return;
      const wrap = ensureAssistantMessageBodyWrap(bodyEl);
      const actions = document.createElement('div');
      actions.className = 'msg-actions';
      const btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'msg-share-btn';
      btn.title = '分享到钉钉';
      btn.setAttribute('aria-label', '分享到钉钉');
      btn.innerHTML = shareIconHtml();
      actions.appendChild(btn);
      wrap.appendChild(actions);
    }

    function setupMessageCopyHandler() {
      const container = getMessagesEl();
      if (!container || container.dataset.msgCopyBound === '1') return;
      container.dataset.msgCopyBound = '1';
      container.addEventListener('copy', (event) => {
        const bodyEl = event.target.closest('.msg-body');
        if (!bodyEl) return;
        const selection = window.getSelection();
        if (!selection || selection.isCollapsed) return;
        const anchor = selection.anchorNode;
        const focus = selection.focusNode;
        if (!bodyEl.contains(anchor) && !bodyEl.contains(focus)) return;
        const range = selection.getRangeAt(0);
        const fragment = range.cloneContents();
        const holder = document.createElement('div');
        holder.appendChild(fragment);
        const plainText = extractMessagePlainText(holder) || selection.toString().trim();
        if (!plainText) return;
        const clone = normalizeMessageCopyClone(holder);
        const html = clone ? `<div>${clone.innerHTML}</div>` : plainText.replace(/\n/g, '<br>');
        if (event.clipboardData) {
          event.preventDefault();
          event.clipboardData.setData('text/plain', plainText);
          event.clipboardData.setData('text/html', html);
        }
      });
    }

    function setupMessageTerminalActions() {
      const container = getMessagesEl();
      if (!container || container.dataset.msgTerminalBound === '1') return;
      container.dataset.msgTerminalBound = '1';
      container.addEventListener('click', (event) => {
        const btn = event.target.closest('[data-terminal-btn]');
        if (!btn) return;
        event.preventDefault();
        event.stopPropagation();
        const msgEl = btn.closest('.msg.assistant');
        if (!msgEl) return;
        const sid = String(currentSessionId || '').trim();
        openTerminalModalForMessage(msgEl, sid);
      });
    }

    function setupMessageShareActions() {
      const container = getMessagesEl();
      if (!container || container.dataset.msgShareBound === '1') return;
      container.dataset.msgShareBound = '1';
      container.addEventListener('click', async (event) => {
        const btn = event.target.closest('.msg-share-btn');
        if (!btn) return;
        event.preventDefault();
        event.stopPropagation();
        const msgEl = btn.closest('.msg.assistant');
        if (!msgEl) return;
        const bodyEl = msgEl.querySelector('.msg-body');
        const markdown = bodyEl ? getMessageMarkdown(bodyEl) : '';
        if (!markdown) {
          alert('暂无内容可分享');
          return;
        }
        if (isGuestMode()) {
          alert('请先登录后再分享消息');
          return;
        }
        const question = findPrecedingUserQuestion(msgEl);
        await openForwardModal(markdown, 'assistant', question);
      });
    }

    function renderPendingAttachments() {
      const container = document.getElementById('pending-images');
      if (!container) return;
      container.innerHTML = pendingAttachments.map(item => {
        if (item.kind === 'image') {
          return `
        <div class="pending-image" data-id="${escapeHtml(item.id)}">
          <img src="${item.previewUrl}" alt="${escapeHtml(item.name)}" />
          <button type="button" title="移除" aria-label="移除附件">×</button>
        </div>`;
        }
        return `
        <div class="pending-file" data-id="${escapeHtml(item.id)}">
          <span>📎</span>
          <span class="file-name" title="${escapeHtml(item.name)}">${escapeHtml(item.name)}</span>
          <button type="button" title="移除" aria-label="移除附件">×</button>
        </div>`;
      }).join('');
      container.querySelectorAll('.pending-image button, .pending-file button').forEach(btn => {
        btn.addEventListener('click', () => {
          const wrap = btn.closest('[data-id]');
          const id = wrap?.getAttribute('data-id');
          if (!id) return;
          pendingAttachments = pendingAttachments.filter(item => item.id !== id);
          renderPendingAttachments();
          syncCurrentSessionInputDraft();
          updateInputState();
        });
      });
    }

    async function readFileAsBase64(file) {
      const dataUrl = await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result || ''));
        reader.onerror = () => reject(new Error('读取文件失败'));
        reader.readAsDataURL(file);
      });
      const comma = dataUrl.indexOf(',');
      return comma >= 0 ? dataUrl.slice(comma + 1) : dataUrl;
    }

    async function addPendingAttachmentFiles(fileList) {
      if (currentSessionReadOnly) return;
      const files = Array.from(fileList || []);
      for (const file of files) {
        if (pendingAttachments.length >= maxAttachments()) {
          alert(`最多上传 ${maxAttachments()} 个附件`);
          break;
        }
        if (!isAllowedAttachment(file)) {
          showUnsupportedAttachmentToast([file]);
          continue;
        }
        const isImage = isImageFile(file);
        const limit = isImage ? MAX_IMAGE_BYTES : (meta.maxFileBytes || MAX_FILE_BYTES);
        if (file.size > limit) {
          alert(`文件过大（>${limit / (1024 * 1024)}MB）：${file.name}`);
          continue;
        }
        const data_base64 = await readFileAsBase64(file);
        const dataUrl = isImage ? `data:${file.type || 'image/png'};base64,${data_base64}` : '';
        pendingAttachments.push({
          id: `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
          name: file.name,
          mime: file.type || (isImage ? 'image/png' : 'application/octet-stream'),
          kind: isImage ? 'image' : 'file',
          previewUrl: dataUrl,
          data_base64,
        });
      }
      renderPendingAttachments();
      syncCurrentSessionInputDraft();
      updateInputState();
    }

    function clearPendingAttachments() {
      pendingAttachments = [];
      renderPendingAttachments();
    }

    const DEFAULT_PLACEHOLDER = '输入问题；可粘贴/拖拽图片或文件';
    const MOBILE_DEFAULT_PLACEHOLDER = '输入问题';

    function defaultInputPlaceholder() {
      return document.documentElement.classList.contains('web-agent-mobile')
        ? MOBILE_DEFAULT_PLACEHOLDER
        : DEFAULT_PLACEHOLDER;
    }

    const RETRY_PLACEHOLDER = '执行失败，原消息已回填，请修改后重试…';
    const RETRY_HINT_MARKDOWN = '\n\n💡 原消息已回填到输入框，请检查后重试。';
    const GUEST_PLACEHOLDER = '登录后即可发送消息…';
    let retryHintActive = false;
    const DINGTALK_READONLY_PLACEHOLDER = '此会话来自钉钉同步，仅供查看；继续对话请点「新对话」';
    const WEB_READONLY_PLACEHOLDER = '此会话归属他人，仅供查看；请点「新对话」继续自己的任务';
    const OPEN_API_READONLY_PLACEHOLDER = '此为 Open API 会话，请在 API 中提问；Web 端仅供查看';

    function canAttachFiles() {
      return !currentSessionReadOnly;
    }

    function canOpenAttachPicker() {
      return canAttachFiles() && !isCurrentSessionStreaming();
    }

    function collectAllFilesFromDataTransfer(dataTransfer) {
      if (!dataTransfer) return [];
      const files = [];
      if (dataTransfer.items?.length) {
        for (const item of dataTransfer.items) {
          if (item.kind === 'file') {
            const file = item.getAsFile();
            if (file) files.push(file);
          }
        }
      }
      if (!files.length && dataTransfer.files?.length) {
        for (const file of dataTransfer.files) files.push(file);
      }
      return files;
    }

    function attachmentRejectToastMessage(files) {
      const list = Array.from(files || []).filter(Boolean);
      if (!list.length) return '不支持的文件类型';
      const shown = list.slice(0, 3).map(f => f.name || '未命名');
      const suffix = list.length > 3 ? ` 等 ${list.length} 个` : '';
      const exts = allowedExtensions().map(e => e.replace(/^\./, '')).join('、');
      return `不支持的文件类型：${shown.join('、')}${suffix}（支持：${exts}）`;
    }

    function showUnsupportedAttachmentToast(files) {
      if (!files?.length) return;
      showWebToast(attachmentRejectToastMessage(files), { error: true, durationMs: 4200 });
    }

    function ingestAttachmentFilesFromDataTransfer(dataTransfer) {
      const all = collectAllFilesFromDataTransfer(dataTransfer);
      if (!all.length) return;
      const allowed = [];
      const rejected = [];
      for (const file of all) {
        if (isAllowedAttachment(file)) allowed.push(file);
        else rejected.push(file);
      }
      if (rejected.length) showUnsupportedAttachmentToast(rejected);
      if (allowed.length) addPendingAttachmentFiles(allowed);
    }

    function setupInputAttachmentHandlers() {
      const inputWrap = document.getElementById('input-wrap');
      const textarea = document.getElementById('input');
      const fileInput = document.getElementById('file-input');
      const attachBtn = document.getElementById('btn-attach');
      if (!inputWrap || !textarea) return;

      attachBtn?.addEventListener('click', () => {
        if (!canOpenAttachPicker()) return;
        fileInput?.click();
      });
      fileInput?.addEventListener('change', () => {
        if (!fileInput.files?.length) return;
        addPendingAttachmentFiles(fileInput.files);
        fileInput.value = '';
      });

      textarea.addEventListener('paste', (e) => {
        if (!canAttachFiles()) return;
        const all = collectAllFilesFromDataTransfer(e.clipboardData);
        if (!all.length) return;
        e.preventDefault();
        ingestAttachmentFilesFromDataTransfer(e.clipboardData);
      });

      function clearInputDragOverState() {
        inputWrap.classList.remove('drag-over', 'drag-over-reject');
      }

      function refreshInputDragOverState(dataTransfer) {
        const all = collectAllFilesFromDataTransfer(dataTransfer);
        const hasAllowed = all.some(isAllowedAttachment);
        const hasRejected = all.some(f => !isAllowedAttachment(f));
        inputWrap.classList.toggle('drag-over', hasAllowed);
        inputWrap.classList.toggle('drag-over-reject', !!all.length && !hasAllowed && hasRejected);
        return { hasAllowed, hasRejected, total: all.length };
      }

      inputWrap.addEventListener('dragenter', (e) => {
        if (!canAttachFiles()) return;
        if (![...(e.dataTransfer?.types || [])].includes('Files')) return;
        e.preventDefault();
        refreshInputDragOverState(e.dataTransfer);
      });

      inputWrap.addEventListener('dragover', (e) => {
        if (!canAttachFiles()) return;
        if (![...(e.dataTransfer?.types || [])].includes('Files')) return;
        e.preventDefault();
        const { hasAllowed, hasRejected, total } = refreshInputDragOverState(e.dataTransfer);
        if (e.dataTransfer) {
          e.dataTransfer.dropEffect = total && !hasAllowed && hasRejected ? 'none' : 'copy';
        }
      });

      inputWrap.addEventListener('dragleave', (e) => {
        if (!inputWrap.contains(e.relatedTarget)) {
          clearInputDragOverState();
        }
      });

      inputWrap.addEventListener('drop', (e) => {
        e.preventDefault();
        clearInputDragOverState();
        if (!canAttachFiles()) return;
        ingestAttachmentFilesFromDataTransfer(e.dataTransfer);
      });
    }

    function formatMessageTime(iso) {
      if (!iso) return '';
      try {
        const dt = new Date(iso);
        if (Number.isNaN(dt.getTime())) return '';
        const pad = (n) => String(n).padStart(2, '0');
        const hhmm = `${pad(dt.getHours())}:${pad(dt.getMinutes())}`;
        const now = new Date();
        if (dt.toDateString() === now.toDateString()) return hhmm;
        const md = `${pad(dt.getMonth() + 1)}-${pad(dt.getDate())}`;
        if (dt.getFullYear() === now.getFullYear()) return `${md} ${hhmm}`;
        return `${dt.getFullYear()}-${md} ${hhmm}`;
      } catch {
        return '';
      }
    }

    const userAvatarCache = new Map();
    const userAvatarNoPhoto = new Set();
    const userAvatarInflight = new Set();

    function wrapAvatarGlyph(char) {
      const glyph = String(char || '?').trim() || '?';
      return `<span class="name-avatar-glyph">${escapeHtml(glyph)}</span>`;
    }

    function avatarInitialFromLabel(label) {
      return String(label || '?').trim().slice(0, 1).toUpperCase() || '?';
    }

    function avatarLabelForElement(el) {
      const stored = (el?.dataset?.avatarLabel || '').trim();
      if (stored) return stored;
      const owner = el?.closest('.session-owner-line')?.querySelector('.session-owner');
      if (owner?.textContent) return owner.textContent.trim();
      const msgLabel = el?.closest('.msg-label-row')?.querySelector('.msg-label');
      if (msgLabel?.textContent) return msgLabel.textContent.trim();
      const collabName = el?.closest('.collaborators-item-name-row')?.querySelector('.collaborators-item-name');
      if (collabName?.textContent) return collabName.textContent.trim();
      const adminName = el?.closest('.admin-list-item-name-wrap')?.querySelector('.admin-list-item-name');
      if (adminName?.textContent) return adminName.textContent.trim();
      const menuName = document.getElementById('user-menu-name');
      if (el?.closest('#user-menu') && menuName?.textContent) return menuName.textContent.trim();
      return '';
    }

    function applyAvatarFallback(el, label) {
      if (!el || el.classList?.contains('name-avatar-fallback')) return;
      const sid = (el.dataset?.staffId || '').trim();
      const resolvedLabel = String(label || avatarLabelForElement(el) || '').trim();
      const fallback = document.createElement('span');
      fallback.className = 'name-avatar name-avatar-fallback';
      if (sid) {
        fallback.dataset.staffId = sid;
        userAvatarNoPhoto.add(sid);
        userAvatarCache.delete(sid);
      }
      if (resolvedLabel) fallback.dataset.avatarLabel = resolvedLabel;
      fallback.setAttribute('aria-hidden', 'true');
      fallback.innerHTML = wrapAvatarGlyph(avatarInitialFromLabel(resolvedLabel));
      el.replaceWith(fallback);
    }

    function isAvatarImageBlank(img) {
      try {
        const w = img.naturalWidth;
        const h = img.naturalHeight;
        if (!w || !h) return true;
        const canvas = document.createElement('canvas');
        canvas.width = w;
        canvas.height = h;
        const ctx = canvas.getContext('2d', { willReadFrequently: true });
        if (!ctx) return false;
        ctx.drawImage(img, 0, 0, w, h);
        const { data } = ctx.getImageData(0, 0, w, h);
        const total = w * h;
        let opaque = 0;
        for (let i = 3; i < data.length; i += 4) {
          if (data[i] > 128) opaque += 1;
        }
        return opaque / total < 0.15;
      } catch (_) {
        return false;
      }
    }

    function bindAvatarImage(img, label) {
      if (!img || img.dataset.avatarBound === '1') return;
      const resolvedLabel = String(label || img.dataset.avatarLabel || avatarLabelForElement(img) || '').trim();
      if (resolvedLabel) img.dataset.avatarLabel = resolvedLabel;
      img.dataset.avatarBound = '1';
      const onAvatarImageFailed = () => {
        applyAvatarFallback(img, img.dataset.avatarLabel || avatarLabelForElement(img));
      };
      const onAvatarImageReady = () => {
        if (isAvatarImageBlank(img)) onAvatarImageFailed();
      };
      img.addEventListener('error', onAvatarImageFailed, { once: true });
      img.addEventListener('load', onAvatarImageReady, { once: true });
      // 404 / 钉钉默认透明占位图在绑定前已加载完成时不会再触发 error
      if (img.complete) {
        if (!img.naturalWidth) onAvatarImageFailed();
        else onAvatarImageReady();
      }
    }

    function bindAvatarImages(root) {
      if (!root) return;
      root.querySelectorAll('img.name-avatar, .user-menu-avatar.has-photo img').forEach((img) => {
        bindAvatarImage(img);
      });
    }

    function buildNameAvatarHtml({ staffId = '', label = '', role = 'user', avatarUrl = '', eager = false } = {}) {
      if (role === 'assistant') {
        const logo = (window.WebAgentLogo && WebAgentLogo.svg)
          ? WebAgentLogo.svg({ glowId: `wa-msg-logo-${Math.random().toString(36).slice(2, 8)}` })
          : 'A';
        return `<span class="name-avatar name-avatar-agent" aria-hidden="true">${logo}</span>`;
      }
      const sid = String(staffId || '').trim();
      const initial = avatarInitialFromLabel(label);
      const labelAttr = label ? ` data-avatar-label="${escapeHtml(label)}"` : '';
      let url = String(avatarUrl || '').trim() || (sid ? (userAvatarCache.get(sid) || '') : '');
      if (sid && userAvatarNoPhoto.has(sid)) url = '';
      if (url && sid) userAvatarCache.set(sid, url);
      const loadingAttr = eager ? 'eager' : 'lazy';
      if (url) {
        return `<img class="name-avatar" src="${escapeHtml(url)}" alt="" loading="${loadingAttr}" referrerpolicy="no-referrer" data-staff-id="${escapeHtml(sid)}"${labelAttr} />`;
      }
      if (sid) {
        return `<span class="name-avatar name-avatar-fallback" data-staff-id="${escapeHtml(sid)}"${labelAttr} aria-hidden="true">${wrapAvatarGlyph(initial)}</span>`;
      }
      return `<span class="name-avatar name-avatar-fallback"${labelAttr} aria-hidden="true">${wrapAvatarGlyph(initial)}</span>`;
    }

    const AVATAR_HYDRATE_SELECTOR = [
      'img.name-avatar[data-staff-id]',
      '.name-avatar-fallback[data-staff-id]',
      '.user-menu-avatar img[data-staff-id]',
    ].join(', ');

    async function hydrateAvatars(root) {
      if (!root) return;
      bindAvatarImages(root);
      const ids = [...new Set(
        [...root.querySelectorAll(AVATAR_HYDRATE_SELECTOR)]
          .map((el) => (el.dataset.staffId || '').trim())
          .filter(Boolean),
      )];
      const missing = ids.filter(
        (id) => !userAvatarCache.has(id)
          && !userAvatarNoPhoto.has(id)
          && !userAvatarInflight.has(id),
      );
      if (missing.length) {
        missing.forEach((id) => userAvatarInflight.add(id));
        try {
          const resp = await fetch(
            `${API}/api/dingtalk/user-avatars?ids=${encodeURIComponent(missing.join(','))}`,
            { credentials: 'same-origin' },
          );
          if (resp.ok) {
            const data = await resp.json();
            Object.entries(data.avatars || {}).forEach(([id, url]) => {
              const resolved = String(url || '').trim();
              if (resolved) userAvatarCache.set(id, resolved);
              else userAvatarNoPhoto.add(id);
            });
            missing.forEach((id) => {
              if (!userAvatarCache.has(id)) userAvatarNoPhoto.add(id);
            });
          }
        } catch (_) {
          /* 网络失败时保留现有 fallback / 稍后重试 */
        } finally {
          missing.forEach((id) => userAvatarInflight.delete(id));
        }
      }
      root.querySelectorAll('img.name-avatar[data-staff-id]').forEach((el) => {
        const id = (el.dataset.staffId || '').trim();
        if (id && userAvatarNoPhoto.has(id)) {
          applyAvatarFallback(el, el.dataset.avatarLabel || avatarLabelForElement(el));
        }
      });
      root.querySelectorAll(AVATAR_HYDRATE_SELECTOR).forEach((el) => {
        const id = (el.dataset.staffId || '').trim();
        if (id && userAvatarNoPhoto.has(id)) {
          if (el.tagName === 'IMG') {
            applyAvatarFallback(el, el.dataset.avatarLabel || avatarLabelForElement(el));
          }
          return;
        }
        const url = userAvatarCache.get(id);
        if (!url) return;
        if (el.tagName === 'IMG') {
          if (el.getAttribute('src') !== url) el.setAttribute('src', url);
          bindAvatarImage(el, el.dataset.avatarLabel || avatarLabelForElement(el));
          return;
        }
        const img = document.createElement('img');
        img.className = 'name-avatar';
        img.src = url;
        img.alt = '';
        img.loading = el.closest('.session-meta') ? 'eager' : 'lazy';
        img.referrerPolicy = 'no-referrer';
        img.dataset.staffId = id;
        if (el.dataset.avatarLabel) img.dataset.avatarLabel = el.dataset.avatarLabel;
        bindAvatarImage(img, el.dataset.avatarLabel || avatarLabelForElement(el));
        el.replaceWith(img);
      });
      bindAvatarImages(root);
    }

    function buildMsgLabelHtml(label, timestamp, opts = {}) {
      const timeText = formatMessageTime(timestamp);
      const timeHtml = timeText
        ? `<span class="msg-time">${escapeHtml(timeText)}</span>`
        : '';
      const avatarHtml = buildNameAvatarHtml({
        staffId: opts.staffId,
        label,
        role: opts.role || 'user',
        avatarUrl: opts.avatarUrl,
      });
      return `<div class="msg-label-row">${avatarHtml}<div class="msg-label">${escapeHtml(label)}</div>${timeHtml}</div>`;
    }

    function withLinksOpenInNewTab(html) {
      return (html || '').replace(/<a\b([^>]*?)>/gi, (match, attrs) => {
        if (/\btarget\s*=/.test(attrs)) return match;
        return `<a${attrs} target="_blank" rel="noopener noreferrer">`;
      });
    }

    function normalizeStreamingMarkdown(text) {
      let s = String(text || '').trim()
        .replace(/^🤔\s*\*\*思考中\*\*/gm, '### 思考中')
        .replace(/^\*\*执行工作\*\*\s*$/gm, '### 执行工作');
      s = s.replace(/^(### [^\n]+)\n(?!\n)/gm, '$1\n\n');
      return s;
    }

    function normalizeToolLine(line) {
      return String(line || '')
        .replace(/^>\s*/, '')
        .replace(/^[-*·]\s*/, '')
        .replace(/^[🔧✅]\s*/u, '')
        .trim();
    }

    function parseStreamingSections(markdown) {
      const normalized = normalizeStreamingMarkdown(markdown);
      const sections = [];
      let rest = normalized;
      const headerRe = /^### ([^\n]+)\n\n/;
      while (headerRe.test(rest)) {
        const m = rest.match(/^### ([^\n]+)\n\n/);
        rest = rest.slice(m[0].length);
        const nextIdx = rest.search(/^### /m);
        const body = (nextIdx >= 0 ? rest.slice(0, nextIdx) : rest).trim();
        sections.push({ title: m[1].trim(), body });
        rest = nextIdx >= 0 ? rest.slice(nextIdx) : '';
      }
      return { sections, preview: rest.trim() };
    }

    function processFromMarkdown(markdown) {
      const { sections } = parseStreamingSections(normalizeStreamingMarkdown(markdown));
      let thinking = '';
      const tools = [];
      sections.forEach((sec) => {
        if (sec.title === '思考中') {
          thinking = normalizeThinkingBody(sec.body);
        } else if (sec.title === '执行工作') {
          sec.body.split('\n').map((l) => normalizeToolLine(l)).filter(Boolean).forEach((t) => tools.push(t));
        }
      });
      return { thinking, tools };
    }

    function isPromptEchoLine(line) {
      const t = String(line || '').trim();
      if (!t) return false;
      if (t === '用户') return true;
      if (/^用户消息/.test(t)) return true;
      if (/^---+$/.test(t)) return true;
      if (/^<!--/.test(t)) return true;
      if (/^会话上下文/.test(t)) return true;
      return false;
    }

    function isClientBootstrapPhase(text) {
      return /^正在连接\s*Agent/.test(String(text || '').trim());
    }

    function patchRunStatusFromServer(sessionId, patch) {
      const next = { ...patch };
      delete next.lifecycle;
      delete next.phase;
      // 服务端 status 可能只带 phase/batch；勿用空串覆盖已有 elapsed/ack/batch/external。
      if (!String(next.elapsed || '').trim()) delete next.elapsed;
      if (!String(next.ack || '').trim()) delete next.ack;
      if (!String(next.batch || '').trim()) delete next.batch;
      if (!String(next.external || '').trim()) delete next.external;
      updateRunStatus(sessionId, next);
    }

    function isLifecyclePhaseText(text) {
      const t = String(text || '').trim();
      if (!t) return false;
      if (/^⏳\s*Agent\s*(启动|执行)中/.test(t)) return true;
      if (isClientBootstrapPhase(t)) return true;
      if (/^Worker\s*已就绪/.test(t)) return true;
      if (/^正在初始化\s*Bridge/.test(t)) return true;
      if (/^正在组装提示词/.test(t)) return true;
      if (/^正在准备\s*Agent/.test(t)) return true;
      if (/^正在创建\s*Agent/.test(t)) return true;
      if (/^正在恢复\s*Agent/.test(t)) return true;
      if (/^等待模型响应/.test(t)) return true;
      if (/^Agent\s*已启动/.test(t)) return true;
      if (/^Agent\s*执行中[…\.]?$/.test(t)) return true;
      if (/^(?:Web )?Agent 重启中[…\.]?$/.test(t)) return true;
      return false;
    }

    function isRunStatusPhase(text) {
      const t = String(text || '').trim();
      return !!t && !isLifecyclePhaseText(t);
    }

    function runStatusForRender(status) {
      const src = status || {};
      return {
        ack: src.ack || '',
        batch: src.batch || '',
        external: src.external || '',
        elapsed: src.elapsed || '',
      };
    }

    function sanitizeStreamThinking(thinking) {
      const text = String(thinking || '').trim();
      if (!text || isLifecyclePhaseText(text)) return '';
      return text;
    }

    const STREAM_CONCLUSION_MARKER = /\*\*结论\*\*[：:]/;
    /** 正文预览达到该长度后再折叠思考区，避免流式误切 has-stream-answer 引发布局抖动 */
    const STREAM_ANSWER_LAYOUT_MIN_CHARS = 40;

    function splitStreamThinkingBody(thinking) {
      const text = String(thinking || '').trim();
      if (!text || !STREAM_CONCLUSION_MARKER.test(text)) {
        return { plan: text, answerFromThink: '' };
      }
      const idx = text.search(STREAM_CONCLUSION_MARKER);
      return {
        plan: text.slice(0, idx).trim(),
        answerFromThink: text.slice(idx).trim(),
      };
    }

    function mergeStreamAnswerPreview(markdown, thinking, payload, prevAnswer = '') {
      const { answerFromThink } = splitStreamThinkingBody(thinking);
      const candidates = [
        String(prevAnswer || '').trim(),
        answerFromThink,
        extractStreamAnswerPreview(markdown, payload),
      ];
      return candidates.reduce((best, cur) => {
        const c = String(cur || '').trim();
        if (!c) return best;
        if (!best || c.length > best.length) return c;
        return best;
      }, '');
    }

    function renderStreamAnswerPreviewHtml(answerMarkdown) {
      const text = String(answerMarkdown || '').trim();
      if (!text) return '';
      return `<section class="stream-section stream-section-answer">${renderMarkdown(text, { streaming: true })}</section>`;
    }

    function normalizeThinkingBody(body) {
      return String(body || '')
        .split('\n')
        .map((l) => l.replace(/^>\s*/, '').replace(/^[-*·]\s*/, '').trim())
        .filter((l) => l && !isPromptEchoLine(l) && !isLifecyclePhaseText(l))
        .join('\n');
    }

    function looksLikeToolLine(line) {
      const t = String(line || '').trim();
      if (!t || /^⏳/.test(t)) return false;
      if (/^[🔧✅·]/.test(t)) return true;
      return /^(Shell|Grep|Read|Glob|Task|Write|StrReplace|Delete|Await|CallMcpTool|GetMcpTools|Fetch|WebFetch|WebSearch|EditNotebook|TodoWrite|SwitchMode|Cursor)\b/i.test(t);
    }

    function renderThinkingSectionHtml(thinking, phase) {
      const text = sanitizeStreamThinking(normalizeThinkingBody(thinking));
      const phaseText = String(phase || '').trim();
      const body = text || phaseText;
      if (!body) return '';
      return `<section class="stream-section stream-section-think">
        <div class="stream-section-title">思考中</div>
        <div class="stream-thinking">${escapeHtml(body)}</div>
      </section>`;
    }

    const msgTerminalTextCache = new WeakMap();
    let terminalModalSource = { sessionId: '', msgEl: null, text: '' };

    function ensureRunTerminalState(sessionId) {
      const run = activeRuns.get(sessionId);
      if (!run) return null;
      if (!run.terminal) run.terminal = { text: '', seq: 0 };
      return run.terminal;
    }

    function ensureTerminalModal() {
      let el = document.getElementById('web-terminal-modal-backdrop');
      if (el) return el;
      el = document.createElement('div');
      el.id = 'web-terminal-modal-backdrop';
      el.className = 'web-terminal-modal-backdrop';
      el.hidden = true;
      el.innerHTML = `<div class="web-terminal-modal" role="dialog" aria-label="终端输出">
        <div class="web-terminal-modal-header">
          <span>终端输出</span>
          <button type="button" class="web-terminal-modal-close" aria-label="关闭">×</button>
        </div>
        <pre class="web-terminal-modal-body"></pre>
      </div>`;
      el.addEventListener('click', (ev) => {
        if (ev.target === el) closeTerminalModal();
      });
      el.querySelector('.web-terminal-modal-close')?.addEventListener('click', closeTerminalModal);
      document.body.appendChild(el);
      return el;
    }

    const TERMINAL_ESCAPE_MAP = { n: '\n', t: '\t', r: '\r', '"': '"', "'": "'", '\\': '\\' };

    function unescapeDisplayEscapes(text) {
      let body = String(text || '');
      if (!body.includes('\\')) return body;
      for (let round = 0; round < 6; round += 1) {
        const next = body.replace(/\\([ntr'"\\])/g, (_, ch) => TERMINAL_ESCAPE_MAP[ch] || `\\${ch}`);
        if (next === body) break;
        body = next;
      }
      return body;
    }

    function formatTerminalDisplayText(text) {
      const raw = String(text || '');
      if (!raw.trim()) return '';
      const marker = "{'exitCode'";
      const parts = [];
      let i = 0;
      while (i < raw.length) {
        const pos = raw.indexOf(marker, i);
        if (pos < 0) {
          const tail = raw.slice(i).trim();
          if (tail) parts.push(unescapeDisplayEscapes(tail));
          break;
        }
        if (pos > i) {
          const prefix = raw.slice(i, pos).trimEnd();
          if (prefix) parts.push(prefix);
        }
        let end = -1;
        for (let j = pos + 12; j <= Math.min(raw.length, pos + 250000); j += 1) {
          const chunk = raw.slice(pos, j);
          if ((chunk.match(/\{/g) || []).length > (chunk.match(/\}/g) || []).length + 2) continue;
          try {
            // eslint-disable-next-line no-new-func
            const parsed = Function(`"use strict"; return (${chunk});`)();
            if (parsed && typeof parsed === 'object' && 'exitCode' in parsed) {
              const block = [];
              block.push(`exitCode: ${parsed.exitCode}`);
              ['stdout', 'stderr'].forEach((key) => {
                const piece = unescapeDisplayEscapes(String(parsed[key] || '')).trim();
                if (piece) block.push(piece);
              });
              parts.push(block.join('\n'));
              end = j;
              break;
            }
          } catch {
            /* continue */
          }
        }
        if (end < 0) {
          parts.push(unescapeDisplayEscapes(raw.slice(pos, pos + 400)));
          i = pos + 1;
        } else {
          i = end;
        }
      }
      return parts.join('\n').trim();
    }

    function stripInterruptShellBlock(markdown) {
      return String(markdown || '').replace(/\n#### Shell 输出（节选）\n\n```[\s\S]*?```/g, '').trim();
    }

    function resolveMsgTerminalText(msgEl, sessionId = '') {
      if (!msgEl) return '';
      const cached = msgTerminalTextCache.get(msgEl);
      if (cached) return cached;
      const sid = String(sessionId || '').trim();
      const run = sid ? activeRuns.get(sid) : null;
      if (run?.shellEl === msgEl && run.terminal?.text) {
        return String(run.terminal.text || '');
      }
      return '';
    }

    function storeMsgTerminalText(msgEl, text) {
      const body = String(text || '').trim();
      if (!msgEl || !body) return;
      msgTerminalTextCache.set(msgEl, body);
    }

    function bindTerminalButton(shell, sessionId) {
      if (!shell) return;
      shell.querySelectorAll('[data-terminal-btn]').forEach((btn) => {
        if (btn.dataset.bound === '1') return;
        btn.dataset.bound = '1';
        btn.addEventListener('click', (ev) => {
          ev.preventDefault();
          ev.stopPropagation();
          const sid = String(sessionId || shellSessionId(shell) || currentSessionId || '').trim();
          openTerminalModalForMessage(shell, sid);
        });
      });
    }

    function updateTerminalButtonVisibility(shell) {
      if (!shell?.classList?.contains('assistant')) return;
      syncMsgTerminalButton(shell, shellSessionId(shell));
    }

    function syncMsgTerminalButton(msgEl, sessionId = '') {
      if (!msgEl?.classList?.contains('assistant')) return;
      const bodyEl = msgEl.querySelector('.msg-body');
      if (!bodyEl) return;
      purgeInlineTerminalButtons(bodyEl);
      const inlineText = resolveMsgTerminalText(msgEl, sessionId);
      if (inlineText.trim()) storeMsgTerminalText(msgEl, inlineText);
      const show = shouldShowMsgTerminalButton(msgEl, sessionId);
      if (!show) {
        removeAssistantTerminalButton(msgEl);
        return;
      }
      ensureAssistantTerminalButton(msgEl);
      const slot = msgEl.querySelector('.msg-terminal-external');
      if (slot) slot.hidden = false;
      bindTerminalButton(msgEl, sessionId);
    }

    async function hydrateMsgTerminalFromRun(msgEl) {
      const runId = String(msgEl?.dataset?.runId || '').trim();
      if (!runId || resolveMsgTerminalText(msgEl)) return;
      try {
        const data = await api(`/api/runs/${runId}/terminal`, { cache: 'no-store' });
        const text = String(data?.terminal_text || '').trim();
        if (text) {
          storeMsgTerminalText(msgEl, text);
          syncMsgTerminalButton(msgEl);
        }
      } catch { /* 历史终端缺失可忽略 */ }
    }

    function attachTerminalFromDoneEvent(msgEl, sessionId, data = {}) {
      if (!msgEl?.isConnected) return;
      const runId = String(data.run_id || data.runId || '').trim();
      if (runId) msgEl.dataset.runId = runId;
      const text = String(data.terminal_text || '').trim();
      if (text) storeMsgTerminalText(msgEl, text);
      else if (sessionId) {
        const buf = ensureRunTerminalState(sessionId);
        if (buf?.text) storeMsgTerminalText(msgEl, buf.text);
      }
      syncMsgTerminalButton(msgEl, sessionId);
      if (!text && runId) void hydrateMsgTerminalFromRun(msgEl);
    }

    function refreshTerminalModalContent() {
      const backdrop = document.getElementById('web-terminal-modal-backdrop');
      if (!backdrop || backdrop.hidden) return;
      const pre = backdrop.querySelector('.web-terminal-modal-body');
      if (!pre) return;
      let raw = String(terminalModalSource.text || '').trim();
      if (!raw && terminalModalSource.msgEl) {
        raw = resolveMsgTerminalText(terminalModalSource.msgEl, terminalModalSource.sessionId);
      }
      if (!raw && terminalModalSource.sessionId) {
        const buf = ensureRunTerminalState(terminalModalSource.sessionId);
        raw = String(buf?.text || '').trim();
      }
      const next = formatTerminalDisplayText(raw);
      const display = next || '（暂无输出：本轮 Agent 尚未通过 Shell 产生 stdout）';
      if (pre.textContent !== display) {
        pre.textContent = display;
        pre.scrollTop = pre.scrollHeight;
      }
    }

    function openTerminalModalForMessage(msgEl, sessionId, textOverride = '') {
      const sid = String(sessionId || '').trim();
      if (!msgEl?.isConnected) return;
      terminalModalSource = {
        sessionId: sid,
        msgEl,
        text: String(textOverride || resolveMsgTerminalText(msgEl, sid) || '').trim(),
      };
      const backdrop = ensureTerminalModal();
      backdrop.hidden = false;
      document.body.classList.add('web-terminal-modal-open');
      if (!terminalModalSource.text && msgEl.dataset.runId) {
        void hydrateMsgTerminalFromRun(msgEl).then(() => refreshTerminalModalContent());
      } else {
        refreshTerminalModalContent();
      }
    }

    function closeTerminalModal() {
      const backdrop = document.getElementById('web-terminal-modal-backdrop');
      if (backdrop) backdrop.hidden = true;
      document.body.classList.remove('web-terminal-modal-open');
      terminalModalSource = { sessionId: '', msgEl: null, text: '' };
    }

    function appendRunTerminalText(sessionId, chunk, seq) {
      const buf = ensureRunTerminalState(sessionId);
      if (!buf || !chunk) return;
      if (seq && seq <= buf.seq) return;
      if (seq) buf.seq = seq;
      buf.text += chunk;
      if (buf.text.length > 200000) buf.text = buf.text.slice(-200000);
    }

    function syncRunTerminalFromServer(sessionId, text, seq) {
      const buf = ensureRunTerminalState(sessionId);
      if (!buf) return;
      const nextSeq = Number(seq) || 0;
      if (nextSeq > 0 && nextSeq < buf.seq) return;
      buf.text = String(text || '');
      if (nextSeq) buf.seq = nextSeq;
    }

    function handleTerminalStreamEvent(sessionId, data) {
      if (!data || data.type !== 'terminal') return;
      if (data.sync) {
        syncRunTerminalFromServer(sessionId, data.text, data.seq);
      } else {
        appendRunTerminalText(sessionId, data.chunk || '', data.seq);
      }
      if (terminalModalSource.sessionId === sessionId) refreshTerminalModalContent();
      const run = activeRuns.get(sessionId);
      if (run?.shellEl?.isConnected) {
        const text = run.terminal?.text || '';
        if (text) storeMsgTerminalText(run.shellEl, text);
        syncMsgTerminalButton(run.shellEl, sessionId);
        updateTerminalButtonVisibility(run.shellEl);
      }
    }

    function renderToolsSectionHtml(tools) {
      const lines = (Array.isArray(tools) ? tools : [])
        .map((t) => String(t || '').trim())
        .filter(Boolean);
      if (!lines.length) return '';
      return `<section class="stream-section stream-section-tools">
        <div class="stream-section-title">执行工作</div>
        <ul class="stream-list stream-tool-list">${lines.map((line) => `<li>${escapeHtml(line)}</li>`).join('')}</ul>
      </section>`;
    }

    function extractStreamAnswerPreview(markdown, payload) {
      const md = String(markdown || '').trim();
      if (!md) return '';
      const normalized = normalizeStreamingMarkdown(md);
      const { sections } = parseStreamingSections(normalized);
      const parts = [];
      const toolSet = new Set(
        (Array.isArray(payload?.tools) ? payload.tools : [])
          .map((t) => String(t || '').replace(/\s*…\s*$/, '').trim())
          .filter(Boolean),
      );

      sections
        .filter((s) => s.title !== '思考中' && s.title !== '执行工作')
        .forEach((s) => {
          const body = String(s.body || '').trim();
          if (body && !/^⏳/.test(body)) parts.push(body);
        });

      const toolSec = sections.find((s) => s.title === '执行工作');
      if (toolSec) {
        const bodyLines = String(toolSec.body || '')
          .split('\n')
          .map((l) => normalizeToolLine(l))
          .filter(Boolean);
        const extra = bodyLines.filter((l) => {
          const key = l.replace(/\s*…\s*$/, '').trim();
          return !toolSet.has(key) && !looksLikeToolLine(l);
        });
        if (extra.length) parts.push(extra.join('\n'));
      }

      let tail = normalized;
      if (sections.length) {
        const last = sections[sections.length - 1];
        const marker = `### ${last.title}\n\n`;
        const idx = normalized.lastIndexOf(marker);
        if (idx >= 0) {
          tail = normalized.slice(idx + marker.length).trim();
          if (last.title === '思考中') {
            const thinking = normalizeThinkingBody(payload?.thinking || last.body);
            if (thinking && tail.startsWith(thinking)) {
              tail = tail.slice(thinking.length).trim();
            } else if (thinking && tail === thinking) {
              tail = '';
            }
          } else if (last.title === '执行工作') {
            const known = new Set(
              String(last.body || '')
                .split('\n')
                .map((l) => normalizeToolLine(l))
                .filter(Boolean),
            );
            const unknown = tail
              .split('\n')
              .map((l) => normalizeToolLine(l))
              .filter((l) => l && !known.has(l) && !looksLikeToolLine(l));
            tail = unknown.join('\n').trim();
          }
        }
      }
      if (tail && !/^⏳/.test(tail) && !looksLikeToolLine(tail)) {
        parts.push(tail);
      }

      return parts
        .map((p) => String(p || '').trim())
        .filter(Boolean)
        .join('\n\n')
        .trim();
    }

    function renderProcessPanel(process) {
      const thinking = String(process?.thinking || '').trim();
      const tools = Array.isArray(process?.tools) ? process.tools.map((t) => String(t || '').trim()).filter(Boolean) : [];
      const sections = [];
      const thinkHtml = renderThinkingSectionHtml(thinking, process?.phase);
      if (thinkHtml) sections.push(thinkHtml);
      const toolsHtml = renderToolsSectionHtml(tools);
      if (toolsHtml) sections.push(toolsHtml);
      if (!sections.length) return '';
      return `<div class="stream-body stream-process">${sections.join('')}</div>`;
    }

    function renderStreamingBody(markdown) {
      const text = String(markdown || '').trim();
      if (!text) {
        return `<div class="stream-body"><div class="stream-placeholder">${escapeHtml('⏳ Agent 启动中…')}</div></div>`;
      }
      const normalized = normalizeStreamingMarkdown(text);
      if (normalized.startsWith('⏳') && !normalized.includes('###')) {
        return `<div class="stream-body"><div class="stream-text stream-status">${escapeHtml(normalized)}</div></div>`;
      }
      const { sections, preview } = parseStreamingSections(normalized);
      if (!sections.length && !preview) {
        return `<div class="stream-body"><div class="stream-text">${escapeHtml(normalized).replace(/\n/g, '<br>')}</div></div>`;
      }
      let html = '<div class="stream-body">';
      sections.forEach((sec) => {
        const kind = sec.title === '思考中' ? 'think' : (sec.title === '执行工作' ? 'tools' : 'other');
        html += `<section class="stream-section stream-section-${kind}">`;
        html += `<div class="stream-section-title">${escapeHtml(sec.title)}</div>`;
        if (sec.title === '思考中') {
          html += `<div class="stream-thinking">${escapeHtml(normalizeThinkingBody(sec.body))}</div>`;
        } else if (sec.title === '执行工作') {
          const toolLines = sec.body.split('\n').map((l) => normalizeToolLine(l)).filter(Boolean);
          if (toolLines.length) {
            html += `<ul class="stream-list stream-tool-list">${toolLines.map((line) => `<li>${escapeHtml(line)}</li>`).join('')}</ul>`;
          } else {
            html += `<div class="stream-text stream-muted">等待工具输出…</div>`;
          }
        } else {
          html += `<div class="stream-text">${escapeHtml(sec.body).replace(/\n/g, '<br>')}</div>`;
        }
        html += '</section>';
      });
      if (preview) {
        const previewLines = preview.split('\n').map((l) => normalizeToolLine(l)).filter(Boolean);
        const hasThinkSec = sections.some((s) => s.title === '思考中');
        const hasToolSec = sections.some((s) => s.title === '执行工作');
        const allToolLike = previewLines.length > 0 && previewLines.every(looksLikeToolLine);
        if (allToolLike && !hasToolSec) {
          html += renderToolsSectionHtml(previewLines);
        } else if (!hasThinkSec && !/^⏳/.test(preview) && !allToolLike) {
          html += renderThinkingSectionHtml(preview);
        } else if (!/^⏳/.test(preview)) {
          html += `<section class="stream-section stream-section-preview"><div class="stream-text">${escapeHtml(preview).replace(/\n/g, '<br>')}</div></section>`;
        }
      }
      html += '</div>';
      return html;
    }

    const markdownRenderCache = new Map();
    const MARKDOWN_CACHE_LIMIT = 256;

    function normalizeQaSummaryMarkdown(text) {
      const raw = String(text || '');
      if (!/问答概述/.test(raw)) return raw;
      const combinedRe = /^(\d+)\.\s*(?:\*\*)?\s*问(?:\*\*)?[：:]\s*(.+?)\s+(?:\*\*)?答(?:\*\*)?[：:]\s*(.+?)\s*$/;
      const splitQuestionRe = /^(\d+)\.\s*\*\*问\*\*[：:]\s*(.+?)\s*$/;
      const splitAnswerRe = /^\s*\*\*答\*\*[：:]\s*(.+?)\s*$/;
      const lines = raw.replace(/\r\n/g, '\n').split('\n');
      const out = [];
      let pendingQ = null;
      const flushPending = () => {
        if (!pendingQ) return;
        out.push(`**${pendingQ.num}. 问**：${pendingQ.q}`, '', `**答**：（无回答）`);
        pendingQ = null;
      };
      const emitPair = (num, q, a) => {
        out.push(`**${num}. 问**：${q}`, '', `**答**：${a}`);
      };
      for (const line of lines) {
        if (!line.trim()) {
          if (!pendingQ) out.push(line);
          continue;
        }
        const combined = line.match(combinedRe);
        if (combined) {
          flushPending();
          emitPair(combined[1], combined[2].trim(), combined[3].trim());
          continue;
        }
        const splitQ = line.match(splitQuestionRe);
        if (splitQ) {
          flushPending();
          pendingQ = { num: splitQ[1], q: splitQ[2].trim() };
          continue;
        }
        const splitA = line.match(splitAnswerRe);
        if (splitA && pendingQ) {
          emitPair(pendingQ.num, pendingQ.q, splitA[1].trim());
          pendingQ = null;
          continue;
        }
        flushPending();
        out.push(line);
      }
      flushPending();
      return out.join('\n');
    }

    let markedLoadPromise = null;
    function ensureMarkedLoaded() {
      if (typeof marked !== 'undefined') return Promise.resolve();
      if (markedLoadPromise) return markedLoadPromise;
      markedLoadPromise = new Promise((resolve, reject) => {
        const el = document.createElement('script');
        el.src = 'https://cdn.jsdelivr.net/npm/marked/marked.min.js';
        el.onload = () => {
          resolve();
          if (isWebAgentMobile() && messagesDomHasConversation()) {
            void loadMessages({ repaint: true, force: false }).catch(() => {});
          }
        };
        el.onerror = () => reject(new Error('marked load failed'));
        document.head.appendChild(el);
      });
      return markedLoadPromise;
    }

    function renderMarkdown(text, options = {}) {
      const { streaming = false } = options;
      const raw = normalizeQaSummaryMarkdown(String(text || ''));
      if (!streaming && raw) {
        const cached = markdownRenderCache.get(raw);
        if (cached) return cached;
      }
      let html;
      try {
        if (typeof marked === 'undefined') {
          html = `<div class="markdown-body">${raw.replace(/</g, '&lt;').replace(/\n/g, '<br>')}</div>`;
        } else {
        const parseOpts = { gfm: true, breaks: !!streaming };
        if (typeof marked?.use === 'function') {
          marked.use(parseOpts);
        } else if (marked?.setOptions) {
          marked.setOptions(parseOpts);
        }
        html = `<div class="markdown-body">${withLinksOpenInNewTab(marked.parse(raw))}</div>`;
        }
      } catch {
        html = `<div class="markdown-body">${raw.replace(/</g, '&lt;').replace(/\n/g, '<br>')}</div>`;
      }
      if (!streaming && raw) {
        markdownRenderCache.set(raw, html);
        while (markdownRenderCache.size > MARKDOWN_CACHE_LIMIT) {
          const oldest = markdownRenderCache.keys().next().value;
          markdownRenderCache.delete(oldest);
        }
      }
      return html;
    }

    function extractPlainStreamingText(markdown) {
      const md = String(markdown || '').trim();
      if (!md || /^⏳ Agent/.test(md)) return '';
      const normalized = normalizeStreamingMarkdown(md);
      const { sections, preview } = parseStreamingSections(normalized);
      const thinkSec = sections.find((s) => s.title === '思考中');
      if (thinkSec) return normalizeThinkingBody(thinkSec.body);
      if (!sections.length) return preview || normalized;
      return preview || '';
    }

    function pickLongerText(a, b) {
      const left = String(a || '').trim();
      const right = String(b || '').trim();
      if (!left) return right;
      if (!right) return left;
      return right.length > left.length ? right : left;
    }

    function streamStateKey(markdown, process) {
      const proc = (process && typeof process === 'object') ? process : {};
      const tools = Array.isArray(proc.tools) ? proc.tools : [];
      return JSON.stringify({
        md: String(markdown || ''),
        thinking: String(proc.thinking || ''),
        tools,
      });
    }

    function mergeProcessPayload(process, markdown) {
      const fromMd = processFromMarkdown(markdown);
      const plain = extractPlainStreamingText(markdown);
      const p = (process && typeof process === 'object') ? process : {};
      const thinking = sanitizeStreamThinking(pickLongerText(
        pickLongerText(p.thinking, fromMd.thinking),
        plain,
      ));
      const mdTools = fromMd.tools;
      const procTools = Array.isArray(p.tools) ? p.tools.map((t) => String(t || '').trim()).filter(Boolean) : [];
      const tools = procTools.length >= mdTools.length ? procTools : mdTools;
      const phase = String(p.phase || '').trim();
      return { thinking, tools, phase };
    }

    function resolveStreamThinking(markdown, payload) {
      const merged = payload || { thinking: '', tools: [], phase: '' };
      let thinking = sanitizeStreamThinking(String(merged.thinking || '').trim());
      const md = String(markdown || '').trim();
      if (!thinking && md && !/^⏳ Agent/.test(md)) {
        const fromMd = processFromMarkdown(md);
        thinking = sanitizeStreamThinking(String(fromMd.thinking || extractPlainStreamingText(md) || '').trim());
        if (!thinking && !md.includes('###')) {
          thinking = md;
        }
      }
      return thinking;
    }

    function hasStreamProcessContent(process) {
      if (!process || typeof process !== 'object') return false;
      if (sanitizeStreamThinking(String(process.thinking || ''))) return true;
      return Array.isArray(process.tools) && process.tools.length > 0;
    }

    function resolveStreamDisplayPhase(incomingPhase, prevPhase, hasThinkingOrTools) {
      if (hasThinkingOrTools) return '';
      const incoming = String(incomingPhase || '').trim();
      const prev = String(prevPhase || '').trim();
      if (incoming) return incoming;
      return prev;
    }

    function buildStreamDisplay(markdown, process, prevDisplay) {
      const prev = prevDisplay || { thinking: '', tools: [], phase: '', answerPreview: '', fullThinking: '' };
      const incoming = mergeProcessPayload(process, markdown);
      const thinking = pickLongerText(
        pickLongerText(prev.fullThinking, prev.thinking),
        resolveStreamThinking(markdown, incoming),
      );
      const sanitizedThinking = sanitizeStreamThinking(thinking);
      const tools = (Array.isArray(incoming.tools) && incoming.tools.length >= (prev.tools || []).length)
        ? incoming.tools
        : (prev.tools || []);
      const answerPreview = mergeStreamAnswerPreview(
        markdown,
        sanitizedThinking,
        { thinking: sanitizedThinking, tools },
        prev.answerPreview,
      );
      const { plan } = splitStreamThinkingBody(sanitizedThinking);
      const displayThinking = answerPreview
        ? plan
        : sanitizedThinking;
      const hasThinkingOrTools = !!displayThinking
        || !!sanitizedThinking
        || (Array.isArray(tools) && tools.length > 0)
        || !!answerPreview;
      const phase = resolveStreamDisplayPhase(incoming.phase, prev.phase, hasThinkingOrTools);
      return {
        thinking: displayThinking,
        tools,
        phase,
        answerPreview,
        fullThinking: sanitizedThinking,
      };
    }

    function rememberRunStreamState(sessionId, markdown, process) {
      const run = activeRuns.get(sessionId);
      if (!run) return null;
      const prevDisplay = run.lastStream?.display || { thinking: '', tools: [] };
      const display = buildStreamDisplay(markdown, process, prevDisplay);
      run.lastStream = {
        markdown: String(markdown || ''),
        process: (process && typeof process === 'object') ? process : null,
        display,
      };
      return display;
    }

    function refreshStreamingShellFromRun(sessionId) {
      const run = activeRuns.get(sessionId);
      if (!run?.lastStream?.display || run.streamFinalized) return;
      const shell = run.shellEl || ensureStreamingShell(sessionId);
      if (isStreamingShellFinalized(shell)) return;
      scheduleStreamingMsgBodyUpdate(shell, run.lastStream.display);
    }

    const streamingBodyRaf = new WeakMap();

    function cancelStreamingMsgBodyUpdate(shell) {
      if (!shell) return;
      const prev = streamingBodyRaf.get(shell);
      if (prev) {
        cancelAnimationFrame(prev);
        streamingBodyRaf.delete(shell);
      }
    }

    function isStreamingShellFinalized(shell) {
      return shell?.dataset?.streamFinalized === '1';
    }

    function finalizeStreamingShell(sessionId, shellEl, markdown, opts = {}) {
      if (!shellEl?.isConnected) return;
      const sid = String(sessionId || '').trim();
      let md = String(markdown || '').trim();
      if (isFailureReplyText(md)) md = stripInterruptShellBlock(md);
      if (!md && (deferredRestartAwaiting.has(sid) || opts.deferWebAgentRestart)) {
        return;
      }
      cancelStreamingMsgBodyUpdate(shellEl);
      shellEl.dataset.streamFinalized = '1';
      shellEl.classList.remove('streaming');
      if (terminalModalSource.msgEl === shellEl) refreshTerminalModalContent();
      clearRunStatus(sessionId, shellEl);
      setAssistantMessageBody(shellEl, md || '（无回复）', {
        files: opts.files || [],
        images: opts.images || [],
      });
      const terminalMeta = opts.terminal && typeof opts.terminal === 'object' ? opts.terminal : {};
      attachTerminalFromDoneEvent(shellEl, sid, terminalMeta);
      ensureAssistantShareButton(shellEl);
      if (opts.timestamp) shellEl.dataset.timestamp = opts.timestamp;
      const run = activeRuns.get(sessionId);
      if (run) run.streamFinalized = true;
    }

    async function refreshAssistantAttachmentsFromServer(sessionId, shellEl) {
      if (!shellEl?.isConnected) return;
      if (sessionCacheAwaitingAssistantReply(sessionId)) return;
      try {
        const data = await api(`/api/sessions/${sessionId}/messages?tail=15`);
        const msgs = data.messages || [];
        const lastAssist = assistantReplyAfterLastUser(msgs);
        if (!lastAssist?.files?.length && !lastAssist?.images?.length) return;
        const bodyEl = shellEl.querySelector('.msg-body');
        const md = getMessageMarkdown(bodyEl) || String(lastAssist.content || '').trim();
        setAssistantMessageBody(shellEl, md, {
          files: lastAssist.files || [],
          images: lastAssist.images || [],
        });
      } catch { /* 附件兜底失败可忽略 */ }
    }

    async function finalizeStreamingShellFromServer(sessionId) {
      const run = activeRuns.get(sessionId);
      const shell = run?.shellEl || findOrphanStreamingShell(sessionId);
      if (!shell?.isConnected || isStreamingShellFinalized(shell)) return;
      try {
        const data = await api(`/api/sessions/${sessionId}/messages?tail=30`, { cache: 'no-store' });
        const msgs = data.messages || [];
        const lastAssist = assistantReplyAfterLastUser(msgs);
        if (!lastAssist) return;
        finalizeStreamingShell(sessionId, shell, lastAssist.content, {
          timestamp: lastAssist.timestamp,
          files: lastAssist.files || [],
          images: lastAssist.images || [],
        });
        sessionMessagesEtags.delete(sessionId);
      } catch { /* 兜底失败时由 loadMessages 重绘 */ }
    }

    function scheduleStreamingMsgBodyUpdate(shell, display) {
      if (!shell || isStreamingShellFinalized(shell)) return;
      const prev = streamingBodyRaf.get(shell);
      if (prev) cancelAnimationFrame(prev);
      streamingBodyRaf.set(shell, requestAnimationFrame(() => {
        streamingBodyRaf.delete(shell);
        updateStreamingMsgBody(shell, display);
      }));
    }

    function stopRunStreamPoll(sessionId, runToken = '') {
      const run = activeRuns.get(sessionId);
      if (!run?.streamPollTimer) return;
      if (runToken && run.runToken !== runToken) return;
      clearInterval(run.streamPollTimer);
      run.streamPollTimer = null;
    }

    function startRunStreamPoll(sessionId) {
      const sid = String(sessionId || '').trim();
      if (!sid) return;
      const run = activeRuns.get(sid);
      if (!run) return;
      stopRunStreamPoll(sid, run.runToken);
      const pollToken = run.runToken;
      run.streamPollTimer = setInterval(async () => {
        if (document.hidden) return;
        const current = activeRuns.get(sid);
        if (!current || current.runToken !== pollToken || !current.runId || current.cancelling) {
          stopRunStreamPoll(sid, pollToken);
          return;
        }
        if (current.streamFinalized) return;
        if (sid !== currentSessionId) return;
        try {
          const headers = {};
          const cachedEtag = activeRunEtags.get(sid);
          if (cachedEtag) headers['If-None-Match'] = cachedEtag;
          const active = await api(`/api/sessions/${sid}/active-run`, { headers });
          if (activeRuns.get(sid)?.streamFinalized) return;
          if (active.__notModified) {
            if (active.__etag) activeRunEtags.set(sid, active.__etag);
            if (
              !current.streamFinalized
              && sid === currentSessionId
              && (current.shellEl?.isConnected || findOrphanStreamingShell(sid))
            ) {
              await finalizeStreamingShellFromServer(sid);
              if (!activeRuns.get(sid)?.streamFinalized && currentSessionId === sid) {
                await refreshSessionMessagesCacheFromServer(sid);
                await loadMessages({ force: true, repaint: true });
              }
            }
            return;
          }
          if (active.__etag) activeRunEtags.set(sid, active.__etag);
          if (!active?.active || !active.run_id) {
            stopRunStreamPoll(sid, pollToken);
            activeRunEtags.delete(sid);
            if (current.streamFinalized) {
              if (isActiveRun(sid, { runToken: pollToken })) finishRun(sid, pollToken);
              else refreshSessionListAfterRunEnd(sid);
              return;
            }
            if (
              sid === currentSessionId
              && (current.shellEl?.isConnected || findOrphanStreamingShell(sid))
              && !deferredRestartAwaiting.has(sid)
            ) {
              await finalizeStreamingShellFromServer(sid);
              if (!activeRuns.get(sid)?.streamFinalized) {
                await refreshSessionMessagesCacheFromServer(sid);
                await loadMessages({ force: true, repaint: true });
              }
            }
            if (isActiveRun(sid, { runToken: pollToken })) {
              finishRun(sid, pollToken);
            } else {
              refreshSessionListAfterRunEnd(sid);
            }
            return;
          }
          const md = String(active.markdown || '');
          let proc = active.process;
          if (active.phase_line && !hasStreamProcessContent(proc)) {
            proc = { ...(proc && typeof proc === 'object' ? proc : {}), phase: active.phase_line };
          }
          const prevDisplay = current.lastStream?.display || { thinking: '', tools: [], phase: '', answerPreview: '' };
          const nextDisplay = buildStreamDisplay(md, proc, prevDisplay);
          const displayChanged = !(
            nextDisplay.thinking === prevDisplay.thinking
            && JSON.stringify(nextDisplay.tools) === JSON.stringify(prevDisplay.tools || [])
            && nextDisplay.phase === prevDisplay.phase
            && nextDisplay.answerPreview === (prevDisplay.answerPreview || '')
          );
          if (displayChanged) {
            const display = rememberRunStreamState(sid, md, proc);
            const shell = current.shellEl || ensureStreamingShell(sid);
            if (display) {
              scheduleStreamingMsgBodyUpdate(shell, display);
            }
          }
          if (active.ack_line || active.elapsed_line || active.batch_line || active.external_line) {
            patchRunStatusFromServer(sid, {
              ack: active.ack_line || '',
              elapsed: active.elapsed_line || '',
              batch: active.batch_line || '',
              external: active.external_line || '',
            });
          }
          const tSeq = Number(active.terminal_seq) || 0;
          const curSeq = Number(current.terminal?.seq) || 0;
          if (active.terminal_text != null && tSeq >= curSeq) {
            syncRunTerminalFromServer(sid, active.terminal_text, tSeq);
            if (terminalModalSource.sessionId === sid) refreshTerminalModalContent();
          }
        } catch {
          /* 轮询失败忽略，SSE 仍为主通道 */
        }
      }, 800);
    }

    function applyLifecyclePhaseToStream(sessionId, phase, { markdown = '', process = null } = {}) {
      const run = activeRuns.get(sessionId);
      if (!run || run.streamFinalized) return;
      const md = String(markdown || run.lastStream?.markdown || '');
      const proc = {
        ...(process && typeof process === 'object' ? process : (run.lastStream?.process || {})),
        phase,
      };
      const display = rememberRunStreamState(sessionId, md, proc);
      if (sessionId !== currentSessionId || !display) return;
      const shell = run.shellEl || ensureStreamingShell(sessionId);
      scheduleStreamingMsgBodyUpdate(shell, display);
    }

    function shouldUseStreamAnswerLayout(shell, answerPreview) {
      const text = String(answerPreview || '').trim();
      if (!text) return false;
      if (shell.classList.contains('has-stream-answer')) return true;
      return text.length >= STREAM_ANSWER_LAYOUT_MIN_CHARS;
    }

    function scrollStreamThinkingIfPinned(thinkEl) {
      if (!thinkEl) return;
      const gap = thinkEl.scrollHeight - thinkEl.scrollTop - thinkEl.clientHeight;
      if (gap <= 28) thinkEl.scrollTop = thinkEl.scrollHeight;
    }

    function tryPatchStreamingThinkingOnly(bodyEl, payload, thinkPhase) {
      const tools = Array.isArray(payload.tools) ? payload.tools : [];
      if (tools.length) return false;
      const root = bodyEl.querySelector(':scope > .stream-body.stream-process');
      if (!root || root.querySelector('.stream-section-answer') || root.querySelector('.stream-section-tools')) {
        return false;
      }
      const thinkSec = root.querySelector('.stream-section-think');
      if (!thinkSec) return false;
      const thinkEl = thinkSec.querySelector('.stream-thinking');
      if (!thinkEl) return false;
      const text = sanitizeStreamThinking(normalizeThinkingBody(payload.thinking));
      const phaseText = String(thinkPhase || '').trim();
      const body = text || phaseText;
      if (!body) return false;
      if (thinkEl.textContent !== body) thinkEl.textContent = body;
      scrollStreamThinkingIfPinned(thinkEl);
      const shell = bodyEl.closest('.msg.assistant');
      const sid = shellSessionId(shell);
      syncMsgTerminalButton(shell, sid);
      bindTerminalButton(shell, sid);
      updateTerminalButtonVisibility(shell);
      return true;
    }

    function buildStreamingMsgBodyHtml(payload, thinkPhase, answerForLayout) {
      const sections = [];
      const thinkHtml = renderThinkingSectionHtml(payload.thinking, thinkPhase);
      if (thinkHtml) sections.push(thinkHtml);
      const toolsHtml = renderToolsSectionHtml(payload.tools);
      if (toolsHtml) sections.push(toolsHtml);
      const answerHtml = renderStreamAnswerPreviewHtml(answerForLayout);
      if (answerHtml) sections.push(answerHtml);
      if (sections.length) {
        return `<div class="stream-body stream-process">${sections.join('')}</div>`;
      }
      return '<div class="stream-body stream-body-empty"></div>';
    }

    function updateStreamingMsgBody(shell, display) {
      if (!shell || isStreamingShellFinalized(shell)) return;
      const bodyEl = shell.querySelector('.msg-body');
      if (!bodyEl) return;
      const payload = (display && typeof display === 'object')
        ? display
        : { thinking: '', tools: [], phase: '', answerPreview: '' };
      const answerPreview = String(payload.answerPreview || '').trim();
      const showAnswerLayout = shouldUseStreamAnswerLayout(shell, answerPreview);
      shell.classList.toggle('has-stream-answer', showAnswerLayout);
      const answerForLayout = showAnswerLayout ? answerPreview : '';
      const thinkPhase = answerForLayout ? '' : payload.phase;
      if (tryPatchStreamingThinkingOnly(bodyEl, payload, thinkPhase)) {
        if (messagesPinnedToBottom) scheduleScrollMessagesToBottom();
        else scheduleAutoLoadOlderIfNeeded(getMessagesEl());
        return;
      }
      bodyEl.innerHTML = buildStreamingMsgBodyHtml(payload, thinkPhase, answerForLayout);
      const sid = shellSessionId(shell);
      syncMsgTerminalButton(shell, sid);
      bindTerminalButton(shell, sid);
      updateTerminalButtonVisibility(shell);
      scrollStreamThinkingIfPinned(bodyEl.querySelector('.stream-thinking'));
      if (messagesPinnedToBottom) {
        scheduleScrollMessagesToBottom();
      } else {
        scheduleAutoLoadOlderIfNeeded(getMessagesEl());
      }
    }

    function setupMarkdownLinkNewTab() {
      const container = document.getElementById('messages');
      if (!container || container.dataset.markdownLinkBound === '1') return;
      container.dataset.markdownLinkBound = '1';
      container.addEventListener('click', (event) => {
        const link = event.target.closest('.msg-body .markdown-body a[href]');
        if (!link) return;
        const href = (link.getAttribute('href') || '').trim();
        if (!href || href.startsWith('#') || href.startsWith('javascript:')) return;
        if (link.getAttribute('target') === '_blank') return;
        event.preventDefault();
        window.open(href, '_blank', 'noopener,noreferrer');
      });
    }

    async function api(path, opts = {}) {
      const { headers: optHeaders, signal, ...restOpts } = opts;
      const resp = await fetch(API + path, {
        credentials: 'same-origin',
        signal,
        ...restOpts,
        headers: { 'Content-Type': 'application/json', ...(optHeaders || {}) },
      });
      if (resp.status === 401) {
        const readOnlyBrowse = opts.method === undefined || opts.method === 'GET';
        const pathOnly = path.split('?')[0];
        const browsingSession = /^\/api\/sessions(\/[a-z0-9]+)?(\/messages)?$/.test(pathOnly);
        const messageBoardApi = /^\/api\/message-board(\/[a-f0-9]{32})?$/.test(pathOnly);
        const avatarApi = pathOnly === '/api/dingtalk/user-avatars'
          || pathOnly.startsWith('/api/dingtalk/avatar/');
        if (otpAuthEnabled && !(readOnlyBrowse && (browsingSession || avatarApi)) && !messageBoardApi) {
          goToLogin();
          throw new Error('请先登录');
        }
        throw new Error('需要登录鉴权，请刷新页面并在浏览器登录框输入账号密码');
      }
      if (resp.status === 304) {
        return { __notModified: true, __etag: resp.headers.get('ETag') || '' };
      }
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.error || `HTTP ${resp.status}`);
      }
      const json = await resp.json();
      const etag = resp.headers.get('ETag');
      if (etag) json.__etag = etag;
      return json;
    }

    async function loadMeta() {
      meta = await api('/api/meta');
      document.getElementById('app-title').textContent = meta.title || 'Yaahlan 智能工具 Agent';
      document.title = meta.title || 'Yaahlan Web Agent';
      renderModelOptions();
      renderExternalAgentOptions();
    }

    const MODEL_KEY = 'web_agent_model';
    const EXTERNAL_AGENTS_KEY = 'web_agent_enabled_external_agents';
    const REPLY_MODE_STORAGE_KEY = 'web_agent_reply_mode';
    const RESTART_SERVICE_SILENT_KEY = 'web_agent_settings_restart_silent';
    const RESTART_WEB_SILENT_KEY_LEGACY = 'web_agent_settings_restart_web_silent';
    const RESTART_GATEWAY_SILENT_KEY_LEGACY = 'web_agent_settings_restart_gateway_silent';
    const SERVICE_RESTART_UI = {
      web_agent: {
        btnId: 'btn-settings-restart-web-agent',
        idle: '重启 Web Agent',
        pending: 'Agent 重启中…',
        done: 'Agent 重启完成',
        fail: 'Web Agent 重启失败',
      },
      dingtalk_gateway: {
        btnId: 'btn-settings-restart-gateway',
        idle: '重启钉钉网关',
        pending: '钉钉网关重启中…',
        done: '钉钉网关重启完成',
        fail: '钉钉网关重启失败',
      },
    };
    /** @type {Map<string, ReturnType<typeof setTimeout>>} */
    const serviceRestartResetTimers = new Map();
    let serviceRestartInFlight = false;
    /** @type {Map<string, boolean>} 各会话「结果发钉钉」勾选，默认不勾选 */
    const sessionPushResultPrefs = new Map();
    const REPLY_MODES = ['concise', 'standard', 'detailed'];
    const REPLY_MODE_LABELS = {
      concise: '精简回复',
      standard: '标准回复',
      detailed: '详细回复',
    };
    const REPLY_MODE_TITLES = {
      concise: '当前：精简回复 · 点击切换为标准 / 详细',
      standard: '当前：标准回复（与原有回复一致）· 点击切换为详细 / 精简',
      detailed: '当前：详细回复 · 点击切换为精简 / 标准',
    };
    let webToastTimer = null;

    function canUseDingtalkPush() {
      return !!(currentAuthUser?.staffId || '').trim();
    }

    function getSessionPushResultPref(sessionId) {
      const sid = String(sessionId || '').trim();
      if (!sid) return false;
      return sessionPushResultPrefs.get(sid) === true;
    }

    function isPushResultChecked() {
      const main = document.getElementById('chk-push-dingtalk');
      const settings = document.getElementById('chk-push-dingtalk-settings');
      if (main) return !!main.checked;
      return !!settings?.checked;
    }

    function setPushResultChecked(checked, { updateSession = true } = {}) {
      const value = !!checked;
      ['chk-push-dingtalk', 'chk-push-dingtalk-settings'].forEach((id) => {
        const el = document.getElementById(id);
        if (el) el.checked = value;
      });
      if (updateSession && currentSessionId) {
        sessionPushResultPrefs.set(currentSessionId, value);
      }
      syncPushResultToggleUi();
    }

    function applySessionPushResultPref(sessionId) {
      setPushResultChecked(getSessionPushResultPref(sessionId), { updateSession: false });
    }

    async function syncActiveRunPushPref(checked) {
      const run = activeRuns.get(currentSessionId);
      const runId = String(run?.runId || '').trim();
      if (!runId) return;
      try {
        await api(`/api/runs/${encodeURIComponent(runId)}/push-dingtalk`, {
          method: 'PUT',
          body: JSON.stringify({ push_result_to_dingtalk: !!checked }),
        });
      } catch (err) {
        console.warn('syncActiveRunPushPref', err);
      }
    }

    function onPushResultCheckboxChange(ev) {
      const target = ev?.target;
      const checked =
        target?.type === 'checkbox' &&
        (target.id === 'chk-push-dingtalk' || target.id === 'chk-push-dingtalk-settings')
          ? !!target.checked
          : isPushResultChecked();
      setPushResultChecked(checked, { updateSession: false });
      if (currentSessionId) {
        sessionPushResultPrefs.set(currentSessionId, checked);
      }
      void syncActiveRunPushPref(checked);
      syncPushResultToggleUi();
    }

    function syncPushResultToggleUi() {
      const busy = isCurrentSessionStreaming();
      const readonly = currentSessionReadOnly || isGuestMode();
      const allowed = canUseDingtalkPush();
      const hidden = readonly || isGuestMode();
      const checked = isPushResultChecked();
      let title;
      if (!allowed) {
        title = '请先使用钉钉账号登录后再推送结果';
      } else if (busy) {
        title = checked
          ? '执行完成后将按当前勾选状态推送到钉钉私聊，可随时取消'
          : '执行完成后不会推送；可随时勾选以在结束时发送';
      } else {
        title = '执行完成后将按当前勾选状态决定是否发送到您的钉钉私聊';
      }
      [
        { wrapId: 'dingtalk-push-toggle', chkId: 'chk-push-dingtalk', hideWhenGuest: true, hideOnMobile: true },
        { wrapId: 'dingtalk-push-toggle-settings', chkId: 'chk-push-dingtalk-settings', hideWhenGuest: false },
      ].forEach(({ wrapId, chkId, hideWhenGuest, hideOnMobile }) => {
        const wrap = document.getElementById(wrapId);
        const checkbox = document.getElementById(chkId);
        if (!wrap || !checkbox) return;
        if (hideOnMobile && isWebAgentMobile()) {
          wrap.hidden = true;
        } else {
          wrap.hidden = hideWhenGuest ? hidden : isGuestMode();
        }
        if (checkbox.checked !== checked) checkbox.checked = checked;
        wrap.classList.toggle('is-checked', checked);
        wrap.classList.toggle('is-disabled', !allowed || readonly);
        checkbox.disabled = !allowed || readonly;
        wrap.title = title;
      });
    }

    function showWebToast(message, { error = false, durationMs = 3200 } = {}) {
      const el = document.getElementById('web-toast');
      if (!el) return;
      el.textContent = message || '';
      el.hidden = false;
      el.classList.toggle('is-error', !!error);
      requestAnimationFrame(() => el.classList.add('is-visible'));
      if (webToastTimer) clearTimeout(webToastTimer);
      webToastTimer = window.setTimeout(() => {
        el.classList.remove('is-visible');
        window.setTimeout(() => {
          el.hidden = true;
        }, 200);
      }, durationMs);
    }

    function syncSettingsServiceSection() {
      const section = document.getElementById('settings-service-section');
      if (!section) return;
      section.hidden = !userIsWebSuperAdmin(currentAuthUser);
    }

    function loadServiceRestartSilentPrefs() {
      const chk = document.getElementById('chk-restart-service-silent');
      if (!chk) return;
      let stored = localStorage.getItem(RESTART_SERVICE_SILENT_KEY);
      if (stored === null) {
        const webLegacy = localStorage.getItem(RESTART_WEB_SILENT_KEY_LEGACY);
        const gwLegacy = localStorage.getItem(RESTART_GATEWAY_SILENT_KEY_LEGACY);
        if (webLegacy !== null || gwLegacy !== null) {
          stored = webLegacy === '0' || gwLegacy === '0' ? '0' : '1';
        }
      }
      chk.checked = stored === null ? true : stored === '1';
    }

    function persistServiceRestartSilentPref(checked) {
      localStorage.setItem(RESTART_SERVICE_SILENT_KEY, checked ? '1' : '0');
    }

    function isServiceRestartSilent() {
      const chk = document.getElementById('chk-restart-service-silent');
      return chk ? !!chk.checked : true;
    }

    function syncServiceRestartButtonsDisabled() {
      const disabled = serviceRestartInFlight;
      document.getElementById('btn-settings-restart-web-agent')?.toggleAttribute('disabled', disabled);
      document.getElementById('btn-settings-restart-gateway')?.toggleAttribute('disabled', disabled);
    }

    function setServiceRestartButtonPhase(target, phase) {
      const cfg = SERVICE_RESTART_UI[target];
      if (!cfg) return;
      const btn = document.getElementById(cfg.btnId);
      if (!btn) return;
      btn.classList.remove('is-pending', 'is-done', 'is-error');
      if (phase === 'pending') {
        btn.textContent = cfg.pending;
        btn.classList.add('is-pending');
      } else if (phase === 'done') {
        btn.textContent = cfg.done;
        btn.classList.add('is-done');
      } else if (phase === 'error') {
        btn.textContent = cfg.fail;
        btn.classList.add('is-error');
      } else {
        btn.textContent = cfg.idle;
      }
    }

    function scheduleServiceRestartButtonIdle(target, delayMs = 4000) {
      const prev = serviceRestartResetTimers.get(target);
      if (prev) clearTimeout(prev);
      const timer = setTimeout(() => {
        serviceRestartResetTimers.delete(target);
        setServiceRestartButtonPhase(target, 'idle');
      }, delayMs);
      serviceRestartResetTimers.set(target, timer);
    }

    async function waitWebAgentRestartOnline(maxWaitMs = 90000) {
      await new Promise((resolve) => { setTimeout(resolve, 1200); });
      const deadline = Date.now() + maxWaitMs;
      let sawDown = false;
      while (Date.now() < deadline) {
        try {
          const resp = await fetch(`${API}/api/meta`, {
            credentials: 'same-origin',
            cache: 'no-store',
          });
          if (resp.ok) {
            if (sawDown) return true;
          } else {
            sawDown = true;
          }
        } catch {
          sawDown = true;
        }
        await new Promise((resolve) => { setTimeout(resolve, 1000); });
      }
      try {
        const resp = await fetch(`${API}/api/meta`, {
          credentials: 'same-origin',
          cache: 'no-store',
        });
        return resp.ok;
      } catch {
        return false;
      }
    }

    function confirmServiceRestart(target, silent) {
      if (target === 'web_agent') {
        return window.confirm(
          '确定重启 Web Agent？\n\n进行中的 Agent 任务可能被中断，页面可能短暂断开连接。',
        );
      }
      const notifyHint = silent
        ? '已勾选静默：不向钉钉群推送启停通知。'
        : '未勾选静默：将向钉钉群推送启停通知。';
      return window.confirm(
        `确定重启钉钉网关？\n\n${notifyHint}\n进行中的 @ 机器人任务可能受影响。`,
      );
    }

    async function invokeServiceRestart(target) {
      if (serviceRestartInFlight) return;
      if (!userIsWebSuperAdmin(currentAuthUser)) {
        showWebToast('仅超管可重启服务', { error: true });
        return;
      }
      const silent = isServiceRestartSilent();
      if (!confirmServiceRestart(target, silent)) return;
      serviceRestartInFlight = true;
      setServiceRestartButtonPhase(target, 'pending');
      syncServiceRestartButtonsDisabled();
      try {
        const res = await fetch('/api/admin/service/restart', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'same-origin',
          body: JSON.stringify({ target, silent }),
        });
        let data = {};
        try {
          data = await res.json();
        } catch { /* ignore */ }
        const message = String(data.message || '').trim()
          || (res.ok ? '重启已提交' : `重启失败（HTTP ${res.status}）`);
        if (!res.ok) {
          setServiceRestartButtonPhase(target, 'error');
          scheduleServiceRestartButtonIdle(target, 4500);
          showWebToast(message, { error: true });
          return;
        }
        if (target === 'web_agent') {
          const online = await waitWebAgentRestartOnline();
          if (online) {
            setServiceRestartButtonPhase(target, 'done');
            scheduleServiceRestartButtonIdle(target);
            showWebToast('Web Agent 重启完成', { durationMs: 3200 });
          } else {
            setServiceRestartButtonPhase(target, 'error');
            scheduleServiceRestartButtonIdle(target, 5000);
            showWebToast('等待 Web Agent 上线超时', { error: true });
          }
        } else {
          setServiceRestartButtonPhase(target, 'done');
          scheduleServiceRestartButtonIdle(target);
          showWebToast(message, { durationMs: 3200 });
        }
      } catch (err) {
        setServiceRestartButtonPhase(target, 'error');
        scheduleServiceRestartButtonIdle(target, 4500);
        showWebToast(err?.message || '重启请求失败', { error: true });
      } finally {
        serviceRestartInFlight = false;
        syncServiceRestartButtonsDisabled();
      }
    }

    function handleDingtalkPushResult(payload) {
      if (!payload || typeof payload !== 'object') return;
      if (payload.ok) {
        showWebToast('结果已发送到钉钉私聊');
        return;
      }
      const err = String(payload.error || '推送失败').trim();
      showWebToast(`钉钉推送失败：${err}`, { error: true, durationMs: 4200 });
    }

    function normalizeReplyMode(mode) {
      const value = String(mode || '').trim();
      return REPLY_MODES.includes(value) ? value : 'standard';
    }

    /** 详略等级图标：递增多行文本线，亮行数 = 当前档位（精简 1 / 标准 2 / 详细 3） */
    function renderReplyModeIcon(mode) {
      const level = { concise: 1, standard: 2, detailed: 3 }[normalizeReplyMode(mode)] || 2;
      const lines = [
        { x: 5, y: 6.5, w: 14 },
        { x: 5, y: 11, w: 14 },
        { x: 5, y: 15.5, w: 10 },
      ];
      return lines.map((line, index) => {
        const active = index < level;
        return `<rect x="${line.x}" y="${line.y}" width="${line.w}" height="2" rx="1" opacity="${active ? 1 : 0.24}"/>`;
      }).join('');
    }

    function syncReplyModeIcon(mode) {
      document.querySelectorAll('.reply-mode-toggle .reply-mode-icon svg').forEach((svg) => {
        svg.innerHTML = renderReplyModeIcon(mode);
      });
    }

    function loadReplyMode() {
      return normalizeReplyMode(localStorage.getItem(REPLY_MODE_STORAGE_KEY));
    }

    function saveReplyMode(mode) {
      localStorage.setItem(REPLY_MODE_STORAGE_KEY, normalizeReplyMode(mode));
    }

    function getReplyMode() {
      const btn = document.getElementById('reply-mode-toggle');
      return normalizeReplyMode(btn?.dataset.mode || loadReplyMode());
    }

    function syncReplyModeToggleUi() {
      const mode = normalizeReplyMode(loadReplyMode());
      const busy = isCurrentSessionStreaming();
      const readonly = currentSessionReadOnly || isGuestMode();
      const title = busy
        ? `思考中切换将于下轮对话生效 · ${REPLY_MODE_TITLES[mode]}`
        : REPLY_MODE_TITLES[mode];
      document.querySelectorAll('.reply-mode-toggle').forEach((btn) => {
        const inSettings = btn.id === 'reply-mode-toggle-settings';
        btn.dataset.mode = mode;
        btn.setAttribute('aria-label', REPLY_MODE_LABELS[mode]);
        const labelEl = btn.querySelector('.reply-mode-label');
        if (labelEl) labelEl.textContent = REPLY_MODE_LABELS[mode];
        btn.hidden = inSettings ? isGuestMode() : (readonly || isWebAgentMobile());
        btn.disabled = readonly;
        btn.title = title;
      });
      syncReplyModeIcon(mode);
    }

    function cycleReplyMode() {
      const btn = document.getElementById('reply-mode-toggle')
        || document.getElementById('reply-mode-toggle-settings');
      if (!btn || btn.disabled) return;
      const busy = isCurrentSessionStreaming();
      const current = normalizeReplyMode(loadReplyMode());
      const next = REPLY_MODES[(REPLY_MODES.indexOf(current) + 1) % REPLY_MODES.length];
      saveReplyMode(next);
      syncReplyModeToggleUi();
      if (busy) {
        showWebToast(`已切换为${REPLY_MODE_LABELS[next]}，下轮对话生效`);
      }
    }

    function initReplyModeControls() {
      document.querySelectorAll('.reply-mode-toggle').forEach((btn) => {
        btn.dataset.mode = loadReplyMode();
        btn.addEventListener('click', cycleReplyMode);
      });
      syncReplyModeToggleUi();
    }

    function initPushResultControls() {
      ['chk-push-dingtalk', 'chk-push-dingtalk-settings'].forEach((id) => {
        document.getElementById(id)?.addEventListener('change', onPushResultCheckboxChange);
      });
      syncPushResultToggleUi();
    }

    const DEFAULT_AGENT_MODELS = [
      { id: 'composer-2.5', label: 'Composer 2.5（默认）', description: '默认推荐，能力完整' },
    ];

    function getExternalAgentCatalog() {
      return Array.isArray(meta.externalAgents) ? meta.externalAgents : [];
    }

    function loadStoredEnabledExternalAgents() {
      try {
        const raw = localStorage.getItem(EXTERNAL_AGENTS_KEY);
        if (!raw) return null;
        const parsed = JSON.parse(raw);
        return Array.isArray(parsed) ? parsed.map((item) => String(item || '').trim()).filter(Boolean) : null;
      } catch (_) {
        return null;
      }
    }

    function getDefaultEnabledExternalAgents() {
      return getExternalAgentCatalog()
        .filter((item) => item.defaultEnabled)
        .map((item) => String(item.id || '').trim())
        .filter(Boolean);
    }

    function getEnabledExternalAgents() {
      const allowed = new Set(
        getExternalAgentCatalog().map((item) => String(item.id || '').trim()).filter(Boolean),
      );
      const stored = loadStoredEnabledExternalAgents();
      const source = stored ?? getDefaultEnabledExternalAgents();
      return source.filter((id) => allowed.has(id));
    }

    function saveEnabledExternalAgents(ids) {
      localStorage.setItem(EXTERNAL_AGENTS_KEY, JSON.stringify(ids));
    }

    function triggerExternalAgentFlash(item) {
      if (!item) return;
      item.classList.remove('external-agent-flash');
      void item.offsetWidth;
      item.classList.add('external-agent-flash');
      window.setTimeout(() => item.classList.remove('external-agent-flash'), 540);
    }

    function renderExternalAgentOptions() {
      const container = document.getElementById('external-agent-list');
      if (!container) return;
      const agents = getExternalAgentCatalog();
      const enabled = new Set(getEnabledExternalAgents());
      if (!agents.length) {
        container.innerHTML = '<p class="settings-hint">暂无可配置的外部 Agent。</p>';
        return;
      }
      const openIcon = '<svg viewBox="0 0 24 24" stroke-width="2" aria-hidden="true"><path d="M14 3h7v7"/><path d="M10 14 21 3"/><path d="M21 14v7h-7"/><path d="M3 10V3h7"/></svg>';
      container.innerHTML = agents.map((item) => {
        const id = String(item.id || '').trim();
        const label = escapeHtml(String(item.label || id));
        const url = String(item.url || '').trim();
        const checked = enabled.has(id) ? ' checked' : '';
        const openLink = url
          ? `<a class="external-agent-open" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer" title="在新标签页打开 ${label}">打开${openIcon}</a>`
          : '';
        return `
          <div class="external-agent-item${checked ? ' is-checked' : ''}">
            <label class="external-agent-check" for="external-agent-${escapeHtml(id)}">
              <input type="checkbox" id="external-agent-${escapeHtml(id)}" data-agent-id="${escapeHtml(id)}"${checked} />
              <span class="external-agent-name">${label}</span>
            </label>
            ${openLink}
          </div>`;
      }).join('');
      container.querySelectorAll('input[type="checkbox"]').forEach((input) => {
        input.addEventListener('change', () => {
          const item = input.closest('.external-agent-item');
          if (input.checked) {
            item?.classList.add('is-checked');
            triggerExternalAgentFlash(item);
          } else {
            item?.classList.remove('is-checked');
          }
          const next = Array.from(container.querySelectorAll('input[type="checkbox"]:checked'))
            .map((el) => el.dataset.agentId)
            .filter(Boolean);
          saveEnabledExternalAgents(next);
        });
      });
    }

    function getDefaultModelId() {
      return String(meta.defaultAgentModel || DEFAULT_AGENT_MODELS[0].id).trim();
    }

    function getModelDisplayLabel(item) {
      const id = String(item?.id || '').trim();
      const base = String(item?.label || id).trim();
      if (!id) return base;
      if (id === getDefaultModelId() && !base.includes('默认')) {
        return `${base}（默认）`;
      }
      return base;
    }

    function getModelCatalog() {
      const models = Array.isArray(meta.agentModels) ? meta.agentModels : [];
      return models.length ? models : DEFAULT_AGENT_MODELS;
    }

    function closeModelPicker() {
      const menu = document.getElementById('model-picker-menu');
      const trigger = document.getElementById('model-picker-trigger');
      if (menu && !menu.hidden) {
        setDropdownAnimated(menu, false).then(() => {
          if (trigger) trigger.setAttribute('aria-expanded', 'false');
        });
        return;
      }
      if (menu) menu.hidden = true;
      if (trigger) trigger.setAttribute('aria-expanded', 'false');
    }

    function toggleModelPicker() {
      const menu = document.getElementById('model-picker-menu');
      const trigger = document.getElementById('model-picker-trigger');
      if (!menu || !trigger) return;
      const willOpen = menu.hidden;
      if (willOpen) {
        renderModelOptions();
        setDropdownAnimated(menu, true);
        trigger.setAttribute('aria-expanded', 'true');
      } else {
        closeModelPicker();
      }
    }

    function getSelectedModel() {
      const stored = (localStorage.getItem(MODEL_KEY) || '').trim();
      const models = getModelCatalog();
      const allowed = new Set(models.map((item) => String(item.id || '').trim()).filter(Boolean));
      const fallback = String(meta.defaultAgentModel || DEFAULT_AGENT_MODELS[0].id);
      if (stored && allowed.has(stored)) return stored;
      if (allowed.has(fallback)) return fallback;
      return models[0]?.id || fallback;
    }

    function renderModelOptions() {
      const menu = document.getElementById('model-picker-menu');
      const label = document.getElementById('model-picker-label');
      if (!menu) return;
      const models = getModelCatalog();
      const current = getSelectedModel();
      menu.innerHTML = models.map((item) => {
        const id = String(item.id || '').trim();
        const name = getModelDisplayLabel(item);
        const active = id === current ? ' active' : '';
        return `<button type="button" class="model-picker-item${active}" data-model-id="${escapeHtml(id)}" role="option" aria-selected="${id === current ? 'true' : 'false'}">${escapeHtml(name)}</button>`;
      }).join('');
      if (label) {
        const currentItem = models.find((entry) => String(entry.id || '') === current);
        label.textContent = currentItem ? getModelDisplayLabel(currentItem) : current;
      }
      localStorage.setItem(MODEL_KEY, current);
    }

    function applyModelSelection(modelId) {
      const next = String(modelId || '').trim();
      if (!next) return;
      localStorage.setItem(MODEL_KEY, next);
      document.querySelectorAll('.model-picker-item').forEach((btn) => {
        const active = btn.dataset.modelId === next;
        btn.classList.toggle('active', active);
        btn.setAttribute('aria-selected', active ? 'true' : 'false');
      });
      const label = document.getElementById('model-picker-label');
      const models = getModelCatalog();
      const item = models.find((entry) => String(entry.id || '') === next);
      if (label) label.textContent = item ? getModelDisplayLabel(item) : next;
      closeModelPicker();
    }

    function isCurrentSessionStreaming() {
      return activeRuns.has(currentSessionId);
    }

    function getMessagesEl() {
      return document.getElementById('messages');
    }

    function isMessagesNearBottom(container, threshold = MESSAGES_SCROLL_NEAR_BOTTOM_PX) {
      if (!container) return true;
      return container.scrollHeight - container.scrollTop - container.clientHeight <= threshold;
    }

    function syncMessagesPinnedState(container) {
      const el = container || getMessagesEl();
      if (!el) return;
      messagesPinnedToBottom = isMessagesNearBottom(el);
      updateScrollToBottomBtn();
    }

    function captureMessagesScrollFromBottom() {
      const container = getMessagesEl();
      if (!container || messagesPinnedToBottom) return null;
      return container.scrollHeight - container.scrollTop;
    }

    function restoreMessagesScrollFromBottom(fromBottom) {
      const container = getMessagesEl();
      if (!container || fromBottom == null) return;
      container.scrollTop = Math.max(0, container.scrollHeight - fromBottom);
      syncMessagesPinnedState(container);
    }

    function scrollMessagesToBottom(options = {}) {
      const { force = false } = options;
      const container = getMessagesEl();
      if (!container) return;
      if (!force && !messagesPinnedToBottom) return;
      if (force) messagesPinnedToBottom = true;

      container.scrollTop = container.scrollHeight;
      updateScrollToBottomBtn();
    }

    function updateScrollToBottomBtn() {
      const btn = document.getElementById('btn-scroll-to-bottom');
      const container = getMessagesEl();
      if (!btn || !container) return;
      const hasMessages = !container.querySelector('.empty-state') && container.children.length > 0;
      const show = hasMessages && !messagesPinnedToBottom;
      btn.toggleAttribute('hidden', !show);
      btn.classList.toggle('is-visible', show);
      btn.setAttribute('aria-hidden', show ? 'false' : 'true');
    }

    let scrollMessagesRaf = 0;
    function scheduleScrollMessagesToBottom(options = {}) {
      cancelAnimationFrame(scrollMessagesRaf);
      const run = () => {
        scrollMessagesRaf = 0;
        scrollMessagesToBottom(options);
      };
      if (isCurrentSessionStreaming() && !options.force) {
        scrollMessagesRaf = requestAnimationFrame(run);
        return;
      }
      scrollMessagesToBottom(options);
      scrollMessagesRaf = requestAnimationFrame(() => {
        scrollMessagesToBottom(options);
        requestAnimationFrame(() => scrollMessagesToBottom(options));
      });
    }

    function bindMessagesMediaLoadScroll(container) {
      if (!container) return;
      container.querySelectorAll('img').forEach((img) => {
        if (img.complete) return;
        img.addEventListener('load', () => {
          if (messagesPinnedToBottom) scrollMessagesToBottom();
        }, { once: true });
      });
    }

    function setupMessagesScrollTracking() {
      const container = getMessagesEl();
      if (!container || container.dataset.scrollTrackBound) return;
      container.dataset.scrollTrackBound = '1';
      let persistScrollRaf = 0;
      container.addEventListener('scroll', () => {
        syncMessagesPinnedState(container);
        maybeAutoLoadOlderMessages(container);
        if (!currentSessionId) return;
        cancelAnimationFrame(persistScrollRaf);
        persistScrollRaf = requestAnimationFrame(() => {
          rememberSessionScrollState(currentSessionId, {
            pinnedToBottom: messagesPinnedToBottom,
            fromBottom: messagesPinnedToBottom ? null : (container.scrollHeight - container.scrollTop),
          });
        });
      }, { passive: true });
      container.addEventListener('wheel', (event) => {
        if (event.deltaY < 0) {
          messagesPinnedToBottom = false;
          updateScrollToBottomBtn();
        }
      }, { passive: true });
      document.getElementById('btn-scroll-to-bottom')?.addEventListener('click', () => {
        scheduleScrollMessagesToBottom({ force: true });
      });
      if (!container.dataset.contextMenuBound) {
        container.dataset.contextMenuBound = '1';
        container.addEventListener('contextmenu', (event) => {
          if (!currentSessionId) return;
          if (event.target.closest('.msg-file-link, .msg-images a, button, a')) return;
          const userMsg = event.target.closest('.msg.user');
          event.preventDefault();
          showMessagesContextMenu(event.clientX, event.clientY, {
            copyTarget: userMsg || null,
          });
        });
      }
      if (typeof ResizeObserver !== 'undefined') {
        let resizeRaf = 0;
        const observer = new ResizeObserver(() => {
          if (!messagesPinnedToBottom) return;
          const el = getMessagesEl();
          if (!el || !isMessagesNearBottom(el)) {
            messagesPinnedToBottom = false;
            updateScrollToBottomBtn();
            return;
          }
          cancelAnimationFrame(resizeRaf);
          resizeRaf = requestAnimationFrame(() => scrollMessagesToBottom());
        });
        observer.observe(container);
      }
    }

    function renderRunStatusHtml(status) {
      const view = runStatusForRender(status);
      const lines = [];
      if (view.ack) {
        lines.push(`<div class="run-status-line run-status-ack">${escapeHtml(view.ack)}</div>`);
      }
      if (view.batch) {
        lines.push(`<div class="run-status-line run-status-batch">${escapeHtml(view.batch)}</div>`);
      }
      if (view.external) {
        lines.push(`<div class="run-status-line run-status-external">${escapeHtml(view.external)}</div>`);
      }
      if (view.elapsed) {
        lines.push(`<div class="run-status-line run-status-elapsed">${escapeHtml(view.elapsed)}</div>`);
      }
      return lines.join('');
    }

    function renderRunStatusEl(statusEl, status) {
      if (!statusEl) return;
      const html = renderRunStatusHtml(status);
      if (statusEl.innerHTML === html) return;
      statusEl.innerHTML = html;
    }

    function ensureStreamingShell(sessionId) {
      const run = activeRuns.get(sessionId);
      if (run?.shellEl?.isConnected) {
        if (isStreamingShellFinalized(run.shellEl)) {
          run.shellEl = null;
        } else {
          removeAssistantShareButton(run.shellEl);
          run.shellEl.classList.add('streaming');
          syncMsgTerminalButton(run.shellEl, sessionId);
          return run.shellEl;
        }
      }
      const orphan = findOrphanStreamingShell(sessionId);
      if (orphan) {
        removeAssistantShareButton(orphan);
        orphan.classList.add('streaming');
        if (run) run.shellEl = orphan;
        syncMsgTerminalButton(orphan, sessionId);
        return orphan;
      }
      const container = document.getElementById('messages');
      if (container.querySelector('.empty-state')) dismissEmptyState(container);
      document.getElementById('typing-indicator')?.remove();
      const el = document.createElement('div');
      el.className = 'msg assistant streaming';
      el.innerHTML = `
        ${buildMsgLabelHtml('Agent', new Date().toISOString(), { role: 'assistant' })}
        <div class="run-status"></div>
        <div class="msg-body"></div>`;
      container.appendChild(el);
      if (messagesPinnedToBottom) scrollMessagesToBottom();
      if (run) {
        run.shellEl = el;
        el.dataset.streamSessionId = sessionId;
        renderRunStatusEl(el.querySelector('.run-status'), run.status);
      }
      syncMsgTerminalButton(el, sessionId);
      return el;
    }

    function shellSessionId(shell) {
      const direct = String(shell?.dataset?.streamSessionId || '').trim();
      if (direct) return direct;
      for (const [sid, run] of activeRuns.entries()) {
        if (run.shellEl === shell) return sid;
      }
      return currentSessionId;
    }

    function updateRunStatus(sessionId, patch) {
      const run = activeRuns.get(sessionId);
      if (!run) return;
      run.status = { ...run.status, ...patch };
      if (sessionId !== currentSessionId) return;
      const shell = run.shellEl || ensureStreamingShell(sessionId);
      const statusEl = shell.querySelector('.run-status');
      const prevHtml = statusEl ? statusEl.innerHTML : '';
      renderRunStatusEl(statusEl, run.status);
      const layoutChanged = statusEl && statusEl.innerHTML !== prevHtml
        && (patch.ack || patch.batch || patch.external);
      if (layoutChanged && messagesPinnedToBottom) {
        scheduleScrollMessagesToBottom();
      }
    }

    function clearRunStatus(sessionId, shellEl = null) {
      const run = activeRuns.get(sessionId);
      const shell = shellEl || run?.shellEl;
      if (!shell?.isConnected) return;
      const statusEl = shell.querySelector('.run-status');
      if (statusEl) statusEl.innerHTML = '';
      shell.classList.remove('streaming');
    }

    function sessionOwnerInfo(item) {
      if (!item) return { id: '', label: '', avatarUrl: '' };
      if (item.source === 'dingtalk') {
        const id = (item.dingtalk_owner_id || '').trim();
        const label = (item.dingtalk_owner || item.dingtalk_label || '').trim();
        const avatarUrl = (item.owner_avatar_url || '').trim();
        return { id, label, avatarUrl };
      }
      const id = (item.web_owner_id || '').trim();
      const label = (item.web_owner || item.web_owner_label || '').trim();
      const avatarUrl = (item.owner_avatar_url || '').trim();
      return { id, label, avatarUrl };
    }

    function seedUserAvatarCacheFromSessions(sessions) {
      (sessions || []).forEach((s) => {
        const info = sessionOwnerInfo(s);
        if (info.id && info.avatarUrl) userAvatarCache.set(info.id, info.avatarUrl);
      });
    }

    function seedUserAvatarCacheFromStaffUsers(users) {
      (users || []).forEach((user) => {
        const sid = String(user?.staffId || '').trim();
        const url = String(user?.avatarUrl || '').trim();
        if (sid && url) userAvatarCache.set(sid, url);
      });
    }

    function buildGroupPickerAvatarHtml() {
      return `<span class="name-avatar name-avatar-fallback name-avatar-group" aria-hidden="true">${wrapAvatarGlyph('群')}</span>`;
    }

    function buildStaffPickerAvatarHtml(user) {
      const staffId = String(user?.staffId || user?.id || '').trim();
      const label = String(user?.displayName || '未知用户').trim();
      return buildNameAvatarHtml({
        staffId,
        label,
        avatarUrl: String(user?.avatarUrl || '').trim(),
      });
    }

    function sessionOwnerName(item) {
      const info = sessionOwnerInfo(item);
      return publicDisplayName(info.label || info.id || '');
    }

    function sessionHasCustomTitle(item) {
      return Boolean((item?.custom_title || '').trim());
    }

    function sessionCustomTitleEditBtnHtml() {
      return '<button type="button" class="session-custom-title-edit" title="修改标题" aria-label="修改标题"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 17.25V21h3.75L17.81 9.94l-3.75-3.75L3 17.25zM20.71 7.04a1.003 1.003 0 0 0 0-1.42l-2.34-2.34a1.003 1.003 0 0 0-1.42 0l-1.83 1.83 3.75 3.75 1.84-1.82z"/></svg></button>';
    }

    function loadStoredSessionScopeFilter() {
      const raw = localStorage.getItem(SESSION_SCOPE_STORAGE_KEY);
      if (!raw) return null;
      const value = raw.trim().toLowerCase();
      return value === 'all' ? 'all' : 'mine';
    }

    function defaultSessionScopeForAuth() {
      if (!currentAuthUser) return 'all';
      return loadStoredSessionScopeFilter() ?? 'mine';
    }

    function applySessionScopeForAuth() {
      sessionScopeFilter = defaultSessionScopeForAuth();
      syncSessionScopeButtonUi();
    }

    function saveSessionScopeFilter(scope) {
      sessionScopeFilter = scope === 'mine' ? 'mine' : 'all';
      if (currentAuthUser) {
        localStorage.setItem(SESSION_SCOPE_STORAGE_KEY, sessionScopeFilter);
      }
      syncSessionScopeButtonUi();
    }

    function sessionListScrollStorageKey() {
      const staffId = (currentAuthUser?.staffId || 'guest').trim() || 'guest';
      return `${SESSION_LIST_SCROLL_STORAGE_PREFIX}:${staffId}`;
    }

    function sessionListMaxScroll(list) {
      return Math.max(0, list.scrollHeight - list.clientHeight);
    }

    function sessionListScrollRatio(list) {
      const max = sessionListMaxScroll(list);
      if (max <= 0) return 0;
      return Math.max(0, Math.min(1, list.scrollTop / max));
    }

    function applySessionListScrollRatio(list, ratio) {
      const max = sessionListMaxScroll(list);
      list.scrollTop = Math.max(0, Math.min(max, ratio * max));
    }

    function preserveSessionListScrollFromBottom(list) {
      if (!list) return;
      const distanceFromBottom = list.scrollHeight - list.scrollTop;
      requestAnimationFrame(() => {
        list.scrollTop = Math.max(0, list.scrollHeight - distanceFromBottom);
        updateSessionListScrollToTopBtn();
      });
    }

    function loadSessionListScrollByScope() {
      try {
        const raw = localStorage.getItem(sessionListScrollStorageKey());
        if (!raw) return;
        const parsed = JSON.parse(raw);
        const mine = Number(parsed?.mine);
        const all = Number(parsed?.all);
        if (Number.isFinite(mine) && mine >= 0 && mine <= 1) sessionListScrollByScope.mine = mine;
        if (Number.isFinite(all) && all >= 0 && all <= 1) sessionListScrollByScope.all = all;
      } catch { /* ignore */ }
    }

    function saveSessionListScrollByScope() {
      try {
        localStorage.setItem(sessionListScrollStorageKey(), JSON.stringify({
          mine: sessionListScrollByScope.mine,
          all: sessionListScrollByScope.all,
        }));
      } catch { /* quota / private mode */ }
    }

    function currentSessionListScopeKey() {
      return sessionScopeFilter === 'mine' ? 'mine' : 'all';
    }

    function rememberSessionListScrollForCurrentScope() {
      const list = document.getElementById('session-list');
      if (!list) return;
      sessionListScrollByScope[currentSessionListScopeKey()] = sessionListScrollRatio(list);
      saveSessionListScrollByScope();
    }

    function sessionListScrollForCurrentScope() {
      return sessionListScrollByScope[currentSessionListScopeKey()] || 0;
    }

    const SESSION_LIST_SCROLL_TOP_THRESHOLD = 48;

    function updateSessionListScrollToTopBtn() {
      const btn = document.getElementById('btn-session-scroll-top');
      const list = document.getElementById('session-list');
      if (!btn || !list) return;
      const hasItems = Boolean(list.querySelector('.session-item[data-id]'));
      const show = hasItems && list.scrollTop > SESSION_LIST_SCROLL_TOP_THRESHOLD;
      btn.toggleAttribute('hidden', !show);
      btn.classList.toggle('is-visible', show);
      btn.setAttribute('aria-hidden', show ? 'false' : 'true');
    }

    function scrollSessionListToTop(options = {}) {
      const list = document.getElementById('session-list');
      if (!list) return;
      const behavior = options.smooth === false ? 'auto' : 'smooth';
      list.scrollTo({ top: 0, behavior });
      sessionListScrollByScope[currentSessionListScopeKey()] = 0;
      saveSessionListScrollByScope();
      updateSessionListScrollToTopBtn();
    }

    let sessionListScrollSaveTimer = 0;
    function setupSessionListScrollTracking() {
      const list = document.getElementById('session-list');
      if (!list || list.dataset.scopeScrollBound) return;
      list.dataset.scopeScrollBound = '1';
      list.addEventListener('scroll', () => {
        updateSessionListScrollToTopBtn();
        clearTimeout(sessionListScrollSaveTimer);
        sessionListScrollSaveTimer = window.setTimeout(() => {
          rememberSessionListScrollForCurrentScope();
        }, 120);
      }, { passive: true });
      document.getElementById('btn-session-scroll-top')?.addEventListener('click', () => {
        scrollSessionListToTop();
      });
    }

    function sessionMatchesScope(item) {
      if (sessionScopeFilter !== 'mine') return true;
      if (isGuestMode()) return false;
      const viewerId = (currentAuthUser?.staffId || '').trim();
      if (!viewerId) return false;
      if (item?.is_mine === true) return true;
      if (item?.is_collaborator === true) return true;
      const ownerId = item?.source === 'dingtalk'
        ? (item.dingtalk_owner_id || '').trim()
        : (item.web_owner_id || '').trim();
      return !!ownerId && ownerId === viewerId;
    }

    function sessionListPrefixBadgesHtml(s) {
      let html = '';
      if (s?.open_api_session) {
        html += '<span class="session-source">API</span>';
      }
      if (s?.source === 'dingtalk') {
        html += '<span class="session-source">钉钉</span>';
      }
      const badge = (s?.shared_conversation_badge || '').trim();
      if (badge === '主建' || badge === '共建') {
        const cls = badge === '主建' ? 'session-collab-badge is-owner' : 'session-collab-badge';
        html += `<span class="${cls}">${badge}</span>`;
      }
      return html;
    }

    function applySessionScopeFilter(list) {
      if (sessionScopeFilter !== 'mine') return list.slice();
      return list.filter(sessionMatchesScope);
    }

    function syncSessionsCacheFromAll() {
      sessionsCache = applySessionScopeFilter(sessionsCacheAll);
      sortSessionsCache();
    }

    function syncSessionScopeButtonUi() {
      const btn = document.getElementById('btn-session-scope');
      if (!btn) return;
      if (isGuestMode()) {
        btn.hidden = true;
        return;
      }
      btn.hidden = false;
      const isMine = sessionScopeFilter === 'mine';
      const scopeText = btn.querySelector('.session-scope-text');
      const scopeLabel = isMine ? '我的' : '全部';
      if (scopeText) scopeText.textContent = scopeLabel;
      else btn.textContent = scopeLabel;
      btn.classList.toggle('is-mine', isMine);
      btn.title = isMine
        ? '我的历史会话 · 点击切换为全部'
        : '全部历史会话 · 点击切换为我的';
      btn.setAttribute('aria-label', isMine ? '筛选：我的历史会话' : '筛选：全部历史会话');
      btn.setAttribute('aria-busy', sessionScopeSwitchPending ? 'true' : 'false');
      document.querySelector('.left-panel')?.classList.toggle('session-scope-mine', isMine);
    }

    async function ensureCurrentSessionMatchesScope() {
      if (!currentSessionId) return;
      const item = getSessionFromCache(currentSessionId);
      if (item && sessionMatchesScope(item)) {
        syncSessionReadOnly(currentSessionId);
        return;
      }
      // 会话在缓存中但被「我的/全部」筛掉时仍切到可见列表首项；未进侧栏列表（如 message_count=0）则保持当前会话
      if (item && !sessionMatchesScope(item)) {
        if (isWebAgentMobile()) {
          syncSessionReadOnly(currentSessionId);
          return;
        }
        const visible = sessionsCache;
        if (visible.length) {
          await activateSession(visible[0].id, { force: true });
          return;
        }
        currentSessionId = '';
        currentSessionReadOnly = false;
        clearPersistedSessionId();
        showEmptyState({ animate: false });
        syncSessionReadOnly('');
        return;
      }
      syncSessionReadOnly(currentSessionId);
    }

    function refreshSessionListForScopeSwitch() {
      syncSessionsCacheFromAll();
      enrichSessionsCacheRelativeTimes(sessionsCache);
      const list = document.getElementById('session-list');
      if (!sessionsCache.length) {
        renderSessionList({ rememberScroll: false });
      } else if (!reconcileSessionListFromCache(sessionsCache)) {
        renderSessionList({ rememberScroll: false });
      } else if (list) {
        applySessionListScrollRatio(list, sessionListScrollForCurrentScope());
        updateSessionListScrollToTopBtn();
        scheduleIdleSessionMessagesPrefetchDebounced();
      }
      lastSessionListKey = sessionListPatchKey(sessionsCache);
    }

    function toggleSessionScopeFilter() {
      if (isGuestMode()) return;
      if (sessionScopeSwitchPending) return;
      rememberSessionListScrollForCurrentScope();
      const nextScope = sessionScopeFilter === 'mine' ? 'all' : 'mine';
      saveSessionScopeFilter(nextScope);
      trackEvent('session_scope_change', { scope: nextScope });
      if (sessionSearchQuery.trim()) {
        sessionsListEtag = '';
        sessionScopeSwitchPending = true;
        syncSessionScopeButtonUi();
        showSessionListLoadingUi({ forceOverlay: isWebAgentMobile() });
        void (async () => {
          try {
            await loadSessions({ force: true, scopeSwitch: true });
            if (!isWebAgentMobile()) {
              await ensureCurrentSessionMatchesScope();
            }
          } catch (err) {
            console.error('loadSessions', err);
            syncSessionsCacheFromAll();
            enrichSessionsCacheRelativeTimes(sessionsCache);
            renderSessionList({ rememberScroll: false, resetScroll: true });
            lastSessionListKey = sessionListPatchKey(sessionsCache);
          } finally {
            sessionScopeSwitchPending = false;
            syncSessionScopeButtonUi();
            hideSessionListLoadingUi();
          }
        })();
        return;
      }
      if (isWebAgentMobile()) {
        sessionScopeSwitchPending = true;
        syncSessionScopeButtonUi();
        const scopeSeq = ++mobileSessionScopeSwitchSeq;
        showSessionListLoadingUi();
        scheduleMessagesRenderYield(() => {
          if (scopeSeq !== mobileSessionScopeSwitchSeq) return;
          try {
            refreshSessionListForScopeSwitch();
          } finally {
            sessionScopeSwitchPending = false;
            syncSessionScopeButtonUi();
            hideSessionListLoadingUi();
          }
        });
        return;
      }
      const applyScopeListUpdate = () => {
        refreshSessionListForScopeSwitch();
        ensureCurrentSessionMatchesScope().catch((err) => {
          console.error('ensureCurrentSessionMatchesScope', err);
        });
      };
      requestAnimationFrame(() => {
        requestAnimationFrame(applyScopeListUpdate);
      });
    }

    function markSessionListActive(sessionId) {
      const list = document.getElementById('session-list');
      if (!list) return false;
      const items = list.querySelectorAll('.session-item[data-id]');
      if (!items.length) return false;
      const sid = String(sessionId || '').trim();
      items.forEach((el) => {
        el.classList.toggle('active', el.dataset.id === sid);
      });
      syncSessionReadOnly(sid);
      return true;
    }

    function formatSessionRelativeTime(iso) {
      const raw = String(iso || '').trim();
      if (!raw) return '';
      try {
        const dt = new Date(raw);
        if (Number.isNaN(dt.getTime())) return '';
        const minutes = Math.floor((Date.now() - dt.getTime()) / 60000);
        if (minutes < 1) return '刚刚';
        if (minutes < 60) return `${minutes} 分钟前`;
        const hours = Math.floor(minutes / 60);
        if (hours < 24) return `${hours} 小时前`;
        const days = Math.floor(hours / 24);
        if (days < 30) return `${days} 天前`;
        return dt.toISOString().slice(0, 10);
      } catch {
        return '';
      }
    }

    function enrichSessionsCacheRelativeTimes(sessions) {
      if (!Array.isArray(sessions)) return;
      sessions.forEach((s) => {
        if (!s?.updated_at) return;
        s.relative_time = formatSessionRelativeTime(s.updated_at);
      });
    }

    function patchSessionCacheEntry(sessionId, patch) {
      const sid = String(sessionId || '').trim();
      if (!sid || !patch || typeof patch !== 'object') return false;
      let changed = false;
      const apply = (arr) => {
        if (!Array.isArray(arr)) return;
        const idx = arr.findIndex((item) => item.id === sid);
        if (idx < 0) return;
        arr[idx] = { ...arr[idx], ...patch };
        changed = true;
      };
      apply(sessionsCache);
      apply(sessionsCacheAll);
      if (changed) {
        const merged = sessionsCacheById.get(sid) || getSessionFromCache(sid);
        if (merged) upsertSessionCacheById({ ...merged, ...patch });
      }
      return changed;
    }

    function refreshSessionListAfterRunEnd(sessionId) {
      const sid = String(sessionId || '').trim();
      if (!sid) return;
      const nowIso = new Date().toISOString();
      patchSessionCacheEntry(sid, {
        running: false,
        updated_at: nowIso,
        relative_time: formatSessionRelativeTime(nowIso),
      });
      sortSessionsCache();
      syncSessionListFromCache();
    }

    function syncSessionListFromCache() {
      enrichSessionsCacheRelativeTimes(sessionsCache);
      if (!sessionsCache.length) {
        renderSessionList();
      } else if (!reconcileSessionListFromCache(sessionsCache)) {
        renderSessionList();
      }
      lastSessionListKey = sessionListPatchKey(sessionsCache);
    }

    function sessionListPatchKey(sessions) {
      if (!Array.isArray(sessions) || !sessions.length) return '';
      return sessions.map((s) => [
        s.id,
        s.title || '',
        s.message_count || 0,
        sessionIsRunning(s) ? 1 : 0,
        s.pinned ? 1 : 0,
        s.updated_at || '',
        s.messages_mtime || 0,
        sessionOwnerInfo(s).id || '',
        (s.web_collaborator_ids || []).join(','),
        s.shared_conversation_badge || '',
        s.is_collaborator ? 1 : 0,
        s.read_only ? 1 : 0,
        s.open_api_session ? 1 : 0,
      ].join('|')).join('\n');
    }

    function sessionRelativeTimeLabel(s) {
      return formatSessionRelativeTime(s?.updated_at) || String(s?.relative_time || '').trim();
    }

    function buildSessionMetaHtml(s) {
      const ownerInfo = sessionOwnerInfo(s);
      const ownerName = sessionOwnerName(s);
      const ownerLine = ownerName
        ? `<span class="session-owner-line" data-staff-id="${escapeHtml(ownerInfo.id)}">${buildNameAvatarHtml({
          staffId: ownerInfo.id,
          label: ownerName,
          role: 'user',
          avatarUrl: ownerInfo.avatarUrl,
          eager: true,
        })}<span class="session-owner">${escapeHtml(ownerName)}</span></span><span class="session-meta-sep"> · </span>`
        : '';
      const rel = sessionRelativeTimeLabel(s);
      const relPart = rel
        ? `<span class="session-meta-relative">${escapeHtml(rel)}</span><span class="session-meta-sep"> · </span>`
        : '';
      const running = sessionIsRunning(s);
      const runningPart = running
        ? `<span class="session-meta-sep"> · </span><span class="session-meta-running">思考中</span>`
        : '';
      return `${ownerLine}${relPart}<span class="session-meta-count">${s.message_count || 0} 条</span>${runningPart}`;
    }

    function ensureSessionOwnerAvatar(ownerLineEl, ownerInfo, ownerName) {
      const sid = (ownerInfo.id || '').trim();
      if (!sid || !ownerLineEl) return;
      const existing = ownerLineEl.querySelector('img.name-avatar[data-staff-id], .name-avatar-fallback[data-staff-id]');
      const url = String(ownerInfo.avatarUrl || '').trim() || userAvatarCache.get(sid) || '';
      if (existing?.tagName === 'IMG' && (existing.dataset.staffId || '').trim() === sid) {
        bindAvatarImage(existing, ownerName);
        if (url && existing.getAttribute('src') !== url) {
          existing.setAttribute('src', url);
        } else if (!url || userAvatarNoPhoto.has(sid)) {
          applyAvatarFallback(existing, ownerName);
        }
        return;
      }
      if (!existing) {
        const avatarWrap = document.createElement('span');
        avatarWrap.innerHTML = buildNameAvatarHtml({
          staffId: sid,
          label: ownerName,
          role: 'user',
          avatarUrl: url,
          eager: true,
        }).trim();
        const avatarEl = avatarWrap.firstElementChild;
        if (avatarEl) ownerLineEl.insertBefore(avatarEl, ownerLineEl.firstChild);
      }
      if (url && existing?.classList?.contains('name-avatar-fallback')) {
        hydrateAvatars(ownerLineEl);
      }
    }

    function patchSessionMetaEl(metaEl, s) {
      if (!metaEl || !s) return;
      if (!metaEl.querySelector('.session-meta-count')) {
        metaEl.innerHTML = buildSessionMetaHtml(s);
        hydrateAvatars(metaEl);
        return;
      }
      const ownerInfo = sessionOwnerInfo(s);
      const ownerName = sessionOwnerName(s);
      const ownerId = (ownerInfo.id || '').trim();
      let ownerLineEl = metaEl.querySelector('.session-owner-line');
      if (!ownerName) {
        if (ownerLineEl) {
          const sep = ownerLineEl.nextElementSibling;
          ownerLineEl.remove();
          if (sep?.classList?.contains('session-meta-sep')) sep.remove();
        }
      } else {
        const needRebuildOwner = !ownerLineEl
          || (ownerLineEl.dataset.staffId || '').trim() !== ownerId;
        if (needRebuildOwner) {
          metaEl.innerHTML = buildSessionMetaHtml(s);
          hydrateAvatars(metaEl);
          return;
        }
        const ownerSpan = ownerLineEl.querySelector('.session-owner');
        if (ownerSpan && ownerSpan.textContent !== ownerName) {
          ownerSpan.textContent = ownerName;
        }
        ensureSessionOwnerAvatar(ownerLineEl, ownerInfo, ownerName);
      }

      const rel = sessionRelativeTimeLabel(s);
      let relEl = metaEl.querySelector('.session-meta-relative');
      if (rel) {
        if (!relEl) {
          metaEl.innerHTML = buildSessionMetaHtml(s);
          hydrateAvatars(metaEl);
          return;
        }
        if (relEl.textContent !== rel) relEl.textContent = rel;
      } else if (relEl) {
        const sep = relEl.nextElementSibling;
        relEl.remove();
        if (sep?.classList?.contains('session-meta-sep')) sep.remove();
      }

      const countEl = metaEl.querySelector('.session-meta-count');
      const countText = `${s.message_count || 0} 条`;
      if (!countEl) {
        metaEl.innerHTML = buildSessionMetaHtml(s);
        hydrateAvatars(metaEl);
        return;
      }
      if (countEl.textContent !== countText) countEl.textContent = countText;

      let runningEl = metaEl.querySelector('.session-meta-running');
      const running = sessionIsRunning(s);
      if (running) {
        if (!runningEl) {
          const sep = document.createElement('span');
          sep.className = 'session-meta-sep';
          sep.textContent = ' · ';
          runningEl = document.createElement('span');
          runningEl.className = 'session-meta-running';
          runningEl.textContent = '思考中';
          metaEl.appendChild(sep);
          metaEl.appendChild(runningEl);
        }
      } else if (runningEl) {
        const sep = runningEl.previousElementSibling;
        if (sep?.classList?.contains('session-meta-sep')) sep.remove();
        runningEl.remove();
      }
    }

    function buildSessionListItemElement(s) {
      const el = document.createElement('div');
      el.className = 'session-item' + (s.id === currentSessionId ? ' active' : '');
      if (s.pinned) el.classList.add('is-pinned');
      el.dataset.id = s.id;
      const sourceBadge = sessionListPrefixBadgesHtml(s);
      const pinIcon = s.pinned
        ? `<button type="button" class="session-pin-icon session-pin-unpin" title="取消置顶" aria-label="取消置顶"><svg viewBox="0 0 24 24" aria-hidden="true"><path d="M16 12V4h1c.55 0 1-.45 1-1s-.45-1-1-1H8c-.55 0-1 .45-1 1s.45 1 1 1h1v8c0 1.1-.9 2-2 2H5v2h5.2c.4 1.2 1.5 2 2.8 2s2.4-.8 2.8-2H21v-2h-2c-1.1 0-2-.9-2-2z"/></svg></button>`
        : '';
      const searchHit = (s.search_snippet || '').trim()
        ? `<div class="session-search-hit">${escapeHtml(s.search_snippet)}</div>`
        : '';
      const customTitleEditBtn = sessionHasCustomTitle(s) ? sessionCustomTitleEditBtnHtml() : '';
      el.innerHTML = `
        <div class="session-item-main">
          <div class="session-title-row">
            <div class="session-title">${sourceBadge}<span class="session-title-text">${escapeHtml(s.title)}</span>${customTitleEditBtn}</div>
            <div class="session-title-input-wrap"></div>
          </div>
          <div class="session-meta">${buildSessionMetaHtml(s)}</div>
          ${searchHit}
        </div>
        ${pinIcon}`;
      bindSessionItemInteractions(el, s);
      bindAvatarImages(el);
      return el;
    }

    function reconcileSessionListFromCache(sessions) {
      if (sessionRenameTarget && sessionRenameInputEl && !sessionRenameSaving) return false;
      const list = document.getElementById('session-list');
      if (!list || !Array.isArray(sessions) || !sessions.length) return false;
      list.querySelector('.session-filter-empty')?.remove();
      list.querySelector('.session-list-page-footer')?.remove();

      const idToEl = new Map();
      list.querySelectorAll('.session-item[data-id]').forEach((el) => {
        idToEl.set(el.dataset.id, el);
      });

      const nextIds = new Set(sessions.map((s) => s.id));
      idToEl.forEach((el, id) => {
        if (!nextIds.has(id)) {
          el.remove();
          idToEl.delete(id);
        }
      });

      const sessionDomItems = () => list.querySelectorAll('.session-item[data-id]');
      let orderChanged = sessionDomItems().length !== sessions.length;
      if (!orderChanged) {
        for (let i = 0; i < sessions.length; i += 1) {
          const el = idToEl.get(sessions[i].id);
          if (!el || sessionDomItems()[i] !== el) {
            orderChanged = true;
            break;
          }
        }
      }

      if (orderChanged) {
        sessions.forEach((s, i) => {
          let el = idToEl.get(s.id);
          const anchor = sessionDomItems()[i] || null;
          if (!el) {
            el = buildSessionListItemElement(s);
            idToEl.set(s.id, el);
            list.insertBefore(el, anchor);
            hydrateAvatars(el);
          } else if (sessionDomItems()[i] !== el) {
            list.insertBefore(el, anchor);
          }
          patchSessionListItemEl(el, s);
        });
        while (sessionDomItems().length > sessions.length) {
          sessionDomItems()[sessionDomItems().length - 1]?.remove();
        }
      } else {
        sessions.forEach((s) => {
          patchSessionListItemEl(idToEl.get(s.id), s);
        });
      }

      syncSessionReadOnly(currentSessionId);
      return true;
    }

    function patchSessionListItemEl(el, s) {
      if (!el || !s) return;
      el.classList.toggle('active', s.id === currentSessionId);
      el.classList.toggle('is-pinned', !!s.pinned);
      const metaEl = el.querySelector('.session-meta');
      if (metaEl) patchSessionMetaEl(metaEl, s);
      const titleText = el.querySelector('.session-title-text');
      if (titleText && titleText.textContent !== (s.title || '')) {
        titleText.textContent = s.title || '';
      }
      const titleRow = el.querySelector('.session-title');
      if (titleRow) {
        const wantBadges = sessionListPrefixBadgesHtml(s);
        const badgeWrap = document.createElement('span');
        badgeWrap.innerHTML = wantBadges;
        const existing = titleRow.querySelectorAll('.session-source, .session-collab-badge');
        const nextBadges = badgeWrap.querySelectorAll('.session-source, .session-collab-badge');
        let badgesMatch = existing.length === nextBadges.length;
        if (badgesMatch) {
          existing.forEach((node, i) => {
            if (node.outerHTML !== nextBadges[i].outerHTML) badgesMatch = false;
          });
        }
        if (!badgesMatch) {
          existing.forEach((node) => node.remove());
          const frag = document.createDocumentFragment();
          nextBadges.forEach((node) => frag.appendChild(node));
          titleRow.insertBefore(frag, titleText || titleRow.firstChild);
        }
      }
    }

    function patchSessionListItemMeta(sessionId) {
      const sid = String(sessionId || '').trim();
      if (!sid) return false;
      const list = document.getElementById('session-list');
      const el = list?.querySelector(`.session-item[data-id="${sid}"]`);
      const s = sessionsCache.find((item) => item.id === sid);
      if (!el || !s) return false;
      patchSessionListItemEl(el, s);
      return true;
    }

    function renderSessionListMobileChunked(sessions, options = {}) {
      const list = document.getElementById('session-list');
      if (!list) return;
      const preserveFromBottom = !!options.preserveScrollFromBottom;
      if (options.rememberScroll !== false) {
        rememberSessionListScrollForCurrentScope();
      }
      const scrollFromBottom = preserveFromBottom
        ? list.scrollHeight - list.scrollTop
        : 0;
      let scrollRatio = options.resetScroll ? 0 : sessionListScrollForCurrentScope();
      if (options.resetScroll) {
        sessionListScrollByScope[currentSessionListScopeKey()] = 0;
        saveSessionListScrollByScope();
      }
      list.innerHTML = '';
      let idx = 0;
      const appendChunk = () => {
        const end = Math.min(idx + SESSION_LIST_MOBILE_CHUNK, sessions.length);
        const frag = document.createDocumentFragment();
        for (; idx < end; idx += 1) {
          frag.appendChild(buildSessionListItemElement(sessions[idx]));
        }
        list.appendChild(frag);
        if (idx < sessions.length) {
          scheduleMobileSessionListChunkYield(appendChunk);
          return;
        }
        if (preserveFromBottom) {
          list.scrollTop = Math.max(0, list.scrollHeight - scrollFromBottom);
        } else {
          applySessionListScrollRatio(list, scrollRatio);
        }
        updateSessionListScrollToTopBtn();
        syncSessionReadOnly(currentSessionId);
        lastSessionListKey = sessionListPatchKey(sessions);
        const runHydrate = () => hydrateAvatars(list);
        if (typeof requestIdleCallback === 'function') {
          requestIdleCallback(runHydrate, { timeout: 1200 });
        } else {
          setTimeout(runHydrate, 0);
        }
      };
      scheduleMessagesRenderYield(appendChunk);
    }

    function renderSessionList(options = {}) {
      if (sessionRenameTarget && sessionRenameInputEl && !sessionRenameSaving) {
        return;
      }
      if (!sessionRenameSaving) cancelSessionTitleEdit();
      const list = document.getElementById('session-list');
      if (!list) return;
      const preserveFromBottom = !!options.preserveScrollFromBottom;
      if (options.rememberScroll !== false) {
        rememberSessionListScrollForCurrentScope();
      }
      const scrollFromBottom = preserveFromBottom
        ? list.scrollHeight - list.scrollTop
        : 0;
      let scrollRatio = options.resetScroll ? 0 : sessionListScrollForCurrentScope();
      if (options.resetScroll) {
        sessionListScrollByScope[currentSessionListScopeKey()] = 0;
        saveSessionListScrollByScope();
      }
      const filtered = sessionsCache;
      if (
        isWebAgentMobile()
        && options.mobileChunked
        && filtered.length > SESSION_LIST_MOBILE_CHUNK
      ) {
        try {
          renderSessionListMobileChunked(filtered, options);
        } catch (err) {
          console.error('renderSessionListMobileChunked', err);
          list.innerHTML = `<div class="session-filter-empty">会话列表加载失败</div>`;
        }
        return;
      }
      list.innerHTML = '';
      try {
        if (!filtered.length) {
          const hint = sessionListEmptyShowsLoading()
            ? '加载中…'
            : sessionSearchQuery.trim()
            ? '未找到匹配的会话<br><span style="font-size:0.72rem;opacity:0.85">可尝试问题、用户名或回答中的关键词</span>'
            : sessionScopeFilter === 'mine'
              ? '暂无我的历史会话<br><span style="font-size:0.72rem;opacity:0.85">点击「全部」查看所有会话</span>'
              : '暂无历史会话<br><span style="font-size:0.72rem;opacity:0.85">点击「新对话」开始</span>';
          list.innerHTML = `<div class="session-filter-empty">${hint}</div>`;
          list.scrollTop = 0;
          updateSessionListScrollToTopBtn();
          syncSessionReadOnly(currentSessionId);
          return;
        }
        filtered.forEach((s) => {
          list.appendChild(buildSessionListItemElement(s));
        });
        if (preserveFromBottom) {
          list.scrollTop = Math.max(0, list.scrollHeight - scrollFromBottom);
        } else {
          applySessionListScrollRatio(list, scrollRatio);
        }
        updateSessionListScrollToTopBtn();
        syncSessionReadOnly(currentSessionId);
        lastSessionListKey = sessionListPatchKey(filtered);
        if (!isWebAgentMobile()) scheduleIdleSessionMessagesPrefetchDebounced();
        if (isWebAgentMobile()) {
          const runHydrate = () => hydrateAvatars(list);
          if (typeof requestIdleCallback === 'function') {
            requestIdleCallback(runHydrate, { timeout: 1200 });
          } else {
            setTimeout(runHydrate, 0);
          }
        } else {
          hydrateAvatars(list);
        }
      } catch (err) {
        console.error('renderSessionList', err);
        list.innerHTML = `<div class="session-filter-empty">会话列表加载失败<br><span style="font-size:0.72rem;opacity:0.85">${escapeHtml(err?.message || '请刷新页面重试')}</span></div>`;
      }
    }

    const SESSION_LONG_PRESS_MS = 500;
    let sessionContextTarget = null;
    let sessionContextAnchorEl = null;
    let sessionLongPressTimer = null;
    let sessionLongPressTriggered = false;
    let sessionContextDismissHandler = null;

    function clearSessionLongPressTimer() {
      if (!sessionLongPressTimer) return;
      clearTimeout(sessionLongPressTimer);
      sessionLongPressTimer = null;
    }

    function detachSessionContextDismiss() {
      if (!sessionContextDismissHandler) return;
      const handler = sessionContextDismissHandler;
      document.removeEventListener('pointerdown', handler, true);
      document.removeEventListener('click', handler, true);
      document.removeEventListener('keydown', handler, true);
      document.getElementById('session-list')?.removeEventListener('scroll', handler, true);
      sessionContextDismissHandler = null;
    }

    function hideCatalogPanelContextMenu() {
      const menu = document.getElementById('catalog-panel-context-menu');
      if (menu && !menu.hidden && typeof setDropdownAnimated === 'function') {
        setDropdownAnimated(menu, false).then(() => { menu.hidden = true; });
      } else if (menu) {
        menu.hidden = true;
      }
      detachCatalogPanelContextDismiss();
    }

    function hideSessionContextMenu() {
      const menu = document.getElementById('session-context-menu');
      if (menu && !menu.hidden && typeof setDropdownAnimated === 'function') {
        setDropdownAnimated(menu, false).then(() => { menu.hidden = true; });
      } else if (menu) {
        menu.hidden = true;
      }
      sessionContextTarget = null;
      sessionContextAnchorEl = null;
      sessionLongPressTriggered = false;
      document.querySelectorAll('.session-item.session-item-pressed').forEach((node) => {
        node.classList.remove('session-item-pressed');
      });
      detachSessionContextDismiss();
    }

    function ensureSessionContextMenuPortal() {
      const menu = document.getElementById('session-context-menu');
      if (menu && menu.parentElement !== document.body) {
        document.body.appendChild(menu);
      }
      return menu;
    }

    function positionSessionContextMenu(clientX, clientY) {
      const menu = ensureSessionContextMenuPortal();
      if (!menu) return;
      menu.classList.remove('dropdown-opening', 'dropdown-closing');
      menu.hidden = false;
      menu.style.left = '0px';
      menu.style.top = '0px';
      void menu.offsetWidth;
      const rect = menu.getBoundingClientRect();
      const margin = 8;
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      let left = clientX;
      let top = clientY;
      if (left + rect.width + margin > vw) left = clientX - rect.width;
      if (top + rect.height + margin > vh) top = clientY - rect.height;
      left = Math.min(Math.max(margin, left), Math.max(margin, vw - rect.width - margin));
      top = Math.min(Math.max(margin, top), Math.max(margin, vh - rect.height - margin));
      menu.style.left = `${left}px`;
      menu.style.top = `${top}px`;
      if (typeof setDropdownAnimated === 'function') setDropdownAnimated(menu, true);
    }

    function showSessionContextMenu(session, clientX, clientY, anchorEl) {
      if (isGuestMode()) return;
      hideMessagesContextMenu();
      hideSessionsPanelContextMenu();
      hideCatalogPanelContextMenu();
      const menu = document.getElementById('session-context-menu');
      const pinBtn = document.getElementById('session-context-pin-btn');
      if (!menu || !pinBtn || !session?.id) return;
      sessionContextTarget = session;
      sessionContextAnchorEl = anchorEl || null;
      pinBtn.textContent = session.pinned ? '取消置顶' : '置顶';
      positionSessionContextMenu(clientX, clientY);
      const handler = (event) => {
        if (menu.hidden) return;
        if (event.type === 'keydown') {
          if (event.key === 'Escape') hideSessionContextMenu();
          return;
        }
        if (menu.contains(event.target)) return;
        if (sessionContextAnchorEl?.contains(event.target)) return;
        hideSessionContextMenu();
      };
      sessionContextDismissHandler = handler;
      document.addEventListener('pointerdown', handler, true);
      document.addEventListener('click', handler, true);
      document.addEventListener('keydown', handler, true);
      document.getElementById('session-list')?.addEventListener('scroll', handler, true);
    }

    let messagesContextDismissHandler = null;
    let messagesContextCopyTarget = null;

    function detachMessagesContextDismiss() {
      if (!messagesContextDismissHandler) return;
      const handler = messagesContextDismissHandler;
      document.removeEventListener('pointerdown', handler, true);
      document.removeEventListener('click', handler, true);
      document.removeEventListener('keydown', handler, true);
      getMessagesEl()?.removeEventListener('scroll', handler, true);
      messagesContextDismissHandler = null;
    }

    function hideMessagesContextMenu() {
      const menu = document.getElementById('messages-context-menu');
      if (menu && !menu.hidden && typeof setDropdownAnimated === 'function') {
        setDropdownAnimated(menu, false).then(() => { menu.hidden = true; });
      } else if (menu) {
        menu.hidden = true;
      }
      messagesContextCopyTarget = null;
      detachMessagesContextDismiss();
    }

    function ensureMessagesContextMenuPortal() {
      const menu = document.getElementById('messages-context-menu');
      if (menu && menu.parentElement !== document.body) {
        document.body.appendChild(menu);
      }
      return menu;
    }

    function positionMessagesContextMenu(clientX, clientY) {
      const menu = ensureMessagesContextMenuPortal();
      if (!menu) return;
      menu.classList.remove('dropdown-opening', 'dropdown-closing');
      menu.hidden = false;
      menu.style.left = '0px';
      menu.style.top = '0px';
      void menu.offsetWidth;
      const rect = menu.getBoundingClientRect();
      const margin = 8;
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      let left = clientX;
      let top = clientY;
      if (left + rect.width + margin > vw) left = clientX - rect.width;
      if (top + rect.height + margin > vh) top = clientY - rect.height;
      left = Math.min(Math.max(margin, left), Math.max(margin, vw - rect.width - margin));
      top = Math.min(Math.max(margin, top), Math.max(margin, vh - rect.height - margin));
      menu.style.left = `${left}px`;
      menu.style.top = `${top}px`;
      if (typeof setDropdownAnimated === 'function') setDropdownAnimated(menu, true);
    }

    let sessionsPanelContextDismissHandler = null;

    function detachSessionsPanelContextDismiss() {
      if (!sessionsPanelContextDismissHandler) return;
      const handler = sessionsPanelContextDismissHandler;
      document.removeEventListener('pointerdown', handler, true);
      document.removeEventListener('click', handler, true);
      document.removeEventListener('keydown', handler, true);
      document.getElementById('session-list')?.removeEventListener('scroll', handler, true);
      sessionsPanelContextDismissHandler = null;
    }

    function hideSessionsPanelContextMenu() {
      const menu = document.getElementById('sessions-panel-context-menu');
      if (menu && !menu.hidden && typeof setDropdownAnimated === 'function') {
        setDropdownAnimated(menu, false).then(() => { menu.hidden = true; });
      } else if (menu) {
        menu.hidden = true;
      }
      detachSessionsPanelContextDismiss();
    }

    function ensureSessionsPanelContextMenuPortal() {
      const menu = document.getElementById('sessions-panel-context-menu');
      if (menu && menu.parentElement !== document.body) {
        document.body.appendChild(menu);
      }
      return menu;
    }

    function positionSessionsPanelContextMenu(clientX, clientY) {
      const menu = ensureSessionsPanelContextMenuPortal();
      if (!menu) return;
      menu.classList.remove('dropdown-opening', 'dropdown-closing');
      menu.hidden = false;
      menu.style.left = '0px';
      menu.style.top = '0px';
      void menu.offsetWidth;
      const rect = menu.getBoundingClientRect();
      const margin = 8;
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      let left = clientX;
      let top = clientY;
      if (left + rect.width + margin > vw) left = clientX - rect.width;
      if (top + rect.height + margin > vh) top = clientY - rect.height;
      left = Math.min(Math.max(margin, left), Math.max(margin, vw - rect.width - margin));
      top = Math.min(Math.max(margin, top), Math.max(margin, vh - rect.height - margin));
      menu.style.left = `${left}px`;
      menu.style.top = `${top}px`;
      if (typeof setDropdownAnimated === 'function') setDropdownAnimated(menu, true);
    }

    function showSessionsPanelContextMenu(clientX, clientY) {
      if (isGuestMode()) return;
      hideSessionContextMenu();
      hideMessagesContextMenu();
      hideSessionsPanelContextMenu();
      hideCatalogPanelContextMenu();
      const menu = document.getElementById('sessions-panel-context-menu');
      if (!menu) return;
      positionSessionsPanelContextMenu(clientX, clientY);
      const handler = (event) => {
        if (menu.hidden) return;
        if (event.type === 'keydown') {
          if (event.key === 'Escape') hideSessionsPanelContextMenu();
          return;
        }
        if (menu.contains(event.target)) return;
        hideSessionsPanelContextMenu();
      };
      sessionsPanelContextDismissHandler = handler;
      document.addEventListener('pointerdown', handler, true);
      document.addEventListener('click', handler, true);
      document.addEventListener('keydown', handler, true);
      document.getElementById('session-list')?.addEventListener('scroll', handler, true);
    }

    function isNativeContextMenuTarget(target) {
      if (!target || !(target instanceof Element)) return false;
      return !!target.closest(
        'input:not([type="checkbox"]):not([type="radio"]), textarea, select, [contenteditable=""], [contenteditable="true"]'
      );
    }

    /** 无自定义右键菜单的区域：静默拦截，不弹出浏览器默认菜单 */
    function setupGlobalContextMenuGuard() {
      if (document.documentElement.dataset.contextMenuGuardBound) return;
      document.documentElement.dataset.contextMenuGuardBound = '1';
      document.addEventListener('contextmenu', (event) => {
        if (event.defaultPrevented) return;
        if (isNativeContextMenuTarget(event.target)) return;
        event.preventDefault();
      }, true);
    }

    function setupSessionsPanelContextMenu() {
      const panel = document.querySelector('.left-panel');
      if (!panel || panel.dataset.sessionsPanelContextBound) return;
      panel.dataset.sessionsPanelContextBound = '1';
      panel.addEventListener('contextmenu', (event) => {
        if (isGuestMode()) return;
        if (event.target.closest('.session-item')) return;
        if (event.target.closest('#sidebar-resizer, .sidebar-tool-actions-host')) return;
        event.preventDefault();
        showSessionsPanelContextMenu(event.clientX, event.clientY);
      });
    }

    let catalogPanelContextDismissHandler = null;

    function detachCatalogPanelContextDismiss() {
      if (!catalogPanelContextDismissHandler) return;
      const handler = catalogPanelContextDismissHandler;
      document.removeEventListener('pointerdown', handler, true);
      document.removeEventListener('click', handler, true);
      document.removeEventListener('keydown', handler, true);
      document.getElementById('catalog-nav')?.removeEventListener('scroll', handler, true);
      document.getElementById('catalog-main')?.removeEventListener('scroll', handler, true);
      catalogPanelContextDismissHandler = null;
    }

    function ensureCatalogPanelContextMenuPortal() {
      const menu = document.getElementById('catalog-panel-context-menu');
      if (menu && menu.parentElement !== document.body) {
        document.body.appendChild(menu);
      }
      return menu;
    }

    function positionCatalogPanelContextMenu(clientX, clientY) {
      const menu = ensureCatalogPanelContextMenuPortal();
      if (!menu) return;
      menu.classList.remove('dropdown-opening', 'dropdown-closing');
      menu.hidden = false;
      menu.style.left = '0px';
      menu.style.top = '0px';
      void menu.offsetWidth;
      const rect = menu.getBoundingClientRect();
      const margin = 8;
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      let left = clientX;
      let top = clientY;
      if (left + rect.width + margin > vw) left = clientX - rect.width;
      if (top + rect.height + margin > vh) top = clientY - rect.height;
      left = Math.min(Math.max(margin, left), Math.max(margin, vw - rect.width - margin));
      top = Math.min(Math.max(margin, top), Math.max(margin, vh - rect.height - margin));
      menu.style.left = `${left}px`;
      menu.style.top = `${top}px`;
      if (typeof setDropdownAnimated === 'function') setDropdownAnimated(menu, true);
    }

    function showCatalogPanelContextMenu(clientX, clientY) {
      if (isGuestMode()) return;
      hideSessionContextMenu();
      hideMessagesContextMenu();
      hideSessionsPanelContextMenu();
      hideCatalogPanelContextMenu();
      const menu = document.getElementById('catalog-panel-context-menu');
      if (!menu) return;
      positionCatalogPanelContextMenu(clientX, clientY);
      const handler = (event) => {
        if (menu.hidden) return;
        if (event.type === 'keydown') {
          if (event.key === 'Escape') hideCatalogPanelContextMenu();
          return;
        }
        if (menu.contains(event.target)) return;
        hideCatalogPanelContextMenu();
      };
      catalogPanelContextDismissHandler = handler;
      document.addEventListener('pointerdown', handler, true);
      document.addEventListener('click', handler, true);
      document.addEventListener('keydown', handler, true);
      document.getElementById('catalog-nav')?.addEventListener('scroll', handler, true);
      document.getElementById('catalog-main')?.addEventListener('scroll', handler, true);
    }

    function setupCatalogPanelContextMenu() {
      const panel = document.getElementById('catalog-panel');
      if (!panel || panel.dataset.catalogPanelContextBound) return;
      panel.dataset.catalogPanelContextBound = '1';
      panel.addEventListener('contextmenu', (event) => {
        if (isGuestMode()) return;
        if (event.target.closest('#catalog-panel-resizer, #catalog-nav-resizer')) return;
        if (event.target.closest('.head-actions, #btn-moa-record')) return;
        if (event.target.closest('.catalog-nav .nav-row')) return;
        if (event.target.closest('.catalog-main .cap, .catalog-main .prompt-line, .catalog-main .module-head[data-module-head]')) return;
        event.preventDefault();
        event.stopPropagation();
        showCatalogPanelContextMenu(event.clientX, event.clientY);
      }, true);
    }

    function showMessagesContextMenu(clientX, clientY, opts = {}) {
      if (!currentSessionId) return;
      hideSessionContextMenu();
      hideSessionsPanelContextMenu();
      hideCatalogPanelContextMenu();
      hideMessagesContextMenu();
      const menu = document.getElementById('messages-context-menu');
      if (!menu) return;
      messagesContextCopyTarget = opts.copyTarget || null;
      const copyBtn = document.getElementById('messages-context-copy-btn');
      const refreshBtn = document.getElementById('messages-context-refresh-btn');
      const onUserBubble = !!messagesContextCopyTarget;
      if (copyBtn) copyBtn.hidden = !onUserBubble;
      if (refreshBtn) refreshBtn.hidden = onUserBubble;
      positionMessagesContextMenu(clientX, clientY);
      const handler = (event) => {
        if (menu.hidden) return;
        if (event.type === 'keydown') {
          if (event.key === 'Escape') hideMessagesContextMenu();
          return;
        }
        if (menu.contains(event.target)) return;
        hideMessagesContextMenu();
      };
      messagesContextDismissHandler = handler;
      document.addEventListener('pointerdown', handler, true);
      document.addEventListener('click', handler, true);
      document.addEventListener('keydown', handler, true);
      getMessagesEl()?.addEventListener('scroll', handler, true);
    }

    function sessionIsRunning(session) {
      return !!(session && (activeRuns.has(session.id) || session.running));
    }

    function sortSessionsCache() {
      const pinned = sessionsCache.filter(s => s.pinned);
      const unpinned = sessionsCache.filter(s => !s.pinned);
      pinned.sort((a, b) => String(a.pinned_at || '').localeCompare(String(b.pinned_at || '')));
      const running = unpinned.filter(s => sessionIsRunning(s));
      const idle = unpinned.filter(s => !sessionIsRunning(s));
      const byUpdated = (a, b) => String(b.updated_at || '').localeCompare(String(a.updated_at || ''));
      running.sort(byUpdated);
      idle.sort(byUpdated);
      sessionsCache = pinned.concat(running, idle);
    }

    function patchSessionPinState(sessionId, pinned) {
      const idx = sessionsCache.findIndex(s => s.id === sessionId);
      if (idx < 0) return null;
      const prev = { ...sessionsCache[idx] };
      const next = { ...prev, pinned: !!pinned };
      if (pinned) {
        next.pinned_at = new Date().toISOString();
      } else {
        delete next.pinned_at;
      }
      sessionsCache[idx] = next;
      sortSessionsCache();
      return prev;
    }

    const sessionPinBusy = new Set();

    async function toggleSessionPinned(session) {
      if (!session?.id || isGuestMode()) return;
      if (sessionPinBusy.has(session.id)) return;
      const cached = sessionsCache.find(s => s.id === session.id) || session;
      const nextPinned = !cached.pinned;
      sessionPinBusy.add(session.id);
      const prevSnapshot = patchSessionPinState(session.id, nextPinned);
      renderSessionList();
      try {
        const res = await fetch(`/api/sessions/${encodeURIComponent(session.id)}/pin`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ pinned: nextPinned }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          if (prevSnapshot) {
            const idx = sessionsCache.findIndex(s => s.id === session.id);
            if (idx >= 0) sessionsCache[idx] = prevSnapshot;
            sortSessionsCache();
          }
          renderSessionList();
          alert(data.error || '操作失败');
          return;
        }
        const idx = sessionsCache.findIndex(s => s.id === session.id);
        if (idx >= 0) sessionsCache[idx] = { ...sessionsCache[idx], ...data };
        sortSessionsCache();
        renderSessionList();
      } catch (_) {
        if (prevSnapshot) {
          const idx = sessionsCache.findIndex(s => s.id === session.id);
          if (idx >= 0) sessionsCache[idx] = prevSnapshot;
          sortSessionsCache();
        }
        renderSessionList();
        alert('操作失败，请稍后重试');
      } finally {
        sessionPinBusy.delete(session.id);
      }
    }

    let sessionRenameTarget = null;
    let sessionRenameSaving = false;
    let sessionRenameInputEl = null;
    let sessionRenameOriginalValue = '';
    let sessionRenameSavePromise = null;

    async function waitForPendingSessionTitleSave() {
      if (sessionRenameSavePromise) {
        await sessionRenameSavePromise.catch(() => {});
      }
    }

    function cancelSessionTitleEdit() {
      if (!sessionRenameTarget) return;
      const el = document.querySelector(`.session-item[data-id="${CSS.escape(sessionRenameTarget.id)}"]`);
      if (el) {
        el.classList.remove('is-editing-title');
        el.querySelector('.session-title-input-wrap')?.replaceChildren();
      }
      sessionRenameTarget = null;
      sessionRenameInputEl = null;
      sessionRenameOriginalValue = '';
    }

    function startSessionTitleEdit(session, anchorEl) {
      if (!session?.id || isGuestMode()) return;
      cancelSessionTitleEdit();
      const el = anchorEl || document.querySelector(`.session-item[data-id="${CSS.escape(session.id)}"]`);
      if (!el) return;
      sessionRenameTarget = session;
      const currentTitle = (session.custom_title || session.title || '').trim();
      sessionRenameOriginalValue = currentTitle;
      el.classList.add('is-editing-title');
      const titleDiv = el.querySelector('.session-title');
      const wrap = el.querySelector('.session-title-input-wrap');
      if (!titleDiv || !wrap) return;
      const sourceBadge = titleDiv.querySelector('.session-source');
      wrap.replaceChildren();
      if (sourceBadge) wrap.appendChild(sourceBadge.cloneNode(true));
      const input = document.createElement('input');
      input.type = 'text';
      input.className = 'session-title-input';
      input.maxLength = 80;
      input.value = currentTitle;
      input.placeholder = '留空恢复自动标题';
      input.setAttribute('aria-label', '会话标题');
      input.autocomplete = 'off';
      wrap.appendChild(input);
      sessionRenameInputEl = input;
      input.focus();
      input.select();
      input.addEventListener('keydown', (event) => {
        event.stopPropagation();
        if (event.key === 'Enter') {
          event.preventDefault();
          input.blur();
        } else if (event.key === 'Escape') {
          event.preventDefault();
          cancelSessionTitleEdit();
        }
      });
      input.addEventListener('blur', () => {
        void saveSessionCustomTitle();
      });
      input.addEventListener('click', (event) => event.stopPropagation());
      input.addEventListener('pointerdown', (event) => event.stopPropagation());
    }

    async function saveSessionCustomTitle() {
      if (sessionRenameSaving || !sessionRenameTarget?.id) return;
      const input = sessionRenameInputEl;
      if (!input) return;
      const title = (input.value || '').trim();
      if (title === sessionRenameOriginalValue) {
        cancelSessionTitleEdit();
        renderSessionList();
        return;
      }
      sessionRenameSaving = true;
      input.disabled = true;
      const targetId = sessionRenameTarget.id;
      const saveTask = (async () => {
        const idx = sessionsCache.findIndex(s => s.id === targetId);
        if (idx >= 0) {
          sessionsCache[idx] = {
            ...sessionsCache[idx],
            title,
            custom_title: title,
          };
          renderSessionList();
        }
        const data = await api(`/api/sessions/${encodeURIComponent(targetId)}/title`, {
          method: 'PUT',
          body: JSON.stringify({ title }),
        });
        const nextIdx = sessionsCache.findIndex(s => s.id === targetId);
        if (nextIdx >= 0) sessionsCache[nextIdx] = { ...sessionsCache[nextIdx], ...data };
        sessionRenameTarget = null;
        sessionRenameInputEl = null;
        sessionRenameOriginalValue = '';
        renderSessionList();
      })();
      sessionRenameSavePromise = saveTask;
      try {
        await saveTask;
      } catch (err) {
        alert(err?.message || '保存失败，请稍后重试');
        if (sessionRenameInputEl) {
          sessionRenameInputEl.disabled = false;
          sessionRenameInputEl.focus();
        }
      } finally {
        sessionRenameSaving = false;
        if (sessionRenameSavePromise === saveTask) sessionRenameSavePromise = null;
      }
    }

    function bindSessionItemInteractions(el, session) {
      const startLongPress = (clientX, clientY) => {
        clearSessionLongPressTimer();
        sessionLongPressTriggered = false;
        sessionLongPressTimer = setTimeout(() => {
          sessionLongPressTriggered = true;
          el.classList.add('session-item-pressed');
          if (navigator.vibrate) navigator.vibrate(10);
          showSessionContextMenu(session, clientX, clientY, el);
        }, SESSION_LONG_PRESS_MS);
      };
      const cancelLongPress = () => {
        clearSessionLongPressTimer();
        el.classList.remove('session-item-pressed');
      };
      const pinUnpinBtn = el.querySelector('.session-pin-unpin');
      if (pinUnpinBtn) {
        pinUnpinBtn.addEventListener('pointerdown', (event) => {
          event.stopPropagation();
          cancelLongPress();
        });
        pinUnpinBtn.addEventListener('click', async (event) => {
          event.preventDefault();
          event.stopPropagation();
          if (isGuestMode()) return;
          await toggleSessionPinned(session);
        });
      }
      const titleEditBtn = el.querySelector('.session-custom-title-edit');
      if (titleEditBtn) {
        titleEditBtn.addEventListener('click', (event) => {
          event.preventDefault();
          event.stopPropagation();
          if (isGuestMode()) return;
          startSessionTitleEdit(session, el);
        });
        titleEditBtn.addEventListener('pointerdown', (event) => {
          event.stopPropagation();
          cancelLongPress();
        });
      }
      el.addEventListener('pointerdown', (event) => {
        if (event.button !== 0) return;
        if (event.target.closest('.session-pin-unpin')) return;
        if (event.target.closest('.session-custom-title-edit')) return;
        if (!document.getElementById('session-context-menu')?.hidden) {
          hideSessionContextMenu();
        }
        startLongPress(event.clientX, event.clientY);
      });
      el.addEventListener('pointerup', (event) => {
        if (sessionLongPressTriggered) {
          cancelLongPress();
          event.preventDefault();
          return;
        }
        cancelLongPress();
      });
      el.addEventListener('pointerleave', cancelLongPress);
      el.addEventListener('pointercancel', cancelLongPress);
      el.addEventListener('pointerenter', () => {
        startSessionMessagesPrefetch(session.id);
      }, { passive: true });
      el.addEventListener('click', (event) => {
        if (el.classList.contains('is-editing-title')) {
          event.preventDefault();
          event.stopPropagation();
          return;
        }
        if (event.target.closest('.session-custom-title-edit')) return;
        if (sessionLongPressTriggered) {
          event.preventDefault();
          sessionLongPressTriggered = false;
          return;
        }
        selectSession(session.id, sessionSearchScrollOpts(session));
      });
      el.addEventListener('contextmenu', (event) => {
        if (isGuestMode()) return;
        event.preventDefault();
        hideSessionContextMenu();
        showSessionContextMenu(session, event.clientX, event.clientY, el);
      });
    }

    document.getElementById('session-context-pin-btn')?.addEventListener('click', async (event) => {
      event.preventDefault();
      event.stopPropagation();
      const target = sessionContextTarget;
      hideSessionContextMenu();
      if (target) await toggleSessionPinned(target);
    });

    document.getElementById('session-context-rename-btn')?.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();
      const target = sessionContextTarget;
      const anchorEl = sessionContextAnchorEl;
      hideSessionContextMenu();
      if (target) startSessionTitleEdit(target, anchorEl);
    });

    document.getElementById('messages-context-copy-btn')?.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();
      const target = messagesContextCopyTarget;
      hideMessagesContextMenu();
      if (!target) return;
      void (async () => {
        const ok = await copyMessageContent(target);
        showWebToast(ok ? '已复制' : '无可复制内容', { error: !ok, durationMs: 2400 });
      })();
    });

    document.getElementById('messages-context-refresh-btn')?.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();
      hideMessagesContextMenu();
      if (!currentSessionId) return;
      void runManualMessagesRefresh();
    });

    document.getElementById('sessions-panel-context-refresh-btn')?.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();
      hideSessionsPanelContextMenu();
      void runManualSessionsRefresh();
    });

    document.getElementById('catalog-panel-context-refresh-btn')?.addEventListener('click', (event) => {
      event.preventDefault();
      event.stopPropagation();
      hideCatalogPanelContextMenu();
      void runManualCatalogRefresh();
    });

    let forwardDraftIds = new Set();
    let forwardSaving = false;
    let forwardPendingText = '';
    let forwardPendingRole = '';
    let forwardPendingQuestion = '';
    let forwardModalEpoch = 0;
    let forwardModalTransition = Promise.resolve();

    function resetForwardModalSelection() {
      forwardDraftIds = new Set();
      const searchInput = document.getElementById('forward-search');
      if (searchInput) searchInput.value = '';
    }

    function enqueueForwardModalTransition(task) {
      const next = forwardModalTransition.then(task, task);
      forwardModalTransition = next.catch(() => {});
      return next;
    }

    function forwardSearchText() {
      const input = document.getElementById('forward-search');
      return (input?.value || '').trim().toLowerCase();
    }

    function forwardDraftKey(kind, id) {
      return `${kind}:${(id || '').trim()}`;
    }

    function parseForwardDraftKey(key) {
      const raw = String(key || '').trim();
      const idx = raw.indexOf(':');
      if (idx <= 0) return { kind: 'staff', id: raw };
      return { kind: raw.slice(0, idx), id: raw.slice(idx + 1) };
    }

    function isHiddenForwardRecipient(staffId) {
      return (staffId || '').trim().toLowerCase() === 'admin';
    }

    function buildShareableForwardTargets() {
      const groups = shareableWebGroups.map(group => ({
        kind: 'group',
        id: (group.conversationId || '').trim(),
        displayName: (group.displayName || '').trim(),
      })).filter(item => item.id && item.displayName);
      const users = shareableWebUsers.map(user => ({
        kind: 'staff',
        id: (user.staffId || '').trim(),
        displayName: (user.displayName || '未知用户').trim(),
        avatarUrl: (user.avatarUrl || '').trim(),
        isAdmin: !!user.isAdmin,
        isSuperAdmin: !!user.isSuperAdmin,
      })).filter(item => item.id && !isHiddenForwardRecipient(item.id));
      return [...groups, ...users];
    }

    function filterForwardTargets(targets, query) {
      if (!query) return targets;
      const needle = query.trim().toLowerCase();
      return targets.filter(item => (item.displayName || '').trim().toLowerCase().includes(needle));
    }

    function updateForwardMeta(total, shown, query) {
      const meta = document.getElementById('forward-meta');
      if (!meta) return;
      if (!total) {
        meta.textContent = '';
        return;
      }
      const selected = forwardDraftIds.size;
      if (query) {
        meta.textContent = `显示 ${shown} / 共 ${total} 项${selected ? ` · 已选 ${selected} 项` : ''}`;
      } else {
        meta.textContent = `共 ${total} 项${selected ? ` · 已选 ${selected} 项` : ''}`;
      }
    }

    function forwardTargetDisplayName(target) {
      const raw = (target.displayName || '').trim();
      if (target.kind === 'group') return raw || '未知群聊';
      return publicDisplayName(raw || '未知用户');
    }

    function showForwardListLoading() {
      const list = document.getElementById('forward-list');
      if (!list) return;
      list.innerHTML = '<div class="collaborators-empty">加载中…</div>';
      updateForwardMeta(0, 0, '');
    }

    function renderForwardList() {
      const list = document.getElementById('forward-list');
      if (!list) return;
      const query = forwardSearchText();
      const targets = buildShareableForwardTargets();
      if (!targets.length) {
        list.innerHTML = '<div class="collaborators-empty">暂无可选人员或群聊（需先有同事登录网页 Agent、同步钉钉会话或机器人群内活动）</div>';
        updateForwardMeta(0, 0, query);
        return;
      }
      const filtered = filterForwardTargets(targets, query);
      updateForwardMeta(targets.length, filtered.length, query);
      if (!filtered.length) {
        list.innerHTML = '<div class="collaborators-empty">未找到匹配人员或群聊</div>';
        return;
      }
      const viewerId = (currentAuthUser?.staffId || '').trim();
      list.innerHTML = filtered.map(target => {
        const draftKey = forwardDraftKey(target.kind, target.id);
        const name = escapeHtml(forwardTargetDisplayName(target));
        const kindTag = target.kind === 'group'
          ? ' <span class="collaborators-item-kind">群聊</span>'
          : '';
        const roleTag = target.kind === 'staff' ? buildStaffAdminRoleTagHtml(target) : '';
        const selfTag = target.kind === 'staff' && target.id && target.id === viewerId
          ? ' <span class="collaborators-item-self">（我）</span>'
          : '';
        const avatarHtml = target.kind === 'group'
          ? buildGroupPickerAvatarHtml()
          : buildStaffPickerAvatarHtml(target);
        const checked = forwardDraftIds.has(draftKey) ? ' checked' : '';
        return `
          <label class="collaborators-item">
            <input type="checkbox" data-target-kind="${escapeHtml(target.kind)}" data-target-id="${escapeHtml(target.id)}"${checked} />
            <span class="collaborators-item-main">
              <span class="collaborators-item-name-row">${avatarHtml}<span class="collaborators-item-name">${name}${roleTag}${kindTag}${selfTag}</span></span>
            </span>
          </label>`;
      }).join('');
      hydrateAvatars(list);
      list.querySelectorAll('input[type="checkbox"]').forEach(input => {
        input.addEventListener('change', () => {
          const kind = (input.dataset.targetKind || 'staff').trim();
          const targetId = (input.dataset.targetId || '').trim();
          if (!targetId) return;
          const draftKey = forwardDraftKey(kind, targetId);
          if (input.checked) forwardDraftIds.add(draftKey);
          else forwardDraftIds.delete(draftKey);
          updateForwardMeta(
            buildShareableForwardTargets().length,
            filterForwardTargets(buildShareableForwardTargets(), forwardSearchText()).length,
            forwardSearchText(),
          );
        });
      });
    }


    async function setForwardModalOpen(open) {
      const modal = document.getElementById('forward-modal');
      if (!modal) return;
      if (!open) {
        const epoch = ++forwardModalEpoch;
        resetForwardModalSelection();
        renderForwardList();
        if (modal.classList.contains('open')) {
          await animateOverlayClose(modal);
          if (epoch !== forwardModalEpoch) return;
          modal.classList.remove('open');
        }
        if (epoch !== forwardModalEpoch) return;
        modal.setAttribute('aria-hidden', 'true');
        forwardPendingText = '';
        forwardPendingRole = '';
        forwardPendingQuestion = '';
        return;
      }
      resetForwardModalSelection();
      renderForwardList();
      modal.classList.add('open');
      modal.setAttribute('aria-hidden', 'false');
      document.getElementById('forward-search')?.focus();
    }

    async function openForwardModal(text, role, questionText = '') {
      return enqueueForwardModalTransition(async () => {
        resetForwardModalSelection();
        const modal = document.getElementById('forward-modal');
        if (modal?.classList.contains('open')) {
          await setForwardModalOpen(false);
        }
        forwardPendingText = (text || '').trim();
        forwardPendingRole = (role || '').trim();
        forwardPendingQuestion = (questionText || '').trim();
        resetForwardModalSelection();
        showForwardListLoading();
        await setForwardModalOpen(true);
        await loadShareableWebUsers({ force: true });
        resetForwardModalSelection();
        renderForwardList();
      });
    }

    function removeForwardDraftGroups(groupIds) {
      const ids = new Set((groupIds || []).map(item => String(item || '').trim()).filter(Boolean));
      if (!ids.size) return false;
      let changed = false;
      ids.forEach((groupId) => {
        const draftKey = forwardDraftKey('group', groupId);
        if (forwardDraftIds.delete(draftKey)) changed = true;
      });
      shareableWebGroups = shareableWebGroups.filter(
        group => !ids.has((group.conversationId || '').trim()),
      );
      return changed;
    }

    async function submitMessageForward() {
      if (forwardSaving) return;
      if (!forwardPendingText) {
        alert('暂无内容可分享');
        await enqueueForwardModalTransition(() => setForwardModalOpen(false));
        return;
      }
      if (!forwardDraftIds.size) {
        alert('请至少选择一位接收人或群聊');
        return;
      }
      const recipientStaffIds = [];
      const recipientGroupIds = [];
      forwardDraftIds.forEach((draftKey) => {
        const parsed = parseForwardDraftKey(draftKey);
        if (parsed.kind === 'group' && parsed.id) recipientGroupIds.push(parsed.id);
        else if (parsed.id) recipientStaffIds.push(parsed.id);
      });
      forwardSaving = true;
      const confirmBtn = document.getElementById('btn-forward-confirm');
      if (confirmBtn) confirmBtn.disabled = true;
      try {
        const res = await fetch('/api/messages/forward', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            text: forwardPendingText,
            message_role: forwardPendingRole,
            question_text: forwardPendingQuestion,
            recipient_staff_ids: recipientStaffIds,
            recipient_group_ids: recipientGroupIds,
          }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          const prunedGroupIds = Array.isArray(data.pruned_group_ids) ? data.pruned_group_ids : [];
          if (prunedGroupIds.length) {
            removeForwardDraftGroups(prunedGroupIds);
          }
          await loadShareableWebUsers({ force: true });
          renderForwardList();
          alert(data.error || '分享失败');
          return;
        }
        const prunedGroupIds = Array.isArray(data.pruned_group_ids) ? data.pruned_group_ids : [];
        if (prunedGroupIds.length) {
          removeForwardDraftGroups(prunedGroupIds);
          renderForwardList();
        }
        const sentCount = Number(data.sent_count) || 0;
        const failedCount = Number(data.failed_count) || 0;
        if (failedCount > 0) {
          showWebToast(`已分享 ${sentCount} 项，${failedCount} 项失败`, { durationMs: 4200 });
        } else {
          showWebToast(`已分享至 ${sentCount} 个目标`);
        }
        await enqueueForwardModalTransition(() => setForwardModalOpen(false));
      } catch (_) {
        alert('分享失败，请稍后重试');
      } finally {
        forwardSaving = false;
        if (confirmBtn) confirmBtn.disabled = false;
      }
    }

    function readonlyPlaceholder(item) {
      if (item?.source === 'dingtalk') return DINGTALK_READONLY_PLACEHOLDER;
      if (item?.open_api_session) return OPEN_API_READONLY_PLACEHOLDER;
      if (item?.read_only) return WEB_READONLY_PLACEHOLDER;
      return DINGTALK_READONLY_PLACEHOLDER;
    }

    function isOwnWebSession(item) {
      if (!item || item.source !== 'web') return false;
      if (item.open_api_session) return false;
      if (isGuestMode()) return false;
      if (item.can_manage_collaborators === true || item.is_mine === true) return true;
      const viewerId = (currentAuthUser?.staffId || '').trim();
      const ownerId = (item.web_owner_id || '').trim();
      return !!viewerId && !!ownerId && viewerId === ownerId;
    }

    function syncCollaboratorFilterVisibility(show) {
      const filterBtn = document.getElementById('btn-session-collaborators');
      if (filterBtn) filterBtn.hidden = !show;
    }

    function buildOwnerBarLabelHtml(kind, owner) {
      let html = `<span class="owner-bar-kind">${escapeHtml(kind)}</span>`;
      html += `<span class="owner-bar-sep"> · </span>`;
      html += `<span class="owner-bar-name">${escapeHtml(owner)}</span>`;
      return html;
    }

    function updateDingtalkOwnerBar() {
      const bar = document.getElementById('dingtalk-owner-bar');
      const labelEl = document.getElementById('owner-bar-label');
      const metaEl = document.getElementById('owner-bar-meta');
      if (!bar || !labelEl) return;
      const item = getSessionFromCache(currentSessionId);
      const owner = sessionOwnerName(item);
      if (item?.source === 'dingtalk' && owner) {
        bar.hidden = false;
        labelEl.innerHTML = buildOwnerBarLabelHtml('钉钉会话', owner);
        if (metaEl) metaEl.textContent = '（仅查看）';
        syncCollaboratorFilterVisibility(false);
      } else if (item?.source === 'web' && owner) {
        bar.hidden = false;
        const collabNames = (item.web_collaborators || [])
          .map(c => publicDisplayName((c.displayName || c.staffId || '').trim()))
          .filter(Boolean);
        let meta = '';
        if (collabNames.length) {
          meta = ` · 共同：${collabNames.join('、')}`;
        } else if (item.is_collaborator) {
          meta = ' · 共同对话';
        } else if (isSessionReadOnly(item)) {
          meta = '（仅查看）';
        }
        const webKind = item.open_api_session ? 'API会话' : '网页会话';
        labelEl.innerHTML = buildOwnerBarLabelHtml(webKind, owner);
        if (metaEl) metaEl.textContent = meta;
        syncCollaboratorFilterVisibility(isOwnWebSession(item));
      } else {
        bar.hidden = true;
        labelEl.innerHTML = '';
        if (metaEl) metaEl.textContent = '';
        syncCollaboratorFilterVisibility(false);
      }
    }

    let selectableWebUsers = [];
    let shareableWebUsers = [];
    let shareableWebGroups = [];
    let shareableWebUsersLoadPromise = null;
    let collaboratorDraftIds = new Set();
    /** 打开共同对话弹窗时的已选快照，仅用于列表排序，勾选过程中不更新 */
    let collaboratorListInitialSelectedIds = new Set();
    let collaboratorsSaving = false;

    async function loadSelectableWebUsers() {
      try {
        const res = await fetch('/api/web-users');
        if (!res.ok) return [];
        const data = await res.json();
        selectableWebUsers = Array.isArray(data.users) ? data.users : [];
        return selectableWebUsers;
      } catch (_) {
        return [];
      }
    }

    async function loadShareableWebUsers(options = {}) {
      const force = options.force === true;
      if (!force && shareableWebUsersLoadPromise) {
        return shareableWebUsersLoadPromise;
      }
      shareableWebUsersLoadPromise = (async () => {
        try {
          const res = await fetch('/api/web-users?include_self=1');
          if (!res.ok) return [];
          const data = await res.json();
          shareableWebUsers = Array.isArray(data.users) ? data.users : [];
          shareableWebGroups = Array.isArray(data.groups) ? data.groups : [];
          seedUserAvatarCacheFromStaffUsers(shareableWebUsers);
          return shareableWebUsers;
        } catch (_) {
          return [];
        } finally {
          shareableWebUsersLoadPromise = null;
        }
      })();
      return shareableWebUsersLoadPromise;
    }

    function collaboratorSearchText() {
      const input = document.getElementById('collaborators-search');
      return (input?.value || '').trim().toLowerCase();
    }

    function filterCollaboratorUsers(users, query) {
      if (!query) return users;
      return users.filter(user => {
        const name = (user.displayName || '').trim().toLowerCase();
        return name.includes(query);
      });
    }

    function sortCollaboratorsByInitialSelection(users) {
      if (!collaboratorListInitialSelectedIds.size) return users;
      const head = [];
      const tail = [];
      users.forEach(user => {
        const staffId = (user.staffId || '').trim();
        if (collaboratorListInitialSelectedIds.has(staffId)) head.push(user);
        else tail.push(user);
      });
      return head.concat(tail);
    }

    function updateCollaboratorsMeta(total, shown, query) {
      const meta = document.getElementById('collaborators-meta');
      if (!meta) return;
      if (!total) {
        meta.textContent = '';
        return;
      }
      const selected = collaboratorDraftIds.size;
      if (query) {
        meta.textContent = `显示 ${shown} / 共 ${total} 人${selected ? ` · 已选 ${selected} 人` : ''}`;
      } else {
        meta.textContent = `共 ${total} 人${selected ? ` · 已选 ${selected} 人` : ''}`;
      }
    }

    function renderCollaboratorsList() {
      const list = document.getElementById('collaborators-list');
      if (!list) return;
      const query = collaboratorSearchText();
      if (!selectableWebUsers.length) {
        list.innerHTML = '<div class="collaborators-empty">暂无可选人员（需先有同事登录网页 Agent 或同步钉钉会话）</div>';
        updateCollaboratorsMeta(0, 0, query);
        return;
      }
      const filtered = sortCollaboratorsByInitialSelection(
        filterCollaboratorUsers(selectableWebUsers, query),
      );
      updateCollaboratorsMeta(selectableWebUsers.length, filtered.length, query);
      if (!filtered.length) {
        list.innerHTML = '<div class="collaborators-empty">未找到匹配人员</div>';
        return;
      }
      list.innerHTML = filtered.map(user => {
        const staffId = (user.staffId || '').trim();
        const name = escapeHtml(publicDisplayName((user.displayName || '未知用户').trim()));
        const roleTag = buildStaffAdminRoleTagHtml(user);
        const avatarHtml = buildStaffPickerAvatarHtml(user);
        const checked = collaboratorDraftIds.has(staffId) ? ' checked' : '';
        return `
          <label class="collaborators-item">
            <input type="checkbox" data-staff-id="${escapeHtml(staffId)}"${checked} />
            <span class="collaborators-item-main">
              <span class="collaborators-item-name-row">${avatarHtml}<span class="collaborators-item-name">${name}${roleTag}</span></span>
            </span>
          </label>`;
      }).join('');
      hydrateAvatars(list);
      list.querySelectorAll('input[type="checkbox"]').forEach(input => {
        input.addEventListener('change', () => {
          const staffId = (input.dataset.staffId || '').trim();
          if (!staffId) return;
          if (input.checked) collaboratorDraftIds.add(staffId);
          else collaboratorDraftIds.delete(staffId);
          updateCollaboratorsMeta(
            selectableWebUsers.length,
            filterCollaboratorUsers(selectableWebUsers, collaboratorSearchText()).length,
            collaboratorSearchText(),
          );
        });
      });
    }

    async function setCollaboratorsModalOpen(open) {
      const modal = document.getElementById('collaborators-modal');
      if (!modal) return;
      if (!open) {
        collaboratorListInitialSelectedIds = new Set();
        if (modal.classList.contains('open')) {
          await animateOverlayClose(modal);
          modal.classList.remove('open');
        }
        modal.setAttribute('aria-hidden', 'true');
        return;
      }
      const item = getSessionFromCache(currentSessionId);
      if (!isOwnWebSession(item)) return;
      collaboratorDraftIds = new Set(
        (item.web_collaborator_ids || item.web_collaborators || [])
          .map(entry => (typeof entry === 'string' ? entry : entry.staffId || '').trim())
          .filter(Boolean),
      );
      collaboratorListInitialSelectedIds = new Set(collaboratorDraftIds);
      await loadSelectableWebUsers();
      const searchInput = document.getElementById('collaborators-search');
      if (searchInput) searchInput.value = '';
      renderCollaboratorsList();
      modal.classList.add('open');
      modal.setAttribute('aria-hidden', 'false');
      searchInput?.focus();
    }

    async function saveSessionCollaborators() {
      if (collaboratorsSaving || !currentSessionId) return;
      const item = getSessionFromCache(currentSessionId);
      if (!isOwnWebSession(item)) return;
      collaboratorsSaving = true;
      const confirmBtn = document.getElementById('btn-collaborators-confirm');
      if (confirmBtn) confirmBtn.disabled = true;
      try {
        const res = await fetch(`/api/sessions/${encodeURIComponent(currentSessionId)}/collaborators`, {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ collaborator_ids: Array.from(collaboratorDraftIds) }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) {
          alert(data.error || '保存失败');
          return;
        }
        patchSessionCacheEntry(currentSessionId, {
          ...data,
          web_collaborator_ids: Array.isArray(data.web_collaborator_ids)
            ? data.web_collaborator_ids
            : [],
          web_collaborators: Array.isArray(data.web_collaborators)
            ? data.web_collaborators
            : [],
          shared_conversation_badge: data.shared_conversation_badge || '',
        });
        updateDingtalkOwnerBar();
        syncSessionReadOnly(currentSessionId);
        renderSessionList();
        await setCollaboratorsModalOpen(false);
      } catch (_) {
        alert('保存失败，请稍后重试');
      } finally {
        collaboratorsSaving = false;
        if (confirmBtn) confirmBtn.disabled = false;
      }
    }

    function isGuestMode() {
      return otpAuthEnabled && !currentAuthUser;
    }

    function goToLogin() {
      window.location.href = '/login.html';
    }

    function updateReadOnlyState() {
      const input = document.getElementById('input');
      const inputWrap = document.querySelector('.input-wrap');
      const hintRow = document.getElementById('input-hint-row');
      const item = getSessionFromCache(currentSessionId);
      if (isGuestMode()) {
        clearRetryPlaceholder();
        input.readOnly = true;
        input.value = '';
        input.placeholder = GUEST_PLACEHOLDER;
        input.classList.add('readonly-input');
        inputWrap?.classList.add('readonly');
        if (hintRow) hintRow.hidden = true;
        clearPendingAttachments();
      } else if (currentSessionReadOnly) {
        clearRetryPlaceholder();
        input.readOnly = true;
        input.value = '';
        input.placeholder = readonlyPlaceholder(item);
        input.classList.add('readonly-input');
        inputWrap?.classList.add('readonly');
        if (hintRow) hintRow.hidden = true;
        clearPendingAttachments();
      } else {
        input.readOnly = false;
        if (!retryHintActive) {
          input.placeholder = defaultInputPlaceholder();
        }
        input.classList.remove('readonly-input');
        inputWrap?.classList.remove('readonly');
        if (hintRow) hintRow.hidden = false;
      }
      document.getElementById('readonly-hint')?.remove();
      syncPushResultToggleUi();
      syncReplyModeToggleUi();
      updateInputState();
    }

    function isSessionReadOnly(item) {
      if (!item) return false;
      if (item.source === 'dingtalk') return true;
      if (item.open_api_session) return true;
      const viewerId = (currentAuthUser?.staffId || '').trim();
      const ownerId = (item.web_owner_id || '').trim();
      if (viewerId && ownerId && viewerId === ownerId) return false;
      const collabIds = new Set(
        (item.web_collaborator_ids || [])
          .map(id => String(id || '').trim())
          .filter(Boolean),
      );
      (item.web_collaborators || []).forEach(entry => {
        const id = (entry?.staffId || '').trim();
        if (id) collabIds.add(id);
      });
      if (viewerId && collabIds.has(viewerId)) return false;
      if (item.is_collaborator) return false;
      return item.read_only === true;
    }

    function syncSessionReadOnly(sessionId) {
      const sid = String(sessionId || '').trim();
      if (!sid) {
        currentSessionReadOnly = false;
        updateReadOnlyState();
        updateDingtalkOwnerBar();
        return;
      }
      const item = getSessionFromCache(sid);
      if (item) {
        currentSessionReadOnly = isSessionReadOnly(item);
      }
      updateReadOnlyState();
      updateDingtalkOwnerBar();
    }

    function cloneAttachmentDraft(items) {
      return (items || []).map(item => ({ ...item }));
    }

    function saveSessionInputDraft(sessionId) {
      const sid = String(sessionId || '').trim();
      if (!sid) return;
      const input = document.getElementById('input');
      if (!input || input.readOnly) return;
      const text = input.value || '';
      const attachments = cloneAttachmentDraft(pendingAttachments);
      if (!text.trim() && !attachments.length) {
        sessionInputDrafts.delete(sid);
        return;
      }
      sessionInputDrafts.set(sid, { text, attachments });
    }

    function restoreSessionInputDraft(sessionId) {
      const sid = String(sessionId || '').trim();
      clearRetryPlaceholder();
      const input = document.getElementById('input');
      if (!input) return;
      if (!sid || currentSessionReadOnly || input.readOnly) {
        input.value = '';
        autoResizeInput();
        clearPendingAttachments();
        updateInputState();
        return;
      }
      const draft = sessionInputDrafts.get(sid);
      input.value = draft?.text || '';
      autoResizeInput();
      if (draft?.attachments?.length) {
        pendingAttachments = cloneAttachmentDraft(draft.attachments);
        renderPendingAttachments();
      } else {
        clearPendingAttachments();
      }
      updateInputState();
    }

    function syncCurrentSessionInputDraft() {
      if (currentSessionId && !currentSessionReadOnly) {
        saveSessionInputDraft(currentSessionId);
      }
    }

    function clearSessionInputDraft(sessionId) {
      sessionInputDrafts.delete(String(sessionId || '').trim());
    }

    function updateInputState() {
      const busy = isCurrentSessionStreaming();
      const hasDraft = !!document.getElementById('input').value.trim() || pendingAttachments.length > 0;
      document.getElementById('input-wrap')?.classList.toggle('has-content', hasDraft);
      const sendBtn = document.getElementById('btn-send');
      const stopBtn = document.getElementById('btn-stop');
      const run = activeRuns.get(currentSessionId);
      const cancelFlightPending = !!currentSessionId
        && (sessionCancelFlights.has(currentSessionId) || sendAwaitingCancelFlight);
      const sendCancelPending = cancelFlightPending && !busy;
      const showStopSlot = busy || sendCancelPending;
      sendBtn.hidden = showStopSlot;
      stopBtn.hidden = !showStopSlot || currentSessionReadOnly;
      sendBtn.classList.remove('is-cancel-flight-pending');
      sendBtn.setAttribute('aria-busy', 'false');
      sendBtn.title = '发送';
      sendBtn.disabled = currentSessionReadOnly || busy || sendCancelPending || !hasDraft;
      const attachBtn = document.getElementById('btn-attach');
      if (attachBtn) {
        attachBtn.disabled = currentSessionReadOnly || busy;
        attachBtn.title = currentSessionReadOnly
          ? '只读会话不可添加附件'
          : (busy ? '思考中暂不可添加附件' : '添加附件');
      }
      const cancelling = !!run?.cancelling;
      stopBtn.disabled = currentSessionReadOnly || !showStopSlot || cancelling || sendCancelPending;
      stopBtn.classList.toggle('is-cancelling', cancelling && busy);
      stopBtn.classList.toggle('is-cancel-flight-settle', sendCancelPending);
      stopBtn.title = sendCancelPending
        ? '等待中断落盘…'
        : (cancelling ? '中断发起中…' : '中断思考');
      stopBtn.setAttribute('aria-busy', ((cancelling && busy) || sendCancelPending) ? 'true' : 'false');
      if (window.WaitingFx) {
        WaitingFx.setActive(busy && !currentSessionReadOnly);
      }
      syncPushResultToggleUi();
      syncReplyModeToggleUi();
    }

    function findActiveAssistantShell(sessionId) {
      const run = activeRuns.get(sessionId);
      if (run?.shellEl?.isConnected && !isStreamingShellFinalized(run.shellEl)) return run.shellEl;
      const msgs = document.getElementById('messages');
      const shells = msgs?.querySelectorAll('.msg.assistant') || [];
      for (let i = shells.length - 1; i >= 0; i -= 1) {
        const el = shells[i];
        if (isStreamingShellFinalized(el)) continue;
        if (el.classList.contains('streaming') || !el.dataset.timestamp) return el;
      }
      return null;
    }

    function findAssistantShellForUserContent(userText) {
      const hint = String(userText || '').trim();
      if (!hint) return null;
      const container = getMessagesEl();
      if (!container) return null;
      const nodes = [...container.querySelectorAll('.msg')];
      for (let i = nodes.length - 1; i >= 0; i -= 1) {
        if (!nodes[i].classList.contains('user')) continue;
        const body = (nodes[i].querySelector('.msg-body')?.textContent || '').trim();
        if (body !== hint) continue;
        for (let j = i + 1; j < nodes.length; j += 1) {
          if (nodes[j].classList.contains('user')) break;
          if (nodes[j].classList.contains('assistant')) return nodes[j];
        }
        return null;
      }
      return null;
    }

    /** 中断后已发下一条 user 时，在对应 user 轮次后插入静态 assistant（勿抢新 run 的 streaming shell）。 */
    function insertAssistantBubbleForUserTurn(userHint, assistantMsg) {
      const hint = String(typeof userHint === 'string' ? userHint : userHint?.text || '').trim();
      const container = getMessagesEl();
      if (!container || !hint || !assistantMsg) return null;
      const md = String(assistantMsg.content || '').trim();
      if (!md) return null;
      const nodes = [...container.querySelectorAll('.msg')];
      for (let i = nodes.length - 1; i >= 0; i -= 1) {
        if (!nodes[i].classList.contains('user')) continue;
        const body = (nodes[i].querySelector('.msg-body')?.textContent || '').trim();
        if (body !== hint) continue;
        for (let j = i + 1; j < nodes.length; j += 1) {
          if (nodes[j].classList.contains('user')) break;
          if (nodes[j].classList.contains('assistant')) {
            const existing = getMessageMarkdown(nodes[j].querySelector('.msg-body'));
            if (existing === md) return nodes[j];
            return null;
          }
        }
        const el = buildMessageElement({
          role: 'assistant',
          content: md,
          timestamp: assistantMsg.timestamp || new Date().toISOString(),
        });
        el.dataset.streamFinalized = '1';
        const anchor = nodes[i + 1] || null;
        if (anchor) container.insertBefore(el, anchor);
        else container.appendChild(el);
        bindMessagesMediaLoadScroll(container);
        hydrateAvatars(el);
        return el;
      }
      return null;
    }

    function showInterruptedReply(sessionId, text, opts = {}) {
      if (currentSessionId !== sessionId) return;
      const headline = '⚠️ 任务已中断。';
      let rawBody = String(text || '').trim() || headline;
      if (isFailureReplyText(rawBody)) rawBody = stripInterruptShellBlock(rawBody);
      const body = appendRetryHint(rawBody);
      const run = activeRuns.get(sessionId);
      const superseded = !!(opts.runToken && run && run.runToken !== opts.runToken);
      const interruptTs = new Date().toISOString();
      let shell = opts.shellEl?.isConnected ? opts.shellEl : null;
      if (!shell) {
        const hintText = typeof opts.userHint === 'string' ? opts.userHint : opts.userHint?.text;
        shell = findAssistantShellForUserContent(hintText);
      }
      if (!shell && superseded) {
        shell = insertAssistantBubbleForUserTurn(opts.userHint, {
          role: 'assistant',
          content: body,
          timestamp: interruptTs,
        });
      }
      if (!shell && !superseded) {
        shell = findActiveAssistantShell(sessionId);
        if (!shell) shell = ensureStreamingShell(sessionId);
      }
      if (!shell?.isConnected && superseded) {
        shell = appendMessage('assistant', body, false, [], [], interruptTs);
        if (shell) shell.dataset.streamFinalized = '1';
      }
      if (!shell?.isConnected) return;
      if (run && !superseded && !opts.shellEl) run.shellEl = shell;
      const staticInterruptShell = shell.dataset.streamFinalized === '1' && !shell.classList.contains('streaming')
        && !shell.querySelector('.run-status')?.innerHTML?.trim();
      if (!staticInterruptShell) {
        clearRunStatus(sessionId, shell);
        finalizeStreamingShell(sessionId, shell, body, {
          timestamp: interruptTs,
          terminal: {
            run_id: run?.runId || '',
            terminal_text: run?.terminal?.text || '',
          },
        });
      } else {
        attachTerminalFromDoneEvent(shell, sessionId, {
          run_id: run?.runId || '',
          terminal_text: run?.terminal?.text || '',
        });
      }
      const activeAfterFinalize = activeRuns.get(sessionId);
      if (activeAfterFinalize?.shellEl === shell) {
        activeAfterFinalize.shellEl = null;
        activeAfterFinalize.streamFinalized = false;
      }
      const assistantMsg = {
        role: 'assistant',
        content: body,
        timestamp: interruptTs,
        run_id: run?.runId || '',
      };
      if (!insertAssistantForUserTurnInCache(sessionId, assistantMsg, opts.userHint)) {
        appendAssistantMessageToSessionCache(sessionId, assistantMsg);
      }
      scrollMessagesToBottom({ force: true });
    }

    function isFailureReplyText(text) {
      const body = (text || '').trim();
      if (!body) return false;
      if (
        body.startsWith('⚠️ Agent 执行失败')
        || body.startsWith('⚠️ Agent 启动失败')
        || body.startsWith('⚠️ 任务已中断')
        || body.startsWith('⚠️ 任务因服务重启中断')
        || body.startsWith('⚠️ 任务执行超时')
      ) {
        return true;
      }
      return body.startsWith('⚠️') && body.includes('已自动重试') && body.includes('仍失败');
    }

    function failureReplyAlreadyVisible(text) {
      const md = String(text || '').trim();
      if (!md) return false;
      return assistantContentAlreadyInDom(md);
    }

    function showRunFailureReply(sessionId, shellEl, text, run = null) {
      const body = appendRetryHint(String(text || '').trim());
      if (!body) return false;
      if (failureReplyAlreadyVisible(body)) {
        if (run) run.failed = true;
        return false;
      }
      let shell = shellEl?.isConnected ? shellEl : findActiveAssistantShell(sessionId);
      if (!shell && currentSessionId === sessionId) {
        shell = ensureStreamingShell(sessionId);
        if (run) run.shellEl = shell;
      }
      if (!shell) return false;
      finalizeStreamingShell(sessionId, shell, body);
      commitAssistantReplyToSessionCache(sessionId, body);
      scrollMessagesToBottom({ force: true });
      if (run) run.failed = true;
      return true;
    }

    function hasCurrentInputDraft() {
      const input = document.getElementById('input');
      if (!input || input.readOnly) return false;
      return !!(input.value || '').trim() || pendingAttachments.length > 0;
    }

    function hasUserInputDuringRun(sessionId) {
      if (!hasCurrentInputDraft()) return false;
      const draft = activeRuns.get(sessionId)?.sentDraft;
      if (!draft) return true;
      const input = document.getElementById('input');
      const currentText = (input?.value || '').trim();
      const draftText = (draft.text || '').trim();
      if (currentText !== draftText) return true;
      return pendingAttachments.length !== (draft.attachments?.length || 0);
    }

    function stripRetryHintMarkdown(text) {
      const body = (text || '').trim();
      if (!body || !body.includes('原消息已回填')) return body || text || '';
      return body.replace(RETRY_HINT_MARKDOWN, '').trim();
    }

    function appendRetryHint(text) {
      const body = (text || '').trim();
      if (!body || body.includes('原消息已回填') || hasUserInputDuringRun(currentSessionId)) {
        return body || text;
      }
      return `${body}${RETRY_HINT_MARKDOWN}`;
    }

    function clearRetryPlaceholder() {
      if (!retryHintActive) return;
      const input = document.getElementById('input');
      if (input && !input.readOnly) {
        input.placeholder = defaultInputPlaceholder();
      }
      retryHintActive = false;
    }

    function shouldRestoreSentDraft(run, doneText) {
      if (!run?.sentDraft) return false;
      if (run.draftRestored) return false;
      if (run.cancelling || run.failed) return true;
      return isFailureReplyText(doneText);
    }

    function restoreSentDraft(sessionId, { showRetryHint = true, runToken = '' } = {}) {
      if (currentSessionId !== sessionId || currentSessionReadOnly) return false;
      const run = activeRuns.get(sessionId);
      if (runToken && run?.runToken !== runToken) return false;
      if (run?.draftRestored) return true;
      const draft = run?.sentDraft;
      if (!draft) return false;
      const input = document.getElementById('input');
      if (!input || input.readOnly) return false;
      const draftText = (draft.text || '').trim();
      const currentText = (input.value || '').trim();
      const draftAttachmentCount = draft.attachments?.length || 0;
      const currentAttachmentCount = pendingAttachments.length;
      if (hasCurrentInputDraft()) {
        if (currentText === draftText && currentAttachmentCount === draftAttachmentCount) {
          return true;
        }
        return false;
      }
      input.value = draft.text || '';
      autoResizeInput();
      if (draft.attachments?.length) {
        pendingAttachments = draft.attachments.map(item => ({
          id: item.id,
          name: item.name,
          mime: item.mime,
          kind: item.kind || (item.previewUrl ? 'image' : 'file'),
          previewUrl: item.previewUrl,
          data_base64: item.data_base64,
        }));
        renderPendingAttachments();
      }
      if (showRetryHint && (draft.text || draft.attachments?.length)) {
        input.placeholder = RETRY_PLACEHOLDER;
        retryHintActive = true;
      }
      sessionInputDrafts.set(sessionId, {
        text: draft.text || '',
        attachments: cloneAttachmentDraft(draft.attachments),
      });
      if (run) run.draftRestored = true;
      updateInputState();
      input.focus();
      return true;
    }

    function listenOrphanRunStream(sessionId, es, { shellEl = null, uiSettled = false } = {}) {
      if (!es) return;
      const pinnedShell = shellEl?.isConnected ? shellEl : null;
      es.onmessage = (ev) => {
        try {
          const data = JSON.parse(ev.data);
          if (data.type === 'terminal') {
            handleTerminalStreamEvent(sessionId, data);
            return;
          }
          if (data.type === 'done' || data.type === 'error') {
            if (currentSessionId === sessionId && !uiSettled && pinnedShell) {
              if (isStreamingShellFinalized(pinnedShell)) {
                /* showInterruptedReply 等已落盘，勿再改 DOM/缓存 */
              } else if (data.type === 'done') {
                if (shouldTreatDoneAsDeferredRestart(sessionId, data)) {
                  applyDeferredWebAgentRestartUi(sessionId, pinnedShell);
                } else {
                  const body = resolveDoneAssistantDisplayText(data.text, null, pinnedShell)
                    || String(data.text || '').trim();
                  if (body) {
                    finalizeStreamingShell(sessionId, pinnedShell, body, { terminal: data });
                    commitAssistantReplyToSessionCache(sessionId, body);
                  } else {
                    finalizeStreamingShell(sessionId, pinnedShell, '⚠️ 任务已中断。', { terminal: data });
                    commitAssistantReplyToSessionCache(sessionId, '⚠️ 任务已中断。');
                  }
                  scrollMessagesToBottom({ force: true });
                }
              } else {
                showRunFailureReply(
                  sessionId,
                  pinnedShell,
                  data.text || `⚠️ ${data.message || 'Agent 执行失败'}`,
                );
              }
            }
            handleDingtalkPushResult(data.dingtalk_push);
            es.close();
          }
        } catch {
          es.close();
        }
      };
      es.onerror = () => {
        if (es.readyState !== EventSource.CONNECTING) es.close();
      };
    }

    async function cancelCurrentRun() {
      const sessionId = currentSessionId;
      const run = activeRuns.get(sessionId);
      if (!run || run.cancelling) return;
      let resolveCancelFlight;
      const cancelFlight = new Promise((resolve) => { resolveCancelFlight = resolve; });
      sessionCancelFlights.set(sessionId, cancelFlight);
      run.cancelling = true;
      updateRunStatus(sessionId, { ack: '', batch: '', external: '', elapsed: '中断发起中…' });
      updateInputState();
      try {
        await api('/api/chat/cancel', {
          method: 'POST',
          body: JSON.stringify({
            run_id: run.runId || '',
            session_id: sessionId,
          }),
        });
        const cancelRunToken = run.runToken;
        const orphanShell = run.shellEl;
        const userHint = run.sentDraft;
        restoreSentDraft(sessionId, { runToken: cancelRunToken });
        showInterruptedReply(sessionId, undefined, {
          shellEl: orphanShell,
          runToken: cancelRunToken,
          userHint,
        });
        const orphanEs = run.eventSource;
        if (typeof run.streamDetach === 'function') {
          run.streamDetach({ orphan: true, shellEl: orphanShell });
        } else if (orphanEs) {
          orphanEs.onmessage = null;
          orphanEs.onerror = null;
          listenOrphanRunStream(sessionId, orphanEs, { shellEl: orphanShell, uiSettled: true });
          run.eventSource = null;
        }
        finishRun(sessionId, run.runToken);
      } catch (err) {
        run.cancelling = false;
        updateInputState();
        alert(err.message || '中断失败');
      } finally {
        sessionCancelFlights.delete(sessionId);
        resolveCancelFlight?.();
        if (currentSessionId === sessionId) updateInputState();
      }
    }

    const MOTION_MS = 240;

    function prefersReducedMotion() {
      return window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    }

    function waitMotion(el, ms = MOTION_MS) {
      return new Promise((resolve) => {
        if (!el || prefersReducedMotion()) {
          resolve();
          return;
        }
        let settled = false;
        const finish = () => {
          if (settled) return;
          settled = true;
          resolve();
        };
        el.addEventListener('animationend', finish, { once: true });
        setTimeout(finish, ms + 60);
      });
    }

    async function animateOverlayClose(modalEl) {
      if (!modalEl?.classList.contains('open') || prefersReducedMotion()) return;
      modalEl.classList.add('overlay-closing');
      await waitMotion(modalEl.querySelector('.settings-box, .bookmarks-bubble, .message-board-bubble, .about-bubble, .usage-bubble, .collaborators-box') || modalEl, 220);
      modalEl.classList.remove('overlay-closing');
    }

    function setDropdownAnimated(menuEl, open) {
      if (!menuEl) return Promise.resolve();
      if (prefersReducedMotion()) {
        menuEl.hidden = !open;
        menuEl.classList.remove('dropdown-opening', 'dropdown-closing');
        return Promise.resolve();
      }
      if (open) {
        menuEl.hidden = false;
        menuEl.classList.remove('dropdown-closing');
        void menuEl.offsetWidth;
        menuEl.classList.add('dropdown-opening');
        menuEl.addEventListener('animationend', () => menuEl.classList.remove('dropdown-opening'), { once: true });
        return Promise.resolve();
      }
      if (menuEl.hidden) return Promise.resolve();
      return new Promise((resolve) => {
        menuEl.classList.remove('dropdown-opening');
        menuEl.classList.add('dropdown-closing');
        const finish = () => {
          menuEl.hidden = true;
          menuEl.classList.remove('dropdown-closing');
          resolve();
        };
        menuEl.addEventListener('animationend', finish, { once: true });
        setTimeout(finish, 200);
      });
    }

    window.WebAgentMotion = {
      prefersReducedMotion,
      waitMotion,
      animateOverlayClose,
      setDropdownAnimated,
    };

    function triggerPanelOpenAnimation(el, className) {
      if (!el) return;
      el.classList.remove(className);
      void el.offsetWidth;
      el.classList.add(className);
      el.addEventListener('animationend', () => el.classList.remove(className), { once: true });
    }

    async function triggerPanelCloseAnimation(el, className) {
      if (!el || prefersReducedMotion()) return;
      el.classList.remove(className);
      void el.offsetWidth;
      el.classList.add(className);
      await waitMotion(el, 280);
      el.classList.remove(className);
    }

    function triggerHeaderBtnActiveAnimation(btn) {
      if (!btn || !btn.classList.contains('active')) return;
      btn.classList.remove('header-btn-active-flash');
      void btn.offsetWidth;
      btn.classList.add('header-btn-active-flash');
      btn.addEventListener('animationend', () => btn.classList.remove('header-btn-active-flash'), { once: true });
    }

    function setHeaderBtnActive(btn, active, opts = {}) {
      if (!btn) return;
      const wasActive = btn.classList.contains('active');
      btn.classList.toggle('active', active);
      if (active && !wasActive && !opts.skipAnimation && document.body.classList.contains('layout-ready')) {
        triggerHeaderBtnActiveAnimation(btn);
      }
    }

    function isMobileSidebarViewport() {
      return isWebAgentMobile() || window.matchMedia('(max-width: 640px)').matches;
    }

    function isMobileSidebarDrawerOpen() {
      return isMobileSidebarViewport()
        && (sidebarOpen || document.body.classList.contains('sidebar-mobile-open'));
    }

    function syncMobileSidebarScrim() {
      const scrim = document.getElementById('mobile-sidebar-scrim');
      if (!scrim) return;
      const show = document.body.classList.contains('sidebar-mobile-open');
      scrim.hidden = !show;
      scrim.setAttribute('aria-hidden', show ? 'false' : 'true');
    }

    function isUserMenuDockedInSidebar() {
      const wrap = document.getElementById('tool-actions-wrap');
      const sidebarHost = document.getElementById('sidebar-tool-actions-host');
      return !!(wrap && sidebarHost && sidebarHost.contains(wrap));
    }

    function resetUserMenuDropdownPlacement() {
      const dropdown = document.getElementById('user-menu-dropdown');
      const wrap = document.getElementById('user-menu');
      if (!dropdown || !wrap) return;
      dropdown.classList.remove('is-portaled', 'is-above');
      dropdown.style.position = '';
      dropdown.style.left = '';
      dropdown.style.top = '';
      dropdown.style.right = '';
      dropdown.style.bottom = '';
      dropdown.style.zIndex = '';
      dropdown.style.visibility = '';
      if (dropdown.parentElement !== wrap) {
        wrap.appendChild(dropdown);
      }
    }

    function shouldPortalUserMenuDropdown() {
      if (isUserMenuDockedInSidebar()) return true;
      return document.documentElement.classList.contains('web-agent-mobile');
    }

    function positionUserMenuDropdown() {
      const btn = document.getElementById('user-menu-btn');
      const dropdown = document.getElementById('user-menu-dropdown');
      if (!btn || !dropdown) return;
      if (!shouldPortalUserMenuDropdown()) {
        resetUserMenuDropdownPlacement();
        return;
      }
      const mobileHeader = document.documentElement.classList.contains('web-agent-mobile')
        && !isUserMenuDockedInSidebar();
      dropdown.classList.add('is-portaled');
      dropdown.classList.toggle('is-above', !mobileHeader);
      if (dropdown.parentElement !== document.body) {
        document.body.appendChild(dropdown);
      }
      const wasHidden = dropdown.hidden;
      dropdown.hidden = false;
      dropdown.classList.remove('dropdown-opening', 'dropdown-closing');
      dropdown.style.visibility = 'hidden';
      dropdown.style.left = '0px';
      dropdown.style.top = '0px';
      void dropdown.offsetWidth;
      const btnRect = btn.getBoundingClientRect();
      const menuRect = dropdown.getBoundingClientRect();
      const margin = 8;
      let left = btnRect.right - menuRect.width;
      let top = mobileHeader ? btnRect.bottom + margin : btnRect.top - menuRect.height - margin;
      left = Math.min(Math.max(margin, left), Math.max(margin, window.innerWidth - menuRect.width - margin));
      const maxTop = Math.max(margin, window.innerHeight - menuRect.height - margin);
      top = Math.min(Math.max(margin, top), maxTop);
      dropdown.style.left = `${left}px`;
      dropdown.style.top = `${top}px`;
      dropdown.style.bottom = '';
      dropdown.style.right = '';
      dropdown.style.visibility = '';
      if (wasHidden) dropdown.hidden = true;
    }

    let sidebarMinWidthCache = 300;
    let applySidebarWidthRef = null;

    function measureSidebarMinWidth() {
      const FALLBACK = 300;
      const MEASURE_WIDTH = 480;
      const host = document.getElementById('sidebar-tool-actions-host');
      const wrap = document.getElementById('tool-actions-wrap');
      const bar = document.getElementById('tool-actions-bar');
      if (!host || !wrap || !bar || wrap.parentElement !== host || document.body.classList.contains('sidebar-collapsed')) {
        sidebarMinWidthCache = FALLBACK;
        return sidebarMinWidthCache;
      }
      const root = document.documentElement;
      const prevWidth = root.style.getPropertyValue('--sidebar-width');
      root.style.setProperty('--sidebar-width', MEASURE_WIDTH + 'px');
      void host.offsetHeight;
      const hostStyle = getComputedStyle(host);
      const padX = parseFloat(hostStyle.paddingLeft) + parseFloat(hostStyle.paddingRight);
      const gap = parseFloat(getComputedStyle(wrap).columnGap || getComputedStyle(wrap).gap) || 8;
      let contentW = bar.scrollWidth;
      const userMenu = document.getElementById('user-menu');
      const loginBtn = document.getElementById('btn-login');
      if (userMenu && !userMenu.hidden) {
        contentW += gap + userMenu.offsetWidth;
      } else if (loginBtn && !loginBtn.hidden) {
        contentW += gap + loginBtn.offsetWidth;
      }
      if (prevWidth) root.style.setProperty('--sidebar-width', prevWidth);
      else root.style.removeProperty('--sidebar-width');
      sidebarMinWidthCache = Math.max(FALLBACK, Math.ceil(padX + contentW + 4));
      return sidebarMinWidthCache;
    }

    function getSidebarMinWidth() {
      return sidebarMinWidthCache;
    }

    function refreshSidebarWidthBounds() {
      measureSidebarMinWidth();
      if (typeof applySidebarWidthRef === 'function') {
        const root = document.documentElement;
        const current = parseInt(getComputedStyle(root).getPropertyValue('--sidebar-width'), 10) || 240;
        applySidebarWidthRef(current);
      }
    }

    function shouldDockToolActionsInSidebar() {
      if (isWebAgentMobile()) return false;
      return !document.body.classList.contains('sidebar-collapsed');
    }

    function syncToolActionsPlacement() {
      const wrap = document.getElementById('tool-actions-wrap');
      const headerHost = document.querySelector('.header-actions');
      const sidebarHost = document.getElementById('sidebar-tool-actions-host');
      if (!wrap || !headerHost || !sidebarHost) return;
      const dockInSidebar = shouldDockToolActionsInSidebar();
      const target = dockInSidebar ? sidebarHost : headerHost;
      document.body.classList.toggle('tool-actions-docked-sidebar', dockInSidebar);
      if (wrap.parentElement !== target) {
        target.insertBefore(wrap, target.firstChild);
      }
      const btn = document.getElementById('user-menu-btn');
      if (btn?.getAttribute('aria-expanded') === 'true') {
        if (dockInSidebar) positionUserMenuDropdown();
        else resetUserMenuDropdownPlacement();
      } else {
        resetUserMenuDropdownPlacement();
      }
      refreshSidebarWidthBounds();
      syncLogoutMenuItem();
      syncMobileHeaderToolbar();
    }

    function paintMobileSidebarShell(open, opts = {}) {
      const leftPanel = document.querySelector('.left-panel');
      localStorage.setItem('web_agent_sidebar_open', '0');
      document.body.classList.add('sidebar-collapsed');
      document.body.classList.remove('tool-actions-docked-sidebar');
      document.body.classList.toggle('sidebar-mobile-open', !!open);
      syncMobileSidebarScrim();
      setHeaderBtnActive(document.getElementById('btn-sidebar'), open, {
        ...opts,
        skipAnimation: true,
      });
      leftPanel?.classList.remove('panel-opening', 'panel-closing');
    }

    function hydrateMobileSessionSidebarList(workSeq) {
      if (workSeq != null && workSeq !== mobileSidebarListWorkSeq) return;
      const listReady = sessionsCacheAll.length > 0;
      if (listReady) {
        syncSessionsCacheFromAll();
        enrichSessionsCacheRelativeTimes(sessionsCache);
        if (reconcileSessionListFromCache(sessionsCache) || !sessionsCache.length) {
          updateSessionListScrollToTopBtn();
          syncSessionReadOnly(currentSessionId);
        } else {
          renderSessionList({ mobileChunked: true });
        }
        if (!initialSessionsListPending) hideSessionListLoadingUi();
      }
      void ensureSessionsListBootstrapPromise()
        .then(() => {
          if (workSeq != null && workSeq !== mobileSidebarListWorkSeq) return;
          endInitialSessionsListLoad();
          syncSessionsCacheFromAll();
          enrichSessionsCacheRelativeTimes(sessionsCache);
          hideSessionListLoadingUi();
          if (!reconcileSessionListFromCache(sessionsCache)) {
            renderSessionList({ mobileChunked: true });
          }
        })
        .catch(() => {
          if (workSeq != null && workSeq !== mobileSidebarListWorkSeq) return;
          hideSessionListLoadingUi();
          renderSessionList({ mobileChunked: true });
        });
    }

    function scheduleMobileSessionSidebarListWork() {
      void ensureSessionsListBootstrapPromise({ immediate: true });
      const workSeq = ++mobileSidebarListWorkSeq;
      const needLoading = !sessionsCacheAll.length || initialSessionsListPending;
      const listWarm = mobileSessionListDomReady()
        && sessionsCacheAll.length > 0
        && !initialSessionsListPending;

      const runHydrate = () => {
        if (workSeq !== mobileSidebarListWorkSeq || !sidebarOpen) return;
        if (listWarm) {
          const refreshMeta = () => {
            if (workSeq !== mobileSidebarListWorkSeq || !sidebarOpen) return;
            syncSessionsCacheFromAll();
            enrichSessionsCacheRelativeTimes(sessionsCache);
            reconcileSessionListFromCache(sessionsCache);
            updateSessionListScrollToTopBtn();
            syncSessionReadOnly(currentSessionId);
          };
          if (typeof requestIdleCallback === 'function') {
            requestIdleCallback(refreshMeta, { timeout: 500 });
          } else {
            scheduleMessagesRenderYield(refreshMeta);
          }
          return;
        }
        if (needLoading) showSessionListLoadingUi();
        scheduleMessagesRenderYield(() => hydrateMobileSessionSidebarList(workSeq));
      };

      requestAnimationFrame(() => {
        if (workSeq !== mobileSidebarListWorkSeq || !sidebarOpen) return;
        if (listWarm) {
          runHydrate();
          return;
        }
        setTimeout(runHydrate, MOBILE_SIDEBAR_LIST_DEFER_MS);
      });
    }

    async function setSidebarOpen(open, opts = {}) {
      const leftPanel = document.querySelector('.left-panel');
      const wasOpen = sidebarOpen;
      sidebarOpen = open;
      if (isWebAgentMobile()) {
        if (open) {
          paintMobileSidebarShell(true, opts);
          if (!wasOpen) scheduleMobileSessionSidebarListWork();
        } else {
          mobileSidebarListWorkSeq += 1;
          hideSessionListLoadingUi();
          paintMobileSidebarShell(false, opts);
        }
        return;
      }
      localStorage.setItem('web_agent_sidebar_open', open ? '1' : '0');
      const collapsed = !open;
      document.body.classList.toggle('sidebar-collapsed', collapsed);
      document.body.classList.toggle('sidebar-mobile-open', open && isMobileSidebarViewport());
      syncMobileSidebarScrim();
      setHeaderBtnActive(document.getElementById('btn-sidebar'), open, opts);
      if (open && !wasOpen && !opts.skipAnimation && document.body.classList.contains('layout-ready')) {
        leftPanel?.classList.remove('panel-closing');
        triggerPanelOpenAnimation(leftPanel, 'panel-opening');
      } else {
        leftPanel?.classList.remove('panel-opening', 'panel-closing');
      }
      syncToolActionsPlacement();
    }

    const deferredRestartFollowupTimers = new Map();
    const deferredRestartAwaiting = new Set();
    const WEB_AGENT_RESTART_CMD_RE = /^(?:重启|restart)\s*(?:web\s*agent|webagent|网页版\s*agent|网页\s*agent)\s*$/i;
    const DEFERRED_RESTART_PHASE = 'Agent 重启中…';

    function isWebAgentRestartUserText(text) {
      return WEB_AGENT_RESTART_CMD_RE.test(String(text || '').trim());
    }

    function lastUserMessageContent(msgs) {
      if (!Array.isArray(msgs)) return '';
      for (let i = msgs.length - 1; i >= 0; i -= 1) {
        const m = msgs[i];
        if (m?.role === 'user') return String(m.content || '').trim();
      }
      return '';
    }

    function shouldTreatDoneAsDeferredRestart(sessionId, data) {
      if (data?.deferred_web_agent_restart) return true;
      if (String(data?.text || '').trim()) return false;
      const sid = String(sessionId || '').trim();
      const msgs = sessionMessagesCache.get(sid) || [];
      return isWebAgentRestartUserText(lastUserMessageContent(msgs));
    }

    function removeDeferredRestartPendingShells(container) {
      const root = container || getMessagesEl();
      if (!root) return;
      root.querySelectorAll('.msg.assistant[data-deferred-restart-pending="1"]').forEach((el) => {
        el.remove();
      });
      root.querySelector('#typing-indicator')?.remove();
    }

    function pinDeferredRestartPendingShell(sessionId, shellEl) {
      const sid = String(sessionId || '').trim();
      if (!sid || !shellEl?.isConnected) return null;
      cancelStreamingMsgBodyUpdate(shellEl);
      clearRunStatus(sid, shellEl);
      shellEl.classList.remove('streaming');
      shellEl.dataset.deferredRestartPending = '1';
      shellEl.dataset.streamFinalized = '1';
      setAssistantMessageBody(shellEl, DEFERRED_RESTART_PHASE);
      ensureAssistantShareButton(shellEl);
      return shellEl;
    }

    function ensureDeferredRestartPendingInDom(sessionId, msgs) {
      const sid = String(sessionId || '').trim();
      if (!sid || !deferredRestartAwaiting.has(sid)) return null;
      if (messagesHaveAssistantSinceLastUser(msgs || [])) return null;
      if (sid !== currentSessionId) return null;
      const container = getMessagesEl();
      if (!container) return null;
      const existing = container.querySelector('.msg.assistant[data-deferred-restart-pending="1"]');
      if (existing) {
        pinDeferredRestartPendingShell(sid, existing);
        return existing;
      }
      document.getElementById('typing-indicator')?.remove();
      if (container.querySelector('.empty-state')) dismissEmptyState(container);
      const el = document.createElement('div');
      el.className = 'msg assistant';
      el.innerHTML = `${buildMsgLabelHtml('Agent', new Date().toISOString(), { role: 'assistant' })}
        <div class="run-status"></div>
        <div class="msg-body"></div>`;
      container.appendChild(el);
      pinDeferredRestartPendingShell(sid, el);
      if (messagesPinnedToBottom) scrollMessagesToBottom({ force: true });
      return el;
    }

    function applyDeferredWebAgentRestartUi(sessionId, assistantEl) {
      const sid = String(sessionId || '').trim();
      if (!sid) return assistantEl;
      deferredRestartAwaiting.add(sid);
      if (currentSessionId === sid) {
        let shell = assistantEl;
        if (!shell?.isConnected) {
          shell = ensureStreamingShell(sid);
          const run = activeRuns.get(sid);
          if (run) run.shellEl = shell;
        }
        pinDeferredRestartPendingShell(sid, shell);
        assistantEl = shell;
      }
      syncDeferredRestartFollowupPoll(sid, sessionMessagesCache.get(sid) || []);
      return assistantEl;
    }

    function isDeferredRestartSubmittedText(text) {
      return String(text || '').includes('Web Agent 重启已提交');
    }

    function isDeferredRestartCompleteText(text) {
      const t = String(text || '');
      return t.includes('Web Agent 已重启完成') || t.includes('Web Agent 重启失败');
    }

    function filterDeferredRestartIntermediateMessages(sessionId, msgs) {
      if (!Array.isArray(msgs) || !msgs.length) return msgs;
      const sid = String(sessionId || '').trim();
      const hasCompleteAfter = (idx) => {
        for (let i = idx + 1; i < msgs.length; i += 1) {
          const m = msgs[i];
          if (m?.role === 'assistant' && isDeferredRestartCompleteText(m.content)) return true;
        }
        return false;
      };
      return msgs.filter((m, i) => {
        if (m?.role !== 'assistant' || !isDeferredRestartSubmittedText(m.content)) return true;
        if (sid && deferredRestartAwaiting.has(sid)) return false;
        return !hasCompleteAfter(i);
      });
    }

    /** 等待 restart.py 落盘最终状态时轮询（不再展示「重启已提交」中间回复）。 */
    function needsDeferredRestartFollowup(msgs, sessionId) {
      const sid = String(sessionId || '').trim();
      if (sid && deferredRestartAwaiting.has(sid)) return true;
      if (!Array.isArray(msgs) || !msgs.length) return false;
      if (
        !messagesHaveAssistantSinceLastUser(msgs)
        && isWebAgentRestartUserText(lastUserMessageContent(msgs))
      ) {
        return true;
      }
      let lastSubmittedIdx = -1;
      for (let i = 0; i < msgs.length; i += 1) {
        const m = msgs[i];
        if (m?.role === 'assistant' && isDeferredRestartSubmittedText(m.content)) {
          lastSubmittedIdx = i;
        }
      }
      if (lastSubmittedIdx < 0) return false;
      for (let i = lastSubmittedIdx + 1; i < msgs.length; i += 1) {
        const m = msgs[i];
        if (m?.role === 'assistant' && isDeferredRestartCompleteText(m.content)) {
          return false;
        }
      }
      return true;
    }

    function syncDeferredRestartFollowupPoll(sessionId, msgs) {
      const sid = String(sessionId || '').trim();
      if (!sid) return;
      if (needsDeferredRestartFollowup(msgs, sid)) {
        startDeferredRestartFollowupPoll(sid);
      } else {
        deferredRestartAwaiting.delete(sid);
        stopDeferredRestartFollowupPoll(sid);
      }
    }

    function stopDeferredRestartFollowupPoll(sessionId) {
      const sid = String(sessionId || '').trim();
      const timer = deferredRestartFollowupTimers.get(sid);
      if (!timer) return;
      clearInterval(timer);
      deferredRestartFollowupTimers.delete(sid);
    }

    function startDeferredRestartFollowupPoll(sessionId) {
      const sid = String(sessionId || '').trim();
      if (!sid) return;
      stopDeferredRestartFollowupPoll(sid);
      let attempts = 0;
      const maxAttempts = 45;
      const timer = setInterval(async () => {
        attempts += 1;
        try {
          const data = await api(`/api/sessions/${sid}/messages?tail=25`, { cache: 'no-store' });
          const msgs = data.messages || [];
          if (data.messages_mtime) {
            patchSessionCacheEntry(sid, { messages_mtime: data.messages_mtime });
          }
          if (!needsDeferredRestartFollowup(msgs, sid)) {
            const hadComplete = msgs.some(
              (m) => m.role === 'assistant' && isDeferredRestartCompleteText(m.content),
            );
            deferredRestartAwaiting.delete(sid);
            stopDeferredRestartFollowupPoll(sid);
            if (hadComplete) {
              if (sid === currentSessionId) {
                await loadMessages({ force: true, repaint: true });
                scrollMessagesToBottom({ force: true });
              } else {
                sessionMessagesEtags.delete(sid);
                await refreshSessionMessagesCacheFromServer(sid);
              }
            }
            return;
          }
        } catch { /* 重启期间服务不可达 */ }
        if (attempts >= maxAttempts) stopDeferredRestartFollowupPoll(sid);
      }, 1000);
      deferredRestartFollowupTimers.set(sid, timer);
    }

    function finishRun(sessionId, runToken = '') {
      const run = activeRuns.get(sessionId);
      if (runToken && run?.runToken !== runToken) return;
      if (run?.cancelWatchdog) {
        clearTimeout(run.cancelWatchdog);
      }
      const sid = String(sessionId || '').trim();
      if (deferredRestartAwaiting.has(sid) && run?.shellEl?.isConnected) {
        pinDeferredRestartPendingShell(sid, run.shellEl);
        run.shellEl = null;
      }
      stopRunStreamPoll(sessionId, run?.runToken || runToken);
      activeRunEtags.delete(sessionId);
      activeRuns.delete(sessionId);
      refreshSessionListAfterRunEnd(sessionId);
      if (sessionId === currentSessionId) {
        updateInputState();
      }
      void (async () => {
        await waitForPendingSessionTitleSave();
        await loadSessions({ lite: true, force: true });
        if (activeRuns.has(sessionId)) {
          if (sessionId !== currentSessionId) {
            await refreshSessionMessagesCacheFromServer(sessionId);
          }
          return;
        }
        if (sessionId === currentSessionId) {
          await loadMessages();
        } else {
          await refreshSessionMessagesCacheFromServer(sessionId);
        }
      })();
    }

    function sessionMatchesLocalSearch(session, query) {
      const needle = String(query || '').trim().toLocaleLowerCase();
      if (!needle) return true;
      const parts = [
        session?.title,
        session?.custom_title,
        session?.latest_preview,
        session?.web_owner_label,
        session?.web_owner,
        session?.dingtalk_label,
      ];
      const hay = parts.filter(Boolean).join(' ').toLocaleLowerCase();
      return hay.includes(needle);
    }

    function applySessionSearchLocalPreview() {
      const q = sessionSearchQuery.trim();
      if (!q) {
        syncSessionsCacheFromAll();
        renderSessionList({ rememberScroll: false, resetScroll: true });
        return;
      }
      if (!sessionsCacheAll.length) return;
      sessionsCache = applySessionScopeFilter(sessionsCacheAll).filter((s) => sessionMatchesLocalSearch(s, q));
      sortSessionsCache();
      renderSessionList({ rememberScroll: false, resetScroll: true });
    }

    async function loadSessions(opts = {}) {
      const q = sessionSearchQuery.trim();
      const searchSeq = q ? ++sessionSearchFetchSeq : 0;
      const params = new URLSearchParams();
      if (q) {
        params.set('q', q);
        params.set('lite', '1');
        if (sessionScopeFilter === 'mine') params.set('scope', 'mine');
      } else if (opts.lite) {
        // lite 始终拉全量列表，scope 由 applySessionScopeFilter 在前端筛选
        params.set('lite', '1');
      }
      const url = params.toString() ? `/api/sessions?${params}` : '/api/sessions';
      const headers = {};
      if (opts.lite && !q && sessionsListEtag && !opts.force) {
        headers['If-None-Match'] = sessionsListEtag;
      }
      const data = await api(url, { headers });
      if (q && searchSeq !== sessionSearchFetchSeq) return;
      if (data.__notModified) {
        if (data.__etag) sessionsListEtag = data.__etag;
        if (opts.scopeSwitch) {
          syncSessionsCacheFromAll();
          enrichSessionsCacheRelativeTimes(sessionsCache);
          sessionScopeSwitchPending = false;
          syncSessionScopeButtonUi();
          renderSessionList({ rememberScroll: false, resetScroll: true });
          lastSessionListKey = sessionListPatchKey(sessionsCache);
        } else {
          syncSessionListFromCache();
        }
        return;
      }
      if (data.__etag) sessionsListEtag = data.__etag;
      const rows = data.sessions || [];
      if (q) {
        sessionsCache = rows;
        for (const s of rows) upsertSessionCacheById(s);
        sortSessionsCache();
      } else {
        sessionsCacheAll = rows;
        rebuildSessionsCacheIndex();
        syncSessionsCacheFromAll();
      }
      enrichSessionsCacheRelativeTimes(sessionsCache);
      seedUserAvatarCacheFromSessions(sessionsCacheAll);
      refreshUserMenuAvatar();
      const nextKey = sessionListPatchKey(sessionsCache);
      if (opts.lite && !q && !opts.force && nextKey === lastSessionListKey) {
        syncSessionListFromCache();
        return;
      }
      if (
        opts.lite && !q && !opts.force && !opts.scopeSwitch
        && reconcileSessionListFromCache(sessionsCache)
      ) {
        lastSessionListKey = nextKey;
        return;
      }
      if (opts.deferRender) {
        lastSessionListKey = nextKey;
        return;
      }
      if (opts.scopeSwitch) {
        sessionScopeSwitchPending = false;
        syncSessionScopeButtonUi();
        hideSessionListLoadingUi();
      }
      renderSessionList({
        rememberScroll: opts.scopeSwitch !== true,
        resetScroll: opts.scopeSwitch === true,
      });
      lastSessionListKey = nextKey;
    }

    function scheduleSessionSearchReload() {
      clearTimeout(sessionSearchTimer);
      sessionSearchTimer = setTimeout(() => {
        loadSessions().catch(err => console.error('loadSessions', err));
      }, 150);
    }

    function escapeHtml(s) {
      return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
    }

    function truncateDisplayText(text, maxLen) {
      const s = String(text || '');
      const n = Number(maxLen);
      if (!Number.isFinite(n) || n <= 0 || s.length <= n) return s;
      return `${s.slice(0, n)}…`;
    }

    let creatingSession = false;
    let sessionBootstrapPromise = null;

    function setNewSessionButtonsDisabled(disabled) {
      ['btn-new', 'btn-new-header'].forEach((id) => {
        const btn = document.getElementById(id);
        if (!btn) return;
        btn.disabled = disabled;
        btn.classList.toggle('is-creating-session', disabled);
        btn.setAttribute('aria-busy', disabled ? 'true' : 'false');
      });
    }

    async function animateMessagesExit() {
      const container = document.getElementById('messages');
      if (!container || prefersReducedMotion() || !container.children.length) return;
      container.classList.remove('messages-exit');
      void container.offsetWidth;
      container.classList.add('messages-exit');
      await waitMotion(container, 220);
    }

    async function createSession(opts = {}) {
      if (isGuestMode()) {
        goToLogin();
        return;
      }
      if (sessionBootstrapPromise) {
        await sessionBootstrapPromise;
        if (opts.animate) showEmptyState({ animate: true });
        return;
      }
      if (creatingSession) return;

      const animate = !!opts.animate;
      const prevSessionId = currentSessionId;

      if (animate) {
        creatingSession = true;
        setNewSessionButtonsDisabled(true);
      }

      if (prevSessionId) {
        saveCurrentSessionScrollState();
        saveSessionInputDraft(prevSessionId);
      }
      clearPendingAttachments();
      const inputEl = document.getElementById('input');
      if (inputEl && !inputEl.readOnly) {
        inputEl.value = '';
        autoResizeInput();
      }
      currentSessionId = '';
      currentSessionReadOnly = false;
      clearPersistedSessionId();
      renderSessionList();
      updateDingtalkOwnerBar();
      updateReadOnlyState();

      sessionBootstrapPromise = (async () => {
        try {
          if (prevSessionId) {
            try {
              const data = await api(`/api/sessions/${prevSessionId}/messages?tail=1`);
              if (!(data.messages || []).length) {
                await api(`/api/sessions/${prevSessionId}`, { method: 'DELETE' });
              }
            } catch { /* ignore */ }
          }
          const s = await api('/api/sessions', { method: 'POST', body: JSON.stringify({ title: '新对话' }) });
          currentSessionId = s.id;
          sessionPushResultPrefs.set(currentSessionId, false);
          persistSessionId(currentSessionId);
          applySessionPushResultPref(currentSessionId);
          updateDingtalkOwnerBar();
          updateReadOnlyState();
          renderSessionList();
          void loadSessions({ lite: true });
        } finally {
          sessionBootstrapPromise = null;
        }
      })();

      try {
        if (animate) {
          await animateMessagesExit();
          showEmptyState({ animate: true });
          document.getElementById('input').focus();
        } else {
          await sessionBootstrapPromise;
          await loadMessages();
          document.getElementById('input').focus();
        }
      } finally {
        if (animate) {
          creatingSession = false;
          setNewSessionButtonsDisabled(false);
        }
      }
    }

    async function selectSession(id, opts = {}) {
      const scrollTo = (opts.scrollToTimestamp || '').trim();
      if (!opts.force && id === currentSessionId && !scrollTo) return;
      startSessionMessagesPrefetch(id);
      await activateSession(id, opts);
    }

    function sessionSearchScrollOpts(session) {
      const q = sessionSearchQuery.trim();
      const ts = (session?.search_message_timestamp || '').trim();
      if (!q || !ts) return {};
      return { scrollToTimestamp: ts, force: true };
    }

    function messageTimestampInDom(timestamp) {
      const ts = String(timestamp || '').trim();
      if (!ts) return false;
      const container = getMessagesEl();
      if (!container) return false;
      return !!container.querySelector(`.msg[data-timestamp="${CSS.escape(ts)}"]`);
    }

    function messageTimestampInCache(sessionId, timestamp) {
      const ts = String(timestamp || '').trim();
      const sid = String(sessionId || '').trim();
      if (!ts || !sid) return false;
      const cached = sessionMessagesCache.get(sid) || [];
      return cached.some((m) => (m.timestamp || '') === ts);
    }

    async function loadOlderMessagesForSession(sessionId) {
      const sid = String(sessionId || '').trim();
      if (!sid || loadOlderMessagesInflight > 0) return false;
      const container = getMessagesEl();
      const firstMsg = getOldestLoadedMessageEl(container);
      const beforeTs = firstMsg?.dataset?.timestamp || '';
      if (!beforeTs) return false;
      loadOlderMessagesInflight += 1;
      loadingOlderMessages = true;
      if (sid === currentSessionId) setLoadOlderMessagesLoading(true);
      try {
        let data = await api(
          `/api/sessions/${sid}/messages?before=${encodeURIComponent(beforeTs)}&limit=${MESSAGES_OLDER_PAGE}`,
          { cache: 'no-store' },
        );
        if (data?.__notModified) {
          data = await api(
            `/api/sessions/${sid}/messages?before=${encodeURIComponent(beforeTs)}&limit=${MESSAGES_OLDER_PAGE}`,
            { cache: 'no-store' },
          );
        }
        if (sid !== currentSessionId) return false;
        if (data?.__notModified || !Array.isArray(data?.messages)) {
          updateLoadOlderButton(sid);
          return false;
        }
        let older = data.messages || [];
        const cachedBefore = sessionMessagesCache.get(sid) || [];
        const seenTs = new Set(cachedBefore.map((m) => m.timestamp).filter(Boolean));
        older = older.filter((m) => m.timestamp && !seenTs.has(m.timestamp));
        if (!older.length) {
          rememberSessionMessages(sid, cachedBefore, {
            total: Math.max(cachedBefore.length, Number(data.total || 0)),
            has_older: false,
            offset: data.offset,
            messages_mtime: data.messages_mtime || sessionMessagesMtimeFromList(sid),
          });
          updateLoadOlderButton(sid);
          return false;
        }
        const merged = [...older, ...cachedBefore];
        rememberSessionMessages(sid, merged, {
          total: data.total,
          has_older: data.has_older,
          offset: Math.max(0, Number(data.offset || 0)),
          messages_mtime: data.messages_mtime || sessionMessagesMtimeFromList(sid),
        });
        prependLoadedMessages(sid, older);
        updateMessagesDomFingerprint(sid, merged, sessionMessagesMeta(sid));
        return true;
      } catch (err) {
        console.error('loadOlderMessagesForSession', err);
        updateLoadOlderButton(sid);
        return false;
      } finally {
        loadOlderMessagesInflight = Math.max(0, loadOlderMessagesInflight - 1);
        loadingOlderMessages = loadOlderMessagesInflight > 0;
        if (loadOlderMessagesInflight === 0) setLoadOlderMessagesLoading(false);
        if (sid === currentSessionId) {
          scheduleAutoLoadOlderIfNeeded(container);
        }
      }
    }

    async function ensureMessageLoadedForScroll(sessionId, targetTs) {
      const sid = String(sessionId || '').trim();
      const ts = String(targetTs || '').trim();
      if (!sid || !ts) return false;
      if (messageTimestampInCache(sid, ts) || messageTimestampInDom(ts)) return true;
      let guard = 0;
      while (guard++ < 120 && sid === currentSessionId && sessionHasOlderMessages(sid)) {
        const cached = sessionMessagesCache.get(sid) || [];
        const oldest = (cached[0]?.timestamp || '').trim();
        if (oldest && oldest <= ts) break;
        const loaded = await loadOlderMessagesForSession(sid);
        if (sid !== currentSessionId) return false;
        if (messageTimestampInCache(sid, ts) || messageTimestampInDom(ts)) return true;
        if (!loaded) break;
      }
      return messageTimestampInCache(sid, ts) || messageTimestampInDom(ts);
    }

    function applySearchHighlight(target) {
      if (!target?.isConnected) return;
      target.classList.remove('search-highlight');
      void target.offsetWidth;
      target.classList.add('search-highlight');
      window.setTimeout(() => target.classList.remove('search-highlight'), 2800);
    }

    function syncChatMessageSearchNav() {
      const nav = document.getElementById('chat-message-search-nav');
      const countEl = document.getElementById('chat-message-search-count');
      const prevBtn = document.getElementById('btn-chat-search-prev');
      const nextBtn = document.getElementById('btn-chat-search-next');
      const total = chatMessageSearchMatches.length;
      const hasQuery = !!chatMessageSearchQuery.trim();
      if (!nav || !countEl) return;
      if (!hasQuery || total === 0) {
        nav.hidden = true;
        countEl.textContent = '';
        if (prevBtn) prevBtn.disabled = true;
        if (nextBtn) nextBtn.disabled = true;
        return;
      }
      nav.hidden = false;
      const idx = chatMessageSearchIndex >= 0 ? chatMessageSearchIndex + 1 : 0;
      countEl.textContent = total ? `${idx}/${total}` : '0/0';
      if (prevBtn) prevBtn.disabled = total <= 1;
      if (nextBtn) nextBtn.disabled = total <= 1;
    }

    function resetChatMessageSearch(options = {}) {
      const clearInput = options.clearInput !== false;
      chatMessageSearchQuery = '';
      chatMessageSearchMatches = [];
      chatMessageSearchIndex = -1;
      clearTimeout(chatMessageSearchTimer);
      chatMessageSearchSeq += 1;
      const input = document.getElementById('chat-message-search');
      if (clearInput && input) input.value = '';
      syncChatMessageSearchNav();
    }

    async function scrollChatToMessageTimestamp(sessionId, timestamp) {
      const sid = String(sessionId || '').trim();
      const ts = String(timestamp || '').trim();
      if (!sid || !ts || sid !== currentSessionId) return false;
      await ensureMessageLoadedForScroll(sid, ts);
      if (sid !== currentSessionId) return false;
      if (messageTimestampInCache(sid, ts) && !messageTimestampInDom(ts)) {
        const cached = sessionMessagesCache.get(sid) || [];
        if (cached.length) {
          renderLoadedMessages(sid, cached, null, { progressive: false });
        }
      }
      return new Promise((resolve) => {
        requestAnimationFrame(() => {
          if (sid !== currentSessionId) {
            resolve(false);
            return;
          }
          if (scrollToMessageTimestamp(ts)) {
            resolve(true);
            return;
          }
          window.setTimeout(() => {
            resolve(sid === currentSessionId && scrollToMessageTimestamp(ts));
          }, 120);
        });
      });
    }

    async function jumpToChatMessageSearchMatch(index) {
      const sid = String(currentSessionId || '').trim();
      if (!sid || !chatMessageSearchMatches.length) return;
      const total = chatMessageSearchMatches.length;
      const wrapped = ((index % total) + total) % total;
      chatMessageSearchIndex = wrapped;
      syncChatMessageSearchNav();
      const hit = chatMessageSearchMatches[wrapped];
      const ts = String(hit?.timestamp || hit?.message_timestamp || '').trim();
      if (!ts) return;
      pendingScrollToTimestamp = ts;
      await scrollChatToMessageTimestamp(sid, ts);
      if (sid === currentSessionId) pendingScrollToTimestamp = '';
    }

    async function runChatMessageSearch(query) {
      const q = String(query || '').trim();
      const sid = String(currentSessionId || '').trim();
      chatMessageSearchQuery = q;
      if (!q || !sid) {
        chatMessageSearchMatches = [];
        chatMessageSearchIndex = -1;
        syncChatMessageSearchNav();
        return;
      }
      const seq = ++chatMessageSearchSeq;
      try {
        const data = await api(
          `/api/sessions/${encodeURIComponent(sid)}/message-search?q=${encodeURIComponent(q)}&limit=80`,
        );
        if (seq !== chatMessageSearchSeq || sid !== currentSessionId) return;
        chatMessageSearchMatches = Array.isArray(data.matches) ? data.matches : [];
        chatMessageSearchIndex = chatMessageSearchMatches.length ? 0 : -1;
        syncChatMessageSearchNav();
        if (chatMessageSearchMatches.length) {
          await jumpToChatMessageSearchMatch(0);
        }
      } catch (err) {
        if (seq !== chatMessageSearchSeq) return;
        console.warn('chat message search failed', err);
        chatMessageSearchMatches = [];
        chatMessageSearchIndex = -1;
        syncChatMessageSearchNav();
      }
    }

    function scheduleChatMessageSearch() {
      clearTimeout(chatMessageSearchTimer);
      chatMessageSearchTimer = window.setTimeout(() => {
        void runChatMessageSearch(chatMessageSearchQuery);
      }, 260);
    }

    function afterMessagesScrollSettled(container, callback, maxMs = 900) {
      if (!container || typeof callback !== 'function') return;
      if (prefersReducedMotion()) {
        callback();
        return;
      }
      let settled = false;
      const finish = () => {
        if (settled) return;
        settled = true;
        callback();
      };
      if ('onscrollend' in window) {
        container.addEventListener('scrollend', finish, { once: true });
      }
      window.setTimeout(finish, maxMs);
    }

    function scrollToMessageTimestamp(timestamp) {
      const ts = String(timestamp || '').trim();
      if (!ts) return false;
      const container = getMessagesEl();
      if (!container) return false;
      let target = null;
      container.querySelectorAll('.msg[data-timestamp]').forEach((node) => {
        if (!target && node.dataset.timestamp === ts) target = node;
      });
      if (!target) return false;
      messagesPinnedToBottom = false;
      target.scrollIntoView({
        block: 'center',
        behavior: prefersReducedMotion() ? 'auto' : 'smooth',
      });
      afterMessagesScrollSettled(container, () => applySearchHighlight(target));
      updateScrollToBottomBtn();
      return true;
    }

    async function fulfillPendingScrollToTimestamp() {
      const ts = String(pendingScrollToTimestamp || '').trim();
      if (!ts || !currentSessionId) return;
      const sessionId = currentSessionId;
      pendingScrollToTimestamp = '';
      await scrollChatToMessageTimestamp(sessionId, ts);
    }

    function agentLogoHtml() {
      return typeof WebAgentLogo !== "undefined" ? WebAgentLogo.svg() : "";
    }

    function mountBrandLogo() {
      const el = document.querySelector(".brand-icon");
      if (el && !el.firstChild) el.innerHTML = agentLogoHtml();
    }

    function dismissEmptyState(container) {
      if (!container.querySelector('.empty-state')) return false;
      stopFeatureDemoCarousel();
      container.innerHTML = '';
      return true;
    }

    function featureDemoLabelPrefix(label) {
      if (!label) return '';
      const s = String(label).trim();
      const dot = s.indexOf('·');
      return (dot >= 0 ? s.slice(0, dot) : s).trim();
    }

    function buildFeatureDemoTitleHtml(label, title) {
      const prefix = featureDemoLabelPrefix(label);
      const t = escapeHtml(title || '');
      if (!prefix) return t;
      const sep = String(label || '').includes('·') ? ' · ' : ' ';
      return `<span class="empty-feature-tag">${escapeHtml(prefix)}${sep}</span>${t}`;
    }

    const EMPTY_FEATURE_NAV_SVG = {
      prev: '<svg viewBox="0 0 24 24" fill="none" stroke-width="2" aria-hidden="true"><path d="M15 18l-6-6 6-6"/></svg>',
      next: '<svg viewBox="0 0 24 24" fill="none" stroke-width="2" aria-hidden="true"><path d="M9 18l6-6-6-6"/></svg>',
    };

    function buildFeatureDemoCarouselHtml(demos, rotateMs, startIdx) {
      if (!demos.length) return '';
      const idx = Number.isFinite(startIdx) ? startIdx : 0;
      const d0 = demos[((idx % demos.length) + demos.length) % demos.length];
      const showNav = demos.length > 1;
      const navPrev = showNav
        ? `<button type="button" class="empty-feature-nav empty-feature-nav-prev" aria-label="上一个演示" title="上一个">${EMPTY_FEATURE_NAV_SVG.prev}</button>`
        : '';
      const navNext = showNav
        ? `<button type="button" class="empty-feature-nav empty-feature-nav-next" aria-label="下一个演示" title="下一个">${EMPTY_FEATURE_NAV_SVG.next}</button>`
        : '';
      return `
        <div class="empty-feature-carousel" data-rotate-ms="${Number(rotateMs) || 10000}" data-start-idx="${idx}" data-active-demo="${escapeHtml(d0.demo || '')}">
          <div class="empty-feature-viewport-wrap${showNav ? ' has-nav' : ''}">
            ${navPrev}
            <div class="empty-feature-viewport">
              <iframe class="empty-feature-frame" data-active-demo="${escapeHtml(d0.demo || '')}" title="${escapeHtml(d0.title || '功能演示')}" src="/keynote?embed=${encodeURIComponent(d0.demo || '')}" loading="lazy" tabindex="-1"></iframe>
            </div>
            ${navNext}
          </div>
          <div class="empty-feature-caption">
            <div class="empty-feature-title">${buildFeatureDemoTitleHtml(d0.label, d0.title)}</div>
          </div>
        </div>`;
    }

    let featureDemoTimer = null;

    function stopFeatureDemoCarousel() {
      if (featureDemoTimer) {
        clearInterval(featureDemoTimer);
        featureDemoTimer = null;
      }
    }

    function isChatInputActive() {
      const input = document.getElementById('input');
      return !!(input && (document.activeElement === input || inputComposing));
    }

    function shouldPauseFeatureDemoCarousel() {
      return !!inputComposing;
    }

    function chatInputFocusSnapshot() {
      const input = document.getElementById('input');
      if (!input || document.activeElement !== input || inputComposing) return null;
      return {
        input,
        start: input.selectionStart,
        end: input.selectionEnd,
        value: input.value,
      };
    }

    function restoreChatInputFocus(snapshot) {
      if (!snapshot?.input || inputComposing) return;
      if (document.activeElement !== snapshot.input) {
        snapshot.input.focus({ preventScroll: true });
        return;
      }
      // 组字或输入过程中 value 已变：只保焦点，不强行还原旧 selection（Safari 会乱序插入拼音）
      if (snapshot.value !== undefined && snapshot.input.value !== snapshot.value) return;
      if (Number.isFinite(snapshot.start) && Number.isFinite(snapshot.end)) {
        const len = snapshot.input.value.length;
        const start = Math.min(Math.max(0, snapshot.start), len);
        const end = Math.min(Math.max(start, snapshot.end), len);
        snapshot.input.setSelectionRange(start, end);
      }
    }

    const EMPTY_FEATURE_EMBED_DARK_BG = '#151923';
    const EMPTY_FEATURE_THEME_DEMO = 'theme';

    function isEmptyFeatureThemeDemo(demoKey) {
      return String(demoKey || '').trim() === EMPTY_FEATURE_THEME_DEMO;
    }

    function emptyFeatureEmbedSolidBg(demoKey) {
      if (!isEmptyFeatureThemeDemo(demoKey)) return EMPTY_FEATURE_EMBED_DARK_BG;
      const bg = getComputedStyle(document.documentElement).getPropertyValue('--bg-solid').trim();
      return bg || EMPTY_FEATURE_EMBED_DARK_BG;
    }

    function syncEmptyFeatureViewportBg(root, demoKey) {
      const viewport = root?.querySelector('.empty-feature-viewport');
      if (!viewport) return;
      viewport.style.background = emptyFeatureEmbedSolidBg(demoKey);
    }

    function refreshEmptyFeatureEmbedSolidBg() {
      document.querySelectorAll('.empty-feature-carousel').forEach((carousel) => {
        const demoKey = carousel.dataset.activeDemo || '';
        syncEmptyFeatureViewportBg(carousel, demoKey);
        carousel.querySelectorAll('.empty-feature-frame').forEach((frame) => {
          applyEmptyFeatureEmbedSolidBg(frame, demoKey);
        });
      });
    }

    let emptyFeatureThemeObserverBound = false;
    function bindEmptyFeatureThemeObserver() {
      if (emptyFeatureThemeObserverBound) return;
      emptyFeatureThemeObserverBound = true;
      const root = document.documentElement;
      new MutationObserver(() => refreshEmptyFeatureEmbedSolidBg()).observe(root, {
        attributes: true,
        attributeFilter: ['data-theme'],
      });
    }

    const EMPTY_FEATURE_EMBED_SOLID_SELECTORS = [
      'body.kn-embed #stage',
      'body.kn-embed .feat-demo',
      'body.kn-embed .feat-demo:has(.mock-app-body)',
      'body.kn-embed .feat-demo .mock-body',
      'body.kn-embed .mock-ap',
      'body.kn-embed .mock-ap-column',
      'body.kn-embed .mock-tp-body',
      'body.kn-embed .mock-so-body',
      'body.kn-embed .mock-rm-body',
      'body.kn-embed .mock-msf-body',
      'body.kn-embed .mock-ea-body',
      'body.kn-embed .mock-rr-body',
      'body.kn-embed .mock-dt-body',
      'body.kn-embed .mock-iso-body',
      'body.kn-embed .mock-motion-body',
      'body.kn-embed .mock-layout-body',
      'body.kn-embed .mock-catalog-body',
      'body.kn-embed .mock-co-body',
      'body.kn-embed .mock-pin-body',
      'body.kn-embed .mock-svc-body',
      'body.kn-embed .mock-egg-body',
      'body.kn-embed .mock-pk-body',
      'body.kn-embed .mock-reg-body',
      'body.kn-embed .mock-usage-body',
      'body.kn-embed .mock-fae-body',
      'body.kn-embed .mock-wf-body',
      'body.kn-embed .mock-mr-body',
      'body.kn-embed .mock-bm-body',
      'body.kn-embed .mock-sb-body',
      'body.kn-embed .mock-map-center',
      'body.kn-embed .mock-main',
      'body.kn-embed .mock-tp-layout',
      'body.kn-embed .mock-tp-chat',
      'body.kn-embed .mock-so-layout',
      'body.kn-embed .mock-so-chat',
      'body.kn-embed .mock-rm-layout',
      'body.kn-embed .mock-cr-layout',
      'body.kn-embed .mock-cr-chat',
      'body.kn-embed .mock-rr-layout',
      'body.kn-embed .mock-rr-chat',
      'body.kn-embed .mock-bm-chat',
      'body.kn-embed .mock-bm-tabbar',
      'body.kn-embed .mock-ab-app',
    ].join(',\n');

    function buildEmptyFeatureEmbedSolidCss(bg, isThemeDemo) {
      const mockAppDarkBg = isThemeDemo ? EMPTY_FEATURE_EMBED_DARK_BG : bg;
      const mockAppLightBg = isThemeDemo ? '#eef2f8' : bg;
      return `
        html.kn-embed, body.kn-embed {
          --kn-embed-bg: ${bg} !important;
          --mock-page-bg: ${bg} !important;
          --mock-page-gradient: ${bg} !important;
          --mock-workspace-bg: ${bg} !important;
          background: ${bg} !important;
        }
        ${EMPTY_FEATURE_EMBED_SOLID_SELECTORS} {
          background: ${bg} !important;
        }
        body.kn-embed .mock-app[data-theme="dark"] { --ma-bg: ${mockAppDarkBg} !important; }
        body.kn-embed .mock-app[data-theme="light"] { --ma-bg: ${mockAppLightBg} !important; }
      `;
    }

    function applyEmptyFeatureEmbedSolidBg(frame, demoKey) {
      try {
        const doc = frame?.contentDocument;
        if (!doc?.body?.classList.contains('kn-embed')) return;
        const key = demoKey ?? frame?.dataset?.activeDemo ?? '';
        const bg = emptyFeatureEmbedSolidBg(key);
        let style = doc.getElementById('chat-empty-embed-solid');
        if (!style) {
          style = doc.createElement('style');
          style.id = 'chat-empty-embed-solid';
          doc.head.appendChild(style);
        }
        style.textContent = buildEmptyFeatureEmbedSolidCss(bg, isEmptyFeatureThemeDemo(key));
      } catch (_) {
        /* iframe 未就绪时忽略 */
      }
    }

    function mountFeatureDemoCarousel(root, demos, rotateMs, startIdx) {
      stopFeatureDemoCarousel();
      bindEmptyFeatureThemeObserver();
      if (!root || !demos.length) return;
      const captionTitle = root.querySelector('.empty-feature-title');
      const frame = root.querySelector('.empty-feature-frame');
      if (!frame || !captionTitle) return;

      frame.addEventListener('load', () => applyEmptyFeatureEmbedSolidBg(frame, frame.dataset.activeDemo));

      const initialIdx = Number.isFinite(startIdx)
        ? startIdx
        : Number(root.dataset.startIdx);
      let activeIdx = Number.isFinite(initialIdx)
        ? (((initialIdx % demos.length) + demos.length) % demos.length)
        : 0;
      let paused = false;
      const ms = Number(root.dataset.rotateMs) || Number(rotateMs) || 10000;

      function pickRandomDemoIdx(excludeIdx) {
        if (demos.length <= 1) return 0;
        if (demos.length === 2) return excludeIdx === 0 ? 1 : 0;
        let next = excludeIdx;
        while (next === excludeIdx) {
          next = Math.floor(Math.random() * demos.length);
        }
        return next;
      }

      function setActive(idx, fade) {
        if (shouldPauseFeatureDemoCarousel()) return;
        activeIdx = ((idx % demos.length) + demos.length) % demos.length;
        const d = demos[activeIdx];
        const focusSnapshot = chatInputFocusSnapshot();
        const apply = () => {
          if (shouldPauseFeatureDemoCarousel()) return;
          captionTitle.innerHTML = buildFeatureDemoTitleHtml(d.label, d.title);
          frame.title = d.title || '功能演示';
          root.dataset.activeDemo = d.demo || '';
          frame.dataset.activeDemo = d.demo || '';
          syncEmptyFeatureViewportBg(root, d.demo);
          frame.src = `/keynote?embed=${encodeURIComponent(d.demo || '')}`;
          frame.addEventListener('load', () => applyEmptyFeatureEmbedSolidBg(frame, d.demo), { once: true });
          restoreChatInputFocus(focusSnapshot);
          if (focusSnapshot) {
            frame.addEventListener('load', () => restoreChatInputFocus(focusSnapshot), { once: true });
          }
        };
        if (!fade || prefersReducedMotion()) {
          root.classList.remove('is-fading');
          apply();
          return;
        }
        root.classList.add('is-fading');
        window.setTimeout(() => {
          apply();
          root.classList.remove('is-fading');
        }, 200);
      }

      function startAutoRotate() {
        if (demos.length <= 1 || prefersReducedMotion()) return;
        featureDemoTimer = window.setInterval(() => {
          if (paused || shouldPauseFeatureDemoCarousel()) return;
          setActive(pickRandomDemoIdx(activeIdx), true);
        }, ms);
      }

      function resetAutoRotate() {
        if (featureDemoTimer) {
          clearInterval(featureDemoTimer);
          featureDemoTimer = null;
        }
        startAutoRotate();
      }

      root.addEventListener('mouseenter', () => { paused = true; });
      root.addEventListener('mouseleave', () => { paused = false; });

      root.querySelector('.empty-feature-nav-prev')?.addEventListener('click', (event) => {
        event.preventDefault();
        setActive(activeIdx - 1, true);
        resetAutoRotate();
      });
      root.querySelector('.empty-feature-nav-next')?.addEventListener('click', (event) => {
        event.preventDefault();
        setActive(activeIdx + 1, true);
        resetAutoRotate();
      });

      setActive(activeIdx, false);
      startAutoRotate();
    }

    function bootstrapLoadingHtml() {
      return `<div class="bootstrap-loading-state" role="status" aria-live="polite">
        <div class="bootstrap-loading-spinner" aria-hidden="true"></div>
        <p>加载中…</p>
      </div>`;
    }

    function showMessagesBootstrapLoading() {
      const container = getMessagesEl();
      if (!container) return;
      if (container.querySelector('.msg, .empty-state, .bootstrap-loading-state')) return;
      container.insertAdjacentHTML('beforeend', bootstrapLoadingHtml());
    }

    function clearMessagesBootstrapLoading() {
      getMessagesEl()?.querySelectorAll('.bootstrap-loading-state').forEach((el) => el.remove());
    }

    function messagesDomHasConversation() {
      const container = getMessagesEl();
      return !!container?.querySelector('.msg, .empty-state');
    }

    let switchSessionLoadingActive = false;

    function beginSessionMessagesLoading(opts = {}) {
      switchSessionLoadingActive = true;
      if (opts.overlay) {
        clearMessagesBootstrapLoading();
        setMessagesManualRefreshStatus('loading');
        return;
      }
      const container = getMessagesEl();
      if (container && !container.querySelector('.msg, .empty-state, .bootstrap-loading-state')) {
        showMessagesBootstrapLoading();
      }
    }

    function endSessionMessagesLoading() {
      clearMessagesBootstrapLoading();
      if (switchSessionLoadingActive) {
        switchSessionLoadingActive = false;
        setMessagesManualRefreshStatus('hidden');
      }
    }

    let messagesManualRefreshSeq = 0;
    let messagesManualRefreshHideTimer = null;

    function setMessagesManualRefreshStatus(mode) {
      const statusEl = document.getElementById('messages-refresh-status');
      const shellEl = document.querySelector('.messages-shell');
      if (!statusEl || !shellEl) return;
      if (messagesManualRefreshHideTimer) {
        clearTimeout(messagesManualRefreshHideTimer);
        messagesManualRefreshHideTimer = null;
      }
      const labelEl = statusEl.querySelector('.messages-refresh-status-label');
      const spinnerEl = statusEl.querySelector('.bootstrap-loading-spinner');
      if (mode === 'loading') {
        statusEl.dataset.mode = 'loading';
        statusEl.hidden = false;
        if (labelEl) labelEl.textContent = '加载中…';
        if (spinnerEl) spinnerEl.hidden = false;
        shellEl.classList.remove('is-refresh-success-flash');
        requestAnimationFrame(() => statusEl.classList.add('is-visible'));
        return;
      }
      if (mode === 'success') {
        statusEl.dataset.mode = '';
        statusEl.classList.remove('is-visible');
        statusEl.hidden = true;
        shellEl.classList.remove('is-refresh-success-flash');
        void shellEl.offsetWidth;
        shellEl.classList.add('is-refresh-success-flash');
        return;
      }
      statusEl.classList.remove('is-visible');
      statusEl.hidden = true;
      statusEl.dataset.mode = '';
      shellEl.classList.remove('is-refresh-success-flash');
    }

    async function runManualMessagesRefresh() {
      if (!currentSessionId) return;
      const seq = ++messagesManualRefreshSeq;
      setMessagesManualRefreshStatus('loading');
      try {
        await loadMessages({ force: true, repaint: true });
        if (seq !== messagesManualRefreshSeq || !currentSessionId) return;
        setMessagesManualRefreshStatus('success');
      } catch (err) {
        if (seq !== messagesManualRefreshSeq) return;
        setMessagesManualRefreshStatus('hidden');
        showWebToast('消息刷新失败', { error: true, durationMs: 2800 });
        console.warn('manual messages refresh failed', err);
      }
    }

    let sessionsManualRefreshSeq = 0;

    function setSessionsManualRefreshStatus(mode) {
      const statusEl = document.getElementById('sessions-refresh-status');
      const shellEl = document.querySelector('.session-list-shell');
      if (!statusEl || !shellEl) return;
      const labelEl = statusEl.querySelector('.sessions-refresh-status-label');
      const spinnerEl = statusEl.querySelector('.bootstrap-loading-spinner');
      if (mode === 'loading') {
        statusEl.dataset.mode = 'loading';
        statusEl.hidden = false;
        if (labelEl) labelEl.textContent = '加载中…';
        if (spinnerEl) spinnerEl.hidden = false;
        shellEl.classList.remove('is-refresh-success-flash');
        requestAnimationFrame(() => statusEl.classList.add('is-visible'));
        return;
      }
      if (mode === 'success') {
        statusEl.dataset.mode = '';
        statusEl.classList.remove('is-visible');
        statusEl.hidden = true;
        shellEl.classList.remove('is-refresh-success-flash');
        void shellEl.offsetWidth;
        shellEl.classList.add('is-refresh-success-flash');
        return;
      }
      statusEl.classList.remove('is-visible');
      statusEl.hidden = true;
      statusEl.dataset.mode = '';
      shellEl.classList.remove('is-refresh-success-flash');
    }

    async function runManualSessionsRefresh() {
      const seq = ++sessionsManualRefreshSeq;
      setSessionsManualRefreshStatus('loading');
      try {
        const q = sessionSearchQuery.trim();
        await loadSessions({ lite: !q, force: true });
        if (seq !== sessionsManualRefreshSeq) return;
        setSessionsManualRefreshStatus('success');
      } catch (err) {
        if (seq !== sessionsManualRefreshSeq) return;
        setSessionsManualRefreshStatus('hidden');
        showWebToast('历史会话刷新失败', { error: true, durationMs: 2800 });
        console.warn('manual sessions refresh failed', err);
      }
    }

    let catalogManualRefreshSeq = 0;

    function setCatalogManualRefreshStatus(mode) {
      const loadingEl = document.getElementById('catalog-panel-loading');
      const shellEl = document.querySelector('.catalog-panel-body');
      if (!loadingEl || !shellEl) return;
      if (mode === 'loading') {
        loadingEl.removeAttribute('hidden');
        shellEl.classList.remove('is-refresh-success-flash');
        return;
      }
      if (mode === 'success') {
        loadingEl.setAttribute('hidden', '');
        shellEl.classList.remove('is-refresh-success-flash');
        void shellEl.offsetWidth;
        shellEl.classList.add('is-refresh-success-flash');
        return;
      }
      loadingEl.setAttribute('hidden', '');
      shellEl.classList.remove('is-refresh-success-flash');
    }

    async function runManualCatalogRefresh() {
      if (!catalogPanel) {
        showWebToast('工具台尚未加载完成', { error: true, durationMs: 2600 });
        return;
      }
      const seq = ++catalogManualRefreshSeq;
      setCatalogManualRefreshStatus('loading');
      try {
        await catalogPanel.reload(() => fetchCatalogData({ forceRefresh: true }), { preserveNavUi: true });
        if (seq !== catalogManualRefreshSeq) return;
        setCatalogManualRefreshStatus('success');
      } catch (err) {
        if (seq !== catalogManualRefreshSeq) return;
        setCatalogManualRefreshStatus('hidden');
        showWebToast('工具台刷新失败', { error: true, durationMs: 2800 });
        console.warn('manual catalog refresh failed', err);
      }
    }

    function showCatalogBootstrapLoading() {
      const el = document.getElementById('catalog-panel-loading');
      if (el) el.removeAttribute('hidden');
    }

    function clearCatalogBootstrapLoading() {
      const el = document.getElementById('catalog-panel-loading');
      if (el) el.setAttribute('hidden', '');
    }

    function showEmptyState(opts = {}) {
      const container = document.getElementById('messages');
      if (!container) return;
      if (
        document.body.classList.contains('is-page-bootstrapping')
        && !isWebAgentMobile()
        && readLikelyPersistedSessionId()
      ) {
        showMessagesBootstrapLoading();
        return;
      }
      const demos = Array.isArray(meta.featureDemos) ? meta.featureDemos : [];
      const rotateMs = meta.featureDemoRotateMs || 10000;
      const existingEmpty = container.querySelector('.empty-state');
      const animate = !!opts.animate && !prefersReducedMotion();
      if (existingEmpty && !animate) {
        if (isWebAgentMobile()) {
          existingEmpty.querySelector('.empty-feature-carousel')?.remove();
          stopFeatureDemoCarousel();
        }
        const featureEl = existingEmpty.querySelector('.empty-feature-carousel');
        if (featureEl && demos.length && !featureDemoTimer && !isWebAgentMobile()) {
          const startIdx = Number(featureEl.dataset.startIdx);
          mountFeatureDemoCarousel(
            featureEl,
            demos,
            rotateMs,
            Number.isFinite(startIdx) ? startIdx : 0,
          );
        }
        updateScrollToBottomBtn();
        syncLoadOlderAutoLoad(container);
        markMessagesDomRendered(currentSessionId || '', [], sessionMessagesMeta(currentSessionId));
        return;
      }
      stopFeatureDemoCarousel();
      const startIdx = demos.length ? Math.floor(Math.random() * demos.length) : 0;
      const featureHtml = isWebAgentMobile()
        ? ''
        : buildFeatureDemoCarouselHtml(demos, rotateMs, startIdx);
      container.classList.remove('messages-exit');
      container.innerHTML = `
        <div class="empty-state${animate ? ' empty-state-enter' : ''}">
          <div class="empty-logo">${agentLogoHtml()}</div>
          <h2>${escapeHtml(meta.title || 'Yaahlan 智能工具 Agent')}</h2>
          <p>${escapeHtml(meta.subtitle || '钉钉 Agent · MOA/Admin 查数 · Tunnel 抓包 · Stage 送礼 · 用例生成')}</p>
          ${featureHtml}
        </div>`;
      const emptyEl = container.querySelector('.empty-state');
      const featureEl = container.querySelector('.empty-feature-carousel');
      if (featureEl && !isWebAgentMobile()) {
        mountFeatureDemoCarousel(featureEl, demos, rotateMs, startIdx);
      }
      if (animate && emptyEl) {
        emptyEl.addEventListener('animationend', () => {
          emptyEl.classList.remove('empty-state-enter');
        }, { once: true });
      }
      updateScrollToBottomBtn();
      syncLoadOlderAutoLoad(container);
      markMessagesDomRendered(currentSessionId || '', [], sessionMessagesMeta(currentSessionId));
    }

    function ensureLoadOlderButton(container) {
      let sentinel = container.querySelector('#btn-load-older-messages');
      if (sentinel) {
        if (sentinel.tagName === 'BUTTON') {
          const replacement = document.createElement('div');
          replacement.id = 'btn-load-older-messages';
          replacement.className = 'load-older-sentinel';
          replacement.hidden = sentinel.hidden;
          replacement.setAttribute('aria-hidden', 'true');
          sentinel.replaceWith(replacement);
          return replacement;
        }
        return sentinel;
      }
      sentinel = document.createElement('div');
      sentinel.id = 'btn-load-older-messages';
      sentinel.className = 'load-older-sentinel';
      sentinel.hidden = true;
      sentinel.setAttribute('aria-hidden', 'true');
      container.prepend(sentinel);
      return sentinel;
    }

    function ensureLoadOlderMessagesStatus(container) {
      const root = container || getMessagesEl();
      if (!root) return null;
      const sentinel = ensureLoadOlderButton(root);
      let status = root.querySelector('#load-older-messages-status');
      if (!status) {
        status = document.createElement('div');
        status.id = 'load-older-messages-status';
        status.className = 'load-older-messages-status';
        status.setAttribute('role', 'status');
        status.setAttribute('aria-live', 'polite');
        status.hidden = true;
        status.innerHTML = '<div class="bootstrap-loading-spinner" aria-hidden="true"></div>'
          + '<span class="load-older-messages-status-label">加载更早的消息…</span>';
      }
      if (status.previousElementSibling !== sentinel) {
        sentinel.insertAdjacentElement('afterend', status);
      }
      return status;
    }

    function setLoadOlderMessagesLoading(loading) {
      const container = getMessagesEl();
      if (!container) return;
      const status = ensureLoadOlderMessagesStatus(container);
      if (!status) return;
      if (loading) {
        status.hidden = false;
        requestAnimationFrame(() => status.classList.add('is-active'));
        status.setAttribute('aria-busy', 'true');
        return;
      }
      status.classList.remove('is-active');
      status.hidden = true;
      status.removeAttribute('aria-busy');
    }

    let loadOlderMessagesObserver = null;
    let loadOlderObservedBtn = null;
    let loadingOlderMessages = false;
    let loadOlderMessagesInflight = 0;

    function isLoadOlderTriggerVisible(container, btn) {
      if (!container || !btn || btn.hidden) return false;
      const rootRect = container.getBoundingClientRect();
      const btnRect = btn.getBoundingClientRect();
      const margin = parseInt(MESSAGES_LOAD_OLDER_ROOT_MARGIN, 10) || 160;
      return btnRect.bottom >= rootRect.top - margin && btnRect.top <= rootRect.bottom;
    }

    function maybeAutoLoadOlderMessages(container) {
      if (!currentSessionId || loadingOlderMessages) return;
      if (!sessionHasOlderMessages(currentSessionId)) return;
      const el = container || getMessagesEl();
      const btn = el?.querySelector('#btn-load-older-messages');
      if (!isLoadOlderTriggerVisible(el, btn)) return;
      void loadOlderMessages();
    }

    function syncLoadOlderAutoLoad(container) {
      const el = container || getMessagesEl();
      if (!el) return;
      const btn = el.querySelector('#btn-load-older-messages');
      const shouldObserve = btn && !btn.hidden && sessionHasOlderMessages(currentSessionId);

      if (!shouldObserve) {
        if (loadOlderMessagesObserver) {
          loadOlderMessagesObserver.disconnect();
          loadOlderMessagesObserver = null;
          loadOlderObservedBtn = null;
        }
        return;
      }

      if (loadOlderObservedBtn === btn && loadOlderMessagesObserver) {
        scheduleAutoLoadOlderIfNeeded(el);
        return;
      }

      if (loadOlderMessagesObserver) loadOlderMessagesObserver.disconnect();
      loadOlderObservedBtn = btn;
      if (typeof IntersectionObserver === 'undefined') {
        scheduleAutoLoadOlderIfNeeded(el);
        return;
      }

      loadOlderMessagesObserver = new IntersectionObserver((entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) maybeAutoLoadOlderMessages(el);
        }
      }, {
        root: el,
        rootMargin: MESSAGES_LOAD_OLDER_ROOT_MARGIN,
        threshold: 0,
      });
      loadOlderMessagesObserver.observe(btn);
      scheduleAutoLoadOlderIfNeeded(el);
    }

    function updateLoadOlderButton(sessionId) {
      const container = document.getElementById('messages');
      if (!container) return;
      const sentinel = ensureLoadOlderButton(container);
      sentinel.hidden = !sessionHasOlderMessages(sessionId);
      ensureLoadOlderMessagesStatus(container);
      syncLoadOlderAutoLoad(container);
    }

    function currentUserMessageAuthorSnapshot() {
      const staffId = (currentAuthUser?.staffId || '').trim();
      const author_label = authUserDisplayName(currentAuthUser);
      let author_avatar_url = String(currentAuthUser?.avatarUrl || '').trim();
      if (staffId && author_avatar_url) userAvatarCache.set(staffId, author_avatar_url);
      return { author_id: staffId, author_label, author_avatar_url };
    }

    function mergeUserMessageAuthorFields(primary, fallback) {
      if (!primary || primary.role !== 'user') return primary;
      const out = { ...primary };
      const fb = fallback && fallback.role === 'user' ? fallback : null;
      const snap = currentUserMessageAuthorSnapshot();
      const idFrom = (obj) => String(obj?.author_id || obj?.authorId || '').trim();
      const labelFrom = (obj) => String(obj?.author_label || obj?.authorLabel || '').trim();
      const avatarFrom = (obj) => String(obj?.author_avatar_url || '').trim();
      const author_id = idFrom(out) || (fb ? idFrom(fb) : '') || snap.author_id;
      const author_label = labelFrom(out) || (fb ? labelFrom(fb) : '') || snap.author_label;
      const author_avatar_url = avatarFrom(out) || (fb ? avatarFrom(fb) : '') || snap.author_avatar_url;
      if (author_id) out.author_id = author_id;
      if (author_label) out.author_label = author_label;
      if (author_avatar_url) out.author_avatar_url = author_avatar_url;
      return out;
    }

    function userMessageStaffId(m) {
      return String(m?.author_id || m?.authorId || '').trim()
        || (currentAuthUser?.staffId || '').trim();
    }

    function userMessageAvatarUrl(m, staffId = '') {
      const sid = staffId || userMessageStaffId(m);
      return String(m?.author_avatar_url || '').trim()
        || (sid ? (userAvatarCache.get(sid) || '') : '')
        || String(currentAuthUser?.avatarUrl || '').trim();
    }

    function messageUserLabel(m) {
      const stored = publicDisplayName((m.author_label || m.authorLabel || '').trim());
      if (stored) return stored;
      if (currentSessionReadOnly) {
        const item = getSessionFromCache(currentSessionId);
        const owner = sessionOwnerName(item);
        if (owner) return owner;
      }
      return authUserDisplayName(currentAuthUser);
    }

    function syncUserMessageLabelRow(msgEl, m) {
      if (!msgEl || m?.role !== 'user') return;
      const msgTs = m.timestamp || msgEl.dataset.timestamp || new Date().toISOString();
      const label = messageUserLabel(m);
      const staffId = userMessageStaffId(m);
      const avatarUrl = userMessageAvatarUrl(m, staffId);
      const labelHtml = buildMsgLabelHtml(label, msgTs, {
        staffId,
        role: 'user',
        avatarUrl,
        eager: true,
      });
      let row = msgEl.querySelector('.msg-label-row');
      if (!row) {
        msgEl.insertAdjacentHTML('afterbegin', labelHtml);
      } else {
        row.outerHTML = labelHtml;
      }
      bindAvatarImages(msgEl);
      void hydrateAvatars(msgEl);
    }

    function buildMessageElement(m) {
      const el = document.createElement('div');
      el.className = `msg ${m.role}`;
      const msgTs = m.timestamp || new Date().toISOString();
      if (msgTs) el.dataset.timestamp = msgTs;
      const label = m.role === 'user' ? messageUserLabel(m) : 'Agent';
      const staffId = m.role === 'user' ? userMessageStaffId(m) : '';
      const avatarUrl = m.role === 'user' ? userMessageAvatarUrl(m, staffId) : '';
      const imageHtml = renderMessageImages(m.images || []);
      const fileHtml = renderMessageFiles(m.files || []);
      const text = (m.content || '').trim();
      const attachmentHtml = `${imageHtml}${fileHtml}`;
      const bodyHtml = m.role === 'assistant'
        ? `${attachmentHtml}${renderMarkdown(text)}`
        : `${attachmentHtml}${text ? escapeHtml(text).replace(/\n/g, '<br>') : ''}`;
      el.innerHTML = `
        ${buildMsgLabelHtml(label, msgTs, { staffId, role: m.role, avatarUrl, eager: m.role === 'user' })}
        <div class="msg-body">${bodyHtml || attachmentHtml}</div>`;
      if (m.role === 'assistant') {
        setMessageMarkdown(el.querySelector('.msg-body'), text);
        if (m.run_id) el.dataset.runId = String(m.run_id);
        syncMsgTerminalButton(el, currentSessionId);
        void hydrateMsgTerminalFromRun(el).then(() => syncMsgTerminalButton(el, currentSessionId));
        ensureAssistantShareButton(el);
      }
      bindAvatarImages(el);
      return el;
    }

    function scheduleAutoLoadOlderIfNeeded(container) {
      requestAnimationFrame(() => {
        maybeAutoLoadOlderMessages(container || getMessagesEl());
      });
    }

    function prependLoadedMessages(sessionId, olderMsgs) {
      const container = getMessagesEl();
      if (!container || !Array.isArray(olderMsgs) || !olderMsgs.length) return;
      const btn = ensureLoadOlderButton(container);
      const anchor = btn ? btn.nextSibling : container.firstChild;
      const prevHeight = container.scrollHeight;
      const prevTop = container.scrollTop;
      const frag = document.createDocumentFragment();
      olderMsgs.forEach((m) => {
        frag.appendChild(buildMessageElement(m));
      });
      container.insertBefore(frag, anchor);
      container.scrollTop = prevTop + (container.scrollHeight - prevHeight);
      bindMessagesMediaLoadScroll(container);
      hydrateAvatars(container);
      updateLoadOlderButton(sessionId);
      updateScrollToBottomBtn();
      if (currentSessionId === sessionId) {
        rememberSessionScrollState(sessionId, {
          pinnedToBottom: messagesPinnedToBottom,
          fromBottom: messagesPinnedToBottom ? null : (container.scrollHeight - container.scrollTop),
        });
      }
    }

    function renderLoadedMessages(sessionId, msgs, restoreFromBottom, opts = {}) {
      const loadSeq = opts.loadSeq ?? null;
      if (!sessionMessagesRenderAllowed(sessionId, loadSeq)) return;
      const container = getMessagesEl();
      endSessionMessagesLoading();
      msgs = filterDeferredRestartIntermediateMessages(sessionId, msgs);
      if (!msgs.length) {
        if (canSkipMessagesRender(sessionId, msgs, sessionMessagesMeta(sessionId))) {
          syncMessagesViewChrome(sessionId, restoreFromBottom, { touchScroll: false });
          return;
        }
        showEmptyState();
        return;
      }
      if (opts.progressive && msgs.length > MESSAGES_FIRST_PAINT_TAIL) {
        renderLoadedMessagesProgressive(sessionId, msgs, restoreFromBottom, opts);
        return;
      }
      container.innerHTML = '';
      ensureLoadOlderButton(container);
      const frag = document.createDocumentFragment();
      msgs.forEach((m) => {
        frag.appendChild(buildMessageElement(m));
      });
      container.appendChild(frag);
      finalizeLoadedMessagesView(sessionId, msgs, restoreFromBottom);
      hydrateAvatars(container);
    }

    function finalizeLoadedMessagesView(sessionId, msgs, restoreFromBottom) {
      const container = getMessagesEl();
      updateLoadOlderButton(sessionId);
      if (shouldAppendStreamingShell(sessionId, msgs)) {
        const run = activeRuns.get(sessionId);
        if (run?.shellEl) {
          container.appendChild(run.shellEl);
          renderRunStatusEl(run.shellEl.querySelector('.run-status'), run.status || {});
          refreshStreamingShellFromRun(sessionId);
        } else if (run) {
          const typingEl = document.createElement('div');
          typingEl.className = 'typing';
          typingEl.id = 'typing-indicator';
          typingEl.textContent = run?.status?.lifecycle || run?.status?.phase || run?.status?.ack || run?.status?.elapsed || 'Agent 思考中…';
          container.appendChild(typingEl);
        }
      } else {
        ensureDeferredRestartPendingInDom(sessionId, msgs);
      }
      if (pendingScrollToTimestamp) {
        /* 搜索跳转由 loadMessages finally 统一分页定位 */
      } else if (restoreFromBottom != null) {
        restoreMessagesScrollFromBottom(restoreFromBottom);
      } else if (messagesPinnedToBottom) {
        scrollMessagesToBottom({ force: !isCurrentSessionStreaming() });
        scheduleScrollMessagesToBottom({ force: !isCurrentSessionStreaming() });
      }
      bindMessagesMediaLoadScroll(container);
      updateScrollToBottomBtn();
      syncLoadOlderAutoLoad(container);
      markMessagesDomRendered(sessionId, msgs, sessionMessagesMeta(sessionId));
    }

    function renderLoadedMessagesProgressive(sessionId, msgs, restoreFromBottom, opts = {}) {
      const loadSeq = opts.loadSeq ?? null;
      if (!sessionMessagesRenderAllowed(sessionId, loadSeq)) return;
      const container = getMessagesEl();
      container.innerHTML = '';
      ensureLoadOlderButton(container);
      const headCount = Math.max(0, msgs.length - MESSAGES_FIRST_PAINT_TAIL);
      const headMsgs = msgs.slice(0, headCount);
      const tailMsgs = msgs.slice(headCount);
      // 记录初始滚动意图：渐进渲染 prepend 历史消息会触发 ResizeObserver 误判 pinned=false
      const scrollPinnedIntent = restoreFromBottom == null && messagesPinnedToBottom;
      const tailFrag = document.createDocumentFragment();
      tailMsgs.forEach((m) => {
        tailFrag.appendChild(buildMessageElement(m));
      });
      container.appendChild(tailFrag);
      finalizeLoadedMessagesView(sessionId, msgs, restoreFromBottom);
      if (!headMsgs.length) return;

      let idx = 0;
      const renderHeadChunk = () => {
        if (!sessionMessagesRenderAllowed(sessionId, loadSeq)) return;
        const chunkSize = messagesRenderChunkSize();
        const chunk = headMsgs.slice(idx, idx + chunkSize);
        idx += chunkSize;
        if (!chunk.length) return;
        const btn = ensureLoadOlderButton(container);
        const anchor = btn ? btn.nextSibling : container.firstChild;
        const prevHeight = container.scrollHeight;
        const prevTop = container.scrollTop;
        const frag = document.createDocumentFragment();
        chunk.forEach((m) => {
          frag.appendChild(buildMessageElement(m));
        });
        container.insertBefore(frag, anchor);
        container.scrollTop = prevTop + (container.scrollHeight - prevHeight);
        bindMessagesMediaLoadScroll(container);
        updateLoadOlderButton(sessionId);
        markMessagesDomRendered(sessionId, msgs, sessionMessagesMeta(sessionId));
        hydrateAvatars(container);
        if (idx < headMsgs.length) {
          scheduleMessagesRenderYield(renderHeadChunk);
          return;
        }
        if (!sessionMessagesRenderAllowed(sessionId, loadSeq)) return;
        if (pendingScrollToTimestamp) return;
        if (restoreFromBottom != null) {
          restoreMessagesScrollFromBottom(restoreFromBottom);
        } else if (scrollPinnedIntent) {
          messagesPinnedToBottom = true;
          scheduleScrollMessagesToBottom({ force: !isCurrentSessionStreaming() });
        }
        updateScrollToBottomBtn();
      };
      scheduleMessagesRenderYield(renderHeadChunk);
    }

    function messagesEqualForSync(a, b) {
      return (a?.timestamp || '') === (b?.timestamp || '')
        && String(a?.content || '') === String(b?.content || '');
    }

    function findTailOverlapIndex(cached, incoming) {
      if (!Array.isArray(cached) || !cached.length || !Array.isArray(incoming) || !incoming.length) {
        return -1;
      }
      const anchor = cached[cached.length - 1];
      const anchorTs = anchor?.timestamp;
      if (!anchorTs) return -1;
      for (let i = incoming.length - 1; i >= 0; i -= 1) {
        if (incoming[i].timestamp === anchorTs) return i;
      }
      if (anchor?.role === 'user') {
        const anchorText = String(anchor.content || '').trim();
        if (anchorText) {
          for (let i = incoming.length - 1; i >= 0; i -= 1) {
            const m = incoming[i];
            if (m?.role === 'user' && String(m.content || '').trim() === anchorText) return i;
          }
        }
      }
      return -1;
    }

    function filterMessagesAlreadyInDom(msgs) {
      if (!Array.isArray(msgs) || !msgs.length) return msgs;
      const container = getMessagesEl();
      if (!container) return msgs;
      return msgs.filter((m) => {
        const ts = String(m?.timestamp || '').trim();
        if (ts && messageTimestampInDom(ts)) return false;
        if (m?.role === 'user') {
          const text = String(m.content || '').trim();
          if (!text) return true;
          const users = container.querySelectorAll('.msg.user');
          for (let i = users.length - 1; i >= 0; i -= 1) {
            const node = users[i];
            const body = (node.querySelector('.msg-body')?.textContent || '').trim();
            if (body === text) return false;
          }
        }
        if (m?.role === 'assistant') {
          const md = String(m.content || '').trim();
          if (md && assistantContentAlreadyInDom(md)) return false;
        }
        return true;
      });
    }

    function appendTailMessageElements(msgs) {
      const container = getMessagesEl();
      if (!container || !msgs.length) return;
      const sessionId = currentSessionId;
      const run = activeRuns.get(sessionId);
      let msgsToAppend = filterStaleAssistantAppends(sessionId, msgs);
      msgsToAppend = filterMessagesAlreadyInDom(msgsToAppend);
      if (!msgsToAppend.length) return;
      let mergeShell = null;
      const tailAssistants = msgsToAppend.filter(
        (m) => m.role === 'assistant' && String(m.content || '').trim(),
      );
      if (tailAssistants.length) {
        mergeShell = resolveTailMergeShell(sessionId);
        const lastAssistant = tailAssistants[tailAssistants.length - 1];
        if (mergeShell && lastAssistant && mergeAssistantIntoShell(sessionId, mergeShell, lastAssistant)) {
          mergeShell = null;
          msgsToAppend = msgs.filter((m) => m !== lastAssistant);
        } else if (lastAssistant && assistantContentAlreadyInDom(lastAssistant.content)) {
          msgsToAppend = msgs.filter((m) => m !== lastAssistant);
        }
      }
      if (!msgsToAppend.length) return;
      const insertBefore = run?.shellEl
        || mergeShell
        || document.getElementById('typing-indicator')
        || null;
      const frag = document.createDocumentFragment();
      msgsToAppend.forEach((m) => frag.appendChild(buildMessageElement(m)));
      if (insertBefore && insertBefore.parentElement === container) {
        container.insertBefore(frag, insertBefore);
      } else {
        container.appendChild(frag);
      }
      bindMessagesMediaLoadScroll(container);
      hydrateAvatars(container);
    }

    function patchLastCachedMessageElement(m) {
      const container = getMessagesEl();
      if (!container) return false;
      const candidates = [...container.querySelectorAll('.msg:not(.streaming)')];
      const last = candidates[candidates.length - 1];
      if (!last) return false;
      if (last.dataset.timestamp !== m.timestamp) {
        if (m.role !== 'user' || !last.classList.contains('user')) return false;
        const lastText = (last.querySelector('.msg-body')?.textContent || '').trim();
        const nextText = String(m.content || '').trim();
        if (!nextText || lastText !== nextText) return false;
        last.dataset.timestamp = m.timestamp;
      }
      if (m.role === 'assistant') {
        const bodyEl = last.querySelector('.msg-body');
        const nextMd = String(m.content || '').trim();
        const nextFiles = m.files || [];
        const nextImages = m.images || [];
        if (getMessageMarkdown(bodyEl) === nextMd && !nextFiles.length && !nextImages.length) return true;
        setAssistantMessageBody(last, nextMd, { files: nextFiles, images: nextImages });
        ensureAssistantShareButton(last);
        return true;
      }
      const bodyEl = last.querySelector('.msg-body');
      const text = String(m.content || '').trim();
      const attachmentHtml = `${renderMessageImages(m.images || [])}${renderMessageFiles(m.files || [])}`;
      const bodyHtml = `${attachmentHtml}${text ? escapeHtml(text).replace(/\n/g, '<br>') : ''}`;
      if (bodyEl && bodyEl.innerHTML !== bodyHtml) {
        bodyEl.innerHTML = bodyHtml || attachmentHtml;
      }
      syncUserMessageLabelRow(last, mergeUserMessageAuthorFields(m, null));
      bindMessagesMediaLoadScroll(container);
      return true;
    }

    function trySyncTailMessages(sessionId, cached, newMsgs, newMeta, restoreFromBottom, scrollPinnedIntent = false) {
      if (!Array.isArray(cached) || !cached.length || !Array.isArray(newMsgs) || !newMsgs.length) {
        return false;
      }
      const overlapIdx = findTailOverlapIndex(cached, newMsgs);
      if (overlapIdx < 0) return false;

      const anchor = cached[cached.length - 1];
      const overlapMsg = newMsgs[overlapIdx];
      const appendSlice = newMsgs.slice(overlapIdx + 1);
      const updateAnchor = !messagesEqualForSync(anchor, overlapMsg);

      let merged = cached.slice();
      if (updateAnchor) merged[merged.length - 1] = mergeUserMessageAuthorFields(overlapMsg, anchor);
      if (appendSlice.length) merged = merged.concat(appendSlice);

      if (!appendSlice.length && !updateAnchor) {
        rememberSessionMessages(sessionId, merged, newMeta);
        if (
          sessionId === currentSessionId
          && messagesHaveAssistantSinceLastUser(merged)
          && (
            findOrphanStreamingShell(sessionId)
            || tailAssistantBubbleCount(sessionId) > 1
          )
        ) {
          return false;
        }
        if (sessionId === currentSessionId && !messagesDomHasConversation()) {
          return false;
        }
        if (sessionId === currentSessionId && !messagesDomMatchesSession(sessionId)) {
          return false;
        }
        if (sessionId === currentSessionId && countLoadedMessageElements() !== merged.length) {
          return false;
        }
        if (sessionId === currentSessionId) {
          ensureDeferredRestartPendingInDom(sessionId, merged);
        }
        return true;
      }

      rememberSessionMessages(sessionId, merged, newMeta);

      if (sessionId !== currentSessionId) return true;

      const container = getMessagesEl();
      if (!container || container.querySelector('.empty-state')) return false;
      if (!messagesDomMatchesSession(sessionId)) return false;

      if (updateAnchor) patchLastCachedMessageElement(overlapMsg);
      if (appendSlice.length) {
        if (
          appendSlice.some(
            (m) => m?.role === 'assistant' && isDeferredRestartCompleteText(m.content),
          )
        ) {
          removeDeferredRestartPendingShells(container);
        }
        appendTailMessageElements(appendSlice);
      }
      updateMessagesDomFingerprint(sessionId, merged, newMeta);

      if (pendingScrollToTimestamp) {
        /* 保持搜索跳转逻辑，不做滚动干预 */
      } else if (restoreFromBottom != null) {
        restoreMessagesScrollFromBottom(restoreFromBottom);
      } else if (scrollPinnedIntent || messagesPinnedToBottom) {
        messagesPinnedToBottom = true;
        scheduleScrollMessagesToBottom();
      }
      updateScrollToBottomBtn();
      updateLoadOlderButton(sessionId);
      return true;
    }

    function tryMergeExpandedHistory(sessionId, cached, incoming, pageMeta, restoreFromBottom, scrollPinnedIntent = false) {
      if (!Array.isArray(cached) || !cached.length || !Array.isArray(incoming) || !incoming.length) {
        return false;
      }
      if (cached.length <= incoming.length) return false;

      const headTs = incoming[0]?.timestamp;
      if (!headTs) return false;

      let prefixLen = -1;
      for (let i = 0; i < cached.length; i += 1) {
        if (cached[i]?.timestamp === headTs) {
          prefixLen = i;
          break;
        }
      }
      if (prefixLen <= 0) return false;

      const prefix = cached.slice(0, prefixLen);
      const tailSlice = cached.slice(prefixLen);
      const overlapIdx = findTailOverlapIndex(tailSlice, incoming);
      if (overlapIdx < 0) return false;

      let mergedTail = tailSlice.slice();
      const overlapMsg = incoming[overlapIdx];
      const appendSlice = incoming.slice(overlapIdx + 1);
      if (!messagesEqualForSync(mergedTail[overlapIdx], overlapMsg)) {
        mergedTail[overlapIdx] = overlapMsg;
      }
      if (appendSlice.length) mergedTail = mergedTail.concat(appendSlice);

      const merged = prefix.concat(mergedTail);
      const mergedMeta = {
        ...pageMeta,
        has_older: true,
        total: Math.max(Number(pageMeta.total || 0), merged.length),
        offset: Math.min(Number(pageMeta.offset || 0), prefixLen),
        messages_mtime: pageMeta.messages_mtime || sessionMessagesMtimeFromList(sessionId),
      };
      rememberSessionMessages(sessionId, merged, mergedMeta);
      if (sessionId !== currentSessionId) return true;

      if (trySyncTailMessages(sessionId, merged, incoming, mergedMeta, restoreFromBottom, scrollPinnedIntent)) {
        return true;
      }
      return false;
    }

    async function loadMessages(opts = {}) {
      if (!currentSessionId) { showEmptyState(); return; }
      const sessionId = currentSessionId;
      const loadSeq = opts.loadSeq ?? activeSessionLoadSeq;
      const isStaleMessagesLoad = () =>
        sessionId !== currentSessionId || loadSeq !== activeSessionLoadSeq;
      if (!messagesDomHasConversation()) {
        beginSessionMessagesLoading({ overlay: false });
      }
      const refetch = !!opts.force;
      const repaint = !!opts.repaint;
      const deferPaintUntilFetch = refetch && repaint;
      if (refetch) {
        sessionMessagesEtags.delete(sessionId);
      }
      if (repaint && messagesDomMatchesSession(sessionId)) {
        clearMessagesDomRendered();
      }
      if (opts.messagesPrefetch) {
        try { await opts.messagesPrefetch; } catch { /* ignore */ }
      }
      if (isStaleMessagesLoad()) return;
      let restoreFromBottom = null;
      let scrollPinnedIntent = true;
      if (!pendingScrollToTimestamp) {
        const scrollState = resolveMessagesScrollState(sessionId);
        messagesPinnedToBottom = scrollState.pinnedToBottom;
        restoreFromBottom = scrollState.fromBottom;
        scrollPinnedIntent = scrollState.pinnedToBottom && scrollState.fromBottom == null;
      } else {
        messagesPinnedToBottom = false;
        scrollPinnedIntent = false;
      }
      const progressiveFirstPaint = !!opts.progressive && !pendingScrollToTimestamp;
      try {
        const cached = sessionMessagesCache.get(sessionId);
        const cachedMeta = sessionMessagesMeta(sessionId);
        const cachedFingerprint = cached ? sessionMessagesFingerprint(cached, cachedMeta) : '';
        const serverMtime = sessionMessagesMtimeFromList(sessionId);
        const cachedMtime = Number(cachedMeta?.mtime || 0);
        const skipFetch = !refetch
          && !pendingScrollToTimestamp
          && cached?.length
          && serverMtime > 0
          && cachedMtime > 0
          && serverMtime === cachedMtime
          && !sessionCacheAwaitingAssistantReply(sessionId)
          && !sessionMessagesStaleAgainstIndex(sessionId);
        const cacheFresh = cached?.length && (
          skipFetch
          || serverMtime <= 0
          || cachedMtime <= 0
          || serverMtime === cachedMtime
        );
        const paintOpts = { progressive: progressiveFirstPaint, loadSeq };
        if (cached?.length && !deferPaintUntilFetch) {
          if (!messagesDomMatchesSession(sessionId)) {
            renderLoadedMessages(sessionId, cached, restoreFromBottom, paintOpts);
          } else if (cacheFresh) {
            if (!repaint && !refetch && canSkipMessagesRender(sessionId, cached, cachedMeta)) {
              syncMessagesViewChrome(sessionId, restoreFromBottom, { touchScroll: false });
            } else {
              renderLoadedMessages(sessionId, cached, restoreFromBottom, paintOpts);
            }
          }
        }
        if (skipFetch) {
          if (deferPaintUntilFetch && cached?.length) {
            renderLoadedMessages(sessionId, cached, restoreFromBottom, paintOpts);
          }
          ensureMessagesDomPaintedFromCache(sessionId, loadSeq, restoreFromBottom, paintOpts);
          return;
        }

        ensureMessagesDomPaintedFromCache(sessionId, loadSeq, restoreFromBottom, paintOpts);

        loadMessagesAbort?.abort();
        const abortCtrl = new AbortController();
        loadMessagesAbort = abortCtrl;
        const { signal } = abortCtrl;

        let data;
        try {
          const msgHeaders = {};
          const cachedEtag = sessionMessagesEtags.get(sessionId);
          if (cachedEtag && !refetch) {
            msgHeaders['If-None-Match'] = cachedEtag;
          }
          data = await api(
            `/api/sessions/${sessionId}/messages?tail=${MESSAGES_TAIL_DEFAULT}`,
            { signal, headers: msgHeaders, cache: 'no-store' },
          );
          if (
            data?.__notModified
            && (
              !sessionMessagesCache.get(sessionId)?.length
              || sessionCacheAwaitingAssistantReply(sessionId)
            )
          ) {
            data = await api(
              `/api/sessions/${sessionId}/messages?tail=${MESSAGES_TAIL_DEFAULT}`,
              { signal, cache: 'no-store' },
            );
          }
        } catch (err) {
          if (err?.name === 'AbortError') return;
          throw err;
        }
        if (signal.aborted || isStaleMessagesLoad()) return;
        if (data?.__notModified) {
          if (data.__etag) sessionMessagesEtags.set(sessionId, data.__etag);
          const cachedLive = sessionMessagesCache.get(sessionId) || cached;
          const cachedLiveMeta = sessionMessagesMeta(sessionId) || cachedMeta;
          if (cachedLive?.length) {
            if (!repaint && !refetch && canSkipMessagesRender(sessionId, cachedLive, cachedLiveMeta)) {
              syncMessagesViewChrome(sessionId, restoreFromBottom, { touchScroll: false });
            } else {
              renderLoadedMessages(sessionId, cachedLive, restoreFromBottom, paintOpts);
            }
          } else {
            const refetched = await api(
              `/api/sessions/${sessionId}/messages?tail=${MESSAGES_TAIL_DEFAULT}`,
              { signal, cache: 'no-store' },
            );
            if (signal.aborted || isStaleMessagesLoad()) return;
            if (!refetched?.__notModified && Array.isArray(refetched?.messages)) {
              data = refetched;
            } else {
              ensureMessagesDomPaintedFromCache(sessionId, loadSeq, restoreFromBottom, paintOpts);
              return;
            }
          }
          if (data?.__notModified) {
            ensureMessagesDomPaintedFromCache(sessionId, loadSeq, restoreFromBottom, paintOpts);
            return;
          }
        }
        if (data?.__etag) sessionMessagesEtags.set(sessionId, data.__etag);
        const msgs = mergeOptimisticSessionMessages(sessionId, data.messages || []);
        const pageMeta = {
          total: data.total,
          has_older: data.has_older,
          offset: data.offset,
          messages_mtime: data.messages_mtime || serverMtime,
        };
        const cachedForSync = sessionMessagesCache.get(sessionId) || cached || [];
        const nextFingerprint = sessionMessagesFingerprint(msgs, pageMeta);
        if (!repaint && nextFingerprint === cachedFingerprint) {
          rememberSessionMessages(sessionId, msgs, pageMeta);
          if (canSkipMessagesRender(sessionId, msgs, pageMeta)) {
            syncMessagesViewChrome(sessionId, restoreFromBottom, { touchScroll: false });
            return;
          }
          if (
            cachedForSync?.length
            && trySyncTailMessages(sessionId, cachedForSync, msgs, pageMeta, restoreFromBottom, scrollPinnedIntent)
          ) {
            return;
          }
          if (
            cachedForSync?.length
            && tryMergeExpandedHistory(sessionId, cachedForSync, msgs, pageMeta, restoreFromBottom, scrollPinnedIntent)
          ) {
            return;
          }
          if (!refetch) {
            renderLoadedMessages(sessionId, msgs, restoreFromBottom, paintOpts);
            return;
          }
        }
        if (
          !repaint
          && !refetch
          && cachedForSync?.length
          && trySyncTailMessages(sessionId, cachedForSync, msgs, pageMeta, restoreFromBottom, scrollPinnedIntent)
        ) {
          return;
        }
        if (
          !repaint
          && !refetch
          && cachedForSync?.length
          && tryMergeExpandedHistory(sessionId, cachedForSync, msgs, pageMeta, restoreFromBottom, scrollPinnedIntent)
        ) {
          return;
        }
        rememberSessionMessages(sessionId, msgs, pageMeta);
        renderLoadedMessages(sessionId, msgs, restoreFromBottom, paintOpts);
      } finally {
        if (pendingScrollToTimestamp && sessionId === currentSessionId) {
          void fulfillPendingScrollToTimestamp();
        }
        const cachedForPoll = sessionMessagesCache.get(sessionId);
        if (cachedForPoll?.length) {
          syncDeferredRestartFollowupPoll(sessionId, cachedForPoll);
        }
        if (sessionId === currentSessionId && !messagesDomHasConversation()) {
          const scrollState = resolveMessagesScrollState(sessionId);
          ensureMessagesDomPaintedFromCache(
            sessionId,
            activeSessionLoadSeq,
            scrollState.fromBottom,
            { loadSeq: activeSessionLoadSeq },
          );
          repaintEmptyMessagesFromCache(sessionId);
        }
        if (sessionId === currentSessionId && !messagesDomHasConversation()) {
          endSessionMessagesLoading();
        }
      }
    }

    async function loadOlderMessages() {
      if (!currentSessionId || loadingOlderMessages) return;
      await loadOlderMessagesForSession(currentSessionId);
    }

    function publicDisplayName(label) {
      const name = String(label || '').trim();
      if (!name) return name;
      const parts = name.match(/[\u3400-\u4DBF\u4E00-\u9FFF]+/g);
      if (parts && parts.length) return parts.join('');
      return name;
    }

    function authUserDisplayName(user) {
      if (!user) return '你';
      const raw = (user.displayName || user.staffId || '用户').trim() || '你';
      return publicDisplayName(raw) || '你';
    }

    function appendMessage(role, content, scroll = true, images = [], files = [], timestamp = '', authorLabel = '') {
      const container = document.getElementById('messages');
      if (container.querySelector('.empty-state')) dismissEmptyState(container);
      const authorSnap = role === 'user' ? currentUserMessageAuthorSnapshot() : null;
      const el = buildMessageElement({
        role,
        content,
        images,
        files,
        timestamp: timestamp || new Date().toISOString(),
        author_label: authorLabel || authorSnap?.author_label || '',
        author_id: authorSnap?.author_id || '',
        author_avatar_url: authorSnap?.author_avatar_url || '',
      });
      container.appendChild(el);
      bindMessagesMediaLoadScroll(container);
      hydrateAvatars(el);
      if (scroll) scheduleScrollMessagesToBottom({ force: true });
      return el;
    }

    function sleepMs(ms) {
      return new Promise((resolve) => setTimeout(resolve, ms));
    }

    async function fetchActiveRun(sessionId, { retries = 5 } = {}) {
      for (let i = 0; i < retries; i += 1) {
        try {
          return await api(`/api/sessions/${sessionId}/active-run`);
        } catch {
          if (i < retries - 1) await sleepMs(400 * (i + 1));
        }
      }
      return null;
    }

    function assistantReplyAfterLastUser(msgs) {
      if (!Array.isArray(msgs) || !msgs.length) return null;
      let lastUserIdx = -1;
      for (let i = msgs.length - 1; i >= 0; i -= 1) {
        if (msgs[i].role === 'user') {
          lastUserIdx = i;
          break;
        }
      }
      if (lastUserIdx < 0) return null;
      for (let i = lastUserIdx + 1; i < msgs.length; i += 1) {
        if (msgs[i].role === 'assistant' && String(msgs[i].content || '').trim()) {
          return msgs[i];
        }
      }
      return null;
    }

    function messagesHaveAssistantSinceLastUser(msgs) {
      return !!assistantReplyAfterLastUser(msgs);
    }

    /** 本地已 append 用户消息、服务端尚未落盘时，勿用服务端上一轮 assistant 填充当前 shell。 */
    function sessionCacheAwaitingAssistantReply(sessionId) {
      const cached = sessionMessagesCache.get(String(sessionId || '').trim()) || [];
      if (!cached.length) return false;
      return cached[cached.length - 1]?.role === 'user';
    }

    function pendingUserMatchesServerTail(pendingUser, serverMsgs) {
      if (!pendingUser || pendingUser.role !== 'user') return false;
      const list = Array.isArray(serverMsgs) ? serverMsgs : [];
      if (!list.length) return false;
      const pendingText = String(pendingUser.content || '').trim();
      if (!pendingText) return false;
      for (let i = list.length - 1; i >= 0; i -= 1) {
        const m = list[i];
        if (m?.role !== 'user') continue;
        return String(m.content || '').trim() === pendingText;
      }
      return false;
    }

    async function refreshSessionMessagesCacheFromServer(sessionId) {
      const sid = String(sessionId || '').trim();
      if (!sid) return false;
      try {
        sessionMessagesEtags.delete(sid);
        const data = await api(
          `/api/sessions/${sid}/messages?tail=${MESSAGES_TAIL_DEFAULT}`,
          { cache: 'no-store' },
        );
        if (!Array.isArray(data?.messages)) return false;
        const pageMeta = {
          total: data.total,
          has_older: data.has_older,
          offset: data.offset,
          messages_mtime: data.messages_mtime || sessionMessagesMtimeFromList(sid),
        };
        const msgs = mergeOptimisticSessionMessages(sid, data.messages || []);
        rememberSessionMessages(sid, msgs, pageMeta);
        if (data.__etag) sessionMessagesEtags.set(sid, data.__etag);
        return true;
      } catch {
        return false;
      }
    }

    function mergeOptimisticTailUser(sessionId, serverMsgs) {
      let list = Array.isArray(serverMsgs) ? [...serverMsgs] : [];
      if (!sessionCacheAwaitingAssistantReply(sessionId)) return list;
      const cached = sessionMessagesCache.get(String(sessionId || '').trim()) || [];
      const pendingUser = cached[cached.length - 1];
      if (!pendingUser?.timestamp || pendingUser.role !== 'user') return list;
      const enrichedPending = mergeUserMessageAuthorFields(pendingUser, pendingUser);
      if (list.some((m) => m?.timestamp === pendingUser.timestamp)) {
        return list.map((m) => (
          m?.timestamp === pendingUser.timestamp
            ? mergeUserMessageAuthorFields(m, enrichedPending)
            : m
        ));
      }
      if (pendingUserMatchesServerTail(pendingUser, list)) {
        for (let i = list.length - 1; i >= 0; i -= 1) {
          const m = list[i];
          if (m?.role !== 'user') continue;
          if (String(m.content || '').trim() !== String(pendingUser.content || '').trim()) continue;
          list[i] = mergeUserMessageAuthorFields(m, enrichedPending);
          break;
        }
        return list;
      }
      return list.concat([enrichedPending]);
    }

    /** SSE done 已 finalize、assistant 尚未落盘时，保留本地 tail assistant，避免 loadMessages 重绘冲掉。 */
    function mergeOptimisticSessionMessages(sessionId, serverMsgs) {
      const list = mergeOptimisticTailUser(sessionId, serverMsgs);
      const cached = sessionMessagesCache.get(String(sessionId || '').trim()) || [];
      const pendingAssist = assistantReplyAfterLastUser(cached);
      if (!pendingAssist || messagesHaveAssistantSinceLastUser(list)) return list;
      const content = String(pendingAssist.content || '').trim();
      if (!content) return list;
      return list.concat([pendingAssist]);
    }

    function resolveDoneAssistantDisplayText(dataText, run, shellEl) {
      const fromDone = String(dataText || '').trim();
      if (fromDone) return fromDone;
      const preview = String(run?.lastStream?.display?.answerPreview || '').trim();
      if (preview) return preview;
      if (shellEl?.isConnected) {
        const fromDom = String(getMessageMarkdown(shellEl.querySelector('.msg-body')) || '').trim();
        if (fromDom && fromDom !== '（无回复）') return fromDom;
      }
      return '';
    }

    function commitAssistantReplyToSessionCache(sessionId, content, extras = {}) {
      const body = String(content || '').trim();
      if (!body) return;
      appendAssistantMessageToSessionCache(sessionId, {
        role: 'assistant',
        content: body,
        timestamp: extras.timestamp || new Date().toISOString(),
        files: Array.isArray(extras.files) ? extras.files : [],
        images: Array.isArray(extras.images) ? extras.images : [],
      });
    }

    function filterStaleAssistantAppends(sessionId, msgs) {
      if (!sessionCacheAwaitingAssistantReply(sessionId)) return msgs;
      return (msgs || []).filter((m) => m?.role !== 'assistant');
    }

    /** 落盘消息已含 assistant 回复时，勿再挂载 streaming shell（避免双气泡）。 */
    function shouldAppendStreamingShell(sessionId, msgs) {
      const run = activeRuns.get(sessionId);
      if (!run) return false;
      if (messagesHaveAssistantSinceLastUser(msgs)) {
        if (run.shellEl) run.shellEl = null;
        return false;
      }
      return true;
    }

    async function hasAssistantReplySinceLastUser(sessionId) {
      try {
        const data = await api(`/api/sessions/${sessionId}/messages?tail=30`);
        return messagesHaveAssistantSinceLastUser(data.messages || []);
      } catch { /* ignore */ }
      return false;
    }

    async function recoverRunStream(sessionId, runId, reconnectAttempt = 0, runToken = '') {
      const MAX_ATTEMPTS = 24;
      const delays = [300, 500, 800, 1200, 2000, 3000, 4000, 5000];

      for (let attempt = reconnectAttempt; attempt < MAX_ATTEMPTS; attempt += 1) {
        if (!isActiveRun(sessionId, { runToken, runId })) return;
        if (attempt > reconnectAttempt) {
          await sleepMs(delays[Math.min(attempt, delays.length - 1)]);
        }

        const active = await fetchActiveRun(sessionId, { retries: 3 });
        if (active?.active && active.run_id) {
          await attachRunStream(sessionId, active.run_id, { reconnectAttempt: attempt + 1, runToken });
          return;
        }

        if (await hasAssistantReplySinceLastUser(sessionId)) {
          if (currentSessionId === sessionId) {
            await finalizeStreamingShellFromServer(sessionId);
            await loadMessages();
          }
          if (isActiveRun(sessionId, { runToken, runId })) {
            finishRun(sessionId, runToken);
          } else {
            refreshSessionListAfterRunEnd(sessionId);
          }
          return;
        }
      }

      throw new Error('流式连接中断');
    }

    function attachRunStream(sessionId, runId, { reconnectAttempt = 0, runToken = '' } = {}) {
      let assistantEl = null;

      return new Promise((resolve, reject) => {
        const existing = activeRuns.get(sessionId);
        if (!existing) {
          reject(new Error('run state missing'));
          return;
        }
        if (runToken && existing.runToken !== runToken) {
          resolve();
          return;
        }
        if (existing.cancelling) {
          resolve();
          return;
        }

        existing.eventSource?.close();

        const es = new EventSource(`${API}/api/chat/stream/${runId}`);
        let streamSettled = false;
        const settleStream = () => {
          if (streamSettled) return;
          streamSettled = true;
          resolve();
        };
        activeRuns.set(sessionId, {
          ...existing,
          pending: false,
          eventSource: es,
          runId,
          streamDetach({ orphan = false, shellEl: orphanShellEl = null } = {}) {
            es.onmessage = null;
            es.onerror = null;
            if (orphan) {
              listenOrphanRunStream(sessionId, es, { shellEl: orphanShellEl || existing.shellEl });
            } else {
              es.close();
            }
            settleStream();
          },
        });
        if (sessionId === currentSessionId) {
          void syncActiveRunPushPref(isPushResultChecked());
        }
        updateInputState();
        loadSessions({ lite: true });
        syncSessionListFromCache();
        startRunStreamPoll(sessionId);

        const isViewing = () => currentSessionId === sessionId;

        es.onmessage = (ev) => {
          if (!isActiveRun(sessionId, { runToken, runId })) {
            es.close();
            settleStream();
            return;
          }
          const data = JSON.parse(ev.data);
          if (data.type === 'ack') {
            updateRunStatus(sessionId, { ack: data.line || '' });
          } else if (data.type === 'status') {
            patchRunStatusFromServer(sessionId, {
              elapsed: data.elapsed_line || '',
              batch: data.batch_line || '',
              external: data.external_line || '',
            });
            if ('phase_line' in data && data.phase_line) {
              if (isViewing() && !assistantEl) {
                assistantEl = ensureStreamingShell(sessionId);
                activeRuns.get(sessionId).shellEl = assistantEl;
              }
              applyLifecyclePhaseToStream(sessionId, data.phase_line);
            }
          } else if (data.type === 'delta') {
            const display = rememberRunStreamState(sessionId, data.markdown || '', data.process);
            if (!isViewing()) return;
            if (!assistantEl) {
              assistantEl = ensureStreamingShell(sessionId);
              activeRuns.get(sessionId).shellEl = assistantEl;
            }
            if (display) {
              scheduleStreamingMsgBodyUpdate(assistantEl, display);
            }
          } else if (data.type === 'terminal') {
            handleTerminalStreamEvent(sessionId, data);
          } else if (data.type === 'done') {
            if (!isActiveRun(sessionId, { runToken, runId })) {
              es.close();
              settleStream();
              return;
            }
            stopRunStreamPoll(sessionId, runToken);
            const doneRun = activeRuns.get(sessionId);
            if (doneRun?.cancelWatchdog) {
              clearTimeout(doneRun.cancelWatchdog);
            }
            let restoredSentDraft = false;
            if (shouldRestoreSentDraft(doneRun, data.text)) {
              restoredSentDraft = restoreSentDraft(sessionId, { runToken });
            }
            if (shouldTreatDoneAsDeferredRestart(sessionId, data)) {
              assistantEl = applyDeferredWebAgentRestartUi(sessionId, assistantEl);
            } else if (isViewing()) {
              if (!assistantEl) {
                assistantEl = ensureStreamingShell(sessionId);
                activeRuns.get(sessionId).shellEl = assistantEl;
              }
              let displayText = resolveDoneAssistantDisplayText(data.text, doneRun, assistantEl);
              if (
                displayText
                && shouldRestoreSentDraft(doneRun, data.text)
                && !restoredSentDraft
                && hasUserInputDuringRun(sessionId)
              ) {
                displayText = stripRetryHintMarkdown(displayText);
              }
              if (!String(displayText || '').trim()) {
                assistantEl?.remove();
                if (doneRun) doneRun.shellEl = null;
              } else {
                finalizeStreamingShell(sessionId, assistantEl, displayText, {
                  files: Array.isArray(data.files) ? data.files : [],
                  terminal: data,
                });
                commitAssistantReplyToSessionCache(sessionId, displayText, {
                  files: Array.isArray(data.files) ? data.files : [],
                });
                if (!data.files?.length) {
                  void refreshAssistantAttachmentsFromServer(sessionId, assistantEl);
                }
                scrollMessagesToBottom({ force: true });
              }
            } else if (data.text) {
              commitAssistantReplyToSessionCache(sessionId, data.text, {
                files: Array.isArray(data.files) ? data.files : [],
              });
            }
            if (!data.deferred_web_agent_restart && isDeferredRestartSubmittedText(data.text)) {
              syncDeferredRestartFollowupPoll(sessionId, [
                ...(sessionMessagesCache.get(sessionId) || []),
                { role: 'assistant', content: data.text },
              ]);
            }
            handleDingtalkPushResult(data.dingtalk_push);
            es.close();
            finishRun(sessionId, runToken);
            settleStream();
          } else if (data.type === 'error') {
            if (!isActiveRun(sessionId, { runToken, runId })) {
              es.close();
              settleStream();
              return;
            }
            stopRunStreamPoll(sessionId, runToken);
            const errorRun = activeRuns.get(sessionId);
            if (isViewing()) {
              if (!assistantEl) {
                assistantEl = ensureStreamingShell(sessionId);
                activeRuns.get(sessionId).shellEl = assistantEl;
              }
              showRunFailureReply(
                sessionId,
                assistantEl,
                data.text || `⚠️ ${data.message || 'Agent 执行失败'}`,
                errorRun,
              );
            } else if (errorRun) {
              errorRun.failed = true;
            }
            es.close();
            finishRun(sessionId, runToken);
            settleStream();
          }
        };

        es.onerror = async () => {
          if (streamSettled) return;
          if (activeRuns.get(sessionId)?.failed) {
            settleStream();
            return;
          }
          if (es.readyState === EventSource.CONNECTING) return;
          es.close();
          if (!isActiveRun(sessionId, { runToken, runId })) {
            settleStream();
            return;
          }
          try {
            await recoverRunStream(sessionId, runId, reconnectAttempt, runToken);
            settleStream();
          } catch (err) {
            if (!isActiveRun(sessionId, { runToken, runId })) {
              settleStream();
              return;
            }
            const failRun = activeRuns.get(sessionId);
            if (failRun?.failed || failureReplyAlreadyVisible(`⚠️ ${err.message}`)) {
              if (failRun) failRun.failed = true;
              settleStream();
              return;
            }
            reject(err);
          }
        };
      });
    }

    async function tryReconnectActiveRun(sessionId) {
      const sid = String(sessionId || '').trim();
      if (!sid) return;

      const existing = activeRuns.get(sid);
      if (existing?.sentDraft) {
        const es = existing.eventSource;
        if (es && es.readyState !== EventSource.CLOSED) return;
        if (existing.pending && !existing.runId) return;
        if (existing.runId) {
          try {
            await attachRunStream(sid, existing.runId, { runToken: existing.runToken });
          } catch (err) {
            if (currentSessionId === sid) {
              document.getElementById('typing-indicator')?.remove();
              showRunFailureReply(sid, existing.shellEl, `⚠️ ${err.message}`, existing);
            }
          }
        }
        return;
      }
      if (existing) {
        const es = existing.eventSource;
        if (es && es.readyState !== EventSource.CLOSED) return;
        if (existing.pending && !existing.runId) return;
        if (existing.runId) {
          try {
            await attachRunStream(sid, existing.runId, { runToken: existing.runToken });
          } catch (err) {
            if (currentSessionId === sid) {
              document.getElementById('typing-indicator')?.remove();
              showRunFailureReply(sid, existing.shellEl, `⚠️ ${err.message}`, existing);
            }
          }
          return;
        }
      }

      let data;
      try {
        const headers = {};
        const cachedEtag = activeRunEtags.get(sid);
        if (cachedEtag) headers['If-None-Match'] = cachedEtag;
        data = await api(`/api/sessions/${sid}/active-run`, { headers });
        if (data.__notModified) {
          if (data.__etag) activeRunEtags.set(sid, data.__etag);
          return;
        }
        if (data.__etag) activeRunEtags.set(sid, data.__etag);
      } catch {
        return;
      }
      if (!data?.active || !data.run_id) {
        if (currentSessionId === sid && sessionCacheAwaitingAssistantReply(sid)) {
          await loadMessages({ force: true });
        }
        return;
      }
      if (activeRuns.get(sid)?.sentDraft) return;

      activeRuns.set(sid, {
        pending: false,
        eventSource: null,
        runId: data.run_id,
        runToken: makeRunToken(),
        cancelling: false,
        status: {
          ack: data.ack_line || '',
          lifecycle: '',
          phase: '',
          batch: data.batch_line || '',
          external: data.external_line || '',
          elapsed: data.elapsed_line || '',
        },
        shellEl: null,
        sentDraft: null,
        terminal: { text: String(data.terminal_text || ''), seq: Number(data.terminal_seq) || 0 },
      });
      patchSessionCacheEntry(sid, { running: true });
      updateInputState();
      sortSessionsCache();
      syncSessionListFromCache();

      if (currentSessionId === sid) {
        if (data.ack_line || data.phase_line || data.elapsed_line || data.batch_line || data.external_line || data.markdown || data.process) {
          const shell = ensureStreamingShell(sid);
          activeRuns.get(sid).shellEl = shell;
          renderRunStatusEl(shell.querySelector('.run-status'), activeRuns.get(sid).status);
          if (data.phase_line) {
            applyLifecyclePhaseToStream(sid, data.phase_line, {
              markdown: data.markdown || '',
              process: data.process,
            });
          } else if (data.markdown || data.process) {
            const display = rememberRunStreamState(sid, data.markdown || '', data.process);
            if (display) scheduleStreamingMsgBodyUpdate(shell, display);
          }
        } else {
          const typingEl = document.createElement('div');
          typingEl.className = 'typing';
          typingEl.id = 'typing-indicator';
          typingEl.textContent = data.phase_line || data.ack_line || data.elapsed_line || 'Agent 思考中…';
          document.getElementById('messages')?.appendChild(typingEl);
        }
      }

      const reconnectToken = activeRuns.get(sid)?.runToken || '';
      try {
        await attachRunStream(sid, data.run_id, { runToken: reconnectToken });
      } catch (err) {
        const run = activeRuns.get(sid);
        if (currentSessionId === sid) {
          document.getElementById('typing-indicator')?.remove();
          showRunFailureReply(sid, run?.shellEl, `⚠️ ${err.message}`, run);
        } else if (run) {
          run.failed = true;
        }
      } finally {
        finishRun(sid, reconnectToken);
      }
    }

    async function sendMessage(text, options = {}) {
      if (sessionRenameTarget && sessionRenameInputEl) {
        await saveSessionCustomTitle();
      }
      const message = (text || document.getElementById('input').value).trim();
      const attachmentSource = Array.isArray(options.attachments) ? options.attachments : pendingAttachments;
      const attachmentsToSend = attachmentSource.map(item => ({
        name: item.name,
        mime: item.mime,
        data_base64: item.data_base64,
      }));
      if ((!message && !attachmentsToSend.length) || currentSessionReadOnly) return;
      if (isGuestMode()) {
        goToLogin();
        return;
      }

      if (currentSessionId) {
        const cancelFlight = sessionCancelFlights.get(currentSessionId);
        if (cancelFlight) {
          sendAwaitingCancelFlight = true;
          updateInputState();
          try {
            await cancelFlight;
          } finally {
            sendAwaitingCancelFlight = false;
            updateInputState();
          }
        }
      }

      const priorRun = activeRuns.get(currentSessionId);
      if (priorRun && isCurrentSessionStreaming() && !priorRun.cancelling) return;

      if (!currentSessionId) {
        if (sessionBootstrapPromise) await sessionBootstrapPromise;
        else await createSession();
      }

      const sessionId = currentSessionId;
      const previewImages = attachmentSource
        .filter(item => item.kind === 'image')
        .map(item => item.previewUrl || (item.data_base64 ? `data:${item.mime || 'image/png'};base64,${item.data_base64}` : ''))
        .filter(src => String(src || '').trim());
      const previewFiles = attachmentSource.filter(item => item.kind !== 'image').map(item => ({
        url: '#', name: item.name, size: 0,
      }));
      const sentDraft = {
        text: message,
        attachments: attachmentSource.map(item => ({ ...item })),
      };
      clearRetryPlaceholder();
      if (!options.attachments) {
        document.getElementById('input').value = '';
        autoResizeInput();
        clearPendingAttachments();
        clearSessionInputDraft(sessionId);
      }
      const userTimestamp = new Date().toISOString();
      const authorSnap = currentUserMessageAuthorSnapshot();
      appendMessage('user', message, true, previewImages, previewFiles, userTimestamp, authorSnap.author_label);
      appendUserMessageToSessionCache(sessionId, {
        role: 'user',
        content: message,
        timestamp: userTimestamp,
        author_id: authorSnap.author_id,
        author_label: authorSnap.author_label,
        author_avatar_url: authorSnap.author_avatar_url,
      });
      sessionMessagesEtags.delete(sessionId);
      const runToken = makeRunToken();
      disposeRunResources(activeRuns.get(sessionId));
      activeRuns.set(sessionId, {
        pending: true,
        eventSource: null,
        runId: '',
        runToken,
        cancelling: false,
        status: { ack: '', lifecycle: '', phase: '', batch: '', elapsed: '' },
        shellEl: null,
        sentDraft,
        terminal: { text: '', seq: 0 },
      });
      patchSessionCacheEntry(sessionId, { running: true });
      if (currentSessionId === sessionId) {
        const shell = ensureStreamingShell(sessionId);
        activeRuns.get(sessionId).shellEl = shell;
        const bootstrapPhase = '正在连接 Agent…';
        rememberRunStreamState(sessionId, '', { phase: bootstrapPhase });
        scheduleStreamingMsgBodyUpdate(shell, { thinking: '', tools: [], phase: bootstrapPhase });
      }
      updateInputState();
      sortSessionsCache();
      syncSessionListFromCache();

      try {
        const { run_id } = await api('/api/chat', {
          method: 'POST',
          body: JSON.stringify({
            session_id: sessionId,
            message,
            attachments: attachmentsToSend,
            model: getSelectedModel(),
            enabled_external_agents: Array.isArray(options.enabledExternalAgents)
              ? options.enabledExternalAgents
              : getEnabledExternalAgents(),
            push_result_to_dingtalk: isPushResultChecked(),
            reply_mode: getReplyMode(),
          }),
        });

        const existing = activeRuns.get(sessionId);
        if (!existing || existing.runToken !== runToken || existing.cancelling) {
          return;
        }
        existing.runId = run_id;
        if (existing.shellEl?.isConnected) {
          existing.shellEl.dataset.runId = run_id;
          syncMsgTerminalButton(existing.shellEl, sessionId);
        }
        if (sessionId === currentSessionId) {
          void syncActiveRunPushPref(isPushResultChecked());
        }

        await attachRunStream(sessionId, run_id, { runToken });
      } catch (err) {
        if (!isActiveRun(sessionId, { runToken })) return;
        if (await hasAssistantReplySinceLastUser(sessionId)) {
          if (currentSessionId === sessionId) await loadMessages();
          return;
        }
        const run = activeRuns.get(sessionId);
        if (currentSessionId === sessionId) {
          document.getElementById('typing-indicator')?.remove();
          showRunFailureReply(sessionId, run?.shellEl, `⚠️ ${err.message}`, run);
        } else if (run) {
          run.failed = true;
        }
      } finally {
        const run = activeRuns.get(sessionId);
        if (!run || run.runToken !== runToken) return;
        if (run.eventSource) run.eventSource.close();
        if (shouldRestoreSentDraft(run)) restoreSentDraft(sessionId, { runToken });
        finishRun(sessionId, runToken);
      }
    }

    function autoResizeInput() {
      if (inputComposing) {
        inputComposeResizePending = true;
        return;
      }
      inputComposeResizePending = false;
      const ta = document.getElementById('input');
      ta.style.height = 'auto';
      ta.style.height = Math.min(ta.scrollHeight, 160) + 'px';
    }

    const PROMPT_STORAGE_KEY = 'web_agent_pending_prompt';

    function fillInputFromPrompt(text, options) {
      const opts = options || {};
      const input = document.getElementById('input');
      const piece = String(text ?? '');
      if (!input || input.readOnly || !piece) return false;
      if (opts.appendWhenOccupied && (input.value || '').trim()) {
        const base = input.value.replace(/\s+$/, '');
        input.value = base + '\n' + piece;
      } else {
        input.value = piece;
      }
      autoResizeInput();
      input.focus();
      syncCurrentSessionInputDraft();
      updateInputState();
      return true;
    }

    function fillInputFromMoaRecord({ text, attachments, suggestExternalAgents }) {
      if (currentSessionReadOnly) {
        alert('当前会话只读，无法编辑输入框');
        return false;
      }
      if (Array.isArray(suggestExternalAgents) && suggestExternalAgents.length) {
        ensureExternalAgentsEnabled(suggestExternalAgents);
      }
      clearPendingAttachments();
      fillInputFromPrompt(text);
      for (const item of attachments || []) {
        const isImage = item.kind === 'image' || (item.mime || '').startsWith('image/');
        const data_base64 = item.data_base64 || '';
        pendingAttachments.push({
          id: `${Date.now()}_${Math.random().toString(36).slice(2, 8)}`,
          name: item.name || (isImage ? 'screenshot.png' : 'attachment'),
          mime: item.mime || (isImage ? 'image/png' : 'application/octet-stream'),
          kind: isImage ? 'image' : 'file',
          previewUrl: isImage && data_base64
            ? `data:${item.mime || 'image/png'};base64,${data_base64}`
            : '',
          data_base64,
        });
      }
      renderPendingAttachments();
      syncCurrentSessionInputDraft();
      updateInputState();
      return true;
    }

    function applyIncomingPrompt() {
      const params = new URLSearchParams(window.location.search);
      const fromUrl = params.get('prompt');
      if (!fromUrl) return;
      fillInputFromPrompt(fromUrl);
      if (window.history && window.history.replaceState) {
        window.history.replaceState(null, '', window.location.pathname + window.location.hash);
      }
    }

    window.addEventListener('storage', (e) => {
      if (e.key !== PROMPT_STORAGE_KEY || !e.newValue) return;
      try {
        const data = JSON.parse(e.newValue);
        fillInputFromPrompt(String(data.text || ''));
      } catch { /* ignore */ }
    });

    window.addEventListener('message', (e) => {
      const data = e.data;
      if (!data || data.type !== 'web-agent-fill-prompt') return;
      fillInputFromPrompt(String(data.text || ''));
    });

    document.getElementById('input').addEventListener('input', () => {
      clearRetryPlaceholder();
      if (isWebAgentMobile()) {
        window.__WEB_AGENT_MOBILE_INPUT_BOOT__?.scheduleResize?.();
      } else {
        autoResizeInput();
      }
      if (!inputComposing) {
        if (isWebAgentMobile()) {
          if (mobileInputChromeRaf) return;
          mobileInputChromeRaf = requestAnimationFrame(() => {
            mobileInputChromeRaf = 0;
            if (!mobileInputFocusSuspend) scheduleMobileInputChromeUpdate();
          });
        } else {
          scheduleMobileInputChromeUpdate();
        }
      }
    });
    const chatInput = document.getElementById('input');
    chatInput.addEventListener('focus', () => {
      if (isWebAgentMobile()) mobileInputFocusSuspend = true;
    });
    chatInput.addEventListener('blur', () => {
      if (isWebAgentMobile()) mobileInputFocusSuspend = false;
    });
    chatInput.addEventListener('compositionstart', () => {
      inputComposing = true;
    });
    chatInput.addEventListener('compositionend', () => {
      inputComposing = false;
      if (inputComposeResizePending) autoResizeInput();
      syncCurrentSessionInputDraft();
      updateInputState();
    });
    chatInput.addEventListener('keydown', (e) => {
      if (e.key !== 'Enter') return;
      if (e.shiftKey || e.ctrlKey || e.metaKey || e.altKey) return;
      // 输入法组字期间 Enter 用于选词/确认，不应发送消息
      if (inputComposing || e.isComposing || e.keyCode === 229) return;
      e.preventDefault();
      sendMessage();
    });
    document.getElementById('btn-send').addEventListener('click', () => sendMessage());
    document.getElementById('btn-stop').addEventListener('click', () => cancelCurrentRun());
    document.getElementById('btn-new').addEventListener('click', () => createSession({ animate: true }));
    document.getElementById('btn-new-header').addEventListener('click', () => createSession({ animate: true }));
    document.getElementById('btn-sidebar-collapse')?.addEventListener('mousedown', (e) => e.stopPropagation());
    document.getElementById('btn-sidebar-collapse')?.addEventListener('click', () => setSidebarOpen(false));
    document.getElementById('btn-sidebar').addEventListener('click', () => setSidebarOpen(!sidebarOpen));
    const mobileSidebarScrim = document.getElementById('mobile-sidebar-scrim');
    const closeMobileSidebarFromScrim = (event) => {
      if (!isMobileSidebarDrawerOpen()) return;
      event?.preventDefault?.();
      event?.stopPropagation?.();
      setSidebarOpen(false);
    };
    mobileSidebarScrim?.addEventListener('click', closeMobileSidebarFromScrim);
    mobileSidebarScrim?.addEventListener('pointerup', closeMobileSidebarFromScrim);
    document.querySelector('.main')?.addEventListener('click', (event) => {
      if (!isMobileSidebarDrawerOpen()) return;
      if (event.target.closest('.left-panel, .sidebar-collapse-btn, .session-context-menu')) return;
      setSidebarOpen(false);
    });
    window.addEventListener('resize', () => {
      document.body.classList.toggle('sidebar-mobile-open', sidebarOpen && isMobileSidebarViewport());
      syncMobileSidebarScrim();
    });
    document.getElementById('session-search')?.addEventListener('input', (event) => {
      sessionSearchQuery = event.target.value || '';
      applySessionSearchLocalPreview();
      scheduleSessionSearchReload();
    });
    document.getElementById('session-search')?.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        event.target.value = '';
        sessionSearchQuery = '';
        applySessionSearchLocalPreview();
        scheduleSessionSearchReload();
      }
    });
    document.getElementById('chat-message-search')?.addEventListener('input', (event) => {
      chatMessageSearchQuery = event.target.value || '';
      if (!chatMessageSearchQuery.trim()) {
        resetChatMessageSearch({ clearInput: false });
        return;
      }
      scheduleChatMessageSearch();
    });
    document.getElementById('chat-message-search')?.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        resetChatMessageSearch({ clearInput: true });
        event.preventDefault();
        return;
      }
      if (event.key === 'Enter') {
        event.preventDefault();
        if (!chatMessageSearchMatches.length) {
          void runChatMessageSearch(chatMessageSearchQuery);
          return;
        }
        const step = event.shiftKey ? -1 : 1;
        void jumpToChatMessageSearchMatch(chatMessageSearchIndex + step);
      }
    });
    document.getElementById('btn-chat-search-prev')?.addEventListener('click', () => {
      if (!chatMessageSearchMatches.length) return;
      void jumpToChatMessageSearchMatch(chatMessageSearchIndex - 1);
    });
    document.getElementById('btn-chat-search-next')?.addEventListener('click', () => {
      if (!chatMessageSearchMatches.length) return;
      void jumpToChatMessageSearchMatch(chatMessageSearchIndex + 1);
    });
    document.getElementById('btn-session-scope')?.addEventListener('click', (event) => {
      event.preventDefault();
      toggleSessionScopeFilter();
    });
    async function openSettingsModal() {
      document.dispatchEvent(new CustomEvent('wa-need-overlays'));
      trackEvent('panel_open', { panel: 'settings' });
      document.getElementById('settings-modal')?.classList.add('open');
      if (!getExternalAgentCatalog().length) {
        try {
          await loadMeta();
        } catch (_) { /* 保留已有 meta，避免阻塞设置弹窗 */ }
      }
      renderModelOptions();
      renderExternalAgentOptions();
      syncSettingsServiceSection();
      loadServiceRestartSilentPrefs();
      syncReplyModeToggleUi();
      syncPushResultToggleUi();
      closeModelPicker();
    }

    function syncUsageRangeUI() {
      document.querySelectorAll('.usage-range-option').forEach((btn) => {
        const active = !usageCustomRange && (btn.dataset.range || '') === usageRangeKey;
        btn.classList.toggle('active', active);
      });
      syncUsageDateInputsFromActiveRange();
    }

    function buildUsageLoadKey(rangeKey, customRange) {
      if (customRange?.start && customRange?.end) {
        return `custom:${customRange.start}:${customRange.end}`;
      }
      return rangeKey || 'day';
    }

    function isActiveUsageLoad(rangeKey, customRange) {
      if (usageCustomRange) {
        return customRange?.start === usageCustomRange.start
          && customRange?.end === usageCustomRange.end;
      }
      return !customRange && rangeKey === usageRangeKey;
    }

    function parseUsageDayInput(value) {
      const text = String(value || '').trim();
      if (!/^\d{4}-\d{2}-\d{2}$/.test(text)) return null;
      const [y, m, d] = text.split('-').map(Number);
      if (!y || !m || !d) return null;
      return { y, m, d };
    }

    function customUsageSpanDays(start, end) {
      const startYmd = parseUsageDayInput(start);
      const endYmd = parseUsageDayInput(end);
      if (!startYmd || !endYmd) return 0;
      const startDt = Date.UTC(startYmd.y, startYmd.m - 1, startYmd.d);
      const endDt = Date.UTC(endYmd.y, endYmd.m - 1, endYmd.d);
      return Math.floor((endDt - startDt) / 86400000) + 1;
    }

    function resolveUsageDateBounds(forNamespace) {
      const ns = forNamespace || datePickerNamespace();
      if (ns === 'callLog') {
        const maxDate = usageDayKey(bjYmd());
        const minYmd = addDaysYmd(bjYmd(), -(CALL_LOG_MAX_CUSTOM_DAYS - 1));
        return { minDate: usageDayKey(minYmd), maxDate };
      }
      const maxDate = usageDateBounds?.maxDate || usageDayKey(bjYmd());
      const minDate = usageDateBounds?.minDate || maxDate;
      return { minDate, maxDate };
    }

    function clampUsageDateValue(value, minDate, maxDate) {
      let next = String(value || '').trim();
      if (!next) return next;
      if (minDate && next < minDate) next = minDate;
      if (maxDate && next > maxDate) next = maxDate;
      return next;
    }

    function usageDateFieldEl(role, namespace) {
      const ns = namespace || datePickerNamespace();
      if (ns === 'callLog') {
        return document.getElementById(role === 'start' ? 'call-log-start-date' : 'call-log-end-date');
      }
      return document.getElementById(role === 'start' ? 'usage-start-date' : 'usage-end-date');
    }

    function callLogDateRangeHintEl() {
      return document.getElementById('call-log-date-range-hint');
    }

    function getUsageDateFieldValue(el) {
      return String(el?.dataset?.value || '').trim();
    }

    function setUsageDateFieldValue(el, value) {
      if (!el) return;
      const next = String(value || '').trim();
      el.dataset.value = next;
      el.textContent = next || '选择日期';
      el.classList.toggle('is-empty', !next);
    }

    function getUsageDateFieldLimits(role) {
      const { minDate, maxDate } = resolveUsageDateBounds();
      const startValue = getUsageDateFieldValue(usageDateFieldEl('start'));
      const endValue = getUsageDateFieldValue(usageDateFieldEl('end'));
      if (role === 'start') {
        const hi = endValue ? clampUsageDateValue(endValue, minDate, maxDate) : maxDate;
        return { lo: minDate, hi };
      }
      const lo = startValue ? clampUsageDateValue(startValue, minDate, maxDate) : minDate;
      return { lo, hi: maxDate };
    }

    /** @type {{ role: 'start' | 'end', viewYear: number, viewMonth: number, anchorEl: HTMLElement | null, namespace: 'usage' | 'callLog' }} */
    const usageDatePickerState = {
      role: 'start',
      viewYear: 0,
      viewMonth: 0,
      anchorEl: null,
      namespace: 'usage',
    };

    function datePickerNamespace() {
      return usageDatePickerState.namespace === 'callLog' ? 'callLog' : 'usage';
    }

    function usageMonthTitle(y, m) {
      return `${y}年${m}月`;
    }

    function canUsagePickerPrevMonth(y, m, lo) {
      const min = parseUsageDayInput(lo);
      if (!min) return true;
      return y > min.y || (y === min.y && m > min.m);
    }

    function canUsagePickerNextMonth(y, m, hi) {
      const max = parseUsageDayInput(hi);
      if (!max) return true;
      return y < max.y || (y === max.y && m < max.m);
    }

    function isUsagePickerMonthInBounds(y, m, minDate, maxDate) {
      const min = parseUsageDayInput(minDate);
      const max = parseUsageDayInput(maxDate);
      if (min && (y < min.y || (y === min.y && m < min.m))) return false;
      if (max && (y > max.y || (y === max.y && m > max.m))) return false;
      return true;
    }

    function usageDaysInMonth(y, m) {
      return new Date(Date.UTC(y, m, 0)).getUTCDate();
    }

    function usageWeekdaySunday0(y, m, d) {
      return new Date(Date.UTC(y, m - 1, d)).getUTCDay();
    }

    function closeUsageDatePicker() {
      const pop = document.getElementById('usage-date-picker');
      if (!pop || pop.hidden) return;
      const ns = datePickerNamespace();
      pop.hidden = true;
      usageDatePickerState.anchorEl = null;
      usageDateFieldEl('start', ns)?.setAttribute('aria-expanded', 'false');
      usageDateFieldEl('end', ns)?.setAttribute('aria-expanded', 'false');
      usageDatePickerState.namespace = 'usage';
    }

    function positionUsageDatePicker(anchor) {
      const pop = document.getElementById('usage-date-picker');
      if (!pop || !anchor) return;
      const rect = anchor.getBoundingClientRect();
      const margin = 8;
      pop.style.visibility = 'hidden';
      pop.hidden = false;
      const popRect = pop.getBoundingClientRect();
      let top = rect.bottom + margin;
      let left = rect.left;
      if (left + popRect.width > window.innerWidth - margin) {
        left = Math.max(margin, window.innerWidth - popRect.width - margin);
      }
      if (top + popRect.height > window.innerHeight - margin) {
        top = Math.max(margin, rect.top - popRect.height - margin);
      }
      pop.style.left = `${left}px`;
      pop.style.top = `${top}px`;
      pop.style.visibility = '';
    }

    function renderUsageDatePicker() {
      const grid = document.getElementById('usage-date-picker-grid');
      const title = document.getElementById('usage-date-picker-title');
      const prevBtn = document.getElementById('usage-date-picker-prev');
      const nextBtn = document.getElementById('usage-date-picker-next');
      if (!grid || !title) return;

      const { role, viewYear: y, viewMonth: m } = usageDatePickerState;
      const { minDate, maxDate } = resolveUsageDateBounds();
      const { lo, hi } = getUsageDateFieldLimits(role);
      const selected = getUsageDateFieldValue(usageDateFieldEl(role));

      title.textContent = usageMonthTitle(y, m);
      if (prevBtn) {
        const canPrev = canUsagePickerPrevMonth(y, m, minDate);
        prevBtn.disabled = !canPrev;
        prevBtn.classList.toggle('is-disabled', !canPrev);
      }
      if (nextBtn) {
        const canNext = canUsagePickerNextMonth(y, m, maxDate);
        nextBtn.disabled = !canNext;
        nextBtn.classList.toggle('is-disabled', !canNext);
      }

      const dim = usageDaysInMonth(y, m);
      const firstWd = usageWeekdaySunday0(y, m, 1);
      /** @type {Array<{ y: number, m: number, d: number, muted: boolean, selectable: boolean, selected?: boolean }>} */
      const cells = [];
      const prevY = m === 1 ? y - 1 : y;
      const prevM = m === 1 ? 12 : m - 1;
      const prevDim = usageDaysInMonth(prevY, prevM);
      for (let i = firstWd - 1; i >= 0; i -= 1) {
        const d = prevDim - i;
        cells.push({ y: prevY, m: prevM, d, muted: true, selectable: false });
      }
      for (let d = 1; d <= dim; d += 1) {
        const key = usageDayKey({ y, m, d });
        const outOfRange = (lo && key < lo) || (hi && key > hi);
        cells.push({
          y,
          m,
          d,
          muted: outOfRange,
          selectable: !outOfRange,
          selected: key === selected,
        });
      }
      let nextY = m === 12 ? y + 1 : y;
      let nextM = m === 12 ? 1 : m + 1;
      let nd = 1;
      while (cells.length < 42) {
        cells.push({ y: nextY, m: nextM, d: nd, muted: true, selectable: false });
        nd += 1;
      }

      grid.innerHTML = cells.map((cell) => {
        const key = usageDayKey({ y: cell.y, m: cell.m, d: cell.d });
        const classes = ['usage-date-picker-day'];
        if (cell.muted) classes.push('is-muted');
        if (cell.selected) classes.push('is-selected');
        if (!cell.selectable) classes.push('is-disabled');
        const attrs = cell.selectable
          ? ` data-day="${escapeHtml(key)}"`
          : ' disabled';
        return `<button type="button" class="${classes.join(' ')}"${attrs} aria-label="${escapeHtml(key)}">${cell.d}</button>`;
      }).join('');
    }

    function openUsageDatePicker(anchor, role, namespace = 'usage') {
      if (!anchor || anchor.disabled) return;
      usageDatePickerState.namespace = namespace === 'callLog' ? 'callLog' : 'usage';
      if (namespace === 'callLog') {
        applyCallLogDateInputLimits();
      } else {
        applyUsageDateInputLimits();
      }
      const { minDate, maxDate } = resolveUsageDateBounds(namespace);
      const fallback = role === 'start' ? minDate : maxDate;
      const current = getUsageDateFieldValue(anchor);
      const seed = parseUsageDayInput(current || fallback) || bjYmd();
      usageDatePickerState.role = role;
      usageDatePickerState.viewYear = seed.y;
      usageDatePickerState.viewMonth = seed.m;
      usageDatePickerState.anchorEl = anchor;
      usageDateFieldEl('start', namespace)?.setAttribute('aria-expanded', 'false');
      usageDateFieldEl('end', namespace)?.setAttribute('aria-expanded', 'false');
      renderUsageDatePicker();
      positionUsageDatePicker(anchor);
      const pop = document.getElementById('usage-date-picker');
      if (pop) pop.hidden = false;
      anchor.setAttribute('aria-expanded', 'true');
    }

    function shiftUsageDatePickerMonth(delta) {
      let { viewYear: y, viewMonth: m } = usageDatePickerState;
      m += delta;
      if (m < 1) { y -= 1; m = 12; }
      if (m > 12) { y += 1; m = 1; }
      const { minDate, maxDate } = resolveUsageDateBounds();
      if (!isUsagePickerMonthInBounds(y, m, minDate, maxDate)) return;
      usageDatePickerState.viewYear = y;
      usageDatePickerState.viewMonth = m;
      renderUsageDatePicker();
      positionUsageDatePicker(usageDatePickerState.anchorEl);
    }

    function onUsageDatePicked(dayKey) {
      const { role, anchorEl } = usageDatePickerState;
      const ns = datePickerNamespace();
      const el = anchorEl || usageDateFieldEl(role, ns);
      setUsageDateFieldValue(el, dayKey);
      closeUsageDatePicker();
      if (ns === 'callLog') {
        applyCallLogDateInputLimits();
        const start = getUsageDateFieldValue(usageDateFieldEl('start', 'callLog'));
        const end = getUsageDateFieldValue(usageDateFieldEl('end', 'callLog'));
        if (start && end && start <= end) applyCallLogCustomRange();
        return;
      }
      applyUsageDateInputLimits();
      const start = getUsageDateFieldValue(usageDateFieldEl('start'));
      const end = getUsageDateFieldValue(usageDateFieldEl('end'));
      if (start && end && start <= end) applyUsageCustomRange();
    }

    function setUsageDateInputsEnabled(enabled) {
      const startInput = usageDateFieldEl('start');
      const endInput = usageDateFieldEl('end');
      if (startInput) startInput.disabled = !enabled;
      if (endInput) endInput.disabled = !enabled;
      if (!enabled) closeUsageDatePicker();
    }

    function applyUsageDateInputLimits() {
      const startInput = usageDateFieldEl('start');
      const endInput = usageDateFieldEl('end');
      const { minDate, maxDate } = resolveUsageDateBounds();
      const endValue = getUsageDateFieldValue(endInput);
      const startValue = getUsageDateFieldValue(startInput);
      const startMax = endValue ? clampUsageDateValue(endValue, minDate, maxDate) : maxDate;
      const endMin = startValue ? clampUsageDateValue(startValue, minDate, maxDate) : minDate;
      if (startInput) {
        const clampedStart = clampUsageDateValue(getUsageDateFieldValue(startInput), minDate, startMax);
        if (clampedStart !== getUsageDateFieldValue(startInput)) setUsageDateFieldValue(startInput, clampedStart);
      }
      if (endInput) {
        const clampedEnd = clampUsageDateValue(getUsageDateFieldValue(endInput), endMin, maxDate);
        if (clampedEnd !== getUsageDateFieldValue(endInput)) setUsageDateFieldValue(endInput, clampedEnd);
      }
      const hintEl = document.getElementById('usage-date-range-hint');
      if (hintEl) hintEl.textContent = '';
      if (!document.getElementById('usage-date-picker')?.hidden) renderUsageDatePicker();
    }

    async function loadUsageDateBounds() {
      try {
        const res = await fetch('/api/usage/me/bounds');
        const data = await res.json().catch(() => ({}));
        if (res.ok) usageDateBounds = data;
      } catch (_) { /* ignore */ }
      applyUsageDateInputLimits();
      return usageDateBounds;
    }

    function syncUsageDateInputsFromActiveRange() {
      const startInput = usageDateFieldEl('start');
      const endInput = usageDateFieldEl('end');
      if (!startInput || !endInput) return;
      if (usageCustomRange?.start && usageCustomRange?.end) {
        setUsageDateFieldValue(startInput, usageCustomRange.start);
        setUsageDateFieldValue(endInput, usageCustomRange.end);
        applyUsageDateInputLimits();
        return;
      }
      const { start, end } = resolveUsageRangeStartYmd(usageRangeKey);
      setUsageDateFieldValue(startInput, usageDayKey(start));
      setUsageDateFieldValue(endInput, usageDayKey(end));
      applyUsageDateInputLimits();
    }

    function applyUsageCustomRange() {
      const startInput = usageDateFieldEl('start');
      const endInput = usageDateFieldEl('end');
      const start = getUsageDateFieldValue(startInput);
      const end = getUsageDateFieldValue(endInput);
      const hintEl = document.getElementById('usage-date-range-hint');
      if (!start || !end) {
        if (hintEl) hintEl.textContent = '请选择开始与结束日期';
        return;
      }
      if (start > end) {
        if (hintEl) hintEl.textContent = '开始日期不能晚于结束日期';
        return;
      }
      const spanDays = customUsageSpanDays(start, end);
      if (spanDays > USAGE_MAX_CUSTOM_DAYS) {
        if (hintEl) hintEl.textContent = `自定义区间最长 ${USAGE_MAX_CUSTOM_DAYS} 天`;
        return;
      }
      const minDate = usageDateBounds?.minDate || '';
      const maxDate = usageDateBounds?.maxDate || usageDayKey(bjYmd());
      if (minDate && start < minDate) {
        if (hintEl) hintEl.textContent = `最早可选 ${minDate}`;
        return;
      }
      if (maxDate && end > maxDate) {
        if (hintEl) hintEl.textContent = '结束日期不能晚于今天';
        return;
      }
      applyUsageDateInputLimits();
      usageCustomRange = { start, end };
      usageRangeKey = 'custom';
      syncUsageRangeUI();
      void loadUsageStatsForRange('custom', { customRange: usageCustomRange });
      if (usageRankOpen) void loadUsageQuestionRank();
    }

    function abortUsageLoad() {
      usageLoadAbortController?.abort();
      usageLoadAbortController = null;
    }

    async function openUsageModal() {
      if (!(currentAuthUser?.staffId || '').trim()) return;
      trackEvent('panel_open', { panel: 'usage' });
      const modal = document.getElementById('usage-modal');
      if (!modal) return;
      usageRangeKey = 'day';
      usageCustomRange = null;
      setUsageRankOpen(false);
      syncUsageRangeUI();
      modal.classList.add('open');
      modal.setAttribute('aria-hidden', 'false');
      abortUsageLoad();
      setUsageStatsLoadingUI('day');
      setUsageDateInputsEnabled(false);
      await loadUsageDateBounds();
      setUsageDateInputsEnabled(true);
      await loadUsageStatsForRange('day', { refresh: true });
      void loadUsageStatsForRange('180d', { silent: true, refresh: true });
    }

    async function closeUsageModal() {
      const modal = document.getElementById('usage-modal');
      if (!modal?.classList.contains('open')) return;
      closeUsageDatePicker();
      hideUsageChartTooltip();
      setUsageRankOpen(false);
      await animateOverlayClose(modal);
      modal.classList.remove('open');
      modal.setAttribute('aria-hidden', 'true');
    }

    async function closeSettingsModal() {
      const modal = document.getElementById('settings-modal');
      if (!modal?.classList.contains('open')) return;
      closeModelPicker();
      await animateOverlayClose(modal);
      modal.classList.remove('open');
    }

    function initThemeSettings() {
      renderModelOptions();
      document.getElementById('model-picker-trigger')?.addEventListener('click', (event) => {
        event.stopPropagation();
        toggleModelPicker();
      });
      document.getElementById('model-picker-menu')?.addEventListener('click', (event) => {
        const btn = event.target.closest('.model-picker-item');
        if (!btn) return;
        event.stopPropagation();
        applyModelSelection(btn.dataset.modelId);
      });
      document.getElementById('model-picker')?.addEventListener('click', (event) => {
        event.stopPropagation();
      });
      document.getElementById('settings-box')?.addEventListener('click', (event) => {
        event.stopPropagation();
      });
      document.addEventListener('click', () => closeModelPicker());
      document.getElementById('btn-settings').addEventListener('click', openSettingsModal);
      document.getElementById('btn-settings-close')?.addEventListener('click', closeSettingsModal);
      document.getElementById('btn-settings-about')?.addEventListener('click', async () => {
        await closeSettingsModal();
        setAboutOpen(true);
      });
      document.getElementById('btn-settings-usage')?.addEventListener('click', async () => {
        await closeSettingsModal();
        openUsageModal();
      });
      document.getElementById('btn-settings-moa-history')?.addEventListener('click', async () => {
        await closeSettingsModal();
        trackEvent('panel_open', { panel: 'moa_call_log', source: 'settings' });
        void setMoaCallLogModalOpen(true);
      });
      document.getElementById('chk-restart-service-silent')?.addEventListener('change', (ev) => {
        persistServiceRestartSilentPref(!!ev.target.checked);
      });
      document.getElementById('btn-settings-restart-web-agent')?.addEventListener('click', () => {
        void invokeServiceRestart('web_agent');
      });
      document.getElementById('btn-settings-restart-gateway')?.addEventListener('click', () => {
        void invokeServiceRestart('dingtalk_gateway');
      });
      loadServiceRestartSilentPrefs();
      document.getElementById('btn-usage-close')?.addEventListener('click', closeUsageModal);
      document.getElementById('usage-modal')?.addEventListener('click', (e) => {
        if (e.target.id === 'usage-modal') closeUsageModal();
      });
      document.getElementById('usage-bubble')?.addEventListener('click', (e) => {
        e.stopPropagation();
      });
      document.getElementById('settings-modal')?.addEventListener('click', (e) => {
        if (e.target.id === 'settings-modal') closeSettingsModal();
      });
      initUsageStatsSettings();
    }

    let mobileDeferredOverlayUiBound = false;
    function bindMobileDeferredOverlayUi() {
      if (!isWebAgentMobile() || mobileDeferredOverlayUiBound) return;
      const catalogClose = document.getElementById('btn-catalog-close');
      if (!catalogClose) return;
      mobileDeferredOverlayUiBound = true;
      catalogClose.addEventListener('click', () => setCatalogOpen(false));
      document.getElementById('btn-settings-close')?.addEventListener('click', closeSettingsModal);
      document.getElementById('btn-settings-about')?.addEventListener('click', async () => {
        await closeSettingsModal();
        setAboutOpen(true);
      });
      document.getElementById('settings-modal')?.addEventListener('click', (e) => {
        if (e.target.id === 'settings-modal') closeSettingsModal();
      });
    }

    async function setCatalogOpen(open, opts = {}) {
      if (open) document.dispatchEvent(new CustomEvent('wa-need-overlays'));
      const panel = document.getElementById('catalog-panel');
      const wasOpen = catalogOpen;
      catalogOpen = open;
      localStorage.setItem('web_agent_catalog_open', open ? '1' : '0');
      if (open && !wasOpen) {
        trackEvent('panel_open', { panel: 'catalog' });
        if (catalogPanel) {
          void refreshCatalogPanel({ preserveNavUi: true });
        } else {
          showCatalogBootstrapLoading();
          void ensureCatalogPanelInit().catch((err) => {
            console.error('catalog init on open', err);
          });
        }
      }
      if (!open) {
        clearCatalogBootstrapLoading();
        catalogPanel?.persistNavCollapsed?.();
      }
      panel?.classList.toggle('open', open);
      document.body.classList.toggle('catalog-open', open);
      setHeaderBtnActive(document.getElementById('btn-catalog'), open, opts);
      if (open && !wasOpen && !opts.skipAnimation && document.body.classList.contains('layout-ready')) {
        panel?.classList.remove('panel-closing');
        triggerPanelOpenAnimation(panel, 'panel-opening');
      } else {
        panel?.classList.remove('panel-opening', 'panel-closing');
      }
    }

    function initSidebarResize() {
      const root = document.documentElement;
      const SIDEBAR_KEY = 'web_agent_sidebar_width';
      const MAX = 480;
      const DEFAULT = 240;

      function clamp(n, min, max) { return Math.min(max, Math.max(min, n)); }

      function setSidebarWidth(w, persist) {
        const width = clamp(w, getSidebarMinWidth(), MAX);
        root.style.setProperty('--sidebar-width', width + 'px');
        if (persist) localStorage.setItem(SIDEBAR_KEY, String(width));
        return width;
      }

      function applySidebarWidth(w) {
        return setSidebarWidth(w, true);
      }
      applySidebarWidthRef = applySidebarWidth;

      measureSidebarMinWidth();
      applySidebarWidth(Number(localStorage.getItem(SIDEBAR_KEY)) || DEFAULT);

      const handle = document.getElementById('sidebar-resizer');
      if (!handle) return;
      handle.addEventListener('pointerdown', (e) => {
        if (e.pointerType === 'mouse' && e.button !== 0) return;
        e.preventDefault();
        handle.setPointerCapture(e.pointerId);
        const startX = e.clientX;
        const startWidth = parseInt(getComputedStyle(root).getPropertyValue('--sidebar-width'), 10) || DEFAULT;
        document.body.classList.add('is-resizing');

        function onMove(ev) {
          if (ev.pointerId !== e.pointerId) return;
          setSidebarWidth(startWidth + (ev.clientX - startX), false);
        }
        function onUp(ev) {
          if (ev.pointerId !== e.pointerId) return;
          document.body.classList.remove('is-resizing');
          try { handle.releasePointerCapture(e.pointerId); } catch (_) { /* already released */ }
          handle.removeEventListener('pointermove', onMove);
          handle.removeEventListener('pointerup', onUp);
          handle.removeEventListener('pointercancel', onUp);
          const finalWidth = parseInt(getComputedStyle(root).getPropertyValue('--sidebar-width'), 10) || DEFAULT;
          localStorage.setItem(SIDEBAR_KEY, String(finalWidth));
        }
        handle.addEventListener('pointermove', onMove);
        handle.addEventListener('pointerup', onUp);
        handle.addEventListener('pointercancel', onUp);
      });
    }

    function initCatalogResize() {
      const root = document.documentElement;
      const nav = document.getElementById('catalog-nav');
      const PANEL_KEY = 'web_agent_catalog_width';
      const NAV_KEY = 'web_agent_catalog_nav_width';
      const MIN_PANEL = 280;
      const MAX_PANEL = 840;
      const MIN_NAV = 88;
      const MAX_NAV = 300;
      const DEFAULT_PANEL = 380;
      const DEFAULT_NAV = 112;

      function clamp(n, min, max) { return Math.min(max, Math.max(min, n)); }

      function applyPanelWidth(w, persist = true) {
        const width = clamp(w, MIN_PANEL, MAX_PANEL);
        root.style.setProperty('--catalog-width', width + 'px');
        if (persist) localStorage.setItem(PANEL_KEY, String(width));
        return width;
      }

      function applyNavWidth(w, persist = true) {
        const width = clamp(w, MIN_NAV, MAX_NAV);
        root.style.setProperty('--catalog-nav-width', width + 'px');
        if (nav) nav.style.width = width + 'px';
        if (persist) localStorage.setItem(NAV_KEY, String(width));
        return width;
      }

      applyPanelWidth(Number(localStorage.getItem(PANEL_KEY)) || DEFAULT_PANEL);
      applyNavWidth(Number(localStorage.getItem(NAV_KEY)) || DEFAULT_NAV);

      function bindHorizontalDrag(handle, getStartWidth, setWidth, invertDelta, persistWidth) {
        if (!handle) return;
        handle.addEventListener('pointerdown', (e) => {
          if (e.pointerType === 'mouse' && e.button !== 0) return;
          e.preventDefault();
          handle.setPointerCapture(e.pointerId);
          const startX = e.clientX;
          const startWidth = getStartWidth();
          document.body.classList.add('is-resizing');

          function onMove(ev) {
            if (ev.pointerId !== e.pointerId) return;
            const delta = ev.clientX - startX;
            setWidth(startWidth + (invertDelta ? -delta : delta), false);
          }
          function onUp(ev) {
            if (ev.pointerId !== e.pointerId) return;
            document.body.classList.remove('is-resizing');
            try { handle.releasePointerCapture(e.pointerId); } catch (_) { /* already released */ }
            handle.removeEventListener('pointermove', onMove);
            handle.removeEventListener('pointerup', onUp);
            handle.removeEventListener('pointercancel', onUp);
            persistWidth();
          }
          handle.addEventListener('pointermove', onMove);
          handle.addEventListener('pointerup', onUp);
          handle.addEventListener('pointercancel', onUp);
        });
      }

      bindHorizontalDrag(
        document.getElementById('catalog-panel-resizer'),
        () => parseInt(getComputedStyle(root).getPropertyValue('--catalog-width'), 10) || DEFAULT_PANEL,
        applyPanelWidth,
        true,
        () => applyPanelWidth(parseInt(getComputedStyle(root).getPropertyValue('--catalog-width'), 10) || DEFAULT_PANEL, true)
      );
      bindHorizontalDrag(
        document.getElementById('catalog-nav-resizer'),
        () => parseInt(getComputedStyle(root).getPropertyValue('--catalog-nav-width'), 10) || DEFAULT_NAV,
        applyNavWidth,
        false,
        () => applyNavWidth(parseInt(getComputedStyle(root).getPropertyValue('--catalog-nav-width'), 10) || DEFAULT_NAV, true)
      );
    }

    async function initBookmarksPanel() {
      if (bookmarksPanel) return;
      if (typeof BookmarksPanel === 'undefined') return;
      bookmarksPanel = new BookmarksPanel({
        modalEl: document.getElementById('bookmarks-modal'),
        bubbleEl: document.getElementById('bookmarks-bubble'),
        bodyEl: document.getElementById('bookmarks-body'),
        addModalEl: document.getElementById('bookmarks-add-modal'),
        addDialogEl: document.getElementById('bookmarks-add-dialog'),
        addFormEl: document.getElementById('bookmarks-add-form'),
        addTitleEl: document.getElementById('bookmarks-add-title'),
        urlInputEl: document.getElementById('bookmarks-url-input'),
        labelInputEl: document.getElementById('bookmarks-label-input'),
        descriptionInputEl: document.getElementById('bookmarks-description-input'),
        editFieldsEl: document.getElementById('bookmarks-add-edit-fields'),
        categorySelectEl: document.getElementById('bookmarks-category-select'),
        categoryNewEl: document.getElementById('bookmarks-category-new'),
        categoryEditModalEl: document.getElementById('bookmarks-category-edit-modal'),
        categoryEditDialogEl: document.getElementById('bookmarks-category-edit-dialog'),
        categoryEditFormEl: document.getElementById('bookmarks-category-edit-form'),
        categoryLabelInputEl: document.getElementById('bookmarks-category-label-input'),
        fetchBookmarks: async () => {
          const latest = await api('/api/meta');
          return latest.bookmarks || { categories: [] };
        },
        requestClose: () => { setBookmarksOpen(false); },
      });
      bookmarksPanel.setAdmin(!!currentAuthUser?.isAdmin);
      bookmarksPanel.bind();
      bookmarksPanel.setData(meta.bookmarks || { categories: [] });
      void bookmarksPanel.migrateFromLocalStorageIfNeeded();
    }

    async function setBookmarksOpen(open, opts = {}) {
      if (!bookmarksPanel) return;
      if (!open && bookmarksPanel.open && !opts.skipAnimation && document.body.classList.contains('layout-ready')) {
        const modal = document.getElementById('bookmarks-modal');
        await animateOverlayClose(modal);
      }
      bookmarksPanel.setOpen(open, opts);
      const modal = document.getElementById('bookmarks-modal');
      if (modal) modal.setAttribute('aria-hidden', open ? 'false' : 'true');
      setHeaderBtnActive(document.getElementById('btn-bookmarks'), open);
    }

    function initAboutPanel() {
      if (typeof WebAgentAboutPanel === 'undefined') return;
      aboutPanel = new WebAgentAboutPanel({
        modalEl: document.getElementById('about-modal'),
        bubbleEl: document.getElementById('about-bubble'),
        titleEl: document.getElementById('about-title'),
        introEl: document.getElementById('about-intro'),
        listEl: document.getElementById('about-docs-list'),
        closeEl: document.getElementById('btn-about-close'),
        request: (path) => api(path),
        animateClose: animateOverlayClose,
      });
      aboutPanel.bind();
    }

    async function setAboutOpen(open, opts = {}) {
      if (!aboutPanel) return;
      await aboutPanel.setOpen(open, opts);
      const modal = document.getElementById('about-modal');
      if (modal) modal.setAttribute('aria-hidden', open ? 'false' : 'true');
    }

    function initMessageBoardPanel() {
      if (typeof MessageBoardPanel === 'undefined') return;
      messageBoardPanel = new MessageBoardPanel({
        modalEl: document.getElementById('message-board-modal'),
        bubbleEl: document.getElementById('message-board-bubble'),
        listEl: document.getElementById('message-board-list'),
        formEl: document.getElementById('message-board-form'),
        contentEl: document.getElementById('message-board-content'),
        realNameEl: document.getElementById('message-board-realname'),
        hintEl: document.getElementById('message-board-hint'),
        submitEl: document.getElementById('message-board-submit'),
        request: (path, init) => api(path, init),
        getAuthUser: () => currentAuthUser,
      });
      messageBoardPanel.setAdmin(!!currentAuthUser?.isAdmin);
      messageBoardPanel.bind();
    }

    async function setMessageBoardOpen(open, opts = {}) {
      if (!messageBoardPanel) return;
      if (open && !messageBoardPanel.open) trackEvent('panel_open', { panel: 'message_board' });
      if (!open && messageBoardPanel.open && !opts.skipAnimation && document.body.classList.contains('layout-ready')) {
        const modal = document.getElementById('message-board-modal');
        await animateOverlayClose(modal);
      }
      messageBoardPanel.setOpen(open, opts);
      const modal = document.getElementById('message-board-modal');
      if (modal) modal.setAttribute('aria-hidden', open ? 'false' : 'true');
      setHeaderBtnActive(document.getElementById('btn-message-board'), open);
    }

    function catalogNavCanEdit() {
      if (!meta?.authRequired) return true;
      return userIsWebAdmin(currentAuthUser);
    }

    function catalogNavCanDelete() {
      if (!meta?.authRequired) return true;
      return userIsWebSuperAdmin(currentAuthUser);
    }

    async function saveCatalogPrompt(payload) {
      const res = await fetch('/api/catalog-prompt', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        let message = '保存失败';
        try {
          const data = await res.json();
          if (data?.error) message = String(data.error);
        } catch (_) { /* ignore */ }
        throw new Error(message);
      }
      return res.json();
    }

    async function saveCatalogNav(payload) {
      const res = await fetch('/api/catalog-nav', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
      if (!res.ok) {
        let message = '保存失败';
        try {
          const data = await res.json();
          if (data?.error) message = String(data.error);
        } catch (_) { /* ignore */ }
        throw new Error(message);
      }
      const data = await res.json();
      if (data?.nav && catalogPanel) {
        catalogPanel.navTree = JSON.parse(JSON.stringify(data.nav.tree || []));
        catalogPanel.ensureFolderChildren(catalogPanel.navTree);
        catalogPanel.hydrateNavCaps(catalogPanel.navTree);
        catalogPanel.hydrateNavPlaybooks(catalogPanel.navTree);
        catalogPanel.sortNavTreeChildOrder(catalogPanel.navTree);
        catalogPanel.renderNav({ preserveScroll: true });
        catalogPanel.render();
      }
    }

    async function fetchCatalogData(opts) {
      const forceRefresh = !!(opts && opts.forceRefresh);
      const url = forceRefresh
        ? `${API}/api/catalog?refresh=1&_=${Date.now()}`
        : `${API}/api/catalog`;
      const resp = await fetch(url, {
        credentials: 'same-origin',
        cache: 'no-store',
        headers: forceRefresh ? { 'Cache-Control': 'no-cache' } : undefined,
      });
      if (resp.status === 304) {
        if (catalogPanel && catalogPanel.DATA) return catalogPanel.DATA;
        return fetchCatalogData({ forceRefresh: true });
      }
      if (!resp.ok) {
        const err = await resp.json().catch(() => ({}));
        throw new Error(err.error || `HTTP ${resp.status}`);
      }
      return resp.json();
    }

    async function refreshCatalogPanel(opts) {
      if (!catalogPanel) return;
      try {
        await catalogPanel.reload(() => fetchCatalogData(), opts);
      } catch (e) {
        console.warn('refresh catalog failed', e);
      }
    }

    function ensureCatalogPanelInit() {
      if (catalogPanel) return Promise.resolve();
      if (catalogPanelInitPromise) return catalogPanelInitPromise;
      catalogPanelInitPromise = (async () => {
        if (isWebAgentMobile() && window.__WEB_AGENT_DEFERRED_PANELS_READY__) {
          await window.__WEB_AGENT_DEFERRED_PANELS_READY__;
        }
        await initCatalogPanel();
      })().catch((err) => {
        catalogPanelInitPromise = null;
        throw err;
      });
      return catalogPanelInitPromise;
    }

    async function initCatalogPanel() {
      if (catalogPanel) return;
      if (typeof CatalogPanel === 'undefined') return;
      catalogPanel = new CatalogPanel({
        root: document.getElementById('catalog-panel'),
        searchEl: document.getElementById('catalog-search'),
        navEl: document.getElementById('catalog-nav'),
        mainEl: document.getElementById('catalog-main'),
        canEditNav: catalogNavCanEdit(),
        canDeleteNav: catalogNavCanDelete(),
        saveNav: saveCatalogNav,
        savePrompt: saveCatalogPrompt,
        onPromptsSaved: () => refreshCatalogPanel({ preserveNavUi: true }),
        onRunPrompt: (text) => {
          if (!text) return;
          trackEvent('catalog_prompt_run', { length: String(text).length });
          fillInputFromPrompt(text, { appendWhenOccupied: true });
        },
        getSessionId: () => String(currentSessionId || '').trim(),
      });
      await catalogPanel.init(() => fetchCatalogData());
    }

    function ensureExternalAgentsEnabled(agentIds) {
      const ids = (agentIds || []).map((item) => String(item || '').trim()).filter(Boolean);
      if (!ids.length) return getEnabledExternalAgents();
      const enabled = new Set(getEnabledExternalAgents());
      let changed = false;
      for (const id of ids) {
        if (!enabled.has(id)) {
          enabled.add(id);
          changed = true;
        }
      }
      if (!changed) return Array.from(enabled);
      const next = Array.from(enabled);
      try {
        localStorage.setItem(EXTERNAL_AGENTS_KEY, JSON.stringify(next));
      } catch (_) { /* ignore */ }
      renderExternalAgentOptions();
      return next;
    }

    function initMoaRecordPanel() {
      if (typeof MoaRecordPanel === 'undefined') return;
      moaRecordPanel = new MoaRecordPanel({
        modalEl: document.getElementById('moa-record-modal'),
        bubbleEl: document.getElementById('moa-record-bubble'),
        modeListEl: document.getElementById('moa-record-mode-list'),
        formEl: document.getElementById('moa-record-form'),
        formFieldsEl: document.getElementById('moa-record-form-fields'),
        formTitleEl: document.getElementById('moa-record-form-title'),
        formDescEl: document.getElementById('moa-record-form-desc'),
        submitEl: document.getElementById('btn-moa-record-submit'),
        closeEl: document.getElementById('btn-moa-record-close'),
        animateClose: animateOverlayClose,
        onSubmit: async ({ text, attachments, suggestExternalAgents }) => {
          fillInputFromMoaRecord({ text, attachments, suggestExternalAgents });
        },
      });
      moaRecordPanel.bind();
    }

    async function setMoaRecordOpen(open, opts = {}) {
      if (!moaRecordPanel) return;
      if (open && !moaRecordPanel.open) trackEvent('panel_open', { panel: 'moa_record' });
      await moaRecordPanel.setOpen(open, opts);
      const modal = document.getElementById('moa-record-modal');
      if (modal) modal.setAttribute('aria-hidden', open ? 'false' : 'true');
    }

    document.getElementById('btn-catalog')?.addEventListener('click', () => setCatalogOpen(!catalogOpen));
    document.getElementById('btn-catalog-close')?.addEventListener('click', () => setCatalogOpen(false));
    document.getElementById('btn-moa-record')?.addEventListener('click', () => setMoaRecordOpen(true));

    document.getElementById('btn-bookmarks')?.addEventListener('click', async () => {
      if (!bookmarksPanel) await initBookmarksPanel();
      await setBookmarksOpen(!bookmarksPanel?.open);
    });
    document.getElementById('btn-message-board')?.addEventListener('click', async () => {
      const opening = !messageBoardPanel?.open;
      if (opening) await closeSettingsModal();
      setMessageBoardOpen(opening);
    });
    document.getElementById('btn-session-collaborators')?.addEventListener('click', () => {
      setCollaboratorsModalOpen(true);
    });
    document.getElementById('btn-collaborators-cancel')?.addEventListener('click', () => {
      setCollaboratorsModalOpen(false);
    });
    document.getElementById('btn-collaborators-confirm')?.addEventListener('click', () => {
      saveSessionCollaborators();
    });
    document.getElementById('collaborators-search')?.addEventListener('input', () => {
      renderCollaboratorsList();
    });
    document.getElementById('collaborators-modal')?.addEventListener('click', (event) => {
      if (event.target.id === 'collaborators-modal') setCollaboratorsModalOpen(false);
    });
    document.getElementById('btn-user-profile-close')?.addEventListener('click', () => {
      void setUserProfileModalOpen(false);
    });
    document.getElementById('btn-user-profile-compose')?.addEventListener('click', () => {
      const compose = document.getElementById('user-profile-compose');
      const sendBtn = document.getElementById('btn-user-profile-send');
      const composeBtn = document.getElementById('btn-user-profile-compose');
      const msgEl = document.getElementById('user-profile-message');
      if (!compose || !sendBtn || !composeBtn) return;
      const open = !compose.classList.contains('open');
      compose.classList.toggle('open', open);
      sendBtn.hidden = !open;
      composeBtn.textContent = open ? '收起' : '发消息';
      if (open) {
        setUserProfileStatus('');
        msgEl?.focus();
      }
    });
    document.getElementById('btn-user-profile-send')?.addEventListener('click', () => {
      void sendUserProfileDingtalkMessage();
    });
    document.getElementById('btn-user-profile-message-log')?.addEventListener('click', () => {
      void toggleUserProfileMessageLog();
    });
    document.getElementById('user-profile-modal')?.addEventListener('click', (event) => {
      if (event.target.id === 'user-profile-modal') void setUserProfileModalOpen(false);
    });
    document.getElementById('btn-forward-cancel')?.addEventListener('click', () => {
      void enqueueForwardModalTransition(() => setForwardModalOpen(false));
    });
    document.getElementById('btn-forward-confirm')?.addEventListener('click', () => {
      submitMessageForward();
    });
    document.getElementById('forward-search')?.addEventListener('input', () => {
      renderForwardList();
    });
    document.getElementById('forward-modal')?.addEventListener('click', (event) => {
      if (event.target.id === 'forward-modal') {
        void enqueueForwardModalTransition(() => setForwardModalOpen(false));
      }
    });
    document.getElementById('message-board-modal')?.addEventListener('click', (event) => {
      if (event.target.id === 'message-board-modal') setMessageBoardOpen(false);
    });
    document.getElementById('btn-bookmarks-add')?.addEventListener('click', () => {
      bookmarksPanel?.toggleAddPanel(true);
    });
    document.getElementById('btn-bookmarks-add-cancel')?.addEventListener('click', () => {
      bookmarksPanel?.toggleAddPanel(false);
    });
    document.getElementById('bookmarks-add-modal')?.addEventListener('click', (event) => {
      if (event.target.id === 'bookmarks-add-modal') bookmarksPanel?.toggleAddPanel(false);
    });
    document.getElementById('bookmarks-category-edit-modal')?.addEventListener('click', (event) => {
      if (event.target.id === 'bookmarks-category-edit-modal') bookmarksPanel?.toggleCategoryEditPanel(false);
    });
    document.getElementById('btn-bookmarks-category-edit-cancel')?.addEventListener('click', () => {
      bookmarksPanel?.toggleCategoryEditPanel(false);
    });
    document.getElementById('bookmarks-modal')?.addEventListener('click', (event) => {
      if (event.target.id === 'bookmarks-modal') setBookmarksOpen(false);
    });
    document.addEventListener('keydown', (event) => {
      if (event.key !== 'Escape') return;
      if (bookmarksPanel?.categoryEditOpen) {
        bookmarksPanel.toggleCategoryEditPanel(false);
        return;
      }
      if (bookmarksPanel?.addOpen) {
        bookmarksPanel.toggleAddPanel(false);
        return;
      }
      if (bookmarksPanel?.open) setBookmarksOpen(false);
      if (messageBoardPanel?.open) setMessageBoardOpen(false);
      if (moaRecordPanel?.open) setMoaRecordOpen(false);
      const forwardModal = document.getElementById('forward-modal');
      if (forwardModal?.classList.contains('open')) {
        void enqueueForwardModalTransition(() => setForwardModalOpen(false));
      }
    });

    let sessionPollTimer = null;
    let sessionListMetaTimer = null;
    function startSessionPolling() {
      if (sessionPollTimer) return;
      const pollMs = isWebAgentMobile() ? 30000 : 15000;
      const metaMs = isWebAgentMobile() ? 60000 : 30000;
      sessionPollTimer = setInterval(async () => {
        if (document.hidden) return;
        const viewingId = currentSessionId;
        try {
          await loadSessions({ lite: true });
          if (viewingId && currentSessionId === viewingId) {
            const sess = sessionsCache.find((s) => s.id === viewingId);
            syncSessionReadOnly(viewingId);
            updateDingtalkOwnerBar();
            const sessionActive = sess?.running;
            if (sessionActive) await tryReconnectActiveRun(viewingId);
            if (sessionMessagesStaleAgainstIndex(viewingId)) {
              await loadMessages({ force: true, repaint: false });
            }
          }
        } catch { /* ignore poll errors */ }
      }, pollMs);
      if (sessionListMetaTimer) return;
      sessionListMetaTimer = setInterval(() => {
        if (document.hidden || sessionSearchQuery.trim()) return;
        syncSessionListFromCache();
      }, metaMs);
    }

    document.addEventListener('visibilitychange', () => {
      if (document.visibilityState !== 'visible') return;
      const sid = currentSessionId;
      if (!sid) return;
      void (async () => {
        try {
          await loadSessions({ lite: true });
          const sess = sessionsCache.find((s) => s.id === sid);
          const sessionActive = sess?.running;
          if (sessionActive || activeRuns.has(sid)) {
            await tryReconnectActiveRun(sid);
          }
          if (sessionMessagesStaleAgainstIndex(sid)) {
            await loadMessages({ force: true, repaint: false });
          }
        } catch { /* ignore */ }
      })();
    });

    async function setUserMenuOpen(open) {
      const btn = document.getElementById('user-menu-btn');
      const dropdown = document.getElementById('user-menu-dropdown');
      if (!btn || !dropdown) return;
      if (!open && !dropdown.hidden) {
        await setDropdownAnimated(dropdown, false);
        resetUserMenuDropdownPlacement();
      } else if (open) {
        if (shouldPortalUserMenuDropdown()) positionUserMenuDropdown();
        else resetUserMenuDropdownPlacement();
        setDropdownAnimated(dropdown, true);
      } else {
        dropdown.hidden = true;
        resetUserMenuDropdownPlacement();
      }
      btn.setAttribute('aria-expanded', open ? 'true' : 'false');
    }

    function isGuestStaffId(staffId) {
      return /^guest_[a-f0-9]{32}$/.test(String(staffId || '').trim());
    }

    const CHENMO_STAFF_ID = '32274159141215328';

    function isProtectedBuiltinAdmin(user) {
      if (!user) return false;
      const staffId = String(user.staffId || '').trim();
      if (!staffId) return false;
      if (staffId === CHENMO_STAFF_ID || staffId === 'admin') return true;
      return publicDisplayName(String(user.displayName || '')).trim() === '陈墨';
    }

    function userIsWebAdmin(user) {
      return !!(user?.isAdmin || user?.adminApplyStatus?.isAdmin);
    }

    function userIsWebSuperAdmin(user) {
      if (!user || !userIsWebAdmin(user)) return false;
      if (user.isSuperAdmin) return true;
      return !!(user.permissions && user.permissions.super_admin);
    }

    function buildStaffAdminRoleTagHtml(user) {
      if (!user?.isAdmin) return '';
      const isSuperAdmin = !!(user.isSuperAdmin || user.permissions?.super_admin);
      const roleClass = isSuperAdmin
        ? 'collaborators-item-role is-super-admin'
        : 'collaborators-item-role is-admin';
      const roleText = isSuperAdmin ? '超管' : '管理员';
      return ` <span class="${roleClass}">${roleText}</span>`;
    }

    function syncUserAdminBadgeFromUser(user) {
      const adminBadgeEl = document.getElementById('user-menu-admin-badge');
      const menuBtn = document.getElementById('user-menu-btn');
      const isAdmin = userIsWebAdmin(user);
      const isSuperAdmin = userIsWebSuperAdmin(user);
      if (adminBadgeEl) {
        adminBadgeEl.hidden = !isAdmin;
        adminBadgeEl.textContent = isSuperAdmin ? '超管' : '管理';
        adminBadgeEl.title = isSuperAdmin ? '超管' : '管理员';
        adminBadgeEl.classList.toggle('is-super-admin', isSuperAdmin);
      }
      if (menuBtn && user) {
        const displayName = authUserDisplayName(user);
        menuBtn.classList.toggle('is-admin', isAdmin);
        menuBtn.setAttribute(
          'aria-label',
          isSuperAdmin ? `${displayName}，超管` : (isAdmin ? `${displayName}，管理员` : displayName),
        );
      }
      syncOpenApiMenuItem();
      syncUserProfileAvatarClickable();
    }

    let userProfileTargetStaffId = '';
    let userProfileLoading = false;
    let userProfileSending = false;
    let userProfileMessageLogOpen = false;
    let userProfileMessageLogLoading = false;
    const USER_PROFILE_CACHE_TTL_MS = 90_000;
    const userProfileCache = new Map();

    function syncUserProfileAvatarClickable() {
      const staffId = (currentAuthUser?.staffId || '').trim();
      document.body.classList.toggle('user-profile-clicks', !!staffId);
    }

    function bindSuperAdminUserProfileClicks() {
      const container = getMessagesEl();
      if (!container || container.dataset.profileClickBound === '1') return;
      container.dataset.profileClickBound = '1';
      container.addEventListener('click', (event) => {
        if (!(currentAuthUser?.staffId || '').trim()) return;
        const avatar = event.target.closest('.msg.user .name-avatar[data-staff-id], .msg.user .name-avatar-fallback[data-staff-id]');
        if (!avatar) return;
        const staffId = (avatar.dataset.staffId || '').trim();
        if (!staffId) return;
        event.preventDefault();
        event.stopPropagation();
        openUserProfileModal(staffId, avatarLabelForElement(avatar));
      });
    }

    function setUserProfileStatus(text, kind = '') {
      const el = document.getElementById('user-profile-status');
      if (!el) return;
      el.textContent = text || '';
      el.classList.remove('is-error', 'is-success');
      if (kind) el.classList.add(kind === 'error' ? 'is-error' : 'is-success');
    }

    function renderUserProfileCard(profile) {
      const head = document.getElementById('user-profile-head');
      const details = document.getElementById('user-profile-details');
      if (!head || !details || !profile) return;
      const name = publicDisplayName(profile.displayName || profile.staffId || '');
      const roleClass = profile.isSuperAdmin
        ? 'user-profile-role is-super-admin'
        : (profile.isAdmin ? 'user-profile-role is-admin' : 'user-profile-role');
      const roleText = profile.roleLabel || (profile.isSuperAdmin ? '超级管理员' : (profile.isAdmin ? '管理员' : '普通用户'));
      head.innerHTML = `
        ${buildNameAvatarHtml({
          staffId: profile.staffId,
          label: name,
          avatarUrl: profile.avatarUrl || '',
          eager: true,
        })}
        <div class="user-profile-head-main">
          <div class="user-profile-name">${escapeHtml(name)}</div>
          <div class="user-profile-id">${escapeHtml(profile.staffId || '')}</div>
          <span class="${roleClass}">${escapeHtml(roleText)}</span>
        </div>`;
      hydrateAvatars(head);
      const EMPTY = '—';
      const rows = (Array.isArray(profile.cardRows) ? profile.cardRows : []).map((item) => {
        const label = item?.label || '';
        let value = item?.value != null ? String(item.value) : '';
        if (label === '最近活跃' && value && value !== EMPTY) {
          value = formatMessageTime(value) || value;
        }
        return [label, value];
      }).filter(([label]) => label);
      details.innerHTML = rows.map(([label, value]) => `
        <div class="user-profile-detail-row">
          <dt>${escapeHtml(label)}</dt>
          <dd class="${value === EMPTY ? 'is-empty' : ''}">${escapeHtml(value)}</dd>
        </div>`).join('') || '<div class="user-profile-detail-row"><dt>说明</dt><dd>暂无更多字段</dd></div>';
      const composeBtn = document.getElementById('btn-user-profile-compose');
      const canSend = profile.canSendDingtalkMessage !== false;
      if (composeBtn) composeBtn.hidden = !canSend;
      const logBtn = document.getElementById('btn-user-profile-message-log');
      if (logBtn) logBtn.hidden = !canSend;
      const subtitle = document.getElementById('user-profile-subtitle');
      if (subtitle) {
        subtitle.textContent = canSend
          ? '查看详细信息，或通过钉钉机器人私聊对方。'
          : '查看用户详细信息。';
      }
    }

    function resetUserProfileMessageLogPanel() {
      userProfileMessageLogOpen = false;
      const panel = document.getElementById('user-profile-message-log');
      const logBtn = document.getElementById('btn-user-profile-message-log');
      if (panel) {
        panel.classList.remove('open');
        panel.innerHTML = '';
      }
      if (logBtn) logBtn.textContent = '查看记录';
    }

    function renderUserProfileMessageLogEntries(entries, total) {
      const panel = document.getElementById('user-profile-message-log');
      if (!panel) return;
      if (!entries.length) {
        panel.innerHTML = '<div class="user-profile-message-log-empty">暂无发送记录</div>';
        return;
      }
      panel.innerHTML = entries.map((item) => {
        const time = escapeHtml(item.timeBj || item.sentAt || '');
        const operator = escapeHtml(item.operatorLabel || item.operatorStaffId || '超管');
        const body = escapeHtml(item.message || '');
        return `<div class="user-profile-message-log-item">
          <div class="user-profile-message-log-meta">${time} · ${operator}</div>
          <div class="user-profile-message-log-body">${body}</div>
        </div>`;
      }).join('');
      if (total > entries.length) {
        panel.insertAdjacentHTML(
          'beforeend',
          `<div class="user-profile-message-log-empty">共 ${total} 条，仅展示最近 ${entries.length} 条</div>`,
        );
      }
    }

    async function loadUserProfileMessageLog() {
      if (!userProfileTargetStaffId || userProfileMessageLogLoading) return;
      const panel = document.getElementById('user-profile-message-log');
      if (!panel) return;
      userProfileMessageLogLoading = true;
      panel.classList.add('open');
      panel.innerHTML = '<div class="user-profile-message-log-empty">加载中…</div>';
      try {
        const qs = new URLSearchParams({
          staffId: userProfileTargetStaffId,
          limit: '50',
          offset: '0',
        });
        const resp = await fetch(`${API}/api/admin/user-profile/message-log?${qs}`, {
          credentials: 'same-origin',
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) {
          panel.innerHTML = `<div class="user-profile-message-log-empty">${escapeHtml(data.error || '加载失败')}</div>`;
          return;
        }
        renderUserProfileMessageLogEntries(data.entries || [], Number(data.total) || 0);
      } catch (_) {
        panel.innerHTML = '<div class="user-profile-message-log-empty">加载失败，请稍后重试</div>';
      } finally {
        userProfileMessageLogLoading = false;
      }
    }

    async function toggleUserProfileMessageLog() {
      const logBtn = document.getElementById('btn-user-profile-message-log');
      const compose = document.getElementById('user-profile-compose');
      if (!compose?.classList.contains('open')) {
        compose?.classList.add('open');
        document.getElementById('btn-user-profile-send')?.removeAttribute('hidden');
        const composeBtn = document.getElementById('btn-user-profile-compose');
        if (composeBtn) composeBtn.textContent = '收起';
      }
      userProfileMessageLogOpen = !userProfileMessageLogOpen;
      if (logBtn) logBtn.textContent = userProfileMessageLogOpen ? '收起记录' : '查看记录';
      if (userProfileMessageLogOpen) {
        await loadUserProfileMessageLog();
      } else {
        resetUserProfileMessageLogPanel();
      }
    }

    function resetUserProfileCompose() {
      const compose = document.getElementById('user-profile-compose');
      const msgEl = document.getElementById('user-profile-message');
      const sendBtn = document.getElementById('btn-user-profile-send');
      const composeBtn = document.getElementById('btn-user-profile-compose');
      if (compose) compose.classList.remove('open');
      if (msgEl) msgEl.value = '';
      if (sendBtn) sendBtn.hidden = true;
      if (composeBtn) composeBtn.textContent = '发消息';
      resetUserProfileMessageLogPanel();
    }

    async function setUserProfileModalOpen(open) {
      const modal = document.getElementById('user-profile-modal');
      if (!modal) return;
      if (!open) {
        resetUserProfileCompose();
        userProfileTargetStaffId = '';
        setUserProfileStatus('');
        if (modal.classList.contains('open')) {
          await animateOverlayClose(modal);
          modal.classList.remove('open');
        }
        modal.setAttribute('aria-hidden', 'true');
        return;
      }
      modal.classList.add('open');
      modal.setAttribute('aria-hidden', 'false');
    }

    async function openUserProfileModal(staffId, fallbackLabel = '') {
      if (!(currentAuthUser?.staffId || '').trim()) return;
      const uid = String(staffId || '').trim();
      if (!uid || userProfileLoading) return;
      userProfileTargetStaffId = uid;
      resetUserProfileCompose();
      setUserProfileStatus('加载中…');
      const head = document.getElementById('user-profile-head');
      const details = document.getElementById('user-profile-details');
      if (head) head.innerHTML = '';
      if (details) details.innerHTML = '';
      await setUserProfileModalOpen(true);
      const cached = userProfileCache.get(uid);
      if (cached && Date.now() - cached.at < USER_PROFILE_CACHE_TTL_MS) {
        renderUserProfileCard(cached.profile);
        setUserProfileStatus('');
        return;
      }
      userProfileLoading = true;
      try {
        const qs = new URLSearchParams({
          staffId: uid,
          displayName: String(fallbackLabel || '').trim(),
        });
        const resp = await fetch(`${API}/api/admin/user-profile?${qs.toString()}`, {
          credentials: 'same-origin',
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) {
          setUserProfileStatus(data.error || '加载失败', 'error');
          return;
        }
        const profilePayload = data.profile || {};
        userProfileCache.set(uid, { at: Date.now(), profile: profilePayload });
        renderUserProfileCard(profilePayload);
        setUserProfileStatus('');
      } catch (_) {
        setUserProfileStatus('加载失败，请稍后重试', 'error');
      } finally {
        userProfileLoading = false;
      }
    }

    async function sendUserProfileDingtalkMessage() {
      if (userProfileSending || !userProfileTargetStaffId) return;
      const msgEl = document.getElementById('user-profile-message');
      const message = (msgEl?.value || '').trim();
      if (!message) {
        setUserProfileStatus('请输入消息内容', 'error');
        msgEl?.focus();
        return;
      }
      userProfileSending = true;
      const sendBtn = document.getElementById('btn-user-profile-send');
      if (sendBtn) sendBtn.disabled = true;
      setUserProfileStatus('发送中…');
      try {
        const resp = await fetch(`${API}/api/admin/user-profile/send-message`, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'same-origin',
          body: JSON.stringify({ staffId: userProfileTargetStaffId, message }),
        });
        const data = await resp.json().catch(() => ({}));
        if (!resp.ok) {
          setUserProfileStatus(data.error || '发送失败', 'error');
          return;
        }
        if (msgEl) msgEl.value = '';
        setUserProfileStatus('已通过钉钉发送', 'success');
        if (userProfileMessageLogOpen) {
          void loadUserProfileMessageLog();
        }
      } catch (_) {
        setUserProfileStatus('发送失败，请稍后重试', 'error');
      } finally {
        userProfileSending = false;
        if (sendBtn) sendBtn.disabled = false;
      }
    }

    let adminListUsers = [];
    let adminListCanManage = false;
    let adminListSaving = false;
    let adminListLoading = false;
    let adminPermissionDefs = [];
    let adminAuditEntries = [];
    let adminAuditLoading = false;
    let moaCallLogEntries = [];
    let moaCallLogTotal = 0;
    let moaCallLogHasMore = false;
    let moaCallLogLoading = false;
    let moaCallLogLoadingMore = false;
    /** 操作记录卡片「参数」展示上限（超出截断并加省略号） */
    const CALL_LOG_PARAMS_DISPLAY_MAX = 160;
    let callLogCustomRange = null;
    let callLogOperatorStaffId = '';
    let callLogTitleKeyword = '';
    let callLogTitleSearchTimer = null;
    let callLogReplayEntryId = '';
    let callLogReplayCanRun = false;
    let callLogReplayRunning = false;
    let callLogReplayLoadSeq = 0;
    const MOA_CALL_LOG_PAGE_SIZE = 100;

    function buildAdminPermissionsHtml(user) {
      if (!user?.isAdmin) return '';
      const perms = user.permissions && typeof user.permissions === 'object'
        ? user.permissions
        : {};
      const defs = adminPermissionDefs.length
        ? adminPermissionDefs
        : [
            { key: 'super_admin', label: '超级管理员' },
            { key: 'code_modify', label: '代码修改' },
            { key: 'source_file', label: '源文件导出' },
            { key: 'online', label: '操作线上环境' },
          ];
      const staffId = String(user.staffId || '').trim();
      const isSuperAdmin = !!perms.super_admin;
      const editable = adminListCanManage && !user.protected;
      const boxes = defs.map((def) => {
        const key = String(def.key || '').trim();
        if (!key) return '';
        const checked = isSuperAdmin && key !== 'super_admin' ? true : !!perms[key];
        const readonly = !editable || (isSuperAdmin && key !== 'super_admin');
        const cls = ['admin-list-perm', checked ? 'is-on' : '', readonly ? 'is-readonly' : '']
          .filter(Boolean)
          .join(' ');
        const disabled = readonly ? ' disabled' : '';
        const checkedAttr = checked ? ' checked' : '';
        return `<label class="${cls}" data-staff-id="${escapeHtml(staffId)}" data-perm-key="${escapeHtml(key)}">
          <input type="checkbox" data-staff-id="${escapeHtml(staffId)}" data-perm-key="${escapeHtml(key)}"${checkedAttr}${disabled} />
          <span>${escapeHtml(def.label || key)}</span>
        </label>`;
      }).join('');
      return boxes ? `<div class="admin-list-perms">${boxes}</div>` : '';
    }

    function syncAdminListMenuItem() {
      const btn = document.getElementById('btn-admin-list');
      if (!btn) return;
      const user = currentAuthUser;
      const visible = user && !isGuestStaffId(user.staffId);
      btn.hidden = !visible;
      btn.title = '查看全员身份与管理员权限';
      syncOpenApiMenuItem();
    }

    function syncOpenApiMenuItem() {
      const btn = document.getElementById('btn-open-api');
      if (!btn) return;
      const user = currentAuthUser;
      btn.hidden = !(user && userIsWebAdmin(user));
      btn.title = '生成或复制 Open API Token';
      syncLogoutMenuItem();
    }

    function userMenuHasVisibleItems() {
      const dropdown = document.getElementById('user-menu-dropdown');
      if (!dropdown) return false;
      return [...dropdown.querySelectorAll('button[role="menuitem"]')].some((el) => !el.hidden);
    }

    function userMenuOpensProfileOnTap() {
      return document.documentElement.classList.contains('web-agent-mobile')
        && !!(currentAuthUser?.staffId || '').trim();
    }

    function syncUserMenuDropdownInteractivity() {
      const btn = document.getElementById('user-menu-btn');
      if (!btn) return;
      const hasItem = userMenuHasVisibleItems();
      const profileTap = userMenuOpensProfileOnTap() && !hasItem;
      btn.setAttribute('aria-haspopup', hasItem ? 'menu' : 'false');
      btn.classList.toggle('user-menu-no-dropdown', !hasItem && !profileTap);
      btn.title = profileTap ? '查看我的资料' : '';
      if (!hasItem) void setUserMenuOpen(false);
    }

    function purgeMobileLogoutControl() {
      if (!document.documentElement.classList.contains('web-agent-mobile')) return;
      document.getElementById('user-menu-logout-park')?.remove();
      document.getElementById('btn-logout')?.remove();
    }

    function purgeMobileLoginHeader() {
      if (!document.documentElement.classList.contains('web-agent-mobile')) return;
      const loginBtn = document.getElementById('btn-login');
      if (!loginBtn) return;
      loginBtn.hidden = true;
      loginBtn.setAttribute('aria-hidden', 'true');
    }

    /** 手机顶栏：工具台 + 设置 + 头像；无快捷入口；登录/退出仍隐藏 */
    function syncMobileHeaderToolbar() {
      if (!document.documentElement.classList.contains('web-agent-mobile')) return;
      ['btn-catalog'].forEach((id) => {
        const el = document.getElementById(id);
        if (!el) return;
        if (el.dataset.mobileHeaderSuppressed === '1') {
          el.hidden = false;
          delete el.dataset.mobileHeaderSuppressed;
        }
      });
      purgeMobileLogoutControl();
      purgeMobileLoginHeader();
    }

    /** 桌面顶栏收起时不展示退出；手机版无退出菜单项（DOM 已移除） */
    function syncLogoutMenuItem() {
      if (document.documentElement.classList.contains('web-agent-mobile')) {
        purgeMobileLogoutControl();
        syncUserMenuDropdownInteractivity();
        return;
      }
      const logoutBtn = document.getElementById('btn-logout');
      if (!logoutBtn) return;
      const dockedInSidebar = isUserMenuDockedInSidebar();
      const hideInHeader = !!(currentAuthUser && !dockedInSidebar);
      const dropdown = document.getElementById('user-menu-dropdown');
      if (dropdown && logoutBtn.parentElement !== dropdown) dropdown.appendChild(logoutBtn);
      logoutBtn.hidden = hideInHeader;
      syncUserMenuDropdownInteractivity();
    }

    const OPEN_API_TOKEN_SESSION_KEY = 'webAgentOpenApiLastToken';

    let openApiTokenPlain = '';
    let openApiLoading = false;
    /** 服务端已存在 Token（本页未必有完整明文） */
    let openApiRemoteHasToken = false;

    function getStoredOpenApiTokenPlain() {
      try {
        return String(sessionStorage.getItem(OPEN_API_TOKEN_SESSION_KEY) || '').trim();
      } catch {
        return '';
      }
    }

    function setStoredOpenApiTokenPlain(token) {
      const text = String(token || '').trim();
      try {
        if (text) sessionStorage.setItem(OPEN_API_TOKEN_SESSION_KEY, text);
        else sessionStorage.removeItem(OPEN_API_TOKEN_SESSION_KEY);
      } catch { /* ignore */ }
    }

    function resolveOpenApiTokenPlain() {
      return String(openApiTokenPlain || getStoredOpenApiTokenPlain() || '').trim();
    }

    function shellSingleQuotedJson(jsonText) {
      return String(jsonText || '').replace(/'/g, `'\\''`);
    }

    function openApiSubmitExampleBodyJson() {
      return JSON.stringify({
        message: '你好，请简要说明 Web Agent 能做什么',
      });
    }

    function refreshOpenApiGuideExamples() {
      const base = `${window.location.origin}/api/open/v1`;
      const submitPre = document.getElementById('open-api-example-submit');
      const queryPre = document.getElementById('open-api-example-query');
      const tokenHint = resolveOpenApiTokenPlain() || 'YOUR_TOKEN';
      if (submitPre) {
        const submitBody = shellSingleQuotedJson(openApiSubmitExampleBodyJson());
        submitPre.textContent =
          `curl -sS -X POST '${base}/task/submit' \\\n`
          + `  -H 'Authorization: Bearer ${tokenHint}' \\\n`
          + `  -H 'Content-Type: application/json' \\\n`
          + `  -d '${submitBody}'`;
      }
      if (queryPre) {
        queryPre.textContent =
          `curl -sS -X POST '${base}/task/query' \\\n`
          + `  -H 'Authorization: Bearer ${tokenHint}' \\\n`
          + `  -H 'Content-Type: application/json' \\\n`
          + `  -d '{"task_id":"<submit 返回的 task_id>"}'`;
      }
    }

    async function setOpenApiModalOpen(open) {
      const modal = document.getElementById('open-api-modal');
      if (!modal) return;
      if (!open) {
        if (modal.classList.contains('open')) {
          await animateOverlayClose(modal);
          modal.classList.remove('open');
        }
        openApiTokenPlain = resolveOpenApiTokenPlain();
        modal.setAttribute('aria-hidden', 'true');
        return;
      }
      const baseEl = document.getElementById('open-api-base-url');
      if (baseEl) {
        baseEl.innerHTML =
          `向 <code>${window.location.origin}/api/open/v1</code> 发 POST JSON，`
          + `请求头填写 <code>Authorization: Bearer &lt;Token&gt;</code>。`;
      }
      refreshOpenApiGuideExamples();
      modal.classList.add('open');
      modal.setAttribute('aria-hidden', 'false');
      void refreshOpenApiTokenStatus();
    }

    function renderOpenApiTokenField() {
      const input = document.getElementById('open-api-token-input');
      const meta = document.getElementById('open-api-meta');
      const genBtn = document.getElementById('btn-open-api-generate');
      const copyBtn = document.getElementById('btn-open-api-copy');
      const plain = resolveOpenApiTokenPlain();
      if (plain) openApiTokenPlain = plain;
      if (input) {
        if (plain) {
          input.value = plain;
          input.placeholder = '';
        } else {
          input.value = '';
        }
      }
      if (genBtn) {
        genBtn.textContent = (plain || openApiRemoteHasToken) ? '重新生成' : '生成 Token';
        genBtn.disabled = openApiLoading;
      }
      if (copyBtn) {
        const canCopy = !!plain && !openApiLoading;
        copyBtn.disabled = !canCopy;
        copyBtn.classList.toggle('no-token', !plain);
        copyBtn.title = plain ? '复制完整 Token' : '完整 Token 仅在本页生成后保存，请重新生成后再复制';
      }
      if (meta && openApiLoading) {
        meta.textContent = '加载中…';
      }
      if (document.getElementById('open-api-modal')?.classList.contains('open')) {
        refreshOpenApiGuideExamples();
      }
    }

    async function refreshOpenApiTokenStatus() {
      openApiLoading = true;
      const preservedPlain = resolveOpenApiTokenPlain();
      if (preservedPlain) openApiTokenPlain = preservedPlain;
      renderOpenApiTokenField();
      try {
        const data = await api('/api/admin/open-api/token');
        openApiRemoteHasToken = !!data?.hasToken;
        const cachedPlain = resolveOpenApiTokenPlain();
        if (cachedPlain) openApiTokenPlain = cachedPlain;
        const input = document.getElementById('open-api-token-input');
        const meta = document.getElementById('open-api-meta');
        if (input && !cachedPlain && data?.hasToken && data.tokenPreview) {
          input.value = '';
          input.placeholder = `已生成（${data.tokenPreview}）；本页未保存完整 Token，请点「重新生成」后再复制`;
        }
        if (meta && data?.hasToken && data.updatedAt) {
          const when = new Date(data.updatedAt * 1000);
          meta.textContent = Number.isFinite(when.getTime())
            ? `上次更新：${when.toLocaleString()}`
            : '';
        } else if (meta) {
          meta.textContent = '';
        }
      } catch (err) {
        const meta = document.getElementById('open-api-meta');
        if (meta) meta.textContent = String(err?.message || err || '加载失败');
      } finally {
        openApiLoading = false;
        renderOpenApiTokenField();
      }
    }

    async function generateOpenApiToken() {
      if (openApiLoading) return;
      const hadToken = !!resolveOpenApiTokenPlain()
        || !!document.getElementById('open-api-token-input')?.placeholder?.includes('已生成');
      if (hadToken && !window.confirm('重新生成将使旧 Token 立即失效，是否继续？')) return;
      openApiLoading = true;
      renderOpenApiTokenField();
      try {
        const data = await api('/api/admin/open-api/token/generate', { method: 'POST' });
        const fresh = String(data?.token || '').trim();
        if (fresh) {
          openApiTokenPlain = fresh;
          setStoredOpenApiTokenPlain(fresh);
          openApiRemoteHasToken = true;
        }
        const meta = document.getElementById('open-api-meta');
        if (meta) {
          const when = data?.updatedAt != null ? new Date(Number(data.updatedAt) * 1000) : null;
          meta.textContent = Number.isFinite(when?.getTime())
            ? `上次更新：${when.toLocaleString()}`
            : '已生成，可点「复制」';
        }
        renderOpenApiTokenField();
      } catch (err) {
        const meta = document.getElementById('open-api-meta');
        if (meta) meta.textContent = String(err?.message || err || '生成失败');
      } finally {
        openApiLoading = false;
        renderOpenApiTokenField();
      }
    }

    async function copyOpenApiToken() {
      const input = document.getElementById('open-api-token-input');
      let text = resolveOpenApiTokenPlain() || String(input?.value || '').trim();
      const meta = document.getElementById('open-api-meta');
      if (!text) {
        if (meta) meta.textContent = '请先生成 Token；仅预览无法复制，需本会话内生成后点「复制」。';
        return;
      }
      openApiTokenPlain = text;
      setStoredOpenApiTokenPlain(text);
      if (input) {
        input.value = text;
        input.placeholder = '';
      }
      let ok = await writeMessageClipboard(text);
      if (!ok && input) {
        input.focus();
        input.select();
        ok = copyPlainTextSync(text);
      }
      if (meta) meta.textContent = ok ? '已复制到剪贴板' : '复制失败，请手动选中上方 Token 后复制';
    }

    function adminListUserSortKey(user) {
      const isSuperAdmin = !!(user.isSuperAdmin || user.permissions?.super_admin);
      const tier = (user.protected && isSuperAdmin)
        ? 0
        : (isSuperAdmin ? 1 : (user.isAdmin ? 2 : 3));
      const name = publicDisplayName(String(user.displayName || '')).toLowerCase();
      const staffId = String(user.staffId || '').toLowerCase();
      return [tier, name, staffId];
    }

    function sortAdminListUsers(users) {
      return [...users].sort((a, b) => {
        const ka = adminListUserSortKey(a);
        const kb = adminListUserSortKey(b);
        for (let i = 0; i < ka.length; i += 1) {
          if (ka[i] < kb[i]) return -1;
          if (ka[i] > kb[i]) return 1;
        }
        return 0;
      });
    }

    function filterAdminListUsers(users, query) {
      const needle = String(query || '').trim().toLowerCase();
      if (!needle) return users;
      return users.filter((user) => {
        const name = publicDisplayName(String(user.displayName || '')).toLowerCase();
        return name.includes(needle);
      });
    }

    function updateAdminListMeta(total, filtered, query) {
      const meta = document.getElementById('admin-list-meta');
      if (!meta) return;
      if (!total) {
        meta.textContent = '暂无用户';
        return;
      }
      if (query) {
        meta.textContent = `共 ${total} 人，匹配 ${filtered} 人`;
        return;
      }
      meta.textContent = `共 ${total} 人`;
    }

    function canUserSelfQuitAdmin(user) {
      if (!user?.isAdmin || user.protected || !user.canQuit) return false;
      const staffId = String(user.staffId || '').trim();
      const currentId = String(currentAuthUser?.staffId || '').trim();
      return staffId && staffId === currentId;
    }

    function canCurrentUserSelfQuitAdmin() {
      const user = currentAuthUser;
      if (!user?.staffId || isGuestStaffId(user.staffId)) return false;
      if (!userIsWebAdmin(user) && !isCurrentUserAdminInList()) return false;
      const staffId = String(user.staffId).trim();
      const listUser = adminListUsers.find((item) => item.staffId === staffId);
      return listUser ? canUserSelfQuitAdmin(listUser) : false;
    }

    function renderAdminListBody() {
      const list = document.getElementById('admin-list-body');
      if (!list) return;
      const query = document.getElementById('admin-list-search')?.value || '';
      const filtered = filterAdminListUsers(adminListUsers, query);
      updateAdminListMeta(adminListUsers.length, filtered.length, query.trim());
      if (!filtered.length) {
        list.innerHTML = adminListLoading
          ? '<div class="collaborators-empty">加载中…</div>'
          : '<div class="collaborators-empty">无匹配用户</div>';
        return;
      }
      list.innerHTML = filtered.map((user) => {
        const staffId = String(user.staffId || '').trim();
        const name = escapeHtml(publicDisplayName((user.displayName || '未知用户').trim()));
        const isSuperAdmin = user.isAdmin && !!(user.isSuperAdmin || user.permissions?.super_admin);
        const roleTagHtml = user.isAdmin
          ? (() => {
            const roleClass = isSuperAdmin
              ? 'admin-list-role is-super-admin'
              : 'admin-list-role is-admin';
            const roleText = isSuperAdmin ? '超管' : '管理员';
            return `<span class="${roleClass}">${roleText}</span>`;
          })()
          : '';
        let actionHtml = '';
        const currentId = String(currentAuthUser?.staffId || '').trim();
        const isSelf = staffId === currentId;
        if (adminListCanManage && !user.protected) {
          const actions = [];
          if (user.isAdmin && !isSelf) {
            actions.push(`<button type="button" class="admin-list-action revoke" data-staff-id="${escapeHtml(staffId)}" data-set-admin="0">撤销</button>`);
          } else if (!user.isAdmin) {
            actions.push(`<button type="button" class="admin-list-action grant" data-staff-id="${escapeHtml(staffId)}" data-set-admin="1">设为管理</button>`);
          }
          actionHtml = actions.length ? `<div class="admin-list-item-actions">${actions.join('')}</div>` : '';
        }
        const avatarHtml = buildStaffPickerAvatarHtml(user);
        return `
          <div class="admin-list-item">
            <div class="admin-list-item-main">
              <div class="admin-list-item-head">
                <div class="admin-list-item-name-wrap">${avatarHtml}<div class="admin-list-item-name">${name}</div></div>
                ${roleTagHtml}
                ${actionHtml}
              </div>
              ${buildAdminPermissionsHtml(user)}
            </div>
          </div>`;
      }).join('');
      hydrateAvatars(list);
      list.querySelectorAll('.admin-list-action').forEach((btn) => {
        btn.addEventListener('click', () => {
          const targetId = (btn.dataset.staffId || '').trim();
          if (btn.dataset.quitAdmin === '1') {
            if (targetId) void quitAdminRoleForUser(targetId, btn);
            return;
          }
          const setAdmin = btn.dataset.setAdmin === '1';
          if (targetId) void setAdminRoleForUser(targetId, setAdmin, btn);
        });
      });
      list.querySelectorAll('.admin-list-perms input[type="checkbox"]').forEach((input) => {
        input.addEventListener('change', () => {
          const targetId = (input.dataset.staffId || '').trim();
          const permKey = (input.dataset.permKey || '').trim();
          if (!targetId || !permKey) return;
          void setAdminPermissionsForUser(targetId, input);
        });
      });
    }

    async function setAdminPermissionsForUser(staffId, changedInput) {
      if (adminListSaving || !adminListCanManage) return;
      const idx = adminListUsers.findIndex((item) => item.staffId === staffId);
      if (idx < 0) return;
      const user = adminListUsers[idx];
      if (!user.isAdmin || user.protected) return;

      const defs = adminPermissionDefs.length
        ? adminPermissionDefs
        : [{ key: 'super_admin' }, { key: 'code_modify' }, { key: 'source_file' }, { key: 'online' }];
      const permissions = {};
      defs.forEach((def) => {
        const key = String(def.key || '').trim();
        if (!key) return;
        const input = document.querySelector(
          `.admin-list-perms input[data-staff-id="${CSS.escape(staffId)}"][data-perm-key="${CSS.escape(key)}"]`,
        );
        permissions[key] = !!(input && input.checked);
      });

      adminListSaving = true;
      if (changedInput) changedInput.disabled = true;
      try {
        const data = await api('/api/admin/users/permissions', {
          method: 'POST',
          body: JSON.stringify({ staffId, permissions }),
        });
        const nextPerms = data.permissions && typeof data.permissions === 'object'
          ? data.permissions
          : permissions;
        const isSuperAdmin = data.isSuperAdmin === true || !!nextPerms.super_admin;
        adminListUsers[idx] = { ...user, permissions: nextPerms, isSuperAdmin };
        adminListUsers = sortAdminListUsers(adminListUsers);
        renderAdminListBody();
        if (currentAuthUser?.staffId === staffId) {
          currentAuthUser.isSuperAdmin = isSuperAdmin;
          currentAuthUser.permissions = nextPerms;
          syncUserAdminBadgeFromUser(currentAuthUser);
        }
        showWebToast('权限已更新');
      } catch (err) {
        if (changedInput) changedInput.checked = !changedInput.checked;
        showWebToast(err.message || '权限更新失败', { error: true, durationMs: 4200 });
        renderAdminListBody();
      } finally {
        adminListSaving = false;
      }
    }

    async function loadAdminListUsers() {
      adminListLoading = true;
      renderAdminListBody();
      try {
        const data = await api('/api/admin/users');
        adminListUsers = sortAdminListUsers(Array.isArray(data.users) ? data.users : []);
        seedUserAvatarCacheFromStaffUsers(adminListUsers);
        adminListCanManage = !!data.canManage;
        adminPermissionDefs = Array.isArray(data.permissionDefinitions)
          ? data.permissionDefinitions
          : [];
      } finally {
        adminListLoading = false;
        renderAdminListBody();
        syncAdminApplyMenuItem();
      }
    }

    async function quitAdminRoleForUser(staffId, btn) {
      if (adminListSaving) return;
      const currentId = String(currentAuthUser?.staffId || '').trim();
      if (staffId !== currentId) return;
      void setAdminListModalOpen(false);
      adminListSaving = true;
      if (btn) btn.disabled = true;
      syncAdminApplyMenuItem();
      try {
        await api('/api/admin/quit', { method: 'POST' });
        const idx = adminListUsers.findIndex((item) => item.staffId === staffId);
        if (idx >= 0) {
          adminListUsers[idx] = {
            ...adminListUsers[idx],
            isAdmin: false,
            isSuperAdmin: false,
            canQuit: false,
            permissions: {},
          };
        }
        adminListUsers = sortAdminListUsers(adminListUsers);
        renderAdminListBody();
        if (currentAuthUser?.staffId === staffId) {
          currentAuthUser.isAdmin = false;
          currentAuthUser.isSuperAdmin = false;
          delete currentAuthUser.permissions;
          syncUserAdminBadgeFromUser(currentAuthUser);
          if (bookmarksPanel) bookmarksPanel.setAdmin(false);
          if (messageBoardPanel) messageBoardPanel.setAdmin(false);
          syncAdminApplyMenuItem();
        }
        showWebToast('已退出管理员');
      } catch (err) {
        showWebToast(err.message || '操作失败', { error: true, durationMs: 4200 });
        renderAdminListBody();
      } finally {
        adminListSaving = false;
        syncAdminApplyMenuItem();
      }
    }

    async function setAdminRoleForUser(staffId, isAdmin, btn) {
      if (adminListSaving || !adminListCanManage) return;
      adminListSaving = true;
      if (btn) btn.disabled = true;
      try {
        await api('/api/admin/users/set', {
          method: 'POST',
          body: JSON.stringify({ staffId, isAdmin }),
        });
        const idx = adminListUsers.findIndex((item) => item.staffId === staffId);
        if (idx >= 0) {
          adminListUsers[idx] = {
            ...adminListUsers[idx],
            isAdmin,
            isSuperAdmin: false,
            permissions: isAdmin
              ? { super_admin: false, code_modify: false, source_file: false, online: false }
              : {},
          };
        }
        renderAdminListBody();
        if (currentAuthUser?.staffId === staffId) {
          currentAuthUser.isAdmin = isAdmin;
          currentAuthUser.isSuperAdmin = false;
          if (!isAdmin) delete currentAuthUser.permissions;
          syncUserAdminBadgeFromUser(currentAuthUser);
          if (bookmarksPanel) bookmarksPanel.setAdmin(isAdmin);
          if (messageBoardPanel) messageBoardPanel.setAdmin(isAdmin);
          syncAdminApplyMenuItem();
        }
        showWebToast(isAdmin ? '已设为管理员' : '已撤销管理员');
      } catch (err) {
        showWebToast(err.message || '操作失败', { error: true, durationMs: 4200 });
        renderAdminListBody();
      } finally {
        adminListSaving = false;
      }
    }

    function formatAdminAuditTime(iso) {
      const raw = String(iso || '').trim();
      if (!raw) return '';
      const date = new Date(raw);
      if (Number.isNaN(date.getTime())) return raw;
      const pad = (n) => String(n).padStart(2, '0');
      return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}`;
    }

    function renderAdminAuditBody() {
      const list = document.getElementById('admin-audit-body');
      const meta = document.getElementById('admin-audit-meta');
      if (!list) return;
      if (meta) {
        meta.textContent = adminAuditLoading
          ? '加载中…'
          : (adminAuditEntries.length ? `共 ${adminAuditEntries.length} 条` : '暂无记录');
      }
      if (adminAuditLoading) {
        list.innerHTML = '<div class="collaborators-empty">加载中…</div>';
        return;
      }
      if (!adminAuditEntries.length) {
        list.innerHTML = '<div class="collaborators-empty">暂无操作记录</div>';
        return;
      }
      list.innerHTML = adminAuditEntries.map((entry) => {
        const action = escapeHtml(String(entry.actionLabel || entry.action || '操作'));
        const time = escapeHtml(formatAdminAuditTime(entry.ts));
        const operatorName = escapeHtml(publicDisplayName(String(entry.operatorName || '未知用户')));
        const operatorStaffId = String(entry.operatorStaffId || '').trim();
        const targetName = escapeHtml(publicDisplayName(String(entry.targetName || '')));
        const targetStaffId = String(entry.targetStaffId || '').trim();
        const detail = escapeHtml(String(entry.detail || '').trim());
        const operatorAvatar = buildStaffPickerAvatarHtml({
          staffId: operatorStaffId,
          displayName: entry.operatorName || operatorStaffId,
          avatarUrl: entry.operatorAvatarUrl || '',
        });
        const targetLine = targetName
          ? `<div class="admin-audit-item-target">对象：${targetName}${targetStaffId && targetStaffId !== operatorStaffId ? `（${escapeHtml(targetStaffId)}）` : ''}</div>`
          : '';
        const detailLine = detail ? `<div class="admin-audit-item-detail">${detail}</div>` : '';
        return `
          <div class="admin-audit-item">
            <div class="admin-audit-item-head">
              <div class="admin-audit-item-action">${action}</div>
              <div class="admin-audit-item-time">${time}</div>
            </div>
            <div class="admin-audit-item-operator">
              ${operatorAvatar}
              <div class="admin-audit-item-operator-name">${operatorName}</div>
            </div>
            ${targetLine}
            ${detailLine}
          </div>`;
      }).join('');
      hydrateAvatars(list);
    }

    async function loadAdminAuditEntries() {
      adminAuditLoading = true;
      renderAdminAuditBody();
      try {
        const data = await api('/api/admin/audit-log?limit=100');
        adminAuditEntries = Array.isArray(data.entries) ? data.entries : [];
        seedUserAvatarCacheFromStaffUsers(
          adminAuditEntries.flatMap((entry) => ([
            {
              staffId: entry.operatorStaffId,
              displayName: entry.operatorName,
              avatarUrl: entry.operatorAvatarUrl || '',
            },
            {
              staffId: entry.targetStaffId,
              displayName: entry.targetName,
              avatarUrl: entry.targetAvatarUrl || '',
            },
          ])),
        );
      } catch (err) {
        adminAuditEntries = [];
        showWebToast(err.message || '加载操作记录失败', { error: true, durationMs: 4200 });
      } finally {
        adminAuditLoading = false;
        renderAdminAuditBody();
      }
    }

    async function setAdminAuditModalOpen(open) {
      const modal = document.getElementById('admin-audit-modal');
      if (!modal) return;
      if (!open) {
        if (modal.classList.contains('open')) {
          await animateOverlayClose(modal);
          modal.classList.remove('open');
        }
        modal.setAttribute('aria-hidden', 'true');
        return;
      }
      modal.classList.add('open');
      modal.setAttribute('aria-hidden', 'false');
      renderAdminAuditBody();
      await loadAdminAuditEntries();
    }

    function renderMoaCallLogBody() {
      const list = document.getElementById('moa-call-log-body');
      const meta = document.getElementById('moa-call-log-meta');
      if (!list) return;
      if (meta) {
        if (moaCallLogLoading && !moaCallLogEntries.length) {
          meta.textContent = '加载中…';
        } else if (moaCallLogLoadingMore) {
          meta.textContent = `共 ${moaCallLogTotal} 条，已展示 ${moaCallLogEntries.length} 条 · 加载中…`;
        } else if (!moaCallLogTotal) {
          meta.textContent = callLogFilterActive() ? '无匹配记录' : '暂无记录';
        } else {
          const filterNote = callLogFilterActive() ? '（已筛选）' : '';
          meta.textContent = `共 ${moaCallLogTotal} 条${filterNote}，已展示 ${moaCallLogEntries.length} 条`;
        }
      }
      if (moaCallLogLoading && !moaCallLogEntries.length) {
        list.innerHTML = '<div class="collaborators-empty">加载中…</div>';
        return;
      }
      if (!moaCallLogEntries.length) {
        list.innerHTML = '<div class="collaborators-empty">暂无操作记录</div>';
        return;
      }
      list.innerHTML = moaCallLogEntries.map((entry) => {
        const operation = escapeHtml(String(entry.operation || 'MOA 调用'));
        const time = escapeHtml(String(entry.timeBj || entry.ts || ''));
        const operatorName = escapeHtml(publicDisplayName(String(entry.operatorName || '未知用户')));
        const operatorStaffId = String(entry.operatorStaffId || '').trim();
        const account = escapeHtml(String(entry.accountSummary || '').trim());
        const moaInterface = escapeHtml(
          String(entry.moaInterfaceDisplay || entry.moaInterface || '').trim()
            || [entry.serviceUrl, entry.method].filter(Boolean).join(' · '),
        );
        const paramsRaw = String(entry.paramsSummary || '').trim();
        const paramsTruncated = paramsRaw.length > CALL_LOG_PARAMS_DISPLAY_MAX;
        const params = escapeHtml(truncateDisplayText(paramsRaw, CALL_LOG_PARAMS_DISPLAY_MAX));
        const count = Number(entry.callCount || 1);
        const batchHint = count > 1 ? `（合并 ${count} 次）` : '';
        const operatorAvatar = buildStaffPickerAvatarHtml({
          staffId: operatorStaffId,
          displayName: entry.operatorName || operatorStaffId,
          avatarUrl: entry.operatorAvatarUrl || '',
        });
        const accountLine = account
          ? `<div class="admin-audit-item-target">账号：${account}</div>`
          : '';
        const interfaceLine = moaInterface
          ? `<div class="admin-audit-item-detail">接口：${moaInterface}${batchHint}</div>`
          : '';
        const paramsTitle = paramsTruncated
          ? ` title="${escapeHtml(paramsRaw).replace(/"/g, '&quot;')}"`
          : '';
        const paramsLine = params
          ? `<div class="admin-audit-item-detail admin-audit-item-detail-params"${paramsTitle}>参数：${params}</div>`
          : '';
        const entryId = escapeHtml(String(entry.id || '').trim());
        return `
          <div class="admin-audit-item" data-call-log-id="${entryId}">
            <div class="admin-audit-item-head">
              <div class="admin-audit-item-action">${operation}</div>
              <div class="admin-audit-item-time">${time}</div>
            </div>
            <div class="admin-audit-item-operator">
              ${operatorAvatar}
              <div class="admin-audit-item-operator-name">${operatorName}</div>
              <button type="button" class="call-log-replay-btn" data-entry-id="${entryId}">运行</button>
            </div>
            ${accountLine}
            ${interfaceLine}
            ${paramsLine}
          </div>`;
      }).join('');
      hydrateAvatars(list);
    }

    function setCallLogReplayModalOpen(open) {
      const modal = document.getElementById('call-log-replay-modal');
      if (!modal) return;
      if (!open) {
        modal.classList.remove('open');
        modal.setAttribute('aria-hidden', 'true');
        callLogReplayEntryId = '';
        callLogReplayCanRun = false;
        return;
      }
      modal.classList.add('open');
      modal.setAttribute('aria-hidden', 'false');
    }

    function readCallLogReplayParamsFromTable() {
      const root = document.getElementById('call-log-replay-fields');
      if (!root) return [];
      return Array.from(root.querySelectorAll('.call-log-replay-field')).map((row) => {
        const key = String(row.dataset.paramKey || '').trim();
        const input = row.querySelector('input');
        const value = input ? String(input.value || '').trim() : '';
        const placeholder = String(row.dataset.placeholder || '').trim();
        return { key, value, placeholder };
      }).filter((row) => row.key);
    }

    function clearCallLogReplayResult() {
      const el = document.getElementById('call-log-replay-result');
      if (!el) return;
      el.hidden = true;
      el.innerHTML = '';
    }

    function parseCallLogReplayRequestMeta(text) {
      const raw = String(text || '').trim();
      const reqIdx = raw.indexOf('请求信息:');
      const slice = reqIdx >= 0 ? raw.slice(reqIdx + '请求信息:'.length).trim() : raw;
      const pairs = [];
      const re = /([a-zA-Z_][\w]*)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^,\s]+))/g;
      let m;
      while ((m = re.exec(slice)) !== null) {
        pairs.push({ key: m[1], value: m[2] ?? m[3] ?? m[4] ?? '' });
      }
      return pairs;
    }

    function renderCallLogReplayResult(summary, tail, resultRows) {
      const el = document.getElementById('call-log-replay-result');
      if (!el) return;
      const sum = String(summary || '').trim();
      const tailText = String(tail || '').trim();
      const rows = Array.isArray(resultRows) ? resultRows : [];
      if (!sum && !tailText && !rows.length) {
        el.hidden = true;
        el.innerHTML = '';
        return;
      }
      const ok = /^成功/.test(sum);
      const bizHtml = rows.length
        ? rows.map(({ label, value }) => `
              <dt>${escapeHtml(String(label || ''))}</dt>
              <dd>${escapeHtml(String(value ?? ''))}</dd>`).join('')
        : '';
      let rawBlock = '';
      if (!bizHtml && tailText) {
        const trimmed = tailText.trim();
        if (trimmed.startsWith('{') || trimmed.startsWith('[')) {
          rawBlock = `<pre class="call-log-replay-result-raw">${escapeHtml(trimmed.slice(-600))}</pre>`;
        } else if (!trimmed.includes('请求信息:')) {
          rawBlock = `<pre class="call-log-replay-result-raw">${escapeHtml(trimmed.slice(-400))}</pre>`;
        }
      }
      el.hidden = false;
      el.innerHTML = `
        <div class="call-log-replay-result-head ${ok ? 'is-ok' : 'is-err'}">${escapeHtml(sum || (ok ? '成功' : '失败'))}</div>
        ${bizHtml ? `<dl class="call-log-replay-result-meta">${bizHtml}</dl>` : ''}
        ${rawBlock}`;
    }

    function renderCallLogReplayTable(rows) {
      const root = document.getElementById('call-log-replay-fields');
      if (!root) return;
      root.classList.remove('is-empty');
      if (!rows.length) {
        root.classList.add('is-empty');
        root.textContent = '无需修改参数，可直接运行';
        return;
      }
      root.innerHTML = rows.map((row) => {
        const key = escapeHtml(String(row.key || ''));
        const label = escapeHtml(String(row.label || row.key || ''));
        const val = escapeHtml(String(row.value || ''));
        const ph = escapeHtml(String(row.placeholder || ''));
        const phAttr = ph ? ` placeholder="${ph}"` : '';
        return `
          <div class="call-log-replay-field" data-param-key="${key}" data-placeholder="${ph}">
            <label for="call-log-replay-${key}">${label}</label>
            <input id="call-log-replay-${key}" type="text" value="${val}" aria-label="${label}"${phAttr} />
          </div>`;
      }).join('');
    }

    function callLogReplayFetchErrorMessage(err, fallback = '加载失败') {
      const raw = String(err?.message || err || '').trim();
      if (/^load failed$/i.test(raw) || /^failed to fetch$/i.test(raw)) {
        return '网络或服务异常，请刷新页面后重试';
      }
      return raw || fallback;
    }

    async function openCallLogReplayModal(entryId) {
      const id = String(entryId || '').trim();
      if (!id || callLogReplayRunning) return;
      const loadSeq = ++callLogReplayLoadSeq;
      callLogReplayEntryId = id;
      const sub = document.getElementById('call-log-replay-sub');
      const notice = document.getElementById('call-log-replay-notice');
      const help = document.getElementById('call-log-replay-help');
      const runBtn = document.getElementById('btn-call-log-replay-run');
      if (sub) sub.textContent = '加载中…';
      if (notice) {
        notice.hidden = true;
        notice.textContent = '';
        notice.classList.remove('is-warn');
      }
      if (help) help.textContent = '';
      clearCallLogReplayResult();
      renderCallLogReplayTable([]);
      if (runBtn) runBtn.disabled = true;
      setCallLogReplayModalOpen(true);
      try {
        const spec = await api(`/api/moa/call-log/replay-spec?id=${encodeURIComponent(id)}`);
        if (loadSeq !== callLogReplayLoadSeq) return;
        callLogReplayCanRun = spec.canReplay === true;
        if (sub) {
          const cap = spec.capabilityName ? ` · ${spec.capabilityName}` : '';
          sub.textContent = `${spec.operation || '操作'}${cap}`;
        }
        renderCallLogReplayTable(Array.isArray(spec.paramsRows) ? spec.paramsRows : []);
        const extra = String(spec.replayHint || '').trim();
        if (notice && extra) {
          notice.hidden = false;
          notice.textContent = extra;
        }
        if (help) {
          help.textContent = spec.canReplay
            ? '修改参数后点「直接运行」，将按 registry 脚本执行（不经过 Agent）。'
            : (spec.reason || '暂不支持运行');
        }
        if (notice && !spec.canReplay) {
          notice.hidden = false;
          notice.classList.add('is-warn');
          notice.textContent = spec.reason || '暂不支持运行';
        }
        if (runBtn) runBtn.disabled = !spec.canReplay;
      } catch (err) {
        if (loadSeq !== callLogReplayLoadSeq) return;
        const msg = callLogReplayFetchErrorMessage(err);
        if (notice) {
          notice.hidden = false;
          notice.classList.add('is-warn');
          notice.textContent = msg;
        }
        if (help) help.textContent = '';
        callLogReplayCanRun = false;
        if (runBtn) runBtn.disabled = true;
      }
    }

    async function runCallLogReplayDirect() {
      if (!callLogReplayEntryId || !callLogReplayCanRun || callLogReplayRunning) return;
      const runBtn = document.getElementById('btn-call-log-replay-run');
      const help = document.getElementById('call-log-replay-help');
      callLogReplayRunning = true;
      if (runBtn) runBtn.disabled = true;
      if (help) help.textContent = '执行中…';
      clearCallLogReplayResult();
      try {
        const paramsRows = readCallLogReplayParamsFromTable();
        const result = await api('/api/moa/call-log/replay', {
          method: 'POST',
          body: JSON.stringify({
            entryId: callLogReplayEntryId,
            paramsRows,
            sessionId: currentSessionId || '',
          }),
        });
        const ok = result.ok === true;
        const displaySummary = String(result.displaySummary || result.summary || '').trim();
        showWebToast(displaySummary || (ok ? '执行成功' : '执行失败'), {
          error: !ok,
          durationMs: ok ? 3200 : 5200,
        });
        const tail = String(result.stdoutTail || result.stderrTail || result.detailTail || '').trim();
        renderCallLogReplayResult(
          displaySummary || result.summary || '',
          tail,
          Array.isArray(result.resultRows) ? result.resultRows : [],
        );
        if (help) {
          help.textContent = ok
            ? '执行完成，结果见下方。'
            : '执行失败，请查看下方输出或修改参数后重试。';
        }
        // 重跑后不刷新操作记录列表；下次打开「操作记录」弹窗时再 load（见 setMoaCallLogModalOpen）
      } catch (err) {
        const msg = callLogReplayFetchErrorMessage(err, '执行失败');
        showWebToast(msg, { error: true, durationMs: 4200 });
        renderCallLogReplayResult('失败', msg);
        if (help) help.textContent = '';
        if (runBtn) runBtn.disabled = false;
      } finally {
        callLogReplayRunning = false;
        if (runBtn && callLogReplayCanRun) runBtn.disabled = false;
      }
    }

    function maybeLoadMoreMoaCallLogFromScroll() {
      const list = document.getElementById('moa-call-log-body');
      if (!list || !moaCallLogHasMore || moaCallLogLoading || moaCallLogLoadingMore) return;
      const threshold = 96;
      if (list.scrollTop + list.clientHeight >= list.scrollHeight - threshold) {
        void loadMoaCallLogEntries({ append: true });
      }
    }

    function fillMoaCallLogViewportIfNeeded() {
      const list = document.getElementById('moa-call-log-body');
      if (!list || !moaCallLogHasMore || moaCallLogLoading || moaCallLogLoadingMore) return;
      if (list.scrollHeight <= list.clientHeight + 8) {
        void loadMoaCallLogEntries({ append: true });
      }
    }

    function seedMoaCallLogAvatars(entries) {
      seedUserAvatarCacheFromStaffUsers(
        entries.map((entry) => ({
          staffId: entry.operatorStaffId,
          displayName: entry.operatorName,
          avatarUrl: entry.operatorAvatarUrl || '',
        })),
      );
    }

    function resetCallLogFilters() {
      callLogOperatorStaffId = '';
      callLogCustomRange = null;
      callLogTitleKeyword = '';
      if (callLogTitleSearchTimer) {
        clearTimeout(callLogTitleSearchTimer);
        callLogTitleSearchTimer = null;
      }
      const select = document.getElementById('call-log-operator-select');
      if (select) select.value = '';
      const titleSearch = document.getElementById('call-log-title-search');
      if (titleSearch) titleSearch.value = '';
      syncCallLogDateUI();
    }

    function syncCallLogDateUI() {
      const startInput = usageDateFieldEl('start', 'callLog');
      const endInput = usageDateFieldEl('end', 'callLog');
      if (!startInput || !endInput) return;
      if (callLogCustomRange?.start && callLogCustomRange?.end) {
        setUsageDateFieldValue(startInput, callLogCustomRange.start);
        setUsageDateFieldValue(endInput, callLogCustomRange.end);
      } else {
        setUsageDateFieldValue(startInput, '');
        setUsageDateFieldValue(endInput, '');
        const hintEl = callLogDateRangeHintEl();
        if (hintEl) hintEl.textContent = '';
      }
      applyCallLogDateInputLimits();
    }

    function applyCallLogDateInputLimits() {
      const startInput = usageDateFieldEl('start', 'callLog');
      const endInput = usageDateFieldEl('end', 'callLog');
      const { minDate, maxDate } = resolveUsageDateBounds('callLog');
      const endValue = getUsageDateFieldValue(endInput);
      const startValue = getUsageDateFieldValue(startInput);
      const startMax = endValue ? clampUsageDateValue(endValue, minDate, maxDate) : maxDate;
      const endMin = startValue ? clampUsageDateValue(startValue, minDate, maxDate) : minDate;
      if (startInput) {
        const clampedStart = clampUsageDateValue(getUsageDateFieldValue(startInput), minDate, startMax);
        if (clampedStart !== getUsageDateFieldValue(startInput)) setUsageDateFieldValue(startInput, clampedStart);
      }
      if (endInput) {
        const clampedEnd = clampUsageDateValue(getUsageDateFieldValue(endInput), endMin, maxDate);
        if (clampedEnd !== getUsageDateFieldValue(endInput)) setUsageDateFieldValue(endInput, clampedEnd);
      }
      if (!document.getElementById('usage-date-picker')?.hidden && datePickerNamespace() === 'callLog') {
        renderUsageDatePicker();
      }
    }

    function applyCallLogCustomRange() {
      const startInput = usageDateFieldEl('start', 'callLog');
      const endInput = usageDateFieldEl('end', 'callLog');
      const start = getUsageDateFieldValue(startInput);
      const end = getUsageDateFieldValue(endInput);
      const hintEl = callLogDateRangeHintEl();
      if (!start || !end) {
        if (hintEl) hintEl.textContent = '请选择开始与结束日期';
        return;
      }
      if (start > end) {
        if (hintEl) hintEl.textContent = '开始日期不能晚于结束日期';
        return;
      }
      const spanDays = customUsageSpanDays(start, end);
      if (spanDays > CALL_LOG_MAX_CUSTOM_DAYS) {
        if (hintEl) hintEl.textContent = `自定义区间最长 ${CALL_LOG_MAX_CUSTOM_DAYS} 天`;
        return;
      }
      const { minDate, maxDate } = resolveUsageDateBounds('callLog');
      if (minDate && start < minDate) {
        if (hintEl) hintEl.textContent = `最早可选 ${minDate}`;
        return;
      }
      if (maxDate && end > maxDate) {
        if (hintEl) hintEl.textContent = '结束日期不能晚于今天';
        return;
      }
      if (hintEl) hintEl.textContent = '';
      applyCallLogDateInputLimits();
      callLogCustomRange = { start, end };
      void loadMoaCallLogEntries();
    }

    function resolveCallLogDateFilter() {
      if (callLogCustomRange?.start && callLogCustomRange?.end) {
        return { startDate: callLogCustomRange.start, endDate: callLogCustomRange.end };
      }
      return { startDate: '', endDate: '' };
    }

    function buildCallLogListQuery(offset) {
      const params = new URLSearchParams();
      params.set('limit', String(MOA_CALL_LOG_PAGE_SIZE));
      params.set('offset', String(offset));
      if (callLogOperatorStaffId) params.set('operatorStaffId', callLogOperatorStaffId);
      const { startDate, endDate } = resolveCallLogDateFilter();
      if (startDate) params.set('startDate', startDate);
      if (endDate) params.set('endDate', endDate);
      if (callLogTitleKeyword) params.set('titleKeyword', callLogTitleKeyword);
      return params.toString();
    }

    function callLogFilterActive() {
      const { startDate, endDate } = resolveCallLogDateFilter();
      return Boolean(callLogOperatorStaffId || startDate || endDate || callLogTitleKeyword);
    }

    async function loadCallLogOperators() {
      const select = document.getElementById('call-log-operator-select');
      if (!select) return;
      const prev = callLogOperatorStaffId || select.value || '';
      try {
        const data = await api('/api/moa/call-log/operators');
        const operators = Array.isArray(data.operators) ? data.operators : [];
        select.innerHTML = '<option value="">全部人员</option>'
          + operators.map((row) => {
            const id = escapeHtml(String(row.staffId || '').trim());
            const name = escapeHtml(publicDisplayName(String(row.displayName || row.staffId || '').trim()));
            return `<option value="${id}">${name}</option>`;
          }).join('');
        if (prev && operators.some((row) => String(row.staffId || '').trim() === prev)) {
          select.value = prev;
          callLogOperatorStaffId = prev;
        } else {
          select.value = '';
          callLogOperatorStaffId = '';
        }
      } catch (_) {
        select.innerHTML = '<option value="">全部人员</option>';
      }
    }

    async function loadMoaCallLogEntries({ append = false } = {}) {
      if (append) {
        moaCallLogLoadingMore = true;
      } else {
        moaCallLogLoading = true;
        moaCallLogEntries = [];
        moaCallLogTotal = 0;
        moaCallLogHasMore = false;
      }
      renderMoaCallLogBody();
      const offset = append ? moaCallLogEntries.length : 0;
      try {
        const data = await api(`/api/moa/call-log?${buildCallLogListQuery(offset)}`);
        const batch = Array.isArray(data.entries) ? data.entries : [];
        moaCallLogTotal = Number(data.total ?? moaCallLogEntries.length + batch.length);
        moaCallLogHasMore = data.hasMore === true
          || moaCallLogEntries.length + batch.length < moaCallLogTotal;
        moaCallLogEntries = append ? moaCallLogEntries.concat(batch) : batch;
        seedMoaCallLogAvatars(batch);
      } catch (err) {
        if (!append) {
          moaCallLogEntries = [];
          moaCallLogTotal = 0;
          moaCallLogHasMore = false;
        }
        showWebToast(err.message || '加载 MOA 调用记录失败', { error: true, durationMs: 4200 });
      } finally {
        moaCallLogLoading = false;
        moaCallLogLoadingMore = false;
        renderMoaCallLogBody();
        requestAnimationFrame(() => fillMoaCallLogViewportIfNeeded());
      }
    }

    async function setMoaCallLogModalOpen(open) {
      const modal = document.getElementById('moa-call-log-modal');
      if (!modal) return;
      if (!open) {
        if (usageDatePickerState.anchorEl?.closest('#call-log-filters')) closeUsageDatePicker();
        if (modal.classList.contains('open')) {
          await animateOverlayClose(modal);
          modal.classList.remove('open');
        }
        modal.setAttribute('aria-hidden', 'true');
        return;
      }
      resetCallLogFilters();
      const selfStaffId = String(currentAuthUser?.staffId || '').trim();
      if (selfStaffId) callLogOperatorStaffId = selfStaffId;
      modal.classList.add('open');
      modal.setAttribute('aria-hidden', 'false');
      renderMoaCallLogBody();
      await loadCallLogOperators();
      await loadMoaCallLogEntries();
    }

    async function setAdminListModalOpen(open) {
      const modal = document.getElementById('admin-list-modal');
      if (!modal) return;
      if (!open) {
        adminApplyInFlight = false;
        await setAdminAuditModalOpen(false);
        if (modal.classList.contains('open')) {
          await animateOverlayClose(modal);
          modal.classList.remove('open');
        }
        modal.setAttribute('aria-hidden', 'true');
        return;
      }
      adminApplyInFlight = false;
      const searchInput = document.getElementById('admin-list-search');
      if (searchInput) searchInput.value = '';
      modal.classList.add('open');
      modal.setAttribute('aria-hidden', 'false');
      renderAdminListBody();
      const applyBtn = document.getElementById('btn-apply-admin');
      if (applyBtn) applyBtn.hidden = true;
      await loadAdminListUsers();
      searchInput?.focus();
    }

    function isCurrentUserAdminInList() {
      const staffId = String(currentAuthUser?.staffId || '').trim();
      if (!staffId || !adminListUsers.length) return false;
      const listUser = adminListUsers.find((item) => item.staffId === staffId);
      return !!listUser?.isAdmin;
    }

    function syncAdminApplyMenuItem() {
      const btn = document.getElementById('btn-apply-admin');
      if (!btn) {
        syncAdminListMenuItem();
        return;
      }
      const user = currentAuthUser;
      const isAdmin = userIsWebAdmin(user) || isCurrentUserAdminInList();
      const canManage = adminListCanManage;
      const canApply = user
        && !isAdmin
        && !canManage
        && !userIsWebSuperAdmin(user)
        && !isProtectedBuiltinAdmin(user)
        && !isGuestStaffId(user.staffId);
      const canQuit = canCurrentUserSelfQuitAdmin();
      const label = btn.querySelector('.admin-list-head-action-label');
      if (adminListLoading) {
        btn.hidden = true;
      } else if (canQuit) {
        btn.hidden = false;
        btn.disabled = adminListSaving;
        btn.dataset.action = 'quit';
        btn.classList.add('is-quit');
        btn.title = '退出当前管理员身份';
        if (label) label.textContent = '退出管理员';
      } else if (canApply) {
        btn.hidden = false;
        btn.disabled = adminApplyInFlight;
        btn.dataset.action = 'apply';
        btn.classList.remove('is-quit');
        btn.title = '勾选需要的权限后提交，超级管理员在钉钉卡片同意或拒绝';
        if (label) label.textContent = '申请管理员';
      } else {
        btn.hidden = true;
      }
      syncAdminListMenuItem();
    }

    let adminApplyInFlight = false;

    function defaultApplicantPermissionDefs() {
      return [
        { key: 'code_modify', label: '代码修改' },
        { key: 'source_file', label: '源文件导出' },
        { key: 'online', label: '操作线上环境' },
      ];
    }

    function applicantPermissionDefs() {
      const defs = (adminPermissionDefs.length ? adminPermissionDefs : defaultApplicantPermissionDefs())
        .filter((def) => String(def.key || '').trim() && def.key !== 'super_admin');
      return defs.length ? defs : defaultApplicantPermissionDefs();
    }

    function buildAdminApplyPermissionBoxes(containerId, defs, selectedKeys, { inputName }) {
      const box = document.getElementById(containerId);
      if (!box) return;
      const selected = new Set(Array.isArray(selectedKeys) ? selectedKeys : []);
      box.innerHTML = defs.map((def) => {
        const key = String(def.key || '').trim();
        if (!key) return '';
        const checked = selected.has(key) ? ' checked' : '';
        return `<label class="admin-list-perm is-on">
          <input type="checkbox" name="${escapeHtml(inputName)}" value="${escapeHtml(key)}"${checked} />
          <span>${escapeHtml(def.label || key)}</span>
        </label>`;
      }).join('');
    }

    function readAdminApplyPermissionKeys(containerId, inputName) {
      const box = document.getElementById(containerId);
      if (!box) return [];
      return Array.from(box.querySelectorAll(`input[name="${inputName}"]:checked`))
        .map((el) => String(el.value || '').trim())
        .filter(Boolean);
    }

    function setAdminApplyModalOpen(open) {
      const modal = document.getElementById('admin-apply-modal');
      if (!modal) return;
      if (!open) {
        if (modal.classList.contains('open')) {
          void animateOverlayClose(modal).then(() => modal.classList.remove('open'));
        }
        modal.setAttribute('aria-hidden', 'true');
        return;
      }
      const pending = currentAuthUser?.adminApplyStatus;
      const selected = pending?.status === 'pending' ? pending.requestedPermissions : [];
      buildAdminApplyPermissionBoxes(
        'admin-apply-perms',
        applicantPermissionDefs(),
        selected,
        { inputName: 'adminApplyPerm' },
      );
      modal.classList.add('open');
      modal.setAttribute('aria-hidden', 'false');
    }

    function submitAdminApply() {
      const btn = document.getElementById('btn-apply-admin');
      if (!btn || btn.disabled || adminApplyInFlight) return;
      void setAdminListModalOpen(false);
      setAdminApplyModalOpen(true);
    }

    function confirmAdminApplySubmit() {
      const btn = document.getElementById('btn-apply-admin');
      if (adminApplyInFlight) return;
      const requestedPermissions = readAdminApplyPermissionKeys('admin-apply-perms', 'adminApplyPerm');
      adminApplyInFlight = true;
      if (btn) btn.disabled = true;
      setAdminApplyModalOpen(false);
      api('/api/admin/apply', {
        method: 'POST',
        body: JSON.stringify({ requestedPermissions }),
      })
        .then((data) => {
          if (currentAuthUser) {
            currentAuthUser.adminApplyStatus = data.status || { status: 'none' };
          }
          syncAdminApplyMenuItem();
          showWebToast(data.notified === false && data.skippedDuplicate ? '申请已记录（24h 内不重复通知）' : '申请成功');
          if (data.warning) {
            showWebToast(data.warning, { durationMs: 5200 });
          }
        })
        .catch((err) => {
          showWebToast(err.message || '申请失败', { error: true, durationMs: 4200 });
          syncAdminApplyMenuItem();
        })
        .finally(() => {
          adminApplyInFlight = false;
          syncAdminApplyMenuItem();
        });
    }

    function formatUsageNumber(value) {
      return Number(value || 0).toLocaleString('zh-CN');
    }

    function bjYmd(date = new Date()) {
      const parts = new Intl.DateTimeFormat('en-CA', {
        timeZone: 'Asia/Shanghai',
        year: 'numeric',
        month: '2-digit',
        day: '2-digit',
      }).formatToParts(date);
      const get = (type) => parts.find((part) => part.type === type)?.value || '';
      return { y: Number(get('year')), m: Number(get('month')), d: Number(get('day')) };
    }

    function addDaysYmd(ymd, days) {
      const dt = new Date(Date.UTC(ymd.y, ymd.m - 1, ymd.d));
      dt.setUTCDate(dt.getUTCDate() + days);
      return { y: dt.getUTCFullYear(), m: dt.getUTCMonth() + 1, d: dt.getUTCDate() };
    }

    function usageDayKey(ymd) {
      return `${ymd.y}-${String(ymd.m).padStart(2, '0')}-${String(ymd.d).padStart(2, '0')}`;
    }

    function usageDayLabel(ymd) {
      return `${String(ymd.m).padStart(2, '0')}-${String(ymd.d).padStart(2, '0')}`;
    }

    function bjWeekdayMonday0(date = new Date()) {
      const wd = new Intl.DateTimeFormat('en-US', {
        timeZone: 'Asia/Shanghai',
        weekday: 'short',
      }).format(date);
      const order = { Mon: 0, Tue: 1, Wed: 2, Thu: 3, Fri: 4, Sat: 5, Sun: 6 };
      return order[wd] ?? 0;
    }

    function resolveUsageRangeStartYmd(rangeKey, customRange) {
      if (customRange?.start && customRange?.end) {
        const start = parseUsageDayInput(customRange.start);
        const end = parseUsageDayInput(customRange.end);
        if (start && end) return { start, end };
      }
      const key = (rangeKey || 'day').trim().toLowerCase();
      const today = bjYmd();
      let start = { ...today };
      let end = { ...today };
      if (key === 'week') {
        start = addDaysYmd(today, -bjWeekdayMonday0());
      } else if (key === 'month') {
        start = { y: today.y, m: today.m, d: 1 };
      } else if (key === 'yesterday') {
        const yday = addDaysYmd(today, -1);
        start = yday;
        end = yday;
      } else if (key === '7d') {
        const thisMonday = addDaysYmd(today, -bjWeekdayMonday0());
        start = addDaysYmd(thisMonday, -7);
        end = addDaysYmd(thisMonday, -1);
      } else if (key === 'last_month') {
        const firstOfThisMonth = { y: today.y, m: today.m, d: 1 };
        const lastDayPrevMonth = addDaysYmd(firstOfThisMonth, -1);
        start = { y: lastDayPrevMonth.y, m: lastDayPrevMonth.m, d: 1 };
        end = lastDayPrevMonth;
      } else if (key === '30d') {
        start = addDaysYmd(today, -29);
      } else if (key === '180d') {
        start = addDaysYmd(today, -179);
      }
      return { start, end };
    }

    function buildUsagePlaceholderDailyRows(rangeKey, customRange) {
      const { start, end } = resolveUsageRangeStartYmd(rangeKey, customRange);
      const rows = [];
      let cur = { ...start };
      while (true) {
        rows.push({
          date: usageDayKey(cur),
          label: usageDayLabel(cur),
          requests: 0,
          tokens: 0,
        });
        if (cur.y === end.y && cur.m === end.m && cur.d === end.d) break;
        cur = addDaysYmd(cur, 1);
      }
      return rows;
    }

    function setUsageStatsLoadingUI(rangeKey, customRange) {
      setUsagePanelMode('stats');
      syncUsageRangeUI();
      const requestsEl = document.getElementById('usage-requests');
      const tokensEl = document.getElementById('usage-tokens');
      if (requestsEl) requestsEl.textContent = formatUsageNumber(0);
      if (tokensEl) tokensEl.textContent = formatUsageNumber(0);
      renderUsageStatsHint();
      renderUsageDailyChart(buildUsagePlaceholderDailyRows(rangeKey, customRange));
    }

    function pickUsageDailyLabelIndices(n, plotW) {
      const labelW = 32;
      const minGapPx = 4;
      const maxCount = Math.max(2, Math.floor((plotW + minGapPx) / (labelW + minGapPx)));
      if (n <= maxCount) {
        return Array.from({ length: n }, (_, i) => i);
      }

      const rawStep = (n - 1) / (maxCount - 1);
      const niceSteps = [1, 2, 3, 5, 7, 10, 14, 21, 30];
      const step = niceSteps.find((candidate) => candidate >= rawStep) || Math.ceil(rawStep);

      const indices = [];
      for (let i = 0; i < n; i += step) {
        indices.push(i);
      }

      const last = n - 1;
      const tail = indices[indices.length - 1];
      if (tail !== last) {
        const tailGap = last - tail;
        const mergeThreshold = Math.max(2, Math.floor(step / 2));
        if (tailGap < mergeThreshold) {
          indices[indices.length - 1] = last;
        } else if (indices.length < maxCount) {
          indices.push(last);
        } else {
          indices[indices.length - 1] = last;
        }
      }
      return indices;
    }

    function shouldRotateUsageDailyLabels(labelIndices, xAt) {
      if (labelIndices.length < 2) return false;
      for (let i = 1; i < labelIndices.length; i += 1) {
        if (xAt(labelIndices[i]) - xAt(labelIndices[i - 1]) < 30) return true;
      }
      return false;
    }

    function hideUsageChartTooltip() {
      const tip = document.getElementById('usage-chart-tooltip');
      if (!tip) return;
      tip.hidden = true;
      tip.classList.remove('visible');
    }

    function showUsageChartTooltip(clientX, clientY, row) {
      const scrollEl = document.querySelector('.usage-daily-chart-scroll');
      const tip = document.getElementById('usage-chart-tooltip');
      if (!scrollEl || !tip || !row) return;
      const rect = scrollEl.getBoundingClientRect();
      const x = clientX - rect.left;
      const y = clientY - rect.top;
      const dateLabel = escapeHtml(String(row.label || row.date || ''));
      tip.innerHTML = [
        `<div class="tip-date">${dateLabel}</div>`,
        `<div class="tip-row"><span class="tip-dot req"></span>请求 ${formatUsageNumber(row.requests)}</div>`,
        `<div class="tip-row"><span class="tip-dot tok"></span>Token ${formatUsageNumber(row.tokens)}</div>`,
      ].join('');
      tip.hidden = false;
      tip.style.left = `${x}px`;
      tip.style.top = `${y}px`;
      tip.classList.add('visible');
    }

    function bindUsageChartTooltip(chartEl, rows) {
      hideUsageChartTooltip();
      const scrollEl = chartEl?.closest('.usage-daily-chart-scroll');
      if (!chartEl || !scrollEl) return;
      if (chartEl._usageTooltipMove) {
        chartEl.removeEventListener('mousemove', chartEl._usageTooltipMove);
        chartEl.removeEventListener('mouseleave', chartEl._usageTooltipLeave);
      }
      const onMove = (ev) => {
        const hit = ev.target.closest('.usage-chart-hit');
        if (!hit) {
          hideUsageChartTooltip();
          return;
        }
        const index = Number(hit.dataset.index);
        const row = rows[index];
        if (row) showUsageChartTooltip(ev.clientX, ev.clientY, row);
      };
      const onLeave = () => hideUsageChartTooltip();
      chartEl.addEventListener('mousemove', onMove);
      chartEl.addEventListener('mouseleave', onLeave);
      chartEl._usageTooltipMove = onMove;
      chartEl._usageTooltipLeave = onLeave;
    }

    function renderUsageDailyChart(dailyRows) {
      const wrap = document.getElementById('usage-daily-chart-wrap');
      const chartEl = document.getElementById('usage-daily-chart');
      if (!wrap || !chartEl) return;
      const rows = Array.isArray(dailyRows) ? dailyRows.filter((row) => row && row.date) : [];
      if (!rows.length) {
        wrap.hidden = true;
        chartEl.innerHTML = '';
        hideUsageChartTooltip();
        return;
      }
      wrap.hidden = false;

      const n = rows.length;
      const vbW = 360;
      const sidePad = 20;
      const pad = { l: sidePad, r: sidePad, t: 14, b: 22 };
      let vbH = 148;
      const plotW = vbW - pad.l - pad.r;
      let plotH = vbH - pad.t - pad.b;
      const maxReq = Math.max(1, ...rows.map((row) => Number(row.requests || 0)));
      const maxTok = Math.max(1, ...rows.map((row) => Number(row.tokens || 0)));

      const xAt = (index) => pad.l + (n <= 1 ? plotW / 2 : (index / (n - 1)) * plotW);
      const labelIndices = pickUsageDailyLabelIndices(n, plotW);
      const rotateLabels = shouldRotateUsageDailyLabels(labelIndices, xAt);
      if (rotateLabels) {
        pad.b = 34;
        vbH = 158;
        plotH = vbH - pad.t - pad.b;
      }
      const yReq = (value) => pad.t + plotH - (Number(value || 0) / maxReq) * plotH;
      const yTok = (value) => pad.t + plotH - (Number(value || 0) / maxTok) * plotH;

      const buildLinePath = (yFn, key) => rows.map((row, index) => {
        const x = xAt(index).toFixed(1);
        const y = yFn(row[key]).toFixed(1);
        return `${index === 0 ? 'M' : 'L'} ${x} ${y}`;
      }).join(' ');

      const buildAreaPath = (yFn, key) => {
        const top = rows.map((row, index) => `${xAt(index).toFixed(1)},${yFn(row[key]).toFixed(1)}`);
        const baseY = (pad.t + plotH).toFixed(1);
        return `M ${xAt(0).toFixed(1)},${baseY} L ${top.join(' L ')} L ${xAt(n - 1).toFixed(1)},${baseY} Z`;
      };

      const parts = [];
      parts.push(`<svg viewBox="0 0 ${vbW} ${vbH}" preserveAspectRatio="xMidYMid meet" role="img" aria-label="每日用量折线图">`);
      for (let grid = 0; grid <= 2; grid += 1) {
        const gy = pad.t + (plotH * grid) / 2;
        parts.push(`<line class="grid-line" x1="${pad.l}" y1="${gy.toFixed(1)}" x2="${vbW - pad.r}" y2="${gy.toFixed(1)}"/>`);
      }
      parts.push(`<line class="grid-line" x1="${pad.l}" y1="${pad.t + plotH}" x2="${vbW - pad.r}" y2="${pad.t + plotH}"/>`);
      parts.push(`<path class="area-req" d="${buildAreaPath(yReq, 'requests')}"/>`);
      parts.push(`<path class="area-tok" d="${buildAreaPath(yTok, 'tokens')}"/>`);
      parts.push(`<path class="line-req" d="${buildLinePath(yReq, 'requests')}"/>`);
      parts.push(`<path class="line-tok" d="${buildLinePath(yTok, 'tokens')}"/>`);

      rows.forEach((row, index) => {
        const cx = xAt(index).toFixed(1);
        const cyReq = yReq(row.requests).toFixed(1);
        const cyTok = yTok(row.tokens).toFixed(1);
        const midY = ((Number(cyReq) + Number(cyTok)) / 2).toFixed(1);
        parts.push('<g class="usage-chart-point">');
        parts.push(`<circle class="usage-chart-hit" cx="${cx}" cy="${midY}" r="12" data-index="${index}"/>`);
        parts.push(`<circle class="dot-req" cx="${cx}" cy="${cyReq}" r="2.8"/>`);
        parts.push(`<circle class="dot-tok" cx="${cx}" cy="${cyTok}" r="2.8"/>`);
        parts.push('</g>');
      });

      labelIndices.forEach((index) => {
        const row = rows[index];
        const label = escapeHtml(String(row.label || row.date || '').slice(-5));
        const x = xAt(index).toFixed(1);
        const y = (pad.t + plotH + 12).toFixed(1);
        if (rotateLabels) {
          parts.push(`<text class="axis-label" x="${x}" y="${y}" text-anchor="middle" dominant-baseline="hanging" transform="rotate(-35 ${x} ${y})">${label}</text>`);
        } else {
          parts.push(`<text class="axis-label" x="${x}" y="${y}" text-anchor="middle" dominant-baseline="hanging">${label}</text>`);
        }
      });
      parts.push('</svg>');
      chartEl.innerHTML = parts.join('');
      bindUsageChartTooltip(chartEl, rows);
    }

    function formatUsageErrorMessage(message) {
      const text = String(message || '').trim();
      if (!text) return '用量加载失败';
      if (/https?:\/\//i.test(text)) {
        return text.replace(/https?:\/\/\S+/g, '').replace(/\s+/g, ' ').trim()
          || 'Cursor 会话已过期，请重新绑定账号';
      }
      return text;
    }

    function renderUsageStatsHint(dashboardUrl) {
      const hintEl = document.getElementById('usage-stats-hint');
      if (!hintEl) return;
      const url = (dashboardUrl || '').trim() || 'https://cursor.com/dashboard/usage';
      hintEl.innerHTML = `数据来源 <a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">Cursor Dashboard</a>`;
    }

    function buildUsageQuestionRankUrl() {
      if (usageCustomRange?.start && usageCustomRange?.end) {
        return `/api/usage/question-rank?startDate=${encodeURIComponent(usageCustomRange.start)}&endDate=${encodeURIComponent(usageCustomRange.end)}`;
      }
      const rangeKey = (usageRangeKey || 'day').trim() || 'day';
      return `/api/usage/question-rank?range=${encodeURIComponent(rangeKey)}`;
    }

    function setUsageRankOpen(open) {
      usageRankOpen = !!open;
      const mainEl = document.getElementById('usage-stats-main');
      const panelEl = document.getElementById('usage-rank-panel');
      if (mainEl) mainEl.classList.toggle('usage-rank-mode', usageRankOpen);
      if (panelEl) panelEl.hidden = !usageRankOpen;
      if (!usageRankOpen) {
        const listEl = document.getElementById('usage-rank-list');
        if (listEl) listEl.innerHTML = '';
      }
    }

    function renderUsageQuestionRank(data) {
      const listEl = document.getElementById('usage-rank-list');
      const emptyEl = document.getElementById('usage-rank-empty');
      const metaEl = document.getElementById('usage-rank-meta');
      const loadingEl = document.getElementById('usage-rank-loading');
      if (loadingEl) loadingEl.hidden = true;
      if (!listEl || !emptyEl) return;
      const items = Array.isArray(data?.items) ? data.items : [];
      const label = String(data?.rangeLabel || '').trim();
      if (metaEl) metaEl.textContent = label;
      listEl.innerHTML = '';
      if (!items.length) {
        emptyEl.hidden = false;
        return;
      }
      emptyEl.hidden = true;
      const myId = (currentAuthUser?.staffId || '').trim();
      items.forEach((row, index) => {
        const li = document.createElement('li');
        const pos = index + 1;
        const staffId = String(row?.staffId || '').trim();
        const name = String(row?.displayName || staffId || '—').trim();
        const count = Number(row?.requests) || 0;
        li.className = 'usage-rank-row' + (staffId && staffId === myId ? ' is-me' : '');
        const posClass = pos <= 3 ? ` top${pos}` : '';
        li.innerHTML =
          `<span class="usage-rank-pos${posClass}">${pos}</span>`
          + `<span class="usage-rank-name" title="${escapeHtml(name)}">${escapeHtml(name)}</span>`
          + `<span class="usage-rank-count">${formatUsageNumber(count)}</span>`;
        listEl.appendChild(li);
      });
    }

    async function loadUsageQuestionRank() {
      const loadingEl = document.getElementById('usage-rank-loading');
      const emptyEl = document.getElementById('usage-rank-empty');
      if (loadingEl) loadingEl.hidden = false;
      if (emptyEl) emptyEl.hidden = true;
      const listEl = document.getElementById('usage-rank-list');
      if (listEl) listEl.innerHTML = '';
      try {
        const res = await fetch(buildUsageQuestionRankUrl());
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.error || '榜单加载失败');
        renderUsageQuestionRank(data);
      } catch (err) {
        if (loadingEl) loadingEl.hidden = true;
        if (emptyEl) {
          emptyEl.hidden = false;
          emptyEl.textContent = err?.message || '榜单加载失败';
        }
      }
    }

    function openUsageQuestionRank() {
      setUsageRankOpen(true);
      void loadUsageQuestionRank();
    }

    function setUsagePanelMode(mode) {
      const statsPanel = document.getElementById('usage-stats-panel');
      const setupPanel = document.getElementById('usage-setup');
      const showSetup = mode === 'setup';
      if (statsPanel) statsPanel.hidden = showSetup;
      if (setupPanel) setupPanel.hidden = !showSetup;
    }

    async function loadUsageCredentialStatus() {
      const res = await fetch('/api/usage/cursor-session');
      if (!res.ok) return { configured: false };
      return res.json();
    }

    async function saveUsageCredentials() {
      const statusEl = document.getElementById('usage-setup-status');
      const tokenInput = document.getElementById('usage-session-token');
      const emailInput = document.getElementById('usage-cursor-email');
      const sessionToken = (tokenInput?.value || '').trim();
      const cursorEmail = (emailInput?.value || '').trim();
      if (!sessionToken && !cursorEmail) {
        if (statusEl) statusEl.textContent = '请至少填写 Session Token 或 Cursor 邮箱';
        return false;
      }
      if (statusEl) statusEl.textContent = '保存中…';
      try {
        const payload = {};
        if (sessionToken) payload.sessionToken = sessionToken;
        if (cursorEmail) payload.cursorEmail = cursorEmail;
        const res = await fetch('/api/usage/cursor-session', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(payload),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.error || '保存失败');
        if (tokenInput) tokenInput.value = '';
        if (statusEl) statusEl.textContent = '已保存，正在查询…';
        setUsagePanelMode('stats');
        await loadUsageStatsForRange(usageRangeKey, {
          customRange: usageCustomRange,
        });
        void loadUsageStatsForRange('180d', { silent: true });
        return true;
      } catch (err) {
        if (statusEl) statusEl.textContent = err?.message || '保存失败';
        return false;
      }
    }

    async function clearUsageCredentials() {
      const statusEl = document.getElementById('usage-setup-status');
      if (statusEl) statusEl.textContent = '清除中…';
      try {
        const res = await fetch('/api/usage/cursor-session', { method: 'DELETE' });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(data.error || '清除失败');
        const tokenInput = document.getElementById('usage-session-token');
        const emailInput = document.getElementById('usage-cursor-email');
        if (tokenInput) tokenInput.value = '';
        if (emailInput) emailInput.value = '';
        if (statusEl) statusEl.textContent = '已清除绑定';
        setUsagePanelMode('setup');
      } catch (err) {
        if (statusEl) statusEl.textContent = err?.message || '清除失败';
      }
    }

    function applyUsageStatsResponse(data, resOk, fetchError) {
      const requestsEl = document.getElementById('usage-requests');
      const tokensEl = document.getElementById('usage-tokens');
      if (!resOk) {
        if (data?.needsSetup || data?.needsReauth) {
          setUsagePanelMode('setup');
          const setupStatus = document.getElementById('usage-setup-status');
          if (setupStatus) {
            setupStatus.textContent = data.needsReauth
              ? (formatUsageErrorMessage(data.error) || 'Cursor 会话已过期，请重新绑定')
              : (data.setupHint || '请先绑定 Cursor 账号');
          }
          return;
        }
        setUsagePanelMode('stats');
        if (requestsEl) requestsEl.textContent = '—';
        if (tokensEl) tokensEl.textContent = '—';
        renderUsageStatsHint();
        renderUsageDailyChart([]);
        return;
      }
      if (data.needsSetup || data.needsReauth) {
        setUsagePanelMode('setup');
        const setupStatus = document.getElementById('usage-setup-status');
        if (setupStatus) {
          setupStatus.textContent = data.needsReauth
            ? (formatUsageErrorMessage(data.error) || 'Cursor 会话已过期，请重新绑定')
            : (data.setupHint || '请先绑定 Cursor 账号');
        }
        return;
      }
      setUsagePanelMode('stats');
      if (requestsEl) requestsEl.textContent = formatUsageNumber(data.requests);
      if (tokensEl) tokensEl.textContent = formatUsageNumber(data.tokens);
      renderUsageStatsHint(data.dashboardUrl);
      syncUsageRangeUI();
      renderUsageDailyChart(data.daily);
    }

    async function loadUsageStatsForRange(rangeKey, options = {}) {
      const forceRefresh = options.refresh === true;
      const silent = options.silent === true;
      const customRange = options.customRange || null;
      const loadKey = buildUsageLoadKey(rangeKey, customRange);
      const isActive = isActiveUsageLoad(rangeKey, customRange);

      const loadSeq = (usageStatsInflightSeq[loadKey] = (usageStatsInflightSeq[loadKey] || 0) + 1);
      if (isActive) {
        abortUsageLoad();
        usageLoadAbortController = new AbortController();
      }
      const fetchSignal = isActive ? usageLoadAbortController?.signal : undefined;
      if (isActive && !silent) {
        setUsageStatsLoadingUI(rangeKey, customRange);
      }
      try {
        const refreshQs = forceRefresh ? '&refresh=1' : '';
        const fetchOpts = fetchSignal ? { signal: fetchSignal } : undefined;
        let url = `/api/usage/me?range=${encodeURIComponent(rangeKey)}${refreshQs}`;
        if (customRange?.start && customRange?.end) {
          url = `/api/usage/me?startDate=${encodeURIComponent(customRange.start)}&endDate=${encodeURIComponent(customRange.end)}${refreshQs}`;
        }
        const res = await fetch(url, fetchOpts);
        const data = await res.json();
        if (loadSeq !== usageStatsInflightSeq[loadKey]) return;
        if (isActive) {
          applyUsageStatsResponse(data, res.ok, res.ok ? undefined : (data.error || '加载失败'));
        }
        if (res.ok && loadKey === '180d') {
          void loadUsageDateBounds();
        }
      } catch (err) {
        if (err?.name === 'AbortError') return;
        if (loadSeq !== usageStatsInflightSeq[loadKey]) return;
        const message = err?.message || '用量加载失败';
        if (isActive) {
          applyUsageStatsResponse({}, false, message);
        }
      }
    }

    async function loadUsageStats(options = {}) {
      const usageBtn = document.getElementById('btn-settings-usage');
      const loggedIn = !!(currentAuthUser?.staffId || '').trim();
      if (usageBtn) usageBtn.hidden = !loggedIn;
      if (!loggedIn) return;
      await loadUsageStatsForRange(usageRangeKey, {
        ...options,
        customRange: usageCustomRange,
      });
    }

    function initUsageStatsSettings() {
      document.querySelectorAll('.usage-range-option').forEach((btn) => {
        btn.addEventListener('click', () => {
          const nextRange = (btn.dataset.range || 'day').trim() || 'day';
          if (!usageCustomRange && nextRange === usageRangeKey) return;
          usageCustomRange = null;
          usageRangeKey = nextRange;
          syncUsageRangeUI();
          void loadUsageStatsForRange(usageRangeKey);
          if (usageRankOpen) void loadUsageQuestionRank();
        });
      });
      document.getElementById('btn-usage-rank')?.addEventListener('click', () => {
        openUsageQuestionRank();
      });
      document.getElementById('btn-usage-rank-back')?.addEventListener('click', () => {
        setUsageRankOpen(false);
      });
      document.getElementById('usage-start-date')?.addEventListener('click', (ev) => {
        ev.stopPropagation();
        const pop = document.getElementById('usage-date-picker');
        if (!pop?.hidden && usageDatePickerState.anchorEl === ev.currentTarget) {
          closeUsageDatePicker();
          return;
        }
        openUsageDatePicker(ev.currentTarget, 'start', 'usage');
      });
      document.getElementById('usage-end-date')?.addEventListener('click', (ev) => {
        ev.stopPropagation();
        const pop = document.getElementById('usage-date-picker');
        if (!pop?.hidden && usageDatePickerState.anchorEl === ev.currentTarget) {
          closeUsageDatePicker();
          return;
        }
        openUsageDatePicker(ev.currentTarget, 'end', 'usage');
      });
      document.getElementById('usage-date-picker-prev')?.addEventListener('click', (ev) => {
        ev.stopPropagation();
        shiftUsageDatePickerMonth(-1);
      });
      document.getElementById('usage-date-picker-next')?.addEventListener('click', (ev) => {
        ev.stopPropagation();
        shiftUsageDatePickerMonth(1);
      });
      document.getElementById('usage-date-picker-grid')?.addEventListener('click', (ev) => {
        const btn = ev.target.closest('[data-day]');
        if (!btn) return;
        ev.stopPropagation();
        onUsageDatePicked(btn.dataset.day || '');
      });
      document.addEventListener('click', (ev) => {
        const pop = document.getElementById('usage-date-picker');
        if (!pop || pop.hidden) return;
        if (ev.target.closest('#usage-date-picker') || ev.target.closest('.usage-date-trigger')) return;
        closeUsageDatePicker();
      });
      document.addEventListener('keydown', (ev) => {
        if (ev.key !== 'Escape') return;
        closeUsageDatePicker();
      });
      document.getElementById('btn-usage-save')?.addEventListener('click', () => {
        void saveUsageCredentials();
      });
      document.getElementById('btn-usage-clear')?.addEventListener('click', () => {
        void clearUsageCredentials();
      });
    }

    function syncUserMenuAvatar(user, avatarEl) {
      if (!avatarEl || !user) return;
      const displayName = authUserDisplayName(user);
      const staffId = (user.staffId || '').trim();
      let avatarUrl = String(user.avatarUrl || '').trim()
        || (staffId ? (userAvatarCache.get(staffId) || '') : '');
      if (staffId && userAvatarNoPhoto.has(staffId)) avatarUrl = '';
      if (avatarUrl && staffId) userAvatarCache.set(staffId, avatarUrl);
      if (avatarUrl) {
        avatarEl.innerHTML = `<img src="${escapeHtml(avatarUrl)}" alt="" referrerpolicy="no-referrer" data-staff-id="${escapeHtml(staffId)}" data-avatar-label="${escapeHtml(displayName)}" />`;
        avatarEl.classList.add('has-photo');
        avatarEl.dataset.staffId = staffId;
        bindAvatarImage(avatarEl.querySelector('img'), displayName);
        return;
      }
      avatarEl.innerHTML = wrapAvatarGlyph(avatarInitialFromLabel(displayName));
      avatarEl.classList.remove('has-photo');
      delete avatarEl.dataset.staffId;
    }

    function refreshUserMenuAvatar() {
      const avatarEl = document.getElementById('user-menu-avatar');
      if (!avatarEl || !currentAuthUser) return;
      syncUserMenuAvatar(currentAuthUser, avatarEl);
      hydrateAvatars(document.getElementById('user-menu') || avatarEl);
    }

    function initAuthUI(authData) {
      otpAuthEnabled = authData?.otpAuthEnabled !== false;
      currentAuthUser = authData?.loggedIn && authData?.user ? authData.user : null;
      if (window.WebAgentAnalytics) {
        WebAgentAnalytics.setUser(currentAuthUser?.staffId || '');
      }
      const loginBtn = document.getElementById('btn-login');
      const wrap = document.getElementById('user-menu');
      const btn = document.getElementById('user-menu-btn');
      const nameEl = document.getElementById('user-menu-name');
      const avatarEl = document.getElementById('user-menu-avatar');
      const adminBadgeEl = document.getElementById('user-menu-admin-badge');
      setUserMenuOpen(false);
      if (currentAuthUser && wrap && nameEl && avatarEl) {
        const displayName = authUserDisplayName(currentAuthUser);
        nameEl.textContent = displayName;
        syncUserMenuAvatar(currentAuthUser, avatarEl);
        hydrateAvatars(wrap);
        syncUserAdminBadgeFromUser(currentAuthUser);
        wrap.hidden = false;
        if (loginBtn) loginBtn.hidden = true;
      } else {
        if (wrap) wrap.hidden = true;
        if (adminBadgeEl) {
          adminBadgeEl.hidden = true;
          adminBadgeEl.classList.remove('is-super-admin');
        }
        if (btn) {
          btn.classList.remove('is-admin');
          btn.removeAttribute('aria-label');
        }
        if (loginBtn) {
          loginBtn.hidden = document.documentElement.classList.contains('web-agent-mobile')
            ? true
            : !otpAuthEnabled;
        }
        syncUserProfileAvatarClickable();
      }
      purgeMobileLoginHeader();
      syncMobileHeaderToolbar();
      updateReadOnlyState();
      if (bookmarksPanel) bookmarksPanel.setAdmin(!!currentAuthUser?.isAdmin);
      if (messageBoardPanel) messageBoardPanel.setAdmin(!!currentAuthUser?.isAdmin);
      if (catalogPanel) {
        catalogPanel.setCanEditNav(catalogNavCanEdit());
        catalogPanel.setCanDeleteNav(catalogNavCanDelete());
      }
      syncAdminApplyMenuItem();
        syncUserProfileAvatarClickable();
        bindSuperAdminUserProfileClicks();
      loadSessionListScrollByScope();
      applySessionScopeForAuth();
      updateDingtalkOwnerBar();
      refreshSidebarWidthBounds();
      syncLogoutMenuItem();
      if (currentAuthUser) void loadShareableWebUsers();
      const usageBtn = document.getElementById('btn-settings-usage');
      if (usageBtn) usageBtn.hidden = !(currentAuthUser?.staffId || '').trim();
      syncSettingsServiceSection();
    }

    async function logoutCurrentUser() {
      setUserMenuOpen(false);
      try {
        await fetch('/api/auth/logout', { method: 'POST' });
      } catch { /* ignore */ }
      window.location.replace('/');
    }

    document.getElementById('btn-login')?.addEventListener('click', goToLogin);

    function openSelfUserProfileFromMenu() {
      const staffId = String(currentAuthUser?.staffId || '').trim();
      if (!staffId) return;
      void openUserProfileModal(staffId, authUserDisplayName(currentAuthUser));
    }

    document.getElementById('user-menu-btn')?.addEventListener('click', (event) => {
      event.stopPropagation();
      if (!userMenuHasVisibleItems()) {
        if (userMenuOpensProfileOnTap()) {
          event.preventDefault();
          openSelfUserProfileFromMenu();
        }
        return;
      }
      const btn = document.getElementById('user-menu-btn');
      const open = btn?.getAttribute('aria-expanded') === 'true';
      setUserMenuOpen(!open);
    });
    document.getElementById('btn-apply-admin')?.addEventListener('click', () => {
      const btn = document.getElementById('btn-apply-admin');
      if (btn?.dataset.action === 'quit') {
        const staffId = String(currentAuthUser?.staffId || '').trim();
        if (staffId) void quitAdminRoleForUser(staffId, btn);
        return;
      }
      submitAdminApply();
    });
    document.getElementById('btn-admin-apply-cancel')?.addEventListener('click', () => {
      setAdminApplyModalOpen(false);
    });
    document.getElementById('btn-admin-apply-submit')?.addEventListener('click', () => {
      confirmAdminApplySubmit();
    });
    document.getElementById('btn-admin-list')?.addEventListener('click', () => {
      setUserMenuOpen(false);
      setAdminListModalOpen(true);
    });
    document.getElementById('btn-open-api')?.addEventListener('click', () => {
      setUserMenuOpen(false);
      setOpenApiModalOpen(true);
    });
    document.getElementById('btn-open-api-close')?.addEventListener('click', () => {
      setOpenApiModalOpen(false);
    });
    document.getElementById('btn-open-api-generate')?.addEventListener('click', () => {
      void generateOpenApiToken();
    });
    document.getElementById('btn-open-api-copy')?.addEventListener('click', () => {
      void copyOpenApiToken();
    });
    document.getElementById('open-api-modal')?.addEventListener('click', (event) => {
      if (event.target.id === 'open-api-modal') setOpenApiModalOpen(false);
    });
    document.getElementById('btn-admin-list-close')?.addEventListener('click', () => {
      setAdminListModalOpen(false);
    });
    document.getElementById('btn-admin-audit-log')?.addEventListener('click', () => {
      void setAdminAuditModalOpen(true);
    });
    document.getElementById('btn-admin-audit-close')?.addEventListener('click', () => {
      void setAdminAuditModalOpen(false);
    });
    document.getElementById('admin-audit-modal')?.addEventListener('click', (event) => {
      if (event.target.id === 'admin-audit-modal') void setAdminAuditModalOpen(false);
    });
    function initCallLogFilters() {
      document.getElementById('call-log-operator-select')?.addEventListener('change', (ev) => {
        callLogOperatorStaffId = String(ev.target.value || '').trim();
        void loadMoaCallLogEntries();
      });
      document.getElementById('call-log-title-search')?.addEventListener('input', (ev) => {
        const next = String(ev.target.value || '').trim();
        if (callLogTitleSearchTimer) clearTimeout(callLogTitleSearchTimer);
        callLogTitleSearchTimer = setTimeout(() => {
          callLogTitleSearchTimer = null;
          if (next === callLogTitleKeyword) return;
          callLogTitleKeyword = next;
          void loadMoaCallLogEntries();
        }, 280);
      });
      document.getElementById('call-log-start-date')?.addEventListener('click', (ev) => {
        ev.stopPropagation();
        const pop = document.getElementById('usage-date-picker');
        if (!pop?.hidden && usageDatePickerState.anchorEl === ev.currentTarget) {
          closeUsageDatePicker();
          return;
        }
        openUsageDatePicker(ev.currentTarget, 'start', 'callLog');
      });
      document.getElementById('call-log-end-date')?.addEventListener('click', (ev) => {
        ev.stopPropagation();
        const pop = document.getElementById('usage-date-picker');
        if (!pop?.hidden && usageDatePickerState.anchorEl === ev.currentTarget) {
          closeUsageDatePicker();
          return;
        }
        openUsageDatePicker(ev.currentTarget, 'end', 'callLog');
      });
    }
    initCallLogFilters();

    document.getElementById('moa-call-log-body')?.addEventListener('click', (event) => {
      const btn = event.target.closest('.call-log-replay-btn');
      if (btn?.dataset?.entryId) {
        event.preventDefault();
        void openCallLogReplayModal(btn.dataset.entryId);
      }
    });
    document.getElementById('moa-call-log-body')?.addEventListener('scroll', () => {
      maybeLoadMoreMoaCallLogFromScroll();
    }, { passive: true });
    document.getElementById('btn-call-log-replay-cancel')?.addEventListener('click', () => {
      setCallLogReplayModalOpen(false);
    });
    document.getElementById('btn-call-log-replay-run')?.addEventListener('click', () => {
      void runCallLogReplayDirect();
    });
    document.getElementById('call-log-replay-modal')?.addEventListener('click', (event) => {
      if (event.target.id === 'call-log-replay-modal') setCallLogReplayModalOpen(false);
    });
    document.getElementById('btn-moa-call-log-close')?.addEventListener('click', () => {
      void setMoaCallLogModalOpen(false);
    });
    document.getElementById('moa-call-log-modal')?.addEventListener('click', (event) => {
      if (event.target.id === 'moa-call-log-modal') void setMoaCallLogModalOpen(false);
    });
    document.getElementById('admin-list-search')?.addEventListener('input', renderAdminListBody);
    document.getElementById('admin-list-modal')?.addEventListener('click', (event) => {
      if (event.target.id === 'admin-list-modal') setAdminListModalOpen(false);
    });
    document.getElementById('btn-logout')?.addEventListener('click', () => {
      logoutCurrentUser();
    });
    document.addEventListener('click', (event) => {
      const menu = document.getElementById('user-menu');
      const dropdown = document.getElementById('user-menu-dropdown');
      if (menu?.contains(event.target) || dropdown?.contains(event.target)) return;
      setUserMenuOpen(false);
    });
    window.addEventListener('resize', () => {
      const btn = document.getElementById('user-menu-btn');
      if (btn?.getAttribute('aria-expanded') === 'true') positionUserMenuDropdown();
    });

    async function ensureAuthSession() {
      if (typeof MiniappSession !== 'undefined') {
        try {
          await MiniappSession.bootstrapFromUrl();
        } catch (err) {
          console.error('MiniappSession.bootstrapFromUrl', err);
        }
      }
      let authRes;
      try {
        authRes = await fetch('/api/auth/status');
      } catch (err) {
        console.error('auth/status fetch', err);
        return null;
      }
      if (!authRes.ok) return null;
      let authData = await authRes.json();
      if (
        !authData.loggedIn
        && authData.dingtalkOAuth?.enabled
        && typeof DingtalkOAuth !== 'undefined'
        && DingtalkOAuth.isLikelyDingTalkClient()
      ) {
        try {
          const ok = await DingtalkOAuth.tryDingTalkOAuthLogin(authData.dingtalkOAuth);
          if (ok) {
            const retry = await fetch('/api/auth/status');
            if (retry.ok) authData = await retry.json();
          }
        } catch { /* fallback guest / login btn */ }
      }
      return authData;
    }

    function showBootstrapConnectionError(err) {
      const container = document.getElementById('messages');
      if (!container || container.querySelector('.msg')) return;
      clearMessagesBootstrapLoading();
      const msg = escapeHtml(err?.message || '连接失败');
      container.innerHTML = `<div class="empty-state"><p>无法连接 Web Agent 服务：${msg}</p>
           <p style="margin-top:12px;font-size:0.82rem">请运行：python3 platform/web_agent/open_web_agent.py</p></div>`;
    }

    let pageBootstrapShellFinished = false;
    function finishPageBootstrapShell() {
      if (pageBootstrapShellFinished) return;
      pageBootstrapShellFinished = true;
      purgeMobileLogoutControl();
      document.body.classList.remove('is-page-bootstrapping', 'layout-shell-pending');
      clearMessagesBootstrapLoading();
      document.body.classList.add('layout-ready');
      syncToolActionsPlacement();
      if (isWebAgentMobile()) {
        runMobileIdleTask(() => void ensureMarkedLoaded(), 4000);
      }
    }

    function runMobileIdleTask(fn, timeoutMs) {
      if (!isWebAgentMobile()) {
        fn();
        return;
      }
      const run = () => {
        if (mobileInputFocusSuspend) {
          setTimeout(() => runMobileIdleTask(fn, timeoutMs), 96);
          return;
        }
        try {
          fn();
        } catch (err) {
          console.error('mobile idle task', err);
        }
      };
      if (typeof requestIdleCallback === 'function') {
        requestIdleCallback(run, { timeout: timeoutMs || 3000 });
      } else {
        setTimeout(run, 80);
      }
    }

    async function ensureSessionsListLoaded(sessionsLoadPromise) {
      try {
        await sessionsLoadPromise;
        if (!sessionsCache.length && !isGuestMode() && currentAuthUser && !isWebAgentMobile()) {
          for (let retry = 0; retry < 3 && !sessionsCache.length; retry += 1) {
            await new Promise((resolve) => setTimeout(resolve, 700 * (retry + 1)));
            try {
              await loadSessions({ lite: true, force: true });
            } catch (err) {
              console.error('loadSessions retry', err);
            }
          }
        }
      } finally {
        endInitialSessionsListLoad();
        const paintList = () => renderSessionList(mobileSessionListRenderOptions());
        if (isWebAgentMobile()) scheduleMessagesRenderYield(paintList);
        else paintList();
        finishPageBootstrapShell();
      }
    }

    async function runWebAgentBootstrap() {
      let bootstrapError = null;
      let sessionsLoadPromise = null;
      if (!(isWebAgentMobile() && document.body.classList.contains('input-interactive'))) {
        document.body.classList.add('is-page-bootstrapping', 'layout-shell-pending');
      } else if (isWebAgentMobile()) {
        document.body.classList.remove('is-page-bootstrapping', 'layout-shell-pending');
      }
      if (!isGuestMode() && shouldBootstrapRestorePersistedSession() && readLikelyPersistedSessionId()) {
        showMessagesBootstrapLoading();
      }
      try {
        mountBrandLogo();
        ensureSessionContextMenuPortal();
        if (!isWebAgentMobile()) {
          initSidebarResize();
          initCatalogResize();
        }
        setSidebarOpen(sidebarOpen, { skipAnimation: true });
        setCatalogOpen(catalogOpen, { skipAnimation: true });
        requestAnimationFrame(() => document.body.classList.add('layout-ready'));
        if (isWebAgentMobile()) {
          await new Promise((resolve) => setTimeout(resolve, 0));
        }
        const authData = await ensureAuthSession();
        if (authData) initAuthUI(authData);
        if (!isWebAgentMobile()) setupInputAttachmentHandlers();
        setupMessageFileDownloads();
        setupMessageCopyHandler();
        setupMessageShareActions();
        setupMessageTerminalActions();
        bindSuperAdminUserProfileClicks();
        setupMarkdownLinkNewTab();
        setupMessagesScrollTracking();
        setupSessionListScrollTracking();
        setupGlobalContextMenuGuard();
        setupSessionsPanelContextMenu();
        setupCatalogPanelContextMenu();
        if (isWebAgentMobile()) {
          runMobileIdleTask(() => {
            initThemeSettings();
            initPushResultControls();
            initReplyModeControls();
          }, 5500);
        } else {
          initThemeSettings();
          initPushResultControls();
          initReplyModeControls();
        }
        const bootstrapSessionId = shouldBootstrapRestorePersistedSession()
          ? (isGuestMode() ? '' : (mobileBootstrapForcedSessionId() || readPersistedSessionId()))
          : '';
        if (!isGuestMode() && bootstrapSessionId) {
          showMessagesBootstrapLoading();
        }
        const messagesPrefetch = bootstrapSessionId
          ? startSessionMessagesPrefetch(bootstrapSessionId)
          : null;
        if (isWebAgentMobile()) {
          const list = document.getElementById('session-list');
          if (list?.querySelector('.session-filter-empty')?.textContent?.includes('加载中')) {
            list.innerHTML = '';
          }
          sessionsLoadPromise = Promise.resolve();
        } else {
          beginInitialSessionsListLoad();
          sessionsLoadPromise = ensureSessionsListBootstrapPromise();
        }
        await loadMeta().catch((err) => {
          console.error('loadMeta', err);
          if (!meta) {
            meta = {
              title: 'Yaahlan 智能工具 Agent',
              subtitle: '钉钉 Agent · MOA/Admin 查数 · Tunnel 抓包 · Stage 送礼 · 用例生成',
              featureDemos: [],
            };
            document.getElementById('app-title').textContent = meta.title;
            document.title = 'Yaahlan Web Agent';
          }
        });
        if (!isWebAgentMobile()) renderSessionList();
        if (!bootstrapSessionId && !isGuestMode()) showEmptyState();
        if (catalogOpen && !isWebAgentMobile()) {
          void ensureCatalogPanelInit().catch((err) => {
            console.error('early catalog init', err);
          });
        }
        try {
          if (isGuestMode()) {
            currentSessionId = '';
            showEmptyState();
            finishPageBootstrapShell();
            void sessionsLoadPromise
              .finally(() => {
                endInitialSessionsListLoad();
                renderSessionList();
              })
              .catch((err) => {
                console.error('loadSessions guest', err);
              });
          } else if (isWebAgentMobile()) {
            scheduleMobileBackgroundDataWarmup();
            clearMessagesBootstrapLoading();
            if (!messagesDomHasConversation()) {
              showEmptyState({ animate: false });
            }
            finishPageBootstrapShell();
          } else if (bootstrapSessionId) {
            const restored = await tryRestorePersistedSession(bootstrapSessionId, {
              progressive: true,
              messagesPrefetch,
              allowMissingCache: true,
            });
            if (restored) {
              if (!messagesDomHasConversation()) {
                repaintEmptyMessagesFromCache(currentSessionId);
              }
              finishPageBootstrapShell();
              void ensureSessionsListLoaded(sessionsLoadPromise).catch((err) => {
                console.error('ensureSessionsListLoaded', err);
                renderSessionList();
                finishPageBootstrapShell();
              });
            } else {
              await ensureSessionsListLoaded(sessionsLoadPromise);
              await restoreOrCreateInitialSession({
                progressive: true,
                messagesPrefetch,
              });
              finishPageBootstrapShell();
            }
          } else {
            await ensureSessionsListLoaded(sessionsLoadPromise);
            await restoreOrCreateInitialSession({
              progressive: true,
              messagesPrefetch,
            });
            finishPageBootstrapShell();
          }
        } catch (err) {
          console.error('restoreOrCreateInitialSession', err);
          if (initialSessionsListPending) {
            void ensureSessionsListLoaded(sessionsLoadPromise).catch((e) => {
              console.error('ensureSessionsListLoaded after restore error', e);
            });
          }
          showEmptyState();
          finishPageBootstrapShell();
        }
        if (!isWebAgentMobile()) renderSessionList();
        if (!isWebAgentMobile()) void initBookmarksPanel();
        runMobileIdleTask(() => {
          const bootPanels = () => {
            initMessageBoardPanel();
            initAboutPanel();
          };
          if (isWebAgentMobile() && window.__WEB_AGENT_DEFERRED_PANELS_READY__) {
            void window.__WEB_AGENT_DEFERRED_PANELS_READY__.then(bootPanels);
          } else {
            bootPanels();
          }
        }, isWebAgentMobile() ? 3500 : 3000);
        const initMoaRecordWhenReady = () => {
          initMoaRecordPanel();
        };
        if (isWebAgentMobile() && window.__WEB_AGENT_DEFERRED_PANELS_READY__) {
          void window.__WEB_AGENT_DEFERRED_PANELS_READY__.then(initMoaRecordWhenReady);
        } else {
          initMoaRecordWhenReady();
        }
        scheduleScrollMessagesToBottom({ force: true });
        if (isWebAgentMobile()) {
          runMobileIdleTask(startSessionPolling, 5000);
        } else {
          startSessionPolling();
        }
        applyIncomingPrompt();
        if (!isWebAgentMobile()) {
          void (async () => {
            try {
              await ensureCatalogPanelInit();
              setCatalogOpen(catalogOpen, { skipAnimation: true });
            } catch (err) {
              console.error('deferred panel init', err);
            }
          })();
        }
      } catch (err) {
        bootstrapError = err;
        console.error('bootstrap', err);
      } finally {
        if (bootstrapError && initialSessionsListPending) {
          void Promise.resolve(sessionsLoadPromise).finally(() => {
            endInitialSessionsListLoad();
            renderSessionList();
          });
        }
        finishPageBootstrapShell();
        try {
          if (!meta?.title) {
            meta = {
              title: 'Yaahlan 智能工具 Agent',
              subtitle: '钉钉 Agent · MOA/Admin 查数 · Tunnel 抓包 · Stage 送礼 · 用例生成',
              featureDemos: [],
            };
            const titleEl = document.getElementById('app-title');
            if (titleEl) titleEl.textContent = meta.title;
            document.title = 'Yaahlan Web Agent';
          }
          if (!isWebAgentMobile()) renderSessionList();
          if (!currentSessionId) {
            showEmptyState();
          } else if (!messagesDomHasConversation()) {
            if (!repaintEmptyMessagesFromCache(currentSessionId)) {
              void loadMessages({ force: true, loadSeq: activeSessionLoadSeq });
            }
          }
        } catch (err) {
          console.error('bootstrap finally', err);
        }
        if (bootstrapError) showBootstrapConnectionError(bootstrapError);
      }
    }

    async function runMobileAppBootstrap() {
      try {
        runMobileIdleTask(() => {
          if (typeof WebAgentTheme !== 'undefined' && WebAgentTheme.initThemeSettings) {
            WebAgentTheme.initThemeSettings();
          }
        }, 6000);
        await runWebAgentBootstrap();
      } catch (err) {
        console.error('runMobileAppBootstrap', err);
      }
    }

    document.addEventListener('wa-overlays-ready', () => {
      bindMobileDeferredOverlayUi();
    });
    if (isWebAgentMobile()) {
      primeMobileInputInteractive();
      setupInputAttachmentHandlers();
      bindMobileDeferredOverlayUi();
      void runMobileAppBootstrap();
    } else {
      WebAgentTheme.initThemeSettings();
      void runWebAgentBootstrap();
    }
