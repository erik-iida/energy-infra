/* System tab: generation mix, load, residual load, prices and cross-border flows per country; country cards and comparison chart.
   ES module (spec 3 step 2): imports name what this file needs from other modules, the export list at the end what it offers. */
import { COUNTRIES, GROUPS, S, isReg } from "../../core/data.js";
import { $, fmt, pm } from "../../core/util.js";
import { MK, N0, NP, NT, dl, hl } from "../../core/feed.js";
import { rangeData } from "../../core/range.js";
import { MIXC, SYS, SYSN, sysData } from "../../core/sysdata.js";
import { axl, dtip, pathOf, tsSVG } from "../../core/chart.js";
import { flagHTML } from "../../core/flags.js";
import { keepScroll, makeSortable } from "../../core/table.js";
import { CMP, cmpRender } from "../../core/cmp.js";
import { go, registerTab } from "../../core/router.js";
import { gasCard, gieCard, gieOverview } from "./gie.js";
/* ---------- System tab: generation mix, load, prices, cross-border flows ---------- */
// stack order chosen so every adjacent pair passes the colour-vision checks in light and dark mode
let STIPS=[];S.sys=null;
const v1=v=>v==null||!isFinite(v)?"–":fmt(v);
const RANGES=[[24,"24 h"],[72,"72 h"],[168,"1 wk"],[720,"1 mo"]];   // System detail charts: hours shown (24 = the feed, longer = store export)
const RANGE={key:null,data:null,missing:false,busy:null};              // the one loaded range (country | hours)
// technologies hidden in the generation mix chart (click the legend); kept per browser
const SYSHIDE=new Set((()=>{try{return JSON.parse(localStorage.getItem("sys-hide")||"[]")}catch(e){return[]}})());
function sysHideSave(){try{localStorage.setItem("sys-hide",JSON.stringify([...SYSHIDE]))}catch(e){}}
function stackSVG(D,W,H){const n=D.n||NP,PR=D.prices||MK.prices,x=i=>3+(W-6)*i/(n-1),vis=MIXC.filter(([k])=>!SYSHIDE.has(k));let mx=1;for(let h=0;h<n;h++)mx=Math.max(mx,h<=D.last?vis.reduce((a,[k])=>a+(D.mix[k][h]||0),0):0,D.load&&!SYSHIDE.has("load")?D.load[h]||0:0);mx=Math.ceil(mx/1000)*1000;
 const y=v=>H-2-(H-6)*v/mx;let s="<line class='ax' x1='3' x2='"+(W-3)+"' y1='"+(H-2)+"' y2='"+(H-2)+"'/><text class='tl' x='3' y='9'>"+fmt(mx)+"</text>";
 const base=Array(n).fill(0);
 MIXC.forEach(([k])=>{if(SYSHIDE.has(k))return;const top=base.map((b,h)=>b+D.mix[k][h]);if(top.every((t,h)=>t===base[h]))return;
  let d="M"+x(0)+","+y(top[0]);for(let h=1;h<=D.last;h++)d+="L"+x(h).toFixed(1)+","+y(top[h]).toFixed(1);for(let h=D.last;h>=0;h--)d+="L"+x(h).toFixed(1)+","+y(base[h]).toFixed(1);
  s+="<path d='"+d+"Z' style='fill:var(--m-"+k+");stroke:var(--panel);stroke-width:1'/>";top.forEach((t,h)=>base[h]=t)});
 if(D.last<n-1)s+="<rect x='"+x(D.last).toFixed(1)+"' y='0' width='"+(x(n-1)-x(D.last)).toFixed(1)+"' height='"+(H-2)+"' fill='var(--line)' opacity='.3'/><text class='tl' x='"+(x(n-1)-4)+"' y='"+(H-8)+"' text-anchor='end'>generation not yet reported</text>";
 if(D.load&&!SYSHIDE.has("load"))s+="<path class='ln' style='stroke:var(--ink);stroke-width:2' d='"+pathOf(D.load,x,y,0,n-1)+"'/>";
 if(D.res&&!SYSHIDE.has("res")&&D.res.some(v=>v!=null))s+="<path class='ln' style='stroke:var(--ink);stroke-width:1.6;stroke-dasharray:5 4' d='"+pathOf(D.res,x,y,0,n-1)+"'/>";
 // day-ahead price on a right-hand axis: the country's bidding zones (first bold, others thin), same hours as the stack
 const pzs=!SYSHIDE.has("price")&&PR?(D.zones||[]).filter(z=>PR[z]&&PR[z].slice(0,n).some(v=>v!=null)):[];
 if(pzs.length){const pv=pzs.flatMap(z=>PR[z].slice(0,n)).filter(v=>v!=null),plo=Math.min(0,...pv),phi=Math.max(1,...pv)*1.05,yp=v=>H-2-(H-6)*(v-plo)/(phi-plo);
  s+="<text class='tl' x='"+(W-3)+"' y='9' text-anchor='end' fill='var(--acc)'>"+Math.round(phi)+" €/MWh</text>"+(plo<0?"<text class='tl' x='"+(W-3)+"' y='"+(yp(0)-3)+"' text-anchor='end' fill='var(--acc)'>0</text>":"");
  pzs.forEach((z,j)=>{s+="<path class='ln' style='stroke:var(--acc);stroke-width:"+(j?1.2:2)+";stroke-opacity:"+(j?.7:1)+"' d='"+pathOf(PR[z],x,yp,0,n-1)+"'/>"})}
 return s}
