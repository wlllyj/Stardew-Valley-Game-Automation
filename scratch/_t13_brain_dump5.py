#!/usr/bin/env python
"""task-13 scratch: plot_exhausted write sites."""
import pathlib

t = pathlib.Path('brain/agentfarm/longrun.py').read_text(encoding='utf-8').splitlines()
for lo, hi in [(1270, 1300), (4345, 4375), (4870, 4910), (6085, 6110), (8190, 8215), (8385, 8480)]:
    print(f'===== {lo}-{hi} =====')
    for i in range(lo - 1, min(hi, len(t))):
        print(f'{i + 1}: {t[i]}')
