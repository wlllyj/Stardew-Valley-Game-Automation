#!/usr/bin/env python
"""task-13 scratch: locate task-3 tests to avoid breaking them."""
import pathlib

t = pathlib.Path('tests/test_analyze_longrun.py').read_text(encoding='utf-8').splitlines()
pats = ['stage_churn', 'work_spot_resume', 'stuck_without_sleep', 'class ', 'def test_']
for pat in pats:
    hits = [i + 1 for i, line in enumerate(t) if pat in line]
    print(f'{pat}: {len(hits)} {hits[:80]}')
print('lines', len(t))
