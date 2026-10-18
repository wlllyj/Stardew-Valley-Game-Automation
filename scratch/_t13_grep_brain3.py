#!/usr/bin/env python
"""task-13 scratch: find stamina_budget init + plot_exhausted source call sites."""
import pathlib
import re

t = pathlib.Path('brain/agentfarm/longrun.py').read_text(encoding='utf-8').splitlines()
for i, line in enumerate(t):
    if re.search(r'stamina_budget\s*[=:]', line) or 'plot_exhausted(' in line or 'def plot_exhausted' in line:
        print(f'{i + 1}: {line}')
