#!/bin/bash
# usage: full_report.sh <highway|urban|rural> <tag>   -- all metrics after a run
SC=$1; TAG=$2; L=~/${SC}_${TAG}.txt
case $SC in
  highway) R=~/2026-09-26-livecosim/results_$TAG; NR=4;   F=~/2026-09-22-10-36-12/highway_rsu_failures.csv ;;
  urban)   R=~/urban-odd-400/results_$TAG;       NR=114; F=~/urban-odd-400/urban_rsu_failures.csv ;;
  rural)   R=~/rural-odd/results_$TAG;           NR=19;  F=~/rural-odd/rural_rsu_failures.csv ;;
esac
[ -n "$FAILS" ] && F=$FAILS   # optional: other failure file (multi-seed)
echo; echo "=================== FULL REPORT: $SC $TAG ==================="
echo "--- mechanism counts"
for k in "PIT-EXPIRED" "VCF-FERRY\] Vehicle" "FERRY-DELIVERY\]" "FERRY-DELIVERY-SKIPPED" "TRANSIT-FERRY\] Vehicle" "TRANSIT-FERRY\] No carrier" \
         "RANGE-BOOST-TRIGGERED" "RANGE-BOOST-END" "DETOUR\]" "DETOUR-END" "RECOVERY-PRIMARY" "LAST-MILE-RELAY\]" "LAST-MILE-FAILED" "breaks down" "HAZARD-RECEIVED"; do
  printf "  %-28s %s\n" "$k" "$(grep -c "$k" $L)"; done
echo "--- network level"
python3 ~/odd-tools/compute_metrics.py $R $SC
echo "--- application level"
python3 ~/odd-tools/app_metrics.py $R $SC $NR $F | tail -n +2
echo "--- information age (requesters)"
grep "\[TRAFFIC-UPDATE\]" $L | sed -E 's/.*age ([0-9.e-]+)s.*/\1/' | sort -g | \
  awk '{a[NR]=$1} END{if(NR){printf "  updates=%d  median=%.2fs  p95=%.2fs  max=%.2fs\n",NR,a[int(NR*0.5)+1],a[int(NR*0.95)+1],a[NR]}}'
grep "\[TRAFFIC-UPDATE\]" $L | sed -E 's/.*age ([0-9.e-]+)s.*/\1/' | awk '$1>2{c++} END{print "  updates older than 2 s:", c+0}'
echo "--- first ferries / transit"
grep "VCF-FERRY\] Vehicle" $L | head -3; grep "TRANSIT-FERRY" $L | head -4
