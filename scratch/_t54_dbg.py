"""调试：为什么 forged 账本的 `journal 自算` = 0（真实 run6 却是 42）。

用 importlib 载入 `tools/verify-run3.py`（文件名带 `-`，不能普通 import），
复刻它自己的 unreachable 计数循环，打印会话键。
"""
from __future__ import annotations

import importlib.util
import inspect
import json
import sys

spec = importlib.util.spec_from_file_location("vr", r"tools\verify-run3.py")
vr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(vr)  # type: ignore[union-attr]

print("module funcs:", [n for n, o in vars(vr).items() if inspect.isfunction(o)])

path = sys.argv[1] if len(sys.argv) > 1 else r"scratch\review-t54-vacuum-all-unreachable.jsonl"
rows = vr.load_rows(path) if hasattr(vr, "load_rows") else None
if rows is None:
    rows = []
    with open(path, "r", encoding="utf-8") as fh:
        for i, line in enumerate(fh, 1):
            if line.strip():
                obj = json.loads(line)
                obj["_lineno"] = i
                rows.append(obj)
print("rows:", len(rows))
print("day_key(day_start):", vr.day_key(rows[0]))
print("day_key(day_end):", vr.day_key(rows[10]))

days = vr.build_days(rows)
print("days type:", type(days))
if isinstance(days, dict):
    print("days keys:", list(days.keys()))
    for k, v in days.items():
        print("  key:", k, "| start_lineno:", v.get("start_lineno"), "| name:", v.get("name"),
              "| stages:", len(v.get("stages") or []))
else:
    for d in days:
        print("  d['key']:", repr(d.get("key")), "| start_lineno:", repr(d.get("start_lineno")),
              "| end_lineno:", repr(d.get("end_lineno")))
        print("  day_start row:", json.dumps({k: v for k, v in d.items() if k not in ("end", "stages")},
                                             ensure_ascii=False)[:300])

MK = ("四邻都站不过去", "寻路无法到达", "无法到达", "unreachable", "A* 未算出路径")
cnt: dict = {}
cur = None
for r in rows:
    if r.get("event") == "day_start":
        cur = (vr.day_key(r), r.get("_lineno"))
        continue
    if cur is None or r.get("event") not in ("blocked", "stage_exhausted", "unreachable"):
        continue
    blob = " ".join(str(r.get(k) or "") for k in ("reason", "note", "tile", "tiles"))
    if any(m in blob for m in MK):
        cnt[cur] = cnt.get(cur, 0) + 1
print("self-compute keys:", cnt)

rows_cli = vr.load(path)
ok, summary = vr.report(rows_cli, target_days=1)
print("report ok:", ok)
for line in summary.get("infos", []):
    if "自算" in line:
        print("INFO:", line)
for line in summary.get("problems", []):
    print("PROBLEM:", line)
