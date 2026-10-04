/* Map canvas: Web Mercator projection, pan / zoom state V, level-of-detail thresholds, coastline tiles and seams.
   ES module (spec 3 step 2): imports name what this file needs from other modules, the export list at the end what it offers. */
import { DATA, F } from "../../core/data.js";
import { $, css } from "../../core/util.js";
const cv=$("cv"),cx=cv.getContext("2d");
/* ---------- map: pan / zoom with level of detail ---------- */
const EU=[-11,40.5,27,62.5],HOME=[-14,34,44,71],WORLD=()=>{let a=[180,90,-180,-90];F.forEach(f=>{a=[Math.min(a[0],f.lon),Math.min(a[1],f.lat),Math.max(a[2],f.lon),Math.max(a[3],f.lat)]});return[a[0]-4,a[1]-4,a[2]+4,a[3]+4]},V={lon:8,lat:51.5,s:30};let W0=0,H0=0;
F.forEach(f=>{let e=0;const add=(x,y)=>{e=Math.max(e,Math.abs(x),Math.abs(y))};if(f.xy)for(let i=0;i<f.xy.length;i+=2)add(f.xy[i],f.xy[i+1]);(f.o||[]).forEach(r=>{for(let i=0;i<r.length;i+=2)add(r[i],r[i+1])});let t=0;if(f.xy)for(let i=0;i<f.xy.length;i+=2)t=Math.max(t,Math.abs(f.xy[i]),Math.abs(f.xy[i+1]));f.tex=f.xy?Math.max(t,300):Math.max(e,400);f.ext=Math.max(e,400);f.kx=111320*Math.cos(f.lat*Math.PI/180)});
// Web Mercator display: panning is a pure shift (no stretching); V.s = pixels per degree of longitude.
// mercY(): Mercator y in degree units; YMAX = edge of the map (85.05 deg), north/south panning stops there.
const D2R=Math.PI/180,mercY=lat=>Math.log(Math.tan(Math.PI/4+Math.max(-85.05,Math.min(85.05,lat))*D2R/2))/D2R,mercInv=y=>(2*Math.atan(Math.exp(y*D2R))-Math.PI/2)/D2R,YMAX=mercY(85.05);
const cosR=()=>Math.cos(V.lat*D2R),sl=()=>V.s/cosR(),pxm=()=>sl()/110574;  // sl: px per degree of latitude at the view centre
const P=(lon,lat)=>[W0/2+(lon-V.lon)*V.s,H0/2-(mercY(lat)-mercY(V.lat))*V.s];
const Pinv=(x,y)=>[V.lon+(x-W0/2)/V.s,mercInv(mercY(V.lat)-(y-H0/2)/V.s)];
const M=(f,x,y)=>P(f.lon+x/f.kx,f.lat+y/110574);
const zMin=()=>H0/(2*YMAX);  // zoomed fully out the world fills the height: no north/south movement left
function clampV(){V.s=Math.max(zMin(),Math.min(4e5,V.s));const half=(H0/2)/V.s;if(half>=YMAX){V.lat=0;return}V.lat=mercInv(Math.max(-YMAX+half,Math.min(YMAX-half,mercY(V.lat))));V.lon=((V.lon+540)%360)-180}
const LOD_TURB=30,LOD_WAKE=90; // farm radius on screen (px) where turbines / wake fields appear
function size(){const r=cv.getBoundingClientRect(),d=devicePixelRatio||1;cv.width=r.width*d;cv.height=r.height*d;cx.setTransform(d,0,0,d,0,0);W0=r.width;H0=r.height;return[r.width,r.height]}
function fit(b,pad=.08){const y0=mercY(b[1]),y1=mercY(b[3]),lat=mercInv((y0+y1)/2),w=Math.max(.02,b[2]-b[0]),h=Math.max(.02,y1-y0);
 return{lon:(b[0]+b[2])/2,lat,s:Math.min(4e5,Math.min(W0*(1-2*pad)/w,H0*(1-2*pad)/h))}}
