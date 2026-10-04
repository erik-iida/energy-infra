/* Tab switching: tab(t) shows one tab's pane, keeps the URL hash for deep links and the body[data-tab] attribute.
   ES module (spec 3 step 2): imports name what this file needs from other modules, the export list at the end what it offers. */
import { S } from "./data.js";
import { $ } from "./util.js";
import { draw } from "../features/map/view.js";
import { csSync } from "./flags.js";
function tab(t){if(t!=="flg"&&/^#flags/.test(location.hash)){try{history.replaceState(null,"",location.pathname+location.search)}catch(e){}}if(t==="sys"&&!S.c){S.c="Europe";csSync()}S.tab=t;document.body.dataset.tab=t;if(t!=="map")S.farm=null;document.querySelectorAll("#tabs button").forEach(b=>b.classList.toggle("on",b.dataset.t===t));
 $("stage").style.display=t==="map"?"block":"none";$("dash").style.display=t==="cmp"?"flex":"none";$("mkt").style.display=t==="mkt"?"flex":"none";$("sys").style.display=t==="sys"?"flex":"none";$("flg").style.display=t==="flg"?"flex":"none";$("nws").style.display=t==="nws"?"flex":"none";$("dat").style.display=t==="dat"?"flex":"none";draw()}

export { tab };
