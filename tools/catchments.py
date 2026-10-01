#!/usr/bin/env python3
"""Draw the catchment of every candidate flow station from the national elevation model.

As fixed in CHANGELOG.md (2026-10-01, "catchments and a soil check"):
  - candidates: VanDa flow stations (examination type 27) with a stated catchment area and a
    total-nitrogen chemistry station with the same number or within 500 m
    (chemistry station positions are the coordinates in data/raw/vandkemi_tn.csv.xz)
  - elevation: Danmarks Højdemodel, terrain (dhm_terraen), Dataforsyningen WCS dhm_wcs_DAF, 25 m
  - depressions filled, flats resolved, D8 flow directions
  - the station is moved to the cell with the largest upstream area within 200 m
  - catchment = every cell that drains to that cell
  - accepted if the drawn area is within ±10 % of the stated area

Reads only station metadata. Never reads a nitrogen value.

    DATAFORSYNINGEN_TOKEN=... python3 tools/catchments.py
Writes data/raw/vandah_stations.json, data/catchments/{catchments.geojson,summary.csv,tiles.json}.
"""
import csv, hashlib, io, json, lzma, math, os, re, sys, time, urllib.request, urllib.error
import numpy as np
if not hasattr(np, "in1d"):          # pysheds 0.5 still calls np.in1d, removed in NumPy 2.4
    np.in1d = lambda a, b, **k: np.isin(a, b, **k)
import rasterio
from rasterio.transform import from_origin
from rasterio import features
from shapely.geometry import shape, mapping
from shapely.ops import unary_union
from pysheds.grid import Grid

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TOKEN = os.environ.get("DATAFORSYNINGEN_TOKEN", "")
UA = "kvantixtech nitrogen-sources-denmark (github actions; validation@kvantix.tech)"
RES = 25.0
X0, Y0, X1, Y1 = 441000.0, 6049000.0, 894000.0, 6403000.0   # coverage envelope, EPSG:25832
TILE = 2000                                                 # cells per tile side = 50 km
SNAP_M = 200.0
TOL = 0.10
CACHE = os.environ.get("KVX_TILE_CACHE", "/tmp/kvx-dem-tiles")
OUT = os.path.join(ROOT, "data", "catchments")
os.makedirs(CACHE, exist_ok=True); os.makedirs(OUT, exist_ok=True)
DIRMAP = (64, 128, 1, 2, 4, 8, 16, 32)


