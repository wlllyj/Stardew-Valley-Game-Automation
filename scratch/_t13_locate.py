#!/usr/bin/env python
"""task-13 scratch: locate analyzer blocks by keyword."""
import pathlib

t = pathlib.Path('tools/analyze-longrun.py').read_text(encoding='utf-8').splitlines()
pats = ['stage_churn', 'work_spot_resume', 'stuck_without_sleep', 'resume_walk',
        'plot_exhausted', 'already', 'window', 'FIELD_PROBES', 'def build_advice',
        'def build_undecidable', 'def build_report', 'def render_text', 'advice',
        'head=', 'deferred', 'pending_executable', 'slept_ok', 'stamina_budget']
for pat in pats:
    hits = [i + 1 for i, line in enumerate(t) if pat in line]
    print(f'{pat}: {len(hits)} {hits[:50]}')
