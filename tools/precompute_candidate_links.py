#!/usr/bin/env python3
"""
precompute_candidate_links.py
-------------------------------
Scans a SUMO FCD trace and an RSU config, and finds every (RSU, vehicle)
pair that ever comes within that RSU's communication range at any point
during the simulation -- with the exact time window(s) of contact.

This does NOT decide which vehicle becomes the VCF mule -- that decision
stays fully live in ns-3 (SelectMuleVehicle(), scored by real-time speed/
heading/memory at the moment of failure). This script only answers a
narrower, physics-only question: "which RSU-vehicle links could ever
possibly matter, and when are they physically in range?" -- because
ns-3/ndnSIM requires point-to-point links to exist as objects before
the NDN stack installs. We pre-create exactly these links, all initially
failed, and the live C++ code just calls UpLink() on whichever one
SelectMuleVehicle() picks at runtime.

Also outputs the vehicle_id -> ns-3 node-index mapping (first-appearance
order in the FCD, matching exactly how Ns2MobilityHelper indexes nodes
from the corresponding .tcl trace).

Usage:
    python3 precompute_candidate_links.py --fcd osm_fcd.xml \
        --rsu-config highway_rsu.json --out highway_candidate_links.csv \
        --node-map-out highway_node_map.csv
"""
import argparse
import csv
import json
import xml.etree.ElementTree as ET


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fcd", required=True, help="SUMO FCD output XML")
    ap.add_argument("--rsu-config", required=True, help="the *_rsu.json file")
    ap.add_argument("--out", required=True, help="output CSV of candidate contact windows")
    ap.add_argument("--node-map-out", required=True, help="output CSV of SUMO vehicle ID -> ns-3 node index")
    ap.add_argument("--max-gap", type=float, default=2.0,
                     help="merge contact windows separated by up to this many seconds")
    args = ap.parse_args()

    with open(args.rsu_config) as f:
        rsu_cfg = json.load(f)
    rsus = rsu_cfg["rsus"]
    comm_range = rsu_cfg["rsu_comm_range_m"]
    range_sq = comm_range ** 2

    node_index = {}
    open_contacts = {}
    windows = []
    last_seen_in_range = {}

    def close_contact(key, last_seen_time):
        start = open_contacts.pop(key)
        windows.append((key[0], key[1], start, last_seen_time))

    for event, elem in ET.iterparse(args.fcd, events=("start", "end")):
        if event == "start" and elem.tag == "timestep":
            t = float(elem.get("time"))
        elif event == "end" and elem.tag == "vehicle":
            vid = elem.get("id")
            if vid not in node_index:
                node_index[vid] = len(node_index)
            idx = node_index[vid]
            vx, vy = float(elem.get("x")), float(elem.get("y"))

            for rsu in rsus:
                rid = rsu["id"]
                dx, dy = vx - rsu["x"], vy - rsu["y"]
                dist_sq = dx * dx + dy * dy
                key = (rid, idx)
                if dist_sq <= range_sq:
                    if key not in open_contacts:
                        open_contacts[key] = t
                    last_seen_in_range[key] = t
            elem.clear()
        elif event == "end" and elem.tag == "timestep":
            for key in list(open_contacts.keys()):
                if t - last_seen_in_range.get(key, t) > args.max_gap:
                    close_contact(key, last_seen_in_range[key])
            elem.clear()

    for key in list(open_contacts.keys()):
        close_contact(key, last_seen_in_range.get(key, open_contacts[key]))

    windows.sort(key=lambda w: (w[0], w[2]))

    with open(args.out, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["rsu_id", "vehicle_node_index", "contact_start", "contact_end"])
        for rid, idx, start, end in windows:
            writer.writerow([rid, idx, round(start, 1), round(end, 1)])

    with open(args.node_map_out, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["sumo_vehicle_id", "ns3_node_index"])
        for vid, idx in sorted(node_index.items(), key=lambda kv: kv[1]):
            writer.writerow([vid, idx])

    print(f"Found {len(windows)} candidate contact windows across {len(rsus)} RSUs "
          f"and {len(node_index)} vehicles.")
    print(f"-> {args.out}")
    print(f"-> {args.node_map_out}")


if __name__ == "__main__":
    main()
