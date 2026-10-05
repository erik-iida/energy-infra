/* Data tab: time-series browser (any zones x any variables, CSV) and the installed-capacity / capacity-factor view (data/browse/*).
   ES module (spec 3 step 2): imports name what this file needs from other modules, the export list at the end what it offers. */
import { S } from "../../core/data.js";
import { $ } from "../../core/util.js";
import { dbJson } from "../../core/load.js";
import { registerTab } from "../../core/router.js";
/* ---------- Data tab: one flexible time-series browser (any variables x any zones) plus the installed-capacity view ---------- */
/* web/data/browse/{index.json, ts/<zone>.json, capacity.json}, built from the `store` release by scripts/build_browse.py */
const DB={idx:null,err:0,busy:0,mode:"ts",zs:["RO"],on:null,days:7,tz:"CET",desc:true,cache:{},open:{},tok:0,cap:null,cv:"cf",cf:"all",cur:null};
const DBFIRST=["PL","CZ","SK","HU","RO","BG","SI","HR","RS","GR","BA","ME","MK","EE","LV","LT","DE-LU"];
function dbFmt(t,tz){if(tz==="UTC")return new Date(t*1000).toISOString().slice(0,16).replace("T"," ");return new Intl.DateTimeFormat("sv-SE",{timeZone:"Europe/Berlin",year:"numeric",month:"2-digit",day:"2-digit",hour:"2-digit",minute:"2-digit"}).format(new Date(t*1000))}
function dbNum(v,u){return v==null?"–":v.toLocaleString("en",{maximumFractionDigits:u&&u.endsWith("/MWh")?2:1})}
function dbZonesAll(){const z=DB.idx.zones;return DBFIRST.filter(x=>z.includes(x)).concat(z.filter(x=>!DBFIRST.includes(x)))}
function dbModeBar(){return"<div class='row'><span class='seg big' id='dbmode'><button data-m='ts' class='"+(DB.mode==="ts"?"on":"")+"'>Time series</button>"+(DB.idx.capacity?"<button data-m='cap' class='"+(DB.mode==="cap"?"on":"")+"'>Installed capacity &amp; capacity factor</button>":"")+"</span></div>"}
function dataTab(){const el=$("dat");
 if(!DB.idx){if(DB.err){el.innerHTML="<div class='feednote'>No stored data is published yet. The Data tab reads the last 30 days of the data store, which the deploy job exports once the collector has run (see DEVNOTES: Data store).</div>";return}
  el.innerHTML="<div class='feednote'>Loading…</div>";if(!DB.busy){DB.busy=1;dbJson("data/browse/index.json").then(j=>{DB.idx=j;DB.busy=0;if(S.tab==="dat")dataTab()}).catch(()=>{DB.err=1;DB.busy=0;if(S.tab==="dat")dataTab()})}return}
 if(!DB.idx.zones.length){DB.idx=null;DB.err=1;dataTab();return}
 if(!DB.on){DB.on={};DB.idx.vars.forEach(v=>{if(v.def)DB.on[v.id]=1})}
 DB.zs=DB.zs.filter(z=>DB.idx.zones.includes(z));if(!DB.zs.length)DB.zs=[DB.idx.zones.includes("RO")?"RO":DB.idx.zones[0]];
 if(DB.mode==="cap"&&!DB.idx.capacity)DB.mode="ts";
 if(DB.mode==="cap"){capView();return}tsView()}
function tsView(){const my=++DB.tok,need=DB.zs.filter(z=>!(z in DB.cache)),go=()=>{if(my===DB.tok&&S.tab==="dat"&&DB.mode==="ts")tsRender()};
 if(!need.length){go();return}
 $("dat").innerHTML=dbModeBar()+"<div class='feednote'>Loading…</div>";
 Promise.all(need.map(z=>dbJson("data/browse/ts/"+z+".json").then(f=>{f.ix={};f.cols.forEach((c,i)=>f.ix[c.id]=i);DB.cache[z]=f}).catch(()=>{DB.cache[z]=null}))).then(go)}
