/* Atmos place-name control.
 *
 * Desktop UX:
 *   - Right-click the globe to open a compact liquid-glass control.
 *   - OFF (default): keep only the current/default location label visible.
 *   - ON: reveal the global CARTO place-name label layer.
 *
 * The label imagery is an overlay only; the existing label-free basemap remains
 * untouched so the dashboard never falls back to localized raster labels.
 */
(function () {
  'use strict';

  let viewer = null;
  let placeLayer = null;
  let menu = null;
  let enabled = false;
  let booted = false;

  function getViewer() {
    const v = window.__atmosViewer;
    return v && typeof v.isDestroyed === 'function' && !v.isDestroyed() ? v : null;
  }

  function injectStyles() {
    if (document.getElementById('atmos-place-names-style')) return;
    const style = document.createElement('style');
    style.id = 'atmos-place-names-style';
    style.textContent = `
      #atmos-place-names-menu {
        position: absolute;
        z-index: 1000;
        width: 186px;
        padding: 10px 12px;
        border: 1px solid rgba(255,255,255,.16);
        border-radius: 13px;
        background: linear-gradient(145deg, rgba(18,25,38,.78), rgba(5,8,16,.64));
        box-shadow: 0 14px 42px rgba(0,0,0,.42), inset 0 1px 0 rgba(255,255,255,.10);
        backdrop-filter: blur(22px) saturate(145%);
        -webkit-backdrop-filter: blur(22px) saturate(145%);
        color: #e8ecf4;
        font-family: 'Space Mono', monospace;
        user-select: none;
        pointer-events: auto;
      }
      #atmos-place-names-menu::before {
        content: '';
        position: absolute;
        inset: 1px;
        border-radius: 12px;
        pointer-events: none;
        background: linear-gradient(120deg, rgba(255,255,255,.08), transparent 38%);
      }
      .atmos-place-title {
        position: relative;
        font-size: 8px;
        letter-spacing: .13em;
        text-transform: uppercase;
        color: rgba(232,236,244,.48);
        margin-bottom: 8px;
      }
      .atmos-place-row {
        position: relative;
        display: flex;
        align-items: center;
        justify-content: space-between;
        gap: 12px;
      }
      .atmos-place-label {
        font-size: 10px;
        font-weight: 700;
        letter-spacing: .03em;
      }
      .atmos-place-switch {
        position: relative;
        width: 38px;
        height: 21px;
        flex: 0 0 auto;
        border: 1px solid rgba(255,255,255,.18);
        border-radius: 999px;
        background: rgba(255,255,255,.08);
        cursor: pointer;
        transition: .18s ease;
        outline: none;
      }
      .atmos-place-switch::after {
        content: '';
        position: absolute;
        top: 3px;
        left: 3px;
        width: 13px;
        height: 13px;
        border-radius: 50%;
        background: rgba(232,236,244,.72);
        box-shadow: 0 1px 5px rgba(0,0,0,.35);
        transition: .18s ease;
      }
      .atmos-place-switch.on {
        border-color: rgba(0,212,255,.55);
        background: rgba(0,212,255,.18);
        box-shadow: 0 0 14px rgba(0,212,255,.12);
      }
      .atmos-place-switch.on::after {
        left: 20px;
        background: #00d4ff;
        box-shadow: 0 0 9px rgba(0,212,255,.7);
      }
      .atmos-place-status {
        position: relative;
        margin-top: 7px;
        font-size: 7px;
        letter-spacing: .07em;
        color: rgba(232,236,244,.35);
        text-transform: uppercase;
      }
      @media (max-width: 700px) {
        #atmos-place-names-menu { width: 170px; }
      }
    `;
    document.head.appendChild(style);
  }

  function installLayer(v) {
    if (placeLayer) return placeLayer;
    try {
      placeLayer = v.imageryLayers.addImageryProvider(new Cesium.UrlTemplateImageryProvider({
        url: 'https://{s}.basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}{r}.png',
        subdomains: ['a', 'b', 'c', 'd'],
        maximumLevel: 19,
        credit: '© OpenStreetMap contributors © CARTO'
      }));
      placeLayer.show = false;
      return placeLayer;
    } catch (error) {
      console.warn('Atmos global place-name layer unavailable:', error);
      return null;
    }
  }

  function currentCoords() {
    const s = window.state || {};
    const lat = Number(s.lat);
    const lon = Number(s.lon);
    return Number.isFinite(lat) && Number.isFinite(lon) ? { lat, lon } : null;
  }

  function angularDistance(lat1, lon1, lat2, lon2) {
    const dLat = lat2 - lat1;
    const dLon = ((lon2 - lon1 + 540) % 360) - 180;
    return Math.hypot(dLat, dLon * Math.cos(lat1 * Math.PI / 180));
  }

  function keepDefaultLocationOnly(v) {
    const coords = currentCoords();
    const entities = v.entities.values.filter(e => e.__atmosEnglishCity);
    if (!entities.length) return;

    if (!coords) {
      entities.forEach(e => { e.show = true; });
      return;
    }

    let nearest = null;
    let best = Infinity;
    entities.forEach(entity => {
      try {
        const cart = entity.position?.getValue?.(Cesium.JulianDate.now());
        if (!cart) return;
        const carto = Cesium.Cartographic.fromCartesian(cart);
        const lat = Cesium.Math.toDegrees(carto.latitude);
        const lon = Cesium.Math.toDegrees(carto.longitude);
        const d = angularDistance(coords.lat, coords.lon, lat, lon);
        if (d < best) {
          best = d;
          nearest = entity;
        }
      } catch (_) {}
    });

    entities.forEach(entity => {
      entity.show = entity === nearest;
    });
  }

  function syncLabelVisibility() {
    const v = getViewer();
    if (!v) return;
    if (enabled) {
      v.entities.values
        .filter(e => e.__atmosEnglishCity)
        .forEach(e => { e.show = true; });
    } else {
      keepDefaultLocationOnly(v);
    }
  }

  function updateMenu() {
    if (!menu) return;
    const sw = menu.querySelector('.atmos-place-switch');
    const status = menu.querySelector('.atmos-place-status');
    if (sw) {
      sw.classList.toggle('on', enabled);
      sw.setAttribute('aria-checked', String(enabled));
    }
    if (status) status.textContent = enabled ? 'Global place names: ON' : 'Default location only: OFF';
  }

  function setEnabled(value) {
    enabled = Boolean(value);
    if (placeLayer) placeLayer.show = enabled;
    syncLabelVisibility();
    updateMenu();
    const v = getViewer();
    if (v?.scene?.requestRender) v.scene.requestRender();
  }

  function hideMenu() {
    if (menu) menu.style.display = 'none';
  }

  function showMenu(event) {
    const host = document.getElementById('globe-container');
    if (!host) return;
    if (!menu) {
      menu = document.createElement('div');
      menu.id = 'atmos-place-names-menu';
      menu.innerHTML = `
        <div class="atmos-place-title">Globe controls</div>
        <div class="atmos-place-row">
          <span class="atmos-place-label">All place names</span>
          <button class="atmos-place-switch" type="button" role="switch" aria-label="Show all place names" aria-checked="false"></button>
        </div>
        <div class="atmos-place-status">Default location only: OFF</div>
      `;
      host.appendChild(menu);

      const sw = menu.querySelector('.atmos-place-switch');
      sw.addEventListener('click', (e) => {
        e.stopPropagation();
        setEnabled(!enabled);
      });
      menu.addEventListener('contextmenu', e => e.preventDefault());
    }

    const rect = host.getBoundingClientRect();
    const menuW = 186;
    const menuH = 82;
    const x = Math.max(8, Math.min(event.clientX - rect.left, rect.width - menuW - 8));
    const y = Math.max(8, Math.min(event.clientY - rect.top, rect.height - menuH - 8));
    menu.style.left = `${x}px`;
    menu.style.top = `${y}px`;
    menu.style.display = 'block';
    updateMenu();
  }

  function bind() {
    if (booted) return;
    const host = document.getElementById('globe-container');
    if (!host) return;
    booted = true;

    host.addEventListener('contextmenu', event => {
      event.preventDefault();
      if (!getViewer()) return;
      showMenu(event);
    });

    document.addEventListener('pointerdown', event => {
      if (menu && menu.style.display !== 'none' && !menu.contains(event.target)) hideMenu();
    });
    document.addEventListener('keydown', event => {
      if (event.key === 'Escape') hideMenu();
    });
  }

  function boot() {
    injectStyles();
    bind();
    let tries = 0;
    const timer = setInterval(() => {
      tries += 1;
      viewer = getViewer();
      if (viewer) {
        installLayer(viewer);
        syncLabelVisibility();
        if (tries > 8) clearInterval(timer);
      }
      if (tries > 120) clearInterval(timer);
    }, 250);

    setInterval(() => {
      const v = getViewer();
      if (!v) return;
      if (!enabled) keepDefaultLocationOnly(v);
    }, 1200);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot, { once: true });
  } else {
    boot();
  }
})();
