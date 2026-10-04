/* Tabs and navigation. Each tab registers itself here (registerTab) and the map registers its paint / side-pane / fly-to
   functions (registerMap), so this file knows no feature by name: tab(t) shows one pane, draw() renders the current
   tab, go(country, farm) changes the selection everywhere. The URL hash of the Flags deep links is kept here too.
   ES module (spec 3 step 2): imports name what this file needs from other modules, the export list at the end what it offers. */
import { S } from "./data.js";
import { $ } from "./util.js";
import { csSync } from "./flags.js";
const TABS={};                                  // tab id -> {el: pane element id, render(): draw the tab's content}
const MAP={paint(){},pane(){},goto(){}};        // set by the map feature: paint the canvas, fill the side pane, fly to a selection
function registerTab(id,api){TABS[id]=api}
function registerMap(api){Object.assign(MAP,api)}
function tab(t){if(t!=="flg"&&/^#flags/.test(location.hash)){try{history.replaceState(null,"",location.pathname+location.search)}catch(e){}}if(t==="sys"&&!S.c){S.c="Europe";csSync()}S.tab=t;document.body.dataset.tab=t;if(t!=="map")S.farm=null;document.querySelectorAll("#tabs button").forEach(b=>b.classList.toggle("on",b.dataset.t===t));
 $("stage").style.display=t==="map"?"block":"none";for(const id in TABS)$(TABS[id].el).style.display=t===id?"flex":"none";draw()}
function draw(){csSync();const T=TABS[S.tab];if(T){T.render();MAP.pane();return}MAP.paint();MAP.pane()}
function go(c,farm){S.c=c;S.farm=farm;S.hover=-1;S.zh=-1;$("tip").style.display="none";if(S.tab==="map"){MAP.goto(c,farm);MAP.pane()}else draw()}

export { draw, go, registerMap, registerTab, tab };
