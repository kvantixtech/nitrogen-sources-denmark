"""Temporary probe: size and resolution of VanDa water-flow series, csv vs json. No nitrogen data involved."""
import json, time, urllib.request
UA = "kvantixtech nitrogen-sources-denmark (github actions)"
out = {"run_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "tries": {}}
B = "https://vandah.miljoeportal.dk/api/water-flows?stationId={s}&from={y}-01-01T00:00Z&to={y1}-01-01T00:00Z&format={f}"
for s, y in [("19000467", 2020), ("21006853", 2023), ("42001223", 2022), ("21006853", 2024), ("19000467", 2012)]:
    for f in ("json", "csv"):
        t = time.time()
        try:
            with urllib.request.urlopen(urllib.request.Request(B.format(s=s, y=y, y1=y + 1, f=f), headers={"User-Agent": UA}), timeout=300) as r:
                b = r.read(); ct = r.headers.get("Content-Type")
        except Exception as e:
            out["tries"][f"{s}_{y}_{f}"] = str(e)[:200]; continue
        info = {"bytes": len(b), "type": ct, "seconds": round(time.time() - t, 1)}
        if f == "csv":
            lines = b.decode("utf-8", "replace").splitlines(); info["lines"] = len(lines); info["head"] = lines[:3]
        else:
            d = json.loads(b); res = d[0]["results"] if d else []
            info["points"] = len(res); info["first"] = res[0]["measurementDateTime"] if res else None; info["last"] = res[-1]["measurementDateTime"] if res else None
            info["days"] = len({r["measurementDateTime"][:10] for r in res})
        out["tries"][f"{s}_{y}_{f}"] = info
json.dump(out, open("probe/result.json", "w"), indent=1)
print("done")
