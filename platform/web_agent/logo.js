/** Yaahlan 智能工具 Agent 品牌 Logo（心跳光标造型，供 chat / login 复用） */
(function (global) {
  let seq = 0;

  function svg(opts) {
    const o = opts || {};
    const glowId = o.glowId || `wa-logo-glow-${++seq}`;
    return (
      `<svg viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg" aria-hidden="true" role="img">` +
      `<defs>` +
      `<filter id="${glowId}" x="-40%" y="-40%" width="180%" height="180%">` +
      `<feGaussianBlur stdDeviation="0.9" result="b"/>` +
      `<feMerge><feMergeNode in="b"/><feMergeNode in="SourceGraphic"/></feMerge>` +
      `</filter>` +
      `</defs>` +
      `<rect width="24" height="24" rx="6" fill="#2a3140"/>` +
      `<circle cx="12" cy="12" r="8.2" stroke="#5B8CFF" stroke-width="1.2" stroke-opacity="0.22"/>` +
      `<circle cx="12" cy="12" r="6.4" stroke="#5B8CFF" stroke-width="1.8" stroke-opacity="0.42"/>` +
      `<circle cx="12" cy="12" r="4.1" fill="#5B8CFF" fill-opacity="0.96" filter="url(#${glowId})"/>` +
      `</svg>`
    );
  }

  global.WebAgentLogo = { svg };
})(typeof window !== "undefined" ? window : globalThis);
