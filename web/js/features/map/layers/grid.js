/* High-voltage grid layer (data/grid.json).
   ES module (spec 3 step 2): imports name what this file needs from other modules, the export list at the end what it offers. */
import { $ } from "../../../core/util.js";
import { P, cx, sl, viewBox } from "../canvas.js";
import { HID, repaint } from "../view.js";
// ---- high-voltage grid (web/data/grid.json: [kV (0 = DC), flags, coords]) ----
const GRID={d:null,b:null,loading:false};
const GCLS=[[700,"#004da8",1.7],[450,"#b81245",1.6],[350,"#e3262d",1.3],[270,"#f29d00",1.1],[200,"#38a800",.9],[0,"#777",.7]];
const GKEY=["g750","g500","g400","g300","g220","g220","gdc"];
const gcls=kv=>kv===0?6:GCLS.findIndex(c=>kv>=c[0]);
function gridLoad(){if(GRID.d||GRID.loading)return;GRID.loading=true;
 fetch("data/grid.json",{cache:"no-cache"}).then(r=>r.ok?r.json():null).then(j=>{if(!j)return;GRID.d=j.lines;GRID.b=j.lines.map(l=>{const c=l[2];let a=[1e9,1e9,-1e9,-1e9];for(let i=0;i<c.length;i+=2){a[0]=Math.min(a[0],c[i]);a[1]=Math.min(a[1],c[i+1]);a[2]=Math.max(a[2],c[i]);a[3]=Math.max(a[3],c[i+1])}return a});
  repaint()}).catch(()=>{})}
function gridDraw(){if(!$("GR").checked)return;gridLoad();if(!GRID.d)return;const v=viewBox(),far=sl()<12;
 const P2=[...Array(14)].map(()=>new Path2D());
 GRID.d.forEach((l,i)=>{const b=GRID.b[i];if(b[2]<v[0]||b[0]>v[2]||b[3]<v[1]||b[1]>v[3])return;const k=gcls(l[0]);if(k===6||(far&&k>=4))return;if(HID.has(GKEY[k]))return;
  const p=P2[k*2+(l[1]&1)],c=l[2];let lx=1e9,ly=1e9;
  for(let j=0;j<c.length;j+=2){const[x,y]=P(c[j],c[j+1]);if(!j){p.moveTo(x,y);lx=x;ly=y}else if(Math.abs(x-lx)+Math.abs(y-ly)>1||j>=c.length-2){p.lineTo(x,y);lx=x;ly=y}}});
 cx.save();cx.lineCap="round";cx.lineJoin="round";cx.globalAlpha=far?.55:.8;const zw=Math.min(1.6,Math.max(.6,sl()/60));
 for(let k=5;k>=0;k--)for(const uc of[0,1]){const st=k===6?["#d660d6",1.3]:[GCLS[k][1],GCLS[k][2]];cx.strokeStyle=st[0];cx.lineWidth=st[1]*zw;cx.setLineDash(uc?[5,3]:[]);cx.stroke(P2[k*2+uc])}
 for(const uc of[0,1]){cx.strokeStyle="#d660d6";cx.lineWidth=1.3*zw;cx.setLineDash(uc?[5,3]:[]);cx.stroke(P2[12+uc])}
 cx.restore()}

export { GRID, gridDraw, gridLoad };
