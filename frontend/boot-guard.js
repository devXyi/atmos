// Pre-render boot guard for static and hosted deployments.
// The main dashboard script currently makes geolocation optional in intent,
// but it can remain pending on mobile. Never let that prevent the first data render.
(function () {
  function startData() {
    if (typeof window.fetchAll !== 'function') return;
    window.fetchAll().catch(error => {
      console.error('Atmos boot data load failed:', error);
    });
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', startData, { once: true });
  } else {
    startData();
  }
})();
