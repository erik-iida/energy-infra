/* Map and side-pane events: country picker, list / breadcrumb clicks, pointer, wheel, pinch and keyboard on the canvas, zoom buttons.
   ES module (spec 3 step 2): imports name what this file needs from other modules, the export list at the end what it offers. */
import { COUNTRIES, F, GROUPS, REGIONS, RGOF, S, Z } from "../../core/data.js";
import { $, fmt } from "../../core/util.js";
import { K_DEF } from "../../core/wake.js";
import { cur, curWind } from "../../core/feed.js";
import { SYS } from "../../core/sysdata.js";
import { CFLAG, ZONEFLAG, csSync, flagSel } from "../../core/flags.js";
import { draw, go, tab } from "../../core/router.js";
import { H0, V, W0, clampV, cv, cx, farmBox, fit, mercInv, mercY } from "./canvas.js";
import { attrib, bmSet } from "./tiles.js";
import { gasHit, gasTip } from "./layers/gas.js";
import { HID, LCAT, anim, catOn, flyTo, legSync, repaint, zoomAt } from "./view.js";
import { bathyColour } from "./layers/bathy.js";
import { MZ, moSet, moTip, moWin } from "./layers/zones.js";
import { sidebar } from "./sidebar.js";
/* ---------- events ---------- */
$("C").innerHTML="<option value=''>World</option><optgroup label='Groups'>"+Object.keys(GROUPS).map(g=>"<option value='"+g+"'>"+g+"</option>").join("")+"</optgroup>"+REGIONS.map(r=>"<optgroup label='"+r+"'><option value='"+r+"'>All of "+r+"</option>"+COUNTRIES.filter(c=>RGOF[c]===r).map(c=>"<option>"+c+"</option>").join("")+"</optgroup>").join("");$("C").onchange=()=>go($("C").value||null,null);$("C2").innerHTML=$("C").innerHTML;$("C2").onchange=()=>go($("C2").value||null,null);flagSel($("C"));flagSel($("C2"));csSync();
$("list").onclick=e=>{const b=e.target.closest("button");if(!b)return;if(b.dataset.c)go(b.dataset.c,null);else{const i=+b.dataset.i;go(F[i].c,i)}};
$("crumb").onclick=e=>{const a=e.target.closest("a");if(!a)return;a.dataset.go==="e"?go(null,null):a.dataset.go==="r"?go(RGOF[S.c],null):go(S.c,null)};
["U","D","K"].forEach(i=>$(i).oninput=draw);$("M").onchange=()=>{$("K").value=K_DEF[$("M").value]||.04;$("kl").textContent=$("M").value==="t"?"Wake expansion A":"Wake decay k";draw()};$("Z").onchange=()=>{legSync();draw()};$("LV").onchange=draw;if(F.some(f=>f.on))$("lon").style.display="";
function legFold(open){$("legb").hidden=!open;$("legt").setAttribute("aria-expanded",String(open));$("legc").textContent=open?"▾":"▸";try{localStorage.setItem("wm-legend",open?"1":"0")}catch(e){}}
$("legt").onclick=()=>legFold($("legb").hidden);legFold(true);  // the legend lives in the right-hand pane now, always open
$("leg").onchange=e=>{if(e.target.id==="mocol")moSet(e.target.value)};
$("leg").onclick=e=>{const mb=e.target.closest("#mosel button");if(mb){if(!mb.disabled)moWin(mb.dataset.mw);return}if(e.target.closest("#mocol"))return;
 const lc=e.target.closest(".lc");if(lc){const c=lc.dataset.c,on=catOn(c);
  if(c==="price")moSet(on?"off":(S.moLast||"price"));else if(c==="zones"){$("Z").checked=!on;if(!on)LCAT.zones.forEach(k=>HID.delete(k))}else if(c==="grid"){$("GR").checked=!on;if(!on)LCAT.grid.forEach(k=>HID.delete(k));$("GR").onchange()}
  else if(c==="depth"){$("BY").checked=!on;on?HID.add("depth"):HID.delete("depth");$("BY").onchange()}else LCAT[c].forEach(k=>on?HID.add(k):HID.delete(k));
  try{localStorage.setItem("wm-hide",JSON.stringify([...HID]))}catch(e){}legSync();S.hover=-1;draw();return}
 const b=e.target.closest(".lk");if(!b)return;const k=b.dataset.k;
 if(k==="depth"){$("BY").checked=!$("BY").checked;$("BY").checked?HID.delete(k):HID.add(k);try{localStorage.setItem("wm-hide",JSON.stringify([...HID]))}catch(e){}$("BY").onchange()}
 else{if(["uc","cs","pl"].includes(k)&&!$("Z").checked){$("Z").checked=true;HID.delete(k)}else HID.has(k)?HID.delete(k):HID.add(k);
  try{localStorage.setItem("wm-hide",JSON.stringify([...HID]))}catch(e){}}
 legSync();S.hover=-1;repaint()};
