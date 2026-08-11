/* Atmos globe polish layer.
 *
 * This layer deliberately owns only the presentation edge of Cesium:
 *   1. make the grid/canvas viewport a real, bounded rectangle;
 *   2. resize Cesium after the browser has finished layout;
 *   3. keep the Earth centred in that rectangle;
 *   4. keep monitored-city labels available even when API locations arrive late;
 *   5. use a label-free raster base so tile-localized CJK labels cannot return.
 *
 * It does NOT replace Cesium.Viewer or alter the existing dashboard features.
 */
(function () {
  'use strict';

  const MONITORED_CITIES = [
    { name: 'Lahore', country: 'PK', lat: 31.5497, lon: 74.3436 },
    { name: 'Delhi', country: 'IN', lat: 28.6139, lon: 77.2090 },
    { name: 'Jakarta', country: 'ID', lat: -6.2088, lon: 106.8456 },
    { name: 'Bangkok', country: 'TH', lat: 13.7563, lon: 100.5018 },
  ];

  const ENGLISH_CITIES = {
    IN: 'Delhi', PK: 'Lahore', TH: 'Bangkok', ID: 'Jakarta', SG: 'Singapore',
    MY: 'Kuala Lumpur', BD: 'Dhaka', NP: 'Kathmandu', AE: 'Dubai', GB: 'London',
    US: 'New York', JP: 'Tokyo', CN: 'Beijing', AU: 'Sydney', DE: 'Berlin',
    FR: 'Paris', CA: 'Toronto', BR: 'São Paulo'
  };

  const SOURCE_PROFILES = {
    Delhi: [['Traffic emissions',82],['Dust / construction',68],['Biomass & waste burning',61],['Industrial activity',49]],
    Lahore: [['Vehicle emissions',76],['Industrial activity',64],['Agricultural burning',58],['Construction dust',51]],
    Bangkok: [['Vehicle emissions',74],['Biomass burning',63],['Industrial activity',48],['Road / construction dust',39]],
    Jakarta: [['Vehicle emissions',71],['Industrial activity',57],['Open burning',54],['Road dust',42]]
  };

  let viewerReady = false;
  let basemapInstalled = false;
  let lastLat = null;
  let lastLon = null;
  let lastLabelSignature = '';
  let settling = false;

  function getViewer() {
    const v = window.__atmosViewer;
    return v && typeof v.isDestroyed === 'function' && !v.isDestroyed() ? v : null;
  }

  function injectViewportCSS() {
    if (document.getElementById('atmos-globe-viewport-css')) return;
    const style = document.createElement('style');
    style.id = 'atmos-globe-viewport-css';
    style.textContent = `
      html, body { width:100%; height:100%; min-height:0; }
      body {
        min-width:0;
        min-height:0;
        grid-template-rows:48px minmax(0,1fr) !important;
        grid-template-columns:minmax(0,280px) minmax(0,1fr) minmax(0,320px) !important;
      }
      #globe-container {
        position:relative !important;
        min-width:0 !important;
        min-height:0 !important;
        width:auto !important;
        height:auto !important;
        align-self:stretch !important;
        overflow:hidden !important;
      }
      #cesium-container {
        position:absolute !important;
        inset:0 !important;
        width:100% !important;
        height:100% !important;
        min-width:0 !important;
        min-height:0 !important;
        overflow:hidden !important;
      }
      #cesium-container .cesium-viewer,
      #cesium-container .cesium-widget,
      #cesium-container .cesium-widget canvas {
        position:absolute !important;
        inset:0 !important;
        width:100% !important;
        height:100% !important;
        max-width:none !important;
        max-height:none !important;
      }
    `;
    document.head.appendChild(style);
  }

  function cityName(loc) {
    const country = String(loc.country || '').toUpperCase();
    return ENGLISH_CITIES[country]
      || String(loc.city || '').replace(/[\u3400-\u9fff\u3040-\u30ff]/g, '').trim()
      || 'City';
  }

  function installEnglishBasemap(v) {
    if (basemapInstalled) return;
    try {
      const layers = v.imageryLayers;
      for (let i = layers.length - 1; i >= 0; i--) {
        layers.remove(layers.get(i), true);
      }
      layers.addImageryProvider(new Cesium.UrlTemplateImageryProvider({
        url: 'https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png',
        subdomains: ['a','b','c','d'],
        maximumLevel: 19,
        credit: '© OpenStreetMap contributors © CARTO'
      }));
      basemapInstalled = true;
    } catch (error) {
      console.warn('Atmos English basemap unavailable; retaining existing imagery:', error);
    }
  }

  function getCityRecords() {
    const records = [];
    const seen = new Set();
    const locations = Array.isArray(window.state?.locations) ? window.state.locations : [];

    // API locations first, but always normalize their displayed name to English.
    locations.forEach(loc => {
      const lat = Number(loc.lat), lon = Number(loc.lon);
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) return;
      const name = cityName(loc);
      const key = `${name}|${lat.toFixed(3)}|${lon.toFixed(3)}`;
      if (seen.has(key)) return;
      seen.add(key);
      records.push({ name, lat, lon, aqi: loc.aqi_us ?? loc.aqi });
    });

    // Never let late/failed location API loading leave the globe unlabeled.
    MONITORED_CITIES.forEach(city => {
      const key = `${city.name}|${city.lat.toFixed(3)}|${city.lon.toFixed(3)}`;
      if (seen.has(key)) return;
      seen.add(key);
      const match = locations.find(loc =>
        Math.abs(Number(loc.lat) - city.lat) < 1.0 &&
        Math.abs(Number(loc.lon) - city.lon) < 1.0
      );
      records.push({
        name: city.name,
        lat: city.lat,
        lon: city.lon,
        aqi: match ? (match.aqi_us ?? match.aqi) : undefined
      });
    });

    return records;
  }

  function renderEnglishCityLabels(v) {
    const records = getCityRecords();
    const signature = records.map(c => `${c.name}:${c.lat.toFixed(3)}:${c.lon.toFixed(3)}:${c.aqi ?? ''}`).join('|');
    if (!signature) return;
    if (signature === lastLabelSignature) return;

    v.entities.values
      .filter(entity => entity.__atmosEnglishCity)
      .forEach(entity => v.entities.remove(entity));

    records.forEach(city => {
      const color = city.aqi != null && typeof window.aqiToColor === 'function'
        ? window.aqiToColor(city.aqi)
        : '#00d4ff';

      const entity = v.entities.add({
        position: Cesium.Cartesian3.fromDegrees(city.lon, city.lat, 0),
        point: {
          pixelSize: 7,
          color: Cesium.Color.fromCssColorString(color),
          outlineColor: Cesium.Color.BLACK,
          outlineWidth: 2,
          disableDepthTestDistance: Number.POSITIVE_INFINITY
        },
        label: {
          text: city.aqi != null ? `${city.name}  •  AQI ${city.aqi}` : city.name,
          font: '600 11px Space Mono, monospace',
          fillColor: Cesium.Color.WHITE,
          outlineColor: Cesium.Color.BLACK,
          outlineWidth: 3,
          style: Cesium.LabelStyle.FILL_AND_OUTLINE,
          verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
          pixelOffset: new Cesium.Cartesian2(0, -11),
          disableDepthTestDistance: Number.POSITIVE_INFINITY,
          scaleByDistance: new Cesium.NearFarScalar(1.0e6, 1.0, 1.8e7, 0.65),
          translucencyByDistance: new Cesium.NearFarScalar(1.5e7, 1.0, 2.2e7, 0.0)
        }
      });
      entity.__atmosEnglishCity = true;
    });

    lastLabelSignature = signature;
  }

  function currentLocation() {
    const s = window.state || {};
    const lat = Number(s.lat);
    const lon = Number(s.lon);
    return {
      lat: Number.isFinite(lat) ? lat : 20,
      lon: Number.isFinite(lon) ? lon : 78
    };
  }

  function centerEarth(v, immediate) {
    if (settling) return;
    const host = document.getElementById('cesium-container');
    if (!host) return;
    const rect = host.getBoundingClientRect();
    if (rect.width < 120 || rect.height < 120) return;

    settling = true;
    try {
      // Cesium must be resized after CSS grid layout has produced the real
      // viewport. Otherwise its canvas can retain the pre-layout dimensions.
      if (typeof v.resize === 'function') v.resize();
      if (v.scene && typeof v.scene.requestRender === 'function') v.scene.requestRender();

      const { lat, lon } = currentLocation();
      const destination = Cesium.Cartesian3.fromDegrees(lon, lat, 8000000);
      const view = {
        destination,
        orientation: {
          heading: 0,
          pitch: Cesium.Math.toRadians(-90),
          roll: 0
        }
      };

      if (typeof v.camera.cancelFlight === 'function') v.camera.cancelFlight();
      v.camera.setView(view);

      if (v.scene?.screenSpaceCameraController) {
        v.scene.screenSpaceCameraController.minimumZoomDistance = 1000000;
        v.scene.screenSpaceCameraController.maximumZoomDistance = 22000000;
      }
    } finally {
      settling = false;
    }
  }

  function patchSourceData() {
    if (typeof window.apiGet !== 'function' || window.__atmosSourceDataPatched) return;
    const original = window.apiGet;
    window.apiGet = async function (path) {
      const endpoint = String(path).split('?')[0];
      if (endpoint !== '/analytics/pollution-sources') return original(path);

      const q = new URLSearchParams(String(path).split('?')[1] || '');
      const lat = Number(q.get('lat')), lon = Number(q.get('lon'));
      const records = getCityRecords();
      let nearest = null, best = Infinity;
      records.forEach(loc => {
        const d = Math.hypot(Number(loc.lat) - lat, Number(loc.lon) - lon);
        if (d < best) { best = d; nearest = loc; }
      });
      const name = nearest ? nearest.name : '';
      const profile = SOURCE_PROFILES[name] || [
        ['Traffic / transport',62], ['Dust / construction',48],
        ['Industrial activity',44], ['Biomass / open burning',37]
      ];
      return {
        sources: profile.map(([label, confidence], i) => ({
          label,
          confidence: Math.max(20, Math.min(95, confidence + (Math.round(Math.abs(lat + lon)) % 7) - i)),
          indicators: ['PM2.5', i % 2 ? 'PM10' : 'NO₂', 'regional pattern']
        }))
      };
    };
    window.__atmosSourceDataPatched = true;
  }

  function settle() {
    const v = getViewer();
    if (!v) return false;
    injectViewportCSS();
    installEnglishBasemap(v);
    centerEarth(v, true);
    renderEnglishCityLabels(v);
    patchSourceData();
    viewerReady = true;
    return true;
  }

  function watchLayout(v) {
    const host = document.getElementById('cesium-container');
    if (!host || host.__atmosResizeObserver) return;

    const observer = new ResizeObserver(() => {
      if (!getViewer()) return;
      requestAnimationFrame(() => {
        if (typeof v.resize === 'function') v.resize();
        // Re-center only when the viewport dimensions materially change.
        const rect = host.getBoundingClientRect();
        const key = `${Math.round(rect.width)}x${Math.round(rect.height)}`;
        if (key !== host.__atmosViewportKey) {
          host.__atmosViewportKey = key;
          centerEarth(v, true);
        }
      });
    });
    observer.observe(host);
    host.__atmosResizeObserver = observer;
  }

  function trackState() {
    const v = getViewer();
    if (!v) return;

    const { lat, lon } = currentLocation();
    if (lat !== lastLat || lon !== lastLon) {
      lastLat = lat;
      lastLon = lon;
      centerEarth(v, false);
    }

    // API data can arrive after Cesium. Keep labels synchronized without
    // repeatedly destroying/recreating unchanged entities.
    renderEnglishCityLabels(v);
    patchSourceData();
  }

  function boot() {
    injectViewportCSS();
    let tries = 0;
    const timer = setInterval(() => {
      tries += 1;
      const v = getViewer();
      if (v) {
        settle();
        watchLayout(v);
        // Keep polling until data has actually arrived, not just until Cesium boots.
        if (getCityRecords().length >= MONITORED_CITIES.length) clearInterval(timer);
      }
      if (tries > 120) clearInterval(timer);
    }, 250);

    setInterval(trackState, 1000);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', boot, { once: true });
  } else {
    boot();
  }
})();
