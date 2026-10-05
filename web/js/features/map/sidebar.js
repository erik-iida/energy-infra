/* Map side pane: breadcrumb, totals, farm list and wake controls; go(country, farm) navigation used by every tab.
   ES module (spec 3 step 2): imports name what this file needs from other modules, the export list at the end what it offers. */
import { COUNTRIES, F, FEED, REGIONS, RGOF, S, Z, inC, isReg, place, sum } from "../../core/data.js";
import { $, fmt } from "../../core/util.js";
import { spacingOf } from "../../core/wake.js";
import { LIVE, MODELS, N0, agg, cur, curWind, hl, now, series } from "../../core/feed.js";
import { registerMap } from "../../core/router.js";
import { HOME, farmBox, fit } from "./canvas.js";
import { bbox, flyTo } from "./view.js";
import { paint } from "./paint.js";
function crumb(){const p=[["World","e"]];if(S.c&&!isReg(S.c))p.push([RGOF[S.c],"r"]);if(S.c)p.push([S.c,"c"]);if(S.farm!==null)p.push([F[S.farm].n,"f"]);
 $("crumb").innerHTML=p.map((q,i)=>i<p.length-1?"<a data-go='"+q[1]+"'>"+q[0]+"</a>":"<span>"+q[0]+"</span>").join("<span>›</span>")}
