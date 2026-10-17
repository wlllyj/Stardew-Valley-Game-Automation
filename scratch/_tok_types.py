import json, sys, collections
import zstandard as zstd

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
path = sys.argv[1]
dctx = zstd.ZstdDecompressor()
types = collections.Counter()
samples = {}
buf = b''
with open(path, 'rb') as f:
    with dctx.stream_reader(f) as r:
        while True:
            chunk = r.read(1 << 20)
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
                    types['PARSE_FAIL'] += 1
                    continue
                t = obj.get('type', '?')
                types[t] += 1
                if 'usage' in t or 'token' in json.dumps(obj)[:200].lower():
                    samples.setdefault(t, json.dumps(obj, ensure_ascii=False)[:900])
for t, c in types.most_common():
    print(f'{c:6d}  {t}')
print('\n--- usage-ish samples ---')
for t, s in samples.items():
    print(t, '::', s)
