/* Preserve the approved overview/chat appearance and manage Stitch navigation shell interactions. */
(() => {
  'use strict';
  const isOriginal = () => /^#space(?:\/(?:overview|ask)(?:[/?]|$)|$)/.test(location.hash);
  function sync() {
    document.documentElement.classList.toggle('workspace-original', isOriginal());
    // Auto-close mobile sidebar on hash change
    const sidebar = document.getElementById('stitchSidebar');
    if (sidebar) sidebar.classList.remove('mobile-open');
  }
  window.XueyaWorkspaceAppearance = {isOriginal};
  window.addEventListener('hashchange', sync);

  document.addEventListener('DOMContentLoaded', () => {
    sync();

    // Stitch sidebar desktop collapse/expand toggle
    const collapseBtn = document.getElementById('stitchSidebarCollapseBtn');
    const sidebar = document.getElementById('stitchSidebar');
    if (collapseBtn && sidebar) {
      collapseBtn.addEventListener('click', () => {
        sidebar.classList.toggle('collapsed');
        const icon = collapseBtn.querySelector('.material-symbols-outlined');
        if (icon) {
          icon.textContent = sidebar.classList.contains('collapsed') ? 'dock_to_left' : 'dock_to_right';
        }
      });
    }

    // Stitch sidebar mobile toggle
    const mobileToggle = document.getElementById('stitchSidebarToggle');
    if (mobileToggle && sidebar) {
      mobileToggle.addEventListener('click', () => {
        sidebar.classList.toggle('mobile-open');
      });
    }

    // Global Cmd+K shortcut to trigger search
    window.addEventListener('keydown', (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault();
        const searchBtn = document.getElementById('searchTrigger');
        if (searchBtn) searchBtn.click();
      }
    });
  });
})();
