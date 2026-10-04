/* Zone colours: bidding zones (data/zones.json) coloured by day-ahead price, TB2 / TB4, a technology's share of load, wind /
   solar / solar + wind share of load or self-sufficiency (all generation / load), now, over 24 h, tomorrow (prices) or over
   the last 7 / 30 / 365 days (browse/agg.json from the store).
   ES module (spec 3 step 2): imports name what this file needs from other modules, the export list at the end what it offers. */
import { S } from "../../../core/data.js";
import { $, css } from "../../../core/util.js";
import { MK, N0, NT, tbn } from "../../../core/feed.js";
import { MIXC, SYS, sysData } from "../../../core/sysdata.js";
import { HMNEG, HMPOS, lerpC } from "../../../core/colours.js";
import { P, cx, viewBox } from "../canvas.js";
import { BM } from "../tiles.js";
import { legSync, repaint } from "../view.js";
// ---- market overlay: bidding zones coloured by day-ahead price or BESS spread (web/data/zones.json) ----
const MZ={d:null,loading:false,paths:[]};
// what colours the zones: MO = the metric (price, tb2, tb4, s:<tech>, s:wind, s:sol, s:vre, s:self, or "off"), MWIN = the
// averaging period (now, d1 = last 24 h, next = tomorrow, w1 / m1 / y1 = last 7 / 30 / 365 days from browse/agg.json)
let MO="price",MWIN="now";  // the site always opens on the current price
const MONAME={price:"Day-ahead price",tb2:"TB2 spread",tb4:"TB4 spread","s:wind":"Wind output (onshore + offshore)","s:sol":"Solar output","s:vre":"Solar + wind output","s:self":"Self-sufficiency"};
const WINNAME={now:"now",d1:"last 24 h",next:"tomorrow",w1:"last 7 days",m1:"last 30 days",y1:"last 365 days"};
const LEGACY={now:["price","now"],avg:["price","d1"],next:["price","next"],tb2:["tb2","d1"],tb4:["tb4","d1"]};
const AGG={d:null,loading:false,failed:false};
function aggLoad(){if(AGG.d||AGG.loading||AGG.failed)return;AGG.loading=true;fetch("data/browse/agg.json",{cache:"no-cache"}).then(r=>r.ok?r.json():null).then(j=>{AGG.loading=false;if(j&&j.zones)AGG.d=j;else AGG.failed=true;repaint()}).catch(()=>{AGG.loading=false;AGG.failed=true;repaint()})}
const isLong=w=>w==="w1"||w==="m1"||w==="y1";
const AGGKEY={price:"price",tb2:"tb2",tb4:"tb4","s:wind":"wind","s:sol":"solar","s:vre":"vre","s:self":"self"};
// which periods make sense for a metric: prices have a "tomorrow", shares do not; the long windows exist only for the
// metrics the daily store carries (prices, wind, solar, wind + solar, self-sufficiency), not for every technology
function winOk(m,w){if(w==="next")return m==="price"||m==="tb2"||m==="tb4";if(isLong(w))return m in AGGKEY;return true}
function mzLoad(){if(MZ.d||MZ.loading)return;MZ.loading=true;fetch("data/zones.json",{cache:"no-cache"}).then(r=>r.ok?r.json():null).then(j=>{if(!j)return;MZ.d=j.zones;
 Object.values(MZ.d).forEach(z=>{let a=[1e9,1e9,-1e9,-1e9];z.p.forEach(r=>{for(let i=0;i<r.length;i+=2){a[0]=Math.min(a[0],r[i]);a[1]=Math.min(a[1],r[i+1]);a[2]=Math.max(a[2],r[i]);a[3]=Math.max(a[3],r[i+1])}});z.b=a});repaint()}).catch(()=>{})}
const avgOf=a=>{const o=a.filter(x=>x!=null);return o.length?o.reduce((p,q)=>p+q,0)/o.length:null};
// technology output as % of load from the System data (country level): latest hour, or the last 24 h as energy
const SHC={};
function sysOf(z){const c=Object.keys(SYS).find(q=>(SYS[q].zones||[]).includes(z))||z.slice(0,2).toLowerCase();if(!SYS[c])return null;return SHC[c]!==undefined?SHC[c]:(SHC[c]=sysData(c))}
const techMW=(D,k,h)=>k==="wind"?D.mix.won[h]+D.mix.woff[h]:k==="vre"?D.mix.won[h]+D.mix.woff[h]+D.mix.sol[h]:k==="self"?D.gen[h]:(D.mix[k]?D.mix[k][h]||0:0);
function shareVal(z,k,win){const D=sysOf(z);if(!D||!D.load)return null;
 if(win==="d1"){let g=0,l=0;for(let h=0;h<=D.last;h++)if(D.load[h]){g+=techMW(D,k,h);l+=D.load[h]}return l?100*g/l:null}
 let h=D.last;while(h>0&&D.load[h]==null)h--;if(D.load[h]==null||!D.load[h])return null;return 100*techMW(D,k,h)/D.load[h]}
