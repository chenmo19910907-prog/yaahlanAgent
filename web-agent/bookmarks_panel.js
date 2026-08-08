/**
 * Web Agent 快捷入口（书签）面板：团队全员共享，数据存 config/bookmarks.json（经 /api/bookmarks 同步）。
 * 任意登录用户可「+ 添加」；名称与备注默认留空、由用户填写；长按图标可编辑/删除。
 */
(function (global) {
  'use strict';

  const LEGACY_STORAGE_KEY = 'web_agent_bookmarks_custom';
  const LONG_PRESS_MS = 500;
  const CATEGORY_EDIT_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" aria-hidden="true"><path d="M12 20h9"/><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4 12.5-12.5z"/></svg>';

  function escapeHtml(s) {
    return String(s)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
  }

  function hostFromUrl(raw) {
    try {
      return new URL(normalizeUrl(raw)).hostname || '';
    } catch (_) {
      return '';
    }
  }

  function isLocalHost(host) {
    if (!host) return true;
    const lower = host.toLowerCase();
    return lower === 'localhost' || lower.startsWith('127.') || lower.endsWith('.local');
  }

  function googleFaviconUrl(raw, size) {
    const host = hostFromUrl(raw);
    if (!host || isLocalHost(host)) return '';
    return `https://www.google.com/s2/favicons?domain=${encodeURIComponent(host)}&sz=${size || 64}`;
  }

  function duckFaviconUrl(raw) {
    const host = hostFromUrl(raw);
    if (!host || isLocalHost(host)) return '';
    return `https://icons.duckduckgo.com/ip3/${encodeURIComponent(host)}.ico`;
  }

  function originFaviconUrl(raw) {
    try {
      return new URL('/favicon.ico', normalizeUrl(raw)).href;
    } catch (_) {
      return '';
    }
  }

  function proxyFaviconUrl(raw) {
    const url = normalizeUrl(raw);
    if (!url) return '';
    return `/api/favicon?url=${encodeURIComponent(url)}`;
  }

  function initialFaviconUrl(raw) {
    return proxyFaviconUrl(raw) || originFaviconUrl(raw) || googleFaviconUrl(raw);
  }

  function letterFallback(label, url) {
    const text = String(label || hostFromUrl(url) || '?').trim();
    if (!text) return '?';
    const ch = [...text][0] || '?';
    return /[a-z]/i.test(ch) ? ch.toUpperCase() : ch;
  }

  function iconSvg(name) {
    const icons = {
      grid: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M4 4h7v7H4zM13 4h7v7h-7zM4 13h7v7H4zM13 13h7v7h-7z"/></svg>',
      link: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></svg>',
      server: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="2" y="3" width="20" height="6" rx="1"/><rect x="2" y="15" width="20" height="6" rx="1"/><path d="M6 6h.01M6 18h.01"/></svg>',
      doc: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6M16 13H8M16 17H8M10 9H8"/></svg>',
      tool: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14.7 6.3a1 1 0 0 0 0 1.4l1.6 1.6a1 1 0 0 0 1.4 0l3.77-3.77a6 6 0 0 1-7.94 7.94l-6.91 6.91a2.12 2.12 0 0 1-3-3l6.91-6.91a6 6 0 0 1 7.94-7.94l-3.76 3.76z"/></svg>',
      agent: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 8V4H8"/><rect x="4" y="8" width="16" height="12" rx="2"/><path d="M2 14h2M20 14h2M12 16v4"/></svg>',
      tunnel: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M22 12h-4l-3 9L9 3l-3 9H2"/></svg>',
      admin: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="8" r="4"/><path d="M4 20c0-4 3.6-7 8-7s8 3 8 7"/></svg>',
      gift: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><rect x="3" y="8" width="18" height="13" rx="1"/><path d="M12 8v13M3 12h18M12 8c-2-2.5-4-3-6-1s0 4 2 5c2-1 4-2.5 4-4zm0 0c2-2.5 4-3 6-1s0 4-2 5c-2-1-4-2.5-4-4z"/></svg>',
      chart: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 3v18h18"/><path d="M7 16l4-4 4 4 5-6"/></svg>',
      code: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M16 18l6-6-6-6M8 6l-6 6 6 6"/></svg>',
      external: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14L21 3"/></svg>',
    };
    return icons[name] || icons.link;
  }

  function loadLegacyCustomStore() {
    try {
      const raw = localStorage.getItem(LEGACY_STORAGE_KEY);
      if (!raw) return { categories: [], items: [] };
      const parsed = JSON.parse(raw);
      if (!parsed || typeof parsed !== 'object') return { categories: [], items: [] };
      const items = (Array.isArray(parsed.items) ? parsed.items : []).filter((item) => item && typeof item === 'object');
      const categories = (Array.isArray(parsed.categories) ? parsed.categories : []).filter((cat) => cat && typeof cat === 'object');
      return {
        categories: categories
          .map((cat) => ({
            id: String(cat.id || '').trim(),
            label: String(cat.label || '').trim(),
          }))
          .filter((cat) => cat.id && cat.label),
        items: items
          .map((item) => ({
            id: String(item.id || '').trim() || `custom-${Date.now()}`,
            label: String(item.label || '').trim(),
            url: String(item.url || '').trim(),
            icon: String(item.icon || 'link').trim() || 'link',
            description: String(item.description || '').trim(),
            categoryId: String(item.categoryId || 'mine').trim() || 'mine',
          }))
          .filter((item) => item.label && item.url),
      };
    } catch (_) {
      return { categories: [], items: [] };
    }
  }

  function clearLegacyCustomStore() {
    try {
      localStorage.removeItem(LEGACY_STORAGE_KEY);
    } catch (_) { /* ignore */ }
  }

  function normalizeUrl(raw) {
    const url = String(raw || '').trim();
    if (!url) return '';
    if (/^https?:\/\//i.test(url)) return url;
    if (url.startsWith('//')) return `https:${url}`;
    return `https://${url}`;
  }

  function categoriesFromData(defaultData) {
    return (defaultData?.categories || []).map((cat) => ({
      id: String(cat.id),
      label: String(cat.label || cat.id),
      items: (cat.items || []).map((item) => ({
        ...item,
        id: String(item.id || item.url),
        label: String(item.label || ''),
        url: String(item.url || ''),
        icon: String(item.icon || 'link'),
        description: String(item.description || ''),
      })).filter((item) => item.label && item.url),
    }));
  }

  function mergeLegacyIntoTeamData(defaultData, legacyStore) {
    if (!legacyStore?.items?.length && !legacyStore?.categories?.length) return false;
    const data = defaultData && typeof defaultData === 'object' ? defaultData : { categories: [] };
    if (!Array.isArray(data.categories)) data.categories = [];
    const categories = data.categories;
    const seenItemIds = new Set();
    categories.forEach((cat) => {
      (cat.items || []).forEach((item) => {
        if (item?.id) seenItemIds.add(String(item.id));
      });
    });
    const ensureCategory = (categoryId, label) => {
      let cat = categories.find((entry) => entry.id === categoryId);
      if (!cat) {
        cat = { id: categoryId, label: label || categoryId, items: [] };
        categories.push(cat);
      }
      if (!Array.isArray(cat.items)) cat.items = [];
      return cat;
    };
    (legacyStore.categories || []).forEach((cat) => {
      if (cat?.id) ensureCategory(String(cat.id), String(cat.label || cat.id));
    });
    let changed = false;
    (legacyStore.items || []).forEach((item) => {
      const itemId = String(item.id);
      if (seenItemIds.has(itemId)) return;
      const categoryId = String(item.categoryId || 'mine');
      const labelById = new Map((legacyStore.categories || []).map((cat) => [String(cat.id), String(cat.label)]));
      const catLabel = categoryId === 'mine'
        ? '我的收藏'
        : (labelById.get(categoryId) || categoryId);
      const cat = ensureCategory(categoryId, catLabel);
      cat.items.push({
        id: itemId,
        label: String(item.label),
        url: String(item.url),
        icon: String(item.icon || 'link'),
        description: String(item.description || ''),
      });
      seenItemIds.add(itemId);
      changed = true;
    });
    return changed;
  }

  function BookmarksPanel(options) {
    this.modalEl = options.modalEl;
    this.bodyEl = options.bodyEl;
    this.addModalEl = options.addModalEl;
    this.addDialogEl = options.addDialogEl || null;
    this.addFormEl = options.addFormEl;
    this.addTitleEl = options.addTitleEl || null;
    this.urlInputEl = options.urlInputEl || null;
    this.labelInputEl = options.labelInputEl || null;
    this.descriptionInputEl = options.descriptionInputEl || null;
    this.editFieldsEl = options.editFieldsEl || null;
    this.categorySelectEl = options.categorySelectEl || null;
    this.categoryNewEl = options.categoryNewEl || null;
    this.categoryEditModalEl = options.categoryEditModalEl || null;
    this.categoryEditDialogEl = options.categoryEditDialogEl || null;
    this.categoryEditFormEl = options.categoryEditFormEl || null;
    this.categoryLabelInputEl = options.categoryLabelInputEl || null;
    this.bubbleEl = options.bubbleEl || null;
    this.fetchBookmarks = options.fetchBookmarks || null;
    this.defaultData = { categories: [] };
    this.open = false;
    this.addOpen = false;
    this.categoryEditOpen = false;
    this.isAdmin = false;
    this.editingItemId = null;
    this.editingCategoryId = null;
    this.contextMenuEl = null;
    this.contextMenuTarget = null;
    this.contextMenuAnchorTile = null;
    this.longPressTimer = null;
    this.longPressTriggered = false;
    this._contextMenuDismiss = null;
    this._legacyMigrated = false;
  }

  BookmarksPanel.prototype.setAdmin = function setAdmin(isAdmin) {
    this.isAdmin = !!isAdmin;
    this.hideContextMenu();
    this.render();
  };

  BookmarksPanel.prototype.setData = function setData(data) {
    this.defaultData = data && typeof data === 'object' ? data : { categories: [] };
    if (!Array.isArray(this.defaultData.categories)) this.defaultData.categories = [];
    this.render();
  };

  BookmarksPanel.prototype.getCategories = function getCategories() {
    return categoriesFromData(this.defaultData);
  };

  BookmarksPanel.prototype.findItem = function findItem(itemId) {
    const categories = this.getCategories();
    for (let i = 0; i < categories.length; i += 1) {
      const cat = categories[i];
      const item = (cat.items || []).find((entry) => entry.id === itemId);
      if (item) return { item, category: cat };
    }
    return null;
  };

  BookmarksPanel.prototype.defaultCategoryId = function defaultCategoryId() {
    const first = (this.defaultData?.categories || [])[0];
    return first?.id ? String(first.id) : 'platform';
  };

  BookmarksPanel.prototype.listCategoryOptions = function listCategoryOptions() {
    return (this.defaultData?.categories || [])
      .map((cat) => ({
        id: String(cat?.id || '').trim(),
        label: String(cat.label || cat.id),
      }))
      .filter((opt) => opt.id);
  };

  BookmarksPanel.prototype.refreshCategorySelect = function refreshCategorySelect() {
    if (!this.categorySelectEl) return;
    const current = this.categorySelectEl.value;
    const options = this.listCategoryOptions();
    const parts = options.map((opt) =>
      `<option value="${escapeHtml(opt.id)}">${escapeHtml(opt.label)}</option>`,
    );
    parts.push('<option value="__new__">+ 新建分类…</option>');
    this.categorySelectEl.innerHTML = parts.join('');
    const values = new Set(options.map((opt) => opt.id));
    const fallback = values.has(current)
      ? current
      : (values.has(this.defaultCategoryId()) ? this.defaultCategoryId() : (options[0]?.id || ''));
    if (fallback) this.categorySelectEl.value = fallback;
    this.syncCategoryNewField();
  };

  BookmarksPanel.prototype.syncCategoryNewField = function syncCategoryNewField() {
    if (!this.categorySelectEl || !this.categoryNewEl) return;
    const isNew = this.categorySelectEl.value === '__new__';
    this.categoryNewEl.hidden = !isNew;
    this.categoryNewEl.required = isNew;
    if (!isNew) this.categoryNewEl.value = '';
  };

  BookmarksPanel.prototype.resolveCategoryFromForm = function resolveCategoryFromForm(formData) {
    const selected = String(formData.get('category') || this.defaultCategoryId()).trim()
      || this.defaultCategoryId();
    if (selected === '__new__') {
      const label = String(formData.get('categoryNew') || '').trim();
      if (!label) return null;
      const id = `team-${Date.now().toString(36)}`;
      return { id, label, isNewCategory: true };
    }
    const known = this.listCategoryOptions().find((opt) => opt.id === selected);
    return {
      id: selected,
      label: known?.label || selected,
      isNewCategory: false,
    };
  };

  BookmarksPanel.prototype.ensureContextMenu = function ensureContextMenu() {
    if (this.contextMenuEl) return this.contextMenuEl;
    const menu = document.createElement('div');
    menu.className = 'bookmark-context-menu';
    menu.hidden = true;
    menu.innerHTML = `
      <button type="button" class="bookmark-context-edit" data-action="edit">编辑</button>
      <button type="button" class="bookmark-context-delete" data-action="delete">删除</button>
    `;
    menu.addEventListener('click', (event) => {
      const btn = event.target.closest('[data-action]');
      if (!btn || !this.contextMenuTarget) return;
      event.preventDefault();
      event.stopPropagation();
      const action = btn.getAttribute('data-action');
      const target = this.contextMenuTarget;
      this.hideContextMenu();
      if (action === 'edit') {
        this.startEdit(target.itemId, target.categoryId);
      } else if (action === 'delete') {
        this.deleteItem(target.itemId, target.categoryId, target.label);
      }
    });
    (this.bubbleEl || this.modalEl || document.body).appendChild(menu);
    this.contextMenuEl = menu;
    return menu;
  };

  BookmarksPanel.prototype._detachContextMenuDismiss = function _detachContextMenuDismiss() {
    if (!this._contextMenuDismiss) return;
    const handler = this._contextMenuDismiss;
    document.removeEventListener('pointerdown', handler, true);
    document.removeEventListener('click', handler, true);
    document.removeEventListener('keydown', handler, true);
    this.modalEl?.removeEventListener('pointerdown', handler, true);
    this.modalEl?.removeEventListener('click', handler, true);
    this.bubbleEl?.removeEventListener('scroll', handler, true);
    this._contextMenuDismiss = null;
  };

  BookmarksPanel.prototype._attachContextMenuDismiss = function _attachContextMenuDismiss() {
    this._detachContextMenuDismiss();
    const menu = this.contextMenuEl;
    const handler = (event) => {
      if (!menu || menu.hidden) return;
      if (event.type === 'keydown') {
        if (event.key === 'Escape') this.hideContextMenu();
        return;
      }
      if (menu.contains(event.target)) return;
      if (this.contextMenuAnchorTile?.contains(event.target)) return;
      this.hideContextMenu();
    };
    this._contextMenuDismiss = handler;
    document.addEventListener('pointerdown', handler, true);
    document.addEventListener('click', handler, true);
    document.addEventListener('keydown', handler, true);
    this.modalEl?.addEventListener('pointerdown', handler, true);
    this.modalEl?.addEventListener('click', handler, true);
    this.bubbleEl?.addEventListener('scroll', handler, true);
  };

  BookmarksPanel.prototype.hideContextMenu = function hideContextMenu() {
    const menu = this.contextMenuEl;
    if (menu && !menu.hidden && window.WebAgentMotion) {
      window.WebAgentMotion.setDropdownAnimated(menu, false);
    } else if (menu) {
      menu.hidden = true;
    }
    this.contextMenuTarget = null;
    this.contextMenuAnchorTile = null;
    this.longPressTriggered = false;
    this.bodyEl?.querySelectorAll('.bookmark-tile-pressed').forEach((el) => {
      el.classList.remove('bookmark-tile-pressed');
    });
    this._detachContextMenuDismiss();
  };

  BookmarksPanel.prototype.showContextMenu = function showContextMenu(tile, clientX, clientY) {
    const menu = this.ensureContextMenu();
    const itemId = tile.getAttribute('data-item-id') || '';
    const categoryId = tile.getAttribute('data-category-id') || '';
    const label = tile.getAttribute('data-label') || '';
    if (!itemId) return;
    this.contextMenuAnchorTile = tile;
    this.contextMenuTarget = { itemId, categoryId, label };
    menu.hidden = false;
    const host = this.bubbleEl || this.modalEl;
    const hostRect = host ? host.getBoundingClientRect() : { left: 0, top: 0, width: window.innerWidth, height: window.innerHeight };
    const menuRect = menu.getBoundingClientRect();
    let left = clientX - hostRect.left;
    let top = clientY - hostRect.top;
    const maxLeft = Math.max(8, hostRect.width - menuRect.width - 8);
    const maxTop = Math.max(8, hostRect.height - menuRect.height - 8);
    left = Math.min(Math.max(8, left), maxLeft);
    top = Math.min(Math.max(8, top), maxTop);
    menu.style.left = `${left}px`;
    menu.style.top = `${top}px`;
    if (window.WebAgentMotion) {
      window.WebAgentMotion.setDropdownAnimated(menu, true);
    }
    this._attachContextMenuDismiss();
  };

  BookmarksPanel.prototype.clearLongPressTimer = function clearLongPressTimer() {
    if (this.longPressTimer) {
      clearTimeout(this.longPressTimer);
      this.longPressTimer = null;
    }
  };

  BookmarksPanel.prototype.bindLongPress = function bindLongPress(tile) {
    const start = (clientX, clientY) => {
      this.clearLongPressTimer();
      this.longPressTriggered = false;
      this.longPressTimer = setTimeout(() => {
        this.longPressTriggered = true;
        tile.classList.add('bookmark-tile-pressed');
        if (navigator.vibrate) navigator.vibrate(10);
        this.showContextMenu(tile, clientX, clientY);
      }, LONG_PRESS_MS);
    };
    const cancel = () => {
      this.clearLongPressTimer();
      tile.classList.remove('bookmark-tile-pressed');
    };
    tile.addEventListener('pointerdown', (event) => {
      if (event.button !== 0) return;
      if (this.contextMenuEl && !this.contextMenuEl.hidden) {
        this.hideContextMenu();
      }
      start(event.clientX, event.clientY);
    });
    tile.addEventListener('pointerup', (event) => {
      if (this.contextMenuEl && !this.contextMenuEl.hidden && this.contextMenuAnchorTile === tile) {
        cancel();
        event.preventDefault();
        return;
      }
      cancel();
    });
    tile.addEventListener('pointerleave', cancel);
    tile.addEventListener('pointercancel', cancel);
    tile.addEventListener('contextmenu', (event) => {
      event.preventDefault();
      this.longPressTriggered = true;
      this.showContextMenu(tile, event.clientX, event.clientY);
    });
  };

  BookmarksPanel.prototype.render = function render() {
    if (!this.bodyEl) return;
    const categories = this.getCategories();
    const parts = [];
    categories.forEach((cat) => {
      const items = cat.items || [];
      if (!items.length) return;
      parts.push(`<section class="bookmarks-section" data-category="${escapeHtml(cat.id)}">
        <div class="bookmarks-section-head">
          <h4 class="bookmarks-section-title">${escapeHtml(cat.label)}</h4>
          <button type="button" class="bookmarks-section-edit" data-category-id="${escapeHtml(cat.id)}"
            data-category-label="${escapeHtml(cat.label)}" title="编辑分类名称" aria-label="编辑分类「${escapeHtml(cat.label)}」">
            ${CATEGORY_EDIT_ICON}
          </button>
        </div>
        <div class="bookmarks-grid">${items.map((item) => this.renderTile(item, cat)).join('')}</div>
      </section>`);
    });
    if (!parts.length) {
      this.bodyEl.innerHTML = '<div class="bookmarks-empty">暂无快捷入口，点击下方添加</div>';
      return;
    }
    this.bodyEl.innerHTML = parts.join('');
    this.applyFaviconFallbacks();
    this.bodyEl.querySelectorAll('.bookmarks-section-edit').forEach((btn) => {
      btn.addEventListener('click', (event) => {
        event.preventDefault();
        event.stopPropagation();
        const categoryId = btn.getAttribute('data-category-id') || '';
        const categoryLabel = btn.getAttribute('data-category-label') || '';
        if (categoryId) this.startEditCategory(categoryId, categoryLabel);
      });
    });
    this.bodyEl.querySelectorAll('.bookmark-tile').forEach((tile) => {
      this.bindLongPress(tile);
      tile.addEventListener('click', (event) => {
        if (this.contextMenuEl && !this.contextMenuEl.hidden && this.contextMenuAnchorTile === tile) {
          event.preventDefault();
          return;
        }
        if (this.longPressTriggered) {
          this.longPressTriggered = false;
          event.preventDefault();
          return;
        }
        const url = tile.getAttribute('data-url');
        if (url) {
          if (global.WebAgentAnalytics) {
            global.WebAgentAnalytics.track('bookmark_click', {
              url,
              label: tile.getAttribute('data-label') || '',
              category_id: tile.getAttribute('data-category-id') || '',
            });
          }
          window.open(url, '_blank', 'noopener,noreferrer');
        }
      });
      tile.addEventListener('keydown', (event) => {
        if (event.key !== 'Enter' && event.key !== ' ') return;
        event.preventDefault();
        const url = tile.getAttribute('data-url');
        if (url) {
          if (global.WebAgentAnalytics) {
            global.WebAgentAnalytics.track('bookmark_click', {
              url,
              label: tile.getAttribute('data-label') || '',
              category_id: tile.getAttribute('data-category-id') || '',
            });
          }
          window.open(url, '_blank', 'noopener,noreferrer');
        }
      });
    });
  };

  BookmarksPanel.prototype.renderTile = function renderTile(item, cat) {
    const url = normalizeUrl(item.url);
    const desc = item.description ? `<span class="bookmark-desc">${escapeHtml(item.description)}</span>` : '';
    const customIcon = String(item.iconUrl || '').trim();
    const favicon = customIcon || initialFaviconUrl(url);
    const iconInner = favicon
      ? `<img class="bookmark-favicon" src="${escapeHtml(favicon)}" alt="" loading="lazy" decoding="async" />`
      : `<span class="bookmark-letter">${escapeHtml(letterFallback(item.label, url))}</span>`;
    const fallbackIcon = escapeHtml(String(item.icon || 'link'));
    return `<div class="bookmark-tile" role="link" tabindex="0"
      data-url="${escapeHtml(url)}"
      data-item-id="${escapeHtml(item.id)}"
      data-category-id="${escapeHtml(cat.id)}"
      data-label="${escapeHtml(item.label)}"
      title="${escapeHtml(item.label)}">
      <span class="bookmark-icon" aria-hidden="true"
        data-page-url="${escapeHtml(url)}"
        data-label="${escapeHtml(item.label)}"
        data-fallback-icon="${fallbackIcon}"
        data-fallback-stage="0">${iconInner}</span>
      <span class="bookmark-label">${escapeHtml(item.label)}</span>
      ${desc}
    </div>`;
  };

  BookmarksPanel.prototype.applyFaviconFallbacks = function applyFaviconFallbacks() {
    if (!this.bodyEl) return;
    this.bodyEl.querySelectorAll('.bookmark-icon').forEach((wrap) => {
      const img = wrap.querySelector('img.bookmark-favicon');
      if (!img) return;
      if (img.dataset.bound === '1') return;
      img.dataset.bound = '1';
      img.addEventListener('error', () => {
        const pageUrl = wrap.getAttribute('data-page-url') || '';
        const label = wrap.getAttribute('data-label') || '';
        const fallbackIcon = wrap.getAttribute('data-fallback-icon') || 'link';
        let stage = Number(wrap.getAttribute('data-fallback-stage') || '0') + 1;
        wrap.setAttribute('data-fallback-stage', String(stage));
        if (stage === 1) {
          const origin = originFaviconUrl(pageUrl);
          if (origin && img.src !== origin) {
            img.src = origin;
            return;
          }
          stage = 2;
          wrap.setAttribute('data-fallback-stage', '2');
        }
        if (stage === 2) {
          const google = googleFaviconUrl(pageUrl);
          if (google && img.src !== google) {
            img.src = google;
            return;
          }
          stage = 3;
          wrap.setAttribute('data-fallback-stage', '3');
        }
        if (stage === 3) {
          const duck = duckFaviconUrl(pageUrl);
          if (duck && img.src !== duck) {
            img.src = duck;
            return;
          }
        }
        const letter = letterFallback(label, pageUrl);
        wrap.innerHTML = letter
          ? `<span class="bookmark-letter">${escapeHtml(letter)}</span>`
          : iconSvg(fallbackIcon);
      });
    });
  };

  BookmarksPanel.prototype.buildTeamPayload = function buildTeamPayload() {
    return {
      categories: (this.defaultData?.categories || []).map((cat) => ({
        id: String(cat.id),
        label: String(cat.label || cat.id),
        items: (cat.items || []).map((item) => {
          const normalized = {
            id: String(item.id),
            label: String(item.label),
            url: String(item.url),
            icon: String(item.icon || 'link'),
          };
          if (item.description) normalized.description = String(item.description);
          if (item.iconUrl) normalized.iconUrl = String(item.iconUrl);
          return normalized;
        }),
      })),
    };
  };

  BookmarksPanel.prototype.saveTeamBookmarks = async function saveTeamBookmarks() {
    const payload = this.buildTeamPayload();
    let res = await fetch('/api/bookmarks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (res.status === 404 || res.status === 405) {
      res = await fetch('/api/bookmarks', {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
      });
    }
    if (!res.ok) {
      let message = '保存失败';
      try {
        const data = await res.json();
        if (data?.error) message = String(data.error);
      } catch (_) { /* ignore */ }
      throw new Error(message);
    }
    const data = await res.json();
    if (data?.bookmarks) this.defaultData = data.bookmarks;
    return data;
  };

  BookmarksPanel.prototype.ensureCategoryInData = function ensureCategoryInData(category) {
    const categories = this.defaultData?.categories || [];
    if (!Array.isArray(this.defaultData.categories)) this.defaultData.categories = categories;
    let cat = categories.find((entry) => entry.id === category.id);
    if (!cat) {
      cat = { id: category.id, label: category.label, items: [] };
      categories.push(cat);
    }
    if (!Array.isArray(cat.items)) cat.items = [];
    return cat;
  };

  BookmarksPanel.prototype.addItem = async function addItem(payload) {
    const label = String(payload.label || '').trim();
    const url = normalizeUrl(payload.url);
    const category = payload.category;
    if (!label || !url || !category?.id) return false;
    const cat = this.ensureCategoryInData(category);
    const item = {
      id: `bookmark-${Date.now().toString(36)}`,
      label,
      url,
      icon: String(payload.icon || 'link').trim() || 'link',
      description: String(payload.description || '').trim(),
    };
    cat.items = [...(cat.items || []), item];
    try {
      await this.saveTeamBookmarks();
      if (global.WebAgentAnalytics) {
        global.WebAgentAnalytics.track('bookmark_save', {
          action: 'add',
          url,
          label,
          category_id: category.id,
        });
      }
      this.refreshCategorySelect();
      this.render();
      return true;
    } catch (err) {
      cat.items = (cat.items || []).filter((entry) => entry.id !== item.id);
      window.alert(err instanceof Error ? err.message : '保存失败');
      return false;
    }
  };

  BookmarksPanel.prototype.updateItem = async function updateItem(itemId, payload) {
    const label = String(payload.label || '').trim();
    const url = normalizeUrl(payload.url);
    const category = payload.category;
    if (!label || !url || !category?.id) return false;
    const categories = this.defaultData?.categories || [];
    let sourceCat = categories.find((cat) => (cat.items || []).some((item) => String(item.id) === itemId));
    if (!sourceCat) return false;
    const item = (sourceCat.items || []).find((entry) => String(entry.id) === itemId);
    if (!item) return false;
    const snapshot = {
      label: item.label,
      url: item.url,
      description: item.description,
      sourceCatId: sourceCat.id,
    };
    item.label = label;
    item.url = url;
    item.description = String(payload.description || '').trim();
    if (sourceCat.id !== category.id) {
      sourceCat.items = (sourceCat.items || []).filter((entry) => String(entry.id) !== itemId);
      const targetCat = this.ensureCategoryInData(category);
      targetCat.items = [...(targetCat.items || []), item];
    }
    try {
      await this.saveTeamBookmarks();
      this.refreshCategorySelect();
      this.render();
      return true;
    } catch (err) {
      item.label = snapshot.label;
      item.url = snapshot.url;
      item.description = snapshot.description;
      if (sourceCat.id !== category.id) {
        const targetCat = categories.find((cat) => cat.id === category.id);
        if (targetCat) {
          targetCat.items = (targetCat.items || []).filter((entry) => String(entry.id) !== itemId);
        }
        sourceCat.items = [...(sourceCat.items || []), item];
      }
      window.alert(err instanceof Error ? err.message : '保存失败');
      return false;
    }
  };

  BookmarksPanel.prototype.updateCategory = async function updateCategory(categoryId, label) {
    const nextLabel = String(label || '').trim();
    if (!categoryId || !nextLabel) return false;
    const categories = this.defaultData?.categories || [];
    const cat = categories.find((entry) => String(entry.id) === categoryId);
    if (!cat) return false;
    const prevLabel = String(cat.label || '');
    if (prevLabel === nextLabel) return true;
    cat.label = nextLabel;
    try {
      await this.saveTeamBookmarks();
      this.refreshCategorySelect();
      this.render();
      return true;
    } catch (err) {
      cat.label = prevLabel;
      window.alert(err instanceof Error ? err.message : '保存失败');
      return false;
    }
  };

  BookmarksPanel.prototype.startEditCategory = function startEditCategory(categoryId, categoryLabel) {
    this.toggleCategoryEditPanel(true, { categoryId, categoryLabel });
  };

  BookmarksPanel.prototype.toggleCategoryEditPanel = function toggleCategoryEditPanel(show, options) {
    if (!this.categoryEditModalEl) return;
    const opts = options || {};
    const visible = show !== undefined ? !!show : !this.categoryEditOpen;
    this.categoryEditOpen = visible;
    this.categoryEditModalEl.hidden = !visible;
    this.categoryEditModalEl.setAttribute('aria-hidden', visible ? 'false' : 'true');
    this.categoryEditModalEl.classList.toggle('open', visible);
    if (visible) {
      this.hideContextMenu();
      this.toggleAddPanel(false);
      this.editingCategoryId = String(opts.categoryId || '').trim() || null;
      const labelInput = this.categoryLabelInputEl
        || this.categoryEditFormEl?.querySelector('[name="label"]');
      if (labelInput) {
        labelInput.value = String(opts.categoryLabel || '').trim();
      }
      window.setTimeout(() => {
        labelInput?.focus();
        labelInput?.select();
      }, 0);
    } else {
      this.editingCategoryId = null;
      this.categoryEditFormEl?.reset();
    }
  };

  BookmarksPanel.prototype.startEdit = function startEdit(itemId, categoryId) {
    const found = this.findItem(itemId);
    if (!found) return;
    this.editingItemId = itemId;
    this.toggleAddPanel(true, { mode: 'edit', item: found.item, categoryId: categoryId || found.category.id });
  };

  BookmarksPanel.prototype.deleteItem = async function deleteItem(itemId, categoryId, label) {
    const name = label || itemId;
    if (!window.confirm(`确定删除「${name}」？`)) return;
    const categories = this.defaultData?.categories || [];
    const cat = categories.find((entry) => entry.id === categoryId);
    if (!cat) return;
    const prevItems = cat.items || [];
    cat.items = prevItems.filter((item) => String(item.id) !== itemId);
    try {
      await this.saveTeamBookmarks();
      this.render();
    } catch (err) {
      cat.items = prevItems;
      window.alert(err instanceof Error ? err.message : '删除失败');
    }
  };

  BookmarksPanel.prototype.refreshFromServer = async function refreshFromServer() {
    if (typeof this.fetchBookmarks !== 'function') return;
    try {
      const data = await this.fetchBookmarks();
      if (data && typeof data === 'object') this.defaultData = data;
      this.render();
    } catch (_) { /* 保留本地缓存，避免阻塞打开面板 */ }
  };

  BookmarksPanel.prototype.importLegacyStore = async function importLegacyStore(legacy, options) {
    const opts = options || {};
    if (!legacy?.items?.length && !legacy?.categories?.length) {
      if (opts.alertEmpty) window.alert('本机未找到可恢复的个人收藏（localStorage 为空）');
      return { imported_count: 0 };
    }
    const res = await fetch('/api/bookmarks/import-legacy', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(legacy),
    });
    if (!res.ok) {
      let message = '恢复失败';
      try {
        const data = await res.json();
        if (data?.error) message = String(data.error);
      } catch (_) { /* ignore */ }
      throw new Error(message);
    }
    const data = await res.json();
    if (data?.bookmarks) this.defaultData = data.bookmarks;
    if ((data?.imported_count || 0) > 0) {
      clearLegacyCustomStore();
    }
    this.refreshCategorySelect();
    this.render();
    return data;
  };

  BookmarksPanel.prototype.recoverLocalBookmarks = async function recoverLocalBookmarks() {
    const legacy = loadLegacyCustomStore();
    try {
      const data = await this.importLegacyStore(legacy, { alertEmpty: true });
      const count = Number(data?.imported_count || 0);
      if (count > 0) {
        window.alert(`已从本机恢复 ${count} 条快捷入口到团队配置`);
      } else if ((legacy.items || []).length || (legacy.categories || []).length) {
        window.alert('本机收藏已在团队配置中，无需重复导入');
      }
      return data;
    } catch (err) {
      window.alert(err instanceof Error ? err.message : '恢复失败');
      return null;
    }
  };

  BookmarksPanel.prototype.migrateFromLocalStorageIfNeeded = async function migrateFromLocalStorageIfNeeded() {
    if (this._legacyMigrated) return;
    const legacy = loadLegacyCustomStore();
    if (!legacy.items.length && !legacy.categories.length) {
      this._legacyMigrated = true;
      return;
    }
    try {
      const data = await this.importLegacyStore(legacy);
      this._legacyMigrated = true;
      if ((data?.imported_count || 0) > 0) {
        window.console.info(`[bookmarks] 已自动恢复 ${data.imported_count} 条本机收藏`);
      }
    } catch (err) {
      window.console.warn('[bookmarks] 迁移本地收藏失败，可点「从本机恢复」重试:', err);
    }
  };

  BookmarksPanel.prototype.setOpen = function setOpen(next) {
    const wasOpen = this.open;
    this.open = !!next;
    if (this.modalEl) this.modalEl.classList.toggle('open', this.open);
    if (this.open) {
      if (!wasOpen) {
        if (global.WebAgentAnalytics) {
          global.WebAgentAnalytics.track('panel_open', { panel: 'bookmarks' });
        }
        this.refreshFromServer();
      }
      this.render();
    } else {
      this.hideContextMenu();
      this.toggleAddPanel(false);
      this.toggleCategoryEditPanel(false);
    }
  };

  BookmarksPanel.prototype.syncEditFieldsVisibility = function syncEditFieldsVisibility() {
    const el = this.editFieldsEl || this.addFormEl?.querySelector('.bookmarks-add-edit-fields');
    if (el) el.hidden = false;
    const labelInput = this.labelInputEl || this.addFormEl?.querySelector('[name="label"]');
    if (labelInput) labelInput.required = true;
  };

  BookmarksPanel.prototype.toggleAddPanel = function toggleAddPanel(show, options) {
    if (!this.addModalEl) return;
    const opts = options || {};
    const visible = show !== undefined ? !!show : !this.addOpen;
    const isEdit = visible && opts.mode === 'edit';
    this.addOpen = visible;
    this.addModalEl.hidden = !visible;
    this.addModalEl.setAttribute('aria-hidden', visible ? 'false' : 'true');
    this.addModalEl.classList.toggle('open', visible);
    if (visible) {
      this.hideContextMenu();
      this.toggleCategoryEditPanel(false);
      this.refreshCategorySelect();
      this.syncEditFieldsVisibility();
      if (this.addTitleEl) {
        this.addTitleEl.textContent = isEdit ? '编辑快捷入口' : '添加快捷入口';
      }
      if (isEdit && opts.item && this.addFormEl) {
        const categoryId = opts.categoryId || this.defaultCategoryId();
        if (this.categorySelectEl) this.categorySelectEl.value = categoryId;
        this.syncCategoryNewField();
        const urlInput = this.urlInputEl || this.addFormEl.querySelector('[name="url"]');
        const labelInput = this.labelInputEl || this.addFormEl.querySelector('[name="label"]');
        const descInput = this.descriptionInputEl || this.addFormEl.querySelector('[name="description"]');
        if (urlInput) urlInput.value = opts.item.url || '';
        if (labelInput) labelInput.value = opts.item.label || '';
        if (descInput) descInput.value = opts.item.description || '';
      } else if (this.addFormEl) {
        this.editingItemId = null;
        this.addFormEl.reset();
        this.syncCategoryNewField();
      }
      window.setTimeout(() => {
        const focusEl = isEdit
          ? (this.labelInputEl || this.addFormEl?.querySelector('[name="label"]'))
          : (this.urlInputEl || this.addFormEl?.querySelector('[name="url"]'));
        focusEl?.focus();
      }, 0);
    } else if (this.addFormEl) {
      this.editingItemId = null;
      this.addFormEl.reset();
      this.syncCategoryNewField();
      this.syncEditFieldsVisibility();
      if (this.addTitleEl) this.addTitleEl.textContent = '添加快捷入口';
    }
  };

  BookmarksPanel.prototype.buildPayloadFromForm = function buildPayloadFromForm(formData) {
    const category = this.resolveCategoryFromForm(formData);
    if (!category) return null;
    const url = normalizeUrl(formData.get('url'));
    if (!url) return null;
    const label = String(formData.get('label') || '').trim();
    const description = String(formData.get('description') || '').trim();
    if (!label) return null;
    return {
      label,
      url,
      description,
      category,
    };
  };

  BookmarksPanel.prototype.bind = function bind() {
    this.addDialogEl?.addEventListener('click', (event) => {
      event.stopPropagation();
    });
    this.addModalEl?.querySelectorAll('button').forEach((btn) => {
      btn.addEventListener('click', () => this.hideContextMenu());
    });
    this.modalEl?.querySelector('.bookmarks-head-actions')?.addEventListener('click', () => {
      this.hideContextMenu();
    });
    this.categorySelectEl?.addEventListener('change', () => this.syncCategoryNewField());
    this.categoryEditDialogEl?.addEventListener('click', (event) => {
      event.stopPropagation();
    });
    this.categoryEditFormEl?.addEventListener('submit', async (event) => {
      event.preventDefault();
      if (!this.editingCategoryId) return;
      const fd = new FormData(this.categoryEditFormEl);
      const label = String(fd.get('label') || '').trim();
      if (!label) {
        (this.categoryLabelInputEl || this.categoryEditFormEl.querySelector('[name="label"]'))?.focus();
        return;
      }
      const ok = await this.updateCategory(this.editingCategoryId, label);
      if (ok) this.toggleCategoryEditPanel(false);
    });
    this.addFormEl?.addEventListener('submit', async (event) => {
      event.preventDefault();
      const fd = new FormData(this.addFormEl);
      const payload = this.buildPayloadFromForm(fd);
      if (!payload) {
        if (this.categorySelectEl?.value === '__new__') this.categoryNewEl?.focus();
        else if (!String(fd.get('label') || '').trim()) {
          (this.labelInputEl || this.addFormEl.querySelector('[name="label"]'))?.focus();
        } else (this.urlInputEl || this.addFormEl.querySelector('[name="url"]'))?.focus();
        return;
      }
      let ok = false;
      if (this.editingItemId) {
        ok = await this.updateItem(this.editingItemId, payload);
      } else {
        ok = await this.addItem(payload);
      }
      if (ok) this.toggleAddPanel(false);
    });
  };

  global.BookmarksPanel = BookmarksPanel;
})(typeof window !== 'undefined' ? window : globalThis);
