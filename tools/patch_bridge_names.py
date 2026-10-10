#!/usr/bin/env python3
"""Add an optional --node-map option to sumo_bridge_server.py so the Live Co-Sim
Events window shows 'Vehicle6 (veh4)' instead of only 'Vehicle6'.
Display only: nothing sent to SUMO or ns-3 changes."""
import shutil, sys

p = "/home/muni/2026-09-26-livecosim/sumo_bridge_server.py"
s = open(p).read()
if "NAME_MAP" in s:
    sys.exit("already patched - nothing changed")

edits = [
    ("def run_dashboard():",
     '''NAME_MAP = {}  # ns-3 vehicle index -> SUMO vehicle id (from --node-map)


def label_names(msg):
    """'Vehicle6 broke down' -> 'Vehicle6 (veh4) broke down' (display only)."""
    if not NAME_MAP:
        return msg
    import re
    return re.sub(r"\\bVehicle(\\d+)\\b",
                  lambda m: f"Vehicle{m.group(1)} ({NAME_MAP.get(int(m.group(1)), '?')})", msg)


def run_dashboard():'''),
    ("event_queue.put((t, text))",
     "event_queue.put((t, label_names(text)))"),
    ('''                     help="disable the Tk event dashboard window")
    args = ap.parse_args()''',
     '''                     help="disable the Tk event dashboard window")
    ap.add_argument("--node-map", default=None,
                     help="<scenario>_node_map.csv: show SUMO names next to ns-3 names in the events window")
    args = ap.parse_args()
    if args.node_map:
        import csv
        for r in csv.DictReader(open(args.node_map)):
            NAME_MAP[int(r["ns3_node_index"])] = r["sumo_vehicle_id"]
        print(f"[BRIDGE] Name map loaded: {len(NAME_MAP)} vehicles (events window shows ns-3 and SUMO names)")'''),
]
for old, new in edits:
    if s.count(old) != 1:
        sys.exit(f"STOPPED: expected text not found exactly once: {old[:50]!r} - nothing changed")
shutil.copy(p, p + ".bak_beforenames")
for old, new in edits:
    s = s.replace(old, new)
open(p, "w").write(s)
print("PATCHED OK (backup: sumo_bridge_server.py.bak_beforenames)")
