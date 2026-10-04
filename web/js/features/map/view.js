/* Map view: coastlines, fly-to / zoom, repaint, wake heat map and legend, farm glyphs, layer legend toggles, scale bar.
   ES module (spec 3 step 2): imports name what this file needs from other modules, the export list at the end what it offers. */
import { CBOX, F, GROUPS, S, Z, inC } from "../../core/data.js";
import { $, css } from "../../core/util.js";
import { wakeFarm, wd } from "../../core/wake.js";
import { cur } from "../../core/feed.js";
import { COASTL, COASTLB, D2R, M, P, Pinv, V, WORLD, clampV, cx, mercInv, mercY, pxm, sl, viewBox, zMin } from "./canvas.js";
import { MO } from "./layers/zones.js";
import { paint } from "./paint.js";
let anim=0,paintReq=0; // fly-to animation frame and pending repaint frame (moved here from canvas.js: only this file sets them)
function coastPath(){const p=new Path2D(),v=viewBox();for(let q=0;q<COASTL.length;q++){const r=COASTL[q],b=COASTLB[q];if(b[2]<v[0]||b[0]>v[2]||b[3]<v[1]||b[1]>v[3])continue;let lx=1e9,ly=1e9;for(let i=0;i<r.length;i+=2){const[x,y]=P(r[i],r[i+1]);if(!i){p.moveTo(x,y);lx=x;ly=y}else if(Math.abs(x-lx)+Math.abs(y-ly)>1.2||i>=r.length-2){p.lineTo(x,y);lx=x;ly=y}}}return p}
function bbox(c){if(GROUPS[c]){let a=[180,90,-180,-90];GROUPS[c].forEach(m=>{const b=bbox(m);if(b[2]-b[0]<200){a=[Math.min(a[0],b[0]),Math.min(a[1],b[1]),Math.max(a[2],b[2]),Math.max(a[3],b[3])]}});return a}
 if(CBOX[c]&&!F.some(f=>f.c===c))return CBOX[c];let a=[180,90,-180,-90];const add=(x,y)=>{a[0]=Math.min(a[0],x);a[1]=Math.min(a[1],y);a[2]=Math.max(a[2],x);a[3]=Math.max(a[3],y)};
 F.filter(f=>inC(f,c)).forEach(f=>f.ol.forEach(r=>{for(let i=0;i<r.length;i+=2)add(r[i],r[i+1])}));
 if($("Z").checked||!F.some(f=>inC(f,c)))Z.filter(z=>inC(z,c)).forEach(z=>z.r.forEach(r=>{for(let i=0;i<r.length;i+=2)add(r[i],r[i+1])}));
 return a[0]>a[2]?WORLD():a}
function flyTo(t,ms=500){cancelAnimationFrame(anim);const a={lon:V.lon,lat:V.lat,s:V.s},t0=performance.now();
 const step=n=>{const k=Math.min(1,(n-t0)/ms),e=k<.5?2*k*k:1-Math.pow(-2*k+2,2)/2;V.lon=a.lon+(t.lon-a.lon)*e;V.lat=a.lat+(t.lat-a.lat)*e;V.s=Math.exp(Math.log(a.s)+(Math.log(t.s)-Math.log(a.s))*e);clampV();paint();if(k<1)anim=requestAnimationFrame(step)};anim=requestAnimationFrame(step)}
