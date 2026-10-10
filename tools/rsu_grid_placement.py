#!/usr/bin/env python3
"""
rsu_grid_placement.py -- grid-coverage RSU placement for NDN-VANET ODD scenarios.
Used for URBAN (and reusable for RURAL). Lays a regular grid over the network's
bounding box and snaps each grid point to the nearest drivable road.

Outputs (in --out-dir, prefixed with --prefix):
  _rsulist.csv, _failures.csv, _markers_only.xml, .json, _neighbours.csv
Requires: export PYTHONPATH=$SUMO_HOME/tools:$PYTHONPATH
"""
import argparse, csv, json, math, os, random, sys
try:
    import sumolib
    from sumolib import geomhelper
except ImportError:
    sys.exit("sumolib not found. export PYTHONPATH=$SUMO_HOME/tools:$PYTHONPATH")

DEFAULT_EXCLUDE = "cycleway,footway,pedestrian,steps,path,bridleway,track"

def parse_args():
    ap = argparse.ArgumentParser(description="Grid-coverage RSU placement (urban/rural ODD).")
    ap.add_argument("--net", required=True)
    ap.add_argument("--prefix", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--spacing", type=float, default=400.0)
    ap.add_argument("--range", type=float, default=800.0)
    ap.add_argument("--snap-radius", type=float, default=None)
    ap.add_argument("--min-sep", type=float, default=None)
    ap.add_argument("--vclass", default="passenger")
    ap.add_argument("--exclude-types", default=DEFAULT_EXCLUDE)
    ap.add_argument("--offset", type=float, default=None)
    ap.add_argument("--failures", default=None)
    ap.add_argument("--auto-failures", type=int, default=0)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--fail-start", type=float, default=150.0)
    ap.add_argument("--fail-end", type=float, default=450.0)
    ap.add_argument("--fail-duration", type=float, default=75.0)
    ap.add_argument("--compare", default=None)
    return ap.parse_args()

def edge_type_ok(edge, excluded):
    t = (edge.getType() or "").lower()
    return not any(x and x in t for x in excluded)

def snap(net, x, y, radius, vclass, excluded):
    best = None
    for lane, _ in net.getNeighboringLanes(x, y, r=radius, includeJunctions=False):
        if not lane.allows(vclass) or not edge_type_ok(lane.getEdge(), excluded):
            continue
        shape = lane.getShape()
        off = geomhelper.polygonOffsetWithMinimumDistanceToPoint((x, y), shape, perpendicular=False)
        px, py = geomhelper.positionAtShapeOffset(shape, off)
        d = math.hypot(px - x, py - y)
        if d <= radius and (best is None or d < best[0]):
            best = (d, px, py, lane.getEdge().getID())
    return best

def place(net, a):
    (xmin, ymin), (xmax, ymax) = net.getBBoxXY()
    sp = a.spacing
    off = sp / 2 if a.offset is None else a.offset
    snap_r = sp / 2 if a.snap_radius is None else a.snap_radius
    min_sep = sp / 2 if a.min_sep is None else a.min_sep
    excluded = [s.strip().lower() for s in a.exclude_types.split(",") if s.strip()]
    rsus, grid_pts, empty, dup = [], 0, 0, 0
    y = ymin + off
    while y <= ymax:
        x = xmin + off
        while x <= xmax:
            grid_pts += 1
            s = snap(net, x, y, snap_r, a.vclass, excluded)
            if s is None:
                empty += 1
            elif any(math.hypot(s[1] - r["x"], s[2] - r["y"]) < min_sep for r in rsus):
                dup += 1
            else:
                rsus.append({"rsu_id": f"rsu{len(rsus)}", "x": round(s[1], 2), "y": round(s[2], 2),
                             "edge": s[3], "grid_x": round(x, 1), "grid_y": round(y, 1)})
            x += sp
        y += sp
    stats = {"bbox": [xmin, ymin, xmax, ymax], "grid_points": grid_pts, "empty_cells": empty,
             "dropped_too_close": dup, "snap_radius": snap_r, "min_sep": min_sep}
    return rsus, stats

def neighbours(rsus, rng):
    pairs = []
    for i in range(len(rsus)):
        for j in range(i + 1, len(rsus)):
            d = math.hypot(rsus[i]["x"] - rsus[j]["x"], rsus[i]["y"] - rsus[j]["y"])
            if d <= rng:
                pairs.append((rsus[i]["rsu_id"], rsus[j]["rsu_id"], round(d, 1)))
    return pairs

def make_failures(a, rsus, pairs):
    ids = {r["rsu_id"] for r in rsus}
    if a.failures:
        out = []
        for item in a.failures.split(","):
            rid, s, e = item.strip().split(":")
            if rid not in ids:
                sys.exit(f"--failures: {rid} is not in the generated RSU list")
            out.append((rid, float(s), float(e)))
        return out
    if a.auto_failures <= 0:
        return []
    rnd = random.Random(a.seed)
    adj = {r["rsu_id"]: [] for r in rsus}
    for p, q, _ in pairs:
        adj[p].append(q); adj[q].append(p)
    candidates = [r for r in adj if adj[r]]
    if not candidates:
        sys.exit("auto-failures: no RSU has an in-range neighbour")
    first = rnd.choice(candidates)
    chosen = [first] + rnd.sample(adj[first], min(a.auto_failures - 1, len(adj[first])))
    base = rnd.uniform(a.fail_start, a.fail_end)
    out = []
    for k, rid in enumerate(chosen):
        s = base - k * rnd.uniform(5, 20)
        e = s + a.fail_duration + rnd.uniform(0, 5)
        out.append((rid, round(s, 1), round(e, 1)))
    return out

def write_outputs(a, rsus, stats, pairs, failures):
    os.makedirs(a.out_dir, exist_ok=True)
    p = lambda suffix: os.path.join(a.out_dir, a.prefix + suffix)
    with open(p("_rsulist.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["rsu_id", "x", "y"])
        for r in rsus:
            w.writerow([r["rsu_id"], f"{r['x']:.2f}", f"{r['y']:.2f}"])
    with open(p("_failures.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["rsu_id", "fail_start", "fail_end"])
        for rid, s, e in failures:
            w.writerow([rid, s, e])
    with open(p("_neighbours.csv"), "w", newline="") as f:
        w = csv.writer(f); w.writerow(["rsu_a", "rsu_b", "distance_m"]); w.writerows(pairs)
    failed = {rid for rid, _, _ in failures}
    with open(p("_markers_only.xml"), "w") as f:
        f.write("<additional>\n")
        for r in rsus:
            color = "0,0,255" if r["rsu_id"] in failed else "255,0,0"
            f.write(f'    <poi id="{r["rsu_id"]}" type="RSU" color="{color}" layer="100" '
                    f'x="{r["x"]:.2f}" y="{r["y"]:.2f}" width="12" height="12"/>\n')
        f.write("</additional>\n")
    deg = {r["rsu_id"]: 0 for r in rsus}
    for x, y, _ in pairs:
        deg[x] += 1; deg[y] += 1
    degs = list(deg.values()) or [0]
    summary = {"scenario": a.prefix.split("_")[0], "rsu_comm_range_m": a.range, "rsu_count": len(rsus),
               "parameters": dict(vars(a)), "placement": stats, "num_rsus": len(rsus),
               "neighbour_pairs_within_range": len(pairs),
               "neighbours_per_rsu": {"min": min(degs), "max": max(degs),
                                      "avg": round(sum(degs) / len(degs), 2)},
               "isolated_rsus": [k for k, v in deg.items() if v == 0],
               "failures": [{"rsu_id": r, "fail_start": s, "fail_end": e} for r, s, e in failures],
               "rsus": [dict(id=r["rsu_id"], **{k: v for k, v in r.items() if k != "rsu_id"}) for r in rsus]}
    with open(p(".json"), "w") as f:
        json.dump(summary, f, indent=2)
    return summary

def compare(path, rsus, tol=50.0):
    old = [(r["rsu_id"], float(r["x"]), float(r["y"])) for r in csv.DictReader(open(path))]
    new = [(r["rsu_id"], r["x"], r["y"]) for r in rsus]
    matched = sum(1 for _, ox, oy in old if any(math.hypot(ox - nx, oy - ny) <= tol for _, nx, ny in new))
    same_id = sum(1 for (oi, ox, oy), (ni, nx, ny) in zip(old, new)
                  if oi == ni and math.hypot(ox - nx, oy - ny) <= tol)
    print(f"\n== compare with {path}")
    print(f"   existing RSUs: {len(old)}   new RSUs: {len(new)}")
    print(f"   existing RSUs with a new RSU within {tol:.0f} m: {matched}/{len(old)}")
    print(f"   same id AND same place (within {tol:.0f} m): {same_id}/{min(len(old), len(new))}")

def main():
    a = parse_args()
    net = sumolib.net.readNet(os.path.expanduser(a.net), withInternal=False)
    rsus, stats = place(net, a)
    if not rsus:
        sys.exit("no RSUs placed -- check --vclass / --exclude-types / --snap-radius")
    pairs = neighbours(rsus, a.range)
    failures = make_failures(a, rsus, pairs)
    s = write_outputs(a, rsus, stats, pairs, failures)
    print(f"grid points: {stats['grid_points']}  empty: {stats['empty_cells']}  too close: {stats['dropped_too_close']}")
    print(f"RSUs placed: {s['num_rsus']}   range: {a.range:.0f} m")
    n = s['neighbours_per_rsu']
    print(f"neighbour pairs within range: {s['neighbour_pairs_within_range']}   per RSU min/avg/max: {n['min']}/{n['avg']}/{n['max']}")
    print(f"isolated RSUs (no neighbour): {len(s['isolated_rsus'])} {s['isolated_rsus'][:10]}")
    for r, st, en in failures:
        print(f"failure: {r} {st}-{en}s")
    print(f"outputs in {a.out_dir}/{a.prefix}_*")
    if a.compare:
        compare(os.path.expanduser(a.compare), rsus)

if __name__ == "__main__":
    main()
