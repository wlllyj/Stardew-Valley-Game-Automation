#!/usr/bin/env python
"""task-13 scratch: dump brain stamina_budget init + day_end budget copy."""
import pathlib

t = pathlib.Path('brain/agentfarm/longrun.py').read_text(encoding='utf-8').splitlines()
for lo, hi in [(3405, 3460), (8970, 9000), (780, 870), (7255, 7300)]:
    print(f'===== {lo}-{hi} =====')
    for i in range(lo - 1, min(hi, len(t))):
        print(f'{i + 1}: {t[i]}')