function sysCard(D){const h=D.last,g=D.gen[h]||1,pz=D.zones.map(z=>MK.prices[z]&&MK.prices[z][N0]).filter(v=>v!=null);
 let bar="",xo=0;MIXC.forEach(([k])=>{const w=100*D.mix[k][h]/g;if(w>0.3){bar+="<span style='left:"+xo+"%;width:calc("+w+"% - 2px);background:var(--m-"+k+")'></span>";xo+=w}});
 const ni=D.net&&D.net[h];
 return"<div class='card"+(D.c===S.sys?" on":"")+"' data-s='"+D.c+"'><h3><span style='display:flex;align-items:center;gap:6px'>"+flagHTML(D.c,7)+(SYSN[D.c]||D.c)+"</span><span>"+(pz.length?pz.map(v=>v.toFixed(0)).join(" / ")+" €/MWh":"price n/a")+"</span></h3><div class='v mut'>Load "+v1(D.load&&D.load[h])+(D.res&&D.res[h]!=null?" · residual "+v1(D.res[h]):"")+" · renewables "+(100*D.ren[h]/g).toFixed(0)+"% of generation<br>"+(ni==null?"flows n/a":ni>=0?"Importing "+fmt(ni):"Exporting "+fmt(-ni))+" · "+(D.lag?"<b>data "+(D.lag+NP-1-h)+" h old</b> (TSO reports late)":"at "+hl(h))+"</div><div class='mixbar'>"+bar+"</div></div>"}
