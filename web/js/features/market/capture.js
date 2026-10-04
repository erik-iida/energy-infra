/* Market tab: capture prices per technology (data/capture.json), sortable tables.
   ES module (spec 3 step 2): imports name what this file needs from other modules, the export list at the end what it offers. */
import { GROUPS, S, isReg } from "../../core/data.js";
import { $ } from "../../core/util.js";
import { MK, N0 } from "../../core/feed.js";
import { ZONEFLAG, flagHTML, selZones } from "../../core/flags.js";
import { CMP, cmpRender } from "../../core/cmp.js";
import { HMPOS, hmColor, lerpC } from "./heatmap.js";
import { ZN, capStats, market, pm } from "./market.js";
import { SYS } from "../system/system.js";
/* ---------- capture prices per technology (ENTSO-E, web/data/capture.json) ---------- */
const CAP={d:null,loading:false};
function capLoad(){if(CAP.d||CAP.loading)return;CAP.loading=true;fetch("data/capture.json",{cache:"no-cache"}).then(r=>r.ok?r.json():null).then(j=>{if(j){CAP.d=j;if(S.tab==="mkt")market()}}).catch(()=>{})}
// id, label, colour key, dashed (to tell apart two techs sharing a colour), shown in the line chart
const CAPT=[["solar","Solar","sol",0,1],["wind_onshore","Wind onshore","won",0,1],["wind_offshore","Wind offshore","woff",0,1],["nuclear","Nuclear","nuc",0,1],["fossil_gas","Gas","gas",0,1],
 ["fossil_hard_coal","Hard coal","coal",0,1],["fossil_brown_coal_lignite","Lignite","coal",1,1],["hydro_run_of_river","Hydro run-of-river","hyd",0,1],["hydro_water_reservoir","Hydro reservoir","hyd",1,1],
 ["hydro_pumped_storage","Pumped storage (generation)","hyd",0,0],["biomass","Biomass","bio",0,1],["fossil_oil","Oil","oil",0,0],["waste","Waste","bio",1,0],["geothermal","Geothermal","oth",0,0],
 ["fossil_coal_derived_gas","Coal-derived gas","coal",0,0],["others","Other","oth",0,0]];
const MON=m=>{const[y,mo]=m.split("-");return["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"][+mo-1]+" "+y.slice(2)};
const curMonth=()=>new Date().toISOString().slice(0,7);
// output-weighted capture over a set of months: {cap, gwh, base, rate, neg}
function capAgg(Z,ms,id){let e=0,r=0,bh=0,bs=0,ng=0;ms.forEach(m=>{const c=Z[m];if(!c)return;if(c.b!=null&&c.h){bs+=c.b*c.h;bh+=c.h}const t=c.t&&c.t[id];if(t&&t[1]>0){e+=t[1];r+=t[0]*t[1];ng+=(t[2]||0)*t[1]}});
 const base=bh?bs/bh:null,cap=e>0?r/e:null;return{cap,gwh:e,base,rate:cap!=null&&base>0?cap/base:null,neg:e>0?ng/e:null}}
function capCountry(){if(!S.c||S.c==="Europe"||isReg(S.c)||GROUPS[S.c])return null;const z=selZones();return z?[...z]:null}
// last-24-h capture per technology from the System data, for countries with one price zone
function cap24(z){const c=Object.keys(SYS).find(k=>SYS[k].zones&&SYS[k].zones.length===1&&SYS[k].zones[0]===z);const d=c&&SYS[c];if(!d||!d.series||d.lag_h||!MK.prices[z])return{};
 const out={};Object.entries(d.series).forEach(([id,v])=>{let e=0,r=0;v.forEach((g,h)=>{const p=MK.prices[z][h];if(g!=null&&g>0&&p!=null&&h<=N0){e+=g;r+=g*p}});if(e>0)out[id]=r/e});return out}
