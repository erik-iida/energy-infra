/* Zone colours: bidding zones (data/zones.json) coloured by day-ahead price, TB2 / TB4 or a technology's share of load.
   ES module (spec 3 step 2): imports name what this file needs from other modules, the export list at the end what it offers. */
import { S } from "../../../core/data.js";
import { $, css } from "../../../core/util.js";
import { MK, N0, NT } from "../../../core/feed.js";
import { P, cx, viewBox } from "../canvas.js";
import { BM } from "../tiles.js";
import { legSync, repaint } from "../view.js";
import { HMNEG, HMPOS, lerpC, tbn } from "../../market/heatmap.js";
import { MIXC, SYS, sysData } from "../../system/system.js";
// ---- market overlay: bidding zones coloured by day-ahead price or BESS spread (web/data/zones.json) ----
const MZ={d:null,loading:false,paths:[]};let MO="now";  // the site always opens on the current price
const MOL={now:"Day-ahead price now",avg:"Day-ahead price, last 24 h average",next:"Day-ahead price, tomorrow's average",tb2:"TB2 spread, last 24 h",tb4:"TB4 spread, last 24 h"};
function mzLoad(){if(MZ.d||MZ.loading)return;MZ.loading=true;fetch("data/zones.json",{cache:"no-cache"}).then(r=>r.ok?r.json():null).then(j=>{if(!j)return;MZ.d=j.zones;
 Object.values(MZ.d).forEach(z=>{let a=[1e9,1e9,-1e9,-1e9];z.p.forEach(r=>{for(let i=0;i<r.length;i+=2){a[0]=Math.min(a[0],r[i]);a[1]=Math.min(a[1],r[i+1]);a[2]=Math.max(a[2],r[i]);a[3]=Math.max(a[3],r[i+1])}});z.b=a});repaint()}).catch(()=>{})}
const avgOf=a=>{const o=a.filter(x=>x!=null);return o.length?o.reduce((p,q)=>p+q,0)/o.length:null};
// technology output as % of load (latest hour every material technology has reported, country level: System data)
const SHC={};
function shareVal(z,k){const c=Object.keys(SYS).find(q=>(SYS[q].zones||[]).includes(z))||z.slice(0,2).toLowerCase();if(!SYS[c])return null;
 const D=SHC[c]!==undefined?SHC[c]:(SHC[c]=sysData(c));if(!D||!D.load)return null;let h=D.last;while(h>0&&D.load[h]==null)h--;if(D.load[h]==null||!D.load[h])return null;
 return 100*(D.mix[k]?D.mix[k][h]||0:0)/D.load[h]}
const moTech=()=>MO.startsWith("s:")?MO.slice(2):null;
function moLabel(){const k=moTech();if(!k)return MOL[MO];const t=MIXC.find(m=>m[0]===k);return(t?t[1]:k)+" output, % of load, latest hour"}
function moVal(z,mode){mode=mode||MO;if(mode.startsWith("s:"))return shareVal(z,mode.slice(2));const p=MK&&MK.prices&&MK.prices[z];if(!p)return null;
 if(mode==="now")return p[N0];if(mode==="avg")return avgOf(p.slice(0,N0+1));if(mode==="next")return avgOf(p.slice(N0+1,NT));
 return tbn(p.slice(0,N0+1),mode==="tb2"?2:4)}
function moScale(){if(!MZ.d)return null;const v=Object.keys(MZ.d).map(z=>moVal(z)).filter(x=>x!=null).sort((a,b)=>a-b);if(!v.length)return null;
 if(moTech()){const top=Math.max(10,Math.ceil(v[Math.floor((v.length-1)*.97)]/10)*10);return{top,lo:0,low:0,min:v[0],max:v[v.length-1]}}
 const top=v[Math.floor((v.length-1)*.97)],lo=v[0]<0?0:Math.floor(v[0]/10)*10;return{top:Math.max(lo+10,top),lo,low:Math.min(0,v[0]),min:v[0],max:v[v.length-1]}}
const moCol=(v,sc)=>moTech()?css("--m-"+moTech()):v<0?lerpC(HMNEG,sc.low<0?v/sc.low:1):lerpC(HMPOS,(v-sc.lo)/(sc.top-sc.lo));
function moBar(sc){const b=$("mobar");if(MO==="off"||!sc){b.innerHTML="";return}
 if(moTech()){b.innerHTML="<div style='display:flex;flex-direction:column;gap:2px'><span>"+moLabel()+"</span><span style='display:flex;align-items:center'>0<i style='background:linear-gradient(90deg,transparent,"+css("--m-"+moTech())+")'></i>"+sc.top+"+ %</span><span>Whole country (System data); above 100 % = more than the country used</span></div>";return}
 b.innerHTML="<span>"+MOL[MO]+"</span><br>"+(sc.low<0?"<i style='width:36px;background:linear-gradient(90deg,rgb("+HMNEG[1].join(",")+"),rgb("+HMNEG[0].join(",")+"))'></i>"+Math.round(sc.low):"")+"<span>"+Math.round(sc.lo)+"</span><i style='background:linear-gradient(90deg,"+HMPOS.map(c=>"rgb("+c.join(",")+")").join(",")+")'></i><span>"+Math.round(sc.top)+"+ €/MWh</span>"+(MK&&MK.price_source&&MK.price_source.GB?"<br><span>GB: Elexon Market Index (traded-price index, converted from GBP)</span>":"")}
function moDraw(){MZ.paths=[];if(MO==="off"||!MK){moBar(null);return}mzLoad();if(!MZ.d)return;const sc=moScale();moBar(sc);if(!sc){$("mobar").innerHTML="<span>"+moLabel()+": not published yet</span>";return}const v=viewBox(),lab=[];
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
function moTip(z){if(moTech()){const v=moVal(z);return z+" · "+moLabel().replace(", latest hour","")+": "+(v==null?"no data":Math.round(v)+" %")+" (latest hour, whole country)"}const p=MK.prices[z],f=v=>v==null?"–":Math.round(v);return z+" · now "+f(moVal(z,"now"))+" · 24 h avg "+f(moVal(z,"avg"))+(p&&p.slice(N0+1).some(x=>x!=null)?" · tomorrow "+f(moVal(z,"next")):"")+" €/MWh · TB2 "+f(moVal(z,"tb2"))+" · TB4 "+f(moVal(z,"tb4"))+(p?"":" · no openly licensed price")}
function moSet(m){MO=m;if(m!=="off")S.moLast=m;document.querySelectorAll("#mosel button").forEach(b=>b.classList.toggle("on",b.dataset.mo===MO));
 const sel=$("mocol");if(sel){if(sel.options.length<3){const og=sel.querySelector("optgroup");MIXC.forEach(([k,n])=>{const o=document.createElement("option");o.value="s:"+k;o.textContent=n;og.appendChild(o)})}
  if(m!=="off")sel.value=m.startsWith("s:")?m:"price";$("mosel").style.display=m.startsWith("s:")?"none":""}
 legSync();repaint()}

export { MO, MZ, moDraw, moSet, moTip, mzLoad };