function system(){const el=$("sys");STIPS=[];
 if(!MK||!Object.keys(SYS).length){el.innerHTML="<div class='feednote'><b>No system data yet.</b> It arrives with the next pipeline run.</div>";return}
 const grp=GROUPS[S.c]?new Set(GROUPS[S.c]):null;const all=Object.keys(SYS).filter(k=>!grp||grp.has(SYSN[k])).map(sysData).filter(Boolean).sort((a,b)=>(b.load?b.load[b.last]:b.gen[b.last])-(a.load?a.load[a.last]:a.gen[a.last]));
 const csel=S.c&&!isReg(S.c)?Object.keys(SYSN).find(k=>SYSN[k]===S.c):null;
 if(csel&&all.some(d=>d.c===csel))S.sys=csel;
 if(!S.sys||!all.some(d=>d.c===S.sys))S.sys=all[0]&&all[0].c;
 const D24=all.find(d=>d.c===S.sys);
 // detail block data: the feed's 24 h, or the longer range from the store export (core/range.js), loaded on demand
 S.sysRange=S.sysRange||24;const feedR={n:NP,pn:NT,now:N0,tl:dl,hl,prices:MK.prices,from:"−24 h",to:"now",title:"last 24 h",short:"24 h"};
 let D=D24?Object.assign({},D24,{R:feedR}):null;
 if(D24&&S.sysRange!==24){const key=D24.c+"|"+S.sysRange;
  if(RANGE.key===key&&RANGE.data){const X=RANGE.data;D=Object.assign({},X,{R:{n:X.n,pn:X.n,now:null,tl:X.tl,hl:X.hl,prices:X.prices,from:X.from,to:X.to,title:"last "+RANGES.find(r=>r[0]===S.sysRange)[1]+" · "+X.from+" to "+X.to+" (store export, hourly means"+(D24.zones.length>1?", "+D24.zones.join(" + "):"")+")",short:RANGES.find(r=>r[0]===S.sysRange)[1]}})}
  else if(RANGE.key===key&&RANGE.missing)D.R=Object.assign({},feedR,{missing:true});
  else{D.R=Object.assign({},feedR,{loading:RANGES.find(r=>r[0]===S.sysRange)[1]});
   if(RANGE.busy!==key){RANGE.busy=key;rangeData(D24.c,D24.zones,S.sysRange).then(X=>{RANGE.key=key;RANGE.data=X;RANGE.missing=!X;RANGE.busy=null;if(S.tab==="sys")keepScroll(system)}).catch(()=>{RANGE.key=key;RANGE.data=null;RANGE.missing=true;RANGE.busy=null;if(S.tab==="sys")keepScroll(system)})}}}
 let h=(S.c&&S.c!=="Europe"&&!csel&&!grp?"<div class='feednote'>No system data for "+S.c+" in this source yet; showing the European countries covered.</div>":"")+"<div class='feednote srcnote'><b>System tab.</b> Generation, load, cross-border physical flows and day-ahead prices: <a href='https://transparency.entsoe.eu' style='color:inherit'>ENTSO-E Transparency Platform</a> (actual generation per production type, actual load, physical flows, day-ahead auction). Last 24 h, hourly averages. Flows: positive = import. Great Britain: Contains BMRS data © Elexon Limited copyright and database right "+new Date().getFullYear()+" (national demand plus the embedded wind and solar estimate). GB price: Market Index Data, the volume-weighted price of half-hourly trades on APX / EPEX SPOT supplied via Elexon BMRS (not an auction result; published after delivery; converted to EUR at the ECB rate). Ireland: generation ENTSO-E, load Supported by EirGrid Group Data.</div>";
 const mark0=h.length;
 h+="<h2>Countries <span class='mut' style='font:13px system-ui'>· latest hour; bar = generation mix; click for detail</span></h2><div class='grid'>"+all.map(sysCard).join("")+"</div>";
 h+="<div class='mixleg' title='Click a technology to hide or show it in the generation mix chart'>"+MIXC.map(([k,n])=>"<span data-k='"+k+"' class='"+(SYSHIDE.has(k)?"off":"")+"'><i style='background:var(--m-"+k+")'></i>"+n+"</span>").join("")+"<span data-k='load' class='"+(SYSHIDE.has("load")?"off":"")+"'><i style='background:var(--ink);height:2px'></i>Load</span><span data-k='res' class='"+(SYSHIDE.has("res")?"off":"")+"'><i style='height:0;border-top:2px dashed var(--ink)'></i>Residual load</span><span data-k='price' class='"+(SYSHIDE.has("price")?"off":"")+"'><i style='background:var(--acc);height:2px'></i>Day-ahead price (right axis)</span>"+(SYSHIDE.size?"<a class='mixall'>show all</a>":"")+"</div>";
 S.tcT=S.tcT||"woff";S.offm=S.offm||"gen";const TN=Object.fromEntries(MIXC.map(([k,n])=>[k,n]));TN.res="Residual load";const resM=S.tcT==="res",om=resM&&S.offm==="gen"?"load":S.offm,offc=all.filter(d=>resM?d.res&&d.res.some(v=>v!=null):d.mix[S.tcT].some(v=>v>0));
 h+="<div class='card' style='cursor:default'><h3><span style='display:flex;align-items:center;gap:8px'>Compare <select id='tcT' style='width:auto;padding:3px 6px;font-size:13px'>"+MIXC.map(([k,n])=>"<option value='"+k+"'"+(k===S.tcT?" selected":"")+">"+n+"</option>").join("")+"<option value='res'"+(S.tcT==="res"?" selected":"")+">Residual load (load − wind − solar)</option></select> across countries</span><span class='seg big'><button data-om='gen' class='"+(S.offm==="gen"?"on":"")+"'>% of generation</button><button data-om='load' class='"+(S.offm==="load"?"on":"")+"'>% of consumption</button><button data-om='mw' class='"+(S.offm==="mw"?"on":"")+"'>MW</button></span></h3>"+(offc.length?"<svg class='cmp' id='cmpOff'></svg>":"<div class='mut'>No country in this selection has "+TN[S.tcT].toLowerCase()+" output in the last 24 h.</div>")+"<div class='mut' style='font-size:12px'>"+TN[S.tcT]+(resM?" (load minus wind and solar)":" output")+" "+(om==="mw"?"in MW":om==="gen"?"as a share of national generation":"as a share of load (consumption)")+", last 24 h, hourly"+(resM&&S.offm==="gen"?" (shown against load: residual load has no generation share)":"")+". Hours a TSO has not reported yet are left blank, not drawn as zero. Countries follow the selector (pick a group such as CEE / SEE to narrow it). Hover to rank them for one hour.</div></div>";
 const mark1=h.length;
 if(D){const lh=D.last,g=D.gen[lh]||1,R=D.R;
  h+="<h2 style='display:flex;align-items:center;gap:10px;flex-wrap:wrap'>"+flagHTML(D.c,9)+" "+(SYSN[D.c]||D.c)+" <span class='mut' style='font:13px system-ui'>· "+R.title+"</span><span class='seg' style='margin-left:auto;font:13px system-ui'>"+RANGES.map(([hrs,lb])=>"<button data-rg='"+hrs+"' class='"+(S.sysRange===hrs?"on":"")+"'>"+lb+"</button>").join("")+"</span></h2>"+(R.loading?"<div class='feednote'>Loading "+R.loading+" from the data store export… (showing the last 24 h meanwhile)</div>":"")+(R.missing?"<div class='feednote'>No store export for "+(SYSN[D.c]||D.c)+" yet; showing the last 24 h.</div>":"");
  const i1=STIPS.push(k=>(SYSN[D.c]||D.c)+" · "+R.tl(k)+(k>D.last?" · generation not yet reported (TSO lag)"+(D.load?" · load "+v1(D.load[k]):""):" · generation "+fmt(D.gen[k])+(D.load?" · load "+v1(D.load[k]):"")+(D.res&&D.res[k]!=null?" · residual load "+fmt(D.res[k]):""))+((D.zones||[]).some(z=>R.prices[z]&&R.prices[z][k]!=null)?" · price "+D.zones.filter(z=>R.prices[z]&&R.prices[z][k]!=null).map(z=>(D.zones.length>1?z+" ":"")+pm(R.prices[z][k])).join(", "):"")+(k>D.last?"":" · ")+(k>D.last?[]:MIXC.filter(([c])=>D.mix[c][k]>0).sort((p,q)=>D.mix[q[0]][k]-D.mix[p[0]][k]).map(([c,n])=>n+" "+fmt(D.mix[c][k]))).join(", "))-1;
  h+="<div class='syswrap'><div class='card wide'><h3>Generation mix, load and price<span>"+fmt(D.gen[lh])+" generation"+(D.load?" · "+v1(D.load[lh])+" load":"")+"</span></h3><svg class='sx' data-t='"+i1+"' data-n='"+R.n+"' data-k='mix'></svg>"+"<div class='mut' style='font-size:12px;display:flex;justify-content:space-between'><span>"+R.from+"</span><span>"+R.to+"</span></div>";
  h+="<table class='mixtab'><thead><tr><th>Source</th><th>Now</th><th>Share now</th><th>"+R.short+" avg</th><th>"+R.short+" energy</th></tr></thead><tbody>"+MIXC.filter(([k])=>D.mix[k].some(v=>v>0)).sort((p,q)=>D.mix[q[0]][lh]-D.mix[p[0]][lh]).map(([k,n])=>{const a=D.mix[k].slice(0,lh+1),av=a.reduce((p,q)=>p+q,0)/a.length;return"<tr><td><i style='background:var(--m-"+k+")'></i>"+n+"</td><td>"+fmt(D.mix[k][lh])+"</td><td>"+(100*D.mix[k][lh]/g).toFixed(1)+"%</td><td>"+fmt(av)+"</td><td>"+(a.reduce((p,q)=>p+q,0)/1000).toFixed(1)+" GWh</td></tr>"}).join("")+"</tbody></table></div>";
  // residual load
  if(D.res&&D.res.some(v=>v!=null)){const rv=D.res.map((v,k)=>[v,k]).filter(q=>q[0]!=null),pk=rv.reduce((a,b)=>b[0]>a[0]?b:a),mn=rv.reduce((a,b)=>b[0]<a[0]?b:a);let rp=0,rk=0;for(let k=3;k<R.n;k++)if(D.res[k]!=null&&D.res[k-3]!=null&&D.res[k]-D.res[k-3]>rp){rp=D.res[k]-D.res[k-3];rk=k}
   const vs=[...Array(R.n)].map((_,k)=>k<=D.last&&D.load&&D.load[k]?100*(D.mix.won[k]+D.mix.woff[k]+D.mix.sol[k])/D.load[k]:null),vv=vs.filter(v=>v!=null);
   const i4=STIPS.push(k=>(SYSN[D.c]||D.c)+" · "+R.tl(k)+(D.res[k]==null?" · not yet reported":" · residual load "+fmt(D.res[k])+" · load "+v1(D.load[k])+" · wind "+fmt(D.mix.won[k]+D.mix.woff[k])+" · solar "+fmt(D.mix.sol[k])+" · wind+solar "+Math.round(vs[k])+"% of load"))-1;
   h+="<div class='card'><h3>Residual load<span>"+v1(D.res[lh])+" at "+R.hl(lh)+"</span></h3><svg class='sx' data-t='"+i4+"' data-n='"+R.n+"' data-k='res'></svg><div class='mut' style='font-size:12px;display:flex;justify-content:space-between'><span>"+R.from+"</span><span>"+R.to+"</span></div><div class='v mut'>Load minus wind and solar: what dispatchable plant, storage and imports have to cover. Peak "+fmt(pk[0])+" at "+R.hl(pk[1])+" · minimum "+fmt(mn[0])+" at "+R.hl(mn[1])+(rp>0?" · steepest 3 h rise "+fmt(rp)+" (to "+R.hl(rk)+")":"")+(vv.length?" · wind + solar "+Math.round(vv.reduce((a,b)=>a+b,0)/vv.length)+"% of load on average":"")+(mn[0]<0?" · negative = wind and solar above load (surplus to storage, export or curtailment)":"")+"</div></div>"}
  // prices
  const zs=D.zones.filter(z=>R.prices[z]);let lo=0,hi=50;zs.forEach(z=>R.prices[z].forEach(p=>{if(p!=null){lo=Math.min(lo,p);hi=Math.max(hi,p)}}));hi=Math.ceil(hi/50)*50;lo=Math.floor(lo/50)*50;
  const i2=STIPS.push(k=>R.tl(k)+(R.now!=null&&k>R.now?" (forecast)":"")+" · "+zs.map(z=>z+" "+pm(R.prices[z][k])).join(" · "))-1;
  h+="<div class='card'><h3>"+(zs.length===1&&zs[0]==="GB"?"Wholesale price (Market Index)":"Day-ahead price")+"<span>"+(zs.map(z=>z+" "+pm(R.prices[z][R.now!=null?R.now:lh])).join(" · ")||"n/a")+"</span></h3>"+(zs.length?"<svg class='sx' data-t='"+i2+"' data-n='"+R.pn+"' data-k='price' data-lo='"+lo+"' data-hi='"+hi+"'></svg><div class='mut' style='font-size:12px'>"+zs.map((z,j)=>"<span style='color:var("+(j?"--ink":"--prc")+")'>━</span> "+z).join(" &nbsp; ")+(R.now!=null?" · dashed = tomorrow once published":"")+"</div>":"<div class='mut'>No openly licensed price for this country's zones.</div>")+"</div>";
  // flows
  if(D.net){const now=D.nb.map(k=>[k,D.fl[k][lh]]).filter(q=>q[1]!=null).sort((a,b)=>b[1]-a[1]),mxf=Math.max(1,...now.map(q=>Math.abs(q[1])));
   const i3=STIPS.push(k=>R.tl(k)+" · net "+(D.net[k]==null?"–":(D.net[k]>=0?"import ":"export ")+fmt(Math.abs(D.net[k])))+" · "+D.nb.map(nb=>(D.fn[nb]||nb)+" "+(D.fl[nb][k]==null?"–":(D.fl[nb][k]>0?"+":"")+Math.round(D.fl[nb][k]))).join(", "))-1;
   h+="<div class='card'><h3>Cross-border physical flows<span>"+(D.net[lh]>=0?"net import ":"net export ")+fmt(Math.abs(D.net[lh]))+"</span></h3><div class='flows'>"+now.map(([k,v])=>"<div class='fr'><span class='fl'>"+(D.fn[k]||k)+"</span><span class='fb'><b style='"+(v>=0?"left:50%;width:"+(50*v/mxf)+"%;background:var(--imp)":"right:50%;width:"+(50*-v/mxf)+"%;background:var(--exp)")+"'></b></span><span class='fv'>"+(v>0?"+":"")+fmt(v).replace(" MW","")+" MW</span></div>").join("")+"</div><div class='mut' style='font-size:12px;margin:6px 0 2px'><span style='color:var(--imp)'>■</span> import · <span style='color:var(--exp)'>■</span> export · at "+R.hl(lh)+". Net import, "+R.short+":</div><svg class='sx' data-t='"+i3+"' data-n='"+R.n+"' data-k='net'></svg></div>"}
  h+="</div>"}
 if(csel&&D&&D.c===csel)h=h.slice(0,mark0)+h.slice(mark1)+h.slice(mark0,mark1);  // a country picked in the selector: its generation mix and load first
 const gh=(D?gieCard(D.c.toUpperCase(),SYSN[D.c]||D.c)+gasCard(D.c.toUpperCase()):"")+gieOverview();
 if(gh)h+="<h2>Gas <span class='mut' style='font:13px system-ui'>· storage, LNG and supply"+(D?" for "+(SYSN[D.c]||D.c)+", then the EU":"")+"</span></h2>"+gh;
 el.innerHTML=h;makeSortable(el);
 if(offc.length){CMP.cmpOff={series:offc.map(d=>{const w=resM?d.res:d.mix[S.tcT],lr=resM?d.last:d.lastRep[S.tcT];return{id:d.c,label:SYSN[d.c]||d.c,flag:d.c,v:w.map((v,hh)=>{if(v==null)return null;if(om==="mw")return hh<=lr?v:null;if(hh>d.last)return null;const den=om==="gen"?d.gen[hh]:(d.load&&d.load[hh]);return !den?null:100*v/den})}}),a:0,b:Math.max(...offc.map(d=>om==="mw"&&!resM?Math.max(d.last,d.lastRep[S.tcT]):d.last)),fmt:om==="mw"?(v=>fmt(v)):(v=>Math.round(v)+"%"),zero:true,H:Math.max(260,offc.length*16+40),right:150};cmpRender("cmpOff")}
 const R=D?D.R:null;
 el.querySelectorAll("svg.sx").forEach(sv=>{const W=sv.clientWidth||400,k=sv.dataset.k,Hh=k==="mix"?180:70;sv.setAttribute("viewBox","0 0 "+W+" "+(Hh+(k==="mix"?0:12)));sv.style.height=(Hh+(k==="mix"?0:12))+"px";
  if(k==="mix")sv.innerHTML=stackSVG(D,W,Hh);
  else if(k==="res"){const rv=D.res.filter(v=>v!=null),hi=Math.max(1000,Math.ceil(Math.max(...rv)/1000)*1000),lo=Math.min(0,Math.floor(Math.min(...rv)/1000)*1000);sv.innerHTML=tsSVG(W,Hh,R.n,[{v:D.res,cls:""}],lo,hi,null,fmt(hi))}
  else if(k==="price"){const zs=D.zones.filter(z=>R.prices[z]);sv.innerHTML=tsSVG(W,Hh,R.pn,zs.map((z,j)=>({v:R.prices[z],cls:j?"act":"pr"})),+sv.dataset.lo,+sv.dataset.hi,R.now,sv.dataset.hi+" €/MWh")+(R.now!=null?axl(W,Hh,"−24 h","now","+24 h",3+(W-6)*R.now/(R.pn-1)):axl(W,Hh,R.from,"",R.to))}
  else{const m=Math.max(100,...D.net.filter(v=>v!=null).map(Math.abs));const hi=Math.ceil(m/500)*500;sv.innerHTML=tsSVG(W,Hh,R.n,[{v:D.net,cls:""}],-hi,hi,null,"+"+fmt(hi))+axl(W,Hh,R.from,"",R.to)}});
}
$("sys").onchange=e=>{if(e.target.id==="tcT"){S.tcT=e.target.value;keepScroll(system)}};
$("sys").onclick=e=>{const b=e.target.closest("button[data-om]");if(b){S.offm=b.dataset.om;keepScroll(system);return}
 const rg=e.target.closest("button[data-rg]");if(rg){S.sysRange=+rg.dataset.rg;keepScroll(system);return}
 const lg=e.target.closest(".mixleg span[data-k]"),la=e.target.closest(".mixleg .mixall");if(lg||la){if(la)SYSHIDE.clear();else{const k=lg.dataset.k;SYSHIDE.has(k)?SYSHIDE.delete(k):SYSHIDE.add(k)}sysHideSave();keepScroll(system);return}const c=e.target.closest(".card[data-s]");if(c){S.sys=c.dataset.s;const nm=SYSN[c.dataset.s];if(nm&&COUNTRIES.includes(nm)){go(nm,null)}else system()}};
