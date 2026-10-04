/* Shared comparison line chart (many series, grey lines, flag + label at the line end, ranked hover): Market price chart and System comparisons.
   Spec 3 step 2, push 3: moved from the former single page script unchanged; classic script, shared global scope. */
const CMP={};
function niceRange(lo,hi){if(!(hi>lo)){hi=lo+1}const span=hi-lo,st=Math.pow(10,Math.floor(Math.log10(span/4))),m=[1,2,2.5,5,10].find(q=>span/(q*st)<=5)*st;return[Math.floor(lo/m)*m,Math.ceil(hi/m)*m,m]}
// spec: {series:[{id,label,flag,v:[...]}], a, b (index range), unit, fmt(v), tipT(k)}
function cmpRender(id){const C=CMP[id],sv=document.getElementById(id);if(!sv)return;const W=sv.clientWidth||600,H=C.H||260,L=46,R=C.right||70,T=10,B=24;
 sv.setAttribute("viewBox","0 0 "+W+" "+H);sv.style.height=H+"px";
 let lo=1e9,hi=-1e9;C.series.forEach(s=>{for(let k=C.a;k<=C.b;k++){const v=s.v[k];if(v!=null){lo=Math.min(lo,v);hi=Math.max(hi,v)}}});
 if(lo>hi){sv.innerHTML="<text class='tl' x='"+W/2+"' y='"+H/2+"' text-anchor='middle'>No data for this period yet</text>";return}
 if(C.zero&&lo>0)lo=0;const[y0,y1,step]=niceRange(lo,hi);C.y0=y0;C.y1=y1;
 const n=C.b-C.a,x=k=>L+(W-L-R)*(k-C.a)/Math.max(1,n),y=v=>T+(H-T-B)*(1-(v-y0)/(y1-y0));C.x=x;C.y=y;C.L=L;C.R=R;C.W=W;
 let s="";for(let g=y0;g<=y1+1e-9;g+=step){s+="<line class='ax' x1='"+L+"' x2='"+(W-R)+"' y1='"+y(g)+"' y2='"+y(g)+"' "+(Math.abs(g)<1e-9?"":"stroke-dasharray='2 3'")+"/><text class='tl' x='"+(L-6)+"' y='"+(y(g)+3)+"' text-anchor='end'>"+C.fmt(g)+"</text>"}
 for(let k=C.a;k<=C.b;k+=(C.xs||6))s+="<text class='tl' x='"+x(k)+"' y='"+(H-6)+"' text-anchor='middle'>"+(C.xl?C.xl(k):hl(k))+"</text>";
 const ord=C.series.map((se,i)=>i).sort((p,q)=>(p===C.hl||!!(C.sel&&C.sel.has(C.series[p].id)))-(q===C.hl||!!(C.sel&&C.sel.has(C.series[q].id))));
 ord.forEach(i=>{const se=C.series[i],on=i===C.hl||(C.hl==null&&C.sel&&C.sel.has(se.id));s+="<path d='"+pathOf(se.v,x,y,C.a,C.b)+"' fill='none' stroke='"+(se.col?se.col:on?"var(--acc)":"var(--mut)")+"' stroke-width='"+(on?2.6:se.col?2:1.4)+"' stroke-opacity='"+(on||C.hl==null?.9:.35)+"' stroke-linejoin='round'"+(se.dash?" stroke-dasharray='5 4'":"")+"/>"+(C.dots?se.v.map((q,k)=>q==null||k<C.a||k>C.b?"":"<circle r='2.4' cx='"+x(k).toFixed(1)+"' cy='"+y(q).toFixed(1)+"' fill='"+(se.col||"var(--mut)")+"' fill-opacity='"+(on||C.hl==null?.9:.35)+"'/>").join(""):"")});
 // flags at line ends, nudged apart vertically
 const ends=C.series.map((se,i)=>{let k=C.b;while(k>C.a&&se.v[k]==null)k--;return se.v[k]==null?null:{i,k,yy:y(se.v[k])}}).filter(Boolean).sort((p,q)=>p.yy-q.yy);
 for(let j=1;j<ends.length;j++)ends[j].yy=Math.max(ends[j].yy,ends[j-1].yy+15);const over=ends.length?ends[ends.length-1].yy-(H-B):0;if(over>0)ends.forEach(e=>e.yy-=over);
 ends.forEach(e=>{const se=C.series[e.i],xe=x(e.k)+10;s+="<line x1='"+x(e.k)+"' x2='"+(xe-7)+"' y1='"+y(se.v[e.k])+"' y2='"+e.yy+"' stroke='var(--line)'/>"+(se.flag?flagSVG(se.flag,xe,e.yy,6.5):"<circle cx='"+xe+"' cy='"+e.yy+"' r='4' fill='"+(se.col||"var(--mut)")+"'/>")+"<text x='"+(xe+9)+"' y='"+(e.yy+4)+"' font-size='11' fill='"+(e.i===C.hl?"var(--ink)":"var(--mut)")+"' font-weight='"+(e.i===C.hl?600:400)+"'>"+se.label+"</text>"});
 if(C.hk!=null)s+="<line class='xh' x1='"+x(C.hk)+"' x2='"+x(C.hk)+"' y1='"+T+"' y2='"+(H-B)+"'/>";
 // the line under the cursor: a dot at the hovered hour plus its flag and label
 if(C.hk!=null&&C.hl!=null){const se=C.series[C.hl],v=se&&se.v[C.hk];if(v!=null){const px=x(C.hk),py=y(v),lw=7*String(se.label).length+(se.flag?24:8),left=px+lw+14>W-R;
  const bx=left?px-10-lw:px+10;s+="<circle cx='"+px.toFixed(1)+"' cy='"+py.toFixed(1)+"' r='4' fill='var(--acc)' stroke='var(--panel)' stroke-width='1.5'/>"
   +"<rect x='"+bx.toFixed(1)+"' y='"+(py-20).toFixed(1)+"' width='"+lw+"' height='18' rx='4' fill='var(--panel)' stroke='var(--line)'/>"
   +(se.flag?flagSVG(se.flag,bx+11,py-11,6.5):"")+"<text x='"+(bx+(se.flag?22:5)).toFixed(1)+"' y='"+(py-7).toFixed(1)+"' font-size='11.5' font-weight='600' fill='var(--ink)'>"+se.label+"</text>"}}
 sv.innerHTML=s}
