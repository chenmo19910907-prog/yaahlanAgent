/**
 * Web Agent「关于」弹窗：产品介绍 + 内网文档链接列表。
 */
(function (global) {
  'use strict';

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function AboutPanel(options) {
    this.modalEl = options.modalEl;
    this.bubbleEl = options.bubbleEl;
    this.titleEl = options.titleEl;
    this.introEl = options.introEl;
    this.listEl = options.listEl;
    this.closeEl = options.closeEl;
    this.apiFetch = options.apiFetch || ((url) => fetch(url));
    /** 与 chat.html 的 api() 一致：直接返回已解析 JSON（优先于 apiFetch） */
    this.request = options.request || null;
    this.animateClose = options.animateClose || null;
    this.open = false;
    this.loading = false;
    this.data = null;
  }

  AboutPanel.prototype.render = function render() {
    if (!this.listEl) return;
    const data = this.data;
    if (!data) {
      this.listEl.innerHTML = '<div class="about-docs-empty">加载中…</div>';
      return;
    }
    if (this.titleEl) this.titleEl.textContent = data.title || '关于 Yaahlan Web Agent';
    if (this.introEl) this.introEl.textContent = data.intro || '';
    const categories = Array.isArray(data.categories) ? data.categories : [];
    if (!categories.length) {
      this.listEl.innerHTML = '<div class="about-docs-empty">暂无文档链接</div>';
      return;
    }
    this.listEl.innerHTML = categories.map((cat) => {
      const items = Array.isArray(cat.items) ? cat.items : [];
      if (!items.length) return '';
      const links = items.map((item) => {
        const url = String(item.url || '').trim();
        const title = escapeHtml(item.title || '未命名文档');
        const desc = item.desc ? `<span class="about-doc-desc">${escapeHtml(item.desc)}</span>` : '';
        return `
          <a class="about-doc-link" href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer" data-analytics-doc="${title}" data-analytics-url="${escapeHtml(url)}">
            <span class="about-doc-link-main">
              <span class="about-doc-title">${title}</span>
              ${desc}
            </span>
            <svg class="about-doc-icon" viewBox="0 0 24 24" fill="none" stroke-width="2" aria-hidden="true">
              <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"/>
              <path d="M15 3h6v6"/>
              <path d="M10 14 21 3"/>
            </svg>
          </a>`;
      }).join('');
      return `
        <section class="about-docs-section">
          <h4 class="about-docs-label">${escapeHtml(cat.name || '文档')}</h4>
          <div class="about-docs-links">${links}</div>
        </section>`;
    }).join('');
  };

  AboutPanel.prototype.loadData = async function loadData() {
    if (this.data) return this.data;
    if (this.loading) return this.data;
    this.loading = true;
    this.render();
    try {
      let payload;
      if (this.request) {
        payload = await this.request('/api/web-docs');
      } else {
        const resp = await this.apiFetch('/api/web-docs');
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        payload = await resp.json();
      }
      this.data = payload;
      this.render();
      return payload;
    } catch (err) {
      if (this.listEl) {
        this.listEl.innerHTML = `<div class="about-docs-empty">${escapeHtml(err.message || '加载失败')}</div>`;
      }
      throw err;
    } finally {
      this.loading = false;
    }
  };

  AboutPanel.prototype.setOpen = async function setOpen(open, opts) {
    const next = !!open;
    if (next === this.open && !(opts && opts.force)) return;
    if (!next && this.animateClose && this.modalEl?.classList.contains('open')) {
      await this.animateClose(this.modalEl);
    }
    this.open = next;
    if (!this.modalEl) return;
    this.modalEl.classList.toggle('open', next);
    this.modalEl.setAttribute('aria-hidden', next ? 'false' : 'true');
    if (next) {
      if (global.WebAgentAnalytics) {
        global.WebAgentAnalytics.track('panel_open', { panel: 'about' });
      }
      try {
        await this.loadData();
      } catch (_) { /* render 已展示错误 */ }
    }
  };

  AboutPanel.prototype.bind = function bind() {
    this.closeEl?.addEventListener('click', () => this.setOpen(false));
    this.modalEl?.addEventListener('click', (event) => {
      if (event.target === this.modalEl) this.setOpen(false);
    });
    this.listEl?.addEventListener('click', (event) => {
      event.stopPropagation();
      const link = event.target.closest('.about-doc-link');
      if (!link || !global.WebAgentAnalytics) return;
      global.WebAgentAnalytics.track('about_doc_click', {
        title: link.getAttribute('data-analytics-doc') || link.textContent || '',
        url: link.getAttribute('data-analytics-url') || link.getAttribute('href') || '',
      });
    });
    this.bubbleEl?.addEventListener('click', (event) => event.stopPropagation());
  };

  global.WebAgentAboutPanel = AboutPanel;
}(typeof window !== 'undefined' ? window : globalThis));
