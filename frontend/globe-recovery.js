/* Atmos globe recovery layer.
 * Cesium 1.122 exposes Viewer as a readonly export. Do not assign to
 * Cesium.Viewer. This module only probes WebGL, publishes safe constructor
 * options, and provides an explicit visual fallback when construction fails.
 */
(function () {
  'use strict';

  function webglProbe() {
    try {
      const c = document.createElement('canvas');
      const gl2 = c.getContext('webgl2', { alpha: false, antialias: false });
      const gl1 = gl2 ? null : c.getContext('webgl', { alpha: false, antialias: false });
      const gl = gl2 || gl1;
      if (!gl) return { available: false, version: 'none', renderer: 'none' };
      const dbg = gl.getExtension('WEBGL_debug_renderer_info');
      return { available: true, version: gl2 ? 'webgl2' : 'webgl1', renderer: dbg ? gl.getParameter(dbg.UNMASKED_RENDERER_WEBGL) : 'unknown' };
    } catch (error) {
      return { available: false, version: 'error', renderer: String(error && error.message || error) };
    }
  }

  const probe = webglProbe();
  window.__atmosWebGLProbe = probe;
  console.info('Atmos WebGL probe:', probe);

  window.__atmosCesiumOptions = function (original) {
    const base = original && typeof original === 'object' ? original : {};
    const safe = {
      terrainProvider: window.Cesium && window.Cesium.EllipsoidTerrainProvider ? new window.Cesium.EllipsoidTerrainProvider() : undefined,
      animation: false, baseLayerPicker: false, fullscreenButton: false, geocoder: false,
      homeButton: false, infoBox: false, sceneModePicker: false, selectionIndicator: false,
      timeline: false, navigationHelpButton: false, scene3DOnly: true,
      orderIndependentTranslucency: false, useBrowserRecommendedResolution: true,
      resolutionScale: probe.available ? 0.75 : 0.5,
      requestRenderMode: false,
      targetFrameRate: 30,
      contextOptions: {
        ...(base.contextOptions || {}),
        requestWebgl1: probe.version === 'webgl1',
        allowTextureFilterAnisotropic: false,
        webgl: {
          alpha: false, depth: true, stencil: false, antialias: false,
          premultipliedAlpha: false, preserveDrawingBuffer: false,
          failIfMajorPerformanceCaveat: false, powerPreference: 'low-power',
          ...((base.contextOptions && base.contextOptions.webgl) || {}),
        },
      },
    };
    return { ...base, ...safe, contextOptions: { ...safe.contextOptions } };
  };

  window.__atmosDrawFallbackGlobe = function drawFallbackGlobe() {
    const host = document.getElementById('cesium-container');
    if (!host || host.querySelector('.cesium-viewer, canvas.cesium-widget-canvas') || document.getElementById('atmos-globe-fallback')) return;
    host.innerHTML = '';
    const wrap = document.createElement('div');
    wrap.id = 'atmos-globe-fallback';
    wrap.style.cssText = 'position:absolute;inset:0;display:flex;align-items:center;justify-content:center;overflow:hidden;background:radial-gradient(circle at 38% 34%,rgba(0,212,255,.10),transparent 34%),#050810;';
    const canvas = document.createElement('canvas');
    canvas.style.cssText = 'width:min(72vw,520px);height:min(72vw,520px);max-width:78%;max-height:78%;filter:drop-shadow(0 0 28px rgba(0,212,255,.14));';
    wrap.appendChild(canvas);
    const label = document.createElement('div');
    label.style.cssText = 'position:absolute;bottom:22px;left:50%;transform:translateX(-50%);font:9px "Space Mono",monospace;letter-spacing:.12em;color:rgba(232,236,244,.34);white-space:nowrap;';
    label.textContent = 'ATMOS EARTH • FALLBACK RENDER MODE';
    wrap.appendChild(label);
    host.appendChild(wrap);
    const ctx = canvas.getContext('2d');
    if (!ctx) return;
    function frame() {
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      const w = canvas.width = Math.max(320, Math.floor(canvas.clientWidth * dpr));
      const h = canvas.height = Math.max(320, Math.floor(canvas.clientHeight * dpr));
      const cx = w / 2, cy = h / 2, r = Math.min(w, h) * .36;
      ctx.clearRect(0, 0, w, h);
      const g = ctx.createRadialGradient(cx-r*.3, cy-r*.35, r*.08, cx, cy, r*1.15);
      g.addColorStop(0, '#16394a'); g.addColorStop(.72, '#071a24'); g.addColorStop(1, '#02070b');
      ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI*2); ctx.fillStyle = g; ctx.fill();
      ctx.save(); ctx.beginPath(); ctx.arc(cx, cy, r, 0, Math.PI*2); ctx.clip();
      ctx.strokeStyle = 'rgba(0,212,255,.18)'; ctx.lineWidth = dpr;
      for (let i=-3;i<=3;i++) { const x=cx+(i/3)*r*.82; ctx.beginPath(); ctx.ellipse(x,cy,Math.max(3,r*(1-Math.abs(i)/4)),r,0,0,Math.PI*2); ctx.stroke(); }
      for (let i=-2;i<=2;i++) { const y=cy+(i/2)*r*.72; ctx.beginPath(); ctx.ellipse(cx,y,r,Math.max(3,r*(.16+(2-Math.abs(i))*.11)),0,0,Math.PI*2); ctx.stroke(); }
      ctx.fillStyle = 'rgba(0,230,118,.20)';
      [[[-.62,-.25],[-.45,-.45],[-.22,-.40],[-.18,-.18],[-.34,-.04],[-.45,.14],[-.61,.08]],[[-.08,-.18],[.12,-.34],[.34,-.26],[.43,-.06],[.28,.08],[.05,.02]],[[.44,-.10],[.67,-.02],[.76,.15],[.55,.26],[.34,.18]],[[-.12,.12],[.06,.25],[.16,.55],[.03,.74],[-.10,.48]]].forEach(poly=>{ctx.beginPath();poly.forEach((p,j)=>{const x=cx+p[0]*r,y=cy+p[1]*r;j?ctx.lineTo(x,y):ctx.moveTo(x,y);});ctx.closePath();ctx.fill();});
      ctx.restore();
      ctx.beginPath(); ctx.arc(cx,cy,r,0,Math.PI*2); ctx.strokeStyle='rgba(0,212,255,.42)'; ctx.lineWidth=1.5*dpr; ctx.stroke();
      requestAnimationFrame(frame);
    }
    requestAnimationFrame(frame);
  };
})();
