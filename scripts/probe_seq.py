"""Probe (runs on Actions, commits data/raw/entsoe/probe_seq_log.txt):
 1. A44 DE-LU: every TimeSeries with classificationSequence position, contract/auction type, resolution, period and
    values; seq 1 vs seq 2 on overlapping timestamps; the same query with contract_MarketAgreement.type=A01.
 2. Compare stored-style prices (seq 1 only, hourly mean) with the live site's feed.json day-ahead price for DE-LU.
 3. Romania A75 actual generation: which hours/PSR types exist per day, with the first and last timestamp.
No token in the log."""
import json, os, re, sys, time
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
import requests

LOG = Path(__file__).resolve().parents[1] / "data" / "raw" / "entsoe" / "probe_seq_log.txt"
tok = os.environ.get("ENTSOE_TOKEN", "")
URL = "https://web-api.tp.entsoe.eu/api"
DE, RO = "10Y1001A1001A82H", "10YRO-TEL------P"
now = datetime.now(timezone.utc)
today = now.replace(hour=0, minute=0, second=0, microsecond=0)
f = lambda d: d.strftime("%Y%m%d%H%M")
out = [f"run {now:%Y-%m-%d %H:%M} UTC, token set: {bool(tok)}"]


def P(s=""):
    out.append(s)


def get(**q):
    for a in range(3):
        r = requests.get(URL, params={**q, "securityToken": tok}, timeout=120)
        if r.status_code == 200:
            return r.text.replace(tok, "***")
        if r.status_code in (429, 503):
            time.sleep(20)
            continue
        return f"HTTP {r.status_code} " + re.sub(r"<[^>]+>", " ", r.text.replace(tok, "***"))[:300]
    return "failed"


def tag(ts, k):
    m = re.search(rf"<{re.escape(k)}>(.*?)</{re.escape(k)}>", ts)
    return m.group(1) if m else None


def parse(txt, vtag):
    """-> list of dicts per TimeSeries with its points as {utc datetime: value}."""
    res = []
    for ts in re.findall(r"<TimeSeries>(.*?)</TimeSeries>", txt, re.S):
        d = {k: tag(ts, k) for k in ("mRID", "auction.type", "businessType", "contract_MarketAgreement.type",
                                     "classificationSequence_AttributeInstanceComponent.position", "currency_Unit.name",
                                     "curveType", "psrType")}
        d["gen"] = "inBiddingZone" in ts
        pts, pers = {}, []
        for per in re.findall(r"<Period>(.*?)</Period>", ts, re.S):
            a, b = re.search(r"<start>(.*?)</start>\s*<end>(.*?)</end>", per, re.S).groups()
            res_ = re.search(r"<resolution>(.*?)</resolution>", per).group(1)
            step = int(re.search(r"PT(\d+)M", res_).group(1)) if "PT" in res_ and "M" in res_ else 60
            a0 = datetime.fromisoformat(a.replace("Z", "+00:00"))
            pers.append((a, b, res_))
            for pos, v in re.findall(rf"<position>(\d+)</position>\s*<{re.escape(vtag)}>(.*?)</{re.escape(vtag)}>", per, re.S):
                pts[a0 + timedelta(minutes=step * (int(pos) - 1))] = float(v)
        d["periods"], d["pts"] = pers, pts
        res.append(d)
    return res


def hourly(pts):
    h = defaultdict(list)
    for t, v in pts.items():
        h[t.replace(minute=0)].append(v)
    return {t: sum(v) / len(v) for t, v in h.items()}


# ---------------------------------------------------------------- 1. DE-LU A44
a, b = today - timedelta(days=1), today + timedelta(days=3)
variants = {"default": {}, "contract A01": {"contract_MarketAgreement.type": "A01"}}
series = {}
for name, extra in variants.items():
    txt = get(documentType="A44", in_Domain=DE, out_Domain=DE, periodStart=f(a), periodEnd=f(b), **extra)
    P(f"\n=== A44 DE-LU {a:%d %b}..{b:%d %b} UTC, {name}: {len(txt)} chars")
    if txt.startswith(("HTTP", "failed")):
        P(txt)
        continue
    ts_list = parse(txt, "price.amount")
    series[name] = ts_list
    for i, d in enumerate(ts_list):
        v = list(d["pts"].values())
        P(f"  TS{i} mRID={d['mRID']} seq={d['classificationSequence_AttributeInstanceComponent.position']} "
          f"auction={d['auction.type']} biz={d['businessType']} contract={d['contract_MarketAgreement.type']} "
          f"curve={d['curveType']} cur={d['currency_Unit.name']}")
        P(f"      periods {d['periods']}")
        if d["pts"]:
            ks = sorted(d["pts"])
            P(f"      n={len(v)} {ks[0]:%d %b %H:%M}..{ks[-1]:%d %b %H:%M} UTC  min {min(v):.2f} max {max(v):.2f} mean {sum(v)/len(v):.2f}")
    # first-publication evidence: raw header of the document
    P("  doc header: " + " ".join(re.sub(r"<[^>]+>", " ", txt[:900]).split())[:300])

