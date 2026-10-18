# -*- coding: utf-8 -*-
"""产品旁观审计：抽 decision/policy/review_llm/outcome/intent_verdict，做逐日表。只读。"""
import json, sys

path = sys.argv[1]
rows = []
with open(path, 'r', encoding='utf-8') as f:
    for i, line in enumerate(f, 1):
        line = line.strip()
        if not line:
            continue
        rows.append((i, json.loads(line)))

def show(i, r, keys=None):
    d = {k: r[k] for k in r if k not in ('t',)}
    print(f'--- L{i} ---')
    print(json.dumps(d, ensure_ascii=False, indent=1)[:4000])

want = sys.argv[2].split(',')
n = 0
for i, r in rows:
    if r.get('event') in want:
        show(i, r)
        n += 1
        if n >= int(sys.argv[3] if len(sys.argv) > 3 else 999):
            break
