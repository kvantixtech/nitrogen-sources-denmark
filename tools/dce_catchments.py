#!/usr/bin/env python3
"""One DCE station catchment per candidate flow station, for the rerun fixed in CHANGELOG.md (5 and 9 October 2026).

Source: data/dce/tot_opl_kemi_2026.* (DCE, Aarhus University; catchments of the chemistry stations, ETRS89 / UTM 32N),
received 5 October 2026, committed unchanged.

For every candidate in data/catchments/summary.csv:
  1. the polygon whose St is the chemistry station paired with the candidate in results/stations.csv (rule in METHOD.md);
     if there is none, the polygon numbered as the flow station, then its oldStationNumber in VanDa
  2. accepted if its area is within ±10 % of the stated area AND the flow station's point lies within 500 m of it

Reads only station numbers, positions and areas: no nitrogen value, no flow value.

    python3 tools/dce_catchments.py
Writes data/catchments_dce/{catchments.geojson, summary.csv} and adds them, and the source files, to data/manifest.json.
"""
import csv, hashlib, json, os, time
import shapefile                                   # pyshp
from shapely.geometry import shape, mapping, Point

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "data", "dce", "tot_opl_kemi_2026")
OUT = os.path.join(ROOT, "data", "catchments_dce")
MAX_DIST_M = 500.0
AREA_TOL = 0.10


def rnd(o):
    if isinstance(o, float):
        return round(o, 1)
    if isinstance(o, (list, tuple)):
        return [rnd(v) for v in o]
    return o


def main():
    sf = shapefile.Reader(SRC, encoding="utf-8")
    fields = [f[0] for f in sf.fields[1:]]
    polys = {}
    for sr in sf.iterShapeRecords():
        st = int(dict(zip(fields, sr.record))["St"])
        if st in polys:
            raise SystemExit(f"station {st} appears twice in the DCE file")
        polys[st] = shape(sr.shape.__geo_interface__)
    print(f"{len(polys)} DCE polygons", flush=True)

    cand = list(csv.DictReader(open(os.path.join(ROOT, "data", "catchments", "summary.csv"), encoding="utf-8")))
    paired = {r["stationId"]: r["chem"] for r in csv.DictReader(open(os.path.join(ROOT, "results", "stations.csv"), encoding="utf-8"))}
    vandah = {s["stationId"]: s for s in json.load(open(os.path.join(ROOT, "data", "raw", "vandah_stations.json"), encoding="utf-8"))}

    rows, feats = [], []
    for c in sorted(cand, key=lambda r: r["stationId"]):
        sid = c["stationId"]
        old = (vandah.get(sid) or {}).get("oldStationNumber") or ""
        chem = paired.get(sid) or ""
        st, via = None, ""
        for key, label in ((chem, "chemistry station"), (sid, "flow station"), (old, "old flow station number")):
            if key and key.isdigit() and int(key) in polys:
                st, via = int(key), label
                break
        stated = float(c["stated_km2"])
        row = {"stationId": sid, "name": c["name"], "x": c["x"], "y": c["y"], "stated_km2": c["stated_km2"], "paired_chem": chem,
               "dce_St": st if st is not None else "", "matched_via": via, "drawn_km2": "", "ratio": "", "dist_m": "",
               "accepted": False, "reason": ""}
        if st is None:
            row["reason"] = "no DCE polygon"
        else:
            g = polys[st]
            area = g.area / 1e6
            dist = g.distance(Point(float(c["x"]), float(c["y"])))
            ratio = area / stated
            ok_area = abs(ratio - 1) <= AREA_TOL
            ok_dist = dist <= MAX_DIST_M
            row.update(drawn_km2=f"{area:.3f}", ratio=f"{ratio:.4f}", dist_m=f"{dist:.0f}", accepted=ok_area and ok_dist,
                       reason="" if ok_area and ok_dist else ("area not within ±10 % of stated area" if not ok_area else "flow station more than 500 m from the polygon"))
            gm = mapping(g)
            feats.append({"type": "Feature", "properties": {"stationId": sid, "dce_St": st, "drawn_km2": round(area, 3), "stated_km2": stated,
                                                            "accepted": row["accepted"]},
                          "geometry": {"type": gm["type"], "coordinates": rnd(gm["coordinates"])}})
        rows.append(row)

    os.makedirs(OUT, exist_ok=True)
    json.dump({"type": "FeatureCollection", "crs": {"type": "name", "properties": {"name": "EPSG:25832"}},
               "source": "DCE – Danish Centre for Environment and Energy, Aarhus University: tot_opl_kemi_2026 (received 5 October 2026)",
               "features": feats}, open(os.path.join(OUT, "catchments.geojson"), "w"), separators=(",", ":"))
    with open(os.path.join(OUT, "summary.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()), lineterminator="\n"); w.writeheader(); w.writerows(rows)

    acc = sum(1 for r in rows if r["accepted"])
    print(f"{len(rows)} candidates, {len(feats)} with a DCE polygon, {acc} accepted", flush=True)
    for reason in sorted({r["reason"] for r in rows if r["reason"]}):
        print(f"  {reason}: {sum(1 for r in rows if r['reason'] == reason)}")

    man_path = os.path.join(ROOT, "data", "manifest.json")
    man = json.load(open(man_path, encoding="utf-8"))
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for f in sorted(os.listdir(os.path.dirname(SRC))):
        p = os.path.join(os.path.dirname(SRC), f)
        man["files"]["dce/" + f] = {"sha256": hashlib.sha256(open(p, "rb").read()).hexdigest(), "bytes": os.path.getsize(p),
                                    "what": "DCE station catchments (tot_opl_kemi_2026), as received 5 October 2026; see CHANGELOG.md 9 October"}
    for f, what in (("catchments.geojson", "The DCE polygon used for each candidate, with acceptance (CHANGELOG.md 5 October)"),
                    ("summary.csv", "Per candidate: paired chemistry station, DCE polygon, area ratio, distance, acceptance")):
        p = os.path.join(OUT, f)
        man["files"]["catchments_dce/" + f] = {"sha256": hashlib.sha256(open(p, "rb").read()).hexdigest(), "bytes": os.path.getsize(p),
                                               "what": what, "made_utc": now}
    json.dump(man, open(man_path, "w", encoding="utf-8"), indent=1, ensure_ascii=False); open(man_path, "a").write("\n")


if __name__ == "__main__":
    main()
