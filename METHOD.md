# Method: how much of the nitrogen in Danish streams comes from farmland?

Written before any nitrogen measurement, flow series or catchment was downloaded. Before writing it, only these things were checked: that the sources exist, what they need for access, and their field names and record counts. Changes are listed in `CHANGELOG.md`, with the reason, before they take effect. A change made after results exist is marked as such, and the original result stays published next to it.

## Question

Across Danish streams where both flow and nitrogen are measured, how much does the total-nitrogen concentration rise with the share of the catchment that is farmland? From that relation follow:

1. **Background:** the concentration in a catchment with no farmland.
2. **Shares:** how much of the nitrogen carried past the stations is background, how much comes from treatment plants and sewer outlets, and how much is left over and attributed to farmland.
3. **Comparison:** whether that farmland share agrees with the split usually cited for Denmark.

This checks a published figure against open measurements. It is not advice, and it is not a verdict on farming, on any farm or on any municipality.

## The figure being checked

Two sources give the split usually cited for nitrogen reaching Danish coastal waters:

- **Svendsen, Windolf & Ellermann (2012)**, *Tilførsel af næringsstoffer og organiske stoffer*, DCE note for the Marine Strategy (havstrateginotat 2.8), table 5a, covering 2010. Of 55,200 t N: background 20.6 %, diffuse human-caused 69.5 %, point sources 10.0 % (5.6 % via streams, 4.4 % direct). The text says the human-caused diffuse part is "especially the contribution from farming". <https://dce.au.dk/fileadmin/dce.au.dk/Udgivelser/Havstrateginotater/2-8_MSFD_notat_tilfoersel_NPO.pdf>
- **Miljøministeriet (2022–23)**, *Udledning af kvælstof til kystvand opdelt på kilder*, sent to Folketinget (MOF alm. del, bilag 121, 2022–23). DANVA quotes it as farming 69.6 %, background 22.1 % and treatment plants 4.8 %, with rain-dependent outlets and houses outside the sewer making up the rest. <https://www.ft.dk/samling/20222/almdel/MOF/bilag/121/2657955.pdf>

**The checked figure is the human-caused diffuse share: about 70 %.**

Our farmland remainder `F` is the closest comparable quantity. Like the cited figure, it holds everything diffuse that is not background, including houses outside the sewer and nitrogen from the air that lands on farmland. The cited point-source share also includes industry and fish farms. Here, catchments with those sources are excluded instead (see "Which stations").

**Pre-registered reading** of the farmland share `ΣF/ΣL` from Analysis 3, with its 95 % interval:

| Reading | Condition |
|---|---|
| **Higher than cited** | The whole interval is above 80 % |
| **Lower than cited** | The whole interval is below 60 % |
| **Agrees** | The point estimate is 60–80 % and the interval is no wider than 30 percentage points |
| **Inconclusive** | Anything else |

The reading is not applied if the stop rule (Analysis 2) or check 6 stops the analysis.

These are shares of nitrogen passing measuring stations, not of nitrogen reaching the sea. See "What this can't show".

## Sources

| Source | What | Access |
|---|---|---|
| **Danmarks Miljøportal, VanDa hydrometry API** (`vandah.miljoeportal.dk/api`) | Station list with stated catchment area; discharge from `water-flows` (examination type 27, l/s) | Open, no login |
| **Danmarks Miljøportal, Arealdata dataset "Vandkemi Vandløb"** (`urn:dmp:ds:vandkemi-vandloeb`) | Every stream chemistry result in VanDa: station, time, parameter, result | Licence CC0 1.0. Station positions are open via WFS `vanda-geo.miljoeportal.dk`, layer `vanda:vandkemi-vandloeb`. The results CSV requires a Danmarks Miljøportal login, so it is downloaded by hand (see "Data handling") |
| **Klimadatastyrelsen, HIP catchments** (Dataforsyningen, `hip_oplande`) | Topographic stream catchments | Free with a personal Dataforsyningen token, which never goes in the repository. The release used is written to `CHANGELOG.md` at first download |
| **Landbrugsstyrelsen, Markblokke** (`geodata.fvm.dk`, layer `Markblokke:Markblokke_<year>`) | Field blocks: land registered for farm support | Open WFS |
| **Miljøministeriet, MiljøGIS** (`wfs2-miljoegis.mim.dk`), layers `vp4basis2026:vp4_ba_26_punkt_rens_saml`, `…_punkt_rbu_saml`, `…_punkt_ferskdam_saml`, `…_punkt_ind_saml`, `…_punkt_spredt_saml`, `…_distrikter` | 2024 nitrogen (kg) from treatment plants and rain-dependent outlets; locations without amounts for fish farms, industrial outlets and houses outside the sewer; river basin districts | Open WFS, no fees or constraints stated |
| **Danmarks Statistik, table VANDUD** | National 2024 nitrogen from houses outside the sewer, used only in R3 | Open API |

