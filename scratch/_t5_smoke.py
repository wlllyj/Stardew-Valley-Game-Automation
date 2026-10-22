# -*- coding: utf-8 -*-
"""T5.1: reproduce analyze/verify rc on the smoke-0746 journal + capture red detail (UTF-8 safe)."""
import json
import os
import subprocess
import sys
from pathlib import Path

PY = sys.executable
REPO = Path(r"D:\OpenCode Workspace\星露谷游戏自动化")
J = REPO / "logs" / "longrun-smoke-0746.jsonl"
env = {**os.environ, "PYTHONUTF8": "1"}

r = subprocess.run([PY, str(REPO / "tools" / "analyze-longrun.py"), "--journal", str(J),
                    "--days", "2", "--json"], capture_output=True, text=True,
                   encoding="utf-8", env=env)
(REPO / "scratch" / "_t5_smoke_analyze.json").write_text(r.stdout, encoding="utf-8")
d = json.loads(r.stdout)
print("analyze_rc=", r.returncode)
print("red.total=", d["red"]["total"])
print("red.subjects=", d["red"]["subjects"])
print("red.lines=", d["red"]["lines"])
print("slot_relief_block=", json.dumps(d.get("slot_relief"), ensure_ascii=False)[:400])

v = subprocess.run([PY, str(REPO / "tools" / "verify-run3.py"), "--journal", str(J), "--days", "2"],
                   capture_output=True, text=True, encoding="utf-8", env=env)
(REPO / "scratch" / "_t5_smoke_verify.txt").write_text(v.stdout + v.stderr, encoding="utf-8")
print("verify_rc=", v.returncode)
lines = [l for l in (v.stdout + v.stderr).splitlines() if l.strip()]
for l in lines[-8:]:
    print("  V|", l[:170])
