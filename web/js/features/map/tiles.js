/* Basemap tile layers (CARTO, OpenStreetMap, satellite, terrain hillshade) reprojected into the map view.
   Spec 3 step 2, push 3: moved from the former single page script unchanged; classic script, shared global scope. */
// ---- web-mercator tile layers, reprojected into this map's equirectangular view ----
// OpenStreetMap standard tiles (basemap) and Mapterhorn terrain (terrarium elevation -> hillshade computed here).
// CARTO raster basemaps need a key (watermark without one). The deploy job writes it in place of the placeholder from the
// CARTO_KEY Actions secret (hourly.yml); without it the old keyless host is used (tiles carry the watermark).
const CARTO_KEY="__CARTO_KEY__",cartoOk=!/^__/.test(CARTO_KEY);
const cartoUrl=(st,z,x,y)=>{const r=(devicePixelRatio||1)>1.2?"@2x":"";return cartoOk?"https://basemaps.cartocdn.com/rastertiles/"+st+"/"+z+"/"+x+"/"+y+r+".png?key="+CARTO_KEY:"https://"+"abcd"[(x+y)&3]+".basemaps.cartocdn.com/"+st+"/"+z+"/"+x+"/"+y+r+".png"};
const TL={sat:{url:(z,x,y)=>"https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2024_3857/default/g/"+z+"/"+y+"/"+x+".jpg",T:256,zmax:15,cache:new Map(),max:400,nocors:true},
 osm:{url:(z,x,y)=>"https://tile.openstreetmap.org/"+z+"/"+x+"/"+y+".png",T:256,zmax:19,cache:new Map(),max:400},
 voyager:{url:(z,x,y)=>cartoUrl("voyager",z,x,y),T:256,zmax:20,cache:new Map(),max:400},
 light:{url:(z,x,y)=>cartoUrl("light_all",z,x,y),T:256,zmax:20,cache:new Map(),max:400},
 lightnl:{url:(z,x,y)=>cartoUrl("light_nolabels",z,x,y),T:256,zmax:20,cache:new Map(),max:400},
 dark:{url:(z,x,y)=>cartoUrl("dark_all",z,x,y),T:256,zmax:20,cache:new Map(),max:400},
 hs:{url:(z,x,y)=>"https://tiles.mapterhorn.com/"+z+"/"+x+"/"+y+".webp",T:512,zmax:12,cache:new Map(),max:160}};
const tlon=(x,z)=>x/2**z*360-180,tlat=(y,z)=>{const n=Math.PI-2*Math.PI*y/2**z;return 180/Math.PI*Math.atan(Math.sinh(n))};
const tx=(lon,z)=>(lon+180)/360*2**z,ty=(lat,z)=>{const r=Math.max(-85.05,Math.min(85.05,lat))*Math.PI/180;return(1-Math.log(Math.tan(r)+1/Math.cos(r))/Math.PI)/2*2**z};
const isDark=()=>{const c=css("--ink").replace("#","");return c.length>=6&&parseInt(c.slice(0,2),16)>140};
function hillshade(img,z,y){const T=img.width,c=document.createElement("canvas");c.width=T;c.height=T;const g=c.getContext("2d",{willReadFrequently:true});g.drawImage(img,0,0);
 const d=g.getImageData(0,0,T,T).data,o=g.createImageData(T,T),od=o.data,el=new Float32Array(T*T);
 for(let i=0;i<T*T;i++)el[i]=d[4*i]*256+d[4*i+1]+d[4*i+2]/256-32768;
 const lat=tlat(y+.5,z),m=40075016.7*Math.cos(lat*Math.PI/180)/(T*2**z),ex=Math.max(1,Math.min(8,2**((10-z)/2.5))); // metres per pixel, exaggeration at small scales
 const az=315*Math.PI/180,alt=45*Math.PI/180,lx=Math.sin(az)*Math.cos(alt),ly=Math.cos(az)*Math.cos(alt),lz=Math.sin(alt);
 for(let r=0;r<T;r++)for(let q=0;q<T;q++){const i=r*T+q,e=el[i];if(e<=0.5){od[4*i+3]=0;continue}
  const ex1=el[r*T+Math.min(T-1,q+1)],ex0=el[r*T+Math.max(0,q-1)],ey1=el[Math.min(T-1,r+1)*T+q],ey0=el[Math.max(0,r-1)*T+q];
  const dzdx=(ex1-ex0)/(2*m)*ex,dzdy=(ey0-ey1)/(2*m)*ex,n=Math.hypot(dzdx,dzdy,1),sh=(-dzdx*lx-dzdy*ly+lz)/n; // 1 = lit, 0 = in shadow
  const k=4*i;if(sh<lz){od[k]=od[k+1]=od[k+2]=20;od[k+3]=Math.min(200,(lz-sh)*330)}else{od[k]=od[k+1]=od[k+2]=255;od[k+3]=Math.min(110,(sh-lz)*260)}}
 g.putImageData(o,0,0);return c}
