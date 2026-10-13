"""机械核对（只读）：brain 里 _journal 发出的事件名 vs tools/analyze-longrun.py 的 EVENT_BUCKETS 键。"""
import re

brain = open("brain/agentfarm/longrun.py", encoding="utf-8").read()
tool = open("tools/analyze-longrun.py", encoding="utf-8").read()

brain_names = sorted(set(re.findall(r'_journal\(\s*"([a-z0-9_]+)"', brain)))
m = re.search(r"EVENT_BUCKETS\s*=\s*\{(.*?)\n\}", tool, re.S)
block = m.group(1)
bucket_keys = sorted(set(re.findall(r'"([a-z0-9_]+)"\s*:', block)))

print("brain _journal names:", len(brain_names))
print("EVENT_BUCKETS keys:", len(bucket_keys))
missing = [n for n in brain_names if n not in bucket_keys]
extra = [k for k in bucket_keys if k not in brain_names]
print("\nbrain 有、桶里没有(未映射):", len(missing))
for n in missing:
    cnt = len(re.findall(r'_journal\(\s*"%s"' % n, brain))
    print(f"   - {n}  ({cnt} 处)")
print("\n桶里有、brain 里没扫到:", len(extra))
for k in extra:
    print("   -", k)
