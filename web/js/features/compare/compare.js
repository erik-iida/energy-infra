/* Compare tab: PyWake model selector, per-farm series, country aggregation and the dashboard cards / farm table.
   ES module (spec 3 step 2): imports name what this file needs from other modules, the export list at the end what it offers. */
import { F, FEED, S, inC, place } from "../../core/data.js";
import { $, eur, fg, fmt } from "../../core/util.js";
import { MODELS, N0, NT, SRC, agg, dl, farmCap, hl, series } from "../../core/feed.js";
import { CO, UMAX, aggW, arrow, chartSVG, fut, line, mean, ms, past } from "../../core/chart.js";
import { registerTab } from "../../core/router.js";
/* ---------- Compare tab ---------- */
S.fm=MODELS.turbopark?"turbopark":"jensen";
$("FM").innerHTML=Object.keys(MODELS).map(m=>"<option value='"+m+"'>"+MODELS[m]+"</option>").join("");$("FM").value=S.fm;
function dash(){series();const fs=F.filter(f=>inC(f,S.c)),A=agg(fs),lay=fs.filter(f=>f.lay),fr=lay.reduce((a,f)=>a+(f.Fr[N0]||0),0),pl=lay.reduce((a,f)=>a+(f.P[N0]||0),0);
 const age=FEED?(Date.now()-new Date(FEED.generated))/36e5:0;
 $("fnote").innerHTML=FEED?("<b>Feed: "+(SRC==="synthetic"?"synthetic test wind":SRC==="openmeteo"?"Open-Meteo, "+(FEED.nwp_model||"")+" forecast":SRC==="windy"?"Windy "+(FEED.windy_model||""):"ECMWF open data")+"</b>, wake losses from PyWake. Generated "+new Date(FEED.generated).toLocaleString()+(age>3?" <span class='warn'>(more than 3 h old, the hourly job may have stopped)</span>":"")+". History "+hl(0)+" → now "+hl(N0)+", forecast to "+dl(NT-1)+".")
  :"<b>No feed.json found</b>, showing synthetic wind through the in-browser models. Run the pipeline to get PyWake results.";
 const cfN=A.P[N0]/A.inst,pv=past(A.P).filter(x=>x!=null);
 $("hero").innerHTML=[[fg(A.P[N0]),place(S.c)+" now"],[(100*cfN).toFixed(0)+"%","capacity factor now"],[fg(mean(past(A.P))),"last 24 h mean"],[fg(mean(fut(A.P))),"next 24 h mean"],[pv.length?fg(Math.min(...pv))+" – "+fg(Math.max(...pv)):"–","last 24 h range"],[ms(aggW(fs)[N0]),"mean hub-height wind now"],[fr?(100*(1-pl/fr)).toFixed(1)+"%":"–","wake loss now (farms with layouts)"]].map(q=>"<div><b>"+q[0]+"</b><span>"+q[1]+"</span></div>").join("");
 const h=S.hh>=0?S.hh:N0;
 $("cards").innerHTML=CO().map(c=>{const a=agg(F.filter(f=>inC(f,c)));return"<div class='card"+(c===S.c?" on":"")+"' data-c='"+c+"'><h3>"+c+"<span>"+fg(a.P[h])+" · CF "+(a.P[h]==null?"–":(100*a.P[h]/a.inst).toFixed(0)+"%")+"</span></h3><div class='v mut'>"+(h===N0?"now":dl(h))+" · last 24 h mean "+fg(mean(past(a.P)))+" of "+fg(a.inst)+"</div><svg data-c='"+c+"'></svg><div class='v mut' style='margin-top:4px'>Wind at hub "+ms(aggW(F.filter(f=>inC(f,c)))[h])+"</div><svg class='w' data-c='"+c+"' data-w='1'></svg></div>"}).join("");
 $("cards").querySelectorAll("svg").forEach(sv=>{const W=sv.clientWidth||200,fc=F.filter(f=>inC(f,sv.dataset.c)),a=agg(fc),L=line([],1,W,64,3);
  if(sv.dataset.w){sv.setAttribute("viewBox","0 0 "+W+" 48");sv.innerHTML=chartSVG(aggW(fc).map(u=>u==null?null:u/UMAX),W,46,true,11.5/UMAX,"≈ rated 11.5 m/s");return}
  sv.setAttribute("viewBox","0 0 "+W+" 78");
  sv.innerHTML=chartSVG(a.P.map(p=>p==null?null:p/a.inst),W,64,true)+"<text class='tl' x='3' y='76'>−24 h</text><text class='tl' x='"+L.x(N0)+"' y='76' text-anchor='middle'>now</text><text class='tl' x='"+(W-3)+"' y='76' text-anchor='end'>+24 h</text>"});
 $("fh").textContent=(S.c?S.c+" farms":"All farms")+" ("+fs.length+")";
 const rows=fs.map(f=>({f,i:F.indexOf(f),now:f.P[N0],cf:f.P[N0]==null?null:f.P[N0]/f.inst,wl:f.lay&&f.Fr[N0]?1-f.P[N0]/f.Fr[N0]:null,cp:farmCap(f).cap,wc:farmCap(f).wc,avg:mean(past(f.P)),nx:mean(fut(f.P)),u:f.U48[N0]}));
 const[k,dirn]=S.sort,val=r=>k==="n"?r.f.n:k==="c"?r.f.c:k==="inst"?r.f.inst:r[k]??-1;rows.sort((a,b)=>{const x=val(a),y=val(b);return(typeof x==="string"?x.localeCompare(y):x-y)*dirn});
 const cols=[["n","Farm"],["c","Country"],["inst","Installed"],["now","Now"],["cf","CF now"],["wl","Wake loss"],["cp","Capture 24 h"],["wc","Wake cost 24 h"],["u","Wind now"],["sp","Output ±24 h"],["sw","Wind ±24 h"],["avg","Last 24 h"],["nx","Next 24 h"]];
 $("ftab").tHead.rows[0].innerHTML=cols.map(q=>"<th data-k='"+q[0]+"'>"+q[1]+(S.sort[0]===q[0]?(S.sort[1]>0?" ▲":" ▼"):"")+"</th>").join("");
 $("ftab").tBodies[0].innerHTML=rows.map(r=>{const L=line(r.f.P.map(p=>p==null?null:p/r.f.inst),1,104,22,2);return"<tr data-i='"+r.i+"' class='"+(r.f.lay?"":"est")+"'><td>"+r.f.n+"</td><td>"+r.f.c+"</td><td>"+fmt(r.f.inst)+"</td><td>"+fmt(r.now)+"</td><td>"+(r.cf==null?"–":(100*r.cf).toFixed(0)+"%")+"</td><td>"+(r.wl==null?"–":Math.max(0,100*r.wl).toFixed(1)+"%")+"</td><td>"+(r.cp==null?"–":r.cp.toFixed(1)+" €/MWh")+"</td><td>"+eur(r.wc)+"</td><td>"+ms(r.u)+arrow(r.f.D48[N0])+"</td><td><svg viewBox='0 0 104 22' data-i='"+r.i+"'><line class='nowl' x1='"+L.x(N0)+"' x2='"+L.x(N0)+"' y1='0' y2='22'/><path class='ln' style='stroke-width:1.5' d='"+L.p+"'/><path class='ln fc' style='stroke-width:1.5' d='"+L.f+"'/></svg></td><td>"+(()=>{const W=line(r.f.U48.map(u=>u==null?null:u/UMAX),1,104,22,2);return"<svg class='w' viewBox='0 0 104 22' data-i='"+r.i+"' data-w='1'><line class='nowl' x1='"+W.x(N0)+"' x2='"+W.x(N0)+"' y1='0' y2='22'/><path class='ln' style='stroke-width:1.5' d='"+W.p+"'/><path class='ln fc' style='stroke-width:1.5' d='"+W.f+"'/></svg>"})()+"</td><td>"+fmt(r.avg)+"</td><td>"+fmt(r.nx)+"</td></tr>"}).join("")}
registerTab("cmp",{el:"dash",render:dash});

export { dash };
