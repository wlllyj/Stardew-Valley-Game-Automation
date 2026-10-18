#!/usr/bin/env python
"""task-13 scratch: locate insertion points in analyzer."""
import pathlib

t = pathlib.Path('tools/analyze-longrun.py').read_text(encoding='utf-8').splitlines()
pats = ['stage_churn', 'work_spot_resume', 'stuck_without_sleep', 'def build_report', 'def build_advice',
        'def render_text', 'def build_undecidable', 'FIELD_PROBES', 'EVENT_BUCKETS', 'NEW_EVENT_BUCKETS',
        'def scan_stage_churn', 'def stage_tile_coords', 'def day_label', 'def _event_gate',
        'report[\'stage_churn\']', 'report = {', 'def main', 'def parse_args']
for pat in pats:
    hits = [i + 1 for i, line in enumerate(t) if pat in line]
    print(f'{pat}: {len(hits)} {hits[:20]}')
print('lines', len(t))
