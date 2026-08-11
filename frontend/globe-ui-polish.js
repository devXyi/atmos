/* Atmos globe UI polish.
 *
 * Desktop globe control:
 *   - Right-click the globe to open a compact liquid-glass menu.
 *   - OFF by default: show only the current/default location label.
 *   - ON: reveal the global CARTO place-name layer across the whole globe.
 *
 * Presentation-only: does not replace Cesium or alter the dashboard data path.
 */
(function () {
  'use strict';

  const CITIES = [
    { name: 'Lahore', country: 'PK', lat: 31.5497, lon: 74.3436, color: '#ff1744' },
    { name: 'Delhi', country: 'IN', lat: 28.6139, lon: 77.2090, color: '#ff9100' },
    { name: 'Jakarta', country: 'ID', lat: -6.2088, lon: 106.8456, color: '#ffea00' },
    { name: 'Bangkok', country: 'TH', lat: 13.7563, lon: 100.5018, color: '#ffea00' }
  ];

  let allPlacesEnabled = false;
  let placeLayer = null;
  let menu = null;
  let layerInstallAttempted = false;

  function getViewer() {
    const v = window.__atmosViewer;
    return v && typeof v.isDestroyed === 'function' && !v.isDestroyed() ? v : null;
  }

  function getAQI(name) {
    const locations = Array.isArray(window.state?.locations) ? window.state.locations : [];
    const c = CITIES.find(x => x.name === name);
    const match = locations.find(x => Math.abs(Number(x.lat) - c.lat) < 1 && Math.abs(Number(x.lon) - c.lon) < 1);
    return match ? (match.aqi_us ?? match.aqi) : null;
  }

  function currentCoords() {
    const s = window.state || {};
    const lat = Number(s.lat);
    const lon = Number(s.lon);
    return Number.isFinite(lat) && Number.isFinite(lon) ? { lat, lon } : null;
  }

  function distance(aLat, aLon, bLat, bLon) {
    const dLon = ((bLon - aLon + 540) % 360) - 180;
    return Math.hypot(bLat - aLat, dLon * Math.cos(aLat * Math.PI / 180));
  }

  function selectedDefaultCity() {
    const coords = currentCoords();
    if (!coords) return CITIES[0];
    return CITIES.reduce((nearest, city) => {
      return distance(coords.lat, coords.lon, city.lat, city.lon) < distance(coords.lat, coords.lon, nearest.lat, nearest.lon)
        ? city : nearest;
    }, CITIES[0]);
  }

  function render(v) {
    v.entities.values
      .filter(e => e.__atmosEnglishCity || e.__atmosVisibleCityLabel)
      .forEach(e => v.entities.remove(e));

    const visibleCities = allPlacesEnabled ? CITIES : [selectedDefaultCity()];

    visibleCities.forEach(city => {
      const aqi = getAQI(city.name);
      const text = aqi == null ? city.name : `${city.name}  ·  AQI ${aqi}`;
      const entity = v.entities.add({
        position: Cesium.Cartesian3.fromDegrees(city.lon, city.lat, 0),
        point: {
          pixelSize: 8,
          color: Cesium.Color.fromCssColorString(city.color),
          outlineColor: Cesium.Color.WHITE,
          outlineWidth: 2,
          disableDepthTestDistance: Number.POSITIVE_INFINITY
        },
        label: {
          text,
          font: '700 13px Space Mono, monospace',
          fillColor: Cesium.Color.WHITE,
          outlineColor: Cesium.Color.BLACK,
          outlineWidth: 5,
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          horizontalOrigin: Cesium.HorizontalOrigin.LEFT,
          verticalOrigin: Cesium.VerticalOrigin.CENTER,
          pixelOffset: new Cesium.Cartesian2(12, 0),
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
          showBackground: true,
          backgroundColor: Cesium.Color.fromCssColorString('rgba(5,8,16,0.72)'),
          backgroundPadding: new Cesium.Cartesian2(7, 4),
          scale: 1.0,
          scaleByDistance: new Cesium.NearFarScalar(4e6, 1.0, 1.8e7, 0.9),
          translucencyByDistance: new Cesium.NearFarScalar(2.0e7, 1.0, 2.2e7, 0.0)
        }
      });
      entity.__atmosVisibleCityLabel = true;
    });
  }

  // globe-polish.js independently maintains its monitored-city labels. Keep
  // that layer compatible with this toggle: OFF means exactly one default label.
  function enforceDefaultLabelOnly(v) {
    if (allPlacesEnabled) return;
    const defaultCity = selectedDefaultCity();
    let defaultEntities = [];

    v.entities.values
      .filter(e => e.__atmosEnglishCity || e.__atmosVisibleCityLabel)
      .forEach(entity => {
        try {
          const cart = entity.position?.getValue?.(Cesium.JulianDate.now());
          if (!cart) return;
          const geo = Cesium.Cartographic.fromCartesian(cart);
          const lat = Cesium.Math.toDegrees(geo.latitude);
          const lon = Cesium.Math.toDegrees(geo.longitude);
          const d = distance(defaultCity.lat, defaultCity.lon, lat, lon);
          if (d < 0.8) defaultEntities.push(entity);
          else entity.show = false;
        } catch (_) {
          entity.show = false;
        }
      });

    defaultEntities.forEach(entity => { entity.show = true; });
  }

  function installGlobalPlaceLayer(v) {
    if (placeLayer || layerInstallAttempted) return placeLayer;
    layerInstallAttempted = true;
    try {
      placeLayer = v.imageryLayers.addImageryProvider(new Cesium.UrlTemplateImageryProvider({
        url: 'https://{s}.basemaps.cartocdn.com/dark_only_labels/{z}/{x}/{y}{r}.png',
        subdomains: ['a', 'b', 'c', 'd'],
        maximumLevel: 19,
        credit: '© OpenStreetMap contributors © CARTO'
      }));
      placeLayer.show = false;
    } catch (error) {
      layerInstallAttempted = false;
      console.warn('Atmos global place-name layer unavailable:', error);
    }
    return placeLayer;
  }

  function injectMenuStyles() {
    if (document.getElementById('atmos-place-toggle-style')) return;
    const style = document.createElement('style');
    style.id = 'atmos-place-toggle-style';
    style.textContent = `
      #atmos-place-toggle {
        position:absolute; z-index:1000; width:190px; padding:10px 12px;
        border:1px solid rgba(255,255,255,.16); border-radius:13px;
        background:linear-gradient(145deg,rgba(18,25,38,.80),rgba(5,8,16,.66));
        box-shadow:0 14px 42px rgba(0,0,0,.44),inset 0 1px 0 rgba(255,255,255,.10);
        backdrop-filter:blur(22px) saturate(145%); -webkit-backdrop-filter:blur(22px) saturate(145%);
        color:#e8ecf4; font-family:'Space Mono',monospace; user-select:none;
      }
      #atmos-place-toggle .apt-title {font-size:8px;letter-spacing:.13em;text-transform:uppercase;color:rgba(232,236,244,.46);margin-bottom:8px}
      #atmos-place-toggle .apt-row {display:flex;align-items:center;justify-content:space-between;gap:12px}
      #atmos-place-toggle .apt-label {font-size:10px;font-weight:700;letter-spacing:.02em}
      #atmos-place-toggle .apt-switch {position:relative;width:39px;height:21px;padding:0;border:1px solid rgba(255,255,255,.18);border-radius:999px;background:rgba(255,255,255,.08);cursor:pointer;outline:none}
      #atmos-place-toggle .apt-switch:after {content:'';position:absolute;top:3px;left:3px;width:13px;height:13px;border-radius:50%;background:rgba(232,236,244,.72);box-shadow:0 1px 5px rgba(0,0,0,.35);transition:.18s ease}
      #atmos-place-toggle .apt-switch.on {border-color:rgba(0,212,255,.55);background:rgba(0,212,255,.18);box-shadow:0 0 14px rgba(0,212,255,.12)}
      #atmos-place-toggle .apt-switch.on:after {left:21px;background:#00d4ff;box-shadow:0 0 9px rgba(0,212,255,.7)}
      #atmos-place-toggle .apt-status {margin-top:7px;font-size:7px;letter-spacing:.06em;color:rgba(232,236,244,.34);text-transform:uppercase}
    `;
    document.head.appendChild(style);
  }

  function updateMenu() {
    if (!menu) return;
    const button = menu.querySelector('.apt-switch');
    const status = menu.querySelector('.apt-status');
    button.classList.toggle('on', allPlacesEnabled);
    button.setAttribute('aria-checked', String(allPlacesEnabled));
    status.textContent = allPlacesEnabled ? 'Global place names: ON' : 'Default location only: OFF';
  }

  function setAllPlacesEnabled(enabled) {
    allPlacesEnabled = Boolean(enabled);
    const v = getViewer();
    if (v) {
      installGlobalPlaceLayer(v);
      if (placeLayer) placeLayer.show = allPlacesEnabled;
      render(v);
      enforceDefaultLabelOnly(v);
      if (v.scene?.requestRender) v.scene.requestRender();
    }
    updateMenu();
  }

  function hideMenu() {
    if (menu) menu.style.display = 'none';
  }

  function showMenu(event) {
    const host = document.getElementById('globe-container');
    const v = getViewer();
    if (!host || !v) return;

    if (!menu) {
      menu = document.createElement('div');
      menu.id = 'atmos-place-toggle';
      menu.innerHTML = `
        <div class="apt-title">Globe controls</div>
        <div class="apt-row">
          <span class="apt-label">All place names</span>
          <button class="apt-switch" type="button" role="switch" aria-label="Show all place names" aria-checked="false"></button>
        </div>
        <div class="apt-status">Default location only: OFF</div>
      `;
      host.appendChild(menu);
      menu.querySelector('.apt-switch').addEventListener('click', e => {
        e.stopPropagation();
        setAllPlacesEnabled(!allPlacesEnabled);
      });
      menu.addEventListener('contextmenu', e => e.preventDefault());
    }

    const rect = host.getBoundingClientRect();
    const menuW = 190, menuH = 82;
    const x = Math.max(8, Math.min(event.clientX - rect.left, rect.width - menuW - 8));
    const y = Math.max(8, Math.min(event.clientY - rect.top, rect.height - menuH - 8));
    menu.style.left = `${x}px`;
    menu.style.top = `${y}px`;
    menu.style.display = 'block';
    updateMenu();
  }

  function bindContextMenu() {
    const host = document.getElementById('globe-container');
    if (!host || host.__atmosPlaceMenuBound) return;
    host.__atmosPlaceMenuBound = true;

    host.addEventListener('contextmenu', event => {
      event.preventDefault();
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
    injectMenuStyles();
    bindContextMenu();
    let last = '';
    const timer = setInterval(() => {
      const v = getViewer();
      if (!v) return;
      installGlobalPlaceLayer(v);
      const signature = `${CITIES.map(c => `${c.name}:${getAQI(c.name) ?? ''}`).join('|')}|${Number(window.state?.lat) || ''}|${Number(window.state?.lon) || ''}|${allPlacesEnabled}`;
      if (signature !== last) {
        last = signature;
        render(v);
      }
      enforceDefaultLabelOnly(v);
    }, 500);
    setTimeout(() => clearInterval(timer), 60000);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
  else boot();
})();
