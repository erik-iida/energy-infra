/* Sortable tables: click a header to sort (unit-aware number parsing), and keepScroll() to re-render a tab without losing the scroll position.
   ES module (spec 3 step 2): imports name what this file needs from other modules, the export list at the end what it offers. */
import { S } from "./data.js";
function keepScroll(fn){const y=window.scrollY,els=[...document.querySelectorAll("#mkt,#main,main,.wrap")].map(e=>[e,e.scrollTop]);fn();els.forEach(([e,t])=>e.scrollTop=t);window.scrollTo(0,y)}
const UNIT={kW:1e-3,MW:1,GW:1e3,TW:1e6,kWh:1e-6,MWh:1e-3,GWh:1,TWh:1e3,"k€":1e3,"M€":1e6};
function cellNum(c){if(!c)return null;let v=c.dataset.v!=null?c.dataset.v:c.textContent.trim();if(v===""||v==="–"||v==="n/a")return null;
 const m=String(v).replace(/,/g,"").replace(/−/g,"-").match(/(-?\d+(?:\.\d+)?)\s*(kWh|MWh|GWh|TWh|kW|MW|GW|TW|k€|M€)?/);if(!m)return null;return parseFloat(m[1])*(UNIT[m[2]]||1)}
function colIsText(t,col){const th=t.tHead.rows[0].cells[col];if(th&&th.dataset.t==="txt")return true;const cs=[...t.tBodies[0].rows].map(r=>r.cells[col]).filter(c=>c&&c.textContent.trim()&&c.textContent.trim()!=="–");
 return cs.filter(c=>cellNum(c)!=null&&/^[\s\d.,−+\-]/.test(c.textContent.trim())).length<cs.length/2}
function sortTab(t,col,dir){const tb=t.tBodies[0];if(!tb||!t.tHead)return;const all=[...tb.rows],rows=all.filter(r=>!r.classList.contains("pin")),pin=all.filter(r=>r.classList.contains("pin"));
 const txt=colIsText(t,col),num=r=>cellNum(r.cells[col]);
 rows.sort((a,b)=>{if(txt)return dir*(a.cells[col]?a.cells[col].textContent.trim():"").localeCompare(b.cells[col]?b.cells[col].textContent.trim():"");const x=num(a),y=num(b);if(x==null&&y==null)return 0;if(x==null)return 1;if(y==null)return-1;return dir*(x-y)});
 rows.concat(pin).forEach(r=>tb.appendChild(r));[...t.tHead.rows[0].cells].forEach((th,i)=>th.dataset.s=i===col?(dir>0?"a":"d"):"")}
function makeSortable(root){if(!root)return;root.querySelectorAll("table").forEach(t=>{if(t.id==="ftab"||!t.tHead||!t.tBodies[0])return;t.classList.add("sortable");
 if(!t.id)t.id=root.id+":"+[...t.tHead.rows[0].cells].map(x=>x.textContent.trim()).join("|")});sortApply(root)}
function sortApply(root){(root||document).querySelectorAll("table.sortable[id]").forEach(t=>{const q=S.tsort[t.id];if(q)sortTab(t,q.col,q.dir)})}

export { colIsText, keepScroll, makeSortable, sortTab };
