#!/usr/bin/env python3
import argparse
import json
import sys
import xml.etree.ElementTree as ET

try:
    import traci
except ImportError:
    sys.exit("traci not found. export PYTHONPATH=$SUMO_HOME/tools:$PYTHONPATH")


def load_hazard_events(path):
    events = {}
    with open(path) as f:
        f.readline()
        for line in f:
            parts = line.strip().split(",")
            if len(parts) < 4:
                continue
            idx, t, x, y = parts[0], float(parts[1]), parts[2], parts[3]
            events[idx] = t
    return events


def parse_fcd(path):
    tree = ET.parse(path)
    root = tree.getroot()
    timesteps = []
    for elem in root.findall("timestep"):
        t = float(elem.get("time"))
        vehicles = [(v.get("id"), float(v.get("x")), float(v.get("y")),
                     float(v.get("angle", "0")), float(v.get("speed", "0")))
                    for v in elem.findall("vehicle")]
        timesteps.append((t, vehicles))
    timesteps.sort(key=lambda p: p[0])
    return timesteps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fcd", required=True)
    ap.add_argument("--net", required=True)
    ap.add_argument("--hazard-events", default=None)
    ap.add_argument("--node-map", default=None)
    ap.add_argument("--port", type=int, default=8813)
    ap.add_argument("--binary", default="sumo-gui")
    ap.add_argument("--gui-settings", default=None, help="SUMO gui-settings-file, e.g. osm.view.xml")
    ap.add_argument("--rsu-config", default=None, help="highway_rsu.json -- draws a marker at each RSU")
    args = ap.parse_args()

    timesteps = parse_fcd(args.fcd)
    print(f"[REPLAY] Loaded {len(timesteps)} timesteps from {args.fcd}")

    breakdown_time_by_idx = {}
    if args.hazard_events:
        breakdown_time_by_idx = load_hazard_events(args.hazard_events)
        print(f"[REPLAY] {len(breakdown_time_by_idx)} breakdown event(s) loaded")

    idx_to_sumo_id = {}
    if args.node_map:
        with open(args.node_map) as f:
            f.readline()
            for line in f:
                parts = line.strip().split(",")
                if len(parts) < 2:
                    continue
                sumo_id, idx = parts[0], parts[1]
                idx_to_sumo_id[idx] = sumo_id

    breakdown_sumo_ids = set()
    for idx, t in breakdown_time_by_idx.items():
        sumo_id = idx_to_sumo_id.get(idx)
        if sumo_id:
            breakdown_sumo_ids.add(sumo_id)
        else:
            print(f"[WARN] no --node-map match -- cannot color/report Vehicle{idx} by name")

    cmd = [args.binary, "-n", args.net, "--step-length", "1", "--start"]
    if args.gui_settings:
        cmd += ["--gui-settings-file", args.gui_settings]
    traci.start(cmd, port=args.port)

    if args.rsu_config:
        with open(args.rsu_config) as f:
            rsu_cfg = json.load(f)
        for rsu in rsu_cfg["rsus"]:
            try:
                traci.poi.add(f"marker_{rsu['id']}", rsu["x"], rsu["y"], (255, 0, 255, 255), width=15)
            except traci.exceptions.TraCIException as e:
                print(f"[WARN] could not place marker for {rsu['id']}: {e}")
        print(f"[REPLAY] Placed {len(rsu_cfg['rsus'])} RSU markers")

    known_vehicles = set()
    frozen_already_reported = set()

    for t, vehicles in timesteps:
        present_now = set()
        for veh_id, x, y, angle, speed in vehicles:
            present_now.add(veh_id)
            if veh_id not in known_vehicles:
                try:
                    traci.vehicle.add(veh_id, routeID="", typeID="DEFAULT_VEHTYPE")
                    traci.vehicle.setSpeedMode(veh_id, 0)
                    known_vehicles.add(veh_id)
                except traci.exceptions.TraCIException as e:
                    print(f"[WARN] could not add {veh_id}: {e}")
                    continue
            try:
                traci.vehicle.moveToXY(veh_id, edgeID="", lane=-1, x=x, y=y,
                                        angle=angle, keepRoute=2)
            except traci.exceptions.TraCIException as e:
                print(f"[WARN] could not move {veh_id}: {e}")
                continue

            if veh_id in breakdown_sumo_ids:
                idx_for_id = next((i for i, sid in idx_to_sumo_id.items() if sid == veh_id), None)
                bt = breakdown_time_by_idx.get(idx_for_id) if idx_for_id else None
                if bt is not None and t >= bt:
                    traci.vehicle.setColor(veh_id, (255, 0, 0, 255))
                    if veh_id not in frozen_already_reported:
                        frozen_already_reported.add(veh_id)
                        print(f"[BREAKDOWN] {veh_id} (Vehicle{idx_for_id}) froze at t={t:.1f}s pos=({x:.1f},{y:.1f})")

        gone = known_vehicles - present_now
        for veh_id in gone:
            try:
                traci.vehicle.remove(veh_id)
            except traci.exceptions.TraCIException:
                pass
            known_vehicles.discard(veh_id)
            frozen_already_reported.discard(veh_id)

        traci.simulationStep()

    print("[REPLAY] Finished replaying all timesteps.")
    traci.close()


if __name__ == "__main__":
    main()
