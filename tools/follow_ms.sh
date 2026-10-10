#!/bin/bash
# Live view of the multi-seed batch: follows the current run, switches automatically.
SC=${1:?scenario}
PAT="FAILURE|VCF-FERRY|FERRY-DELIVERY|TRANSIT-FERRY|RANGE-BOOST|DETOUR|RECOVERY|breaks down|HAZARD|TRAFFIC-UPDATE|simulation complete"
while true; do
  f=$(ls -t ~/${SC}_m?_s*.txt 2>/dev/null | head -1)
  if [ -z "$f" ]; then sleep 3; continue; fi
  done_n=$(ls ~/multiseed/$SC/m?_s*.summary.txt 2>/dev/null | wc -l)
  echo; echo "======== NOW RUNNING: $(basename $f .txt)   (finished so far: $done_n summaries incl. seed 1)"
  tail -n 20 -F "$f" 2>/dev/null | grep --line-buffered -E "$PAT" &
  while [ -e "$f" ]; do sleep 2; done
  pkill -f "tail -n 20 -F $f"; sleep 3
done
