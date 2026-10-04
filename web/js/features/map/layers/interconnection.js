/* Interconnection layer: cross-border flows per bidding-zone pair over land borders and DC links (data/browse/xflow.json).
   ES module (spec 3 step 2): imports name what this file needs from other modules, the export list at the end what it offers. */
import { $ } from "../../../core/util.js";
import { HRS } from "../../../core/feed.js";
import { P, cx, sl, viewBox } from "../canvas.js";
import { GRID, gridLoad } from "./grid.js";
import { dcFlow, dcZone } from "./dc.js";
import { HID, catOn, repaint } from "../view.js";
import { MZ, mzLoad } from "./zones.js";
// ---- Interconnection layer: cross-border flows over land borders and on DC interconnectors, one value per border ----
// Flows are per bidding-zone pair (browse/xflow.json: ENTSO-E A11 physical flows / Elexon, latest hour, from the data
// store), so a border's land part and its subsea DC links are separate pairs where they connect different zones
// (DK1-DE land vs DK2-DE Kontek, SE1-FI land vs SE3-FI Fenno-Skan): land arrow = border flow minus the offshore link.
// Where a DC cable and the land border join the same two zones (INELFE FR-ES, ALEGrO BE-DE: onshore DC) the land arrow
// carries the total and the cable shows direction only. Country-level System data fills pairs the store lacks when the
// two countries meet at just one zone pair. Only pairs between different countries are drawn.
const IC={x:null,map:{},busy:0,land:null,dc:null,cnt:null};
const ctry=z=>z.slice(0,2).toLowerCase();
function icLoad(){if(IC.x||IC.busy)return;IC.busy=1;fetch("data/browse/xflow.json",{cache:"no-cache"}).then(r=>r.ok?r.json():null).catch(()=>null).then(j=>{IC.x=j||{pairs:[]};(IC.x.pairs||[]).forEach(q=>IC.map[q[0]+"|"+q[1]]=q);repaint()})}
function icBuild(){if(IC.land||!MZ.d||!GRID.d)return;const B=new Map(),key=(x,y)=>Math.floor(x/.1)+","+Math.floor(y/.1),cen={};
 for(const[z,Z]of Object.entries(MZ.d)){let A=0,X=0,Y=0;Z.p.forEach(r=>{for(let i=0;i<r.length;i+=2){const k=key(r[i],r[i+1]);if(!B.has(k))B.set(k,[]);B.get(k).push([r[i],r[i+1],z])}
   for(let i=0,j=r.length-2;i<r.length;j=i,i+=2){const f=r[j]*r[i+1]-r[i]*r[j+1];A+=f;X+=(r[j]+r[i])*f;Y+=(r[j+1]+r[i+1])*f}});if(Math.abs(A)>1e-9)cen[z]=[X/(3*A),Y/(3*A)]}
 const m={};for(const[k,pts]of B){const[gx,gy]=k.split(",").map(Number);pts.forEach(([x,y,z])=>{for(let dx=-1;dx<=1;dx++)for(let dy=-1;dy<=1;dy++){const o=B.get((gx+dx)+","+(gy+dy));if(o)o.forEach(([x2,y2,z2])=>{if(z2>z&&ctry(z2)!==ctry(z)&&(x-x2)**2+(y-y2)**2<.0025)(m[z+"|"+z2]=m[z+"|"+z2]||[]).push([x,y])})}})}
 IC.land={};for(const[k,pts]of Object.entries(m)){if(pts.length<3)continue;const[a,b]=k.split("|");if(!cen[a]||!cen[b])continue;const mx=pts.reduce((t,q)=>t+q[0],0)/pts.length,my=pts.reduce((t,q)=>t+q[1],0)/pts.length;
  const c0=pts.reduce((best,q)=>(q[0]-mx)**2+(q[1]-my)**2<(best[0]-mx)**2+(best[1]-my)**2?q:best,pts[0]);IC.land[k]={a,b,x:c0[0],y:c0[1],pa:cen[a],pb:cen[b]}}
 IC.dc=[];GRID.d.forEach((l,i)=>{if(l[0]!==0||l[1]&1)return;const c=l[2],n=c.length,za=dcZone(c[0],c[1]),zb=dcZone(c[n-2],c[n-1]);if(!za||!zb||ctry(za)===ctry(zb))return;IC.dc.push({i,za,zb,k:za<zb?za+"|"+zb:zb+"|"+za})});
 IC.cnt={};const add=k=>{const[a,b]=k.split("|"),ck=[ctry(a),ctry(b)].sort().join("|");(IC.cnt[ck]=IC.cnt[ck]||new Set()).add(k)};Object.keys(IC.land).forEach(add);IC.dc.forEach(d=>add(d.k))}
// MW flowing from zone `from` to zone `to` in the latest hour, and the hour (epoch s)
function icFlow(from,to){const[a,b]=from<to?[from,to]:[to,from],q=IC.map[a+"|"+b];
 if(q&&Date.now()/1000-q[2]<18*3600)return{v:from===a?q[3]:-q[3],t:q[2]};
 const cs=IC.cnt&&IC.cnt[[ctry(a),ctry(b)].sort().join("|")];if(cs&&cs.size===1){const f=dcFlow(ctry(from),ctry(to));if(f&&f.v)return{v:-f.v,t:HRS[f.i]?HRS[f.i].getTime()/1000:null,sys:1}}return null}
