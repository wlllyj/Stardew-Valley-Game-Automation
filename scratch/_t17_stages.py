#!/usr/bin/env python
"""task-17 scratch: stage record key census + coordinate arrays (read-only)."""
import json
import pathlib

J = pathlib.Path('logs/longrun-smoke-0744.jsonl')
rows = []
for i, line in enumerate(J.read_text(encoding='utf-8').splitlines(), 1):
    line = line.strip()
    if line:
        rows.append((i, json.loads(line)))

for i, ev in rows:
    if ev.get('event') != 'day_end':
        continue
    print('=' * 20, 'day_end line', i, ev.get('day_text'))
    stages = ev.get('stages') or []
    print('stages:', len(stages))
    for idx, st in enumerate(stages):
        keys = sorted(st.keys())
        if idx == 0:
            print('stage keys:', keys)
            print('sample:', json.dumps(st, ensure_ascii=False)[:3000])
        print(idx, json.dumps({k: st.get(k) for k in (
            'stage', 'tiles', 'ok', 'already', 'already_tiles', 'unreachable',
            'unreachable_tiles', 'encircled', 'encircled_tiles', 'failed',
            'failed_tiles', 'unexecuted_tiles', 'assigned', 'assigned_undone',
            'leftover', 'leftover_executable', 'leftover_blocked', 'leftover_tiles',
            'alloc_capped_tiles', 'stopped')}, ensure_ascii=False))