function sidebar(){$("uv").textContent=$("U").value+" m/s";$("dv").textContent=$("D").value+"°";$("kv").textContent=(+$("K").value).toFixed(4);crumb();$("note").style.display="none";
 $("wif").style.display=LIVE()?"none":"block";$("mapctl").style.display=S.tab==="map"&&S.farm!=null?"block":"none";  // wake / forecast controls only for a selected farm
 // the offshore-wind figures (output / capacity, farm and country lists) only for a selected farm; at region level the pane
 // is title, crumb and legend (Erik, 5 Oct 2026: the wind metrics and the country selector were the legacy of the wake monitor)
 const farm=S.farm!=null;["farmhd","list","cmp"].forEach(id=>{$(id).style.display=farm?"":"none"});
 const fs=F.filter(f=>inC(f,S.c)),zs=Z.filter(z=>inC(z,S.c)),cap=fs.reduce((a,f)=>a+f.inst,0);
 if(S.tab!=="map"){series();const A=agg(fs);$("mw").textContent=fmt(A.P[N0]);$("mwsub").textContent=place(S.c)+" at "+hl(N0)+", "+MODELS[S.fm]+", of "+fmt(cap)+" operating";$("cmp").innerHTML="";
  $("sub").textContent=fs.length+" operating farms · "+zs.length+" future zones";return}
 const src=LIVE()?"forecast wind":"what-if wind";
 if(S.farm===null){
  $("mw").textContent=fmt(now(S.c));$("mwsub").textContent=place(S.c)+" now with "+src+", of "+fmt(cap)+" operating";
  $("sub").textContent="";$("cmp").innerHTML="";  // farm and zone counts were part of the legacy wind header (removed 5 Oct 2026)
  if(S.c===null||isReg(S.c))$("list").innerHTML=(S.c===null?REGIONS:COUNTRIES.filter(c=>RGOF[c]===S.c)).map(c=>{const i=sum(c);return"<button data-c='"+c+"'><span>"+c+"</span><span class='mut'>"+(i?fmt(now(c))+" / "+fmt(i):"zones only")+"</span></button>"}).join("");
  else $("list").innerHTML=fs.length?F.map((f,i)=>!inC(f,S.c)?"":"<button data-i='"+i+"' class='"+(f.lay?"":"est")+"'><span>"+f.n+"</span><span class='mut'>"+fmt(cur(f).pw)+" / "+fmt(f.inst)+"</span></button>").join(""):"<div class='mut'>No operating farms here yet. Hover the zones on the map.</div>"}
 else{const f=F[S.farm],r=cur(f),[U,D]=curWind(f);$("mw").textContent=fmt(r.pw);
  if(f.lay){$("mwsub").textContent="of "+fmt(f.inst)+" · wake loss "+(100*(1-r.pw/r.free||0)).toFixed(1)+"% · "+U.toFixed(1)+" m/s from "+D+"° at hub ("+src+")";const sp=spacingOf(f);$("sub").innerHTML=(f.mixed?Object.entries(f.mixed).map(([t,c])=>c+" × "+t).join(" + "):f.xy.length/2+" × "+f.t)+(f.mixed?" · hub "+f.h+" m":" · D "+f.D+" m · hub "+f.h+" m")+(f.src==="gowt"?" · first seen "+f.y+(f.y==="2015"?" or earlier":""):f.y?" · COD "+f.y:"")+(f.on?" · <b>onshore (demo)</b>":"")+" · site "+f.a+" km² ("+(f.inst/f.a).toFixed(1)+" MW/km²)"+(sp?"<br>Spacing to nearest turbine: min "+sp.min.toFixed(1)+" D · mean "+sp.mean.toFixed(1)+" D · max "+sp.max.toFixed(1)+" D":"");
   const q=FEED&&FEED.farms[String(f.id)],pyw=FEED&&LIVE()&&f.S,names={jensen:"Jensen (NOJ)",bastankhah:"Bastankhah & Porté-Agel 2014",niayifar:"Niayifar & Porté-Agel 2016",turbopark:"TurbOPark (Nygaard 2022)",nowake:"No wake"};
   const ms=q&&q.ms,sec=v=>v==null?"–":v>=1000?(v/1000).toFixed(1)+" s":Math.round(v)+" ms";
   let h="<h2>PyWake models</h2>";
   if(pyw){h+="<table><tr><td class='mut'>Model</td><td class='mut'>Output "+hl(N0)+"</td><td class='mut'>Calc time</td></tr>"+Object.keys(MODELS).map(m=>"<tr><td>"+(names[m]||MODELS[m])+"</td><td>"+fmt(f.S[m][N0])+"</td><td>"+(m==="nowake"?"":sec(ms&&ms[m]))+"</td></tr>").join("")+"</table>";
    h+="<div class='mut' style='font-size:12px;margin-top:6px'>Calc time = PyWake run time for this farm"+(q&&q.nt?" over "+q.nt+" hours (now + forecast)":"")+" in the hourly pipeline on GitHub Actions"+(ms?"":"; recorded from the next run")+". No blockage modelled.</div>"}
   else h+="<div class='mut' style='font-size:12px'>PyWake results come with the hourly forecast feed; they're not available for what-if wind.</div>";
   if(f.src==="osm")h="<div class='note-est'><b>From OpenStreetMap.</b> Turbine positions"+(f.est==="OpenStreetMap tags"?", type and size":f.est==="OpenStreetMap rated power"?" and rated power":"")+" from OpenStreetMap"+(f.est.startsWith("assumed")?"; the turbine isn't tagged, so "+f.mw+" MW and a "+f.D+" m rotor are assumed":"")+". "+(f.on?"Onshore demo: same flat-terrain wake models with 10% ambient turbulence; no terrain, forest or stability effects. ":"")+"Treat output and wake loss as indicative.</div>"+h;
   if(f.src==="gowt")h="<div class='note-est'><b>Estimated turbines.</b> Positions are Sentinel-1 radar detections up to 2021 (Zhang et al.); the turbine type isn't known"+(f.est==="known turbine type"?", except this project's published type":", so "+f.mw+" MW and a "+f.D+" m rotor are assumed ("+f.est+")")+". Project data from the dataset: "+(f.pmw?f.pmw+" MW, ":"")+(f.own||"owner unknown")+". Treat output and wake loss as indicative.</div>"+h;
   $("cmp").innerHTML=h}
  else{$("mwsub").textContent="of "+fmt(f.inst)+" · estimated";$("sub").textContent="Site "+f.a+" km²";$("cmp").innerHTML="";const n=$("note");n.style.display="block";n.textContent="There are no turbine positions for this farm in the dataset, so there's no wake field. Output is the free-stream power curve with an assumed 10% wake loss."}
  $("list").innerHTML=F.map((g,i)=>g.c!==f.c?"":"<button data-i='"+i+"' class='"+(i===S.farm?"on ":"")+(g.lay?"":"est")+"'><span>"+g.n+"</span><span class='mut'>"+fmt(cur(g).pw)+"</span></button>").join("")}}
registerMap({paint,pane:sidebar,goto(c,farm){if(farm!=null)flyTo(fit(farmBox(F[farm]),.12));else flyTo(fit(c?bbox(c):HOME,0))}}); // the router draws the map and fills the pane through these

export { sidebar };
