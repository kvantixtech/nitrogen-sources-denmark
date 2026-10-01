#!/usr/bin/env python3
"""Cut the total-nitrogen rows out of the "Vandkemi Vandløb" CSV, unchanged.

Every line whose Stofparameter is exactly "Nitrogen,total N" is copied byte for byte,
with the header line, into an xz file. Nothing is filtered on value, fraction, sample
type or quality mark here: those rules are applied by tools/build.py, as fixed in
CHANGELOG.md. Prints counts of metadata only, never a measured result.

    python3 tools/extract_tn.py /var/lib/kvx-nitrogen/raw/vandkemi_vandloeb.csv vandkemi_tn.csv.xz
"""
import collections, csv, hashlib, io, lzma, sys

src, dst = sys.argv[1], sys.argv[2]
PARAM = "Nitrogen,total N"
h_src = hashlib.sha256()
lines = records = kept = 0
meta = {k: collections.Counter() for k in ("ScKode", "Resultat-attribut", "Analysefraktion", "Prøvetype", "Kvalitetsmærke", "Medie", "Delprøve")}
years = collections.Counter()
with open(src, "rb") as f, lzma.open(dst, "wb", preset=6) as out:
    header = f.readline(); h_src.update(header); lines += 1
    head = next(csv.reader(io.StringIO(header.decode("utf-8-sig")), delimiter=";"))
    col = {name: i for i, name in enumerate(head)}
    ip = col["Stofparameter"]
    out.write(header)
    for line in f:
        h_src.update(line); lines += 1
        if PARAM.encode() not in line:
            continue
        row = next(csv.reader(io.StringIO(line.decode("utf-8")), delimiter=";"))
        if len(row) != len(head):
            sys.exit(f"line {lines}: {len(row)} fields, expected {len(head)}; stopping so nothing is cut wrongly")
        if row[ip] != PARAM:
            continue
        out.write(line); kept += 1
        for k in meta:
            meta[k][row[col[k]]] += 1
        years[row[col["Dato"]][-4:] if "." in row[col["Dato"]] else row[col["Dato"]][:4]] += 1
# every record must be one physical line, or the byte-for-byte cut is not safe
with open(src, encoding="utf-8-sig", newline="") as f:
    records = sum(1 for _ in csv.reader(f, delimiter=";"))
print("source sha256", h_src.hexdigest())
print("source lines", lines, "| csv records", records, "| one line per record:", lines == records)
print("kept rows", kept)
print("extract sha256", hashlib.sha256(open(dst, "rb").read()).hexdigest())
for k, c in meta.items():
    print(f"\n## {k} | distinct {len(c)}")
    for v, n in c.most_common(15):
        print(f"  {n:>8}  {v}")
print("\n## rows per year")
print("  " + "  ".join(f"{y}:{n}" for y, n in sorted(years.items())))