base = series.get("default", [])
by_seq = defaultdict(dict)
for d in base:
    by_seq[d["classificationSequence_AttributeInstanceComponent.position"]].update(d["pts"])
P("\n=== seq overlap (DE-LU, per timestamp where both exist)")
if len(by_seq) > 1:
    ks = sorted(by_seq)
    s1, s2 = by_seq[ks[0]], by_seq[ks[1]]
    both = sorted(set(s1) & set(s2))
    P(f"  seqs {ks}: n1={len(s1)} n2={len(s2)} overlap={len(both)}; seq {ks[1]} only: "
      f"{len(set(s2) - set(s1))}, seq {ks[0]} only: {len(set(s1) - set(s2))}")
    diffs = [abs(s1[t] - s2[t]) for t in both]
    if diffs:
        P(f"  mean |diff| {sum(diffs)/len(diffs):.3f}, max {max(diffs):.3f}")
    for t in both[:6] + both[-3:]:
        P(f"    {t:%d %b %H:%M}  seq{ks[0]} {s1[t]:.2f}  seq{ks[1]} {s2[t]:.2f}")
    only2 = sorted(set(s2) - set(s1))
    if only2:
        P(f"  seq {ks[1]}-only range {only2[0]:%d %b %H:%M}..{only2[-1]:%d %b %H:%M} sample "
          + ", ".join(f"{t:%d %H:%M}={s2[t]:.1f}" for t in only2[:4]))
else:
    P(f"  only seq(s) {list(by_seq)}")

# ---------------------------------------------------------------- 2. live site comparison
P("\n=== live site feed.json, DE-LU day-ahead")
try:
    feed = requests.get("https://erik-iida.github.io/energy-infra/data/feed.json", timeout=60).json()
    hrs = feed["hours"] + feed["fc_hours"]
    pr = (feed.get("market") or {}).get("prices", {}).get("DE-LU")
    P(f"  generated {feed.get('generated')}, {len(hrs)} hours, DE-LU price present: {pr is not None}")
    if pr and by_seq:
        ks = sorted(by_seq)
        for label, src in (("seq" + ks[0], by_seq[ks[0]]), ("all seqs mean", None)):
            if src is None:
                allp = defaultdict(list)
                for s in by_seq.values():
                    for t, v in hourly(s).items():
                        allp[t].append(v)
                src = {t: sum(v) / len(v) for t, v in allp.items()}
                hv = src
            else:
                hv = hourly(src)
            diffs, rows = [], []
            for h, p in zip(hrs, pr):
                t = datetime.fromtimestamp(h, timezone.utc)
                if p is not None and t in hv:
                    diffs.append(abs(p - hv[t]))
                    rows.append((t, p, hv[t]))
            P(f"  vs {label}: {len(diffs)} common hours, mean |diff| {sum(diffs)/len(diffs):.3f}, max {max(diffs):.3f}" if diffs else f"  vs {label}: no common hours")
            for t, p, v in rows[:3] + rows[-3:]:
                P(f"     {t:%d %b %H:%M}  site {p:.2f}  entsoe {v:.2f}")
        last = [(datetime.fromtimestamp(h, timezone.utc), p) for h, p in zip(hrs, pr) if p is not None][-1]
        P(f"  site's last DE-LU price hour: {last[0]:%d %b %H:%M} UTC = {last[1]}")
except Exception as e:
    P(f"  failed: {e!r}")

# ---------------------------------------------------------------- 3. Romania A75
P("\n=== A75 RO actual generation, last 5 days")
txt = get(documentType="A75", processType="A16", in_Domain=RO, periodStart=f(today - timedelta(days=4)),
          periodEnd=f(today + timedelta(days=1)))
if txt.startswith(("HTTP", "failed")) or "Acknowledgement" in txt[:400]:
    P("  " + " ".join(re.sub(r"<[^>]+>", " ", txt).split())[:300])
else:
    ts_list = [d for d in parse(txt, "quantity") if d["gen"]]
    days = defaultdict(lambda: defaultdict(set))
    for d in ts_list:
        for t in d["pts"]:
            days[t.date()][d["psrType"]].add(t)
    allts = sorted({t for d in ts_list for t in d["pts"]})
    P(f"  {len(ts_list)} gen TimeSeries; overall {allts[0]:%d %b %H:%M}..{allts[-1]:%d %b %H:%M} UTC" if allts else "  no points")
    for day in sorted(days):
        n = {p: len(v) for p, v in days[day].items()}
        P(f"  {day}: psr types {len(n)}, points per type min {min(n.values())} max {max(n.values())}"
          f" (full day = 24 hourly or 96 quarter-hourly)")
    P("  per-psr last timestamp: " + ", ".join(
        f"{p}={max(t for d in ts_list if d['psrType'] == p for t in d['pts']):%d %H:%M}"
        for p in sorted({d['psrType'] for d in ts_list if d['pts']})))

LOG.parent.mkdir(parents=True, exist_ok=True)
LOG.write_text("\n".join(out) + "\n", encoding="utf-8")
print("\n".join(out))
