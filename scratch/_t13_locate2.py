#!/usr/bin/env python
"""task-13 scratch: analyzer stamina/leftover/already current handling."""
import pathlib

t = pathlib.Path('tools/analyze-longrun.py').read_text(encoding='utf-8').splitlines()
for pat in ['deferred_by_budget', 'stamina_budget', 'stamina', '"plot_pending"', 'plot_pending',
            'leftover_executable', 'alloc_capped', 'assigned_undone', '"already"', "already"]:
    hits = [i + 1 for i, line in enumerate(t) if pat in line]
    print(f'{pat}: {len(hits)} {hits[:40]}')
