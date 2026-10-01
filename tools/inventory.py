#!/usr/bin/env python3
"""Inventory of the "Vandkemi Vandløb" CSV, run before any value is read.

Prints the column names and, for metadata columns only (parameter, unit, fraction,
quality, status and similar), how often each value occurs. It never prints a
column that holds measured results, coordinates or dates. Its output is what
CHANGELOG.md uses to fix the total-nitrogen parameter code and the rejection flags.

    python3 tools/inventory.py /var/lib/kvx-nitrogen/raw/vandkemi_vandloeb.csv
"""
import collections, csv, re, sys, time

path = sys.argv[1]
raw = open(path, "rb").read(200000)
enc = "utf-8-sig"
try:
    raw.decode(enc)
except UnicodeDecodeError:
    enc = "cp1252"
f = open(path, encoding=enc, newline="")
first = f.readline()
delim = ";" if first.count(";") > first.count(",") else ","
f.seek(0)
r = csv.reader(f, delimiter=delim)
head = next(r)
print("encoding", enc, "| delimiter", repr(delim), "|", len(head), "columns")
for i, h in enumerate(head):
    print(f"{i:>3}  {h}")

never = re.compile(r"result|resultat|værdi|vaerdi|value|måle?værdi|koord|^x|^y|dato|date|tid|time|link|url|navn|name|nummer|number|id$", re.I)
meta = re.compile(r"param|enhed|unit|fraktion|fraction|kval|quality|status|attribut|mærk|maerk|flag|metode|oprind|prøvetype|provetype|undersøg|unders|art$|tegn|operator|stof", re.I)
cols = [i for i, h in enumerate(head) if meta.search(h) and not never.search(h)]
print("\ncounted columns:", [head[i] for i in cols])

cnt = {i: collections.Counter() for i in cols}
combo = collections.Counter()
n, t0 = 0, time.time()
for row in r:
    n += 1
    vals = [row[i] if i < len(row) else "" for i in cols]
    for i, v in zip(cols, vals):
        cnt[i][v] += 1
    line = " | ".join(vals)
    if re.search(r"nitrogen|kvælstof|kvaelstof", line, re.I):
        combo[line] += 1
    if n % 1000000 == 0:
        print(f"... {n:,} rows, {time.time() - t0:.0f} s", file=sys.stderr)

print("\nrows", n)
for i in cols:
    print(f"\n## {head[i]} | distinct: {len(cnt[i])}")
    for v, c in cnt[i].most_common(30):
        print(f"  {c:>9}  {v}")
print("\n## every combination of the counted columns where nitrogen is named")
print("   " + " | ".join(head[i] for i in cols))
for v, c in combo.most_common(80):
    print(f"  {c:>9}  {v}")
