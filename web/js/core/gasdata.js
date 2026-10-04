/* Gas data (ENTSOG, data/gas.json): loaded once on demand, shared by the map's gas layer and the System tab's gas-supply card.
   ES module (spec 3 step 2): imports name what this file needs from other modules, the export list at the end what it offers. */
import { draw } from "./router.js";
const GAS={d:null,loading:false,pts:[]};window.GAS=GAS;
const GCN={DE:"Germany",DK:"Denmark",NL:"Netherlands",BE:"Belgium",FR:"France",PL:"Poland",AT:"Austria",CZ:"Czechia",SK:"Slovakia",HU:"Hungary",IT:"Italy",ES:"Spain",PT:"Portugal",
 SI:"Slovenia",HR:"Croatia",RO:"Romania",BG:"Bulgaria",GR:"Greece",LT:"Lithuania",LV:"Latvia",EE:"Estonia",FI:"Finland",SE:"Sweden",IE:"Ireland",UK:"United Kingdom",LU:"Luxembourg",
 CH:"Switzerland",AL:"Albania (TAP)",UA:"Ukraine",TR:"Türkiye",RS:"Serbia",MD:"Moldova",MK:"North Macedonia",NO:"Norway"};
const gname=c=>GCN[c]||c;
function gasLoad(){if(GAS.d||GAS.loading)return;GAS.loading=true;fetch("data/gas.json",{cache:"no-cache"}).then(r=>r.ok?r.json():null).then(j=>{if(j){GAS.d=j;draw()}}).catch(()=>{})}

export { GAS, gasLoad, gname };
