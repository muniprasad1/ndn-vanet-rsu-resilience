#!/bin/bash
# usage: [DUR=600] run_odd.sh <highway|urban|rural> <tag> [extra engine options, e.g. --vcf=false]
# The bridge for that scenario must already be "Listening" on 9001.
SC=${1:?scenario}; TAG=${2:?tag}; shift 2; EXTRA="$*"; DUR=${DUR:-600}
DBG=""; [ "${GDB:-0}" = 1 ] && DBG="gdb -batch -ex run -ex bt --args"
case $SC in
  highway) D=~/2026-09-22-10-36-12; HZ=$D/hazard_events.csv; NV=243; NR=4; OPT="";
           L=~/highway_${TAG}.txt; R=~/2026-09-26-livecosim/results_${TAG} ;;
  urban)   D=~/urban-odd-400; HZ=$D/urban_hazard_events.csv; NV=400; NR=114; OPT="--rsuNeighbourRange=600";
           L=~/urban_${TAG}.txt; R=~/urban-odd-400/results_${TAG}; ulimit -v 4000000 ;;
  rural)   D=~/rural-odd; HZ=$D/rural_hazard_events.csv; NV=151; NR=19; OPT="--rsuNeighbourRange=2000";
           L=~/rural_${TAG}.txt; R=~/rural-odd/results_${TAG} ;;
  *) echo "unknown scenario $SC"; exit 1 ;;
esac
cd ~/ndnsim-project/ws/ns-3
if ! ss -ltn | grep -q ":9001 "; then
  echo "ERROR: the bridge is not listening on port 9001 yet (start it in Terminal 1 with the $SC sumocfg)."; exit 1
fi
BR=$(pgrep -af sumo_bridge_server.py | head -1)
case $SC in
  urban)   echo "$BR" | grep -q "urban-odd-400" || { echo "ERROR: the running bridge is not the URBAN one: $BR"; exit 1; } ;;
  rural)   echo "$BR" | grep -q "rural-odd" || { echo "ERROR: the running bridge is not the RURAL one: $BR"; exit 1; } ;;
  highway) echo "$BR" | grep -q "urban-odd-400\|rural" && { echo "ERROR: the running bridge is not the HIGHWAY one: $BR"; exit 1; } ;;
esac
rm -f ${SC}_hazard_node*_delays.csv ${SC}_metrics_*.csv ${SC}_animation.xml
echo "[run_odd] $SC tag=$TAG duration=${DUR}s vehicles=$NV RSUs=$NR $OPT $EXTRA"
( /usr/bin/time -v env LD_LIBRARY_PATH=$PWD/build-opt/lib $DBG ./build-opt/src/ndnSIM/examples/ns3.35-ndn-town-odd-optimized \
  --scenario=$SC --rsuList=$D/${SC}_rsu_rsulist.csv --failureSchedule=${FAILS:-$D/${SC}_rsu_failures.csv} \
  --candidateLinks=$D/${SC}_candidate_links.csv --v2vLinks=$D/${SC}_v2v_links.csv \
  --hazardEvents=$HZ --nodeMap=$D/${SC}_node_map.csv \
  --numVehicles=$NV --simDuration=$DUR --numRandomRequesters=10 $OPT \
  --liveCoSim=true --bridgeHost=127.0.0.1 --bridgePort=9001 --bridgeStepInterval=1.0 $EXTRA ) > $L 2>&1
if ! grep -q "simulation complete" $L; then
  echo "!!! Simulation did not complete. Last lines of $L:"; tail -20 $L; exit 1
fi
mkdir -p $R; mv ${SC}_hazard_node*_delays.csv ${SC}_metrics_*.csv ${SC}_animation.xml $R/ 2>/dev/null
echo "=================== RESULTS: $SC $TAG ==================="
grep -E "Maximum resident|Elapsed \(wall" $L
grep -E "RSU-BACKBONE|FAILURE-SCHEDULED" $L | head -12
for k in "VCF-FERRY\] Vehicle" "FERRY-DELIVERY\]" "FERRY-DELIVERY-SKIPPED" "TRANSIT-FERRY\] Vehicle" "TRANSIT-FERRY\] No carrier" "RANGE-BOOST\]" "RECOVERY-PRIMARY" "PIT-EXPIRED" "LAST-MILE-RELAY\]" "LAST-MILE-FAILED" "breaks down" "HAZARD-RECEIVED"; do
  printf "%-28s %s\n" "$k" "$(grep -c "$k" $L)"; done
grep "routing overhead" $L
du -sh $R
python3 ~/odd-tools/compute_metrics.py $R $SC
python3 ~/odd-tools/requester_report.py $L $R $SC $D/${SC}_node_map.csv $NR
python3 ~/odd-tools/vehicle_report.py $L $R $SC $D/${SC}_node_map.csv $NR | tail -12