const r0=v=>v==null||!isFinite(v)?"–":Math.round(v);
const fxNote=fx=>(fx&&fx.UAH&&fx.UAH.rate?" Ukraine (UA-IPS) is published in UAH and converted at the latest National Bank of Ukraine rate, "+fx.UAH.rate.toFixed(2)+" UAH/EUR ("+fx.UAH.date+").":"")+(fx&&fx.GBP&&fx.GBP.rate?" GB is published in GBP and converted at the latest European Central Bank reference rate, "+fx.GBP.rate.toFixed(4)+" GBP/EUR"+(fx.GBP.date?" ("+fx.GBP.date+")":"")+".":"");
function capSection(){capLoad();const D=CAP.d,cz=capCountry();
 const head="<div class='mut' style='font-size:12px;margin:2px 0 8px'>Capture price = output-weighted day-ahead price: what a MWh from that technology earned on average in the day-ahead market. Actual generation per production type in each bidding zone and day-ahead prices from the <a href='https://transparency.entsoe.eu' style='color:inherit'>ENTSO-E Transparency Platform</a>, hourly averages."+fxNote(D&&D.fx)+"</div>";
 if(!D)return"<h2>Capture prices</h2>"+head+"<div class='feednote'>Loading… (if this stays, the monthly data hasn't been built yet: a background job fills two years for every zone over its first runs).</div>";
 const ms=D.months||[];
 if(cz){const zs=cz.filter(z=>D.zones[z]);if(!zs.length)return"<h2>Capture prices · "+S.c+"</h2>"+head+"<div class='feednote'>No ENTSO-E capture data for "+S.c+"'s bidding zones yet.</div>";
  return"<h2>Capture prices by technology · "+S.c+" <span class='mut' style='font:13px system-ui'>· monthly; pick Europe or a group to compare all markets</span></h2>"+head+zs.map((z,i)=>{const Z=D.zones[z],cm=curMonth(),full=ms.filter(m=>m<cm&&Z[m]),l12=full.slice(-12),lm=full[full.length-1],c24=cap24(z),cur=Z[cm];
   const B=capAgg(Z,l12,"_"),tb=k=>{const v=l12.map(m=>Z[m][k]).filter(x=>x!=null);return v.length?v.reduce((a,b)=>a+b,0)/v.length:null};
   const techs=CAPT.filter(([id])=>l12.some(m=>Z[m].t&&Z[m].t[id])||(cur&&cur.t&&cur.t[id]));
   const rows=techs.map(([id,n,ck])=>{const A=capAgg(Z,l12,id),L=lm?capAgg(Z,[lm],id):{},C=cur?capAgg(Z,[cm],id):{};return"<tr><td><i style='background:var(--m-"+ck+")'></i>"+n+"</td><td>"+r0(c24[id])+"</td><td>"+r0(C.cap)+"</td><td>"+r0(L.cap)+"</td><td><b>"+r0(A.cap)+"</b></td><td>"+(A.rate!=null?Math.round(100*A.rate)+"%":"–")+"</td><td data-v='"+(A.gwh||"")+"'>"+(A.gwh?(A.gwh>=1000?(A.gwh/1000).toFixed(1)+" TWh":Math.round(A.gwh)+" GWh"):"–")+"</td><td>"+(A.neg!=null?(100*A.neg).toFixed(1)+"%":"–")+"</td></tr>"}).join("");
   return"<div class='card' style='cursor:default'><h3>"+flagHTML(ZONEFLAG[z]||"",7)+" "+(ZN[z]||z)+"<span>baseload "+pm(B.base)+" · TB2 "+r0(tb("tb2"))+" · TB4 "+r0(tb("tb4"))+" €/MWh <span class='mut' style='font-weight:400'>(12-month avg of daily spreads)</span></span></h3>"+
    "<svg class='cmp' id='capZ"+i+"' data-z='"+z+"'></svg><div class='mut' style='font-size:12px'>Monthly capture price per technology, €/MWh; <span style='color:var(--ink)'>┅</span> baseload (mean day-ahead price). Dashed coloured lines: lignite, hydro reservoir. Hover for values.</div>"+
    "<table class='mixtab sortable' id='capT"+i+"'><thead><tr><th data-t='txt'>Technology</th><th>Last 24 h</th><th>"+MON(cm)+" so far</th><th>"+(lm?MON(lm):"Last month")+"</th><th>Last 12 months</th><th>vs baseload</th><th>Output (12 m)</th><th>Output at negative prices</th></tr></thead><tbody>"+rows+
    "<tr class='pin'><td class='mut'>Baseload</td><td>"+(MK.prices[z]?r0(capStats([],MK.prices[z],0,N0).base):"–")+"</td><td>"+r0(cur&&cur.b)+"</td><td>"+r0(lm&&Z[lm].b)+"</td><td><b>"+r0(B.base)+"</b></td><td>100%</td><td></td><td>"+(l12.length?l12.reduce((a,m)=>a+(Z[m].neg||0),0)+" h":"")+"</td></tr></tbody></table>"+
    "<div class='mut' style='font-size:12px'>€/MWh. Last 24 h from the live System data (single-zone countries only). Last 12 months = the 12 latest complete months"+(l12.length<12?" ("+l12.length+" available so far)":"")+", weighted by output.</div></div>"}).join("")}
 // all markets: one technology, months as columns
 S.capt=S.capt||"solar";S.capm=S.capm||"eur";const T=CAPT.find(t=>t[0]===S.capt),sz=selZones(),cm=curMonth();
 const zs=Object.keys(D.zones).filter(z=>(!sz||!sz.size||sz.has(z))&&ms.some(m=>D.zones[z][m]&&D.zones[z][m].t&&D.zones[z][m].t[S.capt]));
 const val=(z,m)=>{const c=D.zones[z][m],t=c&&c.t&&c.t[S.capt];if(!t)return null;return S.capm==="eur"?t[0]:c.b>0?100*t[0]/c.b:null};
 const l12=ms.filter(m=>m<cm).slice(-12);
 const avg=z=>{const A=capAgg(D.zones[z],l12,S.capt);return S.capm==="eur"?A.cap:A.rate!=null?100*A.rate:null};
 const rows=zs.map(z=>({z,a:avg(z)})).sort((p,q)=>(q.a??-1e9)-(p.a??-1e9));
 const all=rows.flatMap(r=>ms.map(m=>val(r.z,m))).filter(v=>v!=null).sort((a,b)=>a-b),top=all.length?all[Math.floor(all.length*.97)]:1,low=all.length?all[0]:0;
 const col=v=>{if(v==null)return"";let t;if(S.capm==="pct"){t=(v-Math.max(0,low))/Math.max(1,top-Math.max(0,low));return"background:"+lerpC(HMPOS,t)+";color:"+(t>.6?"#fff":"#222")}
  const tp=Math.max(50,top);return"background:"+hmColor(v,tp,Math.min(0,low))+";color:"+((v>=0&&v/tp>.6)||(v<0&&low<0&&v/low>.6)?"#fff":"#222")};
 let h="<h2>Monthly capture prices · all markets <span class='mut' style='font:13px system-ui'>· pick a country for every technology in that market</span></h2>"+head;
 h+="<div class='card' style='cursor:default'><h3>"+T[1]+" capture "+(S.capm==="eur"?"price, €/MWh":"rate, % of baseload")+"<span class='seg big'><button data-ct='solar' class='"+(S.capt==="solar"?"on":"")+"'>Solar</button><button data-ct='wind_onshore' class='"+(S.capt==="wind_onshore"?"on":"")+"'>Wind onshore</button><button data-ct='wind_offshore' class='"+(S.capt==="wind_offshore"?"on":"")+"'>Wind offshore</button>&nbsp;<button data-cm='eur' class='"+(S.capm==="eur"?"on":"")+"'>€/MWh</button><button data-cm='pct' class='"+(S.capm==="pct"?"on":"")+"'>% of baseload</button></span></h3>";
 if(!rows.length)h+="<div class='mut'>No zone with "+T[1].toLowerCase()+" output in this selection.</div>";
 else h+="<div class='tw' style='max-height:none'><table class='captab sortable' id='capAll'><thead><tr><th style='text-align:left' data-t='txt'>Zone</th>"+ms.map(m=>"<th>"+MON(m).replace(" ","<br>")+"</th>").join("")+"<th>12 m</th></tr></thead><tbody>"+rows.map(r=>"<tr data-cf='"+(ZONEFLAG[r.z]||"")+"'><td class='z'>"+flagHTML(ZONEFLAG[r.z]||"",6)+" "+r.z+"</td>"+ms.map(m=>{const v=val(r.z,m),c=D.zones[r.z][m],t=c&&c.t&&c.t[S.capt];return"<td style='"+col(v)+"' title='"+r.z+" · "+MON(m)+(m===cm?" (so far)":"")+(t?" · capture "+t[0].toFixed(1)+" €/MWh · baseload "+(c.b!=null?c.b.toFixed(1):"–")+" €/MWh · "+(c.b>0?Math.round(100*t[0]/c.b)+"%":"–")+" · "+Math.round(t[1]).toLocaleString()+" GWh · "+(100*(t[2]||0)).toFixed(1)+"% of output at negative prices":"")+"' data-v='"+(v==null?"":v.toFixed(2))+"'>"+(v==null?"":Math.round(v))+"</td>"}).join("")+"<td class='av' data-v='"+(r.a==null?"":r.a.toFixed(2))+"'>"+r0(r.a)+"</td></tr>").join("")+"</tbody></table></div>";
 h+="<div class='mut' style='font-size:12px'>"+(S.capm==="eur"?"Capture price":"Capture price as a share of the month's baseload (mean day-ahead) price")+" per bidding zone and month"+(ms.includes(cm)?"; the last month is so far":"")+". 12 m = output-weighted over the 12 latest complete months"+(l12.length<12?" ("+l12.length+" so far)":"")+"; zones sorted by it. Hover a cell for details; click a zone for all its technologies; click a column header to sort."+(D.complete?"":" Older months are still being filled in.")+"</div></div>";
 return h}
