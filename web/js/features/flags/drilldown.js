/* Flags drill-down panel: the CET day behind a signal (generation, load, price, event shading, what else was unusual, neighbours); deep links #flags/<zone>/<metric>/<day>.
   ES module (spec 3 step 2): imports name what this file needs from other modules, the export list at the end what it offers. */
import { S } from "../../core/data.js";
import { $ } from "../../core/util.js";
import { dbJson } from "../../core/load.js";
import { dtip } from "../../core/chart.js";
import { ZONEFLAG, flagHTML } from "../../core/flags.js";
import { tab } from "../../core/router.js";
import { FL, flagsTab } from "./table.js";
/* ---------- Flags drill-down: click a fired signal to see the CET day behind it (spec 1, step 1) ---------- */
/* Hourly series: web/data/browse/ts/<zone>.json (the Data tab export). Older days: browse/flags/<day>.json (FLAG_DAYS kept). */
const FX={open:null,day:null,gone:null,cur:null,dj:{},ts:{},busy:{},X:null,rz:0};
const FXTECH=[["nuc","Nuclear"],["coal","Coal & lignite"],["bio","Biomass & waste"],["hyd","Hydro"],["oth","Other"],["gas","Gas"],["oil","Oil"],["won","Onshore wind"],["woff","Offshore wind"],["sol","Solar"]];
const FXPLAIN={
 tb4:"Average of the 4 priciest hours minus the 4 cheapest hours of the day: roughly what a 4-hour battery could earn from one charge-discharge cycle, before losses.",
 tb2:"Average of the 2 priciest hours minus the 2 cheapest hours of the day: roughly what a 2-hour battery could earn from one cycle, before losses.",
 neg_hours:"Hours with a day-ahead price below zero: generators paid to produce, usually because wind and solar exceeded what the zone could use or export.",
 baseload:"The average day-ahead price over all hours of the day.",
 top4:"The average of the 4 most expensive hours of the day.",
 price_max:"The most expensive hour of the day.",price_min:"The cheapest hour of the day.",
 cr_solar:"What solar earned per MWh (generation-weighted price) as a share of the day's average price. Low means solar produced mostly when power was cheap.",
 cr_wind_onshore:"What onshore wind earned per MWh (generation-weighted price) as a share of the day's average price. Low means the wind blew mostly in cheap hours.",
 cr_wind_offshore:"What offshore wind earned per MWh (generation-weighted price) as a share of the day's average price. Low means the wind blew mostly in cheap hours.",
 res_peak:"Residual load is demand minus wind and solar. Its peak is the hour in which the rest of the system (gas, coal, hydro, imports, storage) had to cover the most.",
 res_min:"The lowest residual load (demand minus wind and solar) of the day. Low or negative means wind and solar nearly covered, or exceeded, demand.",
 res_ramp3:"The steepest 3-hour rise in residual load (demand minus wind and solar), typically in the evening when solar fades and other plants must ramp up.",
 res_mean:"Average demand minus wind and solar: what the rest of the system had to cover.",
 import_share:"Net imports as a share of demand. High means the zone leaned on its neighbours; negative means it exported.",
 net_import:"Average net physical import over the zone's borders in the data store (negative = net export).",
 gen_wind_onshore:"Average onshore wind output over the day. Installed capacity barely changes over 90 days, so this percentile is also the capacity-factor percentile.",
 gen_wind_offshore:"Average offshore wind output over the day. Installed capacity barely changes over 90 days, so this percentile is also the capacity-factor percentile.",
 gen_solar:"Average solar output over the day. Installed capacity barely changes over 90 days, so this percentile is also the capacity-factor percentile.",
 vre_share:"Wind and solar generation as a share of demand.",
 gas_share:"Gas-fired generation as a share of all generation.",
 wind_share_load:"Onshore plus offshore wind output as a share of electricity demand (energy over the day).",
 solar_share_load:"Solar output as a share of electricity demand (energy over the day).",
 load_mean:"Average electricity demand over the day."};
