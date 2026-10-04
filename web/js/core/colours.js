/* Colour ramps shared by the Market heatmap and the map's zone colours: warm ramp for prices >= 0, cool ramp for negative prices, linear interpolation.
   ES module (spec 3 step 2): imports name what this file needs from other modules, the export list at the end what it offers. */
const HMPOS=[[253,238,220],[250,201,148],[240,145,82],[214,88,38],[160,48,20],[96,24,12]],HMNEG=[[214,232,250],[42,120,214]];
const lerpC=(R,t)=>{t=Math.max(0,Math.min(1,t))*(R.length-1);const i=Math.min(R.length-2,Math.floor(t)),f=t-i;return"rgb("+[0,1,2].map(k=>Math.round(R[i][k]+(R[i+1][k]-R[i][k])*f)).join(",")+")"};

export { HMNEG, HMPOS, lerpC };
