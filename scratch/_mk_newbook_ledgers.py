# -*- coding: utf-8 -*-
"""造两份"task-15 ④ 新口径"账本，验证 verify-run3.py 的差额容错分支。

负例 I：日级 failed_steps=0，而 stage.failed=3，且 env_block_count=3
        ⇒ 差额 3 被"环境挡路 3"完全解释 ⇒ 应 VERIFIED / exit 0（信息项）。
负例 J：同上但 env_block_count=1 ⇒ 差额解释不完 ⇒ 应 needs_review / exit 1。

做法：以 scratch/journal-green.jsonl 为底本，改第一个有 stages 的 day_end。
"""
import copy
import json
import pathlib

SRC = pathlib.Path("scratch/journal-green.jsonl")
rows = [json.loads(line) for line in SRC.read_text(encoding="utf-8").splitlines() if line.strip()]


def variant(out: str, env_count: int, failed: int = 3) -> dict:
    out_rows = copy.deepcopy(rows)
    hit = None
    for row in out_rows:
        if row.get("event") == "day_end" and row.get("stages"):
            row["stages"][0]["failed"] = failed
            row["stages"][0]["env_block_count"] = env_count
            row["failed_steps"] = 0
            hit = {
                "day": row.get("day"),
                "stage": row["stages"][0].get("stage"),
                "failed": failed,
                "env_block_count": env_count,
                "failed_steps": 0,
            }
            break
    p = pathlib.Path(out)
    p.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in out_rows) + "\n",
        encoding="utf-8",
    )
    return {"path": str(p), "touched": hit}


print(json.dumps(
    {
        "I": variant("scratch/review-neg-I-env-explained.jsonl", 3),
        "J": variant("scratch/review-neg-J-env-understated.jsonl", 1),
    },
    ensure_ascii=False,
    indent=2,
))
