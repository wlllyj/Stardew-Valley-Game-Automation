"""只读：把两份 runA/runB 账本里**提到指定格**的所有事件拉平，回答 Lead m07935 的 Q1。

用法：
  python scratch\\_t169_tile_mentions.py 60 29
"""
import io
import json
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")

JOURNALS = [
    ("A", r"logs\longrun-runA-0732.jsonl"),
    ("B", r"logs\longrun-runB-0732.jsonl"),
]


def mentions(obj, tx, ty):
    """事件里任意位置出现 [tx, ty] 或 {'tile':[...]} 即算提到。"""
    text = json.dumps(obj, ensure_ascii=False)
    return (f"[{tx}, {ty}]" in text) or (f"[{tx},{ty}]" in text)


def main() -> int:
    tx, ty = int(sys.argv[1]), int(sys.argv[2])
    for tag, path in JOURNALS:
        print(f"===== {tag}  {path}")
        try:
            lines = io.open(path, encoding="utf-8", errors="replace").read().splitlines()
        except FileNotFoundError:
            print("  (缺文件)")
            continue
        counts = {}
        for i, raw in enumerate(lines, 1):
            raw = raw.strip()
            if not raw:
                continue
            try:
                ev = json.loads(raw)
            except Exception:
                continue
            if not mentions(ev, tx, ty):
                continue
            name = ev.get("event")
            counts[name] = counts.get(name, 0) + 1
            body = json.dumps(ev, ensure_ascii=False)
            if len(body) > 460:
                body = body[:460] + " …"
            print(f"  L{i} t={ev.get('t')} {name}: {body}")
        print("  提到该格的事件计数:", json.dumps(counts, ensure_ascii=False, sort_keys=True))
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