const moTech=()=>MO.startsWith("s:")?MO.slice(2):null;
function moLabel(){const k=moTech();const base=MONAME[MO]||(k?((MIXC.find(m=>m[0]===k)||[,k])[1])+" output":MO);return base+(k?", % of load":"")+", "+WINNAME[MWIN]}
function moVal(z,mode,win){mode=mode||MO;win=win||MWIN;if(mode==="off")return null;
 if(isLong(win)){if(!AGG.d)return null;const e=AGG.d.zones[z];return e&&e[win]?(e[win][AGGKEY[mode]]??null):null}
 if(mode.startsWith("s:"))return shareVal(z,mode.slice(2),win);
 const p=MK&&MK.prices&&MK.prices[z];if(!p)return null;
 if(mode==="price")return win==="now"?p[N0]:win==="next"?avgOf(p.slice(N0+1,NT)):avgOf(p.slice(0,N0+1));
 const seg=win==="next"?p.slice(N0+1,NT):p.slice(0,N0+1);return tbn(seg,mode==="tb2"?2:4)}
function moScale(){if(!MZ.d)return null;const v=Object.keys(MZ.d).map(z=>moVal(z)).filter(x=>x!=null).sort((a,b)=>a-b);if(!v.length)return null;
 if(moTech()){const top=Math.max(10,Math.ceil(v[Math.floor((v.length-1)*.97)]/10)*10);return{top,lo:0,low:0,min:v[0],max:v[v.length-1]}}
 const top=v[Math.floor((v.length-1)*.97)],lo=v[0]<0?0:Math.floor(v[0]/10)*10;return{top:Math.max(lo+10,top),lo,low:Math.min(0,v[0]),min:v[0],max:v[v.length-1]}}
const TECHCOL={wind:"--m-won",vre:"--m-sol",self:"--acc"};const techCss=k=>css(TECHCOL[k]||("--m-"+k));
const moCol=(v,sc)=>moTech()?techCss(moTech()):v<0?lerpC(HMNEG,sc.low<0?v/sc.low:1):lerpC(HMPOS,(v-sc.lo)/(sc.top-sc.lo));
function moBar(sc){const b=$("mobar");if(MO==="off"||!sc){b.innerHTML="";return}
 if(moTech()){b.innerHTML="<div style='display:flex;flex-direction:column;gap:2px'><span>"+moLabel()+"</span><span style='display:flex;align-items:center'>0<i style='background:linear-gradient(90deg,transparent,"+techCss(moTech())+")'></i>"+sc.top+"+ %</span><span>"+(isLong(MWIN)?"Per bidding zone, energy over the period (store)":"Whole country (System data)")+"; above 100 % = more than the country used</span></div>";return}
 b.innerHTML="<span>"+moLabel()+"</span><br>"+(sc.low<0?"<i style='width:36px;background:linear-gradient(90deg,rgb("+HMNEG[1].join(",")+"),rgb("+HMNEG[0].join(",")+"))'></i>"+Math.round(sc.low):"")+"<span>"+Math.round(sc.lo)+"</span><i style='background:linear-gradient(90deg,"+HMPOS.map(c=>"rgb("+c.join(",")+")").join(",")+")'></i><span>"+Math.round(sc.top)+"+ €/MWh</span>"+(MK&&MK.price_source&&MK.price_source.GB?"<br><span>GB: Elexon Market Index (traded-price index, converted from GBP)</span>":"")}
