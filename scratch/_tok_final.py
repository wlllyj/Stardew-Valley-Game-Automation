import json, os, sys
import zstandard as zstd

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ws = r"C:\Users\admin\.dsh\sessions\--D-Deepseek~0020Harness~0020Workspace-~661F~9732~8C37~6E38~620F~81EA~52A8~5316--"
pc = os.path.join(os.environ['USERPROFILE'], '.dsh', 'storages', 'session_projcache', 'sessions')
dctx = zstd.ZstdDecompressor()

def scan(path):
    st = dict(req=0, inp=0, out=0, cr=0, cw=0, turns=0, users=0, steps=0)
    buf = b''
    hdr = {}
    with open(path, 'rb') as f:
        with dctx.stream_reader(f) as r:
            while True:
                chunk = r.read(1 << 22)
                if not chunk:
                    break
                buf += chunk
                while b'\n' in buf:
                    line, buf = buf.split(b'\n', 1)
                    line = line.strip()
                    if not line:
                        continue
                    o = json.loads(line)
                    t = o.get('type')
                    if t == 'session':
                        hdr = o
                    elif t == 'assistant/message':
                        u = (o.get('data') or {}).get('usage') or {}
                        st['req'] += 1
                        st['inp'] += u.get('inputTokens', 0)
                        st['out'] += u.get('outputTokens', 0)
                        st['cr'] += u.get('cacheReadTokens', 0)
                        st['cw'] += u.get('cacheWriteTokens', 0)
                    elif t == 'turn/start':
                        st['turns'] += 1
                    elif t == 'user/message':
                        st['users'] += 1
                    elif t == 'step/start':
                        st['steps'] += 1
    return hdr, st

sessions = {}
for n in sorted(os.listdir(ws)):
    p = os.path.join(ws, n, 'session.v4.jsonl.zstd')
    if not os.path.exists(p):
        continue
    inherited, ptot = 0, {}
    f = os.path.join(pc, n + '.json')
    if os.path.exists(f):
        rec = json.load(open(f, encoding='utf-8')).get('record', {})
        inherited = rec.get('identity', {}).get('inheritedEventCount', 0) or 0
        ptot = rec.get('rows', {}).get('tokenUsage', {}).get('val', {}).get('totals', {}) or {}
    hdr, st = scan(p)
    sessions[n] = dict(hdr=hdr, st=st, inherited=inherited, ptot=ptot)

roots = {n: d for n, d in sessions.items() if (d['hdr'].get('delegationDepth') == 0)}
children = {n: d for n, d in sessions.items() if (d['hdr'].get('delegationDepth') or 0) > 0}
root_ids = set(roots)

# assign each child to its root lineage
def root_of(n, seen=None):
    seen = seen or set()
    if n in root_ids:
        return n
    if n in seen:
        return None
    seen.add(n)
    par = sessions[n]['hdr'].get('parentSession')
    if par in sessions:
        return root_of(par, seen)
    return par

agg = {}
for n, d in sessions.items():
    r = root_of(n)
    if r not in roots:
        # orphan
        r = 'ORPHAN:' + str(r)
    a = agg.setdefault(r, dict(req=0, inp=0, out=0, cr=0, cw=0, turns=0, users=0, steps=0, nsess=0))
    a['nsess'] += 1
    for k in ('req', 'inp', 'out', 'cr', 'cw', 'turns', 'users', 'steps'):
        a[k] += d['st'][k]

print('=== 按根会话（含其子代理）统计 ===')
tot = dict(req=0, inp=0, out=0, cr=0, cw=0, turns=0, users=0, steps=0)
for r, a in agg.items():
    T = a['inp'] + a['out'] + a['cr'] + a['cw']
    created = sessions.get(r, {}).get('hdr', {}).get('createdAt')
    print(f"{r}\t会话数={a['nsess']}\t请求={a['req']}\tinput={a['inp']}\toutput={a['out']}\tcacheRead={a['cr']}\t总tokens={T}\tturns={a['turns']}\t用户消息={a['users']}")
    for k in tot:
        tot[k] += a[k]
T = tot['inp'] + tot['out'] + tot['cr'] + tot['cw']
print()
print('=== 总计（去重后，主会话+子代理）===')
print(json.dumps(tot, ensure_ascii=False))
print('total_tokens =', T)

print()
print('=== 恢复会话重复量（应剔除）===')
dup = dict(req=0, inp=0, out=0, cr=0)
for n, d in sessions.items():
    if d['inherited'] > 0:
        print(f"  {n}: inheritedEvents={d['inherited']} 重放 usage: req={d['st']['req']} in={d['st']['inp']} out={d['st']['out']} cr={d['st']['cr']}")
        dup['req'] += d['st']['req']; dup['inp'] += d['st']['inp']; dup['out'] += d['st']['out']; dup['cr'] += d['st']['cr']
print('  重复合计:', dup, 'tokens=', dup['inp'] + dup['out'] + dup['cr'])
print()
print('=== 交叉校验: projcache 全量合计 - 重复 ===')
pcs = dict(inp=0, out=0, cr=0, cw=0)
for n, d in sessions.items():
    for src, dst in (('uncachedInputTokens', 'inp'), ('outputTokens', 'out'), ('cacheReadTokens', 'cr'), ('cacheWriteTokens', 'cw')):
        pcs[dst] += d['ptot'].get(src, 0) or 0
print('projcache:', pcs, 'sum=', sum(pcs.values()))
print('projcache - dup =', pcs['inp'] + pcs['out'] + pcs['cr'] + pcs['cw'] - (dup['inp'] + dup['out'] + dup['cr']))
print()
print('=== 各根会话自身（不含子代理）===')
for r in roots:
    d = sessions[r]['st']
    print(f"{r}\t请求={d['req']}\tin={d['inp']}\tout={d['out']}\tcr={d['cr']}\tturns={d['turns']}\tusers={d['users']}\tsteps={d['steps']}\tcreated={sessions[r]['hdr'].get('createdAt')}")
