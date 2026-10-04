/* In-browser wake models (Jensen, Bastankhah, TurbOPark) and turbine power / thrust curves; must match pipeline/wake.py (tests/test_wake_parity.py).
   ES module (spec 3 step 2): imports name what this file needs from other modules, the export list at the end what it offers. */
import { TY } from "./data.js";
const URG=11.5,PC=(u,R,ur)=>u<3||u>25?0:R*Math.min(1,u/(ur||URG))**3;
const CT=(u,ur)=>u<3||u>25?.05:u<=ur?.8:Math.max(.05,.8*Math.pow(ur/u,3));
/* ---------- in-browser wake models (map heatmap + what-if) ---------- */
// In-browser copies of the PyWake models (same formulas and defaults as pipeline/wake.py)
// Jensen_1983:  NOJDeficit, k=0.04, ct2a_madsen, area-overlap rotor average, squared sum on free stream
// Bastankhah_PorteAgel_2014: k=0.0324555, ceps=0.2, ctlim=0.899, ct2a_mom1d, centre point,
//                            linear sum scaled by the source turbine's effective wind speed
// Nygaard_2022 (TurbOPark): TurboGaussianDeficit A=0.04, cTI=[1.5,0.8], ceps=0.25, ctlim=0.96, ct2a_mom1d, ambient TI,
//   Gaussian rotor-overlap average, mirror ground model, squared sum on the free stream (agrees with PyWake within ~0.2 % in wind speed)
const K_DEF={j:.04,g:.0324555,t:.04};
const ct2aMadsen=ct=>((0.0883*ct+0.0586)*ct+0.246)*ct;
const ct2aMom=ct=>.5*(1-Math.sqrt(1-Math.min(1,ct)));
function ovl(R,rw,c){c=Math.abs(c);if(c>=R+rw)return 0;if(c+R<=rw)return 1;if(c+rw<=R)return rw*rw/(R*R);
 const a=Math.acos((c*c+R*R-rw*rw)/(2*c*R)),b=Math.acos((c*c+rw*rw-R*R)/(2*c*rw));
 return(R*R*a+rw*rw*b-.5*Math.sqrt(Math.max(0,(-c+R+rw)*(c+R-rw)*(c-R+rw)*(c+R+rw))))/(Math.PI*R*R)}
// deficit factor at (px,py) from source j. Jensen: fraction of free stream. Gaussian: fraction of source effective ws.
// R>0 = rotor radius of the receiving turbine (area overlap for Jensen); R=0 = single point (flow map)
function wd(m,k,j,D,ct,px,py,dx,dy,R){const s=(px-j[0])*dx+(py-j[1])*dy;if(s<=0||m==="n")return 0;const c=-(px-j[0])*dy+(py-j[1])*dx;
 if(m==="t")return tpDef(k,D,ct,s,c,R);
 if(m==="j"){const rw=D/2+k*s,f=R?ovl(R,rw,c):(Math.abs(c)<rw?1:0);return f*2*ct2aMadsen(ct)/((rw/(D/2))**2)}
 const q=Math.sqrt(1-Math.min(.899,ct)),eps=.2*Math.sqrt(.5*(1+q)/q),sg=k*s+eps*D;
 return Math.min(1,2*ct2aMom(ct*D*D/(8*sg*sg)))*Math.exp(-c*c/(2*sg*sg))}
// ---- TurbOPark (Nygaard 2022), same set-up as PyWake's Nygaard_2022 ----
const erf=x=>{const s=Math.sign(x);x=Math.abs(x);const t=1/(1+.3275911*x),y=1-(((((1.061405429*t-1.453152027)*t)+1.421413741)*t-.284496736)*t+.254829592)*t*Math.exp(-x*x);return s*y};
// mean of exp(-r^2 / 2 sg^2) over a rotor disc of radius R whose centre is offset (c across, dz vertically) from the wake centre; R=0: the point value
function gavg(c,dz,R,sg){if(Math.hypot(c,dz)-R>6*sg)return 0;if(!R)return Math.exp(-(c*c+dz*dz)/(2*sg*sg));const n=24,k=sg*Math.SQRT2,w=Math.PI/n;let a=0; // y = R sin(t): smooth integrand
 for(let i=0;i<n;i++){const t=-Math.PI/2+(i+.5)*w,y=R*Math.sin(t),h=R*Math.cos(t);a+=Math.exp(-((c+y)*(c+y))/(2*sg*sg))*sg*Math.sqrt(Math.PI/2)*(erf((dz+h)/k)-erf((dz-h)/k))*h*w}
 return a/(Math.PI*R*R)}
