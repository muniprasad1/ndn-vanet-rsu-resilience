#!/usr/bin/env python3
"""
generate_rsu_config.py
-----------------------
Places RSUs along a SUMO road network and writes an RSU config JSON,
plus matching CSVs for C++ loading, that your ns-3/ndnSIM core
(ndn-town-final.cpp) reads at startup.

Usage:
    python3 generate_rsu_config.py --net highway.net.xml --scenario highway \
        --spacing 1000 --offset 60 --fail-rsu 3 --fail-start 150 --fail-end 300 \
        --out highway_rsu.json
"""
import argparse
import json
import random
import sys

try:
    import sumolib
except ImportError:
    sys.exit("sumolib not found. Install SUMO's python tools (apt package "
              "'sumo' + $SUMO_HOME/tools on PYTHONPATH) before running this.")


def place_rsus_along_edges_from_list(edges, spacing, offset):
    rsus = []
    seen_positions = set()
    rsu_id = 0
    for edge in edges:
        shape = edge.getShape()
        if len(shape) < 2:
            continue
        dist_since_last = 0.0
        for i in range(len(shape) - 1):
            x1, y1 = shape[i]
            x2, y2 = shape[i + 1]
            seg_len = ((x2 - x1) ** 2 + (y2 - y1) ** 2) ** 0.5
            if seg_len == 0:
                continue
            ux, uy = (x2 - x1) / seg_len, (y2 - y1) / seg_len
            px, py = -uy, ux

            pos = 0.0
            while dist_since_last + (seg_len - pos) >= spacing:
                pos += spacing - dist_since_last
                dist_since_last = 0.0
                rx = x1 + ux * pos + px * offset
                ry = y1 + uy * pos + py * offset
                key = (round(rx, 1), round(ry, 1))
                if key in seen_positions:
                    continue
                seen_positions.add(key)
                rsus.append({
                    "id": f"rsu{rsu_id}",
                    "x": round(rx, 2),
                    "y": round(ry, 2),
                    "edge": edge.getID(),
                })
                rsu_id += 1
            dist_since_last += seg_len - pos

    return rsus


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--net", required=True, help="SUMO .net.xml file")
    ap.add_argument("--scenario", required=True, help="scenario name, e.g. highway/rural/urban")
    ap.add_argument("--spacing", type=float, default=1000.0, help="metres between RSUs along road")
    ap.add_argument("--offset", type=float, default=50.0, help="perpendicular offset from road centerline (m)")
    ap.add_argument("--range", type=float, default=300.0, help="RSU nominal comms range (m), for reference/plots")
    ap.add_argument("--fail-rsu", type=int, action="append", default=[],
                     help="index of an RSU to fail mid-run (repeatable). Ignored if --random-failures is set.")
    ap.add_argument("--fail-start", type=float, default=150.0, help="failure window start (s). Ignored if --random-failures is set.")
    ap.add_argument("--fail-end", type=float, default=300.0, help="failure window end (s). Ignored if --random-failures is set.")
    ap.add_argument("--random-failures", action="store_true",
                     help="pick failing RSU(s), start time, and duration randomly instead of fixed values")
    ap.add_argument("--num-random-failures", type=int, default=1,
                     help="how many independent RSU outages to inject (can hit the same RSU twice)")
    ap.add_argument("--fail-duration-min", type=float, default=60.0, help="min outage duration (s) for random mode")
    ap.add_argument("--fail-duration-max", type=float, default=200.0, help="max outage duration (s) for random mode")
    ap.add_argument("--sim-end", type=float, default=600.0, help="simulation length (s), bounds random start times")
    ap.add_argument("--rand-seed", type=int, default=42, help="seed for reproducible random failure injection")
    ap.add_argument("--out", required=True, help="output JSON path")
    ap.add_argument("--include-edges", default=None,
                     help="comma-separated edge IDs to restrict placement to "
                          "(use to avoid double RSUs on both carriageways of a divided road)")
    ap.add_argument("--sumo-additional-out", default=None,
                     help="also write a SUMO additional-file with RSU markers + range-bubble "
                          "polygons at this path, for visualizing coverage in sumo-gui")
    args = ap.parse_args()

    net = sumolib.net.readNet(args.net)
    if args.include_edges:
        allowed = set(args.include_edges.split(","))
        net_edges = [e for e in net.getEdges() if e.getID() in allowed]
    else:
        net_edges = net.getEdges()
    rsus = place_rsus_along_edges_from_list(net_edges, args.spacing, args.offset)

    failure_schedule = []
    if args.random_failures:
        rng = random.Random(args.rand_seed)
        if not rsus:
            pass
        else:
            for _ in range(args.num_random_failures):
                idx = rng.randrange(len(rsus))
                duration = rng.uniform(args.fail_duration_min, args.fail_duration_max)
                latest_start = max(0.0, args.sim_end - duration)
                start = rng.uniform(0.0, latest_start) if latest_start > 0 else 0.0
                failure_schedule.append({
                    "rsu_id": f"rsu{idx}",
                    "fail_start": round(start, 1),
                    "fail_end": round(start + duration, 1),
                })
            failure_schedule.sort(key=lambda f: f["fail_start"])
    else:
        fail_ids = args.fail_rsu or ([len(rsus) // 2] if rsus else [])
        failure_schedule = [
            {"rsu_id": f"rsu{idx}", "fail_start": args.fail_start, "fail_end": args.fail_end}
            for idx in fail_ids if idx < len(rsus)
        ]

    config = {
        "scenario": args.scenario,
        "rsu_comm_range_m": args.range,
        "rsu_count": len(rsus),
        "rsus": rsus,
        "failure_schedule": failure_schedule,
    }

    with open(args.out, "w") as f:
        json.dump(config, f, indent=2)

    print(f"[{args.scenario}] placed {len(rsus)} RSUs, "
          f"{len(failure_schedule)} scheduled failure(s) -> {args.out}")

    if args.sumo_additional_out:
        write_sumo_additional(rsus, args.range, args.sumo_additional_out)
        print(f"[{args.scenario}] wrote sumo-gui RSU markers + range bubbles -> {args.sumo_additional_out}")
        print(f"    Add to your .sumocfg: <additional-files value=\"{args.sumo_additional_out}\"/>")

    rsulist_path = args.out.replace(".json", "_rsulist.csv")
    if rsulist_path == args.out:
        rsulist_path = args.out + "_rsulist.csv"
    with open(rsulist_path, "w") as f:
        f.write("rsu_id,x,y\n")
        for rsu in rsus:
            f.write(f"{rsu['id']},{rsu['x']},{rsu['y']}\n")

    failures_path = args.out.replace(".json", "_failures.csv")
    if failures_path == args.out:
        failures_path = args.out + "_failures.csv"
    with open(failures_path, "w") as f:
        f.write("rsu_id,fail_start,fail_end\n")
        for fail in failure_schedule:
            f.write(f"{fail['rsu_id']},{fail['fail_start']},{fail['fail_end']}\n")

    print(f"[{args.scenario}] also wrote {rsulist_path} and {failures_path} for C++ loading")


def circle_shape(cx, cy, radius, n_points=36):
    import math
    pts = []
    for i in range(n_points):
        ang = 2 * math.pi * i / n_points
        pts.append(f"{cx + radius * math.cos(ang):.2f},{cy + radius * math.sin(ang):.2f}")
    return " ".join(pts)


def write_sumo_additional(rsus, comm_range, out_path):
    lines = ['<?xml version="1.0" encoding="UTF-8"?>', "<additional>"]
    for rsu in rsus:
        rid, x, y = rsu["id"], rsu["x"], rsu["y"]
        lines.append(f'    <poi id="{rid}" x="{x}" y="{y}" color="1,0,0" layer="200" '
                     f'type="RSU" width="20" height="20"/>')
        lines.append(f'    <poly id="{rid}_range" shape="{circle_shape(x, y, comm_range)}" '
                     f'color="0,0.3,1" fill="0" layer="100" lineWidth="3"/>')
    lines.append("</additional>")
    with open(out_path, "w") as f:
        f.write("\n".join(lines) + "\n")


if __name__ == "__main__":
    main()
