/*
 * Atmos runtime recovery layer.
 * Additive only: preserves the existing Cesium/dashboard features.
 */
(function () {
  'use strict';
  const WEATHER = 'https://api.open-meteo.com/v1/forecast';
  const AIR = 'https://air-quality-api.open-meteo.com/v1/air-quality';
  const GEOCODE = 'https://geocoding-api.open-meteo.com/v1/search';

  const valid = (lat, lon) => Number.isFinite(lat) && Number.isFinite(lon) && lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180;
  const condition = code => ({0:['☀️','Clear sky'],1:['🌤️','Mainly clear'],2:['⛅','Partly cloudy'],3:['☁️','Overcast'],45:['🌫️','Fog'],48:['🌫️','Rime fog'],51:['🌦️','Light drizzle'],53:['🌦️','Drizzle'],55:['🌧️','Heavy drizzle'],61:['🌧️','Light rain'],63:['🌧️','Rain'],65:['🌧️','Heavy rain'],71:['🌨️','Light snow'],73:['🌨️','Snow'],75:['❄️','Heavy snow'],80:['🌦️','Rain showers'],81:['🌧️','Rain showers'],82:['⛈️','Heavy rain showers'],85:['🌨️','Snow showers'],86:['🌨️','Heavy snow showers'],95:['⛈️','Thunderstorm'],96:['⛈️','Thunderstorm with hail'],99:['⛈️','Heavy thunderstorm with hail']}[Number(code)] || ['—','Unknown']);
  const category = aqi => { const n=Number(aqi); if(!Number.isFinite(n)) return {level:'Data unavailable',color:'#888',health:''}; if(n<=50)return{level:'Good',color:'#00e676',health:'Air quality is satisfactory.'}; if(n<=100)return{level:'Moderate',color:'#ffea00',health:'Air quality is acceptable for most people.'}; if(n<=150)return{level:'Unhealthy for Sensitive Groups',color:'#ff9100',health:'Sensitive groups should reduce prolonged outdoor exertion.'}; if(n<=200)return{level:'Unhealthy',color:'#ff1744',health:'Everyone may begin to experience health effects.'}; if(n<=300)return{level:'Very Unhealthy',color:'#d500f9',health:'Health alert: increased risk for everyone.'}; return{level:'Hazardous',color:'#c62828',health:'Health emergency conditions.'}; };

  async function weather(lat,lon){
    const u=`${WEATHER}?latitude=${encodeURIComponent(lat)}&longitude=${encodeURIComponent(lon)}&current=temperature_2m,relative_humidity_2m,apparent_temperature,pressure_msl,uv_index,visibility,wind_speed_10m,wind_gusts_10m,wind_direction_10m,weather_code&timezone=auto`;
    const r=await fetch(u,{cache:'no-store'}); if(!r.ok)throw Error(`weather ${r.status}`); const c=(await r.json()).current||{}; const [icon,label]=condition(c.weather_code);
    const dirs=['N','NNE','NE','ENE','E','ESE','SE','SSE','S','SSW','SW','WSW','W','WNW','NW','NNW']; const deg=Number(c.wind_direction_10m);
    return {temperature:{celsius:c.temperature_2m,feels_like:c.apparent_temperature},humidity:c.relative_humidity_2m,pressure:c.pressure_msl,uv_index:c.uv_index,visibility_m:c.visibility,wind:{speed_kmh:c.wind_speed_10m,gusts_kmh:c.wind_gusts_10m,direction_deg:c.wind_direction_10m,cardinal:Number.isFinite(deg)?dirs[Math.round((((deg%360)+360)%360)/22.5)%16]:'—'},condition:{icon,label}};
  }
  async function air(lat,lon){
    const u=`${AIR}?latitude=${encodeURIComponent(lat)}&longitude=${encodeURIComponent(lon)}&current=us_aqi,pm2_5,pm10,nitrogen_dioxide,ozone,sulphur_dioxide,carbon_monoxide&timezone=auto`;
    const r=await fetch(u,{cache:'no-store'}); if(!r.ok)throw Error(`air ${r.status}`); const c=(await r.json()).current||{};
    return {aqi:c.us_aqi,category:category(c.us_aqi),pollutants:{pm2_5:{value:c.pm2_5,unit:'μg/m³'},pm10:{value:c.pm10,unit:'μg/m³'},nitrogen_dioxide:{value:c.nitrogen_dioxide,unit:'μg/m³'},ozone:{value:c.ozone,unit:'μg/m³'},sulphur_dioxide:{value:c.sulphur_dioxide,unit:'μg/m³'},carbon_monoxide:{value:c.carbon_monoxide,unit:'μg/m³'}}};
  }

  function patchApi(){
    if(typeof window.apiGet!=='function'||window.__atmosRuntimeApiPatched)return;
    const original=window.apiGet;
    window.apiGet=async function(path){
      const endpoint=String(path).split('?')[0], q=new URLSearchParams(String(path).split('?')[1]||''), lat=Number(q.get('lat')), lon=Number(q.get('lon'));
      if(location.hostname.endsWith('github.io')&&valid(lat,lon)&&endpoint==='/weather/current')try{return await weather(lat,lon)}catch(e){console.warn('Atmos live weather unavailable; retaining existing fallback.',e)}
      if(location.hostname.endsWith('github.io')&&valid(lat,lon)&&endpoint==='/aqi/current')try{return await air(lat,lon)}catch(e){console.warn('Atmos live AQI unavailable; retaining existing fallback.',e)}
      return original(path);
    };
    window.__atmosRuntimeApiPatched=true;
  }

  async function locate(){
    if(!navigator.geolocation){if(window.toast)toast('Device location is unavailable. Use Search or coordinates.','info');return}
    const b=document.getElementById('atmos-locate-btn'); if(b){b.disabled=true;b.textContent='LOCATING…'}
    navigator.geolocation.getCurrentPosition(async p=>{
      try{if(typeof window.setLocation==='function')await window.setLocation(p.coords.latitude,p.coords.longitude); if(window.toast)toast(`Using device location: ${p.coords.latitude.toFixed(3)}, ${p.coords.longitude.toFixed(3)}`,'info')}catch(e){console.error('Atmos location refresh failed:',e)}
      finally{if(b){b.disabled=false;b.textContent='LOCATE'}}
    },e=>{console.warn('Atmos geolocation failed:',e.code,e.message);if(window.toast)toast(e.code===1?'Location permission is blocked. Allow location for this site and tap LOCATE again.':'Could not obtain device location. Tap LOCATE to retry.','info');if(b){b.disabled=false;b.textContent='LOCATE'}},{enableHighAccuracy:false,timeout:10000,maximumAge:60000});
  }

  function addControl(){
    if(document.getElementById('atmos-locate-btn'))return;
    const host=document.querySelector('.globe-search')||document.querySelector('header'); if(!host)return;
    const b=document.createElement('button'); b.id='atmos-locate-btn';b.type='button';b.textContent='LOCATE';b.title='Use this device location';b.style.cssText='padding:8px 12px;background:rgba(0,230,118,.08);border:1px solid rgba(0,230,118,.3);border-radius:6px;color:#00e676;font:700 10px Space Mono,monospace;cursor:pointer;letter-spacing:.05em';b.onclick=locate;host.appendChild(b);
  }

  function boot(){patchApi();addControl();setTimeout(locate,250)}
  if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',boot,{once:true});else boot();
})();
