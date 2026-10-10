# Resilient NDN for VANETs under Roadside Unit Backbone Failures

Simulation code, scenarios and results for the paper
"Resilient named data networking for vehicular ad hoc networks under roadside unit backbone failures".

An RSU loses its wired backbone while its radio keeps working. A resilience module in every NDN node
detects the failure from expired Interests and repairs it with vehicle data ferries, transit ferries,
15 s range-boost bursts, loop-free detours and recovery to the primary route. SUMO drives the vehicles
live through a TCP bridge every second; all vehicle and RSU communication is NDN (ndnSIM).

## Software versions
- ns-3.35 with ndnSIM 2.9 (NFD 22.02)
- SUMO 1.27.1 (TraCI), Python 3
- Tested on Ubuntu 26.04 (VirtualBox VM, 4.3 GB RAM)

## Folder layout
- engine/      ndn-town-odd.cpp (simulation engine) and nfd_pit_fix.patch (fix for a double PIT erase in NFD)
- bridge/      sumo_bridge_server.py (live SUMO <-> ns-3 bridge, breakdowns, hazard reactions)
- tools/       scenario preparation, run scripts and metric scripts
- highway/, urban/, rural/   sumo/ (SUMO scenario), data/ (RSUs, failures, contact windows, hazards),
               osm_source/ (OpenStreetMap extract), results/ (reference and comparison runs), logs/
- multiseed/   results of all 75 runs (3 scenarios x 5 configurations x 5 seeds) and each seed's failure file

## Build
1. Copy engine/ndn-town-odd.cpp to ns-3/src/ndnSIM/examples/
2. Apply the NFD fix inside ns-3/src/ndnSIM/NFD:

       git apply /path/to/engine/nfd_pit_fix.patch

3. Build the optimized version inside ns-3:

       WAFLOCK=.lock-waf_linux_build-opt ./waf configure -d optimized --enable-examples --disable-python --out=build-opt
       WAFLOCK=.lock-waf_linux_build-opt ./waf build -j2 --targets=ndn-town-odd

## Run one scenario (600 s)
Terminal 1 (start a fresh bridge for every run):

       python3 -u bridge/sumo_bridge_server.py --sumocfg <scenario>/sumo/osm.sumocfg --end 600 --sumo-binary sumo

Terminal 2 (engine):

       tools/run_odd.sh <scenario> <tag>                                                 # D: full system
       tools/run_odd.sh <scenario> <tag> --rangeBoost=false                              # C: ferries only
       tools/run_odd.sh <scenario> <tag> --vcf=false                                     # B: boost only
       tools/run_odd.sh <scenario> <tag> --vcf=false --rangeBoost=false                  # A: detour only
       tools/run_odd.sh <scenario> <tag> --vcf=false --rangeBoost=false --detour=false   # E: plain NDN

Note: the scripts use the folder paths of the original machine; edit the paths at the top of
tools/run_odd.sh and tools/multiseed.sh to match your folders.

## Five-seed evaluation
tools/multiseed.sh runs the five configurations for each seed (fresh bridge per run, --RngRun selects
the requesters, multiseed/<scenario>/failures/ holds the failure file of each seed).
tools/ms_aggregate.py <scenario> reads multiseed/<scenario>/mf_s<seed>_<run>.summary.txt and prints the
per-seed values and averages used in the paper. Seed 1 is the reference run.

## Metrics
- tools/compute_metrics.py: Interest Satisfaction Ratio, LastDelay and FullDelay (NFD internal:// names excluded)
- tools/app_metrics.py: first-try success and waiting time, including the rows
  "RSU on a FAILED RSU, during its outage" and "Requesters in failure window"

## Scenario preparation (already done; all files are included)
OpenStreetMap export -> netconvert -> trips with randomTrips.py --validate -> RSU placement
(rsu_grid_placement.py, generate_rsu_config.py) -> SUMO position trace -> contact windows
(precompute_candidate_links.py, precompute_v2v_links.py) -> failures (make_failures.py) ->
breakdowns (inject_breakdowns.py)

## Reproducibility
Runs are deterministic: repeating a run gives byte-identical tracer files.

## Data licence
Map data (c) OpenStreetMap contributors, available under the Open Database License (ODbL).
