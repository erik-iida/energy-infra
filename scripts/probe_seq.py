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
                t = datetime.fromisoformat(h.replace('Z', '+00:00'))
                if p is not None and t in hv:
                    diffs.append(abs(p - hv[t]))
                    rows.append((t, p, hv[t]))
            P(f"  vs {label}: {len(diffs)} common hours, mean |diff| {sum(diffs)/len(diffs):.3f}, max {max(diffs):.3f}" if diffs else f"  vs {label}: no common hours")
            for t, p, v in rows[:3] + rows[-3:]:
                P(f"     {t:%d %b %H:%M}  site {p:.2f}  entsoe {v:.2f}")
        last = [(datetime.fromisoformat(h.replace('Z', '+00:00')), p) for h, p in zip(hrs, pr) if p is not None][-1]
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


# ---------------------------------------------------------------- 4. seq 2 in the past, other zones, gaps
P("\n=== A44 DE-LU 18 Sep .. 02 Oct: is there a seq 2 for past days, and how does it relate to seq 1?")
txt = get(documentType="A44", in_Domain=DE, out_Domain=DE, periodStart=f(today - timedelta(days=15)), periodEnd=f(today))
if not txt.startswith(("HTTP", "failed")):
    pd_ = defaultdict(lambda: defaultdict(dict))
    for d in parse(txt, "price.amount"):
        sq = d["classificationSequence_AttributeInstanceComponent.position"]
        for t, v in d["pts"].items():
            pd_[(t + timedelta(hours=2)).date()][sq][t] = v  # local (CEST) delivery day
    for day in sorted(pd_):
        s1, s2 = pd_[day].get("1", {}), pd_[day].get("2", {})
        both = sorted(set(s1) & set(s2))
        md = sum(abs(s1[t] - s2[t]) for t in both) / len(both) if both else float("nan")
        P(f"  {day}: n seq1={len(s1)} seq2={len(s2)}  mean seq1 {sum(s1.values())/max(len(s1),1):.1f} seq2 {sum(s2.values())/max(len(s2),1):.1f}  mean|diff| {md:.1f}")
    # does seq 2 look like seq 1 shifted by a day?
    ks1 = {t: v for dd in pd_.values() for t, v in dd.get("1", {}).items()}
    ks2 = {t: v for dd in pd_.values() for t, v in dd.get("2", {}).items()}
    for lag in (0, 96, -96, 672, -672):
        pairs = [(ks1[t], ks2[t + timedelta(minutes=15 * lag)]) for t in ks1 if t + timedelta(minutes=15 * lag) in ks2]
        if pairs:
            P(f"  seq1 vs seq2 shifted {lag*15/60:+.0f} h: n={len(pairs)} mean|diff| {sum(abs(x-y) for x,y in pairs)/len(pairs):.1f}")

P("\n=== A44 seq presence per zone, window today-1 .. today+3 (does seq 2 reach days without an auction?)")
for z, eic in (("FR", "10YFR-RTE------C"), ("PL", "10YPL-AREA-----S"), ("RO", RO), ("HU", "10YHU-MAVIR----U"),
               ("NL", "10YNL----------L"), ("DK1", "10YDK-1--------W"), ("BG", "10YCA-BULGARIA-R")):
    t2 = get(documentType="A44", in_Domain=eic, out_Domain=eic, periodStart=f(today - timedelta(days=1)), periodEnd=f(today + timedelta(days=3)))
    if t2.startswith(("HTTP", "failed")) or "Acknowledgement" in t2[:400]:
        P(f"  {z}: " + " ".join(re.sub(r"<[^>]+>", " ", t2).split())[:160])
        continue
    rows = []
    for d in parse(t2, "price.amount"):
        k = sorted(d["pts"])
        rows.append(f"seq{d['classificationSequence_AttributeInstanceComponent.position']} {d['periods'][0][2]} n={len(k)} {k[0]:%d %H:%M}..{k[-1]:%d %H:%M}")
    P(f"  {z}: " + " | ".join(rows))

P("\n=== DE-LU seq-2 gaps on the first future day (positions missing)")
for d in parse(get(documentType="A44", in_Domain=DE, out_Domain=DE, periodStart=f(today + timedelta(hours=-2)), periodEnd=f(today + timedelta(days=3))), "price.amount"):
    if d["classificationSequence_AttributeInstanceComponent.position"] == "2" and d["pts"]:
        ks = sorted(d["pts"])
        a0 = datetime.fromisoformat(d["periods"][0][0].replace("Z", "+00:00"))
        miss = [a0 + timedelta(minutes=15 * i) for i in range(96) if a0 + timedelta(minutes=15 * i) not in d["pts"]]
        if miss:
            P(f"  period {d['periods'][0][0]}: missing {[m.strftime('%d %H:%M') for m in miss]}")

LOG.parent.mkdir(parents=True, exist_ok=True)
LOG.write_text("\n".join(out) + "\n", encoding="utf-8")
print("\n".join(out))
