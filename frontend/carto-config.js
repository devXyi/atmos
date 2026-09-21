/* CARTO basemap configuration.
 * The deployment workflow replaces __ATMOS_CARTO_KEY__ with the
 * GitHub Actions secret at build time. The placeholder is intentionally
 * committed instead of the real credential.
 */
(function () {
  'use strict';

  const key = '__ATMOS_CARTO_KEY__';
  window.ATMOS_CARTO_KEY = key === '__ATMOS_CARTO_KEY__' ? '' : key;
})();
