"""负例夹具：把绿账本改造成「真空日」（verified=true 但所有 stage.ok=0 / ok_steps=0）。

用途：证明 `tools/verify-run3.py` 新增的真空日闸门**不是空条文**（绿账本仍 exit 0，
本夹具必须 exit 1 且判红文案含"成功动作 0 步"）。

只读绿账本 → 写 `scratch/_t5x_vacuum.jsonl`。
"""
from __future__ import annotations

import json
import pathlib

SRC = pathlib.Path("scratch/journal-green.jsonl")
DST = pathlib.Path("scratch/_t5x_vacuum.jsonl")


def main() -> int:
    rows = []
    with SRC.open(encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            rows.append(json.loads(line))
    changed = 0
    for row in rows:
        if row.get("event") != "day_end":
            continue
        stats = row.get("day_end") or row.get("stats") or row
        stages = stats.get("stages") if isinstance(stats, dict) else None
        if isinstance(stages, list):
            for st in stages:
                if isinstance(st, dict) and int(st.get("ok") or 0) > 0:
                    st["ok"] = 0
                    changed += 1
        if isinstance(stats, dict) and int(stats.get("ok_steps") or 0) > 0:
            stats["ok_steps"] = 0
            changed += 1
    DST.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n",
        encoding="utf-8",
    )
    print(f"wrote {DST} rows={len(rows)} zeroed_fields={changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
