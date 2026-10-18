#!/usr/bin/env python
"""task-13 scratch: locate 0.7.44 new-field write sites in brain/agentfarm/longrun.py."""
import pathlib

t = pathlib.Path('brain/agentfarm/longrun.py').read_text(encoding='utf-8').splitlines()
pats = [
    '_journal("plot_exhausted"',
    '_journal("no_progress_burst"',
    'slept_ok =',
    'slept_by_us',
    '_journal("blocked"',
    'switched=',
    '_journal("resume_walk"',
    '"checks":',
    'def _do_sleep',
    'resume_exhausted',
    'deferred_by_budget_suppressed',
    'plot_pending_executable',
    'alloc_no_progress',
    'no_progress_burst',
]
for pat in pats:
    hits = [i + 1 for i, line in enumerate(t) if pat in line]
    print(f'{pat}: {hits}')
