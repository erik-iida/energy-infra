/* Market tab: day-ahead prices per zone, model check against actual offshore output, tab render.
   ES module (spec 3 step 2): imports name what this file needs from other modules, the export list at the end what it offers. */
import { F, S, inC, sum } from "../../core/data.js";
import { $, fmt } from "../../core/util.js";
import { MK, MODELS, N0, NP, NT, dl } from "../../core/feed.js";
import { ZONEFLAG, selZones } from "../../core/flags.js";
import { series } from "../compare/compare.js";
import { dtip } from "../../core/chart.js";
import { CMP, cmpRender } from "../../core/cmp.js";
import { HM, hmRender } from "./heatmap.js";
import { capDraw, capSection, fxNote, makeSortable } from "./capture.js";
/* ---------- Market tab (day-ahead prices + actual generation) ---------- */
const ZN={"DK1":"Denmark West (DK1)","DK2":"Denmark East (DK2)","DE-LU":"Germany–Luxembourg","NL":"Netherlands","BE":"Belgium","FR":"France","SE4":"Sweden South (SE4)","IE(SEM)":"Ireland (SEM)","PT":"Portugal","ES":"Spain"};
const CCN={de:"Germany",nl:"Netherlands",be:"Belgium",dk:"Denmark",fr:"France",se:"Sweden",ie:"Ireland",pt:"Portugal",es:"Spain",uk:"United Kingdom"};
const HN={de:"Germany (DE-LU)",nl:"Netherlands",be:"Belgium",dk:"Denmark (DK1/DK2 blend)",fr:"France"};
F.forEach(f=>{f.zone=MK?MK.farm_zone[String(f.id)]:null});
let TIPS=[];
const eur=v=>v==null||!isFinite(v)?"–":(Math.abs(v)>=1e6?(v/1e6).toFixed(2)+" M€":Math.abs(v)>=1e4?Math.round(v/1e3)+" k€":Math.round(v).toLocaleString()+" €");
const pm=v=>v==null||!isFinite(v)?"–":v.toFixed(1)+" €/MWh";
function capStats(fs,price,a,b){let e=0,rev=0,sp=0,np=0,wc=0;
 for(let h=a;h<=b;h++){const p=price[h];if(p==null)continue;np++;sp+=p;let g=0;
  fs.forEach(f=>{const v=f.P[h];if(v!=null){g+=v;if(f.lay&&f.Fr[h]!=null)wc+=(f.Fr[h]-v)*p}});e+=g;rev+=g*p}
 return{base:np?sp/np:null,cap:e>0?rev/e:null,e,wc,np}}
function farmCap(f){const pr=MK&&f.zone&&MK.prices[f.zone];if(!pr)return{cap:null,wc:null};const s=capStats([f],pr,0,N0);return{cap:s.cap,wc:f.lay?s.wc:null}}
function pathOf(v,x,y,a,b){let d="",on=false;for(let h=a;h<=b;h++){const q=v[h];if(q==null){on=false;continue}d+=(on?"L":"M")+x(h).toFixed(1)+","+y(q).toFixed(1);on=true}return d}
function tsSVG(W,H,n,series,lo,hi,now,lbl){const x=i=>3+(W-6)*i/Math.max(1,n-1),y=v=>H-2-(H-6)*(Math.min(hi,Math.max(lo,v))-lo)/((hi-lo)||1);
 let s="<line class='ax' x1='3' x2='"+(W-3)+"' y1='"+(H-2)+"' y2='"+(H-2)+"'/><text class='tl' x='3' y='9'>"+lbl+"</text>";
 if(lo<0)s+="<line class='ax' stroke-dasharray='2 3' x1='3' x2='"+(W-3)+"' y1='"+y(0)+"' y2='"+y(0)+"'/><text class='tl' x='"+(W-3)+"' y='"+(y(0)-3)+"' text-anchor='end'>0</text>";
 if(now!=null)s+="<line class='nowl' x1='"+x(now)+"' x2='"+x(now)+"' y1='0' y2='"+H+"'/>";
 series.forEach(se=>{const b=now==null?n-1:now;s+="<path class='ln "+(se.cls||"")+"' d='"+pathOf(se.v,x,y,0,b)+"'/>";if(now!=null&&now<n-1)s+="<path class='ln fc "+(se.cls||"")+"' d='"+pathOf(se.v,x,y,now,n-1)+"'/>"});
 return s}
