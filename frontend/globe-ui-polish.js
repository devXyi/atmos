/* Atmos globe UI polish.
 * Presentation-only: keeps monitored city names visible over the label-free map.
 */
(function () {
  'use strict';

  const CITIES = [
    { name: 'Lahore', country: 'PK', lat: 31.5497, lon: 74.3436, color: '#ff1744' },
    { name: 'Delhi', country: 'IN', lat: 28.6139, lon: 77.2090, color: '#ff9100' },
    { name: 'Jakarta', country: 'ID', lat: -6.2088, lon: 106.8456, color: '#ffea00' },
    { name: 'Bangkok', country: 'TH', lat: 13.7563, lon: 100.5018, color: '#ffea00' }
  ];

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

  function render(v) {
    v.entities.values
      .filter(e => e.__atmosEnglishCity || e.__atmosVisibleCityLabel)
      .forEach(e => v.entities.remove(e));

    CITIES.forEach(city => {
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

  function boot() {
    let last = '';
    const timer = setInterval(() => {
      const v = getViewer();
      if (!v) return;
      const signature = CITIES.map(c => `${c.name}:${getAQI(c.name) ?? ''}`).join('|');
      if (signature !== last) {
        last = signature;
        render(v);
      }
    }, 500);
    setTimeout(() => clearInterval(timer), 60000);
  }

  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', boot, { once: true });
  else boot();
})();
