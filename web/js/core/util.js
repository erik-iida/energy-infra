/* Small shared helpers: $ (element by id), css variables, MW / GW formatting.
   Spec 3 step 2, push 3: moved from the former single page script unchanged; classic script, shared global scope. */
const $=id=>document.getElementById(id);
const css=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const fmt=mw=>mw==null?"–":mw>=10000?(mw/1000).toFixed(1)+" GW":Math.round(mw).toLocaleString()+" MW";
const fg=mw=>mw==null?"–":mw>=1000?(mw/1000).toFixed(2)+" GW":Math.round(mw)+" MW";
