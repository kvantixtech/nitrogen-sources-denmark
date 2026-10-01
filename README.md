# How much of the nitrogen in Danish streams comes from farmland?

A check of the usually cited split for nitrogen reaching Danish coastal waters: about 70 % human-caused diffuse (mostly farming), 20 % background, 10 % point sources. The check uses open measurements only.

The method was written and committed before any data was read: [`METHOD.md`](METHOD.md). Every change after that, and why, is in [`CHANGELOG.md`](CHANGELOG.md).

## Result (period 2017–2021)

Full numbers are in [`results/summary.md`](results/summary.md), with one row per station in [`results/stations.csv`](results/stations.csv).

**Stations**
- 46 stations with measured flow and nitrogen pass every rule.
- 151 candidates were excluded. The reasons are listed in the summary.

**Relation**
- Total nitrogen rises with the share of the catchment that is farmland. The slope is 6.1 mg/l from no farmland to all farmland (95 % interval 1.1–10.3).
- The stop rule therefore does not apply.

**Shares**
- At the outermost stations, farmland as the remainder comes out at 75.6 % of the nitrogen. Background is 18.5 % and point sources 5.9 %.
- The 95 % interval for the farmland share runs from 4 % to 137 %.

**Pre-registered reading: Inconclusive.** The interval is far too wide to agree or disagree with the cited 70 %.

**Why the result is so uncertain**
- The stations span farmland shares of only 41–84 %, so the background at 0 % is a long extrapolation.
- Only 83 of 197 catchments drawn from the elevation model matched their stated area within ±10 %, and large rivers fail most often.

## Data

| Folder | Content |
|---|---|
| `data/raw/` | The total-nitrogen rows of VanDa "Vandkemi Vandløb" (CC0), cut unchanged from a download that needs a login, and the VanDa station list. SHA-256 for both is in `data/manifest.json` |
| `data/flow/` | Daily discharge from the open VanDa API, with the SHA-256 of every download |
| `data/catchments/` | Catchments drawn from Danmarks Højdemodel (Dataforsyningen) |
| `data/landuse/` | Field blocks (Landbrugsstyrelsen), Jordbundskort 2024 and the 2024 point sources (Miljøministeriet MiljøGIS) |

## Check it yourself

    pip install numpy shapely
    python3 tools/build.py

CI reruns this on every push and fails if any result changes or a data file no longer matches its hash.

Kvantix · CVR 46296036 · MIT licence for code. The data keeps its source licences.
