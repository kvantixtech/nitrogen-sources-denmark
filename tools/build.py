#!/usr/bin/env python3
"""Everything in METHOD.md, from data/ to results/. Standard library + NumPy; same inputs give the same bytes out.

    python3 tools/build.py
Exits 1 if a check in METHOD.md fails; results are still written, marked as not shown.
"""
import calendar, csv, datetime as dt, io, json, lzma, math, os, re, sys
from collections import Counter, defaultdict
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
D = lambda *p: os.path.join(ROOT, "data", *p)
OUT = os.path.join(ROOT, "results")
SEED, NBOOT = 20261001, 10000
PARAM = "Nitrogen,total N"
FRACTIONS = {"Total", "Ej oplyst"}
SAMPLE_TYPE = "Enkeltprøve"
QUALITY = {"2", "3"}
# R3: national nitrogen from houses outside the sewer, 2024 (Danmarks Statistik VANDUD, "Spredt bebyggelse ikke
# tilsluttet kloakering", total-N, Hele landet; checked in github.com/kvantixtech/wastewater-denmark), in kg
SCATTERED_N_KG_2024 = 437_000.0


def utc_date(s):
    # "31.01.2013 12.00.00 +01:00"
    d, t, z = s.split(" ")
    day, mon, yr = map(int, d.split(".")); hh, mm, ss = map(int, t.split("."))
    sign = 1 if z[0] == "+" else -1; zh, zm = map(int, z[1:].split(":"))
    local = dt.datetime(yr, mon, day, hh, mm, ss)
    return (local - sign * dt.timedelta(hours=zh, minutes=zm)).date()


def fnum(s):
    return float(s.replace(",", ".").replace("\xa0", "").strip())


def read_csv(path):
    return list(csv.DictReader(open(path, encoding="utf-8", newline="")))


# ------------------------------------------------------------------ inputs
def load():
    period = json.load(open(D("flow", "period.json")))
    years = period["years"]
    cat = {r["stationId"]: r for r in read_csv(D("catchments", "summary.csv"))}
    att = {r["stationId"]: r for r in read_csv(D("landuse", "attributes.csv"))}
    national = json.load(open(D("landuse", "national.json"), encoding="utf-8"))
    cov = {(r["stationId"], int(r["year"])): r["valid"] == "True" for r in read_csv(D("flow", "coverage.csv"))}
    flow = defaultdict(dict)
    with lzma.open(D("flow", "daily.csv.xz"), "rt", encoding="utf-8", newline="") as fh:
        for r in csv.DictReader(fh):
            flow[r["stationId"]][dt.date.fromisoformat(r["date"])] = float(r["flow_l_s"])
    # chemistry: filters fixed in CHANGELOG.md
    chem, pos, dropped = defaultdict(lambda: defaultdict(list)), {}, defaultdict(int)
    with lzma.open(D("raw", "vandkemi_tn.csv.xz"), "rt", encoding="utf-8-sig", newline="") as fh:
        rd = csv.reader(fh, delimiter=";"); h = next(rd); c = {k: i for i, k in enumerate(h)}
        for row in rd:
            sid = row[c["StedID"]]
            if sid not in pos and row[c["GeoZone"]] == "32":
                try:
                    pos[sid] = (fnum(row[c["x-koordinat"]]), fnum(row[c["y-koordinat"]]))
                except ValueError:
                    pass
            if row[c["Stofparameter"]] != PARAM: dropped["parameter"] += 1; continue
            if row[c["Analysefraktion"]] not in FRACTIONS: dropped["fraction"] += 1; continue
            if row[c["Prøvetype"]] != SAMPLE_TYPE: dropped["sample type"] += 1; continue
            if row[c["Kvalitetsmærke"]] not in QUALITY: dropped["quality mark"] += 1; continue
            attr = row[c["Resultat-attribut"]].replace("\xa0", " ").strip()
            if attr == ">": dropped["attribute >"] += 1; continue
            try:
                v = fnum(row[c["Resultat"]])
            except ValueError:
                dropped["unreadable result"] += 1; continue
            if attr in ("<", "<="): v = v / 2
            elif attr not in ("", "="): dropped["unknown attribute"] += 1; continue
            day = utc_date(row[c["Dato"]])
            chem[sid][day].append(v)
    chem = {s: {d: sum(v) / len(v) for d, v in days.items()} for s, days in chem.items()}   # same date: averaged
    return period, years, cat, att, national, cov, flow, chem, pos, dict(dropped)


