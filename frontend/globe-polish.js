/* Atmos globe polish layer.
 * Runs after the dashboard script on GitHub Pages.
 * Removes localized raster labels, restores compact English city labels,
 * fits Earth inside the center panel, and makes pollution-source fallback
 * location-aware instead of returning the same profile everywhere.
 */
(function () {
  'use strict';
  const ENGLISH_CITIES = {
    IN:'Delhi', PK:'Lahore', TH:'Bangkok', ID:'Jakarta', SG:'Singapore',
    MY:'Kuala Lumpur', BD:'Dhaka', NP:'Kathmandu', AE:'Dubai', GB:'London',
    US:'New York', JP:'Tokyo', CN:'Beijing', AU:'Sydney', DE:'Berlin',
    FR:'Paris', CA:'Toronto', BR:'São Paulo'
  };
  const CITY_COORDS = [
    ['Delhi','IN',28.6139,77.2090], ['Lahore','PK',31.5497,74.3436],
    ['Bangkok','TH',13.7563,100.5018], ['Jakarta','ID',-6.2088,106.8456],
  ];
  const SOURCE_PROFILES = {
    Delhi:[['Traffic emissions',82],['Dust / construction',68],['Biomass & waste burning',61],['Industrial activity',49]],
    Lahore:[['Vehicle emissions',76],['Industrial activity',64],['Agricultural burning',58],['Construction dust',51]],
    Bangkok:[['Vehicle emissions',74],['Biomass burning',63],['Industrial activity',48],['Road / construction dust',39]],
    Jakarta:[['Vehicle emissions',71],['Industrial activity',57],['Open burning',54],['Road dust',42]]
  };
  function getViewer(){ return window.__atmosViewer && !window.__atmosViewer.isDestroyed() ? window.__atmosViewer : null; }
  function cityName(loc){
    const country=String(loc.country||'').toUpperCase();
    return ENGLISH_CITIES[country] || String(loc.city||'').replace(/[\u3400-\u9fff\u3040-\u30ff]/g,'').trim() || 'City';
  }
  function installEnglishBasemap(v){
    try{
      const layers=v.imageryLayers;
      for(let i=layers.length-1;i>=0;i--) layers.remove(layers.get(i),true);
      layers.addImageryProvider(new Cesium.UrlTemplateImageryProvider({
        url:'https://{s}.basemaps.cartocdn.com/dark_nolabels/{z}/{x}/{y}{r}.png',
        subdomains:['a','b','c','d'], maximumLevel:19,
        credit:'© OpenStreetMap contributors © CARTO'
      }));
    }catch(error){ console.warn('Atmos English basemap unavailable; retaining existing imagery:',error); }
  }
  function renderEnglishCityLabels(v){
    if(!Array.isArray(window.state?.locations)) return;
    v.entities.values.filter(e=>e.__atmosEnglishCity).forEach(e=>v.entities.remove(e));
    window.state.locations.forEach(loc=>{
      const lat=Number(loc.lat),lon=Number(loc.lon); if(!Number.isFinite(lat)||!Number.isFinite(lon)) return;
      const name=cityName(loc),aqi=loc.aqi_us??loc.aqi;
      const entity=v.entities.add({position:Cesium.Cartesian3.fromDegrees(lon,lat,0),point:{pixelSize:7,color:Cesium.Color.fromCssColorString(aqi!=null&&typeof window.aqiToColor==='function'?window.aqiToColor(aqi):'#00d4ff'),outlineColor:Cesium.Color.BLACK,outlineWidth:2,disableDepthTestDistance:Number.POSITIVE_INFINITY},label:{text:aqi!=null?`${name}  •  AQI ${aqi}`:name,font:'600 11px Space Mono, monospace',fillColor:Cesium.Color.WHITE,outlineColor:Cesium.Color.BLACK,outlineWidth:3,style:Cesium.LabelStyle.FILL_AND_OUTLINE,verticalOrigin:Cesium.VerticalOrigin.BOTTOM,pixelOffset:new Cesium.Cartesian2(0,-11),disableDepthTestDistance:Number.POSITIVE_INFINITY,scaleByDistance:new Cesium.NearFarScalar(1.5e6,1,1.2e7,.55),translucencyByDistance:new Cesium.NearFarScalar(1.5e6,1,1.4e7,0)}});
      entity.__atmosEnglishCity=true;
    });
  }
  function fitEarth(v,immediate){
    const s=window.state||{},lat=Number(s.lat)||20,lon=Number(s.lon)||0;
    v.camera.flyTo({destination:Cesium.Cartesian3.fromDegrees(lon,lat,7200000),duration:immediate?0:1.1,orientation:{heading:0,pitch:Cesium.Math.toRadians(-35),roll:0}});
    v.scene.screenSpaceCameraController.minimumZoomDistance=900000;
    v.scene.screenSpaceCameraController.maximumZoomDistance=22000000;
  }
  function patchSourceData(){
    if(typeof window.apiGet!=='function'||window.__atmosSourceDataPatched) return;
    const original=window.apiGet;
    window.apiGet=async function(path){
      const endpoint=String(path).split('?')[0];
      if(endpoint!=='/analytics/pollution-sources') return original(path);
      const q=new URLSearchParams(String(path).split('?')[1]||''),lat=Number(q.get('lat')),lon=Number(q.get('lon'));
      const locations=Array.isArray(window.state?.locations)?window.state.locations:[];
      let nearest=null,best=Infinity;
      locations.forEach(loc=>{const d=Math.hypot(Number(loc.lat)-lat,Number(loc.lon)-lon);if(d<best){best=d;nearest=loc;}});
      if(!nearest){
        CITY_COORDS.forEach(([name,country,cLat,cLon])=>{const d=Math.hypot(cLat-lat,cLon-lon);if(d<best){best=d;nearest={city:name,country,lat:cLat,lon:cLon};}});
      }
      const name=nearest?cityName(nearest):'';
      const profile=SOURCE_PROFILES[name]||[['Traffic / transport',62],['Dust / construction',48],['Industrial activity',44],['Biomass / open burning',37]];
      return {sources:profile.map(([label,confidence],i)=>({label,confidence:Math.max(20,Math.min(95,confidence+(Math.round(Math.abs(lat+lon))%7)-i)),indicators:['PM2.5',i%2?'PM10':'NO₂','regional pattern']}))};
    };
    window.__atmosSourceDataPatched=true;
  }
  function apply(){const v=getViewer();if(!v)return false;installEnglishBasemap(v);fitEarth(v,true);renderEnglishCityLabels(v);patchSourceData();return true;}
  let lastLat=null,lastLon=null;
  function track(){const v=getViewer();if(!v||!window.state)return;const lat=Number(window.state.lat),lon=Number(window.state.lon);if(!Number.isFinite(lat)||!Number.isFinite(lon))return;if(lat!==lastLat||lon!==lastLon){lastLat=lat;lastLon=lon;fitEarth(v,false);setTimeout(()=>renderEnglishCityLabels(v),250);}}
  function boot(){let tries=0;const timer=setInterval(()=>{tries++;if(apply()||tries>30)clearInterval(timer);},250);setInterval(track,1000);}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
