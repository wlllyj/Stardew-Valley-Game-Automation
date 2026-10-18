# task-13 文档读数：抓 A8 新版各聚合 + already 双列 + 头部新渲染行
import importlib.util
import json

spec = importlib.util.spec_from_file_location("m", "tools/analyze-longrun.py")
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)

A8 = "logs/longrun-runA8-0743.jsonl"
args = m.parse_args(["--days", "12"])
rows, bad = m.load_journal(A8)
r = m.build_report(rows, A8, args, bad)
print("red_total", r["red"]["total"], "history", r["red"]["history_total"],
      "settled", r["red"]["settled_total"], "subjects", len(r["red"]["subjects"]),
      "undec", len(r["undecidable"]), "window", json.dumps(r["window"], ensure_ascii=False)[:300])
print("bad_lines", r["bad_lines"], "lines", r["lines"])


def dump(key):
    d = r.get(key) or {}
    print("\n==", key)
    simple = {k: v for k, v in d.items() if not isinstance(v, (list, dict))}
    print(json.dumps(simple, ensure_ascii=False))
    for k, v in d.items():
        if isinstance(v, dict):
            print(" dict", k, "=", json.dumps(v, ensure_ascii=False)[:600])
    if "days" in d:
        for day in d["days"]:
            print(" day", day.get("label"), json.dumps(day, ensure_ascii=False)[:700])

for k in ("resume_exhausted", "stage_realloc", "leftover_split", "slept_ok",
          "budget_suppressed", "already_aware"):
    dump(k)

txt = m.render_text(r, 99)
print("\n== render head")
for line in txt.splitlines()[:42]:
    print(line)
