#!/usr/bin/env python
"""task-13 scratch: run analyzer on a ledger and dump new aggregate keys."""
import json
import subprocess
import sys
import pathlib

PY = r'C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe'
ledger = sys.argv[1] if len(sys.argv) > 1 else 'logs/longrun-runA8-0743.jsonl'
p = subprocess.run([PY, 'tools/analyze-longrun.py', '--journal', ledger, '--json'],
                   capture_output=True, text=True, encoding='utf-8')
if p.returncode not in (0, 1):
    print('RC', p.returncode)
    print(p.stdout[-3000:])
    print(p.stderr[-3000:])
    sys.exit(2)
rep = json.loads(p.stdout)
print('rc:', len(rep.get('red', {}).get('subjects', [])),
      'red:', rep.get('red', {}).get('count') or len(rep.get('red', {}).get('subjects', [])))
for key in ('resume_exhausted', 'stage_realloc', 'leftover_split', 'slept_ok',
            'budget_suppressed', 'already_aware'):
    v = rep.get(key)
    if v is None:
        print(key, '<MISSING>')
        continue
    print('=====', key)
    print(json.dumps(v, ensure_ascii=False, indent=1)[:4000])
print('undecidable count:', len(rep.get('undecidable') or []))