const icMW=v=>Math.abs(v)>=1000?(Math.abs(v)/1000).toFixed(1)+" GW":Math.round(Math.abs(v))+" MW";
function icLabel(t,x,y,col){cx.font="600 10.5px system-ui,sans-serif";cx.textAlign="center";cx.lineWidth=3;cx.strokeStyle="rgba(255,255,255,.9)";cx.strokeText(t,x,y);cx.fillStyle=col;cx.fillText(t,x,y)}
function icDraw(){if(!catOn("ic"))return;if(!MZ.d)mzLoad();gridLoad();icLoad();if(!MZ.d||!GRID.d||!IC.x)return;icBuild();
 const v=viewBox(),far=sl()<12,zw=Math.min(1.6,Math.max(.6,sl()/60)),lab=sl()>=9;let asof=0,sys=0;cx.save();cx.setLineDash([]);cx.lineCap="round";cx.lineJoin="round";
 if(!HID.has("xdc")){const done=new Set();IC.dc.forEach(L=>{const b=GRID.b[L.i];if(b[2]<v[0]||b[0]>v[2]||b[3]<v[1]||b[1]>v[3])return;const c=GRID.d[L.i][2],pts=[];for(let j=0;j<c.length;j+=2)pts.push(P(c[j],c[j+1]));
   cx.beginPath();pts.forEach((q,j)=>j?cx.lineTo(q[0],q[1]):cx.moveTo(q[0],q[1]));cx.strokeStyle="#d660d6";cx.lineWidth=1.8*zw;cx.globalAlpha=.85;cx.stroke();
   const f=icFlow(L.za,L.zb);if(!f||!f.v)return;if(f.t)asof=Math.max(asof,f.t);sys+=f.sys||0;if(f.v<0)pts.reverse();  // walk from the exporting end
   let len=0;const seg=[];for(let j=1;j<pts.length;j++){const d=Math.hypot(pts[j][0]-pts[j-1][0],pts[j][1]-pts[j-1][1]);seg.push(d);len+=d}if(len<14)return;
   const step=Math.max(46,len/Math.max(1,Math.round(len/90))),sz=(3.2+Math.min(3,Math.abs(f.v)/700))*zw;let at=Math.min(step/2,len/2),acc=0,j=0;
   while(at<len){while(j<seg.length&&acc+seg[j]<at){acc+=seg[j];j++}if(j>=seg.length)break;const t=(at-acc)/seg[j],x=pts[j][0]+(pts[j+1][0]-pts[j][0])*t,y=pts[j][1]+(pts[j+1][1]-pts[j][1])*t,an=Math.atan2(pts[j+1][1]-pts[j][1],pts[j+1][0]-pts[j][0]);
    cx.save();cx.translate(x,y);cx.rotate(an);cx.beginPath();cx.moveTo(sz*1.3,0);cx.lineTo(-sz,sz);cx.lineTo(-sz*.35,0);cx.lineTo(-sz,-sz);cx.closePath();cx.fillStyle="#a51fa5";cx.strokeStyle="rgba(255,255,255,.85)";cx.lineWidth=1;cx.globalAlpha=.95;cx.stroke();cx.fill();cx.restore();at+=step}
   if(lab&&!far&&!done.has(L.k)&&!IC.land[L.k]){done.add(L.k);const m=pts[Math.floor(pts.length/2)],fr=f.v>0?L.za:L.zb,to=f.v>0?L.zb:L.za;icLabel(fr+"→"+to+" "+icMW(f.v),m[0],m[1]-7,"#7a1a7a")}})}
 if(!HID.has("xac"))Object.values(IC.land).forEach(Q=>{if(Q.x<v[0]||Q.x>v[2]||Q.y<v[1]||Q.y>v[3])return;const f=icFlow(Q.a,Q.b);if(!f||!f.v)return;if(f.t)asof=Math.max(asof,f.t);sys+=f.sys||0;
  const[x,y]=P(Q.x,Q.y),A=P(...Q.pa),Bp=P(...Q.pb);let ux=Bp[0]-A[0],uy=Bp[1]-A[1];const n=Math.hypot(ux,uy)||1;ux/=n;uy/=n;if(f.v<0){ux=-ux;uy=-uy}  // f.v > 0: a -> b
  const L=12+Math.min(22,Math.abs(f.v)/150),w=4+Math.min(4,Math.abs(f.v)/800);
  cx.save();cx.translate(x,y);cx.rotate(Math.atan2(uy,ux));cx.beginPath();cx.moveTo(L/2+w*1.2,0);cx.lineTo(L/2-w*.6,w*1.5);cx.lineTo(L/2-w*.6,w*.55);cx.lineTo(-L/2,w*.55);cx.lineTo(-L/2,-w*.55);cx.lineTo(L/2-w*.6,-w*.55);cx.lineTo(L/2-w*.6,-w*1.5);cx.closePath();
  cx.fillStyle="#1d3b53";cx.strokeStyle="rgba(255,255,255,.9)";cx.lineWidth=1.5;cx.globalAlpha=.92;cx.stroke();cx.fill();cx.restore();
  if(lab)icLabel(icMW(f.v),x+uy*11,y-ux*11+4,"#1d3b53")});
 cx.restore();const nn=$("icnote");if(nn)nn.textContent=asof?"Net flow per border, "+new Date(asof*1000).toLocaleString([],{weekday:"short",hour:"2-digit",minute:"2-digit"})+(sys?" (some borders: System data, latest hour)":""):""}

export { icDraw };
