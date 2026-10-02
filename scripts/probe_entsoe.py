"""One-off probe of the ENTSO-E Transparency API: checks the token and logs the shape of each document type."""
import os, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import requests

LOG = Path(__file__).resolve().parents[1] / "data" / "raw" / "entsoe" / "probe_log.txt"
tok = os.environ.get("ENTSOE_TOKEN", "")
end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
st = end - timedelta(hours=24)
f = lambda d: d.strftime("%Y%m%d%H%M")
PL, DE = "10YPL-AREA-----S", "10Y1001A1001A82H"
tests = {
    "A44 price PL": dict(documentType="A44", in_Domain=PL, out_Domain=PL),
    "A44 price EE": dict(documentType="A44", in_Domain="10Y1001A1001A39I", out_Domain="10Y1001A1001A39I"),
    "A65 load PL": dict(documentType="A65", processType="A16", outBiddingZone_Domain=PL),
    "A75 gen PL": dict(documentType="A75", processType="A16", in_Domain=PL),
    "A11 flow PL->DE": dict(documentType="A11", in_Domain=DE, out_Domain=PL),
    "A73 unit gen PL": dict(documentType="A73", processType="A16", in_Domain=PL),
    "A68 installed PL": dict(documentType="A68", processType="A33", in_Domain=PL),
}
out = [f"token set: {bool(tok)}, length {len(tok)}"]
for name, p in tests.items():
    q = {**p, "securityToken": tok, "periodStart": f(st), "periodEnd": f(end)}
    if name.startswith("A68"):
        q.update(periodStart=f(end.replace(month=1, day=1, hour=0)), periodEnd=f(end))
    try:
        r = requests.get("https://web-api.tp.entsoe.eu/api", params=q, timeout=90)
        out.append(f"--- {name}: HTTP {r.status_code}, {len(r.content)} bytes, {r.headers.get('content-type')}")
        out.append(r.text[:1800].replace(tok, "***"))
    except Exception as ex:
        out.append(f"--- {name}: {ex!r}")
    time.sleep(1)
LOG.parent.mkdir(parents=True, exist_ok=True)
LOG.write_text("\n".join(out) + "\n", encoding="utf-8")
print("\n".join(o[:200] for o in out))