const FXUNU=["baseload","price_max","price_min","neg_hours","tb4","gen_wind_onshore","gen_wind_offshore","gen_solar","wind_share_load","solar_share_load","vre_share","gas_share","load_mean","res_mean","res_peak","res_min","import_share","net_import"];
const FXCET=new Intl.DateTimeFormat("sv-SE",{timeZone:"Europe/Brussels",year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",hourCycle:"h23"});
function fxHash(){const o=FX.open;try{history.replaceState(null,"",location.pathname+location.search+(o?"#flags/"+encodeURIComponent(o.z)+"/"+o.m+"/"+o.d:"#flags"))}catch(e){}}
function fxFromHash(){const m=/^#flags(?:\/([^/]+)\/([a-z0-9_]+)\/(\d{4}-\d{2}-\d{2}))?$/.exec(location.hash);if(!m)return;
 if(m[1]){FX.open={z:decodeURIComponent(m[1]),m:m[2],d:m[3]};FX.day=m[3];FX.gone=null}tab("flg")}
function fxDayLbl(d,o){return new Date(d+"T12:00:00Z").toLocaleDateString("en-GB",Object.assign({day:"numeric",month:"short",timeZone:"UTC"},o||{}))}
function fxN(v,d){if(v==null||!isFinite(v))return"–";if(Math.abs(v)<.05)v=0;return v.toLocaleString("en",{maximumFractionDigits:d!=null?d:Math.abs(v)>=100?0:1})}
function fxPrep(t){const n=t.v.length?t.v[0].length:0,c={};t.cols.forEach((m,k)=>c[m.id]={m,v:t.v[k]});
 const day=[],hr=[];for(let i=0;i<n;i++){const s=FXCET.format(new Date((t.t0+i*t.step)*1000));day.push(s.slice(0,10));hr.push(s.slice(11,13))}
 return{t0:t.t0,step:t.step,n,c,day,hr}}
function fxLast(T,ids){let L=-1;ids.forEach(id=>{const v=T.c[id].v;for(let i=v.length-1;i>L;i--)if(v[i]!=null){L=i;break}});return L}
function fxWhen(T,i){const t=T.t0+i*T.step,s=FXCET.format(new Date(t*1000));return{lbl:fxDayLbl(s.slice(0,10))+" "+s.slice(11,13)+":00 CET",ago:Math.max(0,Math.round((Date.now()/1000-t-T.step)/3600))}}
function fxTicks(a,b){if(!(b>a)){b=a+1}const raw=(b-a)/4,p=Math.pow(10,Math.floor(Math.log10(raw))),st=[1,2,2.5,5,10].map(k=>k*p).find(s=>s>=raw);
 const out=[];for(let v=Math.floor(a/st)*st;v<b+st*.999;v+=st)out.push(+v.toFixed(10));return out}
function fxPath(v,x,y){let d="",pen=false;v.forEach((q,i)=>{if(q==null){pen=false;return}d+=(pen?"L":"M")+x(i).toFixed(1)+" "+y(q).toFixed(1);pen=true});return d}
/* which hours to shade for each signal type (spec table); a = hourly values of the CET day */
function fxEvents(m,P,R){const ix=(a,f)=>a.map((v,i)=>[v,i]).filter(q=>q[0]!=null&&f(q[0]));
 if(m==="tb4"||m==="tb2"){const k=m==="tb4"?4:2,s=ix(P,()=>1).sort((p,q)=>p[0]-q[0]||p[1]-q[1]);if(s.length<2*k)return{};
  const lo=s.slice(0,k),hi=s.slice(-k),mh=hi.reduce((a,q)=>a+q[0],0)/k,ml=lo.reduce((a,q)=>a+q[0],0)/k;
  return{hi:hi.map(q=>q[1]),lo:lo.map(q=>q[1]),hiL:k+" priciest hours",loL:k+" cheapest hours",spread:mh-ml,mh,ml,k}}
 if(m==="neg_hours")return{lo:ix(P,v=>v<0).map(q=>q[1]),loL:"price below zero"};
 if(m==="res_peak"||m==="res_min"){const s=ix(R,()=>1);if(!s.length)return{};s.sort((p,q)=>p[0]-q[0]);const i=(m==="res_peak"?s[s.length-1]:s[0])[1];
  return m==="res_peak"?{hi:[i],hiL:"highest residual load"}:{lo:[i],loL:"lowest residual load"}}
 if(m==="res_ramp3"){let b=null;for(let i=3;i<R.length;i++)if(R[i]!=null&&R[i-3]!=null&&(b==null||R[i]-R[i-3]>b[0]))b=[R[i]-R[i-3],i];
  return b?{hi:[b[1]-3,b[1]-2,b[1]-1,b[1]],hiL:"steepest 3-hour rise",rise:b[0]}:{}}
 return{}}
function fxSeries(T,idx){const pick=id=>T.c[id]?idx.map(i=>T.c[id].v[i]):null,has=a=>a&&a.some(v=>v!=null);
 const gen={},fc={};Object.values(T.c).forEach(c=>{const id=c.m.id;
  if(/^g\|.*\|gen$/.test(id)){const k=c.m.tech||"oth";gen[k]=gen[k]||idx.map(()=>null);idx.forEach((i,j)=>{if(c.v[i]!=null)gen[k][j]=(gen[k][j]||0)+Math.max(0,c.v[i])})}
  if(/^f\|/.test(id)&&["sol","won","woff"].includes(c.m.tech)){const k=c.m.tech;fc[k]=fc[k]||idx.map(()=>null);idx.forEach((i,j)=>{if(c.v[i]!=null)fc[k][j]=(fc[k][j]||0)+Math.max(0,c.v[i])})}});
 const ga=Object.values(gen).some(has),src=ga?"actual":Object.values(fc).some(has)?"forecast":null,G=ga?gen:fc;
 const st=FXTECH.filter(t=>G[t[0]]&&has(G[t[0]])).map(t=>({k:t[0],name:t[1],v:G[t[0]]}));
 let L=pick("l|actual"),Ls="actual";if(!has(L)){L=pick("l|national_demand");Ls="national demand"}if(!has(L)){L=pick("l|da_forecast");Ls="day-ahead forecast"}if(!has(L))L=null;
 const vre=j=>["won","woff","sol"].reduce((a,k)=>a+(G[k]&&G[k][j]!=null?G[k][j]:0),0);
 const R=L&&src?L.map((v,j)=>v==null||!st.some(s=>s.v[j]!=null)?null:v-vre(j)):null;
 const pc=T.c["p|price"];return{P:pick("p|price"),Pu:pc?pc.m.unit.replace("EUR","€").replace("GBP","£"):"€/MWh",st,src,L,Ls,R,
  gIds:Object.keys(T.c).filter(id=>/^g\|.*\|gen$/.test(id)),lIds:T.c["l|actual"]?["l|actual"]:[]}}
function fxChart(X,W){const ci=FX.charts.length,n=X.lab.length,sm=W<520,H=Math.round(Math.min(340,Math.max(230,W*.38))),ml=sm?40:56,mr=sm?42:58,mt=24,mb=26,iw=W-ml-mr,ih=H-mt-mb,bw=iw/n,fs=sm?10:11;
 const num=a=>(a||[]).filter(v=>v!=null),tot=X.lab.map((_,i)=>X.st.reduce((a,s)=>a+(s.v[i]||0),0));
 const Rax=X.showR?num(X.R):[];let lt=fxTicks(Math.min(0,...Rax),Math.max(1,...tot,...num(X.L),...Rax)*1.03);const y0=lt[0],y1=lt[lt.length-1];
 const pv=num(X.P).concat(X.refs.map(r=>r.v));let pt=pv.length?fxTicks(Math.min(0,...pv),Math.max(...pv)*1.03+.01):[0,1];const p0=pt[0],p1=pt[pt.length-1];
 const x=i=>ml+(i+.5)*bw,y=v=>mt+ih-(v-y0)/(y1-y0)*ih,yp=v=>mt+ih-(v-p0)/(p1-p0)*ih,mw=v=>Math.abs(v)>=1e4?fxN(v/1000,0)+"k":fxN(v,0);
 let s="<svg class='fxsv' data-c='"+ci+"' width='"+W+"' height='"+H+"' viewBox='0 0 "+W+" "+H+"' role='img' aria-label='Hourly generation, load and day-ahead price'>";
 const shade=(a,c)=>(a||[]).forEach(i=>{s+="<rect x='"+(ml+i*bw).toFixed(1)+"' y='"+mt+"' width='"+bw.toFixed(1)+"' height='"+ih+"' fill='"+c+"'/>"});
 shade(X.ev.hi,"rgba(194,65,12,.17)");shade(X.ev.lo,"rgba(31,95,153,.17)");
 lt.forEach(v=>{s+="<line x1='"+ml+"' x2='"+(W-mr)+"' y1='"+y(v).toFixed(1)+"' y2='"+y(v).toFixed(1)+"' stroke='var(--line)' stroke-width='"+(v===0?1:.5)+"'/><text x='"+(ml-5)+"' y='"+(y(v)+3.5).toFixed(1)+"' text-anchor='end' font-size='"+fs+"' fill='var(--mut)'>"+mw(v)+"</text>"});
 pt.forEach(v=>{s+="<text x='"+(W-mr+5)+"' y='"+(yp(v)+3.5).toFixed(1)+"' font-size='"+fs+"' fill='var(--acc)'>"+fxN(v,0)+"</text>"});
 s+="<text x='"+(ml-5)+"' y='"+(mt-12)+"' text-anchor='end' font-size='"+fs+"' fill='var(--mut)'>MW</text><text x='"+(W-mr+5)+"' y='"+(mt-12)+"' font-size='"+fs+"' fill='var(--acc)'>"+X.Pu+"</text>";
 const gap=bw>8?1.5:.5,op=X.src==="forecast"?" fill-opacity='.55'":"";
 X.lab.forEach((_,i)=>{let acc=0;X.st.forEach(q=>{const v=q.v[i];if(!v)return;s+="<rect x='"+(ml+i*bw+gap/2).toFixed(1)+"' y='"+y(acc+v).toFixed(1)+"' width='"+Math.max(.5,bw-gap).toFixed(1)+"' height='"+Math.max(0,y(acc)-y(acc+v)).toFixed(1)+"' fill='var(--m-"+q.k+")'"+op+"/>";acc+=v})});
 if(X.R&&X.showR)s+="<path d='"+fxPath(X.R,x,y)+"' fill='none' stroke='var(--ink)' stroke-width='1.4' stroke-dasharray='5 3'/>";
 if(X.L)s+="<path d='"+fxPath(X.L,x,y)+"' fill='none' stroke='var(--ink)' stroke-width='1.8'"+(X.Ls==="day-ahead forecast"?" stroke-dasharray='2 2'":"")+"/>";
 X.refs.forEach(r=>{s+="<line x1='"+ml+"' x2='"+(W-mr)+"' y1='"+yp(r.v).toFixed(1)+"' y2='"+yp(r.v).toFixed(1)+"' stroke='"+r.c+"' stroke-width='1.3' stroke-dasharray='"+r.dash+"'/><text x='"+(W-mr-4)+"' y='"+(yp(r.v)-4).toFixed(1)+"' text-anchor='end' font-size='"+fs+"' fill='"+r.c+"' paint-order='stroke' stroke='var(--panel)' stroke-width='3'>"+r.l+"</text>"});
 if(X.P){s+="<path d='"+fxPath(X.P,x,yp)+"' fill='none' stroke='var(--acc)' stroke-width='2.2'/>";X.P.forEach((v,i)=>{if(v!=null&&bw>12)s+="<circle cx='"+x(i).toFixed(1)+"' cy='"+yp(v).toFixed(1)+"' r='2.2' fill='var(--acc)'/>"})}
 const every=n>30?6:bw<18?3:bw<34?2:1;X.lab.forEach((l,i)=>{if(i%every===0)s+="<text x='"+x(i).toFixed(1)+"' y='"+(H-8)+"' text-anchor='middle' font-size='"+fs+"' fill='var(--mut)'>"+l+"</text>"});
 s+="<line class='fxcr' x1='0' x2='0' y1='"+mt+"' y2='"+(mt+ih)+"' stroke='var(--mut)' stroke-width='1' visibility='hidden'/>";
 s+="<rect class='fxov' x='"+ml+"' y='"+mt+"' width='"+iw+"' height='"+ih+"' fill='transparent'/></svg>";
 Object.assign(X,{ml,bw,W,tip:i=>fxTipMain(X,i)});FX.charts.push(X);return s}
function fxHover(e,sv){const X=FX.charts[+sv.dataset.c];if(!X)return;const r=sv.getBoundingClientRect(),px=(e.clientX-r.left)*X.W/r.width,i=Math.floor((px-X.ml)/X.bw),all=document.querySelectorAll("#fxp svg.fxsv .fxcr");
 if(i<0||i>=X.lab.length){all.forEach(c=>c.setAttribute("visibility","hidden"));$("dtip").style.display="none";return}
 all.forEach(c=>{const C=FX.charts[+c.closest("svg").dataset.c];if(!C)return;const cx=(C.ml+(i+.5)*C.bw).toFixed(1);c.setAttribute("x1",cx);c.setAttribute("x2",cx);c.setAttribute("visibility","visible")});
 dtip(e,X.tip(i).join("\n"))}
function fxTipMain(X,i){const t=[fxDayLbl(X.d,{weekday:"short"})+" "+X.lab[i]+":00 CET"+(X.ev.hi&&X.ev.hi.includes(i)?" · "+X.ev.hiL:X.ev.lo&&X.ev.lo.includes(i)?" · "+X.ev.loL:"")];
 if(X.P)t.push("Day-ahead price "+fxN(X.P[i],1)+" "+X.Pu);if(X.L)t.push("Load "+fxN(X.L[i],0)+" MW"+(X.Ls!=="actual"?" ("+X.Ls+")":""));
 if(X.R)t.push("Residual load "+fxN(X.R[i],0)+" MW");X.st.slice().reverse().forEach(q=>{if(q.v[i])t.push(q.name+" "+fxN(q.v[i],0)+" MW"+(X.src==="forecast"?" (forecast)":""))});return t}
/* ---- step 2: what was going on next door (flows per border, neighbour prices, neighbour strip, shared crosshair) ---- */
const FXNC=["#4e79a7","#f28e2b","#59a14f","#b07aa1","#76b7b2","#e15759","#9c755f","#edc948","#bab0ac","#ff9da7","#86bcb6"]; // neighbour identity colours (same in flows, prices, cards)
const FXZN={AL:"Albania",AT:"Austria",BA:"Bosnia and Herzegovina",BE:"Belgium",BG:"Bulgaria",CH:"Switzerland",CZ:"Czechia","DE-LU":"Germany-Luxembourg",DK1:"West Denmark",DK2:"East Denmark",EE:"Estonia",ES:"Spain",FI:"Finland",FR:"France",GB:"Great Britain",GR:"Greece",HR:"Croatia",HU:"Hungary","IE(SEM)":"Ireland (all-island)",LT:"Lithuania",LV:"Latvia",ME:"Montenegro",MK:"North Macedonia",NL:"Netherlands",PL:"Poland",PT:"Portugal",RO:"Romania",RS:"Serbia",SI:"Slovenia",SK:"Slovakia","UA-IPS":"Ukraine",NO1:"Norway NO1",NO2:"Norway NO2",NO3:"Norway NO3",NO4:"Norway NO4",NO5:"Norway NO5",SE1:"Sweden SE1",SE2:"Sweden SE2",SE3:"Sweden SE3",SE4:"Sweden SE4","IT-North":"Northern Italy","IT-Centre-North":"Central-Northern Italy","IT-Centre-South":"Central-Southern Italy","IT-South":"Southern Italy","IT-Calabria":"Calabria","IT-Sicily":"Sicily","IT-Sardinia":"Sardinia"};
function fxGeom(W,n){const sm=W<520,ml=sm?40:56,mr=sm?42:58;return{sm,ml,mr,iw:W-ml-mr,bw:(W-ml-mr)/n,fs:sm?10:11}}
/* neighbour zones of `o.z` on the day: from the zone file's flow columns (x|in|N, x|out|N), ordered by mean |net flow| */
function fxNbZones(T,idx){const s=new Set();Object.keys(T.c).forEach(id=>{const m=/^x\|(in|out)\|(.+)$/.exec(id);if(m&&idx.some(i=>T.c[id].v[i]!=null))s.add(m[2])});return[...s]}
function fxNb(o,T,idx){return fxNbZones(T,idx).map(n=>{const vi=T.c["x|in|"+n],vo=T.c["x|out|"+n];
  const net=idx.map(i=>{const a=vi?vi.v[i]:null,b=vo?vo.v[i]:null;return a==null&&b==null?null:(a||0)-(b||0)}); // import into o.z positive
  const nn=net.filter(v=>v!=null),U=FX.ts[n],ok=U&&!U.err,pc=ok&&U.c["p|price"];let P=null,Pu=null,mix=null,why="";
  if(ok){const ui=[];for(let i=0;i<U.n;i++)if(U.day[i]===o.d)ui.push(i);
   if(pc){Pu=pc.m.unit.replace("EUR","€").replace("GBP","£");if(Pu==="€/MWh")P=idx.map(i=>{const k=ui.indexOf(i);return k<0?null:pc.v[i]});else why="price published in "+pc.m.unit.split("/")[0]+", not converted"}else why="no price in the store";
   const S=fxSeries(U,ui);if(S.src==="actual"&&S.st.length)mix=S.st.map(q=>({k:q.k,name:q.name,mwh:q.v.reduce((a,v)=>a+(v||0),0)})).filter(q=>q.mwh>0)}
  else why=U&&U.err?"not in the store":"";
  const pp=P?P.filter(v=>v!=null):[];
  return{z:n,net,netMean:nn.length?nn.reduce((a,v)=>a+v,0)/nn.length:null,P,Pu,pmean:pp.length?pp.reduce((a,v)=>a+v,0)/pp.length:null,mix,why}})
 .sort((a,b)=>Math.abs(b.netMean||0)-Math.abs(a.netMean||0)).map((q,k)=>Object.assign(q,{col:FXNC[k%FXNC.length]}))}
function fxShade(s,ev,g,mt,ih){[["hi","rgba(194,65,12,.12)"],["lo","rgba(31,95,153,.12)"]].forEach(([k,c])=>(ev[k]||[]).forEach(i=>{s.push("<rect x='"+(g.ml+i*g.bw).toFixed(1)+"' y='"+mt+"' width='"+g.bw.toFixed(1)+"' height='"+ih+"' fill='"+c+"'/>")}))}
function fxXLab(s,lab,g,H){const n=lab.length,every=n>30?6:g.bw<18?3:g.bw<34?2:1;lab.forEach((l,i)=>{if(i%every===0)s.push("<text x='"+(g.ml+(i+.5)*g.bw).toFixed(1)+"' y='"+(H-8)+"' text-anchor='middle' font-size='"+g.fs+"' fill='var(--mut)'>"+l+"</text>")})}
function fxFlowChart(z,nb,lab,ev,W){const ci=FX.charts.length,g=fxGeom(W,lab.length),H=Math.round(Math.min(260,Math.max(190,W*.26))),mt=24,mb=26,ih=H-mt-mb;
 const up=lab.map((_,i)=>nb.reduce((a,q)=>a+Math.max(0,q.net[i]||0),0)),dn=lab.map((_,i)=>nb.reduce((a,q)=>a+Math.min(0,q.net[i]||0),0));
 const tot=lab.map((_,i)=>{const v=nb.map(q=>q.net[i]).filter(x=>x!=null);return v.length?v.reduce((a,x)=>a+x,0):null});
 const t=fxTicks(Math.min(0,...dn),Math.max(1,...up)),y0=t[0],y1=t[t.length-1],y=v=>mt+ih-(v-y0)/(y1-y0)*ih,mw=v=>Math.abs(v)>=1e4?fxN(v/1000,0)+"k":fxN(v,0);
 const s=["<svg class='fxsv' data-c='"+ci+"' width='"+W+"' height='"+H+"' viewBox='0 0 "+W+" "+H+"' role='img' aria-label='Hourly cross-border flows of "+z+" per neighbour'>"];
 fxShade(s,ev,g,mt,ih);
 t.forEach(v=>s.push("<line x1='"+g.ml+"' x2='"+(W-g.mr)+"' y1='"+y(v).toFixed(1)+"' y2='"+y(v).toFixed(1)+"' stroke='var(--line)' stroke-width='"+(v===0?1.2:.5)+"'/><text x='"+(g.ml-5)+"' y='"+(y(v)+3.5).toFixed(1)+"' text-anchor='end' font-size='"+g.fs+"' fill='var(--mut)'>"+mw(v)+"</text>"));
 s.push("<text x='"+(g.ml-5)+"' y='"+(mt-12)+"' text-anchor='end' font-size='"+g.fs+"' fill='var(--mut)'>MW</text><text x='"+(g.ml+4)+"' y='"+(mt-12)+"' font-size='"+g.fs+"' fill='var(--mut)'>▲ import into "+z+"</text><text x='"+(g.ml+4)+"' y='"+(H-mb+12)+"' font-size='"+g.fs+"' fill='var(--mut)' visibility='hidden'>.</text>");
 const gap=g.bw>8?1.5:.5;lab.forEach((_,i)=>{let a=0,b=0;nb.forEach(q=>{const v=q.net[i];if(!v)return;const x0=(g.ml+i*g.bw+gap/2).toFixed(1),w=Math.max(.5,g.bw-gap).toFixed(1);
  if(v>0){s.push("<rect x='"+x0+"' y='"+y(a+v).toFixed(1)+"' width='"+w+"' height='"+Math.max(0,y(a)-y(a+v)).toFixed(1)+"' fill='"+q.col+"'/>");a+=v}
  else{s.push("<rect x='"+x0+"' y='"+y(b).toFixed(1)+"' width='"+w+"' height='"+Math.max(0,y(b+v)-y(b)).toFixed(1)+"' fill='"+q.col+"'/>");b+=v}})});
 s.push("<path d='"+fxPath(tot,i=>g.ml+(i+.5)*g.bw,y)+"' fill='none' stroke='var(--ink)' stroke-width='2'/>");
 s.push("<text x='"+(g.ml+4)+"' y='"+(mt+ih-4)+"' font-size='"+g.fs+"' fill='var(--mut)'>▼ export from "+z+"</text>");
 fxXLab(s,lab,g,H);
 s.push("<line class='fxcr' x1='0' x2='0' y1='"+mt+"' y2='"+(mt+ih)+"' stroke='var(--mut)' stroke-width='1' visibility='hidden'/><rect class='fxov' x='"+g.ml+"' y='"+mt+"' width='"+g.iw+"' height='"+ih+"' fill='transparent'/></svg>");
 FX.charts.push({lab,ml:g.ml,bw:g.bw,W,tip:i=>[lab[i]+":00 CET · flows of "+z+" (+ import, − export)"].concat(nb.filter(q=>q.net[i]!=null).sort((p,q)=>q.net[i]-p.net[i]).map(q=>q.z+" "+(q.net[i]>0?"+":"")+fxN(q.net[i],0)+" MW")).concat(tot[i]!=null?["Net position "+(tot[i]>0?"+":"")+fxN(tot[i],0)+" MW"]:[])});
 return s.join("")}
function fxPriceChart(z,P,Pu,nb,lab,ev,W){const ci=FX.charts.length,g=fxGeom(W,lab.length),H=Math.round(Math.min(260,Math.max(190,W*.26))),mt=24,mb=26,ih=H-mt-mb;
 const ser=[{z,P,col:"var(--ink)",w:2.6}].concat(nb.filter(q=>q.P).map(q=>({z:q.z,P:q.P,col:q.col,w:1.5})));
 const all=ser.flatMap(q=>q.P||[]).filter(v=>v!=null);if(!all.length)return"";
 const t=fxTicks(Math.min(0,...all),Math.max(...all)*1.03+.01),y0=t[0],y1=t[t.length-1],y=v=>mt+ih-(v-y0)/(y1-y0)*ih;
 const s=["<svg class='fxsv' data-c='"+ci+"' width='"+W+"' height='"+H+"' viewBox='0 0 "+W+" "+H+"' role='img' aria-label='Day-ahead prices of "+z+" and its neighbours'>"];
 fxShade(s,ev,g,mt,ih);
 t.forEach(v=>s.push("<line x1='"+g.ml+"' x2='"+(W-g.mr)+"' y1='"+y(v).toFixed(1)+"' y2='"+y(v).toFixed(1)+"' stroke='var(--line)' stroke-width='"+(v===0?1:.5)+"'/><text x='"+(g.ml-5)+"' y='"+(y(v)+3.5).toFixed(1)+"' text-anchor='end' font-size='"+g.fs+"' fill='var(--mut)'>"+fxN(v,0)+"</text>"));
 s.push("<text x='"+(g.ml-5)+"' y='"+(mt-12)+"' text-anchor='end' font-size='"+g.fs+"' fill='var(--mut)'>"+Pu+"</text>");
 ser.slice(1).concat(ser.slice(0,1)).forEach(q=>s.push("<path d='"+fxPath(q.P,i=>g.ml+(i+.5)*g.bw,y)+"' fill='none' stroke='"+q.col+"' stroke-width='"+q.w+"' stroke-linejoin='round'/>"));
 fxXLab(s,lab,g,H);
 s.push("<line class='fxcr' x1='0' x2='0' y1='"+mt+"' y2='"+(mt+ih)+"' stroke='var(--mut)' stroke-width='1' visibility='hidden'/><rect class='fxov' x='"+g.ml+"' y='"+mt+"' width='"+g.iw+"' height='"+ih+"' fill='transparent'/></svg>");
 FX.charts.push({lab,ml:g.ml,bw:g.bw,W,tip:i=>{const pz=P?P[i]:null;return[lab[i]+":00 CET · day-ahead price, "+Pu].concat(ser.filter(q=>q.P&&q.P[i]!=null).sort((p,q)=>q.P[i]-p.P[i]).map(q=>q.z+(q.z==="GB"?" (Market Index)":"")+" "+fxN(q.P[i],1)+(q.z!==z&&pz!=null?" ("+(q.P[i]-pz>=0?"+":"")+fxN(q.P[i]-pz,1)+" vs "+z+")":"")))}});
 return s.join("")}
function fxStrip(o,nb,pm){return"<div class='fxnb'>"+nb.map(q=>{const tot=q.mix?q.mix.reduce((a,m)=>a+m.mwh,0):0;
  const bar=q.mix&&tot>0?"<div class='fxmix' title='"+q.mix.map(m=>m.name+" "+Math.round(100*m.mwh/tot)+" %").join(", ")+"'>"+FXTECH.map(t=>{const m=q.mix.find(x=>x.k===t[0]);return m?"<i style='width:"+(100*m.mwh/tot).toFixed(1)+"%;background:var(--m-"+t[0]+")'></i>":""}).join("")+"</div>":"<div class='fxmix na mut'>generation n/a</div>";
  const fl=q.netMean==null?"flow n/a":q.netMean>=0?"sent <b>"+fxN(q.netMean,0)+" MW</b> to "+o.z:"took <b>"+fxN(-q.netMean,0)+" MW</b> from "+o.z;
  const pr=q.pmean!=null?"<b>"+fxN(q.pmean,1)+"</b> €/MWh"+(pm!=null?" <span class='mut'>("+(q.pmean-pm>=0?"+":"")+fxN(q.pmean-pm,1)+" vs "+o.z+")</span>":""):"<span class='mut' title='"+q.why+"'>price n/a</span>";
  return"<button class='fxcard' data-nz='"+q.z+"' title='Show "+q.z+" for the same day'><span class='fxsw' style='background:"+q.col+"'></span><b>"+q.z+"</b> <span class='mut'>"+(FXZN[q.z]||"")+"</span><span class='fxcl'>"+pr+(q.z==="GB"&&q.pmean!=null?" <span class='mut'>Market Index</span>":"")+"</span><span class='fxcl'>"+fl+" <span class='mut'>(day mean)</span></span>"+bar+"</button>"}).join("")+"</div>"}
function fxNext(o,T,idx,Q,lab,ev,W){const zs=fxNbZones(T,idx);if(!zs.length)return"<h4 class='fxh4'>Next door</h4><div class='feednote'>No cross-border flow data for "+o.z+" on this day in the store.</div>";
 if(zs.some(n=>!FX.ts[n]))return"<h4 class='fxh4'>Next door</h4><div class='feednote'>Loading the neighbours ("+zs.join(", ")+")…</div>";
 const nb=fxNb(o,T,idx),pm=Q.P&&Q.Pu==="€/MWh"?(a=>a.length?a.reduce((x,v)=>x+v,0)/a.length:null)(Q.P.filter(v=>v!=null)):null;
 const lg=nb.map(q=>"<span class='fxk'><i style='background:"+q.col+"'></i>"+q.z+"</span>").join("");
 let h="<h4 class='fxh4'>Cross-border flows <span class='mut'>physical flow per border, hourly; above the line = import into "+o.z+", below = export; black line = net position over these borders</span></h4><div class='fxch'>"+fxFlowChart(o.z,nb,lab,ev,W)+"</div><div class='fxlg'>"+lg+"<span class='fxk'><i style='height:0;border-top:2px solid var(--ink)'></i>Net position</span></div>";
 const pc=Q.P&&Q.Pu==="€/MWh"?fxPriceChart(o.z,Q.P,Q.Pu,nb,lab,ev,W):"";
 const na=nb.filter(q=>!q.P);
 if(pc)h+="<h4 class='fxh4'>Day-ahead prices next door <span class='mut'>"+o.z+" bold; same colours as the flows</span></h4><div class='fxch'>"+pc+"</div><div class='fxlg'><span class='fxk'><i style='height:0;border-top:3px solid var(--ink)'></i>"+o.z+"</span>"+nb.filter(q=>q.P).map(q=>"<span class='fxk'><i style='height:0;border-top:2px solid "+q.col+"'></i>"+q.z+(q.z==="GB"?" (Market Index, trade-weighted)":"")+(Q.P&&q.P.every((v,i)=>v==null||Q.P[i]==null||Math.abs(v-Q.P[i])<.01)?" (same price as "+o.z+" all day, hidden behind it)":"")+"</span>").join("")+(na.length?"<span class='mut'>price n/a: "+na.map(q=>q.z+(q.why?" ("+q.why+")":"")).join(", ")+"</span>":"")+"</div>";
 h+="<h4 class='fxh4'>Next door on "+fxDayLbl(o.d)+" <span class='mut'>click a neighbour to see the same day there</span></h4>"+fxStrip(o,nb,pm);
 return h}
function fxHead(j,o){const r=j.scan.find(q=>q.zone===o.z&&q.metric===o.m),ru=(j.rules||[]).find(q=>q.metric===o.m)||{label:o.m,unit:""},u=ru.unit==="EUR/MWh"?"€/MWh":ru.unit;
 const fl=typeof ZONEFLAG!=="undefined"&&ZONEFLAG[o.z]?flagHTML(ZONEFLAG[o.z],9)+" ":"",name=ru.label.charAt(0).toUpperCase()+ru.label.slice(1);
 let h="<div class='fxhd'><div class='fxt'><div class='fxz'>"+fl+"<b>"+o.z+"</b> · "+fxDayLbl(o.d,{weekday:"short",year:"numeric"})+"</div><div class='fxn'>"+name
  +(r&&r.side?" — unusually <b class='"+(r.side==="high"?"fh":"fl")+"'>"+r.side+"</b>":"")+" <span class='fxq' tabindex='0' title='"+(FXPLAIN[o.m]||"").replace(/'/g,"&#39;")+"' aria-label='What this means'>?</span></div></div>";
 if(r){const pct=r.pct!=null?Math.round(r.pct*100):null;h+="<div class='fxv'><span class='big'>"+fxN(r.value)+"</span> <span class='mut'>"+u+"</span></div><div class='fxs2 mut'>"
  +(pct==null?"Under "+j.min_hist+" days of history ("+r.n_hist+"), no percentile yet":"P"+pct+": "+(r.side==="low"||(!r.side&&pct<50)?"lower than on "+(100-pct)+" %":"higher than on "+pct+" %")+" of the last "+r.n_hist+" days in "+o.z+"<br>Typical "+fxN(r.median)+" "+u+" (P10–P90 "+fxN(r.p10)+"–"+fxN(r.p90)+")")+"</div>"}
 else h+="<div class='fxs2 mut'>No value for this metric in "+o.z+" on this day.</div>";
 return h+(o.row&&o.row.z!==o.z?"<button class='fxback'>← back to "+o.row.z+"</button>":"")+"<button class='fxx' aria-label='Close' title='Close (Esc)'>✕</button></div>"}
function fxUnusual(j,o){const rows=[];const cr={};(j.context_rules||[]).forEach(r=>cr[r.metric]=r);const rl={};(j.rules||[]).forEach(r=>rl[r.metric]=r);
 FXUNU.forEach(m=>{const r=(j.context||[]).find(q=>q.zone===o.z&&q.metric===m)||j.scan.find(q=>q.zone===o.z&&q.metric===m),d=cr[m]||rl[m];if(r&&d)rows.push([m,r,d])});
 if(!rows.length)return"<div class='feednote'>No daily metrics for "+o.z+" on this day yet (generation or load not published).</div>";
 rows.sort((a,b)=>(b[1].pct==null?-1:Math.abs(b[1].pct-.5))-(a[1].pct==null?-1:Math.abs(a[1].pct-.5)));
 return"<div class='fxuw'><table class='dt fxu'><thead><tr><th style='text-align:left'>Metric</th><th>Value</th><th>Percentile</th><th>Typical (median · P10–P90)</th><th style='text-align:left'>Reading</th></tr></thead><tbody>"
  +rows.map(([m,r,d])=>{const u=d.unit==="EUR/MWh"?"€/MWh":d.unit,p=r.pct,hiX=p!=null&&p>=.9&&(r.p90==null||r.value>r.p90),loX=p!=null&&p<=.1&&(r.p10==null||r.value<r.p10),ext=hiX||loX,cl=hiX?"fh":loX?"fl":"";
   const bar=p==null?"<span class='mut'>–</span>":"<span class='fxbar'><i style='left:"+(p*100).toFixed(0)+"%'></i></span> P"+Math.round(p*100);
   const rd=p==null?"<span class='mut'>under "+j.min_hist+" days of history</span>":ext?"<b class='"+cl+"'>unusually "+(hiX?"high":"low")+"</b>":"<span class='mut'>normal range</span>";
   return"<tr class='"+(ext?"ex":"")+(m===o.m?" me":"")+"' title='"+(FXPLAIN[m]||"").replace(/'/g,"&#39;")+"'><td style='text-align:left'>"+d.label.charAt(0).toUpperCase()+d.label.slice(1)+(m===o.m?" <span class='mut'>(this flag)</span>":"")+"</td><td>"+fxN(r.value)+" <span class='mut'>"+u+"</span></td><td>"+bar+"</td><td>"+fxN(r.median)+" · "+fxN(r.p10)+"–"+fxN(r.p90)+"</td><td style='text-align:left'>"+rd+"</td></tr>"}).join("")+"</tbody></table></div>"}
function fxBody(j,o,T,W){FX.charts=[];let h=fxHead(j,o);if(T.err)return h+"<div class='feednote'>The hourly series for "+o.z+" could not be loaded.</div>";
 const idx=[];for(let i=0;i<T.n;i++)if(T.day[i]===o.d)idx.push(i);
 if(!idx.length)return h+"<div class='feednote'>No hourly data for "+o.z+" on this day in the export (it keeps the last 30 days).</div>"+fxUnusual(j,o);
 const Q=fxSeries(T,idx),n=idx.length,cov=a=>a?a.filter(v=>v!=null).length:0,bad=[];
 const gN=Q.src==="actual"?idx.filter((_,k)=>Q.st.some(q=>q.v[k]!=null)).length:0,gl=Q.gIds.length?fxLast(T,Q.gIds):-1;
 if(gN<n){const w=gl>=0?fxWhen(T,gl):null;bad.push("<b>"+o.z+" generation: "+(gN?gN+" of "+n+" hours published":"not published yet for this day")+"</b>"+(w?" · latest reading "+w.lbl+", <b>"+w.ago+" h old</b>":"")+(Q.src==="forecast"?". The chart shows the day-ahead wind and solar forecast instead (lighter bars).":""))}
 const lN=Q.Ls==="actual"?cov(Q.L):0;if(lN<n&&o.z!=="GB"){const ll=Q.lIds.length?fxLast(T,Q.lIds):-1,w=ll>=0?fxWhen(T,ll):null;bad.push("<b>Load: "+(lN?lN+" of "+n+" hours":"actual not published yet")+"</b>"+(w?" · latest reading "+w.lbl+", "+w.ago+" h old":"")+(Q.L&&Q.Ls!=="actual"?" (dotted line: "+Q.Ls+")":""))}
 const pN=cov(Q.P);if(pN<n)bad.push("<b>Day-ahead price: "+pN+" of "+n+" hours</b>");
 if(bad.length)h+="<div class='fxbad'>"+bad.join("<br>")+"</div>";
 const ev=Q.P||Q.R?fxEvents(o.m,Q.P||[],Q.R||[]):{},refs=[],dm=cov(Q.P)?Q.P.filter(v=>v!=null).reduce((a,v)=>a+v,0)/cov(Q.P):null,mc=(id,k)=>T.c[id]?T.c[id].v[idx[k||0]]:null;
 const r=j.scan.find(q=>q.zone===o.z&&q.metric===o.m);
 if(o.m==="baseload"&&dm!=null){refs.push({v:dm,l:"day mean "+fxN(dm,1),c:"var(--acc)",dash:"6 3"});if(r&&r.median!=null&&Q.Pu==="€/MWh")refs.push({v:r.median,l:"90-day median "+fxN(r.median,1),c:"var(--mut)",dash:"2 3"})}
 const cap={cr_solar:"capture_solar",cr_wind_onshore:"capture_wind_onshore",cr_wind_offshore:"capture_wind_offshore"}[o.m];
 if(cap&&dm!=null){const cp=mc("m|"+cap);refs.push({v:dm,l:"baseload "+fxN(dm,1),c:"var(--mut)",dash:"2 3"});if(cp!=null)refs.push({v:cp,l:"capture price "+fxN(cp,1),c:"var(--acc)",dash:"6 3"})}
 const lab=idx.map((i,k)=>T.hr[i]+(k&&T.hr[idx[k-1]]===T.hr[i]?"′":""));
 const showR=/^res_/.test(o.m);
 h+="<div class='fxch'>"+fxChart({d:o.d,lab,st:Q.st,src:Q.src,L:Q.L,Ls:Q.Ls,R:Q.R,showR,P:Q.P,Pu:Q.Pu,ev,refs},W)+"</div>";
 const chip=(c,l,ln)=>"<span class='fxk'><i style='"+(ln?"height:0;border-top:"+ln+" "+c:"background:"+c)+"'></i>"+l+"</span>";
 let lg=Q.st.slice().reverse().map(q=>chip("var(--m-"+q.k+")",q.name+(Q.src==="forecast"?" (forecast)":""))).join("");
 if(Q.L)lg+=chip("var(--ink)","Load"+(Q.Ls!=="actual"?" ("+Q.Ls+")":""),"2px "+(Q.Ls==="day-ahead forecast"?"dotted":"solid"));
 if(Q.R&&showR)lg+=chip("var(--ink)","Residual load (load − wind − solar)","2px dashed");
 if(Q.P)lg+=chip("var(--acc)","Day-ahead price ("+Q.Pu+", right axis)","2px solid");
 if(ev.hi&&ev.hi.length)lg+=chip("rgba(194,65,12,.35)",ev.hiL);if(ev.lo&&ev.lo.length)lg+=chip("rgba(31,95,153,.35)",ev.loL);
 h+="<div class='fxlg'>"+lg+"</div>";
 let cap2="";if(ev.k)cap2="The "+ev.k+" priciest hours averaged <b>"+fxN(ev.mh,1)+"</b> "+Q.Pu+", the "+ev.k+" cheapest <b>"+fxN(ev.ml,1)+"</b>: a spread of <b data-chk='"+ev.spread.toFixed(2)+"'>"+fxN(ev.spread,1)+" "+Q.Pu+"</b>"+(Q.Pu!=="€/MWh"?" (the flag itself is computed in €/MWh)":"")+".";
 else if(o.m==="neg_hours"&&ev.lo)cap2="<b>"+ev.lo.length+"</b> hours below zero"+(ev.lo.length?", from "+lab[ev.lo[0]]+":00 to "+lab[ev.lo[ev.lo.length-1]]+":59 CET":"")+".";
 else if(o.m==="res_ramp3"&&ev.rise!=null)cap2="Residual load rose by <b>"+fxN(ev.rise,0)+" MW</b> between "+lab[ev.hi[0]]+":00 and "+lab[ev.hi[3]]+":00 CET.";
 else if((o.m==="res_peak"||o.m==="res_min")&&(ev.hi||ev.lo)){const i=(ev.hi||ev.lo)[0];cap2="Residual load "+(o.m==="res_peak"?"peaked":"bottomed out")+" at <b>"+fxN(Q.R[i],0)+" MW</b> at "+lab[i]+":00 CET.";}
 else if(cap&&dm!=null&&mc("m|"+cap)!=null)cap2=(o.m==="cr_solar"?"Solar":o.m==="cr_wind_onshore"?"Onshore wind":"Offshore wind")+" earned <b>"+fxN(mc("m|"+cap),1)+"</b> "+Q.Pu+" on average (generation-weighted) against a day mean of <b>"+fxN(dm,1)+"</b> "+Q.Pu+": it produced mostly in the "+(mc("m|"+cap)<dm?"cheaper":"pricier")+" hours.";
 else if(o.m==="baseload"&&dm!=null)cap2="Day mean <b>"+fxN(dm,1)+"</b> "+Q.Pu+(r&&r.median!=null?" against a 90-day median of <b>"+fxN(r.median,1)+"</b> €/MWh":"")+".";
 else if(o.m==="import_share")cap2="See the cross-border flows below: which borders carried the import or export, and whether prices next door split.";
 if(cap2)h+="<div class='fxcap'>"+cap2+(Q.src==="forecast"&&showR?" Residual load here uses the wind and solar <i>forecast</i>.":"")+"</div>";
 h+=fxNext(o,T,idx,Q,lab,ev,W);
 h+="<h4 class='fxh4'>What else was unusual in "+o.z+" that day <span class='mut'>percentile vs the zone's own last "+j.window_days+" days; ≥ P90 or ≤ P10 highlighted</span></h4>"+fxUnusual(j,o);
 h+="<div class='mut fxsrc'>Data: <a href='https://transparency.entsoe.eu' style='color:inherit'>ENTSO-E Transparency Platform</a> (day-ahead prices, actual generation per type, actual load, day-ahead wind and solar forecast), hourly means of the native resolution, CET day."
  +(o.z==="GB"?" Great Britain: Contains BMRS data © Elexon Limited copyright and database right "+new Date().getFullYear()+" (<a href='https://www.elexon.co.uk/data/balancing-mechanism-reporting-agent/copyright-licence-bmrs-data/' style='color:inherit'>BMRS open data licence</a>); price = Market Index Data (APX / EPEX SPOT trades via Elexon BMRS), stored in GBP, shown in €/MWh at the ECB daily reference rate.":"")
  +" Generation is clipped at zero; pumped-storage consumption is not shown.</div>";
 return h}
function fxFill(){const p=$("fxp");if(!p||!FX.open||!FX.cur)return;const o=FX.open,z=o.z,j=FX.cur;
 const dw=p.closest(".dw");p.style.width=dw?Math.max(280,dw.clientWidth-2)+"px":"";
 const W=Math.max(280,(dw?dw.clientWidth-2:p.clientWidth)-30),T=FX.ts[z];
 if(!T){p.innerHTML=fxHead(j,o)+"<div class='feednote'>Loading the hourly series for "+z+"…</div>";
  if(!FX.busy[z]){FX.busy[z]=1;dbJson("data/browse/ts/"+encodeURIComponent(z)+".json").then(t=>{FX.ts[z]=fxPrep(t)}).catch(()=>{FX.ts[z]={err:1}}).then(()=>{FX.busy[z]=0;if(S.tab==="flg")fxFill()})}return}
 if(!T.err){const idx=[];for(let i=0;i<T.n;i++)if(T.day[i]===o.d)idx.push(i);
  fxNbZones(T,idx).filter(n=>!FX.ts[n]&&!FX.busy[n]).forEach(n=>{FX.busy[n]=1;dbJson("data/browse/ts/"+encodeURIComponent(n)+".json").then(t=>{FX.ts[n]=fxPrep(t)}).catch(()=>{FX.ts[n]={err:1}}).then(()=>{FX.busy[n]=0;if(S.tab==="flg"&&FX.open&&!Object.values(FX.busy).some(Boolean))fxFill()})})}
 p.innerHTML=fxBody(j,o,T,W)}
function fxToggle(z,m,d){const o=FX.open,fr=o&&(o.row||o);FX.open=fr&&fr.z===z&&fr.m===m&&o.d===d?null:{z,m,d};fxHash();flagsTab();
 const row=document.querySelector("#flg tr.fsr[data-z='"+z+"'][data-m='"+m+"']");if(row){row.focus({preventScroll:true});if(FX.open)row.scrollIntoView({block:"nearest"})}}
$("flg").addEventListener("click",e=>{const nc=e.target.closest(".fxcard"),bk=e.target.closest(".fxback");
 if((nc||bk)&&FX.open){const o=FX.open,row=o.row||{z:o.z,m:o.m};FX.open=bk||nc.dataset.nz===row.z?{z:row.z,m:row.m,d:o.d}:{z:nc.dataset.nz,m:o.m,d:o.d,row};fxHash();FX.charts=[];fxFill();const p=$("fxp");if(p)p.scrollIntoView({block:"nearest"});return}
 if(e.target.closest(".fxx")){const o=FX.open&&(FX.open.row||FX.open);FX.open=null;fxHash();flagsTab();if(o){const r=document.querySelector("#flg tr.fsr[data-z='"+o.z+"'][data-m='"+o.m+"']");if(r)r.focus()}return}
 const tr=e.target.closest("tr.fsr");if(tr&&FX.cur)fxToggle(tr.dataset.z,tr.dataset.m,FX.cur.day)});
$("flg").addEventListener("keydown",e=>{const tr=e.target.closest("tr.fsr");if(tr&&(e.key==="Enter"||e.key===" ")){e.preventDefault();fxToggle(tr.dataset.z,tr.dataset.m,FX.cur.day)}});
$("flg").addEventListener("mousemove",e=>{const sv=e.target.closest("svg.fxsv");if(sv)fxHover(e,sv)});
$("flg").addEventListener("mouseout",e=>{const sv=e.target.closest("svg.fxsv");if(sv&&!sv.contains(e.relatedTarget)){$("dtip").style.display="none";document.querySelectorAll("#fxp .fxcr").forEach(c=>c.setAttribute("visibility","hidden"))}});
$("flg").addEventListener("change",e=>{if(e.target.id==="fld"){FX.day=e.target.value===(FL.j&&FL.j.day)?null:e.target.value;FX.open=null;FX.gone=null;fxHash();flagsTab()}});
addEventListener("keydown",e=>{if(e.key==="Escape"&&S.tab==="flg"&&FX.open){const o=FX.open.row||FX.open;FX.open=null;fxHash();flagsTab();const r=document.querySelector("#flg tr.fsr[data-z='"+o.z+"'][data-m='"+o.m+"']");if(r)r.focus()}});
addEventListener("resize",()=>{if(S.tab==="flg"&&FX.open){clearTimeout(FX.rz);FX.rz=setTimeout(fxFill,150)}});

addEventListener("hashchange",fxFromHash);setTimeout(fxFromHash,0);  // deep link #flags/<zone>/<metric>/<day>, once main() has set up the page

export { FX, fxDayLbl, fxFill, fxHash };
