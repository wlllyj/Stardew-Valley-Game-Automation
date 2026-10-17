# -*- coding: utf-8 -*-
"""R2 专项：脑侧 loot 自述（reason 原文）vs 实测逐 qid 增量（task-191 验收点之一）。

task-184 的真机形态：对照格一次 `use_tool` 实际收了 4 格（`(O)262 +4` / `(O)178 +2`），
而脑侧 reason 却写「⚠ 背包没有新增物品（收货可能丢了，不能出货）」。
本模块把两侧并排量化：解析 reason 里的 `进背包：{...}` 自述与那条警告，和观测到的逐 qid 增量对比。

task-191 的判据：对照格一次 `use_tool` 后，**若 reason 仍说「背包没有新增物品」而实测有增量 ⇒ FAIL**。
纯离线、无网络、无游戏。自测：`python scratch\\_t191_loot_check.py`（3 用例，含两个 task-184 真实形态）。
"""
from __future__ import annotations

import json
import re

LOOT_CLAIM_RE = re.compile(r"进背包：\{(.*?)\}")
_ITEM_RE = re.compile(r"'([^']+)':\s*(-?\d+)")
_AFFECTED_RE = re.compile(r"受影响格：(.+?)(?:；|$)", re.S)
_TILE_RE = re.compile(r"\[\s*(\d+)\s*,\s*(\d+)\s*\]")
LOOT_WARN = "背包没有新增物品"


def norm_qid(x: object) -> str:
    """观测里的 itemId 无前缀（`270`），reason 里的自述带前缀（`(O)270`）⇒ 归一化后比较。"""
    return str(x or "").replace("(O)", "").replace("(T)", "").replace("(W)", "")


def parse_loot_claim(text: str | None) -> dict[str, int] | None:
    if not text:
        return None
    m = LOOT_CLAIM_RE.search(text)
    if not m:
        return None
    out: dict[str, int] = {}
    for k, v in _ITEM_RE.findall(m.group(1)):
        q = norm_qid(k)
        out[q] = out.get(q, 0) + int(v)
    return out


def parse_affected_tiles(text: str | None) -> list[tuple[int, int]]:
    if not text:
        return []
    m = _AFFECTED_RE.search(text)
    if not m:
        return []
    return [(int(a), int(b)) for a, b in _TILE_RE.findall(m.group(1))]


def compare(reason: str | None, loot_diff: dict | None) -> dict:
    observed = {norm_qid(k): int(v) for k, v in (loot_diff or {}).items() if int(v) != 0}
    gained = {k: v for k, v in observed.items() if v > 0}
    claim = parse_loot_claim(reason)
    warn = LOOT_WARN in (reason or "")
    matches = claim is not None and claim == gained
    affected = parse_affected_tiles(reason)
    if warn and gained:
        verdict = "FAIL"                      # R2 本体：反着写
        why = f"reason 说『{LOOT_WARN}』但实测有增量 {gained}"
    elif claim is not None and claim != gained:
        verdict = "FAIL"                      # 自述与实测不符（多格/合并入既有栈时易发生）
        why = f"自述 {claim} ≠ 实测 {gained}"
    elif claim is None and gained:
        verdict = "NO_CLAIM"                  # 未自述（不判 FAIL，但要标注）
        why = "reason 未给『进背包』自述，但实测确有增量"
    else:
        verdict = "PASS"
        why = f"自述与实测一致 {gained}" if gained else "无增量、无自述（一致）"
    return {"reason": reason, "loot_claim": claim, "loot_observed": gained,
            "all_qid_diff": observed, "warning_present": warn,
            "claim_matches_observed": matches, "affected_tiles": affected,
            "affected_tile_count": len(affected) or None,
            "verdict": verdict, "why": why}


def report(reason: str | None, loot_diff: dict | None, *, title: str = "") -> dict:
    r = compare(reason, loot_diff)
    print(f"--- R2 loot 记账核对 {('· ' + title) if title else ''} ---")
    print(f"  脑侧 reason 原文 : {(reason or '')[:420]}")
    print(f"  脑侧 loot 自述   : {r['loot_claim']}")
    print(f"  实测逐 qid 增量  : {r['loot_observed']}（全部非零 diff={r['all_qid_diff']}）")
    print(f"  受影响格         : {r['affected_tile_count']} 格 {r['affected_tiles'][:8]}")
    print(f"  含『{LOOT_WARN}』 : {r['warning_present']}")
    print(f"  R2 VERDICT: {r['verdict']} —— {r['why']}")
    return r


def selftest() -> int:
    ok = True
    # case1 = task-184 对照格真实形态（多格 + 反着写的警告）⇒ 预期 FAIL
    reason_ctl = ("收获成功（判据：该格 crop 已消失；该格 ready true→None）；受影响格：[[44, 24], [53, 16], "
                  "[54, 15], [59, 28], [60, 28], [61, 28], [61, 29], [72, 21]]；"
                  "⚠ 背包没有新增物品（收货可能丢了，不能出货）")
    r1 = report(reason_ctl, {"178": 2, "262": 4}, title="真实形态 (60,28) 多格")
    if r1["verdict"] != "FAIL" or r1["loot_claim"] is not None or r1["affected_tile_count"] != 8:
        print("!! case1 预期 FAIL + 无自述 + 8 格"); ok = False

    # case2 = task-184 样本格真实形态（单格新物品，自述与实测一致）⇒ 预期 PASS
    reason_s = ("收获成功（判据：该格 ready true→False；进背包：{'(O)270': 1}（逐 qid 差分；一次动作可能收多格））；"
                "受影响格：[[60, 29]]；再生作物：crop 对象保留、阶段重置（旧判据只看 crop 消失 ⇒ 假阴性）")
    r2 = report(reason_s, {"270": 1}, title="真实形态 (60,29) 单格")
    if r2["verdict"] != "PASS" or not r2["claim_matches_observed"] or r2["affected_tile_count"] != 1:
        print("!! case2 预期 PASS + 自述一致 + 1 格"); ok = False

    # case3 = 自述少于实测（比如只记了该格、漏了连带清掉的格）⇒ 预期 FAIL
    r3 = report("…；进背包：{'(O)262': 4}；受影响格：[[60, 28]]", {"262": 4, "178": 2}, title="合成：自述少于实测")
    if r3["verdict"] != "FAIL":
        print("!! case3 预期 FAIL"); ok = False

    print(f"\nR2 SELFTEST {'PASS' if ok else 'FAIL'}（3 用例：2 真实形态 + 1 合成；纯离线）")
    return 0 if ok else 13


