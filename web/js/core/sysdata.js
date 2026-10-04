/* System data from the feed (feed.market.system): per-country generation mix, load, prices and flows, the technology groups and their colours, and sysData(country) which handles late-reporting technologies.
   ES module (spec 3 step 2): imports name what this file needs from other modules, the export list at the end what it offers. */
import { MK, NP } from "./feed.js";
const SYS=MK&&MK.system||{},SYSN={de:"Germany",fr:"France",nl:"Netherlands",be:"Belgium",dk:"Denmark",no:"Norway",se:"Sweden",pl:"Poland",at:"Austria",ch:"Switzerland",cz:"Czechia",sk:"Slovakia",hu:"Hungary",ro:"Romania",bg:"Bulgaria",si:"Slovenia",hr:"Croatia",rs:"Serbia",gr:"Greece",ba:"Bosnia and Herzegovina",me:"Montenegro",mk:"North Macedonia",ee:"Estonia",lv:"Latvia",lt:"Lithuania",fi:"Finland",es:"Spain",pt:"Portugal",it:"Italy",gb:"United Kingdom",ie:"Ireland"};
const MIXC=[["nuc","Nuclear",["nuclear"]],["coal","Coal & lignite",["fossil_brown_coal_lignite","fossil_hard_coal","fossil_coal_derived_gas"]],["hyd","Hydro",["hydro_run_of_river","hydro_water_reservoir","hydro_pumped_storage"]],
 ["bio","Biomass & waste",["biomass","waste"]],["gas","Gas",["fossil_gas"]],["oil","Oil",["fossil_oil"]],["woff","Wind offshore",["wind_offshore"]],["won","Wind onshore",["wind_onshore"]],["sol","Solar",["solar"]],
 ["oth","Other",["geothermal","others"]]];
const NOTGEN=new Set(["load","residual_load","cross_border_electricity_trading","hydro_pumped_storage_consumption"]);
const RENEW=["hydro_run_of_river","hydro_water_reservoir","biomass","geothermal","wind_offshore","wind_onshore","solar"];
function sysData(c){const d=SYS[c];if(!d||!d.series)return null;const se=d.series,known=new Set(MIXC.flatMap(m=>m[2]));
 const mix={};MIXC.forEach(([k,,ids])=>{mix[k]=[...Array(NP)].map((_,h)=>{let s=0,any=false;ids.forEach(i=>{const v=se[i]&&se[i][h];if(v!=null){s+=Math.max(0,v);any=true}});return any?s:0})});
 Object.keys(se).forEach(id=>{if(!known.has(id)&&!NOTGEN.has(id))se[id].forEach((v,h)=>{if(v!=null&&v>0)mix.oth[h]+=v})});
 const gen=[...Array(NP)].map((_,h)=>MIXC.reduce((a,[k])=>a+mix[k][h],0)),load=se.load||null;
 const ren=[...Array(NP)].map((_,h)=>RENEW.reduce((a,i)=>a+Math.max(0,(se[i]&&se[i][h])||0),0));
 let last=NP-1;while(last>0&&gen[last]===0)last--;
 // TSOs publish technologies at different speeds: the hours after a technology's last report are "not yet reported", not zero.
 // `last` = latest hour at which every material technology (>= 3 % of the window's energy) has reported, so shares and the stack stay valid.
 const lastRep={},tot=gen.reduce((a,b)=>a+b,0)||1;let lastOk=NP-1;
 MIXC.forEach(([k,,ids])=>{let l=-1;for(let h=0;h<NP;h++)if(ids.some(i=>se[i]&&se[i][h]!=null))l=h;
  if(l>=0&&l<NP-1&&mix[k][l]<=0.02*Math.max(...mix[k]))l=NP-1;  // last reported value ~0 (night solar): omitted zeros, not a lag
  lastRep[k]=l;if(l>=0&&l<NP-1&&mix[k].reduce((a,b)=>a+b,0)/tot>=0.03)lastOk=Math.min(lastOk,l)});
 last=Math.max(0,Math.min(last,lastOk));
 // residual load = load - wind - solar (as newsletter/registry.py), only where load and the technologies have reported
 const vreOk=["won","woff","sol"].some(k=>lastRep[k]>=0),res=load&&vreOk?[...Array(NP)].map((_,h)=>h<=last&&load[h]!=null?load[h]-mix.won[h]-mix.woff[h]-mix.sol[h]:null):null;
 const fl=d.flows||{},net=fl.sum||null,nb=Object.keys(fl).filter(k=>k!=="sum");
 return{c,mix,gen,load,ren,last,lastRep,res,net,nb,fl,fn:d.flow_names||{},zones:d.zones||[],lag:d.lag_h||0}}

export { MIXC, SYS, SYSN, sysData };
