import json, sys, os, glob
import zstandard as zstd

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
root = sys.argv[1]
dctx = zstd.ZstdDecompressor()

def scan(path):
    st = {'requests': 0, 'requests_nousage': 0,
          'input': 0, 'output': 0, 'cacheRead': 0, 'cacheWrite': 0, 'total': 0,
          'turns': 0, 'userMsgs': 0, 'steps': 0, 'bad': 0,
          'typeCount': {}}
    buf = b''
    hdr = None
    with open(path, 'rb') as f:
        with dctx.stream_reader(f) as r:
            while True:
                chunk = r.read(1 << 22)
                if not chunk:
                    break
                buf += chunk
                while b'\n' in buf:
                    line, buf = buf.split(b'\n', 1)
                    line = line.decode('utf-8', 'replace').strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except Exception:
                        st['bad'] += 1
                        continue
                    t = obj.get('type', '?')
                    st['typeCount'][t] = st['typeCount'].get(t, 0) + 1
                    if t == 'session':
                        hdr = obj
                    elif t == 'assistant/message':
                        st['requests'] += 1
                        u = obj.get('data', {}).get('usage')
                        if u:
                            st['input'] += u.get('inputTokens', 0)
                            st['output'] += u.get('outputTokens', 0)
                            st['cacheRead'] += u.get('cacheReadTokens', 0)
                            st['cacheWrite'] += u.get('cacheWriteTokens', 0)
                            st['total'] += u.get('totalTokens', 0)
                        else:
                            st['requests_nousage'] += 1
                    elif t == 'step/start':
                        st['steps'] += 1
                    elif t == 'turn/start':
                        st['turns'] += 1
                    elif t == 'user/message':
                        st['userMsgs'] += 1
    return hdr, st

files = sorted(glob.glob(os.path.join(root, '*', 'session.v4.jsonl.zstd')))
grand = {'requests': 0, 'input': 0, 'output': 0, 'cacheRead': 0, 'cacheWrite': 0, 'total': 0, 'turns': 0, 'userMsgs': 0}
rows = []
for p in files:
    hdr, st = scan(p)
    sid = os.path.basename(os.path.dirname(p))
    rows.append((sid, hdr, st))
    for k in grand:
        grand[k] += st.get(k, 0)
for sid, hdr, st in rows:
    tot = st['input'] + st['output'] + st['cacheRead'] + st['cacheWrite']
    print(f"{sid}\treq={st['requests']:5d}\tin={st['input']:>10d}\tout={st['output']:>8d}\tcacheR={st['cacheRead']:>10d}\tcacheW={st['cacheWrite']:>8d}\tsum={tot:>11d}\tsteps={st['steps']:4d}\tturns={st['turns']:3d}\tusers={st['userMsgs']:3d}\tbad={st['bad']}")
    if hdr:
        print(f"    hdr: createdAt={hdr.get('createdAt')} cwd={hdr.get('cwd')} isSeeded={hdr.get('isSeeded')} depth={hdr.get('delegationDepth')} keys={[k for k in hdr.keys() if k not in ('type','version','id')]}")
print()
print('GRAND:', json.dumps(grand, ensure_ascii=False))
print('files:', len(files))
