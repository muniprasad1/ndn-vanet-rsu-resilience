#!/bin/bash
# usage: watch_run.sh <highway|urban|rural> <tag>   -- live event log of a running simulation
L=~/${1}_${2}.txt
echo "waiting for $L ..."; while [ ! -f $L ]; do sleep 1; done
tail -n +1 -F $L | grep --line-buffered -E \
 "FAILURE-SCHEDULED|PIT-EXPIRED|VCF-FERRY\]|FERRY-DELIVERY|TRANSIT-FERRY|RANGE-BOOST-TRIGGERED|RANGE-BOOST-END|DETOUR|RECOVERY-PRIMARY|LAST-MILE|breaks down|HAZARD|TRAFFIC-UPDATE|REQUEST|simulation complete"
