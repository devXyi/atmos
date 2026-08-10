/*
 * Atmos Pages runtime compatibility layer.
 * Loaded before the inline dashboard script.
 *
 * It does not replace Cesium or the dashboard: it only retries Cesium's
 * constructor with mobile-safe WebGL options when the default context fails,
 * and gives browser geolocation a bounded request policy.
 */
(function () {
  'use strict';

  function patchCesiumViewer() {
    if (!window.Cesium || typeof window.Cesium.Viewer !== 'function') return;
    if (window.Cesium.__atmosViewerPatched) return;

    const OriginalViewer = window.Cesium.Viewer;

    const safeContext = {
      webgl: {
        alpha: false,
        depth: true,
        stencil: false,
        antialias: false,
        preserveDrawingBuffer: false,
        failIfMajorPerformanceCaveat: false,
        powerPreference: 'default',
      },
    };

    const webgl1Context = {
      requestWebgl1: true,
      webgl: safeContext.webgl,
    };

    function safeOptions(original, contextOptions) {
      const base = original && typeof original === 'object' ? original : {};
      return {
        ...base,
        useBrowserRecommendedResolution: true,
        contextOptions: {
          ...(base.contextOptions || {}),
          ...contextOptions,
          webgl: {
            ...safeContext.webgl,
            ...((base.contextOptions && base.contextOptions.webgl) || {}),
            ...(contextOptions.webgl || {}),
          },
        },
      };
    }

    window.Cesium.Viewer = new Proxy(OriginalViewer, {
      construct(target, args) {
        try {
          return Reflect.construct(target, args, target);
        } catch (firstError) {
          const container = args[0];
          const originalOptions = args[1] || {};
          const node = typeof container === 'string' ? document.getElementById(container) : container;
          if (node) node.innerHTML = '';

          try {
            console.warn('Atmos: Cesium default context failed; retrying mobile-safe WebGL.', firstError);
            return Reflect.construct(
              target,
              [container, safeOptions(originalOptions, safeContext)],
              target
            );
          } catch (secondError) {
            if (node) node.innerHTML = '';
            console.warn('Atmos: WebGL2 retry failed; retrying with WebGL1.', secondError);
            return Reflect.construct(
              target,
              [container, safeOptions(originalOptions, webgl1Context)],
              target
            );
          }
        }
      },
    });

    window.Cesium.__atmosViewerPatched = true;
  }

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
    } catch (_) {
      // Some browsers expose geolocation methods as non-writable.
    }
  }

  patchCesiumViewer();
  patchGeolocation();

  // Retry device location after the main dashboard script has defined
  // setLocation. This is additive; the existing location flow remains intact.
  window.addEventListener('DOMContentLoaded', function () {
    setTimeout(function () {
      if (!navigator.geolocation || typeof window.setLocation !== 'function') return;

      navigator.geolocation.getCurrentPosition(
        function (position) {
          const lat = position.coords.latitude;
          const lon = position.coords.longitude;
          console.info('Atmos runtime location:', lat, lon, '±', position.coords.accuracy, 'm');
          window.setLocation(lat, lon).catch(function (error) {
            console.warn('Atmos runtime location refresh failed:', error);
          });
        },
        function (error) {
          console.info('Atmos runtime location unavailable:', error && error.code, error && error.message);
        },
        { enableHighAccuracy: false, timeout: 10000, maximumAge: 60000 }
      );
    }, 250);
  }, { once: true });
})();
