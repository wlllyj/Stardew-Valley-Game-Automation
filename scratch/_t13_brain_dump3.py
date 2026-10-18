#!/usr/bin/env python
"""task-13 scratch: grep brain switched/resume_walk/plot_exhausted journals."""
import pathlib

t = pathlib.Path('brain/agentfarm/longrun.py').read_text(encoding='utf-8').splitlines()
for lo, hi in [(3940, 4030), (4340, 4380), (4870, 4910), (6090, 6110), (8190, 8210),
               (8390, 8480), (8640, 8670), (7250, 7300)]:
    print(f'===== {lo}-{hi} =====')
    for i in range(lo - 1, min(hi, len(t))):
        print(f'{i + 1}: {t[i]}')
