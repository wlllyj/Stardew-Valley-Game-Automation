#!/usr/bin/env python
"""task-13 scratch: grep brain for new field writes."""
import pathlib

t = pathlib.Path('brain/agentfarm/longrun.py').read_text(encoding='utf-8').splitlines()
pats = ['already_cause', '"switched"', 'stalled_tiles', 'plot_exhausted',
        'deferred_by_budget_suppressed', 'resume_exhausted', 'alloc_capped_tiles',
        'plot_pending_executable']
for pat in pats:
    hits = [i + 1 for i, line in enumerate(t) if pat in line]
    print(f'{pat}: {len(hits)} {hits[:30]}')
