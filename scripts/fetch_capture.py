"""Monthly capture prices per technology for every bidding zone, from the ENTSO-E Transparency Platform.

    ENTSOE_TOKEN=... python scripts/fetch_capture.py

For each (bidding zone, month):
  * actual generation per production type in the zone (A75, in_Domain = bidding zone) and day-ahead prices (A44),
    both averaged to hours;
  * capture price per technology = generation-weighted average price over the hours with both;
  * baseload (mean price), negative-price hours, and BESS spreads: TB2 / TB4 = mean of the 2 / 4 highest hourly
    prices of a day minus the mean of the 2 / 4 lowest, averaged over the days of the month (days in CET/CEST).

Resumable: data/raw/capture/cells.json keeps finished cells; the current and previous month are refreshed once a day; zones
without data are retried weekly. A run stops after TIME_BUDGET_S and the next run continues (newest months first).
Writes data/static/capture.json for the page and data/raw/capture/capture_log.txt.
Data: ENTSO-E Transparency Platform, https://transparency.entsoe.eu
"""
from __future__ import annotations

import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pipeline import config, entsoe  # noqa: E402

STATE = ROOT / "data" / "raw" / "capture" / "cells.json"
OUT = config.static_file("capture.json")
LOG = ROOT / "data" / "raw" / "capture" / "capture_log.txt"
MONTHS = 24
TIME_BUDGET_S = 40 * 60
WORKERS = 4
CET = ZoneInfo("Europe/Brussels")
SEQ2_ZONES = {"AT", "DE-LU", "DK1", "DK2", "ES"}  # zones with an extra A44 seq-2 series (Oct 3 2026 probe)
SKIP = {"AL"}  # no day-ahead market data on the platform
log_lines: list[str] = []


def log(msg: str) -> None:
    print(msg, flush=True)
    log_lines.append(msg)


def months(n: int) -> list[str]:
    d = datetime.now(timezone.utc).date().replace(day=1)
    out = []
    for _ in range(n):
        out.append(d.strftime("%Y-%m"))
        d = (d - timedelta(days=1)).replace(day=1)
    return out  # newest first


def month_bounds(m: str) -> tuple[float, float]:
    """UTC timestamps of the month in CET (so local days are whole), capped at the current hour."""
    y, mo = map(int, m.split("-"))
    a = datetime(y, mo, 1, tzinfo=CET)
    b = datetime(y + (mo == 12), mo % 12 + 1, 1, tzinfo=CET)
    now = time.time() // 3600 * 3600
    return a.timestamp(), min(b.timestamp(), now)


def fmt(t: float) -> str:
    return datetime.fromtimestamp(t, timezone.utc).strftime("%Y%m%d%H%M")


def spreads(price: dict[int, float]) -> tuple[float | None, float | None]:
    """Average over days (CET) of TB2 and TB4, using days with at least 20 priced hours."""
    days: dict[date, list[float]] = {}
    for h, p in price.items():
        days.setdefault(datetime.fromtimestamp(h, CET).date(), []).append(p)
    t2, t4 = [], []
    for v in days.values():
        if len(v) < 20:
            continue
        v = sorted(v)
        t2.append(sum(v[-2:]) / 2 - sum(v[:2]) / 2)
        t4.append(sum(v[-4:]) / 4 - sum(v[:4]) / 4)
    return (round(sum(t2) / len(t2), 1) if t2 else None, round(sum(t4) / len(t4), 1) if t4 else None)


def cell(zone: str, m: str) -> dict:
    eic = entsoe.ZONE_EIC[zone]
    a, b = month_bounds(m)
    cl = entsoe.Client()
    price: dict[int, float] = {}
    cur = "EUR"
    for _ts, _ns, hv in entsoe.series(cl.get(documentType="A44", in_Domain=eic, out_Domain=eic,
                                         periodStart=fmt(a), periodEnd=fmt(b)), "price.amount"):
        if entsoe.price_seq(_ts, _ns) != 1:  # AT, DE-LU, DK2, ES carry a second, non-auction series
            continue
        cur = entsoe.currency(_ts, _ns)  # stored as published (UA-IPS: UAH); converted to EUR when written out
        for h, v in hv.items():
            if a <= h < b:
                price[h] = v if h not in price else (price[h] + v) / 2
    gen: dict[str, dict[int, float]] = {}
    for ts, ns, hv in entsoe.series(cl.get(documentType="A75", processType="A16", in_Domain=eic,
                                           periodStart=fmt(a), periodEnd=fmt(b)), "quantity"):
        if ts.find(ns + "inBiddingZone_Domain.mRID") is None:  # consumption (pumping / charging)
            continue
        psr = ts.find(f"{ns}MktPSRType/{ns}psrType")
        key = entsoe.PSR.get(psr.text if psr is not None else "", ("others", "Other"))[0]
        d = gen.setdefault(key, {})
        for h, v in hv.items():
            if a <= h < b:
                d[h] = d.get(h, 0) + max(0.0, v)
    out = {"day": datetime.now(timezone.utc).date().isoformat(), "calls": cl.calls, "cur": cur, "sq": 1}
    if cl.errors:
        out["err"] = cl.errors[-2:]
    if not price:
        out["none"] = True
        return out
    out["h"] = len(price)
    out["b"] = round(sum(price.values()) / len(price), 2)
    out["neg"] = sum(1 for p in price.values() if p < 0)
    out["tb2"], out["tb4"] = spreads(price)
    tech = {}
    for k, d in gen.items():
        hrs = [h for h in d if h in price]
        e = sum(d[h] for h in hrs)
        if e / 1000 < 0.5:  # less than 0.5 GWh in the month: not meaningful
            continue
        tech[k] = [round(sum(d[h] * price[h] for h in hrs) / e, 2), round(e / 1000, 1),
                   round(sum(d[h] for h in hrs if price[h] < 0) / e, 4)]
    out["t"] = tech
    return out


