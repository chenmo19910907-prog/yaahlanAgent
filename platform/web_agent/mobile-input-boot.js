/**
 * 手机首屏输入：在 chat 主脚本解析完成前即可聚焦、输入与自动增高。
 */
(function mobileInputBoot() {
  var root = document.documentElement;
  if (!root.classList.contains('web-agent-mobile')) return;

  var input = document.getElementById('input');
  if (!input) return;

  input.readOnly = false;
  input.disabled = false;
  input.removeAttribute('readonly');
  input.removeAttribute('aria-disabled');
  input.setAttribute('enterkeyhint', 'send');

  document.body.classList.remove('is-page-bootstrapping', 'layout-shell-pending');
  document.body.classList.add('layout-ready', 'input-interactive');

  function keepInputEditable() {
    if (input.readOnly) input.readOnly = false;
    if (input.disabled) input.disabled = false;
    input.classList.remove('readonly-input');
  }
  keepInputEditable();
  var guardUntil = Date.now() + 20000;
  var guardTimer = setInterval(function () {
    keepInputEditable();
    if (Date.now() > guardUntil) clearInterval(guardTimer);
  }, 200);

  var resizeRaf = 0;
  function resizeInput() {
    resizeRaf = 0;
    input.style.height = 'auto';
    input.style.height = Math.min(input.scrollHeight, 160) + 'px';
  }
  function scheduleResize() {
    if (resizeRaf) return;
    resizeRaf = requestAnimationFrame(resizeInput);
  }

  input.addEventListener('input', scheduleResize);
  input.addEventListener('focus', function () {
    document.body.classList.add('input-focused');
    if (window.__WEB_AGENT_SUSPEND_BG__ != null) window.__WEB_AGENT_SUSPEND_BG__(true);
  });
  input.addEventListener('blur', function () {
    document.body.classList.remove('input-focused');
    if (window.__WEB_AGENT_SUSPEND_BG__ != null) window.__WEB_AGENT_SUSPEND_BG__(false);
  });

  window.__WEB_AGENT_MOBILE_INPUT_BOOT__ = {
    installed: true,
    scheduleResize: scheduleResize,
  };
})();