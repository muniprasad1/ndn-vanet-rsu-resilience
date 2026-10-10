#!/usr/bin/env python3
"""
inject_breakdowns.py

Makes vehicle breakdowns PHYSICALLY real, not just a communication-layer
event: picks N random (vehicle, time) pairs, freezes each chosen
vehicle's position in the trajectory data from that moment onward (it
genuinely stops moving, like a real breakdown), and regenerates every
downstream artifact that depends on vehicle position so the whole
pipeline stays consistent:

  1. A MODIFIED FCD XML (same schema as the original, vehicle frozen
     after its breakdown time) -- feed this to
     precompute_candidate_links.py and precompute_v2v_links.py instead
     of the original, so RSU/V2V contact windows correctly reflect the
     vehicle now sitting still.
  2. A regenerated ns2mobility.tcl (ns-3's Ns2MobilityHelper format --
     confirmed against generate_hazard_plan.py's own working regex
     parser: "$node_(ID) set X_/Y_ ..." then
     "$ns_ at TIME \"$node_(ID) setdest X Y SPEED\"" lines).
  3. hazard_events.csv (vehicle_index, breakdown_time, x, y) for the
     C++ side to load directly, instead of picking randomly at runtime.

Run BEFORE precompute_candidate_links.py / precompute_v2v_links.py in
the pipeline, using its outputs (not the original FCD) as their input.
"""

import csv
import random
import argparse
import xml.etree.ElementTree as ET
import xml.dom.minidom as minidom


def load_node_map(path):
    id_to_idx, idx_to_id = {}, {}
    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            sumo_id = row['sumo_vehicle_id']
            idx = int(row['ns3_node_index'])
            id_to_idx[sumo_id] = idx
            idx_to_id[idx] = sumo_id
    return id_to_idx, idx_to_id


def parse_fcd(fcd_path):
    """Returns (tree, root, timesteps) where timesteps is a list of
    (time_float, <timestep> Element) in document order, preserving the
    original XML structure so we can write it back out unmodified
    except for the frozen vehicles' coordinates."""
    tree = ET.parse(fcd_path)
    root = tree.getroot()
    timesteps = []
    for elem in root.findall('timestep'):
        timesteps.append((float(elem.get('time')), elem))
    timesteps.sort(key=lambda p: p[0])
    return tree, root, timesteps


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--fcd', required=True, help='Original SUMO FCD trajectory XML')
    ap.add_argument('--nodeMap', required=True, help='SUMO id -> ns-3 node index CSV')
    ap.add_argument('--numBreakdowns', type=int, default=3)
    ap.add_argument('--simEnd', type=float, required=True, help='simulation length (s) -- breakdown times stay below this')
    ap.add_argument('--randSeed', type=int, default=None, help='omit for fresh randomness each run')
    ap.add_argument('--outFcd', required=True, help='Output modified FCD XML path')
    ap.add_argument('--outMobility', required=True, help='Output ns2mobility.tcl path')
    ap.add_argument('--outHazardEvents', required=True, help='Output hazard_events.csv path')
    args = ap.parse_args()

    if args.randSeed is not None:
        random.seed(args.randSeed)

    print(f"[BREAKDOWN-INJECT] Loading node map from {args.nodeMap} ...")
    id_to_idx, idx_to_id = load_node_map(args.nodeMap)

    print(f"[BREAKDOWN-INJECT] Parsing FCD trajectory from {args.fcd} ...")
    tree, root, timesteps = parse_fcd(args.fcd)
    print(f"[BREAKDOWN-INJECT] {len(timesteps)} timesteps loaded.")

    vehicle_times = {}
    for t, ts_elem in timesteps:
        for veh in ts_elem.findall('vehicle'):
            idx = id_to_idx.get(veh.get('id'))
            if idx is None:
                continue
            vehicle_times.setdefault(idx, []).append(t)

    candidate_vehicles = [v for v, ts in vehicle_times.items() if len(ts) >= 3]
    chosen = random.sample(candidate_vehicles, min(args.numBreakdowns, len(candidate_vehicles)))

    breakdown_time = {}
    breakdown_pos = {}
    for idx in chosen:
        ts = sorted(vehicle_times[idx])
        lo, hi = ts[0], min(ts[-1], args.simEnd - 5.0)
        if hi <= lo:
            continue
        breakdown_time[idx] = round(random.uniform(lo, hi), 1)

    print(f"[BREAKDOWN-INJECT] Chose {len(breakdown_time)} breakdown events:")
    for idx, t in breakdown_time.items():
        print(f"  Vehicle{idx} ({idx_to_id[idx]}) breaks down at t={t}s")

    for t, ts_elem in timesteps:
        for veh in ts_elem.findall('vehicle'):
            sumo_id = veh.get('id')
            idx = id_to_idx.get(sumo_id)
            if idx is None or idx not in breakdown_time:
                continue
            if t < breakdown_time[idx]:
                breakdown_pos[idx] = (veh.get('x'), veh.get('y'))
                continue
            if idx not in breakdown_pos:
                breakdown_pos[idx] = (veh.get('x'), veh.get('y'))
            fx, fy = breakdown_pos[idx]
            veh.set('x', fx)
            veh.set('y', fy)
            veh.set('speed', '0.00')

    xml_str = ET.tostring(root, encoding='unicode')
    pretty = minidom.parseString(xml_str).toprettyxml(indent='    ')
    with open(args.outFcd, 'w') as f:
        f.write(pretty)
    print(f"[BREAKDOWN-INJECT] Wrote modified FCD to {args.outFcd}")

    with open(args.outHazardEvents, 'w', newline='') as f:
        writer = csv.writer(f)
        writer.writerow(['vehicle_index', 'breakdown_time', 'x', 'y'])
        for idx, t in breakdown_time.items():
            x, y = breakdown_pos[idx]
            writer.writerow([idx, t, x, y])
    print(f"[BREAKDOWN-INJECT] Wrote {args.outHazardEvents}")

    max_idx = max(id_to_idx.values())
    first_seen = {}
    with open(args.outMobility, 'w') as f:
        f.write(f"# ns2 mobility trace regenerated by inject_breakdowns.py\n")
        f.write(f"set opt(nn) {max_idx + 1}\n\n")

        for t, ts_elem in timesteps:
            for veh in ts_elem.findall('vehicle'):
                idx = id_to_idx.get(veh.get('id'))
                if idx is None:
                    continue
                x, y = float(veh.get('x')), float(veh.get('y'))
                if idx not in first_seen:
                    first_seen[idx] = True
                    f.write(f"$node_({idx}) set X_ {x:.2f}\n")
                    f.write(f"$node_({idx}) set Y_ {y:.2f}\n")
                    f.write(f"$node_({idx}) set Z_ 0.0\n")
                speed = float(veh.get('speed', '0.0'))
                f.write(f'$ns_ at {t:.2f} "$node_({idx}) setdest {x:.2f} {y:.2f} {speed:.2f}"\n')
    print(f"[BREAKDOWN-INJECT] Wrote {args.outMobility}")

    print("[BREAKDOWN-INJECT] Done. Next steps:")
    print(f"  1. Re-run precompute_candidate_links.py against {args.outFcd}")
    print(f"  2. Re-run precompute_v2v_links.py against {args.outFcd}")
    print(f"  3. Point the C++ run at {args.outMobility} and {args.outHazardEvents}")


if __name__ == '__main__':
    main()
