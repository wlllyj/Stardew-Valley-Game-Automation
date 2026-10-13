"""只读：列出真实账本里 decision 的 llm 键与 source 不一致的行。"""
import json
import sys

for path in sys.argv[1:]:
    print("==", path)
    with open(path, encoding="utf-8") as fh:
        for ln, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except Exception:
                continue
            if ev.get("event") != "decision":
                continue
            llm = bool(ev.get("llm"))
            src = ev.get("source")
            if llm != (src == "llm"):
                print(f"  L{ln} llm={ev.get('llm')!r} source={src!r} boundary={ev.get('boundary')!r} "
                      f"fallback={str(ev.get('fallback'))[:60]!r}")
