/* Preserve the approved overview/chat appearance across in-page navigation. */
(() => {
  'use strict';
  const isOriginal = () => /^#space(?:\/(?:overview|ask)(?:[/?]|$)|$)/.test(location.hash);
  function sync() { document.documentElement.classList.toggle('workspace-original', isOriginal()); }
  window.XueyaWorkspaceAppearance = {isOriginal};
  window.addEventListener('hashchange', sync);
  sync();
})();
