/**
 * Agent 思考等待态：对话区内显示跟随鼠标的心跳光标，移出对话区恢复系统鼠标。
 * 执行结束时在当前位置播放一次 burst，再恢复系统鼠标。
 */
(function () {
  'use strict';

  const BURST_MS = 620;

  let active = false;
  let finishing = false;
  let finishTimer = null;
  let cursorEl = null;
  let chatAreaEl = null;
  let inChatArea = false;
  let pos = { x: -100, y: -100 };
  let visible = false;
  let bound = false;

  function getChatArea() {
    if (!chatAreaEl) chatAreaEl = document.querySelector('.chat-area');
    return chatAreaEl;
  }

  function ensureCursor() {
    if (cursorEl) return cursorEl;
    cursorEl = document.createElement('div');
    cursorEl.className = 'agent-waiting-cursor';
    cursorEl.setAttribute('aria-hidden', 'true');
    cursorEl.innerHTML =
      '<span class="agent-waiting-cursor-ring"></span>' +
      '<span class="agent-waiting-cursor-core"></span>' +
      '<span class="agent-waiting-cursor-burst"></span>' +
      '<span class="agent-waiting-cursor-burst agent-waiting-cursor-burst-2"></span>';
    document.body.appendChild(cursorEl);
    return cursorEl;
  }

  function updateCursorPos() {
    if (!cursorEl) return;
    cursorEl.style.transform = `translate3d(${pos.x}px, ${pos.y}px, 0)`;
  }

  function setInChatArea(inside) {
    const next = !!inside;
    if (next === inChatArea) return;
    inChatArea = next;
    const area = getChatArea();
    if (area) area.classList.toggle('agent-waiting-hover', active && inChatArea);
    if (!inChatArea) {
      visible = false;
      if (cursorEl) cursorEl.classList.remove('is-visible');
    }
  }

  function getInputExclusionRect() {
    const area = getChatArea();
    const inputArea = area?.querySelector('.input-area');
    if (!inputArea) return null;
    const rect = inputArea.getBoundingClientRect();
    return {
      left: rect.left,
      right: rect.right + 56,
      top: rect.top,
      bottom: rect.bottom,
    };
  }

  function isPointInInputExclusionZone(x, y) {
    const rect = getInputExclusionRect();
    if (!rect) return false;
    return x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom;
  }

  function isWaitingHoverTarget(event) {
    const area = getChatArea();
    if (!area || !event) return false;
    if (!area.contains(event.target)) return false;
    if (isPointInInputExclusionZone(event.clientX, event.clientY)) return false;
    return true;
  }

  function syncChatAreaHover(event) {
    setInChatArea(isWaitingHoverTarget(event));
  }

  function onMouseMove(event) {
    syncChatAreaHover(event);
    if (!inChatArea) return;
    pos.x = event.clientX;
    pos.y = event.clientY;
    if (!visible) {
      visible = true;
      cursorEl.classList.add('is-visible');
    }
    updateCursorPos();
  }

  function onMouseLeave() {
    setInChatArea(false);
  }

  function bindEvents() {
    if (bound) return;
    bound = true;
    document.addEventListener('mousemove', onMouseMove, { passive: true });
    document.addEventListener('mouseleave', onMouseLeave);
  }

  function unbindEvents() {
    if (!bound) return;
    bound = false;
    document.removeEventListener('mousemove', onMouseMove);
    document.removeEventListener('mouseleave', onMouseLeave);
    inChatArea = false;
    visible = false;
    const area = getChatArea();
    if (area) area.classList.remove('agent-waiting-hover');
    if (cursorEl && !finishing) {
      cursorEl.classList.remove('is-visible', 'is-burst');
    }
  }

  function clearFinishTimer() {
    if (!finishTimer) return;
    clearTimeout(finishTimer);
    finishTimer = null;
  }

  function finishBurstDone() {
    if (!finishing) return;
    finishing = false;
    clearFinishTimer();
    if (cursorEl) cursorEl.classList.remove('is-visible', 'is-burst');
  }

  function playFinishBurst() {
    active = false;
    const hadVisibleCursor = visible;
    document.body.classList.remove('agent-waiting');
    unbindEvents();

    if (!hadVisibleCursor || !cursorEl) return;

    finishing = true;
    cursorEl.classList.add('is-visible', 'is-burst');
    updateCursorPos();
    clearFinishTimer();
    finishTimer = setTimeout(finishBurstDone, BURST_MS);
  }

  function cancelFinish() {
    if (!finishing) return;
    finishBurstDone();
  }

  function setActive(on) {
    const next = !!on;
    if (next) {
      if (active && !finishing) return;
      cancelFinish();
      active = true;
      document.body.classList.add('agent-waiting');
      ensureCursor();
      if (cursorEl) cursorEl.classList.remove('is-burst');
      bindEvents();
      updateCursorPos();
      return;
    }
    if (!active && !finishing) return;
    playFinishBurst();
  }

  window.WaitingFx = { setActive };
})();
