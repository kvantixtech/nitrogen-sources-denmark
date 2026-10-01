#!/usr/bin/env python3
"""Farmland share, clay share and point sources for every accepted catchment.

As fixed in METHOD.md and CHANGELOG.md:
  - farmland share A: area of the union of field blocks (Landbrugsstyrelsen, Markblokke_<year>, the last
    year of the period in data/flow/period.json), clipped to the catchment, divided by the catchment area
  - clay share L (R8): share of the catchment with JB numbers 5-9 in Jordbundskort 2024
  - point sources P: 2024 nitrogen (kg) from treatment plants and rain-dependent outlets inside the catchment
    (MiljøGIS vp4basis2026 punkt_rens_saml, punkt_rbu_saml); split into plants and outlets for R2
  - exclusion flags: freshwater fish farms and industrial outlets inside the catchment (locations only)
  - houses outside the sewer inside the catchment (count, for R3)
  - river basin district of the station (vp4basis2026 distrikter, for R1)

Every WFS response is fetched in tiles of at most 5 km (split further when a tile hits the page size),
features are de-duplicated by geometry, and each response's SHA-256 is listed. Reads no nitrogen value.

    python3 tools/landuse.py
Writes data/landuse/{attributes.csv, national.json, downloads.csv}.
"""
import csv, hashlib, json, os, sys, time, urllib.parse, urllib.request
from concurrent.futures import ThreadPoolExecutor
from shapely.geometry import shape, Point
from shapely.ops import unary_union
from shapely.strtree import STRtree
from shapely import wkb

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "landuse")
UA = "kvantixtech nitrogen-sources-denmark (github actions; validation@kvantix.tech)"
FVM = "https://geodata.fvm.dk/geoserver/ows"
MIM = "https://wfs2-miljoegis.mim.dk/ows"
PAGE = 5000
downloads = []


def http(url):
    for attempt in range(5):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA}), timeout=300) as r:
                return r.read()
        except Exception as e:
            if attempt == 4:
                raise
            time.sleep(10 * (attempt + 1))


def wfs_bbox(base, layer, bbox, props=None, step=10000.0):
    """All features of a layer in a bbox, in tiles of at most `step` m, split while the server has more than it returned.
    Returns {geometry hash: (geometry, properties)}."""
    x0, y0, x1, y1 = bbox
    feats, stack = {}, []
    x = x0
    while x < x1:
        y = y0
        while y < y1:
            stack.append((x, y, min(x + step, x1), min(y + step, y1))); y += step
        x += step
    while stack:
        a, b, c, d = stack.pop()
        q = {"service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeNames": layer, "srsName": "EPSG:25832",
             "bbox": f"{a:.0f},{b:.0f},{c:.0f},{d:.0f},EPSG:25832", "outputFormat": "application/json", "count": str(PAGE)}
        if props:
            q["propertyName"] = props
        url = base + "?" + urllib.parse.urlencode(q)
        raw = http(url)
        downloads.append([layer, f"{a:.0f},{b:.0f},{c:.0f},{d:.0f}", len(raw), hashlib.sha256(raw).hexdigest()])
        js = json.loads(raw)
        fs = js.get("features", [])
        matched = js.get("numberMatched")
        more = (isinstance(matched, int) and matched > len(fs)) or len(fs) >= PAGE
        if more and (c - a) > 300:
            mx, my = (a + c) / 2, (b + d) / 2
            stack += [(a, b, mx, my), (mx, b, c, my), (a, my, mx, d), (mx, my, c, d)]
            continue
        for f in fs:
            if f.get("geometry"):
                g = shape(f["geometry"])
                feats[hashlib.sha1(wkb.dumps(g)).hexdigest()] = (g, f.get("properties") or {})
    return feats


