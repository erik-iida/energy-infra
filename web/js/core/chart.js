/* Shared chart helpers: mean / past, SVG line and area paths, chart frame, arrows, m/s formatting, hour under the cursor, tooltip.
   ES module (spec 3 step 2): imports name what this file needs from other modules, the export list at the end what it offers. */
import { COUNTRIES, F, RGOF, S, isReg } from "./data.js";
import { $ } from "./util.js";
import { N0, NP, NT } from "./feed.js";
const mean=a=>{const v=a.filter(x=>x!=null);return v.length?v.reduce((x,y)=>x+y,0)/v.length:null};
const past=a=>a.slice(0,NP),fut=a=>a.slice(NP);
function line(vals,max,W,H,pad){const x=h=>pad+(W-2*pad)*h/(NT-1),y=v=>H-2-(H-6)*Math.min(1,Math.max(0,v/max));
 const seg=(a,b)=>{let d="",on=false;for(let h=a;h<=b;h++){const v=vals[h];if(v==null){on=false;continue}d+=(on?"L":"M")+x(h).toFixed(1)+","+y(v).toFixed(1);on=true}return d};
 return{p:seg(0,N0),f:seg(N0,NT-1),x,y}}
function area(d,L,H){if(!d)return"";const m=d.match(/[ML]([\d.]+),/g);const a=m[0].slice(1,-1),b=m[m.length-1].slice(1,-1);return d+"L"+b+","+(H-2)+"L"+a+","+(H-2)+"Z"}
function chartSVG(vals,W,H,dot,g=.5,gl="50%"){const L=line(vals,1,W,H,3);
 let s="<line class='ax' x1='3' x2='"+(W-3)+"' y1='"+(H-2)+"' y2='"+(H-2)+"'/><line class='ax' stroke-dasharray='2 3' x1='3' x2='"+(W-3)+"' y1='"+L.y(g)+"' y2='"+L.y(g)+"'/><text class='tl' x='3' y='"+(L.y(g)-3)+"'>"+gl+"</text>";
 s+="<line class='nowl' x1='"+L.x(N0)+"' x2='"+L.x(N0)+"' y1='0' y2='"+H+"'/>";
 s+="<path class='ar' d='"+area(L.p,L,H)+"'/><path class='ar fc' d='"+area(L.f,L,H)+"'/><path class='ln' d='"+L.p+"'/><path class='ln fc' d='"+L.f+"'/>";
 const h=S.hh>=0?S.hh:N0;if(S.hh>=0)s+="<line class='xh' x1='"+L.x(h)+"' x2='"+L.x(h)+"' y1='0' y2='"+H+"'/>";if(dot&&vals[h]!=null)s+="<circle class='dot' r='4' cx='"+L.x(h)+"' cy='"+L.y(vals[h])+"'/>";return s}
const CO=()=>COUNTRIES.filter(c=>F.some(f=>f.c===c)&&(!S.c||!isReg(S.c)||RGOF[c]===S.c));
const UMAX=25;
function aggW(fs){return[...Array(NT)].map((_,h)=>{let a=0,w=0;fs.forEach(f=>{const u=f.U48[h];if(u!=null){a+=u*f.inst;w+=f.inst}});return w?a/w:null})}
const arrow=d=>d==null?"":"<span class='arr' style='transform:rotate("+d+"deg)' title='from "+d+"°'>↓</span>";
const ms=u=>u==null?"–":u.toFixed(1)+" m/s";
function hourAt(sv,e,pad){const r=sv.getBoundingClientRect(),vb=sv.viewBox.baseVal,x=(e.clientX-r.left)/r.width*vb.width;return Math.max(0,Math.min(NT-1,Math.round((x-pad)/(vb.width-2*pad)*(NT-1))))}
function dtip(e,t){const d=$("dtip");d.style.display="block";d.textContent=t;const w=d.offsetWidth,hh=d.offsetHeight;d.style.left=(e.clientX+14+w>innerWidth-8?Math.max(8,e.clientX-14-w):e.clientX+14)+"px";d.style.top=Math.max(8,Math.min(e.clientY+14,innerHeight-hh-8))+"px"}

export { CO, UMAX, aggW, arrow, chartSVG, dtip, fut, hourAt, line, mean, ms, past };
