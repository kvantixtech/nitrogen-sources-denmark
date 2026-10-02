"""Temporary probe for a NEW project (offshore wind and coastal precipitation): metadata only.
Reads station lists, file listings, licences and wind-farm geometry. Reads NO precipitation value:
no observation, grid or reanalysis value is requested, only catalogues and directory listings."""
import json, os, re, time, urllib.request, urllib.parse

UA = "kvantixtech wind-rain metadata probe (github actions; validation@kvantix.tech)"
OUT = "probe/wind"
os.makedirs(OUT, exist_ok=True)
log = {"run_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "tries": {}}


def get(url, limit=None, method="GET"):
    req = urllib.request.Request(url, headers={"User-Agent": UA}, method=method)
    t = time.time()
    with urllib.request.urlopen(req, timeout=180) as r:
        b = r.read(limit) if limit else (r.read() if method == "GET" else b"")
        return r.status, dict(r.headers), b, round(time.time() - t, 1)


def tryit(key, url, save=None, limit=None, method="GET", keep_text=0):
    try:
        st, h, b, s = get(url, limit, method)
        info = {"url": url, "status": st, "bytes": len(b), "type": h.get("Content-Type"), "length": h.get("Content-Length"), "seconds": s}
        if save:
            open(os.path.join(OUT, save), "wb").write(b); info["saved"] = save
        if keep_text:
            info["head"] = b[:keep_text].decode("utf-8", "replace")
        log["tries"][key] = info
        return b
    except Exception as e:
        log["tries"][key] = {"url": url, "error": str(e)[:300]}
        return None


BBOX = "4.5,53.0,11.0,58.0"  # lon/lat: eastern North Sea, Denmark, NW Germany
DMI = "https://opendataapi.dmi.dk/v2"
# DMI: station catalogues only (no stationValue / gridValue requests)
tryit("dmi_climate_stations", f"{DMI}/climateData/collections/station/items?bbox={BBOX}&limit=10000", save="dmi_climate_stations.json")
tryit("dmi_metobs_stations", f"{DMI}/metObs/collections/station/items?bbox={BBOX}&limit=10000", save="dmi_metobs_stations.json")
tryit("dmi_climate_collections", f"{DMI}/climateData/collections", save="dmi_climate_collections.json")

# DWD: directory listings and station descriptions only
CDC = "https://opendata.dwd.de/climate_environment/CDC/"
for key, path in [("dwd_rr_hist", "observations_germany/climate/daily/more_precip/historical/"),
                  ("dwd_rr_recent", "observations_germany/climate/daily/more_precip/recent/"),
                  ("dwd_kl_hist", "observations_germany/climate/daily/kl/historical/"),
                  ("dwd_hyras", "grids_germany/daily/hyras_de/precipitation/"),
                  ("dwd_radklim_rw", "grids_germany/hourly/radolan/reproc/2017_002/"),
                  ("dwd_regnie", "grids_germany/daily/regnie/")]:
    b = tryit(key, CDC + path)
    if b:
        names = sorted(set(re.findall(r'href="([^"?/][^"]*)"', b.decode("utf-8", "replace"))))
        open(os.path.join(OUT, key + "_listing.txt"), "w").write("\n".join(names) + "\n")
        log["tries"][key]["entries"] = len(names)
        for n in names:
            if "Beschreibung" in n and n.endswith(".txt"):
                tryit(key + "_stations", CDC + path + n, save=key + "_stations.txt")
tryit("dwd_terms", CDC + "Terms_of_use.pdf", method="HEAD")

# Wind farms: EMODnet (CC BY 4.0), Rijkswaterstaat (CC0)
EM = "https://ows.emodnet-humanactivities.eu/wfs"
tryit("emodnet_describe", EM + "?" + urllib.parse.urlencode({"service": "WFS", "version": "2.0.0", "request": "DescribeFeatureType", "typeNames": "emodnet:windfarmspoly"}), save="emodnet_describe.xml")
for t in ("windfarmspoly", "windfarms"):
    tryit("emodnet_" + t, EM + "?" + urllib.parse.urlencode({"service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeNames": "emodnet:" + t,
                                                              "outputFormat": "application/json", "srsName": "EPSG:4326"}), save=f"emodnet_{t}.geojson")
tryit("rws_caps", "https://geo.rijkswaterstaat.nl/services/ogc/gdr/windenergiegebieden/ows?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetCapabilities", keep_text=400)

# Danish turbine register (ENS) and German MaStR: find download links only
b = tryit("ens_page", "https://ens.dk/service/statistik-data-noegletal-og-kort/data-oversigt-over-energisektoren")
if b:
    links = sorted(set(l for l in re.findall(r'href="([^"]+)"', b.decode("utf-8", "replace")) if re.search(r"(?i)xlsx?|stamdata|vind", l)))
    log["tries"]["ens_page"]["links"] = links[:40]
b = tryit("mastr_page", "https://www.marktstammdatenregister.de/MaStR/Datendownload")
if b:
    links = sorted(set(re.findall(r'https://download\.marktstammdatenregister\.de/[^"\']+', b.decode("utf-8", "replace"))))
    log["tries"]["mastr_page"]["links"] = links[:10]
    for l in links[:1]:
        tryit("mastr_head", l, method="HEAD")

# Reanalysis and radar: catalogue / metadata only
tryit("cds_era5_single", "https://cds.climate.copernicus.eu/api/catalogue/v1/collections/reanalysis-era5-single-levels", keep_text=300)
tryit("cds_era5_pressure", "https://cds.climate.copernicus.eu/api/catalogue/v1/collections/reanalysis-era5-pressure-levels", keep_text=300)
ARCO = "https://storage.googleapis.com/gcp-public-data-arco-era5/ar/"
for k, p in [("arco_v3_zarrjson", "full_37-1h-0p25deg-chunk-1.zarr-v3/zarr.json"),
             ("arco_v3_zmeta", "full_37-1h-0p25deg-chunk-1.zarr-v3/.zmetadata"),
             ("arco_v2_zmeta", "1959-2022-full_37-1h-0p25deg-chunk-1.zarr-v2/.zmetadata")]:
    b = tryit(k, ARCO + p, limit=3_000_000)
    if b:
        txt = b.decode("utf-8", "replace")
        log["tries"][k]["has_total_precipitation"] = "total_precipitation" in txt
        log["tries"][k]["has_u_component_of_wind"] = "u_component_of_wind" in txt
        m = re.findall(r'"time"[^{]*\{[^}]*"shape"\s*:\s*\[(\d+)\]', txt)
        log["tries"][k]["time_shape"] = m[:2]
tryit("opera_api", "https://api.meteogate.eu/eu-eumetnet-weather-radar", keep_text=600)
tryit("knmi_series_page", "https://www.knmi.nl/nederland-nu/klimatologie/monv/reeksen", method="HEAD")
tryit("knmi_api", "https://api.dataplatform.knmi.nl/open-data/v1/datasets", keep_text=300)
tryit("imerg_dir", "https://gpm1.gesdisc.eosdis.nasa.gov/data/GPM_L3/GPM_3IMERGDF.07/", method="HEAD")

json.dump(log, open(os.path.join(OUT, "result.json"), "w"), indent=1)
print(json.dumps({k: (v.get("status"), v.get("bytes"), v.get("error")) for k, v in log["tries"].items()}, indent=1))
