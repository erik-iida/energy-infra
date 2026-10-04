/* Site data, feed and shared state: DATA / FEED (loaded by index.html), farms F, zones Z, state S, turbine types TY, regions, groups, countries.
   Spec 3 step 2, push 3: moved from the former single page script unchanged; classic script, shared global scope. */
const DATA=window.SITE,FEED=window.FEED||null;
const F=DATA.farms,Z=DATA.zones,S={c:null,farm:null,hover:-1,zh:-1,tab:"map",hh:-1,sort:["now",-1]};
const TY=DATA.types||[];
F.forEach(f=>{f.lay=!!f.xy;f.inst=f.lay?(f.inst||f.mw*f.xy.length/2):f.cap;f.tix=f.lay&&f.ti!=null&&TY.length?(Array.isArray(f.ti)?f.ti:Array(f.xy.length/2).fill(f.ti)):null;
 if(!f.lay){const kx=111320*Math.cos(f.lat*Math.PI/180);f.o=f.ol.map(r=>r.map((v,i)=>i%2?(v-f.lat)*110574:(v-f.lon)*kx))}});
F.forEach(f=>{f.rg=f.rg||"Europe"});Z.forEach(z=>{z.rg=z.rg||"Europe"});
const GROUPS={"CEE / SEE":["Poland","Czechia","Slovakia","Hungary","Romania","Bulgaria","Slovenia","Croatia","Serbia","Greece","Bosnia and Herzegovina","Montenegro","North Macedonia","Estonia","Latvia","Lithuania"]};
const RGOF={};[...F,...Z].forEach(x=>{RGOF[x.c]=x.rg});
const REGIONS=[...new Set(F.map(f=>f.rg))].sort((a,b)=>F.filter(f=>f.rg===b).reduce((s,f)=>s+f.inst,0)-F.filter(f=>f.rg===a).reduce((s,f)=>s+f.inst,0));
const isReg=c=>REGIONS.includes(c)||!!GROUPS[c];
// c: null = world, a region name, or a country
function inC(x,c){return !c||x.c===c||x.rg===c||(GROUPS[c]&&GROUPS[c].includes(x.c))}
const place=c=>c||"World";
function sum(c){return F.filter(f=>inC(f,c)).reduce((a,f)=>a+f.inst,0)}
const COUNTRIES=[...new Set([...F.map(f=>f.c),...Z.map(z=>z.c)])].sort((a,b)=>sum(b)-sum(a)||a.localeCompare(b));
// power-system countries without wind farms (System / Market tabs, ENTSO-E): name -> map box [W,S,E,N]
const CBOX={Czechia:[12,48.5,19,51.1],Slovakia:[16.8,47.7,22.6,49.6],Hungary:[16,45.7,22.9,48.6],Romania:[20.2,43.6,29.7,48.3],Bulgaria:[22.3,41.2,28.6,44.2],
 Slovenia:[13.3,45.4,16.6,46.9],Croatia:[13.4,42.4,19.5,46.6],Serbia:[18.8,42.2,23,46.2],Greece:[19.3,34.8,28.3,41.8],"Bosnia and Herzegovina":[15.7,42.5,19.7,45.3],
 Montenegro:[18.4,41.8,20.4,43.6],"North Macedonia":[20.4,40.8,23.1,42.4],Austria:[9.5,46.3,17.2,49.1],Switzerland:[5.9,45.8,10.5,47.9],Italy:[6.6,36.6,18.6,47.1],
 Latvia:[20.9,55.6,28.3,58.1],Lithuania:[20.9,53.8,26.9,56.5]};
Object.keys(CBOX).forEach(c=>{RGOF[c]=RGOF[c]||"Europe";if(!COUNTRIES.includes(c))COUNTRIES.push(c)});GROUPS["CEE / SEE"].forEach(c=>{RGOF[c]=RGOF[c]||"Europe";if(!COUNTRIES.includes(c))COUNTRIES.push(c)});
