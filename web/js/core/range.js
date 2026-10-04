/* Longer time ranges for the System tab (72 h, 1 week, 1 month) from the Data-tab export: build/data/browse/ts/<zone>.json
   holds hourly means per bidding zone for the last 30 days (UTC). A country is one zone or the sum of its zones (DK1+DK2,
   NO1-5, SE1-4), the same convention as the 24 h feed view. Hours where one of the zones has not reported are left null,
   never drawn as a dip. The result has the shape of core/sysdata.js sysData() plus n, t (epoch s per slot), tl / hl label
   functions and prices per zone, so the System tab's cards draw it unchanged.
   ES module (spec 3 step 2): imports name what this file needs from other modules, the export list at the end what it offers. */
import { dbJson } from "./load.js";
import { MIXC } from "./sysdata.js";

const TS={};                                   // zone -> promise of the ts file (or null)
function zoneTs(z){return TS[z]||(TS[z]=dbJson("data/browse/ts/"+encodeURIComponent(z)+".json").catch(()=>null))}

const DOW=["Sun","Mon","Tue","Wed","Thu","Fri","Sat"],MON=["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
function labeller(t,hours){return k=>{const d=new Date(t[k]*1000),hh=d.getHours().toString().padStart(2,"0")+":00";
 return hours<=72?DOW[d.getDay()]+" "+hh:d.getDate()+" "+MON[d.getMonth()]+" "+hh}}

/* D-like object for `zones` over the last `hours` hourly slots up to `now` (epoch s). null when no zone file exists. */
async function rangeData(c,zones,hours,now=Date.now()/1000){
 const got=await Promise.all(zones.map(zoneTs)),pairs=zones.map((z,i)=>[z,got[i]]).filter(q=>q[1]),files=pairs.map(q=>q[1]);if(!files.length)return null;
 const f0=files[0],t0=f0.t0,step=f0.step||3600,nAll=f0.v[0].length;
 let end=Math.min(nAll-1,Math.floor((now-t0)/step)-1);if(end<0)return null;   // the last fully elapsed hour
 const start=Math.max(0,end-hours+1),idx=[];for(let i=start;i<=end;i++)idx.push(i);
 // zone files may differ in t0 (same export, same window, so in practice equal); align by time stamp
 const slot=(f,i)=>Math.round((t0+i*step-f.t0)/(f.step||3600));
 const F=files.map(f=>({cols:f.cols,v:f.v,at:i=>slot(f,i)}));
 const take=pick=>idx.map(i=>{let s=0,any=false;for(const f of F){const j=f.at(i);if(j<0||j>=f.v[0].length)return null;const cs=f.cols.map((c,q)=>pick(c)?q:-1).filter(q=>q>=0);if(!cs.length)continue;let z=false;for(const q of cs){const v=f.v[q][j];if(v!=null){s+=v;z=true}}if(!z)return null;any=true}return any?s:null});
 const n=idx.length,t=idx.map(i=>t0+i*step);
 const isGen=c=>c.id.startsWith("g|")&&c.id.endsWith("|gen");
 const mix={};MIXC.forEach(([k])=>{mix[k]=take(c=>isGen(c)&&(k==="oth"?!c.tech:c.tech===k)).map(v=>v==null?0:Math.max(0,v))});
 const gen=t.map((_,h)=>MIXC.reduce((a,[k])=>a+mix[k][h],0));
 let last=n-1;while(last>0&&gen[last]===0)last--;
 const lastRep={};MIXC.forEach(([k])=>{let l=-1;for(let h=0;h<n;h++)if(mix[k][h]>0)l=h;lastRep[k]=l<0?-1:(l<n-1&&mix[k][l]<=0.02*Math.max(...mix[k])?n-1:l)});
 const load=take(c=>c.id==="l|actual"),hasLoad=load.some(v=>v!=null);
 const res=hasLoad?load.map((v,h)=>v!=null&&h<=last?v-mix.won[h]-mix.woff[h]-mix.sol[h]:null):null;
 // flows: per neighbour zone outside the country, import positive; internal borders (DK1-DK2) left out
 const own=new Set(zones),nbs=[...new Set(F.flatMap(f=>f.cols.filter(c=>c.id.startsWith("x|")).map(c=>c.id.split("|")[2])))].filter(z=>!own.has(z));
 const fl={},fn={};nbs.forEach(z=>{const inn=take(c=>c.id==="x|in|"+z),out=take(c=>c.id==="x|out|"+z);fl[z]=inn.map((v,h)=>v==null&&out[h]==null?null:(v||0)-(out[h]||0));fn[z]=z});
 const nb=nbs.filter(z=>fl[z].some(v=>v!=null)).sort((a,b)=>Math.abs(fl[b][last]||0)-Math.abs(fl[a][last]||0));
 const net=nb.length?t.map((_,h)=>{let s=0,any=false;nb.forEach(z=>{if(fl[z][h]!=null){s+=fl[z][h];any=true}});return any?s:null}):null;
 if(net)fl.sum=net;
 const prices={};pairs.forEach(([z,f])=>{const j=f.cols.findIndex(c=>c.id==="p|price");if(j<0)return;prices[z]=idx.map(i=>{const s=slot(f,i);return s>=0&&s<f.v[0].length?f.v[j][s]:null})});
 const tl=labeller(t,hours),hl=k=>{const d=new Date(t[k]*1000);return d.getHours().toString().padStart(2,"0")+":00"};
 return{c,zones,mix,gen,load:hasLoad?load:null,ren:null,last,lastRep,res,net,nb,fl,fn,lag:0,n,t,tl,hl,prices,hours,from:tl(0),to:tl(n-1)}}

export { rangeData, zoneTs };