function sysVline(sv,k){let l=sv.querySelector("line.xh");const vb=sv.viewBox.baseVal,n=+sv.dataset.n,xx=3+(vb.width-6)*k/Math.max(1,n-1);
 if(!l){l=document.createElementNS("http://www.w3.org/2000/svg","line");l.setAttribute("class","xh");l.setAttribute("y1","0");l.setAttribute("pointer-events","none");sv.appendChild(l)}l.setAttribute("y2",vb.height);l.setAttribute("x1",xx);l.setAttribute("x2",xx)}
$("sys").onmousemove=e=>{const sv=e.target.closest("svg.sx");$("sys").querySelectorAll("svg.sx line.xh").forEach(l=>{if(l.parentNode!==sv)l.remove()});if(!sv){$("dtip").style.display="none";return}const n=+sv.dataset.n,r=sv.getBoundingClientRect(),k=Math.max(0,Math.min(n-1,Math.round((e.clientX-r.left)/r.width*(n-1)))),t=STIPS[+sv.dataset.t](k);sysVline(sv,k);if(t)dtip(e,t)};
$("sys").onmouseleave=()=>{$("dtip").style.display="none";$("sys").querySelectorAll("svg.sx line.xh").forEach(l=>l.remove())};
registerTab("sys",{el:"sys",render:system});

export { system };
