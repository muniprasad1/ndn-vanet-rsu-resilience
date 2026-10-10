#!/usr/bin/env python3
"""Compare runs inside the RSU-failure window.
usage: compare_runs.py [scenario] <t0> <t1> <num_rsus> label:tag [label:tag ...]
scenario defaults to highway (older call without it still works)."""
import sys, os, re
a = sys.argv[1:]
sc = "highway"
if not re.match(r"^[\d.]+$", a[0]): sc = a.pop(0)
t0, t1, nr = float(a[0]), float(a[1]), int(a[2])
H = os.path.expanduser("~")
base = {"highway": f"{H}/2026-09-26-livecosim", "urban": f"{H}/urban-odd-400"}[sc]
rows = []
for arg in a[3:]:
    label, tag = arg.split(":", 1)
    d = f"{base}/results_{tag}"; log = f"{H}/{sc}_{tag}.txt"
    req = set()
    for line in open(log):
        m = re.search(r"\[RANDOM-REQUESTS\] Vehicle(\d+) requesting", line)
        if m: req.add(int(m.group(1)) + nr)
    grp = lambda n: "bb" if n < nr else ("rq" if n in req else None)
    ans = {"bb": 0, "rq": 0}; full = {"bb": 0.0, "rq": 0.0}; tout = {"bb": 0.0, "rq": 0.0}
    with open(f"{d}/{sc}_metrics_app_delays.csv") as f:
        h = f.readline().rstrip("\n").split("\t"); iT, iN, iY, iS = h.index("Time"), h.index("Node"), h.index("Type"), h.index("DelayS")
        for line in f:
            c = line.rstrip("\n").split("\t"); t = float(c[iT]); g = grp(int(c[iN]))
            if g and t0 <= t <= t1:
                if c[iY] == "LastDelay": ans[g] += 1
                elif c[iY] == "FullDelay": full[g] += float(c[iS])
    with open(f"{d}/{sc}_metrics_l3_rate.csv") as f:
        h = f.readline().rstrip("\n").split("\t"); iT, iN, iD, iY, iP = h.index("Time"), h.index("Node"), h.index("FaceDescr"), h.index("Type"), h.index("PacketRaw")
        for line in f:
            c = line.rstrip("\n").split("\t"); t = float(c[iT]); g = grp(int(c[iN]))
            if not g or not (t0 <= t <= t1): continue
            if c[iD] == "all" and c[iY] == "TimedOutInterests": tout[g] += float(c[iP])
            elif c[iD] == "internal://" and c[iY] == "InTimedOutInterests": tout[g] -= float(c[iP])
    rows.append((label, ans, tout, full))
print(f"\n{sc}: inside the failure window {t0}-{t1} s:\n")
print(f"{'run':<22}{'backbone answers':>17}{'backbone ISR':>14}{'backbone wait':>15}{'requester answers':>19}{'requester ISR':>15}{'requester wait':>16}")
for label, an, t, fd in rows:
    isr = lambda g: 100 * an[g] / (an[g] + t[g]) if an[g] + t[g] else float("nan")
    w = lambda g: fd[g] / an[g] if an[g] else float("nan")
    print(f"{label:<22}{an['bb']:>17}{isr('bb'):>13.1f}%{w('bb'):>14.2f}s{an['rq']:>19}{isr('rq'):>14.1f}%{w('rq'):>15.2f}s")