# ------------------------------------------------------------------ one station-year
def sample_year_valid(days, y):
    ds = sorted(d for d in days if d.year == y)
    if len(ds) < 10:
        return False
    edges = [dt.date(y, 1, 1)] + ds + [dt.date(y, 12, 31)]
    return max((b - a).days for a, b in zip(edges, edges[1:])) <= 92


def interp_days(points, y):
    """Daily series for year y: linear between points, nearest value before the first and after the last."""
    ds = sorted(points)
    n = 366 if calendar.isleap(y) else 365
    x = np.array([(d - dt.date(y, 1, 1)).days for d in ds], dtype=float)
    v = np.array([points[d] for d in ds], dtype=float)
    return np.interp(np.arange(n, dtype=float), x, v)        # np.interp holds the end values flat


def station_year(flow_days, chem_days, y):
    q = {d: v for d, v in flow_days.items() if d.year == y}
    c = {d: v for d, v in chem_days.items() if d.year == y}
    Q = interp_days(q, y)                                     # l/s
    C = interp_days(c, y)                                     # mg/l
    L = float(np.sum(Q * 86400.0 * C * 1e-6))                 # kg
    V = float(np.sum(Q * 86.4))                               # m3
    return L, V


# ------------------------------------------------------------------ fitting
def ols(x, y, extra=None, w=None):
    X = [np.ones(len(x)), np.asarray(x, float)]
    if extra is not None:
        X += [np.asarray(e, float) for e in extra]
    X = np.column_stack(X); y = np.asarray(y, float)
    if w is not None:
        sw = np.sqrt(np.asarray(w, float)); X, y = X * sw[:, None], y * sw
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    return beta


def shares(rows, b):
    L = sum(r["L"] for r in rows); B = sum(b * r["V"] / 1000.0 for r in rows); P = sum(r["nP"] for r in rows)
    F = L - P - B
    return {"farmland": F / L, "background": B / L, "point": P / L, "L_kg": L, "B_kg": B, "P_kg": P, "F_kg": F}


def ci(vals):
    a = np.asarray(vals, float); a = a[~np.isnan(a)]
    return [float(np.percentile(a, 2.5)), float(np.percentile(a, 97.5))] if len(a) else [None, None]


def reading(point, lo, hi):
    if lo is not None and lo > 0.80: return "Higher than cited"
    if hi is not None and hi < 0.60: return "Lower than cited"
    if 0.60 <= point <= 0.80 and lo is not None and (hi - lo) <= 0.30: return "Agrees"
    return "Inconclusive"


