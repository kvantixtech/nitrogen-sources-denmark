# Changelog

Changes to the method are written here, with the reason, before they take effect.

## 2026-10-01

- `METHOD.md` written and committed before any nitrogen data, flow series or catchment was downloaded.

## 2026-10-01, evening: chemistry file downloaded, not yet read

- **The file.** Kvantix downloaded the "Vandkemi Vandløb" CSV by hand, logged in to Danmarks Miljøportal. It is about 1.2 GB. The download link only works with a personal login session, even with the site's public client id; that was checked from GitHub Actions.
- **Values seen before the parameter code was fixed.** Before the file was uploaded, it was opened once in Excel. A screenshot of about 30 rows was shared in the working chat, and two of those rows were total-nitrogen results. No values were read beyond those rows. The period is chosen from flow data only and the stations from metadata only, so those two values cannot steer either choice. This is recorded here so the order of work stays visible.
- **Next.** `tools/inventory.py` lists the column names and counts the metadata values (parameter, unit, fraction, quality marks). It never prints a measured result. Its output fixes the parameter code and the rejection flags, which are written here before any value is extracted.
