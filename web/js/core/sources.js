/* Sources and notes: every tab's source / disclaimer notes fold into one collapsed block at the end of the tab.
   Spec 3 step 2, push 3: moved from the former single page script unchanged; classic script, shared global scope. */
/* ---------- Sources and notes: every tab's source / disclaimer notes (.srcnote) move into one collapsed block at its end ---------- */
const SRCOPEN={};
function foldSrc(el){const ns=[...el.querySelectorAll(":scope > .srcnote, :scope > div > .srcnote")].filter(n=>!n.closest(".srcd"));if(!ns.length)return;
 let d=el.querySelector(":scope > details.srcd");if(!d){d=document.createElement("details");d.className="srcd";d.innerHTML="<summary>Sources and notes</summary><div class='srcb'></div>";
  d.open=!!SRCOPEN[el.id];d.addEventListener("toggle",()=>{SRCOPEN[el.id]=d.open})}
 const b=d.querySelector(".srcb");ns.forEach(n=>b.appendChild(n));el.appendChild(d)}
["dash","mkt","sys","flg","dat"].forEach(id=>{const el=$(id);if(!el)return;foldSrc(el);
 new MutationObserver(()=>{const last=el.lastElementChild;if(el.querySelector(":scope > .srcnote, :scope > div > .srcnote")||(last&&!last.classList.contains("srcd")&&el.querySelector(":scope > details.srcd")))foldSrc(el)}).observe(el,{childList:true})});
