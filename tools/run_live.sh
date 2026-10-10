#!/bin/bash
# usage: run_live.sh <tag>   (bridge must already be "Listening" on 9001)
TAG=${1:-run}; cd ~/ndnsim-project/ws/ns-3; H=~/2026-09-22-10-36-12
shift; EXTRA="$*"
L=~/highway_${TAG}.txt; R=~/2026-09-26-livecosim/results_${TAG}
if ! ss -ltn | grep -q ":9001 "; then
  echo "ERROR: the bridge is not listening on port 9001 yet."
  echo "Start it in Terminal 1, press Play in SUMO-GUI, wait for 'Listening ... 9001', then run this again."
  exit 1
fi
rm -f highway_hazard_node*_delays.csv highway_metrics_*.csv highway_animation.xml
LD_LIBRARY_PATH=$PWD/build-opt/lib ./build-opt/src/ndnSIM/examples/ns3.35-ndn-town-odd-optimized \
  --scenario=highway --rsuList=$H/highway_rsu_rsulist.csv --failureSchedule=$H/highway_rsu_failures.csv \
  --candidateLinks=$H/highway_candidate_links.csv --v2vLinks=$H/highway_v2v_links.csv \
  --hazardEvents=$H/hazard_events.csv --nodeMap=$H/highway_node_map.csv \
  --numVehicles=243 --simDuration=600 --numRandomRequesters=10 \
  --liveCoSim=true --bridgeHost=127.0.0.1 --bridgePort=9001 --bridgeStepInterval=1.0 $EXTRA 2>&1 \
  | tee $L \
  | grep --line-buffered -E "VCF-FERRY|TRANSIT-|FERRY-DELIVERY|RANGE-BOOST|RECOVERY-PRIMARY|FAILURE-SCHEDULED|PIT-EXPIRED|HAZARD|breaks down|LAST-MILE|RANDOM-REQUESTS|TRAFFIC-UPDATE|HAZARD-RECEIVED|\[REQUEST\]|simulation complete|routing overhead|ERROR|error|Error|abort|Assert"
if ! grep -q "simulation complete" $L; then
  echo; echo "!!! Simulation did not complete. Last lines of the full log ($L):"; tail -15 $L; exit 1
fi
mkdir -p $R; mv highway_hazard_node*_delays.csv highway_metrics_*.csv highway_animation.xml $R/ 2>/dev/null
echo; echo "=================== RESULTS: $TAG ==================="
for k in "VCF-FERRY\] Vehicle" "FERRY-DELIVERY\]" "FERRY-DELIVERY-SKIPPED" "RANGE-BOOST\]" "RECOVERY-PRIMARY" "PIT-EXPIRED" "LAST-MILE-RELAY\]" "HAZARD\]" "breaks down"; do printf "%-26s %s\n" "$k" "$(grep -c "$k" $L)"; done
grep "routing overhead" $L
python3 ~/odd-tools/compute_metrics.py $R highway
python3 ~/odd-tools/requester_report.py $L $R highway $H/highway_node_map.csv 4
python3 ~/odd-tools/vehicle_report.py $L $R highway $H/highway_node_map.csv 4
