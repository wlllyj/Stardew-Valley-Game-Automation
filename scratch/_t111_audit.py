"""task-111 只读审计：机械枚举 brain 的 journal 事件名 vs 本工具的 EVENT_BUCKETS。"""
import importlib.util
import os
import re

spec = importlib.util.spec_from_file_location("mod", "tools/analyze-longrun.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)

src = ""
for root, _dirs, files in os.walk("brain/agentfarm"):
    for f in sorted(files):
        if f.endswith(".py"):
            src += open(os.path.join(root, f), encoding="utf-8").read()

names = sorted(set(re.findall(r'_journal\(\s*"([a-z0-9_]+)"', src)))
unmapped = [n for n in names
            if n not in mod.EVENT_BUCKETS and n not in mod.STRUCTURAL_EVENTS]
print("brain_journal_names", len(names))
print("unmapped", unmapped)
print("structural", sorted(mod.STRUCTURAL_EVENTS))

for needle in ("review_llm", "review_llm_failed", "lessons", "lessons_load_failed",
               "lessons_save_failed", "recent_decisions", "recent_lessons",
               "recent_notes", "_lessons_path", "lessons_path"):
    hits = [(i, l.rstrip()) for i, l in
            enumerate(open("brain/agentfarm/longrun.py", encoding="utf-8"), 1)
            if needle in l]
    if hits:
        print(f"\n=== longrun.py :: {needle} ({len(hits)} hits) ===")
        for i, l in hits[:14]:
            print(f"  {i}: {l.strip()[:200]}")
for fname in ("planner.py", "farmwork.py"):
    path = os.path.join("brain/agentfarm", fname)
    if not os.path.exists(path):
        continue
    for needle in ("review_llm", "lessons", "recent_lessons", "recent_notes"):
        hits = [(i, l.rstrip()) for i, l in enumerate(open(path, encoding="utf-8"), 1)
                if needle in l]
        if hits:
            print(f"\n=== {fname} :: {needle} ({len(hits)} hits) ===")
            for i, l in hits[:10]:
                print(f"  {i}: {l.strip()[:200]}")
