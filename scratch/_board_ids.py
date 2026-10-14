import io, re, sys

p = r'C:\Users\admin\AppData\Local\Temp\dsh-spill-MZkGYI\session-0a321cd5cab5\7470969132f7-team_task_list.txt'
t = io.open(p, encoding='utf-8', errors='replace').read()
ids = sorted(set(int(m) for m in re.findall(r'"id":"task-(\d+)"', t)))
print('ids in page:', ids)
for n in (34, 57, 58, 59, 74, 80, 81):
    m = re.search(r'\{"id":"task-%d"' % n, t)
    if not m:
        print('task-%d: NOT IN THIS PAGE' % n)
        continue
    seg = t[m.start():m.start() + 260].replace('\n', ' ')
    print('task-%d: %s' % (n, seg))
