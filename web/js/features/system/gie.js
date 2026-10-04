/* System tab: gas storage and LNG (GIE AGSI+ / ALSI, data/gie.json) and the gas-supply card (ENTSOG).
   ES module (spec 3 step 2): imports name what this file needs from other modules, the export list at the end what it offers. */
import { S } from "../../core/data.js";
import { GAS, gasLoad, gname } from "../../core/gasdata.js";
import { system } from "./system.js";
// ---- GIE: storage fill (AGSI+) and LNG send-out (ALSI), web/data/gie.json ----
const GIE={d:null,loading:false};
function gieLoad(){if(GIE.d||GIE.loading)return;GIE.loading=true;fetch("data/gie.json",{cache:"no-cache"}).then(r=>r.ok?r.json():null).then(j=>{if(j){GIE.d=j;if(S.tab==="sys")system()}}).catch(()=>{})}
// fill % this year vs the same calendar days a year earlier, one axis (0-100 %)
function gieLines(rows,W,H){const last=rows[rows.length-1][0],y0=+last.slice(0,4),cut=new Date(Date.parse(last)-364*864e5).toISOString().slice(0,10);
 const now=rows.filter(r=>r[0]>cut),prev=rows.filter(r=>{const t=Date.parse(r[0])+365*864e5;return t>Date.parse(cut)&&t<=Date.parse(last)+864e5});
 const x0=Date.parse(cut),X=d=>34+(W-44)*(d-x0)/(364*864e5),Y=v=>6+(H-24)*(1-v/100),path=(a,sh)=>a.map((r,i)=>(i?"L":"M")+X(Date.parse(r[0])+sh).toFixed(1)+","+Y(r[1]).toFixed(1)).join("");
 let s="";for(const g of[0,25,50,75,100])s+="<line class='ax' x1='34' x2='"+(W-10)+"' y1='"+Y(g)+"' y2='"+Y(g)+"' stroke-dasharray='2 3'/><text class='tl' x='28' y='"+(Y(g)+3)+"' text-anchor='end'>"+g+"%</text>";
 for(let m=0;m<12;m+=2){const d=new Date(x0);d.setUTCMonth(d.getUTCMonth()+m,1);const xx=X(d.getTime());if(xx>34&&xx<W-10)s+="<text class='tl' x='"+xx+"' y='"+(H-4)+"' text-anchor='middle'>"+d.toLocaleString("en",{month:"short"})+"</text>"}
 s+="<path d='"+path(prev,365*864e5)+"' fill='none' stroke='var(--mut)' stroke-width='1.5' stroke-dasharray='4 3'/><path d='"+path(now,0)+"' fill='none' stroke='var(--m-gas)' stroke-width='2.2'/>";
 const L=now[now.length-1];s+="<circle cx='"+X(Date.parse(L[0]))+"' cy='"+Y(L[1])+"' r='3.5' fill='var(--m-gas)'/>";
 return"<svg viewBox='0 0 "+W+" "+H+"' style='width:100%;height:"+H+"px'>"+s+"</svg>"}
function gieCard(cc,label){gieLoad();if(!GIE.d)return"";const st=GIE.d.storage[cc],ln=GIE.d.lng[cc];if(!st&&!ln)return"";let h="<div class='card' style='cursor:default'><h3>Gas storage"+(ln?" and LNG":"")+" · "+label;
 if(st){const r=st.d,L=r[r.length-1],ly=r.find(q=>q[0]>=new Date(Date.parse(L[0])-365*864e5).toISOString().slice(0,10)),wk=r[Math.max(0,r.length-8)];
  h+="<span>"+L[1].toFixed(1)+"% full · "+(L[2]||0).toFixed(1)+" of "+(L[5]||0).toFixed(1)+" TWh</span></h3>";
  h+="<div class='v mut'>"+(ly?"A year ago "+ly[1].toFixed(1)+"% ("+(L[1]-ly[1]>=0?"+":"")+(L[1]-ly[1]).toFixed(1)+" pts)":"")+" · last 7 days "+(L[1]-wk[1]>=0?"+":"")+(L[1]-wk[1]).toFixed(1)+" pts · "+GIE.d.storage[cc].d.slice(-1)[0][0]+": injection "+Math.round(L[3]||0)+" GWh/d, withdrawal "+Math.round(L[4]||0)+" GWh/d</div>";
  h+=gieLines(r,940,150)+"<div class='mut' style='font-size:12px'><span style='color:var(--m-gas)'>━</span> last 12 months &nbsp; <span>┅</span> the year before · fill level of working gas volume</div>"}else h+="</h3>";
 if(ln){const r=ln.d,L=r[r.length-1],a=r.slice(-30).reduce((p,q)=>p+q[1],0)/Math.min(30,r.length);h+="<div class='v mut' style='margin-top:6px'><b style='color:var(--ink)'>LNG</b> send-out "+Math.round(L[1])+" GWh/d on "+L[0]+" (30-day avg "+Math.round(a)+")"+(L[2]!=null?" · tank inventory "+Math.round(L[2])+" GWh":"")+"</div>"}
 return h+"<div class='mut' style='font-size:12px;margin-top:4px'>Source: GIE AGSI+ / ALSI.</div></div>"}
