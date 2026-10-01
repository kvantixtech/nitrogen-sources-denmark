#!/usr/bin/env python3
"""Daily flow for every candidate station, and the period, as fixed in METHOD.md.

For each candidate in data/catchments/summary.csv and each calendar year 2010-2025:
  - downloads the VanDa discharge series (examination type 27, l/s) as CSV, open API, no login
  - daily flow = arithmetic mean of all values with a time stamp on that UTC date
  - a flow year is valid if at least 90 % of its days have values and no gap is longer than 14 days
    (a gap is a run of days without values, counted inside the year and from 1 January / to 31 December)
Then the period: five consecutive completed calendar years ending with the latest completed year
in which at least 75 % of the candidates have a valid flow year.

The 10-minute series are not stored (several GB). Each download's size, row count and SHA-256 are.
Never reads a nitrogen value.

    python3 tools/flow.py
Writes data/flow/{daily.csv.xz, downloads.csv, coverage.csv, period.json}.
"""
import calendar, csv, datetime as dt, hashlib, io, json, lzma, os, sys, time, urllib.request
from concurrent.futures import ThreadPoolExecutor

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "flow")
YEARS = list(range(2010, 2026))
LAST_COMPLETED = 2025
UA = "kvantixtech nitrogen-sources-denmark (github actions; validation@kvantix.tech)"
URL = "https://vandah.miljoeportal.dk/api/water-flows?stationId={s}&from={y}-01-01T00:00Z&to={y1}-01-01T00:00Z&format=csv"


def fetch(s, y):
    url = URL.format(s=s, y=y, y1=y + 1)
    for attempt in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=300) as r:
                b = r.read()
            break
        except Exception as e:
            if attempt == 4:
                return s, y, None, str(e)[:200]
            time.sleep(15 * (attempt + 1))
    sums, counts, rows = {}, {}, 0
    text = b.decode("utf-8-sig").lstrip("﻿")
    rd = csv.reader(io.StringIO(text), delimiter=";")
    head = next(rd, None)
    if head:
        c = {k: i for i, k in enumerate(head)}
        for r in rd:
            if len(r) < len(head) or r[c["ExaminationTypeSc"]] != "27":
                continue
            day = r[c["MeasurementDateTime"]][:10]
            if not day.startswith(str(y)):
                continue                       # the API's upper bound is inclusive
            try:
                v = float(r[c["Result"]].replace(",", "."))
            except ValueError:
                continue
            sums[day] = sums.get(day, 0.0) + v; counts[day] = counts.get(day, 0) + 1; rows += 1
    daily = {d: (sums[d] / counts[d], counts[d]) for d in sums}
    return s, y, {"bytes": len(b), "rows": rows, "sha256": hashlib.sha256(b).hexdigest(), "daily": daily}, ""


def coverage(days, y):
    n = 366 if calendar.isleap(y) else 365
    have = sorted(dt.date.fromisoformat(d) for d in days)
    gaps, prev = [], dt.date(y, 1, 1) - dt.timedelta(days=1)
    for d in have + [dt.date(y, 12, 31) + dt.timedelta(days=1)]:
        gaps.append((d - prev).days - 1); prev = d
    longest = max(gaps) if gaps else n
    share = len(have) / n
    return share, longest, (share >= 0.90 and longest <= 14)


def main():
    cands = [r["stationId"] for r in csv.DictReader(open(os.path.join(ROOT, "data", "catchments", "summary.csv"), encoding="utf-8"))]
    os.makedirs(OUT, exist_ok=True)
    jobs = [(s, y) for s in cands for y in YEARS]
    print(f"{len(cands)} candidates x {len(YEARS)} years = {len(jobs)} downloads", flush=True)
    results, t0 = {}, time.time()
    with ThreadPoolExecutor(max_workers=4) as ex:
        for n, (s, y, res, err) in enumerate(ex.map(lambda j: fetch(*j), jobs), 1):
            results[(s, y)] = (res, err)
            if n % 100 == 0:
                print(f"... {n}/{len(jobs)} {time.time() - t0:.0f}s", flush=True)
    with open(os.path.join(OUT, "downloads.csv"), "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["stationId", "year", "bytes", "rows", "sha256", "error"])
        for (s, y) in sorted(results):
            res, err = results[(s, y)]
            w.writerow([s, y, res["bytes"] if res else "", res["rows"] if res else "", res["sha256"] if res else "", err])
    buf = io.StringIO(); w = csv.writer(buf, lineterminator="\n"); w.writerow(["stationId", "date", "flow_l_s", "values"])
    cov = []
    for (s, y) in sorted(results):
        res, err = results[(s, y)]
        daily = res["daily"] if res else {}
        for d in sorted(daily):
            w.writerow([s, d, f"{daily[d][0]:.4f}", daily[d][1]])
        share, longest, valid = coverage(daily.keys(), y) if daily else (0.0, 366, False)
        cov.append([s, y, len(daily), round(share, 4), longest, valid, err])
    with lzma.open(os.path.join(OUT, "daily.csv.xz"), "wb", preset=6) as fh:
        fh.write(buf.getvalue().encode())
    with open(os.path.join(OUT, "coverage.csv"), "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["stationId", "year", "days", "share", "longest_gap_days", "valid", "error"]); w.writerows(cov)
    share_valid = {y: sum(1 for r in cov if r[1] == y and r[5]) / len(cands) for y in YEARS}
    end = max((y for y in YEARS if y <= LAST_COMPLETED and share_valid[y] >= 0.75), default=None)
    period = {"rule": "five consecutive completed years ending with the latest completed year in which >= 75 % of candidates have a valid flow year",
              "candidates": len(cands), "share_valid_by_year": {str(y): round(v, 4) for y, v in share_valid.items()},
              "end": end, "years": list(range(end - 4, end + 1)) if end else None}
    json.dump(period, open(os.path.join(OUT, "period.json"), "w"), indent=1)
    man_path = os.path.join(ROOT, "data", "manifest.json")
    man = json.load(open(man_path, encoding="utf-8"))
    for f, what in (("daily.csv.xz", "Daily mean discharge (l/s, UTC dates) per candidate station, 2010-2025, from VanDa water-flows"),
                    ("downloads.csv", "Size, row count and SHA-256 of every VanDa download behind daily.csv.xz"),
                    ("coverage.csv", "Days with flow, longest gap and validity per station-year"),
                    ("period.json", "The period, chosen from flow coverage only")):
        p = os.path.join(OUT, f)
        man["files"]["flow/" + f] = {"sha256": hashlib.sha256(open(p, "rb").read()).hexdigest(), "bytes": os.path.getsize(p),
                                     "what": what, "made_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    json.dump(man, open(man_path, "w", encoding="utf-8"), indent=1, ensure_ascii=False); open(man_path, "a").write("\n")
    print(json.dumps(period, indent=1))


if __name__ == "__main__":
    main()