function keepScroll(fn){const y=window.scrollY,els=[...document.querySelectorAll("#mkt,#main,main,.wrap")].map(e=>[e,e.scrollTop]);fn();els.forEach(([e,t])=>e.scrollTop=t);window.scrollTo(0,y)}
function capRefresh(){const b=$("capbox");if(!b){market();return}keepScroll(()=>{b.innerHTML=capSection();capDraw();makeSortable($("mkt"))})}
// sortable tables: click a header; numbers sort high-to-low first, text A-Z; rows with class 'pin' stay last
S.tsort=S.tsort||{};
// value of a cell for sorting: data-v if set, else the number in the text scaled by its unit (MW/GW, GWh/TWh, k€/M€)
const UNIT={kW:1e-3,MW:1,GW:1e3,TW:1e6,kWh:1e-6,MWh:1e-3,GWh:1,TWh:1e3,"k€":1e3,"M€":1e6};
function cellNum(c){if(!c)return null;let v=c.dataset.v!=null?c.dataset.v:c.textContent.trim();if(v===""||v==="–"||v==="n/a")return null;
 const m=String(v).replace(/,/g,"").replace(/−/g,"-").match(/(-?\d+(?:\.\d+)?)\s*(kWh|MWh|GWh|TWh|kW|MW|GW|TW|k€|M€)?/);if(!m)return null;return parseFloat(m[1])*(UNIT[m[2]]||1)}