function gieOverview(){gieLoad();if(!GIE.d||!GIE.d.storage.EU)return"";const rows=Object.entries(GIE.d.storage).filter(([k,v])=>k!=="EU"&&(v.d.slice(-1)[0][5]||0)>1).map(([k,v])=>({k,n:v.n,L:v.d.slice(-1)[0]})).sort((a,b)=>b.L[5]-a.L[5]).slice(0,14);
 const E=GIE.d.storage.EU.d,L=E[E.length-1],ly=E.find(q=>q[0]>=new Date(Date.parse(L[0])-365*864e5).toISOString().slice(0,10));
 return"<div class='card' style='cursor:default'><h3>EU gas storage<span>"+L[1].toFixed(1)+"% full · "+L[2].toFixed(0)+" TWh on "+L[0]+(ly?" · a year ago "+ly[1].toFixed(1)+"%":"")+"</span></h3>"+gieLines(E,940,130)+
  "<table class='mixtab'><thead><tr><th>Country</th><th style='width:45%'>Fill level</th><th>Full</th><th>Capacity</th></tr></thead><tbody>"+rows.map(r=>"<tr><td>"+r.n+"</td><td><i style='display:block;height:8px;width:"+r.L[1].toFixed(1)+"%;background:var(--m-gas);border-radius:0 3px 3px 0'></i></td><td>"+r.L[1].toFixed(1)+"%</td><td>"+r.L[5].toFixed(0)+" TWh</td></tr>").join("")+
  "</tbody></table><div class='mut' style='font-size:12px'>Largest storage countries by working gas volume. Source: GIE AGSI+.</div></div>"}
function gasCard(cc){gasLoad();if(!GAS.d)return"";const g=GAS.d.countries[cc==="GB"?"UK":cc];if(!g)return"";const n=GAS.d.days.length;
 const rows=Object.entries(g).map(([s,v])=>({s,last:v[n-1]||0,avg:v.reduce((a,b)=>a+b,0)/n})).filter(r=>r.avg>0.5||r.last>0.5).sort((a,b)=>b.last-a.last);if(!rows.length)return"";
 const tot=rows.reduce((a,r)=>a+r.last,0),mx=Math.max(...rows.map(r=>Math.max(r.last,r.avg)));
 return"<div class='card' style='cursor:default'><h3>Gas supply into the system<span>"+Math.round(tot)+" GWh/d on "+GAS.d.days[n-1]+"</span></h3><table class='mixtab'><thead><tr><th>Source</th><th style='width:45%'></th><th>Last day</th><th>8-day avg</th></tr></thead><tbody>"+
  rows.map(r=>"<tr><td>"+(r.s==="LNG"||r.s==="Production"||r.s==="Import"?r.s:gname(r.s))+"</td><td><i style='display:block;height:8px;width:"+(100*r.last/mx).toFixed(1)+"%;background:var(--m-gas);border-radius:0 3px 3px 0'></i></td><td>"+Math.round(r.last)+" GWh/d</td><td>"+Math.round(r.avg)+"</td></tr>").join("")+
  "</tbody></table><div class='mut' style='font-size:12px'>Daily entries into the national transmission system by origin (pipeline from neighbouring countries, LNG terminals, domestic production), ENTSOG. Includes gas in transit to other countries. 1 GWh/d ≈ 42 MW average.</div></div>"}

export { gasCard, gieCard, gieOverview };
