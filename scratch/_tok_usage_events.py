import json, sys, collections
import zstandard as zstd

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
path = sys.argv[1]
dctx = zstd.ZstdDecompressor()
buf = b''
hits = collections.Counter()
samples = {}
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
                if '"uncachedInputTokens"' not in line and '"cacheReadTokens"' not in line and 'usage' not in line.lower():
                    continue
                try:
                    obj = json.loads(line)
                except Exception:
                    continue
                t = obj.get('type', '?')
                hits[t] += 1
                if t not in samples:
                    samples[t] = json.dumps(obj, ensure_ascii=False)[:1500]
for t, c in hits.most_common():
    print(c, t)
print('---')
for t, s in samples.items():
    print('#####', t)
    print(s)
