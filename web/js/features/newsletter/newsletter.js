/* Newsletter tab: the daily draft (data/newsletter/*.md), local edits and ratings, feedback as a GitHub issue.
   ES module (spec 3 step 2): imports name what this file needs from other modules, the export list at the end what it offers. */
import { S } from "../../core/data.js";
import { $ } from "../../core/util.js";
import { dbJson } from "../../core/load.js";
import { registerTab } from "../../core/router.js";
/* ---------- Newsletter tab: the daily draft (web/data/newsletter/*.md, built by scripts/build_newsletter_site.py), local edits and feedback.
   Edits and ratings live in this browser (localStorage); "Send to Claude" opens a prefilled GitHub issue labelled newsletter-feedback, which is
   where a later chat reads them (DEVNOTES: Newsletter tab). ---------- */
const NW={idx:null,err:0,busy:0,day:null,md:{},mode:"read"};
function nwLS(k,v){try{if(v===undefined)return localStorage.getItem(k);if(v===null)localStorage.removeItem(k);else localStorage.setItem(k,v)}catch(e){}return null}
const nwEsc=s=>s.replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
const nwInl=s=>nwEsc(s).replace(/\*\*(.+?)\*\*/g,"<b>$1</b>").replace(/(^|[\s(])_(.+?)_(?=[\s).,;:]|$)/g,"$1<i>$2</i>");
function nwBlocks(md){const out=[],L=md.split("\n");let i=0;while(i<L.length){const l=L[i];if(!l.trim()){i++;continue}
 if(l.startsWith("|")){const a=[];while(i<L.length&&L[i].startsWith("|"))a.push(L[i++]);out.push({t:"tb",raw:a.join("\n")});continue}
 if(l.startsWith("#")){out.push({t:"h",raw:l});i++;continue}
 const a=[];while(i<L.length&&L[i].trim()&&!L[i].startsWith("|")&&!L[i].startsWith("#"))a.push(L[i++]);out.push({t:"p",raw:a.join("\n")})}return out}
function nwTable(raw){const r=raw.split("\n").filter(x=>!/^\|[\s:|-]+\|?$/.test(x)).map(x=>x.replace(/^\||\|$/g,"").split("|").map(c=>c.trim()));if(!r.length)return"";
 return"<div class='dw'><table class='dt'><thead><tr>"+r[0].map((c,j)=>`<th style="text-align:${j?"right":"left"}">${nwEsc(c)}</th>`).join("")+"</tr></thead><tbody>"+r.slice(1).map(x=>"<tr>"+x.map((c,j)=>`<td style="text-align:${j?"right":"left"}">${nwEsc(c)}</td>`).join("")+"</tr>").join("")+"</tbody></table></div>"}
const nwKey=(k,d)=>"nws:"+k+":"+d;
const nwText=()=>{const e=nwLS(nwKey("edit",NW.day));return e==null?NW.md[NW.day]:e};
const nwFb=()=>{try{return JSON.parse(nwLS(nwKey("fb",NW.day))||"{}")}catch(e){return{}}};
const nwSave=j=>nwLS(nwKey("fb",NW.day),JSON.stringify(j));
function nwIssue(){const d=NW.day,pub=NW.md[d],cur=nwText(),fb=nwFb(),bl=nwBlocks(cur),src=(NW.idx.days.find(x=>x.day===d)||{}).source;
 let o=`Newsletter feedback for **${d}** (published as: ${src} draft)\n\n`;if(fb.note)o+=`## Overall\n${fb.note}\n\n`;
 const rows=Object.entries(fb.b||{}).filter(([k,v])=>v.r||v.c);
 if(rows.length){o+="## Per section\n";rows.forEach(([k,v])=>{const b=bl[k],ex=(b?b.raw:"").replace(/\s+/g," ").replace(/\*\*/g,"").slice(0,110);o+=`- ${v.r==="up"?"👍 keep / more like this":v.r==="down"?"👎 cut or weak":"•"} "${ex}"${v.c?" — "+v.c:""}\n`});o+="\n"}
 if(cur!==pub){const a=nwBlocks(pub).map(b=>b.raw),c=bl.map(b=>b.raw),A=new Set(a),C=new Set(c),q=x=>x.length?x.map(t=>"> "+t.replace(/\n/g,"\n> ")).join("\n\n"):"(none)";
  o+="## My edits to the draft\nRemoved:\n"+q(a.filter(x=>!C.has(x)))+"\n\nAdded:\n"+q(c.filter(x=>!A.has(x)))+"\n"}
 return o}
