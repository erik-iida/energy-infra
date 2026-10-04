/* Bathymetry underlay: EMODnet depth grid (data/bathy.png) coloured in the browser, WMS contours when zoomed in.
   Spec 3 step 2, push 3: moved from the former single page script unchanged; classic script, shared global scope. */
// Bathymetry underlay: EMODnet Bathymetry WMS (EPSG:4326 maps linearly onto this projection), requested for the
// visible area after panning/zooming settles; depth contours added when zoomed in.
const BATHY_URL="https://ows.emodnet-bathymetry.eu/wms";let bathyT=0;S.bathy=null;S.bathyKey="";
// Depth grid pre-fetched from EMODnet (scripts/fetch_bathymetry.py) and coloured here, so the scale can change.
const BRAMP=[[232,243,249],[190,222,238],[134,189,220],[78,146,196],[39,99,160],[24,61,112]];
const BG={meta:null,v:null,cv:null,max:60,fail:false};
function bdec(v){return v<=200?v:200+(v-200)*100}
function bcol(t){t=Math.max(0,Math.min(1,t))*(BRAMP.length-1);const i=Math.min(BRAMP.length-2,Math.floor(t)),f=t-i,a=BRAMP[i],b=BRAMP[i+1];return[0,1,2].map(k=>Math.round(a[k]+(b[k]-a[k])*f))}
async function bathyLoad(){if(BG.meta||BG.fail)return;BG.fail=true;
 try{const m=await(await fetch("data/bathy.json",{cache:"no-cache"})).json(),bl=await(await fetch("data/bathy.png")).blob();
  const bm=await createImageBitmap(bl,{colorSpaceConversion:"none",premultiplyAlpha:"none"}),c=document.createElement("canvas");c.width=m.w;c.height=m.h;
  const g=c.getContext("2d",{willReadFrequently:true});g.drawImage(bm,0,0);const d=g.getImageData(0,0,m.w,m.h).data,v=new Uint8Array(m.w*m.h);for(let i=0;i<v.length;i++)v[i]=d[4*i];
  BG.meta=m;BG.v=v;BG.cv=c;BG.fail=false;bathyColour();S.bathyKey="";repaint()}catch(e){console.info("no depth grid yet, using EMODnet WMS colours",e);S.bathyKey="";repaint()}}
// the depth grid covers European seas only: show it when the view is centred on it, with faded edges
function bathyHere(){const b=BG.meta.bbox,[l0]=Pinv(0,0),[l1]=Pinv(W0,H0);return l1-l0<80&&V.lon>b[0]&&V.lon<b[2]&&V.lat>b[1]&&V.lat<b[3]}
function bathyColour(){BG.max=+$("BD").value;$("BDv").textContent="0–"+BG.max+" m";
 const lut=new Uint8ClampedArray(256*4);for(let v=0;v<255;v++){const c=bcol(bdec(v)/BG.max);lut.set([c[0],c[1],c[2],255],4*v)}
 $("blegc").style.background="linear-gradient(90deg,"+BRAMP.map(c=>"rgb("+c.join(",")+")").join(",")+")";$("blegt").textContent="0 – ≥"+BG.max+" m";
 if(!BG.v)return;const m=BG.meta,g=BG.cv.getContext("2d"),im=g.createImageData(m.w,m.h),o=im.data,v=BG.v;
 const fw=Math.round(m.w*.04),fh=Math.round(m.h*.05);
 for(let y=0,i=0;y<m.h;y++){const ey=Math.min(1,Math.min(y,m.h-1-y)/fh);for(let x=0;x<m.w;x++,i++){const k=4*v[i],e=Math.min(ey,Math.min(1,Math.min(x,m.w-1-x)/fw));o[4*i]=lut[k];o[4*i+1]=lut[k+1];o[4*i+2]=lut[k+2];o[4*i+3]=lut[k+3]*e}}g.putImageData(im,0,0)}
function bathyWant(W,H){if(!$("BY").checked)return;bathyLoad();if(BG.meta&&!bathyHere()){S.bathy=null;S.bathyKey="";return}const[l0,a1]=Pinv(0,0),[l1,a0]=Pinv(W,H),ct=false,grid=!!BG.meta;  // no depth contours
 if(grid&&!ct){S.bathy=null;S.bathyKey="";return}  // grid alone; WMS only for contours when zoomed in
 const key=[l0,a0,l1,a1].map(v=>v.toFixed(3)).join(",")+ct+grid;if(S.bathyKey===key)return;S.bathyKey=key;clearTimeout(bathyT);
 bathyT=setTimeout(()=>{const mx=(l1-l0)*.15,my=(a1-a0)*.15,b=[l0-mx,Math.max(-85,a0-my),l1+mx,Math.min(85,a1+my)],sc=Math.min(1,2048/(1.3*Math.max(W,H)));
  const w=Math.round(W*1.3*sc),h=Math.round(H*1.3*sc),img=new Image();img.onload=()=>{S.bathy={img,b,lines:grid};repaint()};
  img.src=BATHY_URL+"?service=WMS&version=1.1.1&request=GetMap&layers="+(grid?"emodnet:contours":ct?"emodnet:mean,emodnet:contours":"emodnet:mean")+"&styles=&srs=EPSG:4326&bbox="+b.map(v=>v.toFixed(5)).join(",")+"&width="+w+"&height="+h+"&format=image/png&transparent=true"},350)}
// depth images are plain lat/lon grids: draw them in latitude strips so they sit right on the Mercator map
function drawLatLonImg(img,b){const n=48,H=img.height,W=img.width;for(let k=0;k<n;k++){const la=b[3]-(b[3]-b[1])*k/n,lb=b[3]-(b[3]-b[1])*(k+1)/n,[x0,y0]=P(b[0],la),[x1,y1]=P(b[2],lb);
 cx.drawImage(img,0,H*k/n,W,H/n,x0,y0,x1-x0,y1-y0+.6)}}
function bathyDraw(){if(!$("BY").checked)return;const al=(+css("--bathy-a")||.75)*(BM()==="simple"?1:BM()==="sat"?.45:.55);cx.imageSmoothingEnabled=true;
 if(BG.meta&&bathyHere()){const b=BG.meta.bbox,[x0,y0]=P(b[0],b[3]),[x1,y1]=P(b[2],b[1]);cx.globalAlpha=al;drawLatLonImg(BG.cv,b)}
 const B=S.bathy;if(B){const[x0,y0]=P(B.b[0],B.b[3]),[x1,y1]=P(B.b[2],B.b[1]);cx.globalAlpha=B.lines?.8:al;drawLatLonImg(B.img,B.b)}cx.globalAlpha=1}
