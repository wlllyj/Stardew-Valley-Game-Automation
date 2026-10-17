import json, os, sys

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
pc = os.path.join(os.environ['USERPROFILE'], '.dsh', 'storages', 'session_projcache', 'sessions')
ws = r"C:\Users\admin\.dsh\sessions\--D-Deepseek~0020Harness~0020Workspace-~661F~9732~8C37~6E38~620F~81EA~52A8~5316--"
names = sorted(os.listdir(ws))
g = {'uncachedInputTokens': 0, 'outputTokens': 0, 'cacheReadTokens': 0, 'cacheWriteTokens': 0}
for n in names:
    f = os.path.join(pc, n + '.json')
    if not os.path.exists(f):
        print(n, 'NO PROJCACHE')
        continue
    d = json.load(open(f, encoding='utf-8'))
    rec = d.get('record', {})
    ident = rec.get('identity', {})
    rows = rec.get('rows', {})
    tu = rows.get('tokenUsage', {}).get('val', {})
    tot = tu.get('totals', {})
    stats = rows.get('sessionStats', {}).get('val', {})
    print(f"{n}\tinherited={ident.get('inheritedEventCount')}\tcreated={ident.get('createdAt')}\t"
          f"turns={stats.get('turns')}\tsteps={stats.get('steps')}\t"
          f"in={tot.get('uncachedInputTokens')}\tout={tot.get('outputTokens')}\tcacheR={tot.get('cacheReadTokens')}\tcacheW={tot.get('cacheWriteTokens')}")
    for k in g:
        g[k] += tot.get(k, 0) or 0
print()
print('PROJCACHE GRAND:', json.dumps(g, ensure_ascii=False), 'sum=', sum(g.values()))