function cmpHover(e,sv){const C=CMP[sv.id];if(!C||!C.x)return;const r=sv.getBoundingClientRect(),px=(e.clientX-r.left)*C.W/r.width,py=(e.clientY-r.top)*C.W/r.width;
 const k=Math.max(C.a,Math.min(C.b,Math.round(C.a+(px-C.L)/(C.W-C.L-C.R)*(C.b-C.a))));let best=null,bd=1e9;
 C.series.forEach((se,i)=>{const v=se.v[k];if(v!=null){const d=Math.abs(C.y(v)-py);if(d<bd){bd=d;best=i}}});
 if(px>C.W-C.R){const lab=[...sv.querySelectorAll("text")].find(t=>{const b=t.getBBox();return py>=b.y-4&&py<=b.y+b.height+4&&px>=b.x-20});if(lab){const i=C.series.findIndex(se=>se.label===lab.textContent);if(i>=0)best=i}}
 if(best!==C.hl||k!==C.hk){C.hl=best;C.hk=k;cmpRender(sv.id)}
 const rows=C.series.map((se,i)=>[se,se.v[k],i]).filter(q=>q[1]!=null).sort((p,q)=>q[1]-p[1]);
 dtipH(e,"<div class='dth'>"+(C.tl?C.tl(k):dl(k))+"</div>"+rows.map(([se,v,i])=>"<div class='dtr"+(i===C.hl?" on":"")+"'>"+(se.flag?flagHTML(se.flag,6):"<i class='dtd' style='background:"+(se.col||"var(--mut)")+"'></i>")+"<span>"+se.label+"</span><b>"+C.fmt(v)+"</b></div>").join(""))}
// rich tooltip (flags, highlighted row); same box and placement as dtip
function dtipH(e,html){const d=$("dtip");d.style.display="block";d.innerHTML=html;const w=d.offsetWidth,hh=d.offsetHeight;d.style.left=(e.clientX+14+w>innerWidth-8?Math.max(8,e.clientX-14-w):e.clientX+14)+"px";d.style.top=Math.max(8,Math.min(e.clientY+14,innerHeight-hh-8))+"px"}
function cmpLeave(sv){const C=CMP[sv.id];if(C){C.hl=null;C.hk=null;cmpRender(sv.id)}$("dtip").style.display="none"}