def main():
    problems = []
    period, years, cat, att, national, cov, flow, chem, pos, dropped = load()
    y0, y1 = years[0], years[-1]
    log = open(os.path.join(ROOT, "CHANGELOG.md"), encoding="utf-8").read()
    # check 1: the period and the parameter code are written in CHANGELOG.md
    if f"Period fixed: {y0}–{y1}" not in log or "ScKode 253" not in log:
        problems.append("check 1: period or parameter code not found in CHANGELOG.md")
    # check 4: point layers add up to the national 2024 totals (Punktkilder 2024: plants 3,850 t, rain-dependent 1,476 t)
    if national["plants_n_t"] != 3850 or national["outlets_n_t"] != 1476:
        problems.append(f"check 4: point layers {national['plants_n_t']} t / {national['outlets_n_t']} t, expected 3850 / 1476")

    # ---- pairing and per-station values
    stations, excluded = [], []
    for sid, cr in sorted(cat.items()):
        why = None
        stated = float(cr["stated_km2"])
        if cr["accepted"] != "True": why = "catchment not accepted (±10 % of stated area)"
        elif not (5 <= stated <= 3000): why = "catchment outside 5–3000 km²"
        a = att.get(sid)
        if why is None and a is None: why = "no land-use attributes"
        # pairing: same number, else within 500 m; several -> same number, else most samples in the period, then nearest
        fx, fy = float(cr["x"]), float(cr["y"])
        near = []
        for csid, (cx, cy) in pos.items():
            d = math.hypot(cx - fx, cy - fy)
            if csid == sid or d <= 500:
                n_in = sum(1 for day in chem.get(csid, {}) if y0 <= day.year <= y1)
                near.append((csid != sid, -n_in, d, csid))
        chem_id = sorted(near)[0][3] if near else None
        if why is None and chem_id is None: why = "no chemistry station"
        rec = {"stationId": sid, "name": cr["name"], "chem": chem_id, "stated_km2": stated, "drawn_km2": float(cr["drawn_km2"] or 0)}
        if why is None:
            if int(a["fish_farms"]) > 0 or int(a["industrial_outlets"]) > 0:
                why = "fish farm or industrial outlet in catchment"
        valid = []
        if why is None:
            for y in years:
                if cov.get((sid, y)) and sample_year_valid(chem.get(chem_id, {}), y):
                    valid.append(y)
            if len(valid) < 4: why = f"{len(valid)} valid years (needs 4)"
        if why:
            rec["excluded"] = why; excluded.append(rec); continue
        per_year = {y: station_year(flow[sid], chem[chem_id], y) for y in valid}
        n = len(valid); L = sum(v[0] for v in per_year.values()); V = sum(v[1] for v in per_year.values())
        P_pl, P_out = float(a["plants_n_kg"]), float(a["outlets_n_kg"])
        runoff = V / (rec["drawn_km2"] * 1000.0) / n
        rec.update(A=float(a["farmland_share"]), clay=float(a["clay_share"]), district=a["district"], years=valid, n=n, L=L, V=V,
                   P=P_pl + P_out, P_plants=P_pl, scattered=int(a["scattered_houses"]), runoff_mm=runoff, per_year=per_year,
                   C=1000.0 * L / V, C_ps=1000.0 * (L - n * (P_pl + P_out)) / V)
        rec["nP"] = n * rec["P"]
        if not (100 <= runoff <= 900):
            rec["excluded"] = f"runoff {runoff:.0f} mm a year"; excluded.append(rec); continue
        if rec["C_ps"] <= 0:
            rec["excluded"] = "point sources exceed measured load"; excluded.append(rec); continue
        stations.append(rec)

    # ---- nesting and systems (station B is upstream of A if B's catchment outlet lies in A's catchment)
    from shapely.geometry import shape, Point
    geo = {f["properties"]["stationId"]: shape(f["geometry"]) for f in json.load(open(D("catchments", "catchments.geojson")))["features"]}
    outlet = {sid: Point(float(cat[sid]["outlet_x"]), float(cat[sid]["outlet_y"])) for sid in cat if cat[sid]["outlet_x"]}
    ids = [s["stationId"] for s in stations]
    down = {i: [j for j in ids if j != i and geo[j].covers(outlet[i])] for i in ids}
    outer = [i for i in ids if not down[i]]
    system = {}
    for i in ids:
        cands = [o for o in outer if o == i or geo[o].covers(outlet[i])]
        system[i] = min(cands, key=lambda o: geo[o].area) if cands else i
    for s in stations:
        s["outermost"] = s["stationId"] in outer; s["system"] = system[s["stationId"]]
    check6 = len(stations) >= 30

    # ---- analyses
    def fit(rows, mode="primary"):
        x = [r["A"] for r in rows]; y = [r["C_ps"] for r in rows]
        if mode == "R1":
            ds = sorted({r["district"] for r in rows}); dum = [[1.0 if r["district"] == d else 0.0 for r in rows] for d in ds[1:]]
            beta = ols(x, y, extra=dum); return float(beta[0]), float(beta[1])
        if mode == "R7":
            beta = ols(x, y, w=[r["V"] / r["n"] for r in rows]); return float(beta[0]), float(beta[1])
        if mode == "R8":
            beta = ols(x, y, extra=[[r["clay"] for r in rows]]); return float(beta[0]), float(beta[1]), float(beta[2])
        beta = ols(x, y); return float(beta[0]), float(beta[1])

    def variant(rows, mode):
        out = {"stations": len(rows), "outermost": sum(1 for r in rows if r["outermost"])}
        if len(rows) < 3:
            return dict(out, note="too few stations")
        f = fit(rows, mode)
        b, s = f[0], f[1]
        oc = [r for r in rows if r["outermost"]]
        sh = shares(oc, b)
        out.update(b=b, s=s, **{k: sh[k] for k in ("farmland", "background", "point")})
        if mode == "R8":
            out.update(clay_coef=f[2], b_sand=b, b_clay=b + f[2])
        return out

    rng = np.random.default_rng(SEED)
    systems = sorted({s["system"] for s in stations})
    by_sys = defaultdict(list)
    for s in stations: by_sys[s["system"]].append(s)
    boot_b, boot_s, boot_f, boot_bg, boot_p = [], [], [], [], []
    for _ in range(NBOOT):
        pick = rng.integers(0, len(systems), len(systems))
        rows = [r for k in pick for r in by_sys[systems[k]]]
        oc = [r for r in rows if r["outermost"]]
        if len(rows) < 3 or len({r["A"] for r in rows}) < 2 or not oc:
            for a in (boot_b, boot_s, boot_f, boot_bg, boot_p): a.append(float("nan"))
            continue
        b, s = fit(rows); sh = shares(oc, b)
        boot_b.append(b); boot_s.append(s); boot_f.append(sh["farmland"]); boot_bg.append(sh["background"]); boot_p.append(sh["point"])

    prim = variant(stations, "primary")
    prim.update(b_ci=ci(boot_b), s_ci=ci(boot_s), farmland_ci=ci(boot_f), background_ci=ci(boot_bg), point_ci=ci(boot_p))
    stop = not (prim.get("s_ci") and prim["s_ci"][0] is not None and prim["s_ci"][0] > 0)
    show_shares = check6 and not stop
    prim["reading"] = reading(prim["farmland"], *prim["farmland_ci"]) if show_shares else None
    A_vals = [s["A"] for s in stations]
    prim["A_range"] = [min(A_vals), max(A_vals)] if A_vals else None

    rob = {"R1": variant(stations, "R1")}
    r2 = [dict(s, nP=s["n"] * s["P_plants"], C_ps=1000.0 * (s["L"] - s["n"] * s["P_plants"]) / s["V"]) for s in stations]
    rob["R2"] = variant(r2, "primary")
    per_house = SCATTERED_N_KG_2024 / national["scattered_houses_count"]
    r3 = [dict(s, nP=s["n"] * (s["P"] + per_house * s["scattered"]), C_ps=1000.0 * (s["L"] - s["n"] * (s["P"] + per_house * s["scattered"])) / s["V"]) for s in stations]
    rob["R3"] = dict(variant(r3, "primary"), kg_per_house=round(per_house, 3))
    rob["R4"] = variant([s for s in stations if s["stated_km2"] <= 500], "primary")
    rob["R5"] = {}
    for y in years:
        ry = []
        for s in stations:
            if y in s["per_year"]:
                L, V = s["per_year"][y]
                ry.append(dict(s, L=L, V=V, n=1, nP=s["P"], C_ps=1000.0 * (L - s["P"]) / V))
        rob["R5"][str(y)] = variant(ry, "primary")
    rob["R6"] = {"note": "not run: no catchments were drawn for flow stations without a stated area (tools/catchments.py draws only stations with one)"}
    rob["R7"] = variant(stations, "R7")
    rob["R8"] = variant(stations, "R8")

    if not check6:
        problems.append(f"check 6: {len(stations)} stations included, needs 30 (shown as exploratory, no shares)")

    # ---- write
    os.makedirs(OUT, exist_ok=True)
    cols = ["stationId", "name", "chem", "stated_km2", "drawn_km2", "A", "clay", "n", "years", "runoff_mm", "C", "C_ps", "P",
            "outermost", "system", "excluded"]
    with open(os.path.join(OUT, "stations.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh, lineterminator="\n"); w.writerow(cols)
        for r in sorted(stations + excluded, key=lambda r: r["stationId"]):
            w.writerow([("" if r.get(k) is None else (" ".join(map(str, r[k])) if k == "years" else
                        (f"{r[k]:.4f}" if isinstance(r.get(k), float) else r[k]))) for k in cols])
    rnd = lambda o: (round(o, 6) if isinstance(o, float) else {k: rnd(v) for k, v in o.items()} if isinstance(o, dict)
                     else [rnd(v) for v in o] if isinstance(o, list) else o)
    res = {"period": years, "included": len(stations), "excluded": len(excluded),
           "excluded_by_reason": dict(sorted(Counter(re.sub(r"^\d+ valid years.*", "fewer than 4 valid years", re.sub(r"^runoff .*", "runoff outside 100–900 mm", e["excluded"])) for e in excluded).items())),
           "rows_dropped_by_filter": dropped, "check6_at_least_30": check6, "stop_rule_triggered": stop,
           "primary": prim if show_shares else {k: v for k, v in prim.items() if k in ("stations", "outermost", "b", "s", "b_ci", "s_ci", "A_range")},
           "robustness": rob if show_shares else {}, "problems": problems}
    json.dump(rnd(res), open(os.path.join(OUT, "results.json"), "w"), indent=1, sort_keys=True)
    L = ["# Results", "", "Generated by `tools/build.py`. Do not edit by hand.", "", f"Period: {y0}–{y1}.", ""]
    L += ["## Checks", ""] + (["All checks passed."] if not problems else [f"- {p}" for p in problems]) + [""]
    L += [f"Included stations: {len(stations)} (outermost: {sum(1 for s in stations if s['outermost'])}). Excluded: {len(excluded)}.", ""]
    for k, v in res["excluded_by_reason"].items():
        L.append(f"- {k}: {v}")
    L += ["", "## Relation (primary)", ""]
    if A_vals:
        L.append(f"`C_ps = b + s·A`: b = {prim['b']:.3f} mg/l (95 % {prim['b_ci'][0]:.3f}–{prim['b_ci'][1]:.3f}), "
                 f"s = {prim['s']:.3f} mg/l (95 % {prim['s_ci'][0]:.3f}–{prim['s_ci'][1]:.3f}). Farmland share range {min(A_vals):.2f}–{max(A_vals):.2f}.")
    if stop:
        L += ["", "Stop rule: the 95 % interval for s is not entirely above 0. No shares are reported."]
    elif not check6:
        L += ["", "Fewer than 30 stations: exploratory, no shares."]
    else:
        L += ["", "## Shares (outermost stations)", "",
              f"- Farmland (remainder): {100 * prim['farmland']:.1f} % (95 % {100 * prim['farmland_ci'][0]:.1f}–{100 * prim['farmland_ci'][1]:.1f})",
              f"- Background: {100 * prim['background']:.1f} % (95 % {100 * prim['background_ci'][0]:.1f}–{100 * prim['background_ci'][1]:.1f})",
              f"- Point sources: {100 * prim['point']:.1f} % (95 % {100 * prim['point_ci'][0]:.1f}–{100 * prim['point_ci'][1]:.1f})",
              "", f"**Reading: {prim['reading']}** (cited figure about 70 %; METHOD.md).", "", "## Robustness", ""]
        for k in ("R1", "R2", "R3", "R4", "R7", "R8"):
            v = rob[k]
            L.append(f"- {k}: " + (v.get("note") or f"{v['stations']} stations, b = {v['b']:.3f}, s = {v['s']:.3f}, farmland {100 * v['farmland']:.1f} %"
                                    + (f", background on sand {v['b_sand']:.3f} and on clay {v['b_clay']:.3f} mg/l" if k == "R8" else "")))
        L.append("- R5: " + "; ".join(f"{y}: " + (v.get("note") or f"farmland {100 * v['farmland']:.1f} %") for y, v in rob["R5"].items()))
        L.append(f"- R6: {rob['R6']['note']}")
    open(os.path.join(OUT, "summary.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
    print("\n".join(L))
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
