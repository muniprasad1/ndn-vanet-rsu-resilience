#!/usr/bin/env python3
"""Mean +- 95% CI over seeds.  usage: ms_aggregate.py <scenario>"""
import sys, re, glob, os, math, statistics as st, csv
sc = sys.argv[1]; pfx = sys.argv[2] if len(sys.argv) > 2 else "ms"; d = os.path.expanduser(f"~/multiseed/{sc}")
T = {1: 12.706, 2: 4.303, 3: 3.182, 4: 2.776, 5: 2.571, 6: 2.447, 7: 2.365, 8: 2.306, 9: 2.262}
ROWS = {"RSU on a FAILED RSU, during its outage": "failedRSU", "Requesters in failure window": "reqWin"}
def parse(path):
    m = {}
    for line in open(path, errors="replace"):
        if line.startswith("ISR:"): m["ISR"] = float(line.split()[1].rstrip("%"))
        for label, key in ROWS.items():
            if line.startswith(label):
                v = line[len(label):].split()
                if len(v) == 7:
                    m[key+"_first"] = float(v[1]); m[key+"_wait"] = float(v[6])
                    if v[3] != "n/a": m[key+"_never"] = float(v[3])
    return m
data = {}
for f in sorted(glob.glob(f"{d}/{pfx}_s*_*.summary.txt")):
    g = re.search(pfx + r"_s(\d+)_([A-E])\.summary\.txt$", f); m = parse(f)
    if "ISR" not in m: print(f"  (skipped, incomplete: {os.path.basename(f)})"); continue
    data.setdefault(g.group(2), []).append((int(g.group(1)), m))
COLS = [("failedRSU_first","Failed RSU first-try %"),("failedRSU_wait","Failed RSU wait s"),
        ("reqWin_first","Requesters first-try %"),("reqWin_wait","Requesters wait s"),
        ("reqWin_never","Requesters never answered"),("ISR","Network ISR %")]
def ms(vals):
    n = len(vals)
    if n == 0: return "-", None, None
    mean = st.mean(vals)
    if n == 1: return f"{mean:.2f} (n=1)", mean, 0.0
    ci = T.get(n-1, 1.96) * st.stdev(vals) / math.sqrt(n)
    return f"{mean:.2f} ± {ci:.2f}", mean, ci
print(f"\n{sc.upper()} [{pfx}]: mean ± 95% CI over seeds"); out = []
for run in "DCBAE":
    if run not in data: continue
    seeds = sorted(s for s, _ in data[run]); print(f"\nRun {run}  (seeds {seeds}, n={len(seeds)})")
    for key, name in COLS:
        vals = [m[key] for _, m in data[run] if key in m]; txt, mean, ci = ms(vals)
        print(f"  {name:28s} {txt:>18s}   per seed: {', '.join(f'{v:g}' for v in vals)}")
        out.append([sc, run, len(vals), name, mean, ci] + vals)
with open(f"{d}/{pfx}_table.csv", "w", newline="") as fo:
    w = csv.writer(fo); w.writerow(["scenario","run","n","metric","mean","ci95","values..."]); w.writerows(out)
print(f"\nwritten: {d}/{pfx}_table.csv")