function zoomAt(x,y,f){const[lon,lat]=Pinv(x,y);V.s=Math.min(4e5,Math.max(zMin(),V.s*f));const[l2,a2]=Pinv(x,y);V.lon+=lon-l2;V.lat=mercInv(mercY(V.lat)+mercY(lat)-mercY(a2));clampV();repaint()}
function repaint(){if(!paintReq)paintReq=requestAnimationFrame(()=>{paintReq=0;paint()})}
// Country / region picker with flags: the native <select> stays the source of truth (hidden), this draws a searchable list over it
// Wake deficit field on a grid aligned with the wind: fine across the wakes, coarser along them, so thin
// streaks stay crisp. Colour = one sequential ramp; tiny deficits fully transparent (no box edge).
const RAMP=[[68,1,84],[72,40,120],[62,74,137],[49,104,142],[38,130,142],[31,158,137],[53,183,121],[109,205,89],[180,222,44],[253,231,37]]; // viridis
function rampC(t){t=Math.max(0,Math.min(1,t))*(RAMP.length-1);const i=Math.min(RAMP.length-2,Math.floor(t)),f=t-i,a=RAMP[i],b=RAMP[i+1];return[a[0]+(b[0]-a[0])*f,a[1]+(b[1]-a[1])*f,a[2]+(b[2]-a[2])*f]}
const DEF_MAX=.3; // colour scale top: 30 % wind speed deficit
function heat(f,m,k){const r=cur(f),key=m+"|"+k+"|"+f._k;wakeFarm(f);
 if(!f._hm||f._hm.key!==key){const D=f.D||150,dx=r.dx,dy=r.dy,P=r.P;
  let s0=1e9,s1=-1e9,c0=1e9,c1=-1e9;P.forEach(p=>{const s=p[0]*dx+p[1]*dy,c=-p[0]*dy+p[1]*dx;s0=Math.min(s0,s);s1=Math.max(s1,s);c0=Math.min(c0,c);c1=Math.max(c1,c)});
  s0-=1.5*D;s1+=m==="t"?Math.max(8000,80*D):Math.max(4000,30*D);  // TurbOPark wakes are narrower and recover more slowlyc0-=3*D;c1+=3*D;
  const ds=D/3,dc=D/10,Ns=Math.min(600,Math.ceil((s1-s0)/ds)),Nc=Math.min(1000,Math.ceil((c1-c0)/dc)),DS=(s1-s0)/Ns,DC=(c1-c0)/Nc;
  const off=document.createElement("canvas");off.width=Ns;off.height=Nc;const oc=off.getContext("2d"),im=oc.createImageData(Ns,Nc);
  for(let v=0;v<Nc;v++){const c=c0+(v+.5)*DC;for(let u=0;u<Ns;u++){const s=s0+(u+.5)*DS,px=s*dx-c*dy,py=s*dy+c*dx;let q=0;
   if(m==="j"||m==="t"){for(let j=0;j<P.length;j++){const d=wd(m,k,P[j],r.Dt[j],r.ct[j],px,py,dx,dy,0);if(d)q+=d*d}q=Math.sqrt(q)}
   else for(let j=0;j<P.length;j++){const d=wd(m,k,P[j],r.Dt[j],r.ct[j],px,py,dx,dy,0);if(d)q+=r.u[j]/r.U*d}
   const o=4*(v*Ns+u);if(q<.008){im.data[o+3]=0;continue}
   const fade=Math.min(1,(s1-s)/(.3*(s1-s0))),al=Math.pow(Math.min(1,(q-.008)/.08),.9)*.72*fade,col=rampC(q/DEF_MAX);
   im.data[o]=col[0];im.data[o+1]=col[1];im.data[o+2]=col[2];im.data[o+3]=al*255}}
  oc.putImageData(im,0,0);f._hm={key,c:off,s0,c0,DS,DC,dx,dy}}
 const h=f._hm,dpr=devicePixelRatio||1,ax=V.s/f.kx,ay=V.s/Math.cos(f.lat*D2R)/110574,[Xo,Yo]=M(f,0,0);
 cx.save();cx.setTransform(dpr*ax*h.DS*h.dx,-dpr*ay*h.DS*h.dy,-dpr*ax*h.DC*h.dy,-dpr*ay*h.DC*h.dx,dpr*(Xo+ax*(h.s0*h.dx-h.c0*h.dy)),dpr*(Yo-ay*(h.s0*h.dy+h.c0*h.dx)));
 cx.imageSmoothingEnabled=true;cx.imageSmoothingQuality="high";cx.drawImage(h.c,0,0);cx.restore();S.heatShown=true}
