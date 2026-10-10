#!/usr/bin/env python3
"""Write a copy of an engine log with SUMO names added next to ns-3 vehicle names.
usage: name_log.py <engine log> <scenario>_node_map.csv
   ->  <engine log without .txt>.named.txt   (the original log is not changed)"""
import sys, csv, re
log, nm = sys.argv[1], sys.argv[2]
names = {int(r["ns3_node_index"]): r["sumo_vehicle_id"] for r in csv.DictReader(open(nm))}
out = (log[:-4] if log.endswith(".txt") else log) + ".named.txt"
pat = re.compile(r"\bVehicle(\d+)\b")
n = 0
with open(log, errors="replace") as fi, open(out, "w") as fo:
    for line in fi:
        new = pat.sub(lambda m: f"Vehicle{m.group(1)} ({names.get(int(m.group(1)), '?')})", line)
        n += new != line
        fo.write(new)
print(f"{out}: {n} lines with vehicle names labelled ({len(names)} vehicles in map)")