let WTI=.06,WHH=100; // ambient turbulence intensity and hub height of the farm being computed
function wakeFarm(f){WTI=f.on?.10:.06;WHH=f.h||100} // set them for farm f (onshore demo farms: TI 10 %)
function tpDef(A,D,ct,s,c,R){const I=WTI,al=1.5*I,be=.8*I/Math.sqrt(Math.max(ct,1e-20)),x=s/D,t1=Math.sqrt((al+be*x)**2+1),t2=Math.sqrt(1+al*al);
 const sg=(A*I/be*(t1-t2-Math.log((t1+1)*al/((t2+1)*(al+be*x)))))*D+.25*Math.sqrt(.5*(1+Math.sqrt(1-Math.min(.96,ct)))/Math.sqrt(1-Math.min(.96,ct)))*D;
 const d0=Math.min(1,2*(.5*(1-Math.sqrt(1-Math.min(1,ct*D*D/(8*sg*sg))))));
 const a=d0*gavg(c,0,R,sg),b=d0*gavg(c,2*WHH,R,sg);return Math.sqrt(a*a+b*b)} // with its ground mirror (squared sum)
function tinterp(xs,ys,x){const N=xs.length;if(!(x>=xs[0]&&x<=xs[N-1]))return 0;let lo=0,hi=N-1;while(hi-lo>1){const m=(lo+hi)>>1;if(xs[m]<=x)lo=m;else hi=m}const a=xs[lo],b=xs[hi];return b===a?ys[lo]:ys[lo]+(ys[hi]-ys[lo])*(x-a)/(b-a)}
function run(f,m,U,dir,k){const t=dir*Math.PI/180,dx=-Math.sin(t),dy=-Math.cos(t);wakeFarm(f);
 if(!f.lay){const free=PC(U,f.cap,URG);return{P:[],u:[],ct:[],pw:free*(m==="n"?1:.9),free,dx,dy,U,Dt:[]}}
 const n=f.xy.length/2,P=[];for(let i=0;i<n;i++)P.push([f.xy[2*i],f.xy[2*i+1]]);
 const ord=P.map((p,i)=>i).sort((a,b)=>(P[a][0]*dx+P[a][1]*dy)-(P[b][0]*dx+P[b][1]*dy));
 const T=i=>f.tix?TY[f.tix[i]]:null,Dt=P.map((_,i)=>T(i)?T(i).D:f.D);
 const pwr=(i,v)=>T(i)?tinterp(T(i).ws,T(i).p,v):PC(v,f.mw,f.ur),ctf=(i,v)=>T(i)?tinterp(T(i).ws,T(i).ct,v):CT(v,f.ur);
 const u=new Array(n),ct=new Array(n),done=[];
 for(const i of ord){let q=0;
  if(m==="j"||m==="t"){for(const j of done){const d=wd(m,k,P[j],Dt[j],ct[j],P[i][0],P[i][1],dx,dy,Dt[i]/2);q+=d*d}u[i]=U*(1-Math.sqrt(q))}
  else if(m==="g"){for(const j of done)q+=u[j]*wd(m,k,P[j],Dt[j],ct[j],P[i][0],P[i][1],dx,dy,0);u[i]=Math.max(0,U-q)}
  else u[i]=U;
  ct[i]=ctf(i,u[i]);done.push(i)}
 let pw=0,free=0;for(let i=0;i<n;i++){pw+=pwr(i,u[i]);free+=pwr(i,U)}return{P,u,ct,pw,free,dx,dy,U,Dt}}
function spacingOf(f){if(f.sp&&f.sp.min!=null)return f.sp;const n=f.xy.length/2;if(n<2)return null;const Dt=[...Array(n)].map((_,i)=>f.tix?TY[f.tix[i]].D:f.D),nn=[];
 for(let i=0;i<n;i++){let b=1e18;for(let j=0;j<n;j++)if(j!==i){const d=(f.xy[2*i]-f.xy[2*j])**2+(f.xy[2*i+1]-f.xy[2*j+1])**2;if(d<b)b=d}nn.push(Math.sqrt(b)/Dt[i])}
 return f.sp={min:Math.min(...nn),mean:nn.reduce((a,b)=>a+b,0)/n,max:Math.max(...nn)}}

export { K_DEF, run, spacingOf, wakeFarm, wd };
