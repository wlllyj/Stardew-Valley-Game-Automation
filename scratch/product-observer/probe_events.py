# -*- coding: utf-8 -*-
"""产品旁观审计：只读解析账本事件类型/样本，不修改任何文件。"""
import json, sys, collections

def load(path):
    rows = []
    with open(path, 'r', encoding='utf-8') as f:
        for i, line in enumerate(f, 1):
            line = line.strip()
            if not line:
                continue
            try:
                rows.append((i, json.loads(line)))
            except Exception as e:
                rows.append((i, {'__bad__': str(e)}))
    return rows

if __name__ == '__main__':
    path = sys.argv[1]
    rows = load(path)
    print('lines', len(rows))
    cnt = collections.Counter()
    for i, r in rows:
        cnt[r.get('event')] += 1
    for k, v in cnt.most_common():
        print(f'{v:5d}  {k}')