const axl=(W,H,a,m,b,mx)=>"<text class='tl' x='3' y='"+(H+11)+"'>"+a+"</text>"+(m?"<text class='tl' x='"+mx+"' y='"+(H+11)+"' text-anchor='middle'>"+m+"</text>":"")+"<text class='tl' x='"+(W-3)+"' y='"+(H+11)+"' text-anchor='end'>"+b+"</text>";
function modSum(fs,k){let s=0,n=0;fs.forEach(f=>{if(f.P[k]!=null){s+=f.P[k];n++}});return n?s:null}
function market(){series();const el=$("mkt");TIPS=[];
 if(!MK){el.innerHTML="<div class='feednote'><b>No market data yet.</b> The pipeline adds it on its next run with a real forecast source.</div>";return}
 const zinst=z=>F.filter(f=>f.zone===z).reduce((a,f)=>a+f.inst,0),zones=Object.keys(MK.prices).filter(z=>F.some(f=>f.zone===z&&(inC(f,S.c)))).sort((a,b)=>zinst(b)-zinst(a));
 let lo=0,hi=50;zones.forEach(z=>MK.prices[z].forEach(p=>{if(p!=null){lo=Math.min(lo,p);hi=Math.max(hi,p)}}));hi=Math.ceil(hi/50)*50;lo=Math.floor(lo/50)*50;
 let h="<div class='feednote srcnote'><b>Market tab.</b> Day-ahead prices and actual generation: <a href='https://transparency.entsoe.eu' style='color:inherit'>ENTSO-E Transparency Platform</a>. Offshore output from the "+MODELS[S.fm]+" model on the forecast (change it in Compare). "+(MK.restricted_zones.length?"Not shown because their price licence is private use only: "+MK.restricted_zones.length+" zones ("+MK.restricted_zones.join(", ")+"). ":"")+(MK.price_source&&MK.price_source.GB?"GB (UK) has no day-ahead auction series in open data: its line is the Elexon Market Index, the volume-weighted price of half-hourly wholesale trades on APX / EPEX SPOT (third-party data supplied via Elexon BMRS). It appears about an hour after delivery, never for tomorrow, and differs from an auction result; TB2 / TB4 on it cover the hours traded so far. ":"UK has no day-ahead price in this source yet.")+fxNote(MK.fx)+"</div>";
 const pz=(MK.core_zones||Object.keys(MK.prices)).filter(z=>MK.prices[z]&&ZONEFLAG[z]),tAv=pz.some(z=>MK.prices[z].slice(N0+1).some(v=>v!=null));S.prng=S.prng||"past";if(S.prng==="next"&&!tAv)S.prng="past";
 const SZ=selZones();if(SZ&&!SZ.size)h+="<div class='feednote'>No day-ahead price data for "+S.c+" in this source yet; showing Europe.</div>";else if(SZ)h+="<div class='feednote'>"+S.c+"'s bidding zones are highlighted"+([...SZ].some(z=>MK.prices[z])?"":" (none of them has an openly licensed price)")+". Pick World or Europe in the selector to clear.</div>";
 h+="<div class='card' style='cursor:default'><h3>Day-ahead prices by zone<span class='seg'><button data-pr='past' class='"+(S.prng==="past"?"on":"")+"'>Last 24 h</button><button data-pr='next' "+(tAv?"":"disabled title='Published around midday'")+" class='"+(S.prng==="next"?"on":"")+"'>Tomorrow</button></span></h3><svg class='cmp' id='cmpPrice'></svg><div class='mut' style='font-size:12px'>Hourly averages of the 15-minute day-ahead auction, €/MWh. Hover to rank all zones for one hour; the line under the cursor is highlighted.</div></div>";
 const hz=Object.keys(MK.prices);
 S.hms=S.hms||"m";h+="<div class='card' style='cursor:default'><h3>All bidding zones · "+(S.prng==="next"?"tomorrow":"last 24 h")+"<span class='seg'><span class='mut' style='font-size:12px;font-weight:400;margin-right:6px'>"+hz.length+" zones · sort by</span><button data-hs='m' class='"+(S.hms==="m"?"on":"")+"'>Mean</button><button data-hs='tb2' class='"+(S.hms==="tb2"?"on":"")+"'>TB2</button><button data-hs='tb4' class='"+(S.hms==="tb4"?"on":"")+"'>TB4</button>"+(MK.spark?"<button data-hs='sp' class='"+(S.hms==="sp"?"on":"")+"'>Spark</button>":"")+"</span></h3><svg class='hm' id='hmPrice'></svg><div class='mut' style='font-size:12px' id='hmPriceL'></div><div class='mut' style='font-size:12px'><b>TB2 / TB4</b> (€/MWh): mean of the 2 / 4 most expensive hours minus mean of the 2 / 4 cheapest in the 24 h shown, a first indication of what a 1-hour / 2-hour battery could capture from one cycle a day (before losses; trading the 15-minute auction gives a bit more than hourly averages). Hourly day-ahead price per zone; the colour scale tops out at the 97th percentile so a few spikes don't wash out the rest. Hover a cell for its value and rank in that hour."+(MK.spark?"<br><b>Spark</b> (€/MWh): mean of the 4 most expensive hours minus the gas cost of a 55 % efficient gas plant at the TTF front-month price"+(MK.spark.carbon?" incl. carbon":", fuel only (no carbon), so it reads higher than a clean spark spread")+", the same reference cost in every zone (local gas premia and oil-indexed supply are not included). Red = below the reference cost. Gas reference: TTF front-month futures (ICE Endex) via Yahoo Finance; only derived spreads are shown.":"")+"</div></div>";
 h+="<div id='capbox'>"+capSection()+"</div>";
 const act=MK.actual_offshore||{},cs=Object.keys(act).filter(c=>HN[c]&&(!S.c||CCN[c]===S.c)).sort((a,b)=>sum(CCN[b])-sum(CCN[a]));
 if(cs.length){h+="<h2>Model check: modelled vs actual offshore output <span class='mut' style='font:13px system-ui'>· last 24 h; actual is the whole national fleet, the model only covers farms in the dataset; countries where the dataset has most of the fleet</span></h2><div class='grid'>";
  cs.forEach(c=>{const fs=F.filter(f=>f.c===CCN[c]),a=act[c],mod=[...Array(NP)].map((_,k)=>modSum(fs,k));let sm=0,sa=0;
   for(let k=0;k<NP;k++)if(mod[k]!=null&&a[k]!=null){sm+=mod[k];sa+=a[k]}
   const hv=Math.max(1,...mod.filter(v=>v!=null),...a.filter(v=>v!=null)),i=TIPS.push(k=>CCN[c]+" · "+dl(k)+" · modelled "+fmt(mod[k])+" · actual "+fmt(a[k]))-1;
   h+="<div class='card'><h3>"+CCN[c]+"<span>"+(sa>0?(sm>=sa?"+":"")+(100*(sm/sa-1)).toFixed(0)+"% vs actual":"–")+"</span></h3><div class='v mut'><span style='color:var(--acc)'>━</span> modelled avg "+fmt(sm/NP)+" · <span style='color:var(--ink)'>━</span> actual avg "+fmt(sa/NP)+"<br>Model: "+fs.length+" farms, "+fmt(fs.reduce((q,f)=>q+f.inst,0))+" installed in the dataset</div><svg class='mk' data-t='"+i+"' data-n='"+NP+"' data-c='"+c+"' data-hi='"+hv+"'></svg></div>"});
  h+="</div>"}
 el.innerHTML=h;
 CMP.cmpPrice={series:pz.map(z=>({id:z,label:z,flag:ZONEFLAG[z],v:MK.prices[z]})),a:S.prng==="past"?0:N0+1,b:S.prng==="past"?N0:NT-1,fmt:v=>Math.round(v)+"",H:Math.max(290,pz.length*15+50),sel:selZones()};cmpRender("cmpPrice");HM.hmPrice={sel:selZones(),zones:Object.keys(MK.prices),a:S.prng==="past"?0:N0+1,b:S.prng==="past"?N0:NT-1,sort:S.hms};hmRender("hmPrice");capDraw();makeSortable($("mkt"));
 el.querySelectorAll("svg.mk").forEach(sv=>{const W=sv.clientWidth||220,Hh=70;sv.setAttribute("viewBox","0 0 "+W+" "+(Hh+12));
  {const c=sv.dataset.c,fs=F.filter(f=>f.c===CCN[c]),mod=[...Array(NP)].map((_,k)=>modSum(fs,k));
   sv.innerHTML=tsSVG(W,Hh,NP,[{v:act[c],cls:"act"},{v:mod,cls:""}],0,+sv.dataset.hi,null,fmt(+sv.dataset.hi))+axl(W,Hh,"−24 h","","now")}});
 }
$("mkt").onmousemove=e=>{const sv=e.target.closest("svg.mk,svg.mh");if(!sv){$("dtip").style.display="none";return}const n=+sv.dataset.n,r=sv.getBoundingClientRect(),k=Math.max(0,Math.min(n-1,Math.round((e.clientX-r.left)/r.width*(n-1)))),t=TIPS[+sv.dataset.t](k);if(t)dtip(e,t);else $("dtip").style.display="none"};
$("mkt").onmouseleave=()=>{$("dtip").style.display="none"};

export { ZN, axl, capStats, eur, farmCap, market, pathOf, pm, tsSVG };
