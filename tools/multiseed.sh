#!/bin/bash
# Unattended multi-seed runs.  usage:  multiseed.sh <highway|urban|rural> <seed> [seed ...]
#   CFGS="D C B A E" (default) chooses which runs; seed = ns-3 --RngRun value.
#   Seed 1 = the existing final runs (default RngRun=1), so new seeds start at 2.
SC=${1:?scenario}; shift; SEEDS="$*"; [ -z "$SEEDS" ] && { echo "give seeds, e.g. 2 3 4 5"; exit 1; }
CFGS=${CFGS:-"D C B A E"}
OUT=~/multiseed/$SC; mkdir -p $OUT
PFX=ms; [ "${VARYFAIL:-0}" = 1 ] && PFX=mf   # mf = new requesters AND new failures
case $SC in
  highway) CFG=~/2026-09-26-livecosim/osm.sumocfg; NM=~/2026-09-22-10-36-12/highway_node_map.csv; RB=~/2026-09-26-livecosim ;;
  urban)   CFG=~/urban-odd-400/osm.sumocfg;        NM=~/urban-odd-400/urban_node_map.csv;          RB=~/urban-odd-400 ;;
  rural)   CFG=~/rural-odd/osm.sumocfg;            NM=~/rural-odd/rural_node_map.csv;              RB=~/rural-odd ;;
  *) echo "unknown scenario $SC"; exit 1 ;;
esac
flags() { case $1 in
  D) echo "" ;; C) echo "--rangeBoost=false" ;; B) echo "--vcf=false" ;;
  A) echo "--vcf=false --rangeBoost=false" ;; E) echo "--vcf=false --rangeBoost=false --detour=false" ;; esac; }
stop_all() { pkill -f sumo_bridge_server.py; pkill -9 -f sumo-gui; pkill -9 -x sumo; sleep 3; }
start_bridge() {
  stop_all
  ( cd ~/2026-09-26-livecosim && export PYTHONPATH=$SUMO_HOME/tools:$PYTHONPATH && \
    nohup python3 -u sumo_bridge_server.py --sumocfg $CFG --end 600 --sumo-binary sumo \
      --no-dashboard --node-map $NM > ~/multiseed/bridge_${SC}_$1.log 2>&1 & )
  for i in $(seq 90); do ss -ltn | grep -q ":9001 " && return 0; sleep 1; done
  echo "ERROR: bridge did not start for $1 (see ~/multiseed/bridge_${SC}_$1.log)"; return 1
}
old_tag() { case $SC:$1 in
  highway:D) echo fresh_v1 ;; highway:C) echo baseline_vcfonly ;; highway:B) echo final_B ;;
  highway:A) echo final_A ;;  highway:E) echo final_E ;;
  *:D) [ $SC = urban ] && echo final_v2 || echo final_v1 ;; *:C) echo baseline_vcfonly ;;
  *:B) echo baseline_boost ;; *:A) echo baseline_none ;; *:E) echo baseline_plain ;; esac; }
for c in D C B A E; do
  [ -s $OUT/${PFX}_s1_$c.summary.txt ] || ~/odd-tools/full_report.sh $SC $(old_tag $c) > $OUT/${PFX}_s1_$c.summary.txt 2>&1
done
echo "[multiseed] $SC seeds: $SEEDS   runs: $CFGS   ($(date))"
for s in $SEEDS; do
  unset FAILS
  if [ $PFX = mf ]; then export FAILS=$OUT/failures/${SC}_rsu_failures_s$s.csv
    [ -s $FAILS ] || { echo "ERROR: missing $FAILS"; exit 1; }; echo "  seed $s failures: $(tail -n +2 $FAILS | cut -d, -f1 | tr '\n' ' ')"; fi
  for c in $CFGS; do
    TAG=${PFX}_s${s}_${c}
    if [ -s $OUT/$TAG.summary.txt ]; then echo "  skip $TAG (already done)"; continue; fi
    echo "=== $SC $TAG  ($(date +%H:%M:%S))"
    start_bridge $TAG || continue
    ~/odd-tools/run_odd.sh $SC $TAG $(flags $c) --RngRun=$s > $OUT/$TAG.run.txt 2>&1
    ~/odd-tools/full_report.sh $SC $TAG > $OUT/$TAG.summary.txt 2>&1
    grep -q "^ISR" $OUT/$TAG.summary.txt || { echo "  WARNING: no ISR in $TAG summary"; mv $OUT/$TAG.summary.txt $OUT/$TAG.FAILED.txt; }
    grep -A12 "Per random requester" $OUT/$TAG.run.txt | sed -n '3,4p' | sed 's/^/     requester: /'
    R=$RB/results_$TAG
    cp $R/per_vehicle.csv $OUT/$TAG.per_vehicle.csv 2>/dev/null
    gzip -c $R/${SC}_metrics_app_delays.csv > $OUT/$TAG.app_delays.csv.gz 2>/dev/null
    gzip -f ~/${SC}_${TAG}.txt 2>/dev/null && mv ~/${SC}_${TAG}.txt.gz $OUT/ 2>/dev/null
    rm -rf $R
  done
done
stop_all
echo "[multiseed] done ($(date)).  Table:  python3 ~/odd-tools/ms_aggregate.py $SC"