MAX_LEN = 4000


def _deep_reason(obj: object, depth: int = 0) -> str | None:
    """从任意嵌套 JSON 里挖出脑侧 reason（对 payload 形状不敏感）。"""
    if depth > 6:
        return None
    if isinstance(obj, str):
        return obj if ("进背包" in obj or LOOT_WARN in obj or "收获" in obj) else None
    if isinstance(obj, dict):
        for k in ("reason", "note", "message"):
            v = obj.get(k)
            if isinstance(v, str) and ("进背包" in v or LOOT_WARN in v or "收获" in v):
                return v
        for v in obj.values():
            r = _deep_reason(v, depth + 1)
            if r:
                return r
    if isinstance(obj, list):
        for v in obj:
            r = _deep_reason(v, depth + 1)
            if r:
                return r
    return None


_DIFF_KEYS = ("loot_qid_diff", "observed_loot_qid_diff", "loot")


def _parse_diff(text: str) -> dict[str, int]:
    """pwsh 会把参数内层的双引号剥掉（`{"262":4}` → `{262:4}`）⇒ JSON 失败时退化成宽松解析。"""
    try:
        return {str(k): int(v) for k, v in json.loads(text).items()}
    except Exception:  # noqa: BLE001
        return {k: int(v) for k, v in re.findall(r"([A-Za-z0-9_()]+)\s*[:=]\s*(-?\d+)", text)}


def _deep_loot(obj: object, depth: int = 0) -> dict[str, int] | None:
    """从 payload 里挖出逐 qid 增量（键名不敏感）。"""
    if depth > 6:
        return None
    if isinstance(obj, dict):
        for k in _DIFF_KEYS:
            v = obj.get(k)
            if isinstance(v, dict) and v:
                return {str(a).replace("(O)", "").replace("(T)", "").replace("(W)", ""): int(b)
                        for a, b in v.items()}
        for v in obj.values():
            r = _deep_loot(v, depth + 1)
            if r:
                return r
    if isinstance(obj, list):
        for v in obj:
            r = _deep_loot(v, depth + 1)
            if r:
                return r
    return None


def main(argv: list[str] | None = None) -> int:
    import argparse
    import json
    import os
    import sys

    ap = argparse.ArgumentParser(description="R2：脑侧 loot 自述 vs 实测逐 qid 增量")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--payload", help="任意含脑侧 reason 的 JSON（例：scratch\\_t184_<tag>-verdict.json）")
    ap.add_argument("--reason", help="直接给 reason 原文")
    ap.add_argument("--reason-file", help="含 {\"reason\": \"…\"} 的 JSON")
    ap.add_argument("--before", help="before observe JSON")
    ap.add_argument("--after", help="after observe JSON")
    ap.add_argument("--tile", help="x,y")
    ap.add_argument("--loot-diff", help='逐 qid 增量，如 {"262":4,"178":2}')
    ap.add_argument("--loot-diff-file", help="逐 qid 增量 JSON 文件（pwsh 下更稳）")
    ap.add_argument("--json", help="写出结果 JSON")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()

    doc = None
    for path in (args.reason_file, args.payload):
        if path:
            with open(path, encoding="utf-8") as fh:
                doc = json.load(fh)
            break
    reason = args.reason if args.reason is not None else _deep_reason(doc)

    loot: dict | None = None
    if args.loot_diff_file:
        with open(args.loot_diff_file, encoding="utf-8") as fh:
            loot = {str(k): int(v) for k, v in json.load(fh).items()}
    elif args.loot_diff:
        loot = _parse_diff(args.loot_diff)
    elif args.before and args.after and args.tile:
        here = os.path.dirname(os.path.abspath(__file__))
        if here not in sys.path:
            sys.path.insert(0, here)
        import _t184_triple_check as tc  # noqa: PLC0415

        tile = tuple(int(p) for p in args.tile.split(","))
        with open(args.before, encoding="utf-8") as fh:
            before = json.load(fh)
        with open(args.after, encoding="utf-8") as fh:
            after = json.load(fh)
        loot = tc.world_diff(before, after, tile)["loot_qid_diff"]
    else:
        loot = _deep_loot(doc)

    if reason is None and loot is None:
        ap.print_help()
        return 11

    r = report((reason or "")[:MAX_LEN], loot)
    if args.json:
        with open(args.json, "w", encoding="utf-8") as fh:
            json.dump(r, fh, ensure_ascii=False, indent=2)
        print(f"已写出 {args.json}")
    return {"PASS": 0, "FAIL": 1, "NO_CLAIM": 2}[r["verdict"]]


if __name__ == "__main__":
    import sys

    sys.exit(main())
