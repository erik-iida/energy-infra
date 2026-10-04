/* Map paint: draws sea, land, layers, farms and legends onto the canvas in order.
   ES module (spec 3 step 2): imports name what this file needs from other modules, the export list at the end what it offers. */
import { DATA, F, S, Z } from "../../core/data.js";
import { $, css, fmt } from "../../core/util.js";
import { spacingOf } from "../../core/wake.js";
import { cur, curWind } from "../../core/feed.js";
import { LOD_TURB, LOD_WAKE, M, P, clampV, cx, landInView, pxm, seamCover, size, sl } from "./canvas.js";
import { BM, isDark, tilesDraw } from "./tiles.js";
import { gasDraw } from "./layers/gas.js";
import { gridDraw } from "./layers/grid.js";
import { icDraw } from "./layers/interconnection.js";
import { HID, coastPath, fcol, glyph, heat, heatLegend, scaleBar } from "./view.js";
import { bathyDraw, bathyWant } from "./layers/bathy.js";
import { moDraw } from "./layers/zones.js";
function paint(){if(S.tab!=="map")return;const[W,H]=size();clampV();S.heatShown=false;cx.fillStyle=css("--sea");cx.fillRect(0,0,W,H);S.pts=[];S.zp=[];S.fp=[];if(BM()!=="simple")tilesDraw(BM(),1);bathyWant(W,H);bathyDraw();
 // polygons -> Path2D, skipping vertices less than ~1 px from the last one drawn (big win at small scales)
const TILE=DATA.tile||0,onTile=v=>TILE>0&&Math.abs(v/TILE-Math.round(v/TILE))<1e-4;
const pth=fl=>{const p=new Path2D();for(const r of fl){let lx=1e9,ly=1e9;for(let i=0;i<r.length;i+=2){const[x,y]=P(r[i],r[i+1]);if(!i){p.moveTo(x,y);lx=x;ly=y}else if(Math.abs(x-lx)+Math.abs(y-ly)>1.2||i>=r.length-2||onTile(r[i])||onTile(r[i+1])){p.lineTo(x,y);lx=x;ly=y}}p.closePath()}return p};
 if(BM()==="simple"){cx.fillStyle=css("--land");cx.strokeStyle=css("--line");cx.lineWidth=1;const land=pth(landInView());cx.fill(land);seamCover();cx.stroke(coastPath())}if($("HS").checked)tilesDraw("hs",isDark()?.55:.8);moDraw();gridDraw();icDraw();gasDraw();
 const far=sl()<40,SC={uc:["--uc",[6,4]],cs:["--cs",[6,4]],pl:["--pl",[2,3]]};
 if($("Z").checked)Z.forEach((z,i)=>{if(HID.has(z.s))return;const p=pth(z.r),[col,d]=SC[z.s];S.zp.push([p,i]);cx.fillStyle=css(col);cx.globalAlpha=i===S.zh?.3:far?.07:.1;cx.fill(p);cx.globalAlpha=far?.7:1;cx.setLineDash(d);cx.strokeStyle=css(col);cx.lineWidth=i===S.zh?2.2:far?.8:1.3;cx.stroke(p);cx.setLineDash([]);cx.globalAlpha=1});
 const vis=[];F.forEach((f,i)=>{if(i!==S.farm&&HID.has(f.on?"on":"off"))return;const[x,y]=P(f.lon,f.lat),R=f.tex*pxm(),m=Math.max(f.ext*pxm(),20)+40;if(x>-m&&x<W+m&&y>-m&&y<H+m)vis.push([i,x,y,R])});
 vis.forEach(([i,,,R])=>{const f=F[i],p=pth(f.ol);S.fp.push([p,i]);if(f.lay&&R>=LOD_TURB)return;cx.fillStyle=fcol(f);cx.globalAlpha=.16;cx.fill(p);cx.globalAlpha=1;cx.strokeStyle=fcol(f);cx.lineWidth=i===S.farm||i===S.hover?2.4:1.1;cx.stroke(p)});
 const m=$("M").value,k=+$("K").value;
 if(m!=="n")vis.filter(v=>F[v[0]].lay&&(v[3]>=LOD_WAKE||(v[0]===S.farm&&v[3]>=LOD_TURB))).sort((a,b)=>b[3]-a[3]).slice(0,4).forEach(([i])=>heat(F[i],m,k));
 vis.forEach(([i,x,y,R])=>{const f=F[i],r=cur(f);
  if(f.lay&&R>=LOD_TURB){r.P.forEach((p,j)=>{const[a,b]=M(f,p[0],p[1]);cx.beginPath();cx.arc(a,b,Math.max(1.6,r.Dt[j]/2*pxm()),0,7);cx.fillStyle=css("--panel");cx.globalAlpha=.92;cx.fill();cx.globalAlpha=1;cx.strokeStyle=fcol(f);cx.lineWidth=1;cx.stroke()});
   if(R>=LOD_TURB*2){cx.font="600 12px sans-serif";cx.fillStyle=css("--ink");const t=f.n+" · "+fmt(r.pw),w=cx.measureText(t).width,[lx,ly]=M(f,0,f.tex);cx.fillText(t,Math.max(4,Math.min(W-w-4,lx-w/2)),Math.max(14,ly-8))}}
  else glyph(f,r,x,y,i)});
 const fs=S.farm!==null?F[S.farm]:null,near=fs||(sl()>800?vis.map(v=>F[v[0]]).sort((a,b)=>{const[ax,ay]=P(a.lon,a.lat),[bx,by]=P(b.lon,b.lat);return Math.hypot(ax-W/2,ay-H/2)-Math.hypot(bx-W/2,by-H/2)})[0]:null);
 if(near){const[U,D]=curWind(near),t=D*Math.PI/180,ax=40,ay=40;cx.strokeStyle=css("--ink");cx.fillStyle=css("--ink");cx.lineWidth=2;cx.beginPath();cx.moveTo(ax+Math.sin(t)*22,ay-Math.cos(t)*22);cx.lineTo(ax-Math.sin(t)*22,ay+Math.cos(t)*22);cx.stroke();
  cx.beginPath();cx.arc(ax-Math.sin(t)*22,ay+Math.cos(t)*22,4.5,0,7);cx.fill();cx.font="12px sans-serif";cx.fillText(U.toFixed(1)+" m/s from "+D+"°",14,ay+40);cx.fillStyle=css("--mut");cx.fillText(near.n.length>28?near.n.slice(0,27)+"…":near.n,14,ay+55)}
 if(fs&&fs.lay&&fs.tex*pxm()>=LOD_TURB){const sp=spacingOf(fs);if(sp){const l1="Spacing to nearest turbine",l2="min "+sp.min.toFixed(1)+" D · mean "+sp.mean.toFixed(1)+" D · max "+sp.max.toFixed(1)+" D";
  cx.font="12px sans-serif";const w=Math.max(cx.measureText(l1).width,cx.measureText(l2).width+20)+20;cx.fillStyle=css("--panel");cx.globalAlpha=.92;cx.fillRect(10,104,w,42);cx.globalAlpha=1;cx.strokeStyle=css("--line");cx.lineWidth=1;cx.strokeRect(10.5,104.5,w,42);
  cx.fillStyle=css("--mut");cx.fillText(l1,20,121);cx.fillStyle=css("--ink");cx.font="600 13px sans-serif";cx.fillText(l2,20,139)}}
 scaleBar(W,H);if(S.heatShown)heatLegend(W,H)}

export { paint };