def main() -> None:
    if not entsoe.token():
        log("ENTSOE_TOKEN not set")
        return
    t0 = time.time()
    fx = entsoe.refresh_fx(log)
    st = json.loads(STATE.read_text()) if STATE.exists() else {}
    cells = st.setdefault("cells", {})
    ms = months(MONTHS)
    today = datetime.now(timezone.utc).date()
    zones = [z for z in entsoe.ZONE_EIC if z not in SKIP]
    todo = []
    for m in ms:
        for z in zones:
            c = cells.get(f"{z}|{m}")
            if c is None or (z in entsoe.ZONE_CURRENCY and "cur" not in c):  # non-EUR zones: refetch until stored raw
                todo.append((z, m))
            elif c.get("sq") != 1:  # computed before the A44 seq-1 filter (position-2 series were averaged in)
                todo.append((z, m))
            elif m in ms[:2] and c.get("day") != today.isoformat():
                todo.append((z, m))
            elif c.get("none") and (today - date.fromisoformat(c["day"])).days >= 7:
                todo.append((z, m))
    log(f"{len(todo)} (zone, month) cells to fetch")
    done = calls = 0
    with ThreadPoolExecutor(WORKERS) as ex:
        it = iter(todo)
        running = {}
        for _ in range(WORKERS):
            nx = next(it, None)
            if nx:
                running[ex.submit(cell, *nx)] = nx
        while running:
            fut = next(as_completed(running))
            z, m = running.pop(fut)
            try:
                c = fut.result()
                cells[f"{z}|{m}"] = c
                calls += c.get("calls", 0)
                done += 1
                if c.get("err"):
                    log(f"  {z} {m}: {c['err']}")
            except Exception as e:
                log(f"  {z} {m}: failed {e!r}"[:300])
            if done % 25 == 0:
                STATE.parent.mkdir(parents=True, exist_ok=True)
                STATE.write_text(json.dumps(st, separators=(",", ":")))
            if time.time() - t0 < TIME_BUDGET_S:
                nx = next(it, None)
                if nx:
                    running[ex.submit(cell, *nx)] = nx
    STATE.parent.mkdir(parents=True, exist_ok=True)
    STATE.write_text(json.dumps(st, separators=(",", ":")))
    left = len(todo) - done
    log(f"fetched {done} cells with {calls} calls in {time.time() - t0:.0f} s; {left} left for the next run")

    # public file: months ascending, only cells with prices
    pub_months = sorted({k.split("|")[1] for k, c in cells.items() if not c.get("none") and k.split("|")[1] in ms})
    out_z = {}
    for z in zones:
        row = {}
        for m in pub_months:
            c = cells.get(f"{z}|{m}")
            if c and not c.get("none"):
                if z in SEQ2_ZONES and c.get("sq") != 1:  # known to be contaminated until refetched
                    continue
                cur = c.get("cur", "EUR")
                if z in entsoe.ZONE_CURRENCY and "cur" not in c:  # old cell of unknown currency: skip until refetched
                    continue
                r = entsoe.eur_rate(cur)
                if r is None:  # no stored rate: leave the zone out rather than publish another currency
                    continue
                row[m] = {k: c[k] for k in ("h", "neg") if k in c}
                for k in ("b", "tb2", "tb4"):
                    if c.get(k) is not None:
                        row[m][k] = round(c[k] / r, 2)
                row[m]["t"] = {k: [round(v[0] / r, 2), *v[1:]] for k, v in c.get("t", {}).items()}
        if row:
            out_z[z] = row
    names = {}
    for code, (k, n) in entsoe.PSR.items():
        names.setdefault(k, n if k != "others" else "Other")
    names["fossil_gas"] = "Gas"
    OUT.write_text(json.dumps({
        "generated": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "source": "ENTSO-E Transparency Platform: actual generation per production type (per bidding zone) and "
                  "day-ahead prices, hourly averages",
        "complete": left == 0, "months": pub_months,
        "fx": {k: {"rate": v.get("rate"), "date": v.get("date"), "source": v.get("source")} for k, v in fx.items()}, "names": names, "zones": out_z,
    }, separators=(",", ":")), encoding="utf-8")
    log(f"wrote {OUT.relative_to(ROOT)}: {len(out_z)} zones, {len(pub_months)} months, {OUT.stat().st_size / 1e3:.0f} kB")


if __name__ == "__main__":
    try:
        main()
    finally:
        LOG.parent.mkdir(parents=True, exist_ok=True)
        LOG.write_text("\n".join(log_lines) + "\n", encoding="utf-8")
