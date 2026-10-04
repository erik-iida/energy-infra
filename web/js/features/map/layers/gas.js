/* Gas layer: ENTSOG interconnection points, LNG terminals and production entries (data/gas.json).
   Spec 3 step 2, push 3: moved from the former single page script unchanged; classic script, shared global scope. */
// ---- gas: ENTSOG interconnection points, LNG terminals, production entry (web/data/gas.json, daily GWh/d) ----
const GAS={d:null,loading:false,pts:[]};window.GAS=GAS;
const GCN={DE:"Germany",DK:"Denmark",NL:"Netherlands",BE:"Belgium",FR:"France",PL:"Poland",AT:"Austria",CZ:"Czechia",SK:"Slovakia",HU:"Hungary",IT:"Italy",ES:"Spain",PT:"Portugal",
 SI:"Slovenia",HR:"Croatia",RO:"Romania",BG:"Bulgaria",GR:"Greece",LT:"Lithuania",LV:"Latvia",EE:"Estonia",FI:"Finland",SE:"Sweden",IE:"Ireland",UK:"United Kingdom",LU:"Luxembourg",
 CH:"Switzerland",AL:"Albania (TAP)",UA:"Ukraine",TR:"Türkiye",RS:"Serbia",MD:"Moldova",MK:"North Macedonia",NO:"Norway"};
const gname=c=>GCN[c]||c;
function gasLoad(){if(GAS.d||GAS.loading)return;GAS.loading=true;fetch("data/gas.json",{cache:"no-cache"}).then(r=>r.ok?r.json():null).then(j=>{if(j){GAS.d=j;repaint();if(S.tab==="sys")system()}}).catch(()=>{})}
function gasDraw(){gasLoad();GAS.pts=[];if(!GAS.d)return;const v=viewBox(),gc=css("--m-gas"),pn=css("--panel");
 GAS.d.points.forEach((p,i)=>{const key=p.t==="lng"?"glng":p.t==="prod"?"gprod":"gip";if(HID.has(key))return;if(p.lon<v[0]||p.lon>v[2]||p.lat<v[1]||p.lat>v[3])return;
  const val=p.v[p.v.length-1]||0,r=2.5+Math.sqrt(val)/2.3,[x,y]=P(p.lon,p.lat);cx.beginPath();
  if(p.t==="lng"){cx.moveTo(x,y-r*1.2);cx.lineTo(x+r*1.2,y);cx.lineTo(x,y+r*1.2);cx.lineTo(x-r*1.2,y);cx.closePath()}else if(p.t==="prod")cx.rect(x-r,y-r,2*r,2*r);else cx.arc(x,y,r,0,7);
  cx.fillStyle=gc;cx.globalAlpha=val>0.5?.78:.25;cx.fill();cx.globalAlpha=1;cx.strokeStyle=pn;cx.lineWidth=1;cx.stroke();GAS.pts.push([x,y,r,i])})}
function gasHit(x,y){let b=-1,bd=1e9;GAS.pts.forEach(p=>{const d=Math.hypot(p[0]-x,p[1]-y);if(d<p[2]+5&&d<bd){bd=d;b=p[3]}});return b}
function gasTip(i){const p=GAS.d.points[i],n=p.v.length,last=p.v[n-1],avg=p.v.reduce((a,b)=>a+b,0)/n,ty={ip:"interconnection point",imp:"import point",lng:"LNG terminal",prod:"production entry"}[p.t];
 const dir=p.d&&p.d[1]?(p.d[0]?gname(p.d[0])+" → ":(p.from?p.from+" → ":"into "))+gname(p.d[1]):"";
 return p.n+" · gas "+ty+" · "+Math.round(last)+" GWh/d on "+GAS.d.days[n-1]+(dir?" ("+dir+")":"")+" · 8-day avg "+Math.round(avg)+" GWh/d · position approximate"}