function farmBox(f){if(f.lay){const e=(f.tex+800)/110574,c=Math.cos(f.lat*Math.PI/180);return[f.lon-e/c,f.lat-e,f.lon+e/c,f.lat+e]}const b=[180,90,-180,-90];f.ol.forEach(r=>{for(let i=0;i<r.length;i+=2){b[0]=Math.min(b[0],r[i]);b[1]=Math.min(b[1],r[i+1]);b[2]=Math.max(b[2],r[i]);b[3]=Math.max(b[3],r[i+1])}});
 const e=f.ext/110574;return[Math.min(b[0],f.lon-e/Math.cos(f.lat*Math.PI/180)),Math.min(b[1],f.lat-e),Math.max(b[2],f.lon+e/Math.cos(f.lat*Math.PI/180)),Math.max(b[3],f.lat+e)]}
// coastline strokes: land polygon edges, except edges along the borders of the detailed-land boxes (dbox).
// Split once into polylines (lon/lat); each paint only projects them.
const SEAML=[];const COASTL=(()=>{const DB=DATA.dbox||[],out=[];
 const TL=DATA.tile||0,onT=v=>TL&&Math.abs(v/TL-Math.round(v/TL))<1e-4;
 const seam=(x0,y0,x1,y1)=>(Math.abs(x0-x1)<1e-6&&onT(x0))||(Math.abs(y0-y1)<1e-6&&onT(y0))||DB.some(b=>(Math.abs(x0-x1)<1e-6&&(Math.abs(x0-b[0])<.006||Math.abs(x0-b[2])<.006))||(Math.abs(y0-y1)<1e-6&&(Math.abs(y0-b[1])<.006||Math.abs(y0-b[3])<.006)));
 for(const r of DATA.coast){const n=r.length/2;let cur=[];
  for(let k=0;k<n;k++){const i=2*k,j=2*((k+1)%n);if(seam(r[i],r[i+1],r[j],r[j+1])){SEAML.push(r[i],r[i+1],r[j],r[j+1]);if(cur.length>2)out.push(cur);cur=[];continue}
   if(!cur.length)cur.push(r[i],r[i+1]);cur.push(r[j],r[j+1])}
  if(cur.length>2)out.push(cur)}return out})();
const COASTLB=COASTL.map(r=>{let a=[1e9,1e9,-1e9,-1e9];for(let i=0;i<r.length;i+=2){a[0]=Math.min(a[0],r[i]);a[1]=Math.min(a[1],r[i+1]);a[2]=Math.max(a[2],r[i]);a[3]=Math.max(a[3],r[i+1])}return a});
// land rings with their bounding boxes; only rings overlapping the view are drawn
const LANDB=DATA.coast.map(r=>{let a=[1e9,1e9,-1e9,-1e9];for(let i=0;i<r.length;i+=2){a[0]=Math.min(a[0],r[i]);a[1]=Math.min(a[1],r[i+1]);a[2]=Math.max(a[2],r[i]);a[3]=Math.max(a[3],r[i+1])}return a});
function viewBox(){const[l0,a1]=Pinv(0,0),[l1,a0]=Pinv(W0,H0),mx=(l1-l0)*.05,my=(a1-a0)*.05;return[l0-mx,a0-my,l1+mx,a1+my]}
function landInView(){const v=viewBox();return DATA.coast.filter((r,i)=>{const b=LANDB[i];return b[2]>=v[0]&&b[0]<=v[2]&&b[3]>=v[1]&&b[1]<=v[3]})}
// canvas anti-aliasing leaves hairlines where two land polygons meet along a cut: paint over them in land colour
function seamCover(){const v=viewBox(),p=new Path2D();for(let i=0;i<SEAML.length;i+=4){const x0=SEAML[i],y0=SEAML[i+1],x1=SEAML[i+2],y1=SEAML[i+3];
 if(Math.max(x0,x1)<v[0]||Math.min(x0,x1)>v[2]||Math.max(y0,y1)<v[1]||Math.min(y0,y1)>v[3])continue;const[a,b]=P(x0,y0),[c,d]=P(x1,y1);p.moveTo(a,b);p.lineTo(c,d)}
 const lw=cx.lineWidth,ss=cx.strokeStyle;cx.strokeStyle=css("--land");cx.lineWidth=1.5;cx.stroke(p);cx.lineWidth=lw;cx.strokeStyle=ss}

export { COASTL, COASTLB, D2R, H0, HOME, LOD_TURB, LOD_WAKE, M, P, Pinv, V, W0, WORLD, clampV, cv, cx, farmBox, fit, landInView, mercInv, mercY, pxm, seamCover, size, sl, viewBox, zMin };
