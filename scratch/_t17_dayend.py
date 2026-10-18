#!/usr/bin/env python
"""task-17 scratch: compact dump of day_end records (read-only)."""
import json
import pathlib

J = pathlib.Path('logs/longrun-smoke-0744.jsonl')
rows = []
for i, line in enumerate(J.read_text(encoding='utf-8').splitlines(), 1):
    line = line.strip()
    if not line:
        continue
    rows.append((i, json.loads(line)))

for i, ev in rows:
    if ev.get('event') != 'day_end':
        continue
    print('=' * 20, 'day_end line', i, ev.get('day_text'))
    keys = [k for k in ev.keys() if k not in ('plots', 'stages')]
    for k in keys:
        print(f'  {k} = {json.dumps(ev.get(k), ensure_ascii=False)}')
    print('  plots: n=', len(ev.get('plots') or []))
    for p in (ev.get('plots') or [])[:30]:
        print('    plots[]:', json.dumps({k: v for k, v in p.items() if k != 'note'}, ensure_ascii=False),
              '| note:', (p.get('note') or '')[:80])
    print('  stages: n=', len(ev.get('stages') or []))
    for st in (ev.get('stages') or []):
        print('    stage:', json.dumps({k: st.get(k) for k in (
            'stage', 'zone', 'tiles', 'ok', 'skipped', 'failed', 'already', 'unreachable',
            'encircled', 'assigned', 'assigned_undone', 'leftover', 'leftover_executable',
            'leftover_blocked', 'alloc_capped_tiles', 'stopped')}, ensure_ascii=False))