The plant and outlet layers are the ones checked in [wastewater-denmark](https://github.com/kvantixtech/wastewater-denmark).

## Units

Flow `Q` is in l/s. Concentration `c` is in mg/l (equal to g/m³).

- **Daily load (kg):** `Q · 86,400 · c · 10⁻⁶`
- **Daily water (m³):** `Q · 86.4`
- **Flow-weighted concentration (mg/l):** `C = 1,000 · ΣL[kg] / ΣV[m³]`
- **Runoff (mm a year):** `ΣV / (area_km² · 1,000) / n`

## Definitions

**Stations, catchments and pairs**
- **Flow station:** a VanDa station with examination type 27. Only stations with a stated catchment area are used in the primary analysis. The area is taken from `catchmentAreaKm2`, or from "Opland = … km2" in its description.
- **Catchment:** the HIP catchment polygon containing the flow station's point, merged with every HIP catchment upstream of it. It is accepted only if its area is within ±10 % of the stated area. Stations without a stated area are used only in R6, with their catchment as drawn.
- **Station pair:** a flow station and one chemistry station that share a station number, or lie at most 500 m apart.
  - If several chemistry stations qualify, the one with the same number is used. If none has the same number, the one with the most total-nitrogen samples in the period is used, and the nearest one breaks a tie. Counting samples does not read their values.
  - The flow station's catchment is used for everything (farmland share, point sources, water). The chemistry station gives only the concentrations.

**Total nitrogen**
- **Total nitrogen:** the VanDa parameter for total nitrogen, in mg/l. At the first download, the exact parameter name and code, the unit, and the flags that mean "rejected" are written to `CHANGELOG.md`, before any value is read.
  - Values below the detection limit are set to half the limit.
  - Several samples at one station on one date are averaged.

**Daily values and valid years**
- **Days:** UTC calendar dates.
- **Daily flow:** the arithmetic mean of all discharge values on that date.
  - Missing days inside a year are filled by straight-line interpolation.
  - Missing days at the start or end of a year take the nearest value, if that value is no more than 14 days away.
  - A flow year is **valid** if at least 90 % of its days have values and no gap is longer than 14 days.
- **Daily concentration:** straight-line interpolation between samples. Before the first sample and after the last, the nearest sample is used.
  - A sample year is **valid** if it has at least 10 samples and no gap longer than 92 days. Gaps are counted between samples, and from 1 January and to 31 December.
- A **valid year** for a station is one where both its flow year and its sample year are valid.

**Farmland and point sources**
- **Farmland share `A`:** the area of the union of field blocks, clipped to the catchment, divided by the catchment area. One field-block year is used for all stations: the last year of the period.
- **Point sources `P`:** the 2024 nitrogen (kg) from treatment plants and rain-dependent outlets whose point lies inside the catchment. The open layers have amounts for 2024 only, so `P` is used for every year.
- **Concentration without point sources:** `C_ps = 1,000 · (ΣL − n·P) / ΣV`, where `n` is the number of valid years.

## Which stations and years

**The period**
- The period is five consecutive completed calendar years.
- It ends with the latest completed year in which at least 75 % of the candidate stations have a valid flow year. The candidate stations are the flow stations with a stated area and a chemistry station within 500 m in the open station layer.
- It is chosen from flow coverage and station metadata only, before any nitrogen value is read, and is written to `CHANGELOG.md`.
- If the period does not include 2024, the gap between the period and the point-source year is listed in the results.

**Included stations**
- A pair is included if it has at least 4 valid years in the period, an accepted catchment, and a catchment area of 5–3,000 km².

**Excluded stations**
- Pairs whose catchment contains a freshwater fish farm or an industrial outlet. Their nitrogen amounts are not in the open layers.
- Pairs with runoff outside 100–900 mm a year. This is a sign of a wrong catchment or a broken flow series.
- Pairs where `C_ps ≤ 0`, i.e. point sources larger than the measured load. This is a sign of a data error.
- Every exclusion is listed with its reason. The farmland share and catchment size of excluded pairs are published next to those of included pairs, so any skew from excluding is visible.

**Systems**
- A **system** is an outermost included station together with every included station upstream of it.
- All included stations are in the regression.
- Only outermost stations are summed in the shares, so no water is counted twice.

## Analyses

**Resampling.** Every interval uses the same 10,000 resamples of whole systems, drawn with replacement with seed 20261001. Stations in the same river system are not independent, so they are resampled together. Intervals are the 2.5th and 97.5th percentiles. Each resample refits Analysis 1 on all its stations and recomputes Analysis 3 on its outermost stations.

**1. The relation (primary).** Ordinary least squares, one row per included station: `C_ps = b + s·A`.
- `b` is the background concentration (at `A = 0`).
- `s` is the rise from no farmland to all farmland.
- The lowest and highest `A` among included stations are reported, so it is visible how far `b` is extrapolated.

**2. Stop rule.** Shares are reported only if the whole 95 % interval for `s` is above 0. Otherwise the relation is shown with the statement that no positive relation was found, and nothing more.

**3. Shares (outermost stations).** For each outermost station:

| Part | Formula |
|---|---|
| Background load | `B = b · ΣV / 1,000` (kg) |
| Point sources | `n·P` |
| Farmland load | `F = ΣL − n·P − B` |

- A negative `F` for a single station is kept as it is, so it lowers the sum rather than being rounded to 0.
- The shares are `ΣF/ΣL`, `ΣB/ΣL` and `Σn·P/ΣL`.

**Robustness checks** are reported next to the primary result, never instead of it:
- **R1:** one intercept per river basin district (`…_distrikter`), with a shared slope.
- **R2:** treatment plants only as point sources. Rain-dependent outlets are left in the remainder.
- **R3:** houses outside the sewer subtracted as their number in the catchment × the national 2024 average per house. The average is VANDUD "Spredt bebyggelse" nitrogen divided by the number of points in `…_punkt_spredt_saml`.
- **R4:** catchments up to 500 km² only, where lakes and in-stream removal matter less.
- **R5:** each year of the period on its own.
- **R6:** adds flow stations without a stated area, with their catchments as drawn.
- **R7:** the regression weighted by each station's mean yearly water `ΣV/n`.

## Data handling

- Every open download is saved unchanged in `data/raw/`, with its SHA-256 in `data/manifest.json`.
- The chemistry CSV needs a login, so Kvantix downloads it by hand. Its SHA-256, size and download time go in the manifest. The repository stores, unchanged, every row for the total-nitrogen parameter at the candidate chemistry stations. This is allowed under CC0.
- Tokens and logins are never stored in the repository.
- `tools/build.py` computes everything from `data/raw/` only. CI recomputes it on every change and fails if any result differs.

## Checks that must pass before results are shown

1. The period, the parameter code, the rejection flags and the HIP release are in `CHANGELOG.md` before the build first reads nitrogen values.
2. Every catchment used in the primary analysis is within ±10 % of its stated area.
3. Every included station's runoff is within 100–900 mm a year.
4. The plant and outlet layers sum to the national 2024 totals, as in wastewater-denmark.
5. No catchment is counted twice in the shares (outermost stations only).
6. At least 30 stations are included. If fewer qualify, the relation is shown as exploratory, and neither shares nor a reading are given.

## What this can't show

- **Stations, not the sea.** Nitrogen is also removed between station and coast, in lower streams, lakes and wetlands. Areas without a station drain straight to the sea. The cited split covers the whole country, so the comparison is between similar quantities, not identical ones.
- **Farmland is a remainder.** Whatever background and registered point sources don't explain lands in `F`: houses outside the sewer (except in R3), nitrogen from the air, nitrogen lost or added between outlet and station, and errors in the other parts.
- **Wrong catchments flatten the line.** Water on sandy soil can cross topographic divides underground. Errors in `A` make `s` flatter and `b` higher, which lowers the farmland share. The ±10 % area check catches only part of this.
- **Background is extrapolated.** Few Danish catchments have little farmland, and those that do are often forest, heath or town. `b` may therefore include town runoff, and the true relation may not be a straight line. The range of `A` is reported. R1 and R4 test parts of this.
- **One line for the whole country.** Background differs between clay and sand landscapes (Bøgestrand et al., DCE note 2014, *Baggrundsbelastning med total N og nitrat-N*). R1 tests regional intercepts. A soil-type split is not possible with these open data.
- **Point sources from one year,** with no removal between outlet and station. That overstates their share and understates `F`.
- **Excluding fish farms and industry removes many large catchments.** The included set may not represent the country. The comparison of included and excluded catchments shows how much.
- **Field blocks are registered land,** not a crop map. They include grassland and land outside rotation.
- **A relation across catchments is not an experiment.** Catchments with more farmland also differ in other ways.

## References

- Thodsen, H. et al. (2025). *Vand- og næringsstoftransport 2024.* DCE scientific report no. 681. <https://dce.au.dk/fileadmin/dce.au.dk/Udgivelser/Videnskabelige_rapporter_600-699/SR681.pdf>
- Bøgestrand, J., Kronvang, B., Windolf, J. & Kjeldgaard, A. (2014). *Baggrundsbelastning med total N og nitrat-N – opdatering.* DCE note. <https://dce.au.dk/fileadmin/dce.au.dk/Udgivelser/Notater_2014/Baggrundsbelastning_med_total_N_opdatering.pdf>
- Svendsen, L. M., Windolf, J. & Ellermann, T. (2012). *Tilførsel af næringsstoffer og organiske stoffer.* DCE note 2.8 for the Marine Strategy. Link under "The figure being checked".
- Miljøministeriet (2022–23). *Udledning af kvælstof til kystvand opdelt på kilder.* Folketinget, MOF alm. del bilag 121. Link under "The figure being checked".
