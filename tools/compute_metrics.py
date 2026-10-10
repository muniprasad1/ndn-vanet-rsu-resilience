#!/usr/bin/env python3
"""ISR / delays from ndnSIM tracer CSVs (streams line by line; safe for multi-GB files).
usage: compute_metrics.py <results_dir> <scenario>"""
import sys, os
d, sc = sys.argv[1], sys.argv[2]
sat = tout = 0
with open(os.path.join(d, f"{sc}_metrics_l3_rate.csv")) as f:
    hdr = f.readline().rstrip("\n").split("\t")
    iD, iT, iP = hdr.index("FaceDescr"), hdr.index("Type"), hdr.index("PacketRaw")
    for line in f:
        c = line.rstrip("\n").split("\t")
        if c[iD] == "internal://":   # NFD's own management Interests: not app traffic
            if c[iT] == "InSatisfiedInterests": sat -= float(c[iP])
            elif c[iT] == "InTimedOutInterests": tout -= float(c[iP])
            continue
        if c[iD] != "all": continue
        if c[iT] == "SatisfiedInterests": sat += float(c[iP])
        elif c[iT] == "TimedOutInterests": tout += float(c[iP])
ld = fd = 0.0; nl = nf = 0
with open(os.path.join(d, f"{sc}_metrics_app_delays.csv")) as f:
    hdr = f.readline().rstrip("\n").split("\t")
    iT, iS = hdr.index("Type"), hdr.index("DelayS")
    for line in f:
        c = line.rstrip("\n").split("\t")
        if c[iT] == "LastDelay": ld += float(c[iS]); nl += 1
        elif c[iT] == "FullDelay": fd += float(c[iS]); nf += 1
tot = sat + tout
print(f"SatisfiedInterests: {sat:.0f}   TimedOutInterests: {tout:.0f}")
print(f"ISR: {100*sat/tot:.2f}%" if tot else "ISR: n/a")
print(f"LastDelay avg: {1000*ld/nl:.3f} ms  (n={nl})" if nl else "LastDelay: n/a")
print(f"FullDelay avg: {fd/nf:.3f} s  (n={nf})" if nf else "FullDelay: n/a")
