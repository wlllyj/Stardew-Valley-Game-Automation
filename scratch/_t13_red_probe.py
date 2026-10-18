#!/usr/bin/env python
"""task-13 scratch: inspect red/undecidable summary for a ledger."""
import json
import subprocess
import sys

PY = r'C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe'
ledger = sys.argv[1]
extra = sys.argv[2:]
p = subprocess.run([PY, 'tools/analyze-longrun.py', '--journal', ledger, '--json'] + extra,
                   capture_output=True, text=True, encoding='utf-8')
if p.returncode not in (0, 1):
    print('RC', p.returncode, p.stderr[-2000:])
    sys.exit(2)
rep = json.loads(p.stdout)
red = rep.get('red') or {}
print('red keys:', list(red.keys()))
print('red count:', red.get('count'), 'subjects:', len(red.get('subjects') or []))
print('rc_code:', rep.get('rc'), 'undecidable:', len(rep.get('undecidable') or []))
win = rep.get('window') or {}
print('window:', {k: win.get(k) for k in ('days', 'tail_streak', 'active', 'history_total', 'settled_total')})
