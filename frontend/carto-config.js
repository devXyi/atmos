/* CARTO basemap configuration.
 * The deployment workflow replaces __ATMOS_CARTO_KEY__ with the
 * GitHub Actions secret at build time. The placeholder is intentionally
 * committed instead of the real credential.
 */
(function () {
  'use strict';

  const key = '__ATMOS_CARTO_KEY__';
  window.ATMOS_CARTO_KEY = key === '__ATMOS_CARTO_KEY__' ? '' : key;

  // The existing ATMoS globe creates CARTO imagery through Cesium's
  // UrlTemplateImageryProvider. Wrap that constructor so every CARTO
  // raster tile request receives the configured key without changing
  // the globe presentation layer itself.
  if (!window.Cesium || !window.Cesium.UrlTemplateImageryProvider || !window.ATMOS_CARTO_KEY) return;
  if (window.__atmosCartoProviderPatched) return;

  const OriginalProvider = window.Cesium.UrlTemplateImageryProvider;
  window.Cesium.UrlTemplateImageryProvider = new Proxy(OriginalProvider, {
    construct(target, args, newTarget) {
      const options = args[0] || {};
      const url = String(options.url || '');
      if (!url.includes('basemaps.cartocdn.com')) {
        return Reflect.construct(target, args, newTarget);
      }

      const separator = url.includes('?') ? '&' : '?';
      const patchedOptions = {
        ...options,
        url: `${url}${separator}key=${encodeURIComponent(window.ATMOS_CARTO_KEY)}`
      };
      return Reflect.construct(target, [patchedOptions], newTarget);
    }
  });

  window.__atmosCartoProviderPatched = true;
})();