function tsRender(){const I=DB.idx,zf=DB.zs.filter(z=>DB.cache[z]);
 if(!zf.length){$("dat").innerHTML=dbModeBar()+"<div class='feednote'>No stored rows for this zone.</div>";return}
 const av=new Set();zf.forEach(z=>DB.cache[z].cols.forEach(c=>av.add(c.id)));
 const cols=[];I.vars.forEach(v=>{if(!DB.on[v.id]||!av.has(v.id))return;zf.forEach(z=>{const f=DB.cache[z],k=f.ix[v.id];if(k!=null)cols.push({z,v,c:f.cols[k],a:f.v[k]})})});
 const f0=DB.cache[zf[0]],t0=f0.t0,step=f0.step,n=f0.v[0].length,multi=DB.zs.length>1;
 const zop=!!DB.open.__z,zchips="<div class='chips' id='dbzs'>"+(zop?dbZonesAll():DB.zs).map(z=>"<button class='chip"+(DB.zs.includes(z)?" on":"")+"' data-z='"+z+"'>"+z+"</button>").join("")+"</div>";
 let vh="";I.groups.forEach((g,gi)=>{const vs=I.vars.filter(v=>v.grp===g&&av.has(v.id));if(!vs.length)return;const op=!!DB.open[g],non=vs.filter(v=>DB.on[v.id]).length,shown=op?vs:vs.filter(v=>DB.on[v.id]);
  vh+="<div class='vg'><div class='vgh'><button class='gtog' data-g='"+g+"' title='"+(op?"Hide the unselected variables":"Show all variables of this group")+"'>"+(op?"▾ ":"▸ ")+g+"</button><span class='mut'>"+non+" of "+vs.length+" shown</span><button class='gall' data-g='"+g+"'>all</button><button class='gnone' data-g='"+g+"'>none</button></div>"
   +(shown.length?"<div class='chips'>"+shown.map(v=>"<button class='chip vchip"+(DB.on[v.id]?" on":"")+"' data-v='"+v.id+"' title='"+v.unit+"' style='"+(v.tech?"--c:var(--m-"+v.tech+")":"")+"'><i></i>"+v.name+"</button>").join("")+"</div>":"")+"</div>"});
 const nowH=Math.floor(Date.now()/3600000)*3600;let last=-1;for(let r=n-1;r>=0&&last<0;r--)if(cols.some(c=>c.a[r]!=null))last=r;if(last<0)last=n-1;
 const first=Math.max(0,last-DB.days*24+1),rows=[];for(let r=first;r<=last;r++)rows.push(r);if(DB.desc)rows.reverse();
 const stat=c=>{const a=[];for(let r=first;r<=last;r++)if(c.a[r]!=null)a.push(c.a[r]);return a.length?{mn:Math.min(...a),mx:Math.max(...a),av:a.reduce((x,y)=>x+y,0)/a.length}:null};
 const st=cols.map(stat),sm=(lab,fn)=>"<tr class='sm'><td>"+lab+"</td>"+cols.map((c,j)=>"<td>"+(st[j]?dbNum(fn(st[j]),c.c.unit):"–")+"</td>").join("")+"</tr>";
 let tb="<div class='feednote'>Pick any zones and any variables; they combine in one table.</div><div class='feednote srcnote'><b>Data tab.</b> Stored history from the ENTSO-E Transparency Platform, hourly means of the native-resolution rows (UTC hours), last 30 days; the store itself keeps more and the full resolution. Exported "+I.generated.slice(0,16).replace("T"," ")+" UTC. Day-ahead prices: auction result only (classification sequence 1). Daily columns (baseload, TB2, TB4, capture rates …) are computed per CET day and repeated on every hour of that day. Rows marked ·fc are in the future (day-ahead data). Great Britain (GB: generation, demand, interconnector flows): Contains BMRS data © Elexon Limited copyright and database right "+new Date().getFullYear()+" (<a href='https://www.elexon.co.uk/data/balancing-mechanism-reporting-agent/copyright-licence-bmrs-data/' style='color:inherit'>BMRS open data licence</a>); GB load = national demand plus the embedded wind and solar estimate; GB price: Market Index Data (APX / EPEX SPOT trades via Elexon BMRS; third-party data, an index of half-hourly trades, not an auction result), stored in GBP and shown here, like TB2 / TB4 and the capture metrics, in EUR at the ECB daily reference rate; GB imbalance prices are stored too. GB history since 2009, demand and forecasts in the store: Supported by National Energy SO Open Data (<a href=\'https://www.neso.energy/data-portal/neso-open-licence\' style=\'color:inherit\'>NESO Open Data Licence</a>); GB unit output also from BMRS (B1610); plant sites: DESNZ Renewable Energy Planning Database (<a href=\'https://www.gov.uk/government/publications/renewable-energy-planning-database-quarterly-extract\' style=\'color:inherit\'>Open Government Licence v3.0</a>). Ireland (IE(SEM)) load: Supported by EirGrid Group Data (<a href='https://www.smartgriddashboard.com/all/open-data-license' style='color:inherit'>EirGrid open data licence</a>).</div>"
  +dbModeBar()
  +"<div class='row'><label style='gap:6px;align-items:center'>Show <select id='dbn'>"+[[1,"last day"],[3,"last 3 days"],[7,"last 7 days"],[14,"last 14 days"],[30,"all 30 days"]].map(([k,t])=>"<option value='"+k+"'"+(k===DB.days?" selected":"")+">"+t+"</option>").join("")+"</select></label>"
  +"<span class='seg' id='dbtz'><button data-z='CET' class='"+(DB.tz==="CET"?"on":"")+"'>CET/CEST</button><button data-z='UTC' class='"+(DB.tz==="UTC"?"on":"")+"'>UTC</button></span>"
  +"<span class='seg' id='dbo'><button data-o='1' class='"+(DB.desc?"on":"")+"'>Newest first</button><button data-o='0' class='"+(DB.desc?"":"on")+"'>Oldest first</button></span>"
  +"<button id='dbcsv' style='width:auto;padding:5px 11px;font-size:13px'>Download CSV</button></div>"
  +"<div class='row'><button class='gtog' id='dbzt' style='width:auto;border:0;background:none;padding:2px 0;font-weight:600'>"+(zop?"▾ ":"▸ ")+"Zones ("+DB.zs.length+")</button><span class='seg' id='dbq'><button data-q='focus'>CEE / SEE + DE-LU</button><button data-q='one'>Only "+DB.zs[0]+"</button></span></div>"+zchips
  +"<div class='row' style='margin-top:2px'><span style='font-size:13px;font-weight:600'>Variables</span><span class='mut' style='font-size:12px'>click a group name to see all of its variables</span></div>"+vh;
 const head=c=>(multi?"<span class='mut'>"+c.z+"</span> ":"")+c.v.name+" <span class='mut'>"+c.c.unit+"</span>";
 tb+=cols.length?"<div class='dw'><table class='dt'><thead><tr><th>Time ("+(DB.tz==="UTC"?"UTC":"CET/CEST")+")</th>"+cols.map(c=>"<th>"+head(c)+"</th>").join("")+"</tr></thead><tbody>"+sm("Mean",x=>x.av)+sm("Min",x=>x.mn)+sm("Max",x=>x.mx)
  +rows.map(r=>{const t=t0+r*step;return"<tr"+(t>=nowH+3600?" class='fc'":"")+"><td>"+dbFmt(t,DB.tz)+"</td>"+cols.map(c=>{const v=c.a[r];return"<td"+(v==null?" class='nu'":v<0?" class='ng'":"")+">"+dbNum(v,c.c.unit)+"</td>"}).join("")+"</tr>"}).join("")
  +"</tbody></table></div><div class='mut' style='font-size:12px'>"+rows.length+" hours × "+cols.length+" columns. Negative values in red, – = nothing stored for that hour (not yet published, or the TSO doesn't report it). Source: <a href='https://transparency.entsoe.eu' style='color:inherit'>ENTSO-E Transparency Platform</a>.</div>":"<div class='feednote'>No variable switched on for the selected zones.</div>";
 $("dat").innerHTML=tb;DB.cur={cols,t0,step,rows,multi}}
