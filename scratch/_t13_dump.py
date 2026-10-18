#!/usr/bin/env python
"""task-13 scratch: dump 0.7.44 aggregations + render lines for one ledger."""
import json
import subprocess
import sys
from pathlib import Path

PY = r'C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe'
ROOT = Path(__file__).resolve().parent.parent
ledger = sys.argv[1] if len(sys.argv) > 1 else 'logs/longrun-runA8-0743.jsonl'
extra = sys.argv[2:]
env = {'PYTHONUTF8': '1'}
p = subprocess.run([PY, str(ROOT / 'tools/analyze-longrun.py'), '--journal', str(ROOT / ledger), '--json'] + extra,
                   cwd=ROOT, capture_output=True, text=True, encoding='utf-8', env=env)
rep = json.loads(p.stdout)
t = subprocess.run([PY, str(ROOT / 'tools/analyze-longrun.py'), '--journal', str(ROOT / ledger)] + extra,
                   cwd=ROOT, capture_output=True, text=True, encoding='utf-8', env=env)
lines = t.stdout.splitlines()
for key in ('resume_exhausted', 'stage_realloc', 'leftover_split', 'slept_ok',
            'budget_suppressed', 'already_aware'):
    v = rep.get(key)
    print(f'===== {key} =====')
    print(json.dumps(v, ensure_ascii=False, indent=1))
print('===== render head 0.7.44 lines =====')
for i, ln in enumerate(lines):
    if any(k in ln for k in ('resume_exhausted', 'stage_realloc', '余格拆分', 'slept_ok',
                             '预算抑制', 'already-aware', '双列')):
        print(f'{i+1}: {ln}')
