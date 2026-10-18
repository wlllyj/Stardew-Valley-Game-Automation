#!/usr/bin/env python
"""task-13 scratch: A8 ledger field census (read-only)."""
import json
import pathlib
from collections import Counter

J = pathlib.Path('logs/longrun-runA8-0743.jsonl')
rows = []
bad = 0
for line in J.read_text(encoding='utf-8').splitlines():
    line = line.strip()
    if not line:
        continue
    try:
        rows.append(json.loads(line))
    except json.JSONDecodeError:
        bad += 1
print('lines', len(rows), 'bad', bad)

stages = []
resume_walks = 0
resume_walk_switched = Counter()
blocked_actions = Counter()
stage_realloc = []
plot_exhausted_src = Counter()
npb_src = Counter()
day_end_keys = Counter()
stage_keys = Counter()
for ev in rows:
    if ev.get('event') == 'day_end':
        for k in ev:
            day_end_keys[k] += 1
        for st in ev.get('stages') or []:
            if isinstance(st, dict):
                stages.append(st)
                for k in st:
                    stage_keys[k] += 1
    elif ev.get('event') == 'resume_walk':
        resume_walks += 1
        if 'switched' in ev:
            resume_walk_switched[ev['switched']] += 1
        else:
            resume_walk_switched['<缺失>'] += 1
    elif ev.get('event') == 'blocked':
        blocked_actions[ev.get('action')] += 1
        if ev.get('action') == 'stage_realloc':
            stage_realloc.append(ev)
    elif ev.get('event') == 'plot_exhausted':
        plot_exhausted_src[ev.get('source')] += 1
    elif ev.get('event') == 'no_progress_burst':
        npb_src[ev.get('source')] += 1

print('stages', len(stages), 'stage_keys', dict(stage_keys))
print('day_end_keys', dict(day_end_keys))
print('resume_walks', resume_walks, 'switched', dict(resume_walk_switched))
print('blocked_actions', dict(blocked_actions))
print('stage_realloc', len(stage_realloc))
for ev in stage_realloc[:5]:
    print('  ', json.dumps({k: ev.get(k) for k in ('tile', 'stage', 'alloc_no_progress', 'limit', 'reason')}, ensure_ascii=False))
print('plot_exhausted_src', dict(plot_exhausted_src))
print('npb_src', dict(npb_src))

# ok==0 && already>0
z = [st for st in stages if (st.get('ok') or 0) == 0 and (st.get('already') or 0) > 0]
print('stages ok==0 already>0:', len(z))
for st in z[:8]:
    print('  ', json.dumps({k: st.get(k) for k in ('stage', 'ok', 'already', 'assigned', 'leftover', 'stopped')}, ensure_ascii=False))
