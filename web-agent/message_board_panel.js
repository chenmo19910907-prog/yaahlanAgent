/**
 * Web Agent 反馈：所有人可见全部反馈，仅可删除自己的；访客凭当次页面会话标识发帖。
 */
(function (global) {
  'use strict';

  const GUEST_STORAGE_KEY = 'web_agent_message_board_guest';
  let pageGuestId = null;

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function formatTime(iso) {
    if (!iso) return '';
    try {
      const date = new Date(iso);
      if (Number.isNaN(date.getTime())) return iso;
      return date.toLocaleString('zh-CN', {
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
      });
    } catch (_) {
      return iso;
    }
  }

  function createGuestId() {
    if (global.crypto && typeof global.crypto.randomUUID === 'function') {
      return `guest_${global.crypto.randomUUID().replace(/-/g, '')}`;
    }
    const rand = Math.random().toString(16).slice(2).padEnd(32, '0').slice(0, 32);
    return `guest_${rand}`;
  }

  function getOrCreateGuestId() {
    if (pageGuestId && /^guest_[a-f0-9]{32}$/.test(pageGuestId)) return pageGuestId;
    pageGuestId = createGuestId();
    try {
      global.localStorage.removeItem(GUEST_STORAGE_KEY);
    } catch (_) { /* ignore */ }
    return pageGuestId;
  }

  function MessageBoardPanel(options) {
    this.modalEl = options.modalEl;
    this.bubbleEl = options.bubbleEl;
    this.listEl = options.listEl;
    this.formEl = options.formEl;
    this.contentEl = options.contentEl;
    this.realNameEl = options.realNameEl;
    this.realNameRowEl = options.realNameRowEl || this.realNameEl?.closest('.message-board-compose-row');
    this.hintEl = options.hintEl;
    this.submitEl = options.submitEl;
    this.apiFetch = options.apiFetch || ((url, init) => fetch(url, init));
    this.request = options.request || null;
    this.getAuthUser = options.getAuthUser || (() => null);
    this.getGuestId = options.getGuestId || getOrCreateGuestId;
    this.open = false;
    this.loading = false;
    this.isAdmin = false;
    this.isGuest = false;
    this.messages = [];
    this._listClickBound = false;
  }

  MessageBoardPanel.prototype.getViewerContext = function getViewerContext() {
    const user = this.getAuthUser();
    if (user) {
      return { user, guestId: null, isGuest: false };
    }
    return { user: null, guestId: this.getGuestId(), isGuest: true };
  };

  MessageBoardPanel.prototype.setAdmin = function setAdmin(isAdmin) {
    this.isAdmin = !!isAdmin;
    this.renderHint();
  };

  MessageBoardPanel.prototype.renderHint = function renderHint() {
    if (!this.hintEl) return;
    this.hintEl.textContent = '遇到问题、优化建议、功能补充 都可以进行反馈';
  };

  MessageBoardPanel.prototype.updateComposeVisibility = function updateComposeVisibility() {
    if (this.formEl) this.formEl.hidden = false;
    const showRealName = !this.isGuest;
    if (this.realNameEl) {
      this.realNameEl.disabled = !showRealName;
      if (!showRealName) this.realNameEl.checked = false;
    }
    const realNameLabel = this.realNameEl?.closest('.message-board-realname');
    if (realNameLabel) realNameLabel.hidden = !showRealName;
  };

  MessageBoardPanel.prototype.setOpen = function setOpen(open, opts) {
    const next = !!open;
    if (next === this.open && !(opts && opts.force)) return;
    this.open = next;
    if (!this.modalEl) return;
    this.modalEl.classList.toggle('open', next);
    this.modalEl.setAttribute('aria-hidden', next ? 'false' : 'true');
    if (next) {
      this.loadMessages();
      window.setTimeout(() => this.contentEl?.focus(), 0);
    }
  };

  MessageBoardPanel.prototype.renderList = function renderList() {
    if (!this.listEl) return;
    if (!this.messages.length) {
      this.listEl.innerHTML = '<div class="message-board-empty">暂无反馈，在下方输入第一条吧。</div>';
      return;
    }
    this.listEl.innerHTML = this.messages.map((item) => {
      const badge = item.isGuestAuthor
        ? '<span class="message-board-badge anon">访客</span>'
        : item.showRealName
          ? '<span class="message-board-badge real">实名</span>'
          : '<span class="message-board-badge anon">匿名</span>';
      const adminMeta = this.isAdmin && item.staffId && !item.isMine
        ? `<span class="message-board-staff">${escapeHtml(item.staffId)}</span>`
        : '';
      const canDelete = !!item.canDelete;
      const deleteBtn = canDelete
        ? `<button type="button" class="message-board-delete" data-id="${escapeHtml(item.id)}" title="删除反馈" aria-label="删除反馈">删除</button>`
        : '';
      return `
        <article class="message-board-item${item.isMine ? ' is-mine' : ''}">
          <div class="message-board-item-head">
            <div class="message-board-item-leading">
              <span class="message-board-author">${escapeHtml(item.authorLabel || '用户')}</span>
              ${badge}
              ${adminMeta}
            </div>
            <div class="message-board-item-actions">
              ${deleteBtn}
              <time class="message-board-time">${escapeHtml(formatTime(item.createdAt))}</time>
            </div>
          </div>
          <div class="message-board-content">${escapeHtml(item.content || '').replace(/\n/g, '<br>')}</div>
        </article>`;
    }).join('');
  };

  MessageBoardPanel.prototype._boardHeaders = function _boardHeaders(extra) {
    const headers = Object.assign({}, extra || {});
    const ctx = this.getViewerContext();
    if (ctx.isGuest && ctx.guestId) {
      headers['X-Message-Board-Guest'] = ctx.guestId;
    }
    return headers;
  };

  MessageBoardPanel.prototype._fetchBoard = async function _fetchBoard(method, body, path) {
    const url = path || '/api/message-board';
    const headers = this._boardHeaders(
      body !== undefined ? { 'Content-Type': 'application/json' } : {},
    );
    if (this.request) {
      const opts = { method: method || 'GET', headers };
      if (body !== undefined) {
        const payload = Object.assign({}, body);
        const ctx = this.getViewerContext();
        if (ctx.isGuest && ctx.guestId) payload.guestId = ctx.guestId;
        opts.body = JSON.stringify(payload);
      }
      return this.request(url, opts);
    }
    const init = { method: method || 'GET', headers };
    if (body !== undefined) {
      const payload = Object.assign({}, body);
      const ctx = this.getViewerContext();
      if (ctx.isGuest && ctx.guestId) payload.guestId = ctx.guestId;
      init.body = JSON.stringify(payload);
    }
    const res = await this.apiFetch(url, init);
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || '请求失败');
    return data;
  };

  MessageBoardPanel.prototype.loadMessages = async function loadMessages() {
    const ctx = this.getViewerContext();
    this.isGuest = ctx.isGuest;
    this.updateComposeVisibility();
    this.renderHint();
    if (this.listEl) {
      this.listEl.innerHTML = '<div class="message-board-empty">加载中…</div>';
    }
    try {
      const data = await this._fetchBoard('GET');
      this.messages = Array.isArray(data.messages) ? data.messages : [];
      this.isAdmin = !!data.isAdmin;
      this.renderHint();
      this.renderList();
    } catch (err) {
      if (this.listEl) {
        this.listEl.innerHTML = `<div class="message-board-empty">${escapeHtml(err.message || '加载失败')}</div>`;
      }
    }
  };

  MessageBoardPanel.prototype.deleteMessage = async function deleteMessage(messageId) {
    if (this.loading || !messageId) return;
    if (!global.confirm('确定删除这条反馈吗？')) return;
    this.loading = true;
    try {
      await this._fetchBoard('DELETE', undefined, `/api/message-board/${encodeURIComponent(messageId)}`);
      await this.loadMessages();
    } catch (err) {
      alert(err.message || '删除失败');
    } finally {
      this.loading = false;
    }
  };

  MessageBoardPanel.prototype.submitMessage = async function submitMessage(event) {
    event.preventDefault();
    if (this.loading) return;
    const content = String(this.contentEl?.value || '').trim();
    if (!content) return;
    this.loading = true;
    if (this.submitEl) this.submitEl.disabled = true;
    try {
      const ctx = this.getViewerContext();
      await this._fetchBoard('POST', {
        content,
        showRealName: ctx.isGuest ? false : !!this.realNameEl?.checked,
      });
      if (this.contentEl) this.contentEl.value = '';
      if (this.realNameEl) this.realNameEl.checked = false;
      await this.loadMessages();
    } catch (err) {
      alert(err.message || '提交失败');
    } finally {
      this.loading = false;
      if (this.submitEl) this.submitEl.disabled = false;
    }
  };

  MessageBoardPanel.prototype.bind = function bind() {
    this.formEl?.addEventListener('submit', (event) => this.submitMessage(event));
    this.bubbleEl?.addEventListener('click', (event) => event.stopPropagation());
    if (this.listEl && !this._listClickBound) {
      this._listClickBound = true;
      this.listEl.addEventListener('click', (event) => {
        const btn = event.target.closest('.message-board-delete');
        if (!btn) return;
        event.preventDefault();
        const id = btn.getAttribute('data-id');
        this.deleteMessage(id);
      });
    }
  };

  global.MessageBoardPanel = MessageBoardPanel;
  global.MessageBoardGuest = { getOrCreateGuestId, GUEST_STORAGE_KEY };
})(window);
