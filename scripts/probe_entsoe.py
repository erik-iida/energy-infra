"""One-off probe of the ENTSO-E Transparency API: Ukraine (UA-IPS) day-ahead prices - which TimeSeries come back,
in which currency, with what values (last 24 h and August 2026)."""
import os, re, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
import requests

LOG = Path(__file__).resolve().parents[1] / "data" / "raw" / "entsoe" / "probe_log.txt"
tok = os.environ.get("ENTSOE_TOKEN", "")
end = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)
f = lambda d: d.strftime("%Y%m%d%H%M")
UA = "10Y1001C--000182"
windows = {"last 24 h": (end - timedelta(hours=24), end),
           "Aug 2026": (datetime(2026, 7, 31, 22, tzinfo=timezone.utc), datetime(2026, 8, 31, 22, tzinfo=timezone.utc))}
out = [f"token set: {bool(tok)}"]
for name, (a, b) in windows.items():
    q = dict(documentType="A44", in_Domain=UA, out_Domain=UA, periodStart=f(a), periodEnd=f(b), securityToken=tok)
    r = requests.get("https://web-api.tp.entsoe.eu/api", params=q, timeout=90)
    t = r.text.replace(tok, "***")
    out.append(f"=== {name}: HTTP {r.status_code}, {len(t)} chars")
    out.append(t[:700])
    for i, ts in enumerate(re.findall(r"<TimeSeries>(.*?)</TimeSeries>", t, re.S)):
        tags = {k: (re.search(f"<{k}>(.*?)</{k}>", ts) or [None, None])[1] for k in
                ("mRID", "auction.type", "businessType", "contract_MarketAgreement.type", "classificationSequence_AttributeInstanceComponent.position",
                 "currency_Unit.name", "price_Measure_Unit.name", "curveType")}
        per = re.findall(r"<start>(.*?)</start>\s*<end>(.*?)</end>\s*</timeInterval>\s*<resolution>(.*?)</resolution>", ts)
        vals = [float(v) for v in re.findall(r"<price.amount>(.*?)</price.amount>", ts)]
        out.append(f"  TS {i}: {tags} periods {per[:2]}{'...' if len(per) > 2 else ''} n={len(vals)} "
                   f"min {min(vals) if vals else None} max {max(vals) if vals else None} mean {sum(vals) / len(vals) if vals else None:.1f}"
                   if vals else f"  TS {i}: {tags} no values")
    time.sleep(1)
LOG.parent.mkdir(parents=True, exist_ok=True)
LOG.write_text("\n".join(out) + "\n", encoding="utf-8")
print("\n".join(out))