function moDraw(){MZ.paths=[];if(MO==="off"||!MK){moBar(null);return}mzLoad();if(isLong(MWIN))aggLoad();if(!MZ.d)return;const sc=moScale();moBar(sc);
 if(!sc){$("mobar").innerHTML="<span>"+moLabel()+": "+(isLong(MWIN)?(AGG.failed?"no store export for this period yet":AGG.d?"no data":"loading…"):"not published yet")+"</span>";return}const v=viewBox(),lab=[];
 cx.save();cx.lineJoin="round";
 for(const[z,Z_]of Object.entries(MZ.d)){const b=Z_.b;if(b[2]<v[0]||b[0]>v[2]||b[3]<v[1]||b[1]>v[3])continue;const val=moVal(z);
  const p=new Path2D();for(const r of Z_.p){let lx=1e9,ly=1e9;for(let i=0;i<r.length;i+=2){const[x,y]=P(r[i],r[i+1]);if(!i){p.moveTo(x,y);lx=x;ly=y}else if(Math.abs(x-lx)+Math.abs(y-ly)>1||i>=r.length-2){p.lineTo(x,y);lx=x;ly=y}}p.closePath()}
  MZ.paths.push([p,z]);const on=S.mzh===z;
  if(val!=null){const t=val<0?Math.min(1,val/(sc.low||-1)):Math.max(0,Math.min(1,(val-sc.lo)/(sc.top-sc.lo)));  // low prices fade towards transparent
   cx.globalAlpha=on?.85:(BM()==="simple"?.1:.06)+(BM()==="simple"?.65:.6)*Math.pow(t,.85);cx.fillStyle=moCol(val,sc);cx.fill(p)}
  else{cx.globalAlpha=.35;cx.fillStyle=css("--panel");cx.fill(p)}
  cx.globalAlpha=on?1:.85;cx.strokeStyle=on?css("--ink"):"rgba(255,255,255,.85)";cx.lineWidth=on?2:.8;cx.stroke(p);
  const[x0,y0]=P(b[0],b[3]),[x1,y1]=P(b[2],b[1]);if(x1-x0>34&&y1-y0>16){const[cxp,cyp]=P(Z_.c[0],Z_.c[1]);lab.push([cxp,cyp,z,val,x1-x0])}}
 cx.globalAlpha=1;cx.textAlign="center";cx.lineWidth=3;cx.strokeStyle="rgba(0,0,0,.6)";cx.fillStyle="#fff";
 lab.forEach(([x,y,z,val,w])=>{const t=val==null?"–":Math.round(val)+(moTech()?"%":"");cx.font="700 12px sans-serif";cx.strokeText(t,x,y+4);cx.fillText(t,x,y+4);
  if(w>70){cx.font="10px sans-serif";cx.strokeText(z,x,y-9);cx.fillText(z,x,y-9)}});
 cx.restore()}
function moTip(z){const f=v=>v==null?"–":Math.round(v)+(moTech()?" %":"");const cur=moVal(z);let t=z+" · "+moLabel()+": "+(cur==null?"no data":f(cur));
 if(isLong(MWIN)&&AGG.d&&AGG.d.zones[z]&&AGG.d.zones[z][MWIN]){const n=AGG.d.zones[z][MWIN]["n_"+AGGKEY[MO]];if(n)t+=" ("+n+" days)"}
 if(!moTech()){const p=MK.prices[z];t+=" · now "+f(moVal(z,"price","now"))+" · 24 h "+f(moVal(z,"price","d1"))+(p&&p.slice(N0+1).some(x=>x!=null)?" · tomorrow "+f(moVal(z,"price","next")):"")+" · TB2 "+f(moVal(z,"tb2","d1"))+" · TB4 "+f(moVal(z,"tb4","d1"))}
 else t+=(isLong(MWIN)?"":" ("+WINNAME[MWIN]+", whole country)");return t}
function moSync(){document.querySelectorAll("#mosel button").forEach(b=>{const w=b.dataset.mw;b.classList.toggle("on",w===MWIN);b.disabled=MO!=="off"&&!winOk(MO,w);b.title=b.disabled?(w==="next"?"tomorrow exists for prices only":"longer periods exist for prices, wind, solar, solar + wind and self-sufficiency"):""});
 const sel=$("mocol");if(sel){if(!sel.querySelector("option[value='s:nuc']")){const og=sel.querySelectorAll("optgroup")[2];MIXC.forEach(([k,n])=>{const o=document.createElement("option");o.value="s:"+k;o.textContent=n;og.appendChild(o)})}if(MO!=="off")sel.value=MO}}
function moSet(m){if(LEGACY[m]){[m,MWIN]=LEGACY[m]}MO=m;if(m!=="off"){S.moLast=m;if(!winOk(MO,MWIN))MWIN="now"}moSync();legSync();repaint()}
function moWin(w){MWIN=w;if(MO!=="off"&&!winOk(MO,w))MWIN="now";S.mwLast=MWIN;moSync();repaint()}

export { MO, MWIN, MZ, moDraw, moSet, moTip, moWin, mzLoad };
