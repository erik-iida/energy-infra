/* Data loading: fetch a JSON file relative to the page (data/...).
   ES module (spec 3 step 2): imports name what this file needs from other modules, the export list at the end what it offers. */
function dbJson(u){return fetch(u).then(r=>{if(!r.ok)throw new Error(r.status);return r.json()})}

export { dbJson };
