#!/usr/bin/env python3
"""Choose RSU failures by rule: a FRACTION of all RSUs fail, half as one clustered
area outage (neighbouring RSUs, near-simultaneous) and half scattered (not adjacent
to the outage or to each other). Only RSUs with vehicles nearby are chosen."""
import argparse, csv, math, random, collections
ap = argparse.ArgumentParser()
ap.add_argument("--rsulist", required=True); ap.add_argument("--candidates", required=True)
ap.add_argument("--out", required=True); ap.add_argument("--markers", default=None)
ap.add_argument("--fraction", type=float, default=0.2); ap.add_argument("--range", type=float, default=600.0)
ap.add_argument("--seed", type=int, default=42)
ap.add_argument("--t0", type=float, default=150.0, help="earliest failure start (s)")
ap.add_argument("--t1", type=float, default=450.0, help="latest failure end (s)")
ap.add_argument("--min-dur", type=float, default=80.0); ap.add_argument("--max-dur", type=float, default=150.0)
ap.add_argument("--min-veh", type=int, default=3, help="distinct vehicles in range during t0-t1")
a = ap.parse_args()

rsus = [(r["rsu_id"], float(r["x"]), float(r["y"])) for r in csv.DictReader(open(a.rsulist))]
ids = [r[0] for r in rsus]; pos = {r[0]: (r[1], r[2]) for r in rsus}
contacts = collections.defaultdict(list)
for r in csv.DictReader(open(a.candidates)):
    contacts[r["rsu_id"]].append((int(r["vehicle_node_index"]), float(r["contact_start"]), float(r["contact_end"])))
def veh_in(rid, s, e): return {v for v, cs, ce in contacts[rid] if cs <= e and ce >= s}
adj = {i: [] for i in ids}
for i in range(len(ids)):
    for j in range(i + 1, len(ids)):
        if math.dist(pos[ids[i]], pos[ids[j]]) <= a.range: adj[ids[i]].append(ids[j]); adj[ids[j]].append(ids[i])

rnd = random.Random(a.seed)
n_fail = round(a.fraction * len(ids)); n_cl = n_fail // 2; n_sc = n_fail - n_cl
busy = [r for r in ids if len(veh_in(r, a.t0, a.t1)) >= a.min_veh]
print(f"RSUs: {len(ids)}   busy (>= {a.min_veh} vehicles in {a.t0:.0f}-{a.t1:.0f} s): {len(busy)}   to fail: {n_fail} ({n_cl} area + {n_sc} scattered)")
if len(busy) < n_fail: raise SystemExit("not enough busy RSUs for this fraction")

def window(rid, start=None):
    for _ in range(100):
        d = rnd.uniform(a.min_dur, a.max_dur)
        s = start + rnd.uniform(0, 5) if start is not None else rnd.uniform(a.t0, a.t1 - d)
        e = min(s + d, a.t1)
        if veh_in(rid, s, e): return round(s, 1), round(e, 1)
    return None

cluster = []
for _ in range(200):                                 # area outage: BFS over busy RSUs
    seed = rnd.choice(busy); seen = [seed]; q = [seed]
    while q and len(seen) < n_cl:
        u = q.pop(0)
        for v in sorted(adj[u]):
            if v in busy and v not in seen and len(seen) < n_cl: seen.append(v); q.append(v)
    if len(seen) == n_cl: cluster = seen; break
if not cluster: raise SystemExit("could not find a connected busy area of that size")
T = rnd.uniform(a.t0, a.t1 - a.max_dur)
fails = []
for r in cluster:
    w = window(r, T)
    if w: fails.append((r, "area", *w))
near = set(cluster) | {v for c in cluster for v in adj[c]}
cands = [r for r in busy if r not in near]; rnd.shuffle(cands)
scat = []
for r in cands:
    if len(scat) >= n_sc: break
    if any(r in adj[s] for s in scat): continue
    w = window(r)
    if w: scat.append(r); fails.append((r, "scattered", *w))
if len(fails) < n_fail: print(f"WARNING: only {len(fails)} failures could be placed")

with open(a.out, "w", newline="") as f:
    w = csv.writer(f); w.writerow(["rsu_id", "fail_start", "fail_end"])
    for r, _, s, e in fails: w.writerow([r, s, e])
if a.markers:
    col = {r: ("0,0,255" if t == "area" else "255,140,0") for r, t, _, _ in fails}
    with open(a.markers, "w") as f:
        f.write("<additional>\n")
        for r in ids:
            x, y = pos[r]
            f.write(f'    <poi id="{r}" type="RSU" color="{col.get(r, "255,0,0")}" layer="100" x="{x:.2f}" y="{y:.2f}" width="14" height="14"/>\n')
        f.write("</additional>\n")

failed = {r for r, *_ in fails}
pairs = sum(1 for i in ids for j in adj[i] if i < j and (i in failed or j in failed))
tot = sum(len(adj[i]) for i in ids) // 2
print(f"\n{'rsu':<8}{'type':<11}{'start':>8}{'end':>8}{'len':>6}{'veh in window':>15}{'neighbours':>12}")
for r, t, s, e in sorted(fails, key=lambda x: x[2]):
    print(f"{r:<8}{t:<11}{s:>8}{e:>8}{e - s:>6.0f}{len(veh_in(r, s, e)):>15}{len(adj[r]):>12}")
print(f"\nfailed RSUs: {len(fails)}/{len(ids)} ({100 * len(fails) / len(ids):.1f}%)   "
      f"backbone links affected: {pairs}/{tot}   overall window: {min(f[2] for f in fails)}-{max(f[3] for f in fails)} s")
iso = [r for r in ids if r not in failed and adj[r] and all(v in failed for v in adj[r])]
print(f"healthy RSUs cut off from every neighbour: {len(iso)} {iso}")
print(f"written: {a.out}" + (f" and {a.markers}" if a.markers else ""))
