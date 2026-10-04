/* Small shared helpers: $ (element by id), css variables, MW / GW formatting.
   ES module (spec 3 step 2): imports name what this file needs from other modules, the export list at the end what it offers. */
const $=id=>document.getElementById(id);
const css=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const fmt=mw=>mw==null?"–":mw>=10000?(mw/1000).toFixed(1)+" GW":Math.round(mw).toLocaleString()+" MW";
const fg=mw=>mw==null?"–":mw>=1000?(mw/1000).toFixed(2)+" GW":Math.round(mw)+" MW";
const eur=v=>v==null||!isFinite(v)?"–":(Math.abs(v)>=1e6?(v/1e6).toFixed(2)+" M€":Math.abs(v)>=1e4?Math.round(v/1e3)+" k€":Math.round(v).toLocaleString()+" €");
const pm=v=>v==null||!isFinite(v)?"–":v.toFixed(1)+" €/MWh";

export { $, css, eur, fg, fmt, pm };