function dbCsv(){const c=DB.cur;if(!c)return;const q=x=>'"'+String(x).replace(/"/g,'""')+'"';
 let t=["utc,local_cet"].concat(c.cols.map(k=>q((c.multi?k.z+" · ":"")+k.v.name+" ["+k.c.unit+"]"))).join(",")+"\n";
 c.rows.forEach(r=>{const ts=c.t0+r*c.step;t+=[dbFmt(ts,"UTC"),dbFmt(ts,"CET")].concat(c.cols.map(k=>k.a[r]==null?"":k.a[r])).join(",")+"\n"});
 const a=document.createElement("a");a.href=URL.createObjectURL(new Blob([t],{type:"text/csv"}));a.download="radialeconomics_timeseries.csv";a.click();setTimeout(()=>URL.revokeObjectURL(a.href),2000)}
/* installed capacity (IRENA, annual, reference only), 90-day peak output (capacity proxy) and 30-day CF vs that peak: web/data/browse/capacity.json */
function capRows(c){const f=DB.cf==="zone"?c.rows.filter(r=>r.zones.length):c.rows.slice(),rk=r=>{const i=Math.min(...r.zones.map(z=>DBFIRST.indexOf(z)<0?99:DBFIRST.indexOf(z)));return r.zones.length?i:100};
 return f.sort((x,y)=>rk(x)-rk(y)||x.name.localeCompare(y.name))}
function capView(){const el=$("dat");
 const go=c=>{if(S.tab!=="dat"||DB.mode!=="cap")return;const v=DB.cv||"cf",cls=c.classes,rows=capRows(c),nz=c.rows.filter(r=>r.zones.length).length;
  const cell=(r,k)=>{const x=((v==="gw"?r.gw:v==="pk"?r.pk:r.cf)||{})[k];return x==null?"<td class='nu'>–</td>":"<td>"+x.toLocaleString("en",{maximumFractionDigits:v==="cf"?1:2})+"</td>"};
  let h="<div class='feednote'>Capacity factor against each technology's highest hourly output in the last 90 days; installed GW from IRENA as a reference (method under Sources and notes).</div><div class='feednote srcnote'><b>Capacity factor</b> = mean ENTSO-E actual output over "+c.cf_window[0]+" to "+c.cf_window[1]+" ÷ the highest hourly output of the same technology "+(c.peak_window?"from "+c.peak_window[0]+" to "+c.peak_window[1]:"in the last 90 days")+". That peak is the capacity proxy: IRENA's year-end installed capacity is older than the fleet, so it no longer serves as the denominator. Because a fleet never runs at 100 % at once, this reads higher than a nameplate capacity factor. Shown for countries whose bidding zones are all in the store (multi-zone countries are summed hour by hour). <b>Installed GW</b> is the IRENA Renewable Energy Statistics reference (year-end of each country's latest year; DE-LU = Germany + Luxembourg).</div>"
  +dbModeBar()
  +"<div class='row'><span class='seg' id='cpv'><button data-v='cf' class='"+(v==="cf"?"on":"")+"'>30-day capacity factor %</button><button data-v='pk' class='"+(v==="pk"?"on":"")+"'>Peak output, 90 days GW</button><button data-v='gw' class='"+(v==="gw"?"on":"")+"'>Installed GW (IRENA)</button></span>"
  +"<label style='gap:6px;align-items:center'>Show <select id='cpf'><option value='all'"+(DB.cf==="zone"?"":" selected")+">all "+c.rows.length+" IRENA countries</option><option value='zone'"+(DB.cf==="zone"?" selected":"")+">"+nz+" countries with a bidding zone</option></select></label>"
  +"<button id='cpcsv' style='width:auto;padding:5px 11px;font-size:13px'>Download CSV</button></div>"
  +"<div class='dw'><table class='dt'><thead><tr><th>Country</th><th>Zones</th>"+(v==="gw"?"<th>IRENA year</th>":"")+cls.map(k=>"<th>"+k.name+" <span class='mut'>"+(v==="cf"?"%":"GW")+"</span></th>").join("")+"</tr></thead><tbody>"
  +rows.map(r=>"<tr><td>"+r.name+"</td><td style='text-align:left' title='"+r.zones.join(", ")+"'>"+(r.zones.length>3?r.zones.length+" zones":r.zones.join(", ")||"–")+"</td>"+(v==="gw"?"<td>"+r.year+"</td>":"")+cls.map(k=>cell(r,k.id)).join("")+"</tr>").join("")+"</tbody></table></div>"
  +"<div class='mut' style='font-size:12px'>"+rows.length+" countries. Installed capacity: IRENA Renewable Energy Statistics, © IRENA (<a href='https://www.irena.org/Data' style='color:inherit'>irena.org/Data</a>). Generation: <a href='https://transparency.entsoe.eu' style='color:inherit'>ENTSO-E Transparency Platform</a>. Fossil capacity is one class (not every country splits it by fuel); ENTSO-E generation can miss small distributed solar, which lowers its capacity factor.</div>";
  el.innerHTML=h};
 if(DB.cap){go(DB.cap);return}
 el.innerHTML=dbModeBar()+"<div class='feednote'>Loading…</div>";dbJson("data/browse/capacity.json").then(c=>{DB.cap=c;go(c)}).catch(()=>{el.innerHTML=dbModeBar()+"<div class='feednote'>No capacity table published yet.</div>"})}
function capCsv(){const c=DB.cap;if(!c)return;const q=x=>'"'+String(x).replace(/"/g,'""')+'"',cl=c.classes;
 let t=["iso3","country","zones","irena_year"].concat(cl.map(k=>k.name+" [IRENA GW]")).concat(cl.map(k=>k.name+" [peak 90 d GW]")).concat(cl.map(k=>k.name+" [30-day CF vs peak %]")).map(q).join(",")+"\n";
 const gv=(o,k)=>o&&o[k]!=null?o[k]:"";capRows(c).forEach(r=>{t+=[r.id,r.name,r.zones.join(" "),r.year].map(q).concat(cl.map(k=>gv(r.gw,k.id)),cl.map(k=>gv(r.pk,k.id)),cl.map(k=>gv(r.cf,k.id))).join(",")+"\n"});
 const a=document.createElement("a");a.href=URL.createObjectURL(new Blob([t],{type:"text/csv"}));a.download="radialeconomics_capacity.csv";a.click();setTimeout(()=>URL.revokeObjectURL(a.href),2000)}
$("dat").addEventListener("click",e=>{let b;
 if(b=e.target.closest("#dbmode button")){DB.mode=b.dataset.m;dataTab()}
 else if(b=e.target.closest("#dbzs .chip")){const z=b.dataset.z,i=DB.zs.indexOf(z);if(i>=0){if(DB.zs.length>1)DB.zs.splice(i,1)}else DB.zs.push(z);tsView()}
 else if(e.target.closest("#dbzt")){DB.open.__z=!DB.open.__z;tsRender()}
 else if(b=e.target.closest("#dbq button")){DB.zs=b.dataset.q==="focus"?DBFIRST.filter(z=>DB.idx.zones.includes(z)):[DB.zs[0]];tsView()}
 else if(b=e.target.closest(".vchip")){DB.on[b.dataset.v]=DB.on[b.dataset.v]?0:1;tsRender()}
 else if(b=e.target.closest(".gtog")){const g=b.dataset.g;DB.open[g]=!DB.open[g];tsRender()}
 else if(b=e.target.closest(".gall,.gnone")){const g=b.dataset.g,on=b.classList.contains("gall")?1:0,av=new Set();DB.zs.forEach(z=>DB.cache[z]&&DB.cache[z].cols.forEach(c=>av.add(c.id)));DB.idx.vars.forEach(v=>{if(v.grp===g&&av.has(v.id))DB.on[v.id]=on});DB.open[g]=true;tsRender()}
 else if(b=e.target.closest("#dbtz button")){DB.tz=b.dataset.z;tsRender()}
 else if(b=e.target.closest("#dbo button")){DB.desc=b.dataset.o==="1";tsRender()}
 else if(e.target.closest("#dbcsv"))dbCsv()
 else if(b=e.target.closest("#cpv button")){DB.cv=b.dataset.v;capView()}
 else if(e.target.closest("#cpcsv"))capCsv()});
$("dat").addEventListener("change",e=>{if(e.target.id==="cpf"){DB.cf=e.target.value;capView()}else if(e.target.id==="dbn"){DB.days=+e.target.value;tsRender()}});
registerTab("dat",{el:"dat",render:dataTab});
