import json, sys
import zstandard as zstd

sys.stdout.reconfigure(encoding='utf-8', errors='replace')
path = sys.argv[1]
limit = int(sys.argv[2]) if len(sys.argv) > 2 else 6
dctx = zstd.ZstdDecompressor()
buf = b''
n = 0
with open(path, 'rb') as f:
    with dctx.stream_reader(f) as r:
        while n < limit:
            chunk = r.read(1 << 16)
            if not chunk:
                break
            buf += chunk
            while b'\n' in buf and n < limit:
                line, buf = buf.split(b'\n', 1)
                line = line.decode('utf-8', 'replace').strip()
                if not line:
                    continue
                n += 1
                try:
                    obj = json.loads(line)
                except Exception as e:
                    print('PARSE FAIL', n, e, line[:200])
                    continue
                print('=== line', n, 'keys:', list(obj.keys()))
                print(json.dumps(obj, ensure_ascii=False)[:1000])
