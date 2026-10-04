/* Hourly time axis (24 h back, 24 h ahead), per-farm wind and PyWake series from feed.json (or the synthetic fallback), current wind and output.
   ES module (spec 3 step 2): imports name what this file needs from other modules, the export list at the end what it offers. */
import { F, FEED, S, inC } from "./data.js";
import { $ } from "./util.js";
import { K_DEF, run } from "./wake.js";
/* ---------- time series: pipeline feed, or synthetic fallback ---------- */
const NP=24,NF=24,NT=NP+NF,N0=NP-1; // index N0 = now
let HRS,MODELS,SRC;
if(FEED){HRS=[...FEED.hours,...FEED.fc_hours].map(s=>new Date(s.replace("Z",":00Z")));MODELS=FEED.models;SRC=FEED.source}
else{const t0=new Date();t0.setMinutes(0,0,0);HRS=[...Array(NT)].map((_,h)=>new Date(t0.getTime()+(h-N0)*3600e3));MODELS={jensen:"Jensen (NOJ)",bastankhah:"Bastankhah & Porté-Agel 2014",nowake:"No wake"};SRC="browser"}
if(FEED){const keep=F.filter(f=>FEED.farms[String(f.id)]);if(keep.length<F.length){console.info("farms not yet in feed (shown after next hourly run):",F.filter(f=>!FEED.farms[String(f.id)]).map(f=>f.n));F.splice(0,F.length,...keep)}}
F.forEach((f,i)=>{const q=FEED&&FEED.farms[String(f.id)];
 if(q){f.U48=[...q.U,...(q.fU||Array(NF).fill(null))];f.D48=[...q.dir,...(q.fdir||Array(NF).fill(null))];f.S={};for(const m in MODELS)f.S[m]=[...q.P[m],...(q.fP?q.fP[m]:Array(NF).fill(null))];return}
 let s=Math.sin((i+1)*12.9898)*43758.5453;s-=Math.floor(s);f.U48=[];f.D48=[];
 for(let h=0;h<NT;h++){f.U48.push(+Math.max(1,Math.min(24,10+5*Math.sin(2*Math.PI*(h-f.lon*1.3)/26+f.lat*.4)+1.6*Math.sin(h/3.1+f.lat*2)+(s-.5))).toFixed(1));f.D48.push(Math.round((250+60*Math.sin((h-f.lon)/9)+360)%360))}});
function browserSeries(m){const key={jensen:"j",bastankhah:"g",turbopark:"t",nowake:"n"}[m];F.forEach(f=>{f.S=f.S||{};if(f.S[m])return;f.S[m]=f.U48.map((U,h)=>run(f,key,U,f.D48[h],K_DEF[key]||0).pw)})}
const hl=h=>HRS[h].toLocaleTimeString([],{hour:"2-digit",minute:"2-digit"}),dl=h=>HRS[h].toLocaleString([],{weekday:"short",hour:"2-digit",minute:"2-digit"});
const LIVE=()=>$("LV").checked;
function curWind(f){return LIVE()&&f.U48[N0]!=null?[f.U48[N0],f.D48[N0]]:[+$("U").value,+$("D").value]}
function cur(f){const m=$("M").value,[U,D]=curWind(f),k=+$("K").value,key=m+U+"|"+D+"|"+k;if(f._k!==key){f._k=key;f._r=run(f,m,U,D,k)}return f._r}
const now=c=>F.filter(f=>!c||inC(f,c)).reduce((a,f)=>a+cur(f).pw,0);
const MK=FEED&&FEED.market; // market block of the feed (prices, system data); null without a feed
function series(){if(!FEED){browserSeries(S.fm);browserSeries("nowake")}F.forEach(f=>{f.P=f.S[S.fm];f.Fr=f.S.nowake})}
function agg(fs){const P=Array(NT).fill(null),Fr=Array(NT).fill(null);let inst=0;
 fs.forEach(f=>{inst+=f.inst;for(let h=0;h<NT;h++){if(f.P[h]!=null)P[h]=(P[h]||0)+f.P[h];if(f.lay&&f.Fr[h]!=null)Fr[h]=(Fr[h]||0)+f.Fr[h]}});return{P,inst,Fr}}
function tbn(v,n){const o=v.filter(x=>x!=null).sort((a,b)=>a-b);if(o.length<20)return null;const m=a=>a.reduce((p,q)=>p+q,0)/a.length;return m(o.slice(-n))-m(o.slice(0,n))}
function capStats(fs,price,a,b){let e=0,rev=0,sp=0,np=0,wc=0;
 for(let h=a;h<=b;h++){const p=price[h];if(p==null)continue;np++;sp+=p;let g=0;
  fs.forEach(f=>{const v=f.P[h];if(v!=null){g+=v;if(f.lay&&f.Fr[h]!=null)wc+=(f.Fr[h]-v)*p}});e+=g;rev+=g*p}
 return{base:np?sp/np:null,cap:e>0?rev/e:null,e,wc,np}}
function farmCap(f){const pr=MK&&f.zone&&MK.prices[f.zone];if(!pr)return{cap:null,wc:null};const s=capStats([f],pr,0,N0);return{cap:s.cap,wc:f.lay?s.wc:null}}

export { HRS, LIVE, MK, MODELS, N0, NP, NT, SRC, agg, capStats, cur, curWind, dl, farmCap, hl, now, series, tbn };
