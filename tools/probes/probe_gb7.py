"""Probe 7: Elexon Market Index (MID): providers, price/volume, coverage, history depth. No keys. Commits its log."""
import collections
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

LOG = Path(__file__).resolve().parents[2] / "data" / "raw" / "gbie" / "probe7_log.txt"
UA = {"User-Agent": "GridEconomics hobby project (erikiida10@gmail.com)"}
EL = "https://data.elexon.co.uk/bmrs/api/v1"
out = []
now = datetime.now(timezone.utc).replace(minute=0, second=0, microsecond=0)


def mid(a, b, label):
    r = requests.get(f"{EL}/datasets/MID", params={"from": a.strftime("%Y-%m-%dT%H:%MZ"), "to": b.strftime("%Y-%m-%dT%H:%MZ"), "format": "json"}, headers=UA, timeout=90)
    out.append(f"=== {label}: {r.status_code} {len(r.content)} B {r.url[:160]}")
    if r.status_code != 200:
        out.append("    " + r.text[:300])
        return
    j = r.json()
    rows = j.get("data", j) if isinstance(j, dict) else j
    out.append(f"    rows {len(rows)}; keys {list(rows[0]) if rows else None}")
    by = collections.defaultdict(list)
    for x in rows:
        by[x["dataProvider"]].append(x)
    for p, xs in by.items():
        nz = [x for x in xs if x["volume"]]
        pr = [x["price"] for x in nz]
        out.append(f"    {p}: rows {len(xs)}, with volume {len(nz)}, price min/mean/max {min(pr, default=None)}/{(sum(pr) / len(pr)) if pr else None}/{max(pr, default=None)}, "
                   f"first {min(x['startTime'] for x in xs)} last {max(x['startTime'] for x in xs)}")
    for x in sorted(by.get("APXMIDP", []), key=lambda x: x["startTime"])[:8]:
        out.append("      APX " + json.dumps(x))
    # hourly products: do both half hours of an hour carry the same price?
    apx = {x["startTime"]: x["price"] for x in by.get("APXMIDP", [])}
    same = sum(1 for t, v in apx.items() if t.endswith(":00:00Z") and apx.get(t.replace(":00:00Z", ":30:00Z")) == v)
    out.append(f"    APX hours with equal :00/:30 price: {same} of {sum(1 for t in apx if t.endswith(':00:00Z'))}")


mid(now - timedelta(days=3), now, "last 3 days")
mid(now - timedelta(days=3), now + timedelta(days=1), "up to tomorrow (is the next day there?)")
for d in ("2018-02-01", "2019-06-03", "2021-01-12", "2022-09-05", "2024-03-04"):
    a = datetime.fromisoformat(d).replace(tzinfo=timezone.utc)
    mid(a, a + timedelta(days=1), f"history {d}")
mid(now - timedelta(days=31), now, "31 days (request size limit?)")
mid(now - timedelta(days=95), now, "95 days")
LOG.write_text("\n".join(out) + "\n")
print("\n".join(out)[:2500])