if(HID.has("depth")){$("BY").checked=false;$("bys").style.display="none"}
$("bmbtn").onclick=()=>{const l=$("bmlist"),o=l.hidden;l.hidden=!o;$("bmbtn").setAttribute("aria-expanded",String(o))};
document.querySelectorAll(".bmo").forEach(b=>b.onclick=()=>{bmSet(b.dataset.bm);$("bmlist").hidden=true;$("bmbtn").setAttribute("aria-expanded","false")});
document.addEventListener("keydown",e=>{if(e.key==="Escape"&&!$("bmlist").hidden){$("bmlist").hidden=true;$("bmbtn").setAttribute("aria-expanded","false")}});
try{$("HS").checked=localStorage.getItem("wm-hs")==="1";bmSet(localStorage.getItem("wm-basemap")||"simple")}catch(e){bmSet("simple")}
$("HS").onchange=()=>{try{localStorage.setItem("wm-hs",$("HS").checked?"1":"0")}catch(e){}attrib();repaint()};attrib();
legSync();
$("GR").onchange=()=>{legSync();repaint()};
$("BY").onchange=()=>{S.bathyKey="";$("bys").style.display=$("BY").checked?"block":"none";legSync();draw()};$("BD").oninput=()=>{bathyColour();repaint()};bathyColour();
$("FM").onchange=()=>{S.fm=$("FM").value;draw()};
function hit(e){const r=cv.getBoundingClientRect(),x=e.clientX-r.left,y=e.clientY-r.top;let b=-1,bd=1e9;S.pts.forEach(p=>{const d=Math.hypot(p[0]-x,p[1]-y);if(d<p[2]+6&&d<bd){bd=d;b=p[3]}});
 // paths are built in CSS pixels: test them with an identity transform at the cursor's CSS position (works at any display scaling)
 cx.save();cx.setTransform(1,0,0,1,0,0);
 if(b<0)for(const[p,i]of S.fp)if(cx.isPointInPath(p,x,y)){b=i;break}
 let zh=-1;if(b<0)for(const[p,i]of S.zp)if(cx.isPointInPath(p,x,y)&&(zh<0||Z[i].a<Z[zh].a))zh=i;
 let mz=null;if(b<0&&zh<0)for(const[p,z]of MZ.paths)if(cx.isPointInPath(p,x,y)){mz=z;break}cx.restore();S.mzhit=mz;return[b,zh,x,y]}
function zoneToSystem(z){const c=ZONEFLAG[z];if(!c||!SYS[c])return;S.sys=c;const nm=Object.keys(CFLAG).find(n=>CFLAG[n]===c&&COUNTRIES.includes(n));S.c=nm||null;$("tip").style.display="none";tab("sys");scrollTo(0,0)}
function selectFarm(i){S.farm=i;S.c=F[i].c;S.hover=-1;$("tip").style.display="none";flyTo(fit(farmBox(F[i]),.12));sidebar()}
const ptr=new Map();let drag=null;cv.style.touchAction="none";
cv.onpointerdown=e=>{cv.setPointerCapture(e.pointerId);ptr.set(e.pointerId,[e.clientX,e.clientY]);cancelAnimationFrame(anim);
 if(ptr.size===1)drag={x:e.clientX,y:e.clientY,lon:V.lon,lat:V.lat,moved:0};
 else if(ptr.size===2){const[a,b]=[...ptr.values()];drag={pinch:Math.hypot(a[0]-b[0],a[1]-b[1]),moved:99}}};
