/* Atmos Pages runtime compatibility layer.
 * IMPORTANT: Cesium.Viewer is a readonly export in Cesium 1.122.
 * This file must never replace/mutate Cesium.Viewer. It only patches the
 * optional browser geolocation/data paths used by GitHub Pages.
 */
(function () {
  'use strict';

  function patchGeolocation() {
    if (!navigator.geolocation || navigator.geolocation.__atmosPatched) return;
    const original = navigator.geolocation.getCurrentPosition.bind(navigator.geolocation);
    const wrapper = function (success, error, options) {
      const requested = options || {};
      return original(success, error, {
        ...requested,
        enableHighAccuracy: requested.enableHighAccuracy ?? false,
        timeout: Math.min(Number.isFinite(requested.timeout) ? requested.timeout : 10000, 10000),
        maximumAge: Number.isFinite(requested.maximumAge) ? requested.maximumAge : 60000,
      });
    };
    try {
      Object.defineProperty(wrapper, '__atmosPatched', { value: true });
      navigator.geolocation.getCurrentPosition = wrapper;
    } catch (_) {}
  }

  function weatherCode(code) {
    const map = {
      0: ['☀️', 'Clear sky'], 1: ['🌤️', 'Mainly clear'], 2: ['⛅', 'Partly cloudy'], 3: ['☁️', 'Overcast'],
      45: ['🌫️', 'Fog'], 48: ['🌫️', 'Depositing rime fog'], 51: ['🌦️', 'Light drizzle'], 53: ['🌦️', 'Drizzle'],
      55: ['🌧️', 'Heavy drizzle'], 56: ['🌧️', 'Freezing drizzle'], 57: ['🌧️', 'Heavy freezing drizzle'],
      61: ['🌧️', 'Light rain'], 63: ['🌧️', 'Rain'], 65: ['🌧️', 'Heavy rain'], 66: ['🌧️', 'Freezing rain'],
      67: ['🌧️', 'Heavy freezing rain'], 71: ['🌨️', 'Light snow'], 73: ['🌨️', 'Snow'], 75: ['❄️', 'Heavy snow'],
      77: ['❄️', 'Snow grains'], 80: ['🌦️', 'Rain showers'], 81: ['🌧️', 'Rain showers'], 82: ['⛈️', 'Heavy rain showers'],
      85: ['🌨️', 'Snow showers'], 86: ['🌨️', 'Heavy snow showers'], 95: ['⛈️', 'Thunderstorm'],
      96: ['⛈️', 'Thunderstorm with hail'], 99: ['⛈️', 'Heavy thunderstorm with hail'],
    };
    return map[Number(code)] || ['—', 'Unknown'];
  }

  function cardinal(deg) {
    if (!Number.isFinite(deg)) return '—';
    const dirs = ['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW'];
    return dirs[Math.round((((deg % 360) + 360) % 360) / 22.5) % 16];
  }

  function aqiCategory(aqi) {
    const n = Number(aqi);
    if (!Number.isFinite(n)) return { level: 'Data unavailable', color: '#888', health: '' };
    if (n <= 50) return { level: 'Good', color: '#00e676', health: 'Air quality is satisfactory.' };
    if (n <= 100) return { level: 'Moderate', color: '#ffea00', health: 'Air quality is acceptable for most people.' };
    if (n <= 150) return { level: 'Unhealthy for Sensitive Groups', color: '#ff9100', health: 'Sensitive groups should reduce prolonged outdoor exertion.' };
    if (n <= 200) return { level: 'Unhealthy', color: '#ff1744', health: 'Everyone may begin to experience health effects.' };
    if (n <= 300) return { level: 'Very Unhealthy', color: '#d500f9', health: 'Health alert: increased risk for everyone.' };
    return { level: 'Hazardous', color: '#c62828', health: 'Health emergency conditions.' };
  }

  function patchPagesData() {
    if (typeof window.apiGet !== 'function' || window.__atmosLivePagesDataPatched) return;
    const originalApiGet = window.apiGet;
    window.apiGet = async function (path) {
      if (!window.location.hostname.endsWith('github.io')) return originalApiGet(path);
      const endpoint = String(path).split('?')[0];
      if (endpoint !== '/weather/current' && endpoint !== '/aqi/current') return originalApiGet(path);
      const q = new URLSearchParams(String(path).split('?')[1] || '');
      const lat = Number(q.get('lat')), lon = Number(q.get('lon'));
      if (!Number.isFinite(lat) || !Number.isFinite(lon)) return originalApiGet(path);
      try {
        if (endpoint === '/weather/current') {
          const url = `https://api.open-meteo.com/v1/forecast?latitude=${encodeURIComponent(lat)}&longitude=${encodeURIComponent(lon)}&current=temperature_2m,relative_humidity_2m,apparent_temperature,pressure_msl,uv_index,visibility,wind_speed_10m,wind_gusts_10m,wind_direction_10m,weather_code&timezone=auto`;
          const r = await fetch(url, { cache: 'no-store' });
          if (!r.ok) throw new Error(`Open-Meteo weather HTTP ${r.status}`);
          const d = await r.json(), c = d.current || {}, [icon, label] = weatherCode(c.weather_code);
          return { temperature: { celsius: c.temperature_2m, feels_like: c.apparent_temperature }, humidity: c.relative_humidity_2m, pressure: c.pressure_msl, uv_index: c.uv_index, visibility_m: c.visibility, wind: { speed_kmh: c.wind_speed_10m, gusts_kmh: c.wind_gusts_10m, direction_deg: c.wind_direction_10m, cardinal: cardinal(c.wind_direction_10m) }, condition: { icon, label } };
        }
        const url = `https://air-quality-api.open-meteo.com/v1/air-quality?latitude=${encodeURIComponent(lat)}&longitude=${encodeURIComponent(lon)}&current=us_aqi,pm2_5,pm10,nitrogen_dioxide,ozone,sulphur_dioxide,carbon_monoxide&timezone=auto`;
        const r = await fetch(url, { cache: 'no-store' });
        if (!r.ok) throw new Error(`Open-Meteo air-quality HTTP ${r.status}`);
        const d = await r.json(), c = d.current || {}, aqi = c.us_aqi;
        return { aqi, category: aqiCategory(aqi), pollutants: { pm2_5: { value: c.pm2_5, unit: 'μg/m³' }, pm10: { value: c.pm10, unit: 'μg/m³' }, nitrogen_dioxide: { value: c.nitrogen_dioxide, unit: 'μg/m³' }, ozone: { value: c.ozone, unit: 'μg/m³' }, sulphur_dioxide: { value: c.sulphur_dioxide, unit: 'μg/m³' }, carbon_monoxide: { value: c.carbon_monoxide, unit: 'μg/m³' } } };
      } catch (error) {
        console.warn('Atmos live Pages data unavailable; retaining existing fallback:', error);
        return originalApiGet(path);
      }
    };
    window.__atmosLivePagesDataPatched = true;
  }

  patchGeolocation();
  window.addEventListener('DOMContentLoaded', function () {
    patchPagesData();
    setTimeout(function () {
      if (!navigator.geolocation || typeof window.setLocation !== 'function') return;
      navigator.geolocation.getCurrentPosition(function (position) {
        const { latitude: lat, longitude: lon, accuracy } = position.coords;
        console.info('Atmos runtime location:', lat, lon, '±', accuracy, 'm');
        window.setLocation(lat, lon).catch(function (error) { console.warn('Atmos runtime location refresh failed:', error); });
      }, function (error) { console.info('Atmos runtime location unavailable:', error && error.code, error && error.message); }, { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 });
    }, 250);
  }, { once: true });
})();