function heatLegend(W,H){const w=150,x=W-16-w,y=H-150;  // above the basemap switchercx.font="11px sans-serif";cx.fillStyle=css("--panel");cx.globalAlpha=.9;cx.fillRect(x-8,y-16,w+16,34);cx.globalAlpha=1;
 const g=cx.createLinearGradient(x,0,x+w,0);for(let i=0;i<=4;i++){const c=rampC(i/4),a=i?.72:.2;g.addColorStop(i/4,"rgba("+c.map(Math.round).join(",")+","+a+")")}
 cx.fillStyle=css("--mut");cx.fillText("Wind speed deficit",x,y-4);cx.fillStyle=g;cx.fillRect(x,y,w,8);cx.fillStyle=css("--mut");cx.fillText("0",x,y+18);cx.textAlign="right";cx.fillText(Math.round(DEF_MAX*100)+"%+",x+w,y+18);cx.textAlign="left"}
function ringR(f){return(3+Math.sqrt(f.inst)*.28)*Math.min(1.6,Math.max(1,sl()/40))}
// legend toggles: keys of map objects the viewer has hidden (remembered in this browser)
const HID=new Set((()=>{try{return JSON.parse(localStorage.getItem("wm-hide")||"[]")}catch(e){return[]}})());
const LCAT={farms:["off","on"],zones:["uc","cs","pl"],gas:["gip","glng","gprod"],grid:["g750","g500","g400","g300","g220"],ic:["xac","xdc"]};
function catOn(c){return c==="price"?MO!=="off":c==="zones"?$("Z").checked:c==="grid"?$("GR").checked:c==="depth"?$("BY").checked:LCAT[c].some(k=>!HID.has(k))}
function legSync(){document.querySelectorAll("#leg .lc").forEach(b=>{const on=catOn(b.dataset.c);b.classList.toggle("off",!on);b.setAttribute("aria-pressed",String(on))});document.querySelectorAll("#leg .lk").forEach(b=>{const k=b.dataset.k,off=k==="depth"?!$("BY").checked:HID.has(k)||(["uc","cs","pl"].includes(k)&&!$("Z").checked);b.classList.toggle("off",off);b.setAttribute("aria-pressed",String(!off))})}
const fcol=f=>css(f.on?"--m-won":"--acc");
function glyph(f,r,x,y,i){const Ro=ringR(f),cf=Math.max(0,Math.min(1,r.pw/Math.max(1,f.inst))),hot=i===S.hover||i===S.farm;
 cx.beginPath();cx.arc(x,y,Ro,0,7);cx.fillStyle=css("--panel");cx.globalAlpha=.8;cx.fill();cx.globalAlpha=1;
 cx.lineWidth=hot?2.6:1.4;cx.strokeStyle=fcol(f);if(!f.lay)cx.setLineDash([3,2]);cx.stroke();cx.setLineDash([]);
 if(cf>0.002){cx.beginPath();cx.arc(x,y,Math.max(1,Ro*cf),0,7);cx.fillStyle=fcol(f);cx.fill()}
 S.pts.push([x,y,Ro,i])}
function scaleBar(W,H){const pm=pxm();let km=[1,2,5,10,20,50,100,200,500].find(v=>v*1000*pm>=70)||500;const w=km*1000*pm;
 cx.fillStyle=css("--ink");cx.font="12px sans-serif";const up=$("attr").style.display==="block"?$("attr").offsetHeight+4:0;cx.fillText(km+" km",W-16-w,H-16-up);cx.fillRect(W-16-w,H-12-up,w,2)}

export { HID, LCAT, anim, bbox, catOn, coastPath, fcol, flyTo, glyph, heat, heatLegend, legSync, repaint, scaleBar, zoomAt };
