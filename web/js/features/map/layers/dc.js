/* DC interconnectors: ends placed in bidding zones, flow direction from the System data.
   Spec 3 step 2, push 3: moved from the former single page script unchanged; classic script, shared global scope. */
// ---- DC interconnectors: flow direction from the System data (cross-border physical flows, country level) ----
// Each DC link's two ends are placed in a bidding zone (zones.json, point in polygon, else nearest zone within ~0.6°);
// links whose ends are in two countries get the latest hourly border flow between those countries (import positive on
// SYS[a].flows[b]; the other side is used when one is missing or zero). The value is the whole border, all links on it.
const DCX={links:null,asof:null};
const FLN={austria:"at",belgium:"be",switzerland:"ch",czech_republic:"cz",germany:"de",denmark:"dk",estonia:"ee",spain:"es",finland:"fi",france:"fr",united_kingdom:"gb",greece:"gr",croatia:"hr",hungary:"hu",ireland:"ie",italy:"it",lithuania:"lt",luxembourg:"de",latvia:"lv",montenegro:"me",north_macedonia:"mk",netherlands:"nl",norway:"no",poland:"pl",portugal:"pt",romania:"ro",serbia:"rs",sweden:"se",slovenia:"si",slovakia:"sk",bosnia_and_herzegovina:"ba",bulgaria:"bg",albania:"al",ukraine:"ua",moldova:"md"};
const flKey=k=>{k=String(k).toLowerCase();return k==="sum"?null:FLN[k]||k.slice(0,2)};
function dcInRings(x,y,rs){let c=false;rs.forEach(r=>{for(let i=0,j=r.length-2;i<r.length;j=i,i+=2){const xi=r[i],yi=r[i+1],xj=r[j],yj=r[j+1];if((yi>y)!==(yj>y)&&x<(xj-xi)*(y-yi)/(yj-yi)+xi)c=!c}});return c}
function dcZone(x,y){let best=null,bd=0.36;for(const[z,Z]of Object.entries(MZ.d)){const b=Z.b;if(x<b[0]-1||x>b[2]+1||y<b[1]-1||y>b[3]+1)continue;
  if(x>=b[0]&&x<=b[2]&&y>=b[1]&&y<=b[3]&&dcInRings(x,y,Z.p))return z;
  Z.p.forEach(r=>{for(let i=0;i<r.length;i+=2){const d=(r[i]-x)**2*Math.cos(y*Math.PI/180)**2+(r[i+1]-y)**2;if(d<bd){bd=d;best=z}}})}return best}
function dcFlow(a,b){let best=null;[[a,b,1],[b,a,-1]].forEach(([p,q,sg])=>{const F=SYS[p]&&SYS[p].flows;if(!F)return;
  for(const[k,v]of Object.entries(F)){if(flKey(k)!==q||!Array.isArray(v))continue;let i=v.length-1;while(i>=0&&v[i]==null)i--;if(i<0)continue;
   const c={v:sg*v[i],i};if(!best||(best.v===0&&c.v!==0)||(c.v!==0&&c.i>best.i))best=c}});return best}
