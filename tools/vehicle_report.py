#!/usr/bin/env python3
"""Per-vehicle table: role, satisfied/timed-out Interests, ISR, delays.
usage: vehicle_report.py <log> <results_dir> <scenario> <node_map.csv> <num_rsus>
Prints vehicles with any NDN traffic; writes the full table to <results_dir>/per_vehicle.csv"""
import sys, os, re, csv
log, d, sc, nmap, nrsu = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5])
sumo = {int(r['ns3_node_index']): r['sumo_vehicle_id'] for r in csv.DictReader(open(nmap))}
roles = {}
def add(v, r): roles.setdefault(int(v), set()).add(r)
for line in open(log):
    m = re.search(r"\[RANDOM-REQUESTS\] Vehicle(\d+) requesting", line);   m and add(m.group(1), "requester")
    m = re.search(r"\[TRANSIT-FERRY\] Vehicle(\d+) loads", line);    m and add(m.group(1), "transit-carrier")
    m = re.search(r"\[VCF-FERRY\] Vehicle(\d+) loads", line);             m and add(m.group(1), "ferry")
    m = re.search(r"\[LAST-MILE-RELAY\] Vehicle(\d+) fetching", line);    m and add(m.group(1), "relay")
    m = re.search(r"\[HAZARD\] Vehicle(\d+) warned", line);          m and add(m.group(1), "hazard-warned")
    m = re.search(r"Vehicle(\d+) .*breaks down", line);                   m and add(m.group(1), "broken-down")
sat, tout = {}, {}
with open(os.path.join(d, f"{sc}_metrics_l3_rate.csv")) as f:
    h = f.readline().rstrip("\n").split("\t")
    iN, iD, iT, iP = h.index("Node"), h.index("FaceDescr"), h.index("Type"), h.index("PacketRaw")
    for line in f:
        c = line.rstrip("\n").split("\t")
        n = int(c[iN])
        if c[iD] == "internal://":   # NFD's own management Interests: not app traffic
            if c[iT] == "InSatisfiedInterests": sat[n] = sat.get(n, 0) - float(c[iP])
            elif c[iT] == "InTimedOutInterests": tout[n] = tout.get(n, 0) - float(c[iP])
            continue
        if c[iD] != "all": continue
        if c[iT] == "SatisfiedInterests": sat[n] = sat.get(n, 0) + float(c[iP])
        elif c[iT] == "TimedOutInterests": tout[n] = tout.get(n, 0) + float(c[iP])
dl = {}
with open(os.path.join(d, f"{sc}_metrics_app_delays.csv")) as f:
    h = f.readline().rstrip("\n").split("\t")
    iN, iT, iS = h.index("Node"), h.index("Type"), h.index("DelayS")
    for line in f:
        c = line.rstrip("\n").split("\t"); k = (int(c[iN]), c[iT])
        s = dl.setdefault(k, [0.0, 0]); s[0] += float(c[iS]); s[1] += 1
rows = []
for n in sorted(set(sat) | set(tout)):
    if n < nrsu: continue
    v = n - nrsu; S, T = sat.get(n, 0), tout.get(n, 0)
    if S + T < 0.5: continue
    ld, fd = dl.get((n, "LastDelay"), [0, 0]), dl.get((n, "FullDelay"), [0, 0])
    rows.append([v, sumo.get(v, "?"), "+".join(sorted(roles.get(v, {"-"}))), int(S), int(T),
                 round(100*S/(S+T), 1), round(1000*ld[0]/ld[1], 2) if ld[1] else "", round(fd[0]/fd[1], 3) if fd[1] else ""])
hdr = ["vehicle", "sumo_id", "role", "satisfied", "timed_out", "ISR_%", "LastDelay_ms", "FullDelay_s"]
with open(os.path.join(d, "per_vehicle.csv"), "w", newline="") as f:
    w = csv.writer(f); w.writerow(hdr); w.writerows(rows)
print(f"\nPer-vehicle table ({len(rows)} vehicles with NDN traffic; full table: {d}/per_vehicle.csv)")
os.environ.get("FULL_TABLE") and print(f"{'vehicle':>7} {'sumo_id':>9} {'role':>22} {'sat':>6} {'tout':>6} {'ISR%':>6} {'LastDelay_ms':>12} {'FullDelay_s':>11}")
for r in (rows if os.environ.get("FULL_TABLE") else []):
    print(f"{r[0]:>7} {r[1]:>9} {r[2]:>22} {r[3]:>6} {r[4]:>6} {r[5]:>6} {str(r[6]):>12} {str(r[7]):>11}")
by = {}
for r in rows:
    b = by.setdefault(r[2], [0, 0, 0]); b[0] += 1; b[1] += r[3]; b[2] += r[4]
print("\nBy role:")
for k, (c, S, T) in sorted(by.items()):
    print(f"  {k:>22}: {c:>3} vehicles  satisfied={S}  timed_out={T}  ISR={100*S/(S+T):.1f}%")