function nwsTab(){const el=$("nws");
 if(!NW.idx){if(NW.err){el.innerHTML="<div class='feednote'>No newsletter published yet. The deploy job builds the daily draft from the data store (DEVNOTES: Newsletter tab).</div>";return}
  el.innerHTML="<div class='feednote'>Loading…</div>";if(!NW.busy){NW.busy=1;dbJson("data/newsletter/index.json").then(j=>{NW.idx=j;NW.day=j.latest;NW.busy=0;if(S.tab==="nws")nwsTab()}).catch(()=>{NW.err=1;NW.busy=0;if(S.tab==="nws")nwsTab()})}return}
 const d=NW.day;if(NW.md[d]==null){el.innerHTML="<div class='feednote'>Loading…</div>";if(!NW.busy){NW.busy=1;fetch("data/newsletter/"+d+".md").then(r=>{if(!r.ok)throw 0;return r.text()}).then(t=>{NW.md[d]=t;NW.busy=0;if(S.tab==="nws")nwsTab()}).catch(()=>{NW.md[d]="# No draft for this day\n";NW.busy=0;if(S.tab==="nws")nwsTab()})}return}
 const cur=nwText(),edited=cur!==NW.md[d],fb=nwFb(),src=(NW.idx.days.find(x=>x.day===d)||{}).source;
 const nr=Object.values(fb.b||{}).filter(v=>v.r).length,nc=Object.values(fb.b||{}).filter(v=>v.c).length+(fb.note?1:0);
 let h=`<div class='row'><label style="display:flex;gap:6px;align-items:center;font-size:13px">Day <select id="nwday">${NW.idx.days.map(x=>`<option value="${x.day}"${x.day===d?" selected":""}>${x.day}</option>`).join("")}</select></label>
  <span class='badge'>${src==="editorial"?"edited draft":"auto draft"}</span>${edited?"<span class='badge' style='color:var(--uc)'>your edits (this browser)</span>":""}
  <span class='seg'><button data-m="read" class="${NW.mode==="read"?"on":""}">Read &amp; rate</button><button data-m="edit" class="${NW.mode==="edit"?"on":""}">Edit text</button></span></div>`;
 if(NW.mode==="edit"){h+=`<textarea id="nwta" rows="26" spellcheck="true">${nwEsc(cur)}</textarea><div class='hint'>Markdown. Your changes are kept in this browser and go to Claude with "Send feedback" (only the changed sections).</div>
  <div class='btns row'><button data-a="reset">Reset to published text</button></div>`}
 else{const bl=nwBlocks(cur);h+=bl.map((b,i)=>{const x=(fb.b||{})[i]||{};const body=b.t==="h"?`<h3>${nwInl(b.raw.replace(/^#+\s*/,""))}</h3>`:b.t==="tb"?nwTable(b.raw):`<div>${nwInl(b.raw).replace(/\n/g,"<br>")}</div>`;
   return`<div class="nb ${x.r||""}">${body}<div class="nf${x.r||x.c?" set":""}"><button data-nb="${i}" data-a="up" class="${x.r==="up"?"on":""}" title="Keep / more like this">👍</button><button data-nb="${i}" data-a="down" class="${x.r==="down"?"on":""}" title="Cut or weak">👎</button><button data-nb="${i}" data-a="c" class="${x.c?"on":""}" title="Comment">💬</button></div>${x.open||x.c?`<div class="nc"><textarea class="nwc" data-nb="${i}" placeholder="What should change here?">${nwEsc(x.c||"")}</textarea></div>`:""}</div>`}).join("")}
 h+=`<h2 style="margin:10px 0 0">Feedback to Claude</h2><textarea id="nwnote" rows="3" placeholder="Overall: what worked, what is missing, what to cut, which signals matter most…">${nwEsc(fb.note||"")}</textarea>
  <div class='btns row'><button class="pri" data-a="send">Send feedback (opens a GitHub issue)</button><button data-a="copy">Copy as text</button><button data-a="dl">Download current draft (.md)</button><span class='hint' id="nwst">${nr} rated, ${nc} comments${edited?", edited text":""}</span></div>
  <div class='hint'>Ratings, comments and edits stay in this browser until you send them. Sending opens a prefilled issue (label newsletter-feedback) in the project repo; submit it there and a later chat reads it and updates the format (newsletter/STYLE.md).</div>`;
 el.innerHTML=h}
$("nws").addEventListener("click",e=>{const b=e.target.closest("button");if(!b)return;const d=NW.day;
 if(b.dataset.m){NW.mode=b.dataset.m;nwsTab();return}
 if(b.dataset.nb!=null){const fb=nwFb();fb.b=fb.b||{};const x=fb.b[b.dataset.nb]=fb.b[b.dataset.nb]||{};if(b.dataset.a==="c")x.open=!x.open;else x.r=x.r===b.dataset.a?"":b.dataset.a;nwSave(fb);nwsTab();return}
 const a=b.dataset.a,st=$("nwst");
 if(a==="reset"){nwLS(nwKey("edit",d),null);nwsTab()}
 else if(a==="send"){const body=nwIssue(),enc=encodeURIComponent,base=`https://github.com/${NW.idx.repo}/issues/new?labels=newsletter-feedback&title=${enc("Newsletter feedback "+d)}&body=`;let url=base+enc(body);
  if(url.length>7000){try{navigator.clipboard.writeText(body)}catch(e){}url=base+enc("Too long for a link: the feedback text was copied to your clipboard. Paste it here (Ctrl+V).")}
  window.open(url,"_blank","noopener")}
 else if(a==="copy"){navigator.clipboard.writeText(nwIssue()).then(()=>{if(st)st.textContent="Copied."}).catch(()=>{if(st)st.textContent="Copy failed: select the text yourself."})}
 else if(a==="dl"){const u=URL.createObjectURL(new Blob([nwText()],{type:"text/markdown"})),l=document.createElement("a");l.href=u;l.download="radialeconomics-"+d+".md";l.click();setTimeout(()=>URL.revokeObjectURL(u),2000)}});
$("nws").addEventListener("input",e=>{const t=e.target;
 if(t.id==="nwta"){if(t.value===NW.md[NW.day])nwLS(nwKey("edit",NW.day),null);else nwLS(nwKey("edit",NW.day),t.value)}
 else if(t.id==="nwnote"){const fb=nwFb();fb.note=t.value;nwSave(fb)}
 else if(t.classList.contains("nwc")){const fb=nwFb();fb.b=fb.b||{};const x=fb.b[t.dataset.nb]=fb.b[t.dataset.nb]||{};x.c=t.value;x.open=true;nwSave(fb)}});
$("nws").addEventListener("change",e=>{if(e.target.id==="nwday"){NW.day=e.target.value;nwsTab()}});
registerTab("nws",{el:"nws",render:nwsTab});