function colIsText(t,col){const th=t.tHead.rows[0].cells[col];if(th&&th.dataset.t==="txt")return true;const cs=[...t.tBodies[0].rows].map(r=>r.cells[col]).filter(c=>c&&c.textContent.trim()&&c.textContent.trim()!=="–");
 return cs.filter(c=>cellNum(c)!=null&&/^[\s\d.,−+\-]/.test(c.textContent.trim())).length<cs.length/2}
function sortTab(t,col,dir){const tb=t.tBodies[0];if(!tb||!t.tHead)return;const all=[...tb.rows],rows=all.filter(r=>!r.classList.contains("pin")),pin=all.filter(r=>r.classList.contains("pin"));
 const txt=colIsText(t,col),num=r=>cellNum(r.cells[col]);
 rows.sort((a,b)=>{if(txt)return dir*(a.cells[col]?a.cells[col].textContent.trim():"").localeCompare(b.cells[col]?b.cells[col].textContent.trim():"");const x=num(a),y=num(b);if(x==null&&y==null)return 0;if(x==null)return 1;if(y==null)return-1;return dir*(x-y)});
 rows.concat(pin).forEach(r=>tb.appendChild(r));[...t.tHead.rows[0].cells].forEach((th,i)=>th.dataset.s=i===col?(dir>0?"a":"d"):"")}
// every table with a header row in a tab becomes sortable; its sort is kept (by its headers) when the tab re-renders
function makeSortable(root){if(!root)return;root.querySelectorAll("table").forEach(t=>{if(t.id==="ftab"||!t.tHead||!t.tBodies[0])return;t.classList.add("sortable");
 if(!t.id)t.id=root.id+":"+[...t.tHead.rows[0].cells].map(x=>x.textContent.trim()).join("|")});sortApply(root)}
function sortApply(root){(root||document).querySelectorAll("table.sortable[id]").forEach(t=>{const q=S.tsort[t.id];if(q)sortTab(t,q.col,q.dir)})}
document.addEventListener("click",e=>{const th=e.target.closest("table.sortable th");if(!th)return;const t=th.closest("table"),col=th.cellIndex,q=S.tsort[t.id],txt=colIsText(t,col);
 const dir=q&&q.col===col?-q.dir:(txt?1:-1);S.tsort[t.id]={col,dir};sortTab(t,col,dir)});
function capDraw(){const D=CAP.d;if(!D)return;const ms=D.months||[];document.querySelectorAll("#mkt svg.cmp[data-z]").forEach(sv=>{const Z=D.zones[sv.dataset.z];if(!Z)return;
 const ser=CAPT.filter(t=>t[4]&&ms.some(m=>Z[m]&&Z[m].t&&Z[m].t[t[0]])).map(([id,n,ck,dash])=>({id,label:n,col:"var(--m-"+ck+")",dash,v:ms.map(m=>Z[m]&&Z[m].t&&Z[m].t[id]?Z[m].t[id][0]:null)}));
 ser.push({id:"_b",label:"Baseload",col:"var(--ink)",dash:1,v:ms.map(m=>Z[m]?Z[m].b:null)});
 CMP[sv.id]={series:ser,a:0,b:ms.length-1,fmt:v=>Math.round(v)+"",H:280,right:150,xs:Math.max(1,Math.round(ms.length/8)),xl:k=>MON(ms[k]),tl:k=>MON(ms[k])+(ms[k]===curMonth()?" (so far)":"")+" · €/MWh",dots:1};cmpRender(sv.id)})}

export { capDraw, capRefresh, capSection, fxNote, keepScroll, makeSortable };
