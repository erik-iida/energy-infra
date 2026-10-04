/* Market tab: price heatmap of every bidding zone x hour, with TB2 / TB4 and the optional spark column.
   ES module (spec 3 step 2): imports name what this file needs from other modules, the export list at the end what it offers. */
import { $ } from "../../core/util.js";
import { MK, dl, hl } from "../../core/feed.js";
import { ZONEFLAG, flagSVG } from "../../core/flags.js";
import { dtip } from "../../core/chart.js";
import { cmpHover, cmpLeave } from "../../core/cmp.js";
// ---- price heatmap: every bidding zone (rows, sorted by mean) x hour (columns) ----
// One warm sequential hue for prices >= 0 (light -> dark), a separate cool hue for negative prices.
const HMPOS=[[253,238,220],[250,201,148],[240,145,82],[214,88,38],[160,48,20],[96,24,12]],HMNEG=[[214,232,250],[42,120,214]];
const lerpC=(R,t)=>{t=Math.max(0,Math.min(1,t))*(R.length-1);const i=Math.min(R.length-2,Math.floor(t)),f=t-i;return"rgb("+[0,1,2].map(k=>Math.round(R[i][k]+(R[i+1][k]-R[i][k])*f)).join(",")+")"};
const HM={};
function hmColor(v,top,low){return v<0?lerpC(HMNEG,low<0?v/low:1):lerpC(HMPOS,v/top)}
// TBn: mean of the n highest hourly prices minus mean of the n lowest (BESS arbitrage indication); needs 20+ priced hours
function tbn(v,n){const o=v.filter(x=>x!=null).sort((a,b)=>a-b);if(o.length<20)return null;const m=a=>a.reduce((p,q)=>p+q,0)/a.length;return m(o.slice(-n))-m(o.slice(0,n))}
const HMTB=[122,166,210],HMTW=42;
function hmRender(id){const C=HM[id],sv=document.getElementById(id);if(!sv)return;const SPK=MK.spark&&MK.spark.zones,SPW=C.a===0?"past":"next",W=sv.clientWidth||700,L=SPK?258:214,R=58,T=4,rh=14,B=22,sk=(C.sort==="sp"&&!SPK)?"m":(C.sort||"m");
 const rows=C.zones.map(z=>{const v=MK.prices[z].slice(C.a,C.b+1),ok=v.filter(x=>x!=null);return{z,v,m:ok.length?ok.reduce((a,b)=>a+b,0)/ok.length:null,tb2:tbn(v,2),tb4:tbn(v,4),sp:SPK&&SPK[z]&&SPK[z][SPW]?SPK[z][SPW].top4:null}}).filter(r=>r.m!=null).sort((p,q)=>(q[sk]??-1e9)-(p[sk]??-1e9));
 const tbmax=Math.max(1,...rows.map(r=>r.tb4||0));C.tbmax=tbmax;
 const all=rows.flatMap(r=>r.v.filter(x=>x!=null)).sort((a,b)=>a-b);if(!all.length){sv.innerHTML="<text class='tl' x='"+W/2+"' y='20' text-anchor='middle'>No prices for this period yet</text>";sv.style.height="30px";return}
 const top=Math.max(50,all[Math.floor(all.length*.97)]),low=Math.min(0,all[0]),n=C.b-C.a+1,cw=(W-L-R)/n,H=T+rows.length*rh+B;C.rows=rows;C.top=top;C.low=low;C.L=L;C.R=R;C.T=T;C.rh=rh;C.cw=cw;C.W=W;
 sv.setAttribute("viewBox","0 0 "+W+" "+H);sv.style.height=H+"px";let s="";
 rows.forEach((r,i)=>{const y=T+i*rh,on=C.sel&&C.sel.has(r.z);if(on)s+="<rect x='0' y='"+y+"' width='"+(W-R+40)+"' height='"+rh+"' fill='var(--acc)' opacity='.13'/>";s+=flagSVG(ZONEFLAG[r.z]||"",8,y+rh/2,5)+"<text x='18' y='"+(y+rh-3.5)+"' font-size='11' fill='var(--ink)' font-weight='"+(on?700:400)+"'>"+r.z+"</text>";
  [["tb2",HMTB[0]],["tb4",HMTB[1]]].forEach(([q,x0])=>{const t=r[q];if(t==null)return;s+="<rect x='"+x0+"' y='"+(y+2)+"' width='"+(HMTW-4)*Math.min(1,t/tbmax)+"' height='"+(rh-4)+"' fill='var(--m-sol)' opacity='.45' rx='1'/><text x='"+(x0+HMTW-6)+"' y='"+(y+rh-3.5)+"' font-size='11' text-anchor='end' fill='var(--ink)'"+(sk===q?" font-weight='700'":"")+">"+Math.round(t)+"</text>"});
  if(SPK&&r.sp!=null)s+="<text x='"+(HMTB[2]+HMTW-6)+"' y='"+(y+rh-3.5)+"' font-size='11' text-anchor='end' fill='"+(r.sp<0?"var(--exp)":"var(--ink)")+"'"+(sk==="sp"?" font-weight='700'":"")+">"+Math.round(r.sp)+"</text>";
  r.v.forEach((v,k)=>{if(v!=null)s+="<rect x='"+(L+k*cw).toFixed(1)+"' y='"+(y+.5)+"' width='"+Math.max(.5,cw-1).toFixed(1)+"' height='"+(rh-1)+"' fill='"+hmColor(v,top,low)+"'/>"});
  s+="<text x='"+(W-R+6)+"' y='"+(y+rh-3.5)+"' font-size='11' fill='var(--mut)'>"+Math.round(r.m)+"</text>"});
 for(let k=0;k<n;k+=6)s+="<text class='tl' x='"+(L+k*cw+cw/2)+"' y='"+(H-6)+"' text-anchor='middle'>"+hl(C.a+k)+"</text>";
 s+="<text class='tl' x='"+(W-R+6)+"' y='"+(H-6)+"'"+(sk==="m"?" font-weight='700'":"")+">mean</text><text class='tl' x='"+(HMTB[0]+HMTW-6)+"' y='"+(H-6)+"' text-anchor='end'"+(sk==="tb2"?" font-weight='700'":"")+">TB2</text><text class='tl' x='"+(HMTB[1]+HMTW-6)+"' y='"+(H-6)+"' text-anchor='end'"+(sk==="tb4"?" font-weight='700'":"")+">TB4</text>"+(SPK?"<text class='tl' x='"+(HMTB[2]+HMTW-6)+"' y='"+(H-6)+"' text-anchor='end'"+(sk==="sp"?" font-weight='700'":"")+">Spark</text>":"");
 if(C.hk!=null&&C.hr!=null)s+="<rect x='"+(L+(C.hk-C.a)*cw)+"' y='"+(T+C.hr*rh)+"' width='"+cw+"' height='"+rh+"' fill='none' stroke='var(--ink)' stroke-width='1.5'/>";
 sv.innerHTML=s;const lg=document.getElementById(id+"L");
 if(lg)lg.innerHTML="<span style='display:inline-block;width:110px;height:10px;vertical-align:middle;border-radius:2px;background:linear-gradient(90deg,"+HMPOS.map(c=>"rgb("+c.join(",")+")").join(",")+")'></span> 0 – "+Math.round(top)+"+ €/MWh"+(low<0?" &nbsp;<span style='display:inline-block;width:40px;height:10px;vertical-align:middle;border-radius:2px;background:linear-gradient(90deg,rgb("+HMNEG[0].join(",")+"),rgb("+HMNEG[1].join(",")+"))'></span> negative (down to "+Math.round(low)+")":"")}
