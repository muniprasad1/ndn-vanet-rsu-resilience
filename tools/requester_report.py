#!/usr/bin/env python3
"""Per-requester + backbone/vehicle ISR report.
usage: requester_report.py <log> <results_dir> <scenario> <node_map.csv> <num_rsus>"""
import sys, os, re, csv
log, d, sc, nmap, nrsu = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4], int(sys.argv[5])
sumo = {int(r['ns3_node_index']): r['sumo_vehicle_id'] for r in csv.DictReader(open(nmap))}
req = {}
for line in open(log):
    m = re.search(r"\[RANDOM-REQUESTS\] Vehicle(\d+) requesting (\S+) from t=([\d.]+)s to t=([\d.]+)s", line)
    if m: req[int(m.group(1))] = (m.group(2), float(m.group(3)), float(m.group(4)))
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
        c = line.rstrip("\n").split("\t")
        k = (int(c[iN]), c[iT]); s = dl.setdefault(k, [0.0, 0]); s[0] += float(c[iS]); s[1] += 1
def isr(nodes):
    S = sum(sat.get(n, 0) for n in nodes); T = sum(tout.get(n, 0) for n in nodes)
    return S, T, (100 * S / (S + T) if S + T else float('nan'))
allnodes = set(sat) | set(tout)
for name, nodes in [("RSU backbone", [n for n in allnodes if n < nrsu]), ("Vehicles", [n for n in allnodes if n >= nrsu])]:
    S, T, r = isr(nodes); print(f"{name:13s} satisfied={S:.0f} timedout={T:.0f} ISR={r:.2f}%")
print("\nPer random requester:")
print(f"{'vehicle':>8} {'sumo_id':>9} {'node':>5} {'requests':>22} {'window(s)':>14} {'sat':>6} {'tout':>6} {'ISR%':>6} {'LastDelay_ms':>12} {'FullDelay_s':>11}")
for v, (pfx, t0, t1) in sorted(req.items()):
    n = v + nrsu; S, T, r = isr([n])
    ld = dl.get((n, "LastDelay"), [0, 0]); fd = dl.get((n, "FullDelay"), [0, 0])
    print(f"{v:>8} {sumo.get(v,'?'):>9} {n:>5} {pfx:>22} {t0:>6.0f}-{t1:<6.0f} {S:>6.0f} {T:>6.0f} {r:>6.1f} "
          f"{(1000*ld[0]/ld[1] if ld[1] else float('nan')):>12.2f} {(fd[0]/fd[1] if fd[1] else float('nan')):>11.2f}")