cv.onpointermove=e=>{if(ptr.has(e.pointerId))ptr.set(e.pointerId,[e.clientX,e.clientY]);
 if(drag){$("tip").style.display="none";
  if(ptr.size===2&&drag.pinch){const[a,b]=[...ptr.values()],dd=Math.hypot(a[0]-b[0],a[1]-b[1]),r=cv.getBoundingClientRect();zoomAt((a[0]+b[0])/2-r.left,(a[1]+b[1])/2-r.top,dd/drag.pinch);drag.pinch=dd;return}
  if(drag.lon!=null){const dx=e.clientX-drag.x,dy=e.clientY-drag.y;drag.moved=Math.max(drag.moved,Math.abs(dx)+Math.abs(dy));V.lon=drag.lon-dx/V.s;V.lat=mercInv(mercY(drag.lat)+dy/V.s);clampV();cv.style.cursor="grabbing";repaint()}return}
 const[b,zh,x,y]=hit(e);if(b!==S.hover||zh!==S.zh){S.hover=b;S.zh=zh;repaint()}const t=$("tip");cv.style.cursor=b>=0?"pointer":"grab";
 const gi=b<0?gasHit(x,y):-1;if(gi>=0){t.style.display="block";t.style.left=Math.min(x+12,cv.clientWidth-260)+"px";t.style.top=y+12+"px";t.textContent=gasTip(gi);return}
 if(b>=0||zh>=0){t.style.display="block";t.style.left=Math.min(x+12,cv.clientWidth-260)+"px";t.style.top=y+12+"px";
  if(b>=0){const f=F[b],[U,D]=curWind(f),r=cur(f);t.textContent=f.n+" ("+f.c+") · "+fmt(r.pw)+" of "+fmt(f.inst)+" · CF "+(100*r.pw/Math.max(1,f.inst)).toFixed(0)+"%"+(f.lay?"":" (est.)")+" · "+U.toFixed(1)+" m/s from "+D+"°"}
  else{const z=Z[zh];t.textContent=z.n+" ("+z.c+") · "+z.st+(z.mw>=5?" · "+fmt(z.mw):"")+" · "+z.a+" km²"}}
 else if(S.mzhit){t.style.display="block";t.style.left=Math.min(x+12,cv.clientWidth-260)+"px";t.style.top=y+12+"px";t.textContent=moTip(S.mzhit)+(SYS[ZONEFLAG[S.mzhit]]?" · click for the System view":"");cv.style.cursor=SYS[ZONEFLAG[S.mzhit]]?"pointer":"grab"}else t.style.display="none";
 if(S.mzhit!==S.mzh){S.mzh=S.mzhit;repaint()}};
cv.onpointerup=cv.onpointercancel=e=>{ptr.delete(e.pointerId);cv.style.cursor="grab";
 if(drag&&drag.moved<5&&ptr.size===0&&e.type==="pointerup"){const[b,zh]=hit(e);if(b>=0)selectFarm(b);else if(zh<0&&S.mzhit)zoneToSystem(S.mzhit)}
 if(ptr.size===0)drag=null;else if(ptr.size===1){const[p]=[...ptr.values()];drag={x:p[0],y:p[1],lon:V.lon,lat:V.lat,moved:99}}};
cv.onwheel=e=>{e.preventDefault();cancelAnimationFrame(anim);zoomAt(e.offsetX,e.offsetY,Math.exp(-e.deltaY*.0016))};
cv.ondblclick=e=>{zoomAt(e.offsetX,e.offsetY,2)};
cv.onmouseleave=()=>{$("tip").style.display="none";if(S.hover>=0||S.zh>=0||S.mzh){S.hover=-1;S.zh=-1;S.mzh=null;repaint()}};
$("zin").onclick=()=>zoomAt(W0/2,H0/2,1.6);$("zout").onclick=()=>zoomAt(W0/2,H0/2,1/1.6);$("zhome").onclick=()=>go(null,null);
