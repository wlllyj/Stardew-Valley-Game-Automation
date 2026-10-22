# -*- coding: utf-8 -*-
"""T5.1 extra: 0.7.47-era analyzer red detail + line130 raw (UTF-8 safe)."""
import json
import pathlib

repo = pathlib.Path(r"D:\OpenCode Workspace\星露谷游戏自动化")

raw = (repo / "scratch" / "_t5_analyze_0747.json").read_bytes()
d = json.loads(raw.decode("utf-16"))
print("0747 analyzer red.total=", d["red"]["total"], "subjects=", d["red"]["subjects"], "lines=", d["red"]["lines"])
print("0747 top keys=", list(d.keys()))
print("0747 has slot_relief key?", "slot_relief" in d)

ls = (repo / "logs" / "longrun-smoke-0746.jsonl").read_text(encoding="utf-8").splitlines()
o = json.loads(ls[129])
print("line130 keys=", list(o.keys()))
print("line130 day=", o.get("day"), "verified=", o.get("verified"))
print("line130 coverage=", str(o.get("coverage"))[:400])
print("line130 missed=", str(o.get("missed"))[:400])
print("line130 unmet=", str(o.get("unmet"))[:300])
print("line130 raw=", ls[129][:900])