def http(url, timeout=300):
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json, */*"}), timeout=timeout) as r:
                return r.read()
        except (urllib.error.URLError, TimeoutError) as e:
            if attempt == 3:
                raise RuntimeError(str(e).replace(TOKEN, "<TOKEN>") if TOKEN else str(e))
            time.sleep(10 * (attempt + 1))


# ------------------------------------------------------------------ stations
def stations():
    raw = http("https://vandah.miljoeportal.dk/api/stations?format=json")
    open(os.path.join(ROOT, "data", "raw", "vandah_stations.json"), "wb").write(raw)
    flow = []
    for s in json.loads(raw):
        if not any(e.get("examinationTypeSc") == 27 for mp in (s.get("measurementPoints") or []) for e in (mp.get("examinations") or [])):
            continue
        area, src = s.get("catchmentAreaKm2"), "catchmentAreaKm2"
        if area is None:
            m = re.search(r"Opland\s*=\s*([\d.,]+)\s*km", s.get("description") or "", re.I)
            area, src = (float(m.group(1).replace(".", "").replace(",", ".")), "description") if m else (None, None)
        loc = s.get("location") or {}
        if str(loc.get("srid")) != "25832":
            continue
        flow.append({"stationId": s["stationId"], "name": s.get("name"), "x": loc["x"], "y": loc["y"], "stated_km2": area, "area_source": src})
    return flow


def chem_positions():
    f = lzma.open(os.path.join(ROOT, "data", "raw", "vandkemi_tn.csv.xz"), "rt", encoding="utf-8-sig", newline="")
    r = csv.reader(f, delimiter=";"); h = next(r); c = {k: i for i, k in enumerate(h)}
    pos = {}
    for row in r:
        sid = row[c["StedID"]]
        if sid in pos or row[c["GeoZone"]] != "32":
            continue
        try:
            pos[sid] = (float(row[c["x-koordinat"]].replace(",", ".")), float(row[c["y-koordinat"]].replace(",", ".")))
        except ValueError:
            pass
    return pos


# ------------------------------------------------------------------ elevation tiles
tiles_used = {}


def tile(i, j):
    path = os.path.join(CACHE, f"t_{i}_{j}.tif")
    x0, y1 = X0 + i * TILE * RES, Y1 - j * TILE * RES
    x1, y0 = x0 + TILE * RES, y1 - TILE * RES
    req = (f"https://api.dataforsyningen.dk/dhm_wcs_DAF?service=WCS&version=1.0.0&request=GetCoverage&coverage=dhm_terraen"
           f"&crs=EPSG:25832&bbox={x0:.0f},{y0:.0f},{x1:.0f},{y1:.0f}&width={TILE}&height={TILE}&format=GTiff")
    if not os.path.exists(path):
        b = http(req + "&token=" + TOKEN)
        if not b[:4] in (b"II*\x00", b"MM\x00*"):
            raise RuntimeError(f"tile {i},{j}: not a GeoTIFF: {b[:200]!r}")
        open(path, "wb").write(b)
    with rasterio.open(path) as src:
        a = src.read(1).astype("float32")
        nod = src.nodata
    if nod is not None:
        a[a == nod] = np.nan
    a[(a < -50) | (a > 300)] = np.nan
    tiles_used[f"{i}_{j}"] = {"request": req, "sha256": hashlib.sha256(open(path, "rb").read()).hexdigest()}
    return a


def window(x, y, half):
    """Mosaic of 25 m elevation, aligned to the tile grid, covering x±half, y±half."""
    cx0 = max(0, int((x - half - X0) // RES)); cx1 = min(int((X1 - X0) // RES), int(math.ceil((x + half - X0) / RES)))
    cy0 = max(0, int((Y1 - (y + half)) // RES)); cy1 = min(int((Y1 - Y0) // RES), int(math.ceil((Y1 - (y - half)) / RES)))
    arr = np.full((cy1 - cy0, cx1 - cx0), np.nan, dtype="float32")
    for i in range(cx0 // TILE, (cx1 - 1) // TILE + 1):
        for j in range(cy0 // TILE, (cy1 - 1) // TILE + 1):
            t = tile(i, j)
            gx0, gy0 = i * TILE, j * TILE
            sx0, sx1 = max(cx0, gx0), min(cx1, gx0 + TILE)
            sy0, sy1 = max(cy0, gy0), min(cy1, gy0 + TILE)
            arr[sy0 - cy0:sy1 - cy0, sx0 - cx0:sx1 - cx0] = t[sy0 - gy0:sy1 - gy0, sx0 - gx0:sx1 - gx0]
    return arr, from_origin(X0 + cx0 * RES, Y1 - cy0 * RES, RES, RES)


# ------------------------------------------------------------------ one catchment
def delineate(x, y, stated):
    half = 1200.0 * math.sqrt(max(stated, 1.0)) + 3000.0
    for attempt in range(1, 5):
        arr, aff = window(x, y, half)
        sea = np.isnan(arr)
        dem = np.where(sea, -100.0, arr).astype("float64")     # sea and missing cells drain out of the window
        path = os.path.join(CACHE, "win.tif")
        with rasterio.open(path, "w", driver="GTiff", height=dem.shape[0], width=dem.shape[1], count=1, dtype="float64",
                           crs="EPSG:25832", transform=aff, nodata=-9999.0) as dst:
            dst.write(dem, 1)
        grid = Grid.from_raster(path)
        d = grid.read_raster(path)
        d = grid.resolve_flats(grid.fill_depressions(grid.fill_pits(d)))
        fdir = grid.flowdir(d, dirmap=DIRMAP)
        acc = np.asarray(grid.accumulation(fdir, dirmap=DIRMAP))
        assert tuple(grid.affine)[:6] == tuple(aff)[:6] and acc.shape == arr.shape, "grid and window do not line up"
        col, row = ~aff * (x, y); col, row = int(col), int(row)
        k = int(math.ceil(SNAP_M / RES))
        best, bi, bj = -1, row, col
        for di in range(-k, k + 1):
            for dj in range(-k, k + 1):
                ii, jj = row + di, col + dj
                if 0 <= ii < acc.shape[0] and 0 <= jj < acc.shape[1] and math.hypot(di * RES, dj * RES) <= SNAP_M and not sea[ii, jj]:
                    if acc[ii, jj] > best:
                        best, bi, bj = acc[ii, jj], ii, jj
        px, py = aff * (bj + 0.5, bi + 0.5)
        mask = np.asarray(grid.catchment(x=bj, y=bi, fdir=fdir, dirmap=DIRMAP, xytype="index")).astype(bool)
        m = 3                                                  # pysheds leaves the outermost cells without a direction
        edge = bool(mask[:m, :].any() or mask[-m:, :].any() or mask[:, :m].any() or mask[:, -m:].any())
        if not edge or half >= 120000:
            break
        half = min(half * 1.6, 120000.0)
    polys = [shape(g) for g, v in features.shapes(mask.astype("uint8"), mask=mask, transform=aff) if v == 1]
    geom = unary_union(polys).simplify(RES / 2, preserve_topology=True)
    return {"drawn_km2": round(mask.sum() * RES * RES / 1e6, 3), "snap_m": round(math.hypot(px - x, py - y)),
            "outlet_x": round(px, 1), "outlet_y": round(py, 1), "attempts": attempt, "window_km": round(2 * half / 1000, 1),
            "touches_window_edge": edge}, geom


def main():
    if not TOKEN:
        sys.exit("DATAFORSYNINGEN_TOKEN is not set")
    flow = stations()
    chem = chem_positions()
    cands = []
    for f in flow:
        if not f["stated_km2"]:
            continue
        near = sorted((round(math.hypot(cx - f["x"], cy - f["y"])), sid) for sid, (cx, cy) in chem.items()
                      if sid == f["stationId"] or math.hypot(cx - f["x"], cy - f["y"]) <= 500)
        if near:
            cands.append(dict(f, chem_nearby=";".join(f"{sid}@{d}m" for d, sid in near)))
    cands.sort(key=lambda c: c["stationId"])
    print(f"flow stations {len(flow)}, with stated area {sum(1 for f in flow if f['stated_km2'])}, candidates {len(cands)}", flush=True)
    feats, rows = [], []
    for n, c in enumerate(cands, 1):
        t0 = time.time()
        try:
            res, geom = delineate(c["x"], c["y"], c["stated_km2"])
            ratio = res["drawn_km2"] / c["stated_km2"]
            res.update(ratio=round(ratio, 4), accepted=abs(ratio - 1) <= TOL and not res["touches_window_edge"], error="")
        except Exception as e:
            res, geom = {"drawn_km2": None, "ratio": None, "accepted": False, "error": str(e)[:200]}, None
        row = {k: c[k] for k in ("stationId", "name", "x", "y", "stated_km2", "area_source", "chem_nearby")}
        row.update(res); rows.append(row)
        if geom is not None:
            feats.append({"type": "Feature", "properties": {"stationId": c["stationId"], "drawn_km2": res["drawn_km2"],
                                                           "stated_km2": c["stated_km2"], "accepted": res["accepted"]},
                          "geometry": mapping(geom)})
        print(f"[{n}/{len(cands)}] {c['stationId']} stated {c['stated_km2']} drawn {res.get('drawn_km2')} "
              f"ok={res['accepted']} {time.time() - t0:.0f}s {res.get('error', '')}", flush=True)
    fields = ["stationId", "name", "x", "y", "stated_km2", "area_source", "chem_nearby", "drawn_km2", "ratio", "accepted",
              "snap_m", "outlet_x", "outlet_y", "attempts", "window_km", "touches_window_edge", "error"]
    with open(os.path.join(OUT, "summary.csv"), "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=fields, extrasaction="ignore"); w.writeheader(); w.writerows(rows)
    json.dump({"type": "FeatureCollection", "crs": {"type": "name", "properties": {"name": "EPSG:25832"}}, "features": feats},
              open(os.path.join(OUT, "catchments.geojson"), "w"), separators=(",", ":"))
    json.dump({"resolution_m": RES, "coverage": "dhm_terraen", "service": "Dataforsyningen dhm_wcs_DAF (token not stored)",
               "tiles": dict(sorted(tiles_used.items()))}, open(os.path.join(OUT, "tiles.json"), "w"), indent=1)
    man_path = os.path.join(ROOT, "data", "manifest.json")
    man = json.load(open(man_path, encoding="utf-8"))
    for rel, what in (("raw/vandah_stations.json", "VanDa hydrometry API, GET /api/stations?format=json (open)"),
                      ("catchments/catchments.geojson", "Catchments drawn by tools/catchments.py, EPSG:25832"),
                      ("catchments/summary.csv", "One row per candidate flow station: stated and drawn area, accepted or not"),
                      ("catchments/tiles.json", "Elevation tiles used, with the request (no token) and SHA-256 of each")):
        p = os.path.join(ROOT, "data", rel)
        man["files"][rel.split("/", 1)[1] if rel.startswith("raw/") else rel] = {
            "sha256": hashlib.sha256(open(p, "rb").read()).hexdigest(), "bytes": os.path.getsize(p), "what": what,
            "made_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    json.dump(man, open(man_path, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    open(man_path, "a").write("\n")
    acc = sum(1 for r in rows if r["accepted"])
    print(f"accepted {acc} of {len(rows)}")


if __name__ == "__main__":
    main()
