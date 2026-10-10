#!/usr/bin/env python3
"""Application-level delivery metrics from the AppDelayTracer CSV (FullDelay rows).

Counts every request the way the application sees it, including retries,
so failures cannot be hidden by per-hop / per-PIT-entry counting.

usage: app_metrics.py <results_dir> <scenario> <nRSU> [failures.csv]
  nRSU         : RSUs are nodes 0..nRSU-1, vehicles are nodes >= nRSU
  failures.csv : rsu_id,fail_start,fail_end  (optional; enables failure-window rows)
Requester vehicles are read from <results_dir>/per_vehicle.csv (role column):
pure requesters (not also ferry / transit carrier) ask at a constant rate, so
gaps in their sequence numbers are real losses, exactly like RSU consumers.
"""
import sys, os, csv, collections

d, sc, nrsu = sys.argv[1], sys.argv[2], int(sys.argv[3])

# ---- failures (optional) ----
fails = collections.defaultdict(list)
if len(sys.argv) > 4:
    with open(sys.argv[4]) as f:
        rd = csv.reader(f)
        next(rd)
        for r in rd:
            if len(r) < 3:
                continue
            fails[int(r[0].strip().replace("rsu", ""))].append((float(r[1]), float(r[2])))
allw = [w for ws in fails.values() for w in ws]
gw = (min(w[0] for w in allw), max(w[1] for w in allw)) if allw else None

# ---- pure requester vehicles (from per_vehicle.csv) ----
requesters = set()
pv = os.path.join(d, "per_vehicle.csv")
if os.path.exists(pv):
    with open(pv) as f:
        rd = csv.DictReader(f)
        hn = [h for h in rd.fieldnames if "node" in h.lower()]
        hv = [h for h in rd.fieldnames if h.lower() == "vehicle"]
        hr = [h for h in rd.fieldnames if "role" in h.lower()]
        if (hn or hv) and hr:
            for r in rd:
                role = r[hr[0]]
                if "requester" in role and "ferry" not in role and "transit" not in role:
                    # node id = vehicle index + number of RSUs (RSUs are nodes 0..nRSU-1)
                    nid = int(float(r[hn[0]])) if hn else int(float(r[hv[0]])) + nrsu
                    requesters.add(nid)
        else:
            print("WARNING: per_vehicle.csv has no node/role column:", rd.fieldnames)

# ---- read FullDelay rows (one per delivered request) ----
apps = collections.defaultdict(list)        # (node, appId) -> [(seq, sendT, fullDelay, tx)]
last = {}                                   # (node, appId, seq) -> LastDelay
with open(os.path.join(d, f"{sc}_metrics_app_delays.csv")) as f:
    hdr = f.readline().rstrip("\n").split("\t")
    iT, iN, iA, iS, iY, iD, iR = (hdr.index(k) for k in
        ("Time", "Node", "AppId", "SeqNo", "Type", "DelayS", "RetxCount"))
    for line in f:
        c = line.rstrip("\n").split("\t")
        key = (int(c[iN]), int(c[iA]))
        if c[iY] == "FullDelay":
            t, dl = float(c[iT]), float(c[iD])
            apps[key].append((int(c[iS]), t - dl, dl, int(c[iR])))
        elif c[iY] == "LastDelay":
            last[(key[0], key[1], int(c[iS]))] = float(c[iD])

minTx = min(r[3] for v in apps.values() for r in v)   # 1 => RetxCount counts every send

def cat_of(node, sendT):
    """Return the list of categories this request belongs to."""
    cats = ["ALL", "RSU backbone" if node < nrsu else "Vehicles"]
    if gw and gw[0] <= sendT <= gw[1]:
        cats.append(("RSU" if node < nrsu else "Veh") + " in failure window")
    if node < nrsu and any(a <= sendT <= b for a, b in fails.get(node, [])):
        cats.append("RSU on a FAILED RSU, during its outage")
    if node in requesters:
        cats.append("Requester vehicles")
        if gw and gw[0] <= sendT <= gw[1]:
            cats.append("Requesters in failure window")
    return cats

def gap_counted(k):
    return k.startswith("RSU") or k.startswith("Requester")

S = collections.defaultdict(lambda: dict(n=0, first=0, tx=0, fd=0.0, ld=0.0, nld=0, miss=0))
for (node, app), rows in apps.items():
    rows.sort()
    for seq, st, dl, tx in rows:
        for k in cat_of(node, st):
            s = S[k]
            s["n"] += 1
            s["first"] += (tx == minTx)
            s["tx"] += tx - minTx + 1
            s["fd"] += dl
            lv = last.get((node, app, seq))
            if lv is not None:
                s["ld"] += lv; s["nld"] += 1
    # never-delivered requests: gaps in the sequence of a constant-rate consumer
    if node < nrsu or node in requesters:
        for (s1, t1, *_), (s2, t2, *_) in zip(rows, rows[1:]):
            for m in range(s1 + 1, s2):
                tm = t1 + (t2 - t1) * (m - s1) / (s2 - s1)
                for k in cat_of(node, tm):
                    if gap_counted(k):
                        S[k]["miss"] += 1

order = ["ALL", "RSU backbone", "Vehicles", "RSU in failure window", "Veh in failure window",
         "RSU on a FAILED RSU, during its outage", "Requester vehicles",
         "Requesters in failure window"]
print(f"== App-level metrics: {sc}  ({d}) ==")
if gw:
    print(f"failure window: {gw[0]:.1f}-{gw[1]:.1f} s, failed RSUs: {len(fails)}")
print(f"pure requester vehicles found: {len(requesters)} {sorted(requesters)}")
print(f"(RetxCount minimum in file = {minTx}; 'first-try' = delivered with no retry)")
print(f"{'category':40s} {'delivered':>9s} {'first-try%':>10s} {'avg sends':>9s} "
      f"{'never-deliv':>11s} {'delivered%':>10s} {'LastDelay ms':>12s} {'FullDelay s':>11s}")
for k in order:
    if k not in S:
        continue
    s = S[k]
    n = s["n"]
    dv = f"{100*n/(n+s['miss']):.2f}" if gap_counted(k) else "n/a"
    ms = str(s["miss"]) if gap_counted(k) else "n/a"
    print(f"{k:40s} {n:9d} {100*s['first']/n:10.2f} {s['tx']/n:9.3f} {ms:>11s} {dv:>10s} "
          f"{1000*s['ld']/max(s['nld'],1):12.2f} {s['fd']/n:11.3f}")