function tileGet(L,key,z,x,y){const C=TL[L].cache;let e=C.get(key);if(e){C.delete(key);C.set(key,e);return e.ok?e.v:null}
 e={ok:false,v:null};C.set(key,e);if(C.size>TL[L].max)C.delete(C.keys().next().value);
 const img=new Image();if(!TL[L].nocors)img.crossOrigin="anonymous";img.decoding="async";
 img.onload=()=>{try{e.v=L==="hs"?hillshade(img,z,y):img;e.ok=true}catch(err){e.fail=true}repaint()};img.onerror=()=>{e.fail=true};
 img.src=TL[L].url(z,x,y);return null}
function tilesDraw(L,alpha){const t=TL[L],W=W0,H=H0,dpr=devicePixelRatio||1,ppl=V.s*dpr; // device px per degree of longitude
 let z=Math.round(Math.log2(360*ppl/t.T)+.2);z=Math.max(0,Math.min(t.zmax,z));const n=2**z,v=viewBox();
 const x0=Math.floor(tx(Math.max(-180,v[0]),z)),x1=Math.floor(tx(Math.min(179.999,v[2]),z)),y0=Math.floor(ty(Math.min(85,v[3]),z)),y1=Math.floor(ty(Math.max(-85,v[1]),z));
 if((x1-x0+1)*(y1-y0+1)>120)return;cx.save();cx.globalAlpha=alpha;cx.imageSmoothingEnabled=true;if(L==="osm"&&isDark())cx.filter="invert(1) hue-rotate(180deg) brightness(.92) contrast(.88)";
 const strips=z<=5?16:z<=8?6:2;
 for(let ty_=Math.max(0,y0);ty_<=Math.min(n-1,y1);ty_++)for(let tx_=x0;tx_<=x1;tx_++){const xw=((tx_%n)+n)%n;
  // the tile itself, or the nearest loaded ancestor's matching sub-square while it loads
  let img=tileGet(L,z+"/"+xw+"/"+ty_,z,xw,ty_),sx=0,sy=0,sw=null;
  if(!img)for(let up=1;up<=4&&z-up>=0;up++){const k=2**up,e=t.cache.get((z-up)+"/"+(xw>>up)+"/"+(ty_>>up));if(e&&e.ok){img=e.v;const S_=img.width/k;sx=(xw%k)*S_;sy=(ty_%k)*S_;sw=S_;break}}
  if(!img)continue;const T=img.width,sz=sw||T;
  for(let s=0;s<strips;s++){const a=s/strips,b=(s+1)/strips,la=tlat(ty_+a,z),lb=tlat(ty_+b,z),[px0,py0]=P(tlon(tx_,z),la),[px1,py1]=P(tlon(tx_+1,z),lb);
   cx.drawImage(img,sx,sy+a*sz,sz,sz/strips,px0,py0,px1-px0+.6,py1-py0+.6)}}
 cx.restore()}
let BMV="simple";const BM=()=>BMV;
function bmSet(v){BMV=TL[v]||v==="simple"?v:"simple";try{localStorage.setItem("wm-basemap",BMV)}catch(e){}
 const opt=document.querySelector('.bmo[data-bm="'+BMV+'"]');$("bmcur").style.cssText=opt.querySelector(".bmt").style.cssText;$("bmcur").className="bmt"+(BMV==="simple"?" bm-simple":"");
 $("bmlab").textContent=opt.textContent;document.querySelectorAll(".bmo").forEach(b=>b.classList.toggle("on",b.dataset.bm===BMV));attrib();repaint()}
function attrib(){const a=[];if(BM()==="sat")a.push("<a href='https://s2maps.eu' target='_blank' rel='noopener'>Sentinel-2 cloudless 2024</a> by EOX IT Services GmbH (modified Copernicus Sentinel data)");if(["voyager","light","lightnl","dark"].includes(BM()))a.push("© <a href='https://www.openstreetmap.org/copyright' target='_blank' rel='noopener'>OpenStreetMap</a> contributors © <a href='https://carto.com/attributions' target='_blank' rel='noopener'>CARTO</a>");if(BM()==="osm")a.push("© <a href='https://www.openstreetmap.org/copyright' target='_blank' rel='noopener'>OpenStreetMap</a> contributors");
 if($("HS").checked)a.push("<a href='https://mapterhorn.com/attribution' target='_blank' rel='noopener'>© Mapterhorn</a>");$("attr").innerHTML=a.join(" · ");$("attr").style.display=a.length?"block":"none"}
