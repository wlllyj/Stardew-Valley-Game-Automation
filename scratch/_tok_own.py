import json, os, sys
import zstandard as zstd

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
ws = r"C:\Users\admin\.dsh\sessions\--D-Deepseek~0020Harness~0020Workspace-~661F~9732~8C37~6E38~620F~81EA~52A8~5316--"
pc = os.path.join(os.environ['USERPROFILE'], '.dsh', 'storages', 'session_projcache', 'sessions')
dctx = zstd.ZstdDecompressor()

info = {}
for n in sorted(os.listdir(ws)):
    p = os.path.join(ws, n, 'session.v4.jsonl.zstd')
    inherited = 0
    f = os.path.join(pc, n + '.json')
    if os.path.exists(f):
        inherited = json.load(open(f, encoding='utf-8')).get('record', {}).get('identity', {}).get('inheritedEventCount', 0) or 0
    own = {'req': 0, 'in': 0, 'out': 0, 'cr': 0}
    inh = {'req': 0, 'in': 0, 'out': 0, 'cr': 0}
    hdr = None
    buf = b''
    with open(p, 'rb') as fh:
        with dctx.stream_reader(fh) as r:
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
                    try:
                        obj = json.loads(line)
                    except Exception:
                        continue
                    t = obj.get('type')
                    if t == 'session':
                        hdr = obj
                    elif t == 'assistant/message':
                        seq = obj.get('seq', 0)
                        u = (obj.get('data') or {}).get('usage') or {}
                        tgt = inh if seq <= inherited else own
                        tgt['req'] += 1
                        tgt['in'] += u.get('inputTokens', 0)
                        tgt['out'] += u.get('outputTokens', 0)
                        tgt['cr'] += u.get('cacheReadTokens', 0)
    info[n] = dict(hdr=hdr or {}, inherited=inherited, own=own, inh=inh)

for n, d in info.items():
    h = d['hdr']
    print(f"{n}\tparent={h.get('parentSession')}\tdepth={h.get('delegationDepth')}\tseeded={h.get('isSeeded')}\t"
          f"inhEvents={d['inherited']}\tOWN req={d['own']['req']} in={d['own']['in']} out={d['own']['out']} cr={d['own']['cr']}\t"
          f"INHERITED req={d['inh']['req']} in={d['inh']['in']} out={d['inh']['out']} cr={d['inh']['cr']}")