function hmHover(e,sv){const C=HM[sv.id];if(!C||!C.rows)return;const r=sv.getBoundingClientRect(),px=(e.clientX-r.left)*C.W/r.width,py=(e.clientY-r.top)*C.W/r.width;
 const k=Math.floor((px-C.L)/C.cw),i=Math.floor((py-C.T)/C.rh);
 if(i>=0&&i<C.rows.length&&px>=HMTB[0]&&px<HMTB[1]+HMTW){const row=C.rows[i],o=row.v.filter(x=>x!=null).sort((a,b)=>a-b),m=a=>a.length?Math.round(a.reduce((p,q)=>p+q,0)/a.length):"–";if(C.hk!=null){C.hk=C.hr=null;hmRender(sv.id)}
  dtip(e,row.z+" · BESS spread over the "+(o.length)+" h shown\nTB2 "+(row.tb2==null?"–":Math.round(row.tb2))+" €/MWh = top 2 h avg "+m(o.slice(-2))+" − bottom 2 h avg "+m(o.slice(0,2))+"\nTB4 "+(row.tb4==null?"–":Math.round(row.tb4))+" €/MWh = top 4 h avg "+m(o.slice(-4))+" − bottom 4 h avg "+m(o.slice(0,4)));return}
 if(k<0||k>C.b-C.a||i<0||i>=C.rows.length){$("dtip").style.display="none";return}
 if(C.hk!==C.a+k||C.hr!==i){C.hk=C.a+k;C.hr=i;hmRender(sv.id)}const row=C.rows[i],v=row.v[k];
 const rank=C.rows.map(q=>q.v[k]).filter(x=>x!=null).sort((a,b)=>b-a);dtip(e,row.z+" · "+dl(C.a+k)+"\n"+(v==null?"no price":Math.round(v)+" €/MWh · rank "+(rank.indexOf(v)+1)+" of "+rank.length)+"\nmean over the period "+Math.round(row.m)+" €/MWh"+(row.tb2!=null?" · TB2 "+Math.round(row.tb2)+" · TB4 "+Math.round(row.tb4):""))}
document.addEventListener("mousemove",e=>{const sv=e.target.closest&&e.target.closest("svg.hm");if(sv)hmHover(e,sv)});
document.addEventListener("mouseout",e=>{const sv=e.target.closest&&e.target.closest("svg.hm");if(sv&&!sv.contains(e.relatedTarget)){const C=HM[sv.id];if(C){C.hk=C.hr=null;hmRender(sv.id)}$("dtip").style.display="none"}});
document.addEventListener("mousemove",e=>{const sv=e.target.closest&&e.target.closest("svg.cmp");if(sv)cmpHover(e,sv)});
document.addEventListener("mouseout",e=>{const sv=e.target.closest&&e.target.closest("svg.cmp");if(sv&&!sv.contains(e.relatedTarget))cmpLeave(sv)});

export { HM, HMNEG, HMPOS, hmColor, hmRender, lerpC, tbn };
