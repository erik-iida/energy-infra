/* Flags tab: fired signals table and the zone x metric percentile matrix (data/browse/flags.json).
   ES module (spec 3 step 2): imports name what this file needs from other modules, the export list at the end what it offers. */
import { S } from "../../core/data.js";
import { $ } from "../../core/util.js";
import { FX, fxDayLbl, fxFill, fxHash } from "./drilldown.js";
import { dbJson } from "../data/data.js";
/* ---------- Flags tab: signals and metric overview (web/data/browse/flags.json, built from the `store` release by scripts/build_browse.py with newsletter/signals.py) ---------- */
const FL={j:null,err:0,busy:0,all:false};
function flFmt(v,u){if(v==null)return"–";return v.toLocaleString("en",{maximumFractionDigits:Math.abs(v)>=100?0:1})}
function flagsTab(){const el=$("flg");
 if(!FL.j){if(FL.err){el.innerHTML="<div class='feednote'>No flags published yet. This tab reads the signals computed from the data store (last 90 days per zone), which the deploy job exports once the collector has run (see DEVNOTES: Data store, Newsletter generator).</div>";return}
  el.innerHTML="<div class='feednote'>Loading…</div>";if(!FL.busy){FL.busy=1;dbJson("data/browse/flags.json").then(j=>{FL.j=j;FL.busy=0;if(S.tab==="flg")flagsTab()}).catch(()=>{FL.err=1;FL.busy=0;if(S.tab==="flg")flagsTab()})}return}
 let j=FL.j;
 if(FX.day&&FX.day!==FL.j.day){
  if(!(FL.j.days||[]).includes(FX.day)){FX.gone=FX.day;FX.day=null;FX.open=null;fxHash()}
  else if(FX.dj[FX.day])j=FX.dj[FX.day];
  else{const d=FX.day;el.innerHTML="<div class='feednote'>Loading the flags for "+fxDayLbl(d,{year:"numeric"})+"…</div>";dbJson("data/browse/flags/"+d+".json").then(x=>{FX.dj[d]=x}).catch(()=>{FX.gone=d;FX.day=null;FX.open=null;fxHash()}).then(()=>{if(S.tab==="flg")flagsTab()});return}}
 if(FX.open&&FX.open.d!==j.day)FX.open=null;
 FX.cur=j;const latest=j.day===FL.j.day;
 const foc=new Set(j.focus),keep=r=>FL.all||foc.has(r.zone),rl={};j.rules.forEach(r=>rl[r.metric]=r);
 const dl=new Date(j.day+"T12:00:00Z").toLocaleDateString("en-GB",{day:"numeric",month:"short",year:"numeric",timeZone:"UTC"});
 const fired=j.scan.filter(r=>r.side&&keep(r)).sort((a,b)=>b.score-a.score);
 const zr=z=>foc.has(z)?j.focus.indexOf(z):100,zones=[...new Set(j.scan.filter(keep).map(r=>r.zone))].sort((a,b)=>zr(a)-zr(b)||a.localeCompare(b));
 const by={};j.scan.forEach(r=>by[r.zone+"|"+r.metric]=r);
 const gate=r=>{const a=[];if(r.hi!=null)a.push("≥ P"+Math.round(r.hi*100));if(r.lo!=null)a.push("≤ P"+Math.round(r.lo*100));return a.join(" or ")+(r.min_abs!=null?" and |value| ≥ "+r.min_abs+" "+r.unit:"")};
 let h=(FX.gone?"<div class='fxbad'>Context for <b>"+fxDayLbl(FX.gone,{year:"numeric"})+"</b> is no longer available: the Flags tab keeps the last "+((FL.j.days||[]).length||14)+" days. Showing the latest day instead.</div>":"")+"<div class='feednote'>Flags for <b>"+dl+"</b>"+(latest?", the latest complete CET day.":" (an earlier day; the latest is "+fxDayLbl(FL.j.day)+").")+" Click a signal to see the day behind it.</div><div class='feednote srcnote'><b>How flags work.</b> A flag fires when a zone's value sits in the tail of its <i>own</i> last "+j.window_days+" days (percentile P: share of those days at or below the value), with at least "+j.min_hist+" days of history and an absolute floor so a tiny number does not flag. The store holds "+j.hist_days+" days of prices so far, so percentiles firm up as the history backfills. Rules: "+j.rules.map(r=>r.label+" "+gate(r)).join("; ")+". Same signals as the newsletter (without the private spark spreads). Data: <a href='https://transparency.entsoe.eu' style='color:inherit'>ENTSO-E Transparency Platform</a>.</div>"
  +"<div class='row'>"+((FL.j.days||[]).length>1?"<label style='gap:6px;align-items:center'>Day <select id='fld'>"+FL.j.days.map((d,i)=>"<option value='"+d+"'"+(d===j.day?" selected":"")+">"+fxDayLbl(d,{weekday:"short"})+(i?"":" (latest)")+"</option>").join("")+"</select></label>":"")+"<label style='gap:6px;align-items:center'>Zones <select id='flz'><option value='f'"+(FL.all?"":" selected")+">CEE / SEE + DE-LU</option><option value='a'"+(FL.all?" selected":"")+">all zones in the store</option></select></label></div>";
 h+="<h3 class='flh'>Signals fired ("+fired.length+")</h3>";
 if(FX.open&&!fired.some(r=>r.zone===(FX.open.row||FX.open).z&&r.metric===(FX.open.row||FX.open).m))h+="<div class='dw fxsolo'><div class='fxp' id='fxp' role='region' aria-label='Context for "+FX.open.z+"'></div></div>";
 h+=fired.length?"<div class='dw' style='max-height:none'><table class='dt ft'><thead><tr><th>Zone</th><th style='text-align:left'>Signal</th><th>Value</th><th>Percentile</th><th>Typical (median · P10–P90)</th><th>Days in window</th></tr></thead><tbody>"+fired.map(r=>{const fr=FX.open&&(FX.open.row||FX.open),o=!!(fr&&fr.z===r.zone&&fr.m===r.metric);return"<tr class='fsr"+(o?" on":"")+"' tabindex='0' role='button' aria-expanded='"+o+"' data-z='"+r.zone+"' data-m='"+r.metric+"'><td><span class='chev' aria-hidden='true'>"+(o?"▾":"▸")+"</span>"+r.zone+"</td><td style='text-align:left'>"+rl[r.metric].label+" — "+(r.side==="high"?"unusually <b class='fh'>high</b>":"unusually <b class='fl'>low</b>")+"</td><td>"+flFmt(r.value)+" <span class='mut'>"+rl[r.metric].unit+"</span></td><td>P"+Math.round(r.pct*100)+"</td><td>"+flFmt(r.median)+" · "+flFmt(r.p10)+"–"+flFmt(r.p90)+"</td><td>"+r.n_hist+"</td></tr>"+(o?"<tr class='fxr'><td colspan='6' class='fxc'><div class='fxp' id='fxp' role='region' aria-label='Context for "+r.zone+" "+rl[r.metric].label+"'></div></td></tr>":"")}).join("")+"</tbody></table></div>":"<div class='feednote'>No metric left its own normal range for these zones on this day.</div>";
 h+="<h3 class='flh'>Overview, all metrics <span class='mut'>shade = percentile vs the zone's own last "+j.window_days+" days (orange high, blue low); bold = flag fired; grey = under "+j.min_hist+" days of history</span></h3>"
  +"<div class='dw'><table class='dt ft'><thead><tr><th>Zone</th>"+j.rules.map(r=>"<th>"+r.label+" <span class='mut'>"+r.unit+"</span></th>").join("")+"</tr></thead><tbody>"
  +zones.map(z=>"<tr><td>"+z+"</td>"+j.rules.map(r=>{const c=by[z+"|"+r.metric];if(!c)return"<td class='nu'>–</td>";
    let st="",cl="";if(c.status==="short")cl=" sh";else if(c.pct!=null){const a=Math.min(.75,Math.abs(c.pct-.5)*1.5);st="background:"+(c.pct>=.5?"rgba(194,65,12,"+a.toFixed(2)+")":"rgba(31,95,153,"+a.toFixed(2)+")")}
    if(c.side)cl+=" fd";const tip=c.pct==null?"under "+j.min_hist+" days of history ("+c.n_hist+")":"P"+Math.round(c.pct*100)+" of the last "+c.n_hist+" days · median "+flFmt(c.median)+" · P10–P90 "+flFmt(c.p10)+"–"+flFmt(c.p90)+(c.status==="gated"?" · below the absolute floor, no flag":"");
    return"<td class='"+cl.trim()+"' style='"+st+"' title='"+tip+"'>"+flFmt(c.value)+(c.pct!=null?"<span class='pc'>P"+Math.round(c.pct*100)+"</span>":"")+"</td>"}).join("")+"</tr>").join("")+"</tbody></table></div>"
  +"<div class='mut' style='font-size:12px'>Capture rate = generation-weighted day-ahead price ÷ baseload; only the low side flags. TB2 / TB4: mean of the 2 / 4 highest minus the 2 / 4 lowest hourly day-ahead prices of the CET day. Generated "+j.generated.slice(0,16).replace("T"," ")+" UTC.</div>";
 el.innerHTML=h;fxFill()}

$("flg").addEventListener("change",e=>{if(e.target.id==="flz"){FL.all=e.target.value==="a";flagsTab()}});

export { FL, flagsTab };
