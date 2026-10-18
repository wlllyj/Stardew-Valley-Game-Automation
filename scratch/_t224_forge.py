"""task-224（0.7.39 冻结树验收）—— B2/B3 作弊通道：伪造账本 + 坏 gaps 文件。

只写 scratch/。用法（在仓库根、冻结树源码跑 analyzer）：
    python scratch/_t224_forge.py
随后用 tools/analyze-longrun.py 跑：
    python <冻结树>/tools/analyze-longrun.py --journal scratch/_t224_forged_b2.jsonl --days 1 --window 1
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
SMOKE = REPO / "logs" / "longrun-smoke-0739.jsonl"
OUT = REPO / "scratch"


def load(path: Path) -> list[dict]:
    rows = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        rows.append(json.loads(line))
    return rows


def dump(rows: list[dict], name: str) -> Path:
    p = OUT / name
    p.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in rows) + "\n", encoding="utf-8")
    return p


def pick_target(rows: list[dict]) -> tuple[int, dict]:
    """找第一条 executed_steps>0 的 intent_coverage 记录（连同它的 day_end）。"""
    for idx, r in enumerate(rows):
        if r.get("event") != "day_end":
            continue
        for rec in r.get("intent_coverage") or []:
            if not isinstance(rec, dict):
                continue
            if int(rec.get("executed_steps") or 0) > 0 and not rec.get("actionless"):
                return idx, rec
    raise SystemExit("smoke 账本里没有 executed_steps>0 的 intent_coverage 记录")


def main() -> int:
    rows = load(SMOKE)
    idx, rec = pick_target(rows)
    iid = rec.get("intent_id")
    task = rec.get("task")
    print(f"[target] day_end idx={idx} line={idx + 1} intent_id={iid} task={task} "
          f"executed_steps={rec.get('executed_steps')} requested_tiles={rec.get('requested_tiles')}")

    # 对照：原账本（不应因这条被判红）
    dump(rows, "_t224_ctrl.jsonl")

    # B2-a：executed_steps=0 且 reasons 为空 ⇒ 期望 analyzer 判红 missed:intent_no_reason
    bad = json.loads(json.dumps(rows))
    for r2 in bad[idx]["intent_coverage"]:
        if r2.get("intent_id") == iid:
            r2["executed_steps"] = 0
            r2["reasons"] = {}
            r2["bad_reasons"] = []
    dump(bad, "_t224_forged_b2.jsonl")

    # B2-b：executed_steps=0 但带闭合集原因码 ⇒ 期望【不】判红（证明闸门不是一刀切）
    ok = json.loads(json.dumps(rows))
    for r2 in ok[idx]["intent_coverage"]:
        if r2.get("intent_id") == iid:
            r2["executed_steps"] = 0
            r2["reasons"] = {"budget_deferred": 1}
            r2["bad_reasons"] = []
    dump(ok, "_t224_forged_b2_reasons.jsonl")

    # B3：坏 gaps 文件（旁边放一份非法 JSON）⇒ 观察 analyzer 的读失败口径
    dump(rows, "_t224_forged_b3.jsonl")
    (OUT / "_t224_forged_b3-gaps.json").write_text("{ this is not json ", encoding="utf-8")

    # 备份/覆盖日志目录里的 gaps 扫描场景：analyzer 用 --gaps-dir 读同目录 *-gaps.json
    shutil.copyfile(OUT / "_t224_forged_b3-gaps.json", OUT / "_t224_gapsdir-probe.json")
    print("[ok] 伪造账本已写出：ctrl / b2 / b2_reasons / b3 + 坏 gaps 文件")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
