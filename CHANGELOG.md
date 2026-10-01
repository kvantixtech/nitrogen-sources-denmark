# Changelog

Changes to the method are written here, with the reason, before they take effect.

## 2026-10-01

- `METHOD.md` written and committed before any nitrogen data, flow series or catchment was downloaded.

## 2026-10-01, evening: chemistry file downloaded, not yet read

- **The file.** Kvantix downloaded the "Vandkemi Vandløb" CSV by hand, logged in to Danmarks Miljøportal. It is about 1.2 GB. The download link only works with a personal login session, even with the site's public client id; that was checked from GitHub Actions.
- **Values seen before the parameter code was fixed.** Before the file was uploaded, it was opened once in Excel. A screenshot of about 30 rows was shared in the working chat, and two of those rows were total-nitrogen results. No values were read beyond those rows. The period is chosen from flow data only and the stations from metadata only, so those two values cannot steer either choice. This is recorded here so the order of work stays visible.
- **Next.** `tools/inventory.py` lists the column names and counts the metadata values (parameter, unit, fraction, quality marks). It never prints a measured result. Its output fixes the parameter code and the rejection flags, which are written here before any value is extracted.

## 2026-10-01, evening: parameter and filters fixed from the inventory (no values read)

`tools/inventory.py` (sha256 `3a71fea8…`) was run on the downloaded file:
- sha256 `ec97684fe27c1ceb86b4bbb200940634836a2db8b5abb0d2e38459720987c1e3`, 1,269,582,881 bytes, 2,667,506 records, 35 columns
- delimiter `;`, UTF-8 with BOM.

Fixed now, before any value is extracted:

- **Parameter.** `Stofparameter` = `Nitrogen,total N` (331,527 rows, all in mg/l). Its `ScKode` is recorded by `tools/extract_tn.py`.
- **Fraction.** `Analysefraktion` `Total` or `Ej oplyst` (not stated). Total nitrogen is a total by definition, and older rows often leave the fraction blank. The 349 rows marked as dissolved (`Opløst …`) are left out.
- **Sample type.** `Prøvetype` `Enkeltprøve` (single samples) only. The method interpolates between points in time. Pooled samples (`Puljet prøve …`, 13,825 rows) cover a stretch of time that the file does not state, so they cannot be placed on the timeline.
- **Quality mark.** `Kvalitetsmærke` 2 or 3. In Miljøstyrelsen's technical instruction for marine chemistry (DTA DM01), KS1 means "loaded via StanLab". KS2 means "passed the analysis quality control and the KS2 rules of the subject", and only KS2 or higher may be used for reporting. KS3 means approved by the topic centre after its own check. KS1 rows (1,198 rows) are left out. This replaces "flags that mean rejected" in METHOD.md: the file has no rejection flag, only these three levels.
- **Detection limit.** If `Resultat-attribut` is `<`, the result is taken as half the number given, as METHOD.md says. Rows with `>` are left out. The counts of each attribute are recorded by the extract step.
- **What goes in the repository.** Every row with the parameter above, unchanged, whatever its fraction, sample type or quality mark, as `data/raw/vandkemi_tn.csv.xz`, cut by `tools/extract_tn.py`. The filters above are applied in `tools/build.py`, so anyone can see what was left out. This is wider than "the candidate stations" in METHOD.md. Nothing is lost by keeping more, and the station pairing then happens in code that CI runs.

## 2026-10-01, evening: extract added (no values read)

- `data/raw/vandkemi_tn.csv.xz` holds 331,527 rows, all `Nitrogen,total N`, ScKode 253, unit mg/l, medium Vandløb. Its SHA-256 is in `data/manifest.json`.
- **`Resultat-attribut` in these rows:**

  | Value | Rows |
  |---|---|
  | `=` (written with a leading no-break space) | 329,128 |
  | empty | 2,369 |
  | `<` | 28 |
  | `<=` | 1 |
  | `>` | 1 |

- **Rule added before any value is read.** Leading and trailing spaces, including no-break spaces, are stripped. An empty attribute counts as `=`. `<=` is treated like `<`, so the value is half the number given.
- **Rows that pass the filters fixed above:** 316,446, counted on metadata only.
- **Cut confirmed on the server.**
  - `tools/extract_tn.py` read a source whose SHA-256 is the same as in the inventory.
  - The source has 2,667,507 lines and 2,667,507 CSV records (header included), so every record is one line and the byte-for-byte cut is safe.
  - The extract's SHA-256 on the server equals the one in this repository.
  - The script's per-year count was wrong, because the date field also holds a time, and it is not used. Years are counted by `tools/build.py`.
  - `Delprøve` (sub-sample) runs from 1 to 16. Several samples at one station on one date are averaged, as METHOD.md says.
