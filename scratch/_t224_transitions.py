"""task-224 B 段：逐卡「pre 树状态 → 冻结树状态」对照（只读 scratch/）。

判定口径（Lead 要求"缺失 ≠ 通过"）：
- 冻结树（cea9c0f，验收对象）里该卡组的检查必须全部 PASS；
- pre 树（该卡父提交）里同组检查要么 FAIL、要么 SKIP（门槛未开）——只要不是 PASS 就算"该卡的证据"，
  逐条列出它从什么状态变成 PASS，避免把 SKIP 当通过。
"""
from __future__ import annotations

import re
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
LINE = re.compile(r"^\s*(PASS|FAIL|SKIP)\s+([A-Za-z0-9_.-]+)\b")
SUM = re.compile(r"合计 PASS=(\d+) FAIL=(\d+) SKIP=(\d+)")

GROUP_CARD = {
    "P0-1": "218", "P0-2": "218",
    "P0-3": "219", "P0-4": "219",
    "P0-5": "220",
    "D228": "228",
}


def parse(path: Path) -> tuple[dict[str, str], str]:
    out: dict[str, str] = {}
    total = ""
    if not path.exists():
        return out, "MISSING"
    for line in path.read_text(encoding="utf-8").splitlines():
        m = LINE.match(line)
        if m and m.group(2) not in out:
            out[m.group(2)] = m.group(1)
        ms = SUM.search(line)
        if ms:
            total = f"{ms.group(1)}/{ms.group(2)}/{ms.group(3)}"
    return out, total


def card_of(cid: str) -> str:
    for prefix, card in GROUP_CARD.items():
        if cid.startswith(prefix):
            return card
    return "?"


def main() -> int:
    frozen, frozen_total = parse(REPO / "scratch" / "_t224_frozen_probe.txt")
    print(f"冻结树（cea9c0f）合计 P/F/S = {frozen_total}\n")
    print("| 卡 | 父提交（pre，P/F/S） | 该卡组在冻结树的检查数 | pre 非 PASS → 冻结点 PASS 的条数 | 冻结树该组非 PASS |")
    print("|---|---|---|---|---|")
    for card in ("218", "219", "220", "228"):
        pre, pre_total = parse(REPO / "scratch" / f"_t224_pre{card}_probe.txt")
        own = sorted(cid for cid in frozen if card_of(cid) == card)
        flips = [cid for cid in own if pre.get(cid) != "PASS"]
        bad = [cid for cid in own if frozen.get(cid) != "PASS"]
        print(f"| {card} | {pre_total} | {len(own)} | {len(flips)}：{', '.join(flips)} | {', '.join(bad) or '无'} |")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