def wfs_all(base, layer, sort):
    """All features of a (small) national layer, paged with a stable sort."""
    feats, start = [], 0
    while True:
        q = {"service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeNames": layer, "srsName": "EPSG:25832",
             "outputFormat": "application/json", "count": str(PAGE), "startIndex": str(start)}
        if sort:
            q["sortBy"] = sort
        raw = http(base + "?" + urllib.parse.urlencode(q))
        downloads.append([layer, f"start={start}", len(raw), hashlib.sha256(raw).hexdigest()])
        fs = json.loads(raw).get("features", [])
        feats += [(shape(f["geometry"]), f.get("properties") or {}) for f in fs if f.get("geometry")]
        if len(fs) < PAGE:
            return feats
        start += PAGE


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def main():
    period = json.load(open(os.path.join(ROOT, "data", "flow", "period.json")))
    year = period["years"][-1]
    gj = json.load(open(os.path.join(ROOT, "data", "catchments", "catchments.geojson")))
    summ = {r["stationId"]: r for r in csv.DictReader(open(os.path.join(ROOT, "data", "catchments", "summary.csv"), encoding="utf-8"))}
    cats = [(f["properties"]["stationId"], shape(f["geometry"])) for f in gj["features"] if f["properties"]["accepted"]]
    print(f"{len(cats)} accepted catchments, field blocks {year}", flush=True)
    os.makedirs(OUT, exist_ok=True)

    # national point layers (small): plants, outlets, fish farms, industry; districts
    nat = {}
    for key, layer, sort in (("rens", "vp4basis2026:vp4_ba_26_punkt_rens_saml", "pkt_id"), ("rbu", "vp4basis2026:vp4_ba_26_punkt_rbu_saml", "pkt_id"),
                             ("ferskdam", "vp4basis2026:vp4_ba_26_punkt_ferskdam_saml", "pkt_id"), ("ind", "vp4basis2026:vp4_ba_26_punkt_ind_saml", "pkt_id"),
                             ("distr", "vp4basis2026:vp4_ba_26_distrikter", None)):
        nat[key] = wfs_all(MIM, layer, sort)
        print(f"{key}: {len(nat[key])} features", flush=True)
    hits = http(MIM + "?" + urllib.parse.urlencode({"service": "WFS", "version": "2.0.0", "request": "GetFeature",
                "typeNames": "vp4basis2026:vp4_ba_26_punkt_spredt_saml", "resultType": "hits"})).decode()
    import re
    national = {"plants_count": len(nat["rens"]), "plants_n_t": round(sum(num(p.get("udl_tn_sta")) for _, p in nat["rens"]) / 1000),
                "outlets_count": len(nat["rbu"]), "outlets_n_t": round(sum(num(p.get("udl_tn_sta")) for _, p in nat["rbu"]) / 1000),
                "fish_farms_count": len(nat["ferskdam"]), "industrial_count": len(nat["ind"]),
                "scattered_houses_count": int(re.search(r'numberMatched="(\d+)"', hits).group(1)),
                "districts": [{k: (str(v).strip() if v is not None else "") for k, v in p.items() if k != "link"} for _, p in nat["distr"]]}
    json.dump(national, open(os.path.join(OUT, "national.json"), "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print("national", {k: v for k, v in national.items() if k != "districts"}, flush=True)
    for key in ("rens", "rbu"):
        years = {str(p.get("aar")) for _, p in nat[key]}
        if years != {"2024"}:
            sys.exit(f"{key} layer is not all 2024: {years}")

    def one(item):
        sid, cat = item
        bb = cat.bounds
        area = cat.area
        blocks = wfs_bbox(FVM, f"Markblokke:Markblokke_{year}", bb, "the_geom")
        geoms = [g for g, _ in blocks.values()]
        tree = STRtree(geoms) if geoms else None
        hit = [geoms[i] for i in tree.query(cat)] if tree else []
        farm = unary_union([g.intersection(cat) for g in hit]).area if hit else 0.0
        soil = wfs_bbox(FVM, "Jordbunds_og_terraenforhold:Jordbundskort_2024", bb, step=5000.0)
        sg = [(g, int(num(p.get("JB_kode")))) for g, p in soil.values()]
        st = STRtree([g for g, _ in sg]) if sg else None
        clay = sum(sg[i][0].intersection(cat).area for i in st.query(cat) if 5 <= sg[i][1] <= 9) if st else 0.0
        soil_cov = sum(sg[i][0].intersection(cat).area for i in st.query(cat)) if st else 0.0
        spredt = wfs_bbox(MIM, "vp4basis2026:vp4_ba_26_punkt_spredt_saml", bb)
        n_spredt = sum(1 for g, _ in spredt.values() if cat.covers(g.representative_point()))
        inside = lambda key: [p for g, p in nat[key] if cat.covers(g.representative_point())]
        rens, rbu = inside("rens"), inside("rbu")
        s = summ[sid]
        pt = Point(float(s["x"]), float(s["y"]))
        distr = [p for g, p in nat["distr"] if g.covers(pt)]
        return {"stationId": sid, "catchment_km2": round(area / 1e6, 3), "field_block_year": year,
                "farmland_share": round(farm / area, 5), "clay_share": round(clay / area, 5), "soil_map_coverage": round(soil_cov / area, 4),
                "plants_n": len(rens), "plants_n_kg": round(sum(num(p.get("udl_tn_sta")) for p in rens), 1),
                "outlets_n": len(rbu), "outlets_n_kg": round(sum(num(p.get("udl_tn_sta")) for p in rbu), 1),
                "fish_farms": len(inside("ferskdam")), "industrial_outlets": len(inside("ind")), "scattered_houses": n_spredt,
                "district": json.dumps({k: (str(v).strip() if v is not None else "") for k, v in distr[0].items() if k != "link"}, ensure_ascii=False, sort_keys=True) if distr else ""}

    rows = []
    with ThreadPoolExecutor(max_workers=3) as ex:
        for n, row in enumerate(ex.map(one, cats), 1):
            rows.append(row)
            print(f"[{n}/{len(cats)}] {row['stationId']} A={row['farmland_share']} L={row['clay_share']} "
                  f"plants={row['plants_n']} outlets={row['outlets_n']} fish={row['fish_farms']} ind={row['industrial_outlets']}", flush=True)
    rows.sort(key=lambda r: r["stationId"])
    with open(os.path.join(OUT, "attributes.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
    with open(os.path.join(OUT, "downloads.csv"), "w", newline="") as fh:
        w = csv.writer(fh); w.writerow(["layer", "bbox", "bytes", "sha256"]); w.writerows(sorted(downloads))
    man_path = os.path.join(ROOT, "data", "manifest.json")
    man = json.load(open(man_path, encoding="utf-8"))
    for f, what in (("attributes.csv", "Per accepted catchment: farmland share, clay share, point sources, exclusion flags, district"),
                    ("national.json", "National totals of the point layers (check 4) and the district list"),
                    ("downloads.csv", "Every WFS response behind attributes.csv, with its SHA-256")):
        p = os.path.join(OUT, f)
        man["files"]["landuse/" + f] = {"sha256": hashlib.sha256(open(p, "rb").read()).hexdigest(), "bytes": os.path.getsize(p),
                                        "what": what, "made_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    json.dump(man, open(man_path, "w", encoding="utf-8"), indent=1, ensure_ascii=False); open(man_path, "a").write("\n")
    print("done", len(rows))


if __name__ == "__main__":
    main()
