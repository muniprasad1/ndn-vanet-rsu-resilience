#!/usr/bin/env python3
"""
precompute_v2v_links.py

Sibling to precompute_candidate_links.py, but for VEHICLE-TO-VEHICLE
contact windows instead of RSU-to-vehicle. Needed for genuine V2V
last-mile relay: when the original requesting vehicle has driven out
of an RSU's range before the Data comes back, the RSU needs a
pre-created point-to-point link to whichever OTHER vehicle can
physically reach the original requester, and ns-3 point-to-point links
can't be created mid-simulation -- so every pair that might ever need
one must be precomputed here, just like the RSU<->vehicle links were.

Reads the same highway_fcd.xml trajectory data and highway_node_map.csv
(SUMO vehicle id -> ns-3 node index) already used for
precompute_candidate_links.py, so vehicle indices line up exactly.

V2V_RANGE defaults to 300m (typical DSRC/V2V range), deliberately
smaller than the 800m RSU range, since it's a much lower-power,
vehicle-to-vehicle link, not an RSU's infrastructure radio.

Output: <scenario>_v2v_links.csv with columns
  vehicle_a_index,vehicle_b_index,contact_start,contact_end
(vehicle_a_index < vehicle_b_index always, each pair listed once;
 the relay logic can use the same row regardless of which vehicle
 initiates delivery to the other.)
"""

import sys
import csv
import argparse
import xml.etree.ElementTree as ET
from collections import defaultdict

V2V_RANGE = 300.0  # meters


def load_node_map(path):
    """SUMO vehicle id -> ns-3 node index."""
    id_to_idx = {}
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            id_to_idx[row['sumo_vehicle_id']] = int(row['ns3_node_index'])
    return id_to_idx


def load_fcd_positions(fcd_path, id_to_idx):
    """
    Returns: dict[timestep_float] -> dict[vehicle_index] -> (x, y)
    Skips any SUMO vehicle id not present in the node map (shouldn't
    happen if the same run produced both files, but defensive).
    """
    timesteps = {}
    for event, elem in ET.iterparse(fcd_path, events=('end',)):
        if elem.tag == 'timestep':
            t = float(elem.get('time'))
            frame = {}
            for veh in elem.findall('vehicle'):
                sumo_id = veh.get('id')
                idx = id_to_idx.get(sumo_id)
                if idx is None:
                    continue
                frame[idx] = (float(veh.get('x')), float(veh.get('y')))
            if frame:
                timesteps[t] = frame
            elem.clear()
    return timesteps


def compute_v2v_windows(timesteps, v2v_range):
    """
    Sweeps timesteps in order; for every pair of vehicles simultaneously
    present and within v2v_range, extends an open contact window or
    starts a new one. Returns list of (a_idx, b_idx, start, end).
    """
    times = sorted(timesteps.keys())
    range_sq = v2v_range * v2v_range

    # open_windows[(a,b)] = start_time  (a < b always)
    open_windows = {}
    closed_windows = []

    prev_t = None
    for t in times:
        frame = timesteps[t]
        present_now = set()

        indices = sorted(frame.keys())
        n = len(indices)
        for i in range(n):
            ai = indices[i]
            ax, ay = frame[ai]
            for j in range(i + 1, n):
                bi = indices[j]
                bx, by = frame[bi]
                dx = ax - bx
                dy = ay - by
                if dx * dx + dy * dy <= range_sq:
                    present_now.add((ai, bi))

        # close windows for pairs no longer in range
        for pair in list(open_windows.keys()):
            if pair not in present_now:
                start = open_windows.pop(pair)
                closed_windows.append((pair[0], pair[1], start, prev_t if prev_t is not None else t))

        # open windows for newly-in-range pairs
        for pair in present_now:
            if pair not in open_windows:
                open_windows[pair] = t

        prev_t = t

    # close any still-open windows at the last timestep
    last_t = times[-1] if times else 0.0
    for pair, start in open_windows.items():
        closed_windows.append((pair[0], pair[1], start, last_t))

    return closed_windows


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--fcd', required=True, help='SUMO FCD trajectory XML file')
    ap.add_argument('--nodeMap', required=True, help='SUMO id -> ns-3 node index CSV (from earlier pipeline)')
    ap.add_argument('--out', required=True, help='Output CSV path')
    ap.add_argument('--range', type=float, default=V2V_RANGE, help=f'V2V range in meters (default {V2V_RANGE})')
    args = ap.parse_args()

    print(f"[V2V-PRECOMPUTE] Loading node map from {args.nodeMap} ...")
    id_to_idx = load_node_map(args.nodeMap)
    print(f"[V2V-PRECOMPUTE] {len(id_to_idx)} vehicles in node map.")

    print(f"[V2V-PRECOMPUTE] Parsing FCD trajectory from {args.fcd} ...")
    timesteps = load_fcd_positions(args.fcd, id_to_idx)
    print(f"[V2V-PRECOMPUTE] {len(timesteps)} timesteps loaded.")

    print(f"[V2V-PRECOMPUTE] Computing V2V contact windows at range={args.range}m ...")
    windows = compute_v2v_windows(timesteps, args.range)
    print(f"[V2V-PRECOMPUTE] {len(windows)} vehicle-pair contact windows found.")

    with open(args.out, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['vehicle_a_index', 'vehicle_b_index', 'contact_start', 'contact_end'])
        for a, b, start, end in sorted(windows, key=lambda w: w[2]):
            writer.writerow([a, b, round(start, 1), round(end, 1)])

    print(f"[V2V-PRECOMPUTE] Wrote {args.out}")


if __name__ == '__main__':
    main()
