#!/bin/bash
set -u
H=$HOME; LC=$H/2026-09-26-livecosim; HW=$H/2026-09-22-10-36-12; T=$H/odd-tools
EX=$H/ndnsim-project/ws/ns-3/src/ndnSIM/examples
KEEP_RUNS="fresh_v1 fresh_v2 baseline_none baseline_boost clean_check2 transit_v1"
DEL_RUNS="full300 full400 full600 regress600 final_live600 final_live600b final_live600_gui final_costfix final_costfix_b final_guard_gui final_demo_gui final_traffic_gui final_B_gui clean_check transit_v2"
DEL_DIRS="$H/highway_fix_results $H/highway_fix2_results $H/highway_fix3_results $H/highway_ferry_results $H/highway_carry_results $H/urban-odd-400/results_baseline600_run1"
KEEP_LOGS="highway_fresh_v1.txt highway_fresh_v2.txt highway_baseline_none.txt highway_baseline_boost.txt highway_clean_check2.txt highway_transit_v1.txt highway_final_B_gui.txt"

echo "=== WILL DELETE (superseded results) ==="
for r in $DEL_RUNS; do du -sh $LC/results_$r 2>/dev/null; done
for d in $DEL_DIRS; do du -sh $d 2>/dev/null; done
echo "=== WILL PACK INTO ~/archive_highway_dev_20260930.tar.gz, THEN REMOVE ==="
echo "old run logs in home, engine backups (except FINAL_FRESH), bridge test files, patch scripts"
echo "=== WILL NOT TOUCH ==="
echo "~/ndnSIM, ~/ndnsim-project (except engine backups), August folders, netanim, snap, builds,"
echo "urban-odd-400 and urban-odd-final input files, kept results: $KEEP_RUNS"
read -p "Type YES to continue: " a; [ "$a" = "YES" ] || { echo "Stopped, nothing changed."; exit 1; }
echo "Before:"; df -h ~ | tail -1

# 1. archive
A=$H/archive_highway_dev_20260930.tar.gz
cd $H
LOGS=$(ls highway_*.txt livecosim_*.txt urban_*.txt urban400_*.txt bridge_*.log urban_*.log 2>/dev/null)
ENG=$(cd $EX && ls ndn-town-odd.cpp.*)
BRT=$(cd $LC && ls test_bridge_client*.py sumo_bridge_server.py.* bridge_*.log 2>/dev/null)
PAT=$(cd $T && ls patch_*.py cleanup_engine.py 2>/dev/null)
tar czf $A $LOGS -C $EX $ENG -C $LC $BRT -C $T $PAT || { echo "ARCHIVE FAILED - stopped, nothing removed"; exit 1; }
N=$(tar tzf $A | wc -l); echo "Archive: $A ($N files, $(du -h $A | cut -f1))"
[ "$N" -gt 50 ] || { echo "Archive looks too small - stopped, nothing removed"; exit 1; }

# 2. remove what is archived (keeping the final logs and FINAL_FRESH)
for f in $LOGS; do case " $KEEP_LOGS bridge_final_B.log " in *" $f "*) ;; *) rm -f "$H/$f";; esac; done
for f in $ENG; do [ "$f" = "ndn-town-odd.cpp.FINAL_FRESH_20260930" ] || rm -f "$EX/$f"; done
for f in $BRT; do rm -f "$LC/$f"; done; rm -rf $LC/__pycache__
for f in $PAT; do rm -f "$T/$f"; done

# 3. delete superseded results
for r in $DEL_RUNS; do rm -rf "$LC/results_$r"; done
for d in $DEL_DIRS; do rm -rf "$d"; done

# 4. clean project folder (copies; everything still runs from the original places)
F=$H/ndn-vanet-final
mkdir -p $F/engine $F/bridge $F/tools $F/highway/sumo $F/highway/data $F/highway/results $F/urban $F/rural
cp $EX/ndn-town-odd.cpp $F/engine/
cp $LC/sumo_bridge_server.py $F/bridge/
cp $T/*.py $T/*.sh $F/tools/ 2>/dev/null
cp $HW/*.py $F/tools/ 2>/dev/null
cp $LC/osm.* $LC/output.add.xml $LC/highway_rsu_markers_only.add.xml $F/highway/sumo/ 2>/dev/null
cp $HW/*.csv $HW/*.tcl $HW/*.json $HW/highway_*.xml $F/highway/data/ 2>/dev/null
for r in $KEEP_RUNS; do
  d=$F/highway/results/$r; mkdir -p $d
  cp $H/highway_$r.txt $d/run_log.txt 2>/dev/null
  cp $LC/results_$r/per_vehicle.csv $d/ 2>/dev/null
  { python3 $T/compute_metrics.py $LC/results_$r highway
    python3 $T/requester_report.py $H/highway_$r.txt $LC/results_$r highway $HW/highway_node_map.csv 4; } > $d/summary.txt 2>&1
done
python3 $T/compare_runs.py 160.8 354.1 4 "A-no-recovery:baseline_none" "B-range-boost:baseline_boost" \
  "C-VCF:clean_check2" "D-VCF-transit-final:fresh_v1" > $F/highway/results/comparison_failure_window.txt 2>&1
cat > $F/README.md <<'README'
# NDN-VANET with Vehicle Carry-and-Forward (VCF) -- ODD scenarios

All vehicle and RSU communication is Named Data Networking (ndnSIM). SUMO drives
the vehicles live through a small TCP bridge (tool link only, not part of the network).

## Versions
ns-3.35 with ndnSIM, SUMO 1.27.1 (TraCI), Python 3. Tested on Ubuntu 26.04 (VM, 4.3 GB RAM).

## Layout
engine/   ndn-town-odd.cpp   -- simulation engine (goes in ns-3/src/ndnSIM/examples/)
bridge/   sumo_bridge_server.py -- live SUMO <-> ns-3 bridge, hazard reactions, events window
tools/    run_live.sh, compute_metrics.py, requester_report.py, vehicle_report.py,
          compare_runs.py, rsu_grid_placement.py, precompute_*.py, inject_breakdowns.py
highway/  sumo/ (SUMO scenario), data/ (RSUs, failures, contact windows, hazards),
          results/ (final run, repeat, baselines A/B/C, failure-window comparison)
urban/, rural/  -- same structure (in progress)

## Build (optimized)
cd ns-3
WAFLOCK=.lock-waf_linux_build-opt ./waf configure -d optimized --enable-examples --disable-python --out=build-opt
WAFLOCK=.lock-waf_linux_build-opt ./waf build -j2 --targets=ndn-town-odd

## Run the highway scenario (600 s)
Terminal 1:  python3 -u bridge/sumo_bridge_server.py --sumocfg highway/sumo/osm.sumocfg --end 600 [--sumo-binary sumo --no-dashboard]
Terminal 2:  tools/run_live.sh <tag>                      # final scheme
             tools/run_live.sh <tag> --vcf=false --rangeBoost=false   # baseline A: no recovery
             tools/run_live.sh <tag> --vcf=false                      # baseline B: range-boost only
Results are deterministic: repeated runs give byte-identical tracer files.

## Final highway results (600 s, 2 of 4 RSUs failing)
ISR 98.25 % (RSU backbone 98.83 %, vehicles 96.55 %), LastDelay 39.8 ms, FullDelay 0.22 s,
45/45 data ferries, 8/8 transit ferries, 0 range-boost uses, 6/6 routes restored.
See highway/results/ and the scenario report for the full tables.
README
echo; echo "Done. After:"; df -h ~ | tail -1
echo "Clean project folder:"; du -sh $F; ls -R $F | head -60
