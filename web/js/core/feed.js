/* Hourly time axis (24 h back, 24 h ahead), per-farm wind and PyWake series from feed.json (or the synthetic fallback), current wind and output.
   Spec 3 step 2, push 3: moved from the former single page script unchanged; classic script, shared global scope. */
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
