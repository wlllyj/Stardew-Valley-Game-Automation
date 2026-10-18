# -*- coding: utf-8 -*-
"""task-18 冒烟步骤简报：从 scratch/smoke-0745.json 抽出 8 步 name/verdict/reason + evidence 关键值。只读。"""
import json
import os

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(REPO, "scratch", "smoke-0745.json")
OUT = os.path.join(REPO, "scratch", "_t18_steps_brief.txt")

d = json.load(open(SRC, encoding="utf-8"))
out = []
out.append("keys=%s" % sorted(d.keys()))
out.append("phases_run=%s" % json.dumps(d.get("phases_run"), ensure_ascii=False))
out.append("expect=%s journal=%s smapi=%s" % (d.get("expect_version"), d.get("journal"), d.get("smapi")))
steps = d.get("results_all_steps") or d.get("steps") or []
out.append("n_steps=%d" % len(steps))
for st in steps:
    out.append("")
    out.append("== step %s verdict=%s name=%s" % (st.get("step"), st.get("verdict"), st.get("name")))
    out.append("reason=%s" % st.get("reason"))
    ev = st.get("evidence") or {}
    if not isinstance(ev, dict):
        out.append("evidence=%s" % json.dumps(ev, ensure_ascii=False)[:2000])
        continue
    for k in sorted(ev.keys()):
        v = ev[k]
        s = json.dumps(v, ensure_ascii=False)
        if len(s) > 2500:
            s = s[:2500] + "...<truncated>"
        out.append("  %s = %s" % (k, s))

text = "\n".join(out) + "\n"
with open(OUT, "w", encoding="utf-8", newline="\n") as f:
    f.write(text)
print("WROTE", OUT, len(text), "chars")
