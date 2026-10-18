#!/usr/bin/env python
"""task-13 scratch: brain 0.7.44 write sites for leftover split / slept_ok / realloc."""
import pathlib

t = pathlib.Path('brain/agentfarm/longrun.py').read_text(encoding='utf-8').splitlines()
pats = ['leftover_executable', 'leftover_blocked', 'plot_pending_executable', 'plot_pending_blocked',
        'slept_ok', 'alloc_no_progress', 'assigned_undone', 'deferred_by_budget_suppressed',
        'def _flush_budget_deferrals', 'def _realloc', 'stage_realloc']
for pat in pats:
    hits = [i + 1 for i, line in enumerate(t) if pat in line]
    print(f'{pat}: {hits}')
    for h in hits[:14]:
        print(f'   {h}: {t[h-1][:150]}')
