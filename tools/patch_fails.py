import re, shutil, sys
p1 = "/home/muni/odd-tools/run_odd.sh"; p2 = "/home/muni/odd-tools/full_report.sh"
s1 = open(p1).read(); s2 = open(p2).read()
if "FAILS" in s1 or "FAILS" in s2: sys.exit("already patched - nothing changed")
old1 = "--failureSchedule=$D/${SC}_rsu_failures.csv"
if s1.count(old1) != 1: sys.exit("STOPPED: run_odd.sh line not found - nothing changed")
if s2.count("esac") < 1 or not re.search(r"\bF=", s2): sys.exit("STOPPED: full_report.sh has no F= / esac - nothing changed")
shutil.copy(p1, p1 + ".bak_beforefails"); shutil.copy(p2, p2 + ".bak_beforefails")
open(p1, "w").write(s1.replace(old1, "--failureSchedule=${FAILS:-$D/${SC}_rsu_failures.csv}"))
i = s2.index("esac") + len("esac")
open(p2, "w").write(s2[:i] + '\n[ -n "$FAILS" ] && F=$FAILS   # optional: other failure file (multi-seed)' + s2[i:])
print("PATCHED OK (backups: *.bak_beforefails)")
