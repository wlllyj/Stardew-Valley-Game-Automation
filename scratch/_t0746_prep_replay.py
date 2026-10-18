#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""【0.7.46 / task-31 预热】smoke-0745 + A8 账本的独立重放与判据草案。

只读账本、不碰生产代码、不跑真机。用法（PYTHONUTF8=1）：
  python scratch/_t0746_prep_replay.py
  python scratch/_t0746_prep_replay.py --out scratch/_t0746_prep_replay.txt

三段：
  1) 判据自检（judge self-test）：喂合成记录，判红/判绿/无法判定三态都要对；
  2) 真账本重放：0.7.45 的 smoke-0745 按 0.7.46 判据应命中的形态（冬26 inventory_blocked
     四门槛、冬27 resume_exhausted/7 格、32 格 till/clear、售材纪律、A8 263/217）；
  3) 判据草案清单（gate 细节将在冻结后按 task-28/25/33 实装对齐）。

⚠ 这是预热草案：J1 的四门槛、卡 A 的观测面、task-33 talk 契约都还没冻结，
   GL 明确后可能改判据——本脚本只证明"判据能抓形态"，不是正式判定。
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

REPO = Path(__file__).resolve().parents[1]
SMOKE = REPO / "logs" / "longrun-smoke-0745.jsonl"
A8 = REPO / "logs" / "longrun-runA8-0743.jsonl"

FORBIDDEN_SELL_QIDS = ("388", "390", "330", "771", "382", "378", "380", "384", "386", "909")
PRESERVE_QIDS = ("92", "766")  # Sap / Slime：保留要有归类依据，不许无依据卖

results: list[tuple[str, str, str]] = []  # (tag, state, detail)


def say(tag: str, state: str, detail: str = "") -> None:
    results.append((tag, state, detail))
    print(f"[{state}] {tag}{(' — ' + detail) if detail else ''}")


def expect(tag: str, state: str, want: str, detail: str = "") -> None:
    """自检用：state 必须等于 want，否则记 FAIL。"""
    if state == want:
        say(tag, "green", f"{state}（期望 {want}）" + (f"；{detail}" if detail else ""))
    else:
        say(tag, "FAIL", f"got={state} 期望={want}；{detail}")


def load_jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]


def day_groups(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """按 day_end 切日；day_end 之前（上一 day_end 之后）的所有行归当天。"""
    out, start = [], 0
    for i, r in enumerate(rows):
        if r.get("event") != "day_end":
            continue
        out.append({"day_end": r, "rows": rows[start:i + 1], "day": r.get("day_text") or r.get("day")})
        start = i + 1
    return out


def qid_of(sold: Any) -> str:
    s = str(sold or "")
    return s.replace("(O)", "").replace("(T)", "")


# ---------------------------------------------------------------- judges
def judge_inventory_blocked(day: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """J1（Lead 2026-10-18 裁定）：E1–E5 五条全满足才认 inventory_blocked 诚实收工。

    E1 ended_by=="inventory_blocked"；
    E2 free_slots_status=="ok" 且 free_slots_last==0（不是 min）；
    E3 腾格用尽：至少一次 space_pressure/buy_full 的 slot_relief，且最后一次腾格尝试之后
       没有 freed>0 的成功、其后也没有 strategy=="slot_relief_space" 的 sell；
    E4 pending_executable==0 且 pending_malformed==0（pending_unobserved 允许 >0）；
    E5 loot_lost_steps <= 5（卡 D 常量）。
    """
    de = day["day_end"]
    if de.get("ended_by") != "inventory_blocked":
        return "none", {"reason": "当天不是 inventory_blocked"}
    if de.get("free_slots_status") is None:
        return "none", {"reason": "账本无 free_slots_status ⇒ 无法判定"}
    rows = day["rows"]
    e1 = True
    e2 = de.get("free_slots_status") == "ok" and de.get("free_slots_last") == 0
    relief_idx = [i for i, r in enumerate(rows) if r.get("event") == "slot_relief"]
    relief_ok = [i for i in relief_idx if rows[i].get("trigger") == "space_pressure"
                 or rows[i].get("demand_basis") == "buy_full"]
    e3 = False
    if relief_ok:
        last = relief_ok[-1]
        freed_after = [r for r in rows[last + 1:] if r.get("event") == "slot_relief"
                       and int(r.get("freed") or 0) > 0]
        sell_after = [r for r in rows[last + 1:] if r.get("event") == "sell"
                      and r.get("strategy") == "slot_relief_space" and r.get("ok")]
        e3 = not freed_after and not sell_after
    e4 = int(de.get("pending_executable") or 0) == 0 and int(de.get("pending_malformed") or 0) == 0
    e5 = int(de.get("loot_lost_steps") or 0) <= 5
    gates = {"E1_理由": e1, "E2_最后观测真满": e2, "E3_腾格用尽": e3,
             "E4_无可执行无残缺": e4, "E5_浪费有界": e5}
    detail = {"gates": gates, "relief_events": len(relief_idx),
              "relief_pressure_events": len(relief_ok),
              "free_slots_last": de.get("free_slots_last"),
              "loot_lost_steps": de.get("loot_lost_steps"),
              "pending_executable": de.get("pending_executable"),
              "pending_malformed": de.get("pending_malformed")}
    return ("green" if all(gates.values()) else "red"), detail


def judge_claim_source(text: str) -> tuple[str, dict[str, Any]]:
    """J2s（Lead 裁定）：task-26 之后旧组合不可复现 —— 只认源码级证据 + 单测反向用例。"""
    has_claim = "claim_exhausted = (" in text
    budget_prefix = "resume_budget_exhausted:" in text
    guarded = "if claim_exhausted:" in text
    ok = has_claim and budget_prefix and guarded
    return ("green" if ok else "red"), {"claim_exhausted_assign": has_claim,
                                        "budget_prefix": budget_prefix,
                                        "guarded_write": guarded}


def judge_resume_claim(day: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """J2：resume_exhausted 必须 exec==0 且 malformed==0；budget 变体必须带走路预算证据。"""
    de = day["day_end"]
    reason = str(de.get("ended_reason") or "")
    prefix = reason.split(":", 1)[0]
    if prefix not in ("resume_exhausted", "resume_budget_exhausted"):
        return "none", {"reason": f"ended_reason={reason[:40]}"}
    exec_ = de.get("pending_executable")
    mal = de.get("pending_malformed")
    if exec_ is None or mal is None:
        return "none", {"reason": "日终缺 pending_executable/pending_malformed"}
    if prefix == "resume_exhausted":
        ok = int(exec_) == 0 and int(mal) == 0
        return ("green" if ok else "red"), {"executable": exec_, "malformed": mal}
    # resume_budget_exhausted：账本仍有余格，但必须能看到"走路预算用尽"的证据
    bursts = [r for r in day["rows"] if r.get("event") == "no_progress_burst"]
    ev = [r for r in bursts if r.get("claim_exhausted") is not None]
    ok = int(exec_) > 0 and bool(ev) and any(
        r.get("resume_walk_attempts") is not None and r.get("resume_walks") is not None for r in ev)
    return ("green" if ok else "red"), {"executable": exec_, "budget_events": len(ev)}


def judge_pending_arith(day: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """J3：pending 不变式判红/绿；blocked−stalled 差额只作 INFO（Lead 已裁【无法判定】）。"""
    de = day["day_end"]
    need = ("pending_ledger", "pending_guard", "pending_blocked", "pending_executable",
            "pending_unobserved", "pending_malformed", "pending_stalled")
    if any(de.get(k) is None for k in need):
        return "none", {"reason": "日终缺 pending_*（0.7.44 账本）"}
    inv1 = int(de["pending_ledger"]) == int(de["pending_guard"]) + int(de["pending_blocked"])
    inv2 = int(de["pending_guard"]) == (int(de["pending_executable"]) + int(de["pending_unobserved"])
                                        + int(de["pending_malformed"]))
    delta = int(de["pending_blocked"]) - int(de["pending_stalled"])
    explained = de.get("pending_blocked_other") is not None or de.get("pending_blocked_tiles") is not None
    return ("green" if (inv1 and inv2) else "red"), {
        "inv1": inv1, "inv2": inv2, "blocked_minus_stalled": delta, "explained_field": explained}


def judge_till_shape(day: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """J4：till 的 unreachable 必须带落脚证据（0.7.45 形态：till 12 格静默记 unreachable ⇒ 红）。"""
    ev = [r for r in day["rows"] if r.get("event") == "unreachable_stage"]
    by_stage: dict[str, int] = {}
    for r in ev:
        by_stage[str(r.get("stage"))] = by_stage.get(str(r.get("stage")), 0) + int(r.get("tiles") or 0)
    till = by_stage.get("till_area", 0)
    if till == 0:
        return "none", {"by_stage": by_stage}
    encircled = [r for r in day["rows"] if r.get("event") == "encircled"]
    prefiltered = [r for r in encircled if r.get("prefilter")]
    # 0.7.46 要求：till 的挡死格走 prefilter/encircled 且带 kinds；旧账本一条都没有 ⇒ 红
    ok = bool(prefiltered) or bool([r for r in encircled if r.get("stage") == "till_area"])
    return ("green" if ok else "red"), {"by_stage": by_stage, "encircled": len(encircled),
                                        "prefiltered": len(prefiltered)}


def judge_sell_discipline(day: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """J5：售材纪律（禁止集零卖；92/766 需归类依据）。"""
    sold: list[str] = []
    has_category = False
    for r in day["rows"]:
        if r.get("event") == "sell":
            sold.append(qid_of(r.get("qid")))
            if r.get("category") or r.get("tier_basis") or r.get("classification"):
                has_category = True
        elif r.get("event") == "slot_relief":
            for s in r.get("sold") or []:
                sold.append(qid_of((s or {}).get("qid")))
                if (s or {}).get("category") or (s or {}).get("classification"):
                    has_category = True
    if not sold:
        return "none", {"sold": []}
    bad = sorted({q for q in sold if q in FORBIDDEN_SELL_QIDS})
    preserve_sold = sorted({q for q in sold if q in PRESERVE_QIDS})
    ok = not bad and not (preserve_sold and not has_category)
    return ("green" if ok else "red"), {"sold": sorted(set(sold)), "forbidden": bad,
                                        "preserve_sold": preserve_sold, "category_evidence": has_category}


def replay_a8(rows: list[dict[str, Any]]) -> dict[str, Any]:
    """J6：A8 的 263/217 形态（沿用 task-21/23 的复算口径）。"""
    days = day_groups(rows)
    co = 0
    for d in days:
        de = d["day_end"]
        ev = [r for r in d["rows"] if r.get("event") == "deferred_by_budget"]
        fw = de.get("final_water") or {}
        if ev and (de.get("checks") or {}).get("watered_outdoor") is True and int(fw.get("dry") or 0) == 0:
            co += 1
    ends = {str((d["day_end"].get("day_text") or "")): d["day_end"] for d in days}
    return {"days": len(days), "budget_water_same_truth": co,
            "day_keys": list(ends)[:3],
            "winter9_slept": (ends.get("1年 winter 9日") or {}).get("checks", {}).get("slept_by_us")}


# ---------------------------------------------------------------- self-tests
def self_tests() -> None:
    def de(**kw: Any) -> dict[str, Any]:
        base = {"event": "day_end", "day_text": "syn", "ended_by": "sleep", "ended_reason": "",
                "checks": {}, "pending_executable": 0, "pending_malformed": 0,
                "pending_ledger": 3, "pending_guard": 3, "pending_blocked": 0,
                "pending_unobserved": 3, "pending_stalled": 0,
                "free_slots_status": "ok", "free_slots_start": 0, "free_slots_last": 0,
                "free_slots_min": 0}
        base.update(kw)
        return {"day_end": base, "rows": [base]}

    # J1（E1–E5）：五条全过 ⇒ green；反向三例必须 False
    g = de(ended_by="inventory_blocked", ended_reason="inventory_blocked:满", loot_lost_steps=3)
    g["rows"] += [
        {"event": "slot_relief", "trigger": "space_pressure", "freed": 0,
         "blocked_reason": "腾不动"},
        {"event": "sell", "qid": "(O)262", "ok": True, "strategy": "other"},
    ]
    expect("selftest J1 green(E1–E5)", judge_inventory_blocked(g)[0], "green")
    expect("selftest J1 red(E2 last≠0)", judge_inventory_blocked(de(
        ended_by="inventory_blocked", loot_lost_steps=0, free_slots_last=1))[0], "red")
    expect("selftest J1 red(E4 exec>0)", judge_inventory_blocked(de(
        ended_by="inventory_blocked", loot_lost_steps=0, pending_executable=1))[0], "red")
    expect("selftest J1 none(缺字段)", judge_inventory_blocked(de(
        ended_by="inventory_blocked", free_slots_status=None))[0], "none")
    # 反向三例（Lead 点名）：冬27 形态 loot=205；满包但 exec>0；relief 后卖出成功
    winter27 = de(ended_by="inventory_blocked", loot_lost_steps=205, pending_executable=7,
                  pending_guard=7, pending_unobserved=0)
    expect("selftest J1 red(冬27 loot=205)", judge_inventory_blocked(winter27)[0], "red")
    sold_after = de(ended_by="inventory_blocked", loot_lost_steps=0)
    sold_after["rows"] += [
        {"event": "slot_relief", "trigger": "space_pressure", "freed": 0},
        {"event": "sell", "qid": "(O)262", "ok": True, "strategy": "slot_relief_space"},
    ]
    expect("selftest J1 red(relief 后又卖出)", judge_inventory_blocked(sold_after)[0], "red")
    # J2（旧账本形态仅作合成判据；0.7.46 起不可复现 —— 真账本只记 INFO）
    expect("selftest J2 green", judge_resume_claim(de(ended_reason="resume_exhausted:回片区"))[0], "green")
    expect("selftest J2 red(exec=7)", judge_resume_claim(de(
        ended_reason="resume_exhausted:回片区", pending_executable=7))[0], "red")
    budget = de(ended_reason="resume_budget_exhausted:预算",
                pending_executable=7, pending_guard=7, pending_unobserved=0)
    budget["rows"].append({"event": "no_progress_burst", "claim_exhausted": False,
                           "resume_walks": 5, "resume_walk_attempts": 9})
    expect("selftest J2 green(budget 证据)", judge_resume_claim(budget)[0], "green")
    # J2s：源码级证据（claim_exhausted=(exec==0 and malformed==0) + budget 前缀 + 守卫写）
    src_ok = ('claim_exhausted = (int(snap["executable"]) == 0\n'
              '                           and int(snap.get("malformed", 0)) == 0)\n'
              'if claim_exhausted:\n    why = "resume_exhausted:x"\n'
              'else:\n    why = "resume_budget_exhausted:x"')
    expect("selftest J2s green", judge_claim_source(src_ok)[0], "green")
    expect("selftest J2s red(无 claim_exhausted)", judge_claim_source("pass")[0], "red")
    # J3：不变式破坏 ⇒ red；5 格差额只 INFO（不判红）
    expect("selftest J3 green", judge_pending_arith(de())[0], "green")
    expect("selftest J3 red(ledger≠guard+blocked)", judge_pending_arith(de(pending_ledger=9))[0], "red")
    st, det = judge_pending_arith(de(
        pending_ledger=230, pending_guard=7, pending_blocked=223, pending_executable=7,
        pending_unobserved=0, pending_stalled=218))
    expect("selftest J3 green(5 格差额只 INFO)", st, "green")
    # J4：till unreachable 无 encircled 证据 ⇒ red；有 prefilter ⇒ green
    till = de()
    till["rows"].append({"event": "unreachable_stage", "stage": "till_area", "tiles": 12})
    expect("selftest J4 red(till 无证据)", judge_till_shape(till)[0], "red")
    till2 = de()
    till2["rows"] += [{"event": "unreachable_stage", "stage": "till_area", "tiles": 12},
                      {"event": "encircled", "stage": "till_area", "prefilter": True}]
    expect("selftest J4 green(prefilter)", judge_till_shape(till2)[0], "green")
    # J5：卖禁售品 ⇒ red；只卖 Wheat ⇒ green；Sap 无归类 ⇒ red
    bad = de()
    bad["rows"].append({"event": "sell", "qid": "(O)388", "ok": True})
    expect("selftest J5 red(Wood)", judge_sell_discipline(bad)[0], "red")
    good = de()
    good["rows"].append({"event": "sell", "qid": "(O)262", "ok": True})
    expect("selftest J5 green(Wheat)", judge_sell_discipline(good)[0], "green")
    keep = de()
    keep["rows"].append({"event": "sell", "qid": "(O)92", "ok": True})
    expect("selftest J5 red(Sap 无归类)", judge_sell_discipline(keep)[0], "red")


def head_source(rel: str) -> str:
    """读 HEAD 的源码（不读工作树：工作树有 task-28 在制改动）。"""
    import subprocess
    r = subprocess.run(["git", "-C", str(REPO), "show", f"HEAD:{rel}"], capture_output=True)
    if r.returncode != 0:
        return ""
    return r.stdout.decode("utf-8", "replace")


# ---------------------------------------------------------------- real replay
def real_replay() -> None:
    smoke = load_jsonl(SMOKE)
    days = day_groups(smoke)
    print(f"\n== smoke-0745：{len(smoke)} 行 / {len(days)} 天")

    def hit(tag: str, state: str, want: str, detail: str) -> None:
        expect(tag, state, want, detail)

    for d in days:
        label = str(d["day"])
        de = d["day_end"]
        if de.get("ended_by") == "inventory_blocked":
            state, detail = judge_inventory_blocked(d)
            say(f"smoke {label} J1（旧账本按 E1–E5，仅 INFO）", "INFO",
                json.dumps(detail, ensure_ascii=False))
        state, detail = judge_resume_claim(d)
        if state != "none":
            say(f"smoke {label} J2（0.7.46 起不可复现，仅记 INFO）", "INFO",
                json.dumps(detail, ensure_ascii=False))
        state, detail = judge_pending_arith(d)
        if state != "none":
            if state == "red":
                hit(f"smoke {label} J3 不变式", state, "red", json.dumps(detail, ensure_ascii=False))
            elif detail.get("blocked_minus_stalled"):
                say(f"smoke {label} J3 差额（Lead 已裁无法判定，仅 INFO）", "INFO",
                    json.dumps(detail, ensure_ascii=False))
            else:
                hit(f"smoke {label} J3", state, "green", json.dumps(detail, ensure_ascii=False))
        state, detail = judge_sell_discipline(d)
        if state != "none":
            hit(f"smoke {label} J5", state, "red", json.dumps(detail, ensure_ascii=False))
        state, detail = judge_till_shape(d)
        if state != "none":
            hit(f"smoke {label} J4", state, "red", json.dumps(detail, ensure_ascii=False))

    # J2s：HEAD 源码级证据（task-26 之后旧组合不可复现）
    src = head_source("brain/agentfarm/longrun.py")
    state, detail = judge_claim_source(src)
    hit("HEAD longrun.py J2s", state, "green", json.dumps(detail, ensure_ascii=False))

    # 32 格归属表（独立重算，不给代码结论）
    print("\n== 32 格 till/clear 归属（0.7.45 账本）")
    for d in days:
        ev = [r for r in d["rows"] if r.get("event") == "unreachable_stage"]
        if not ev:
            continue
        print(f"  {d['day']}: " + ", ".join(
            f"{r.get('stage')}/{r.get('zone')}={r.get('tiles')}" for r in ev))
        print(f"    合计={sum(int(r.get('tiles') or 0) for r in ev)}")

    print("\n== 售材 qid（smoke-0745）")
    sold: list[str] = []
    for d in days:
        for r in d["rows"]:
            if r.get("event") == "sell":
                sold.append(qid_of(r.get("qid")))
            elif r.get("event") == "slot_relief":
                for s in r.get("sold") or []:
                    sold.append(qid_of((s or {}).get("qid")))
    print("  sold =", sorted(set(sold)))
    print("  禁售命中 =", sorted(set(sold) & set(FORBIDDEN_SELL_QIDS)))
    print("  保留项命中 =", sorted(set(sold) & set(PRESERVE_QIDS)))

    a8 = load_jsonl(A8)
    print("\n== A8 账本（J6 复算）")
    print("  ", json.dumps(replay_a8(a8), ensure_ascii=False))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    print("== 0.7.46 预热：账本重放与判据草案（草案，不是正式判定）==")
    self_tests()
    real_replay()
    bad = [r for r in results if r[1] == "FAIL"]
    reds = [r for r in results if r[1] == "red"]
    print(f"\n汇总：FAIL={len(bad)}，判红命中={len(reds)}，共 {len(results)} 条")
    if bad:
        print("FAIL：")
        for tag, _, detail in bad:
            print("  -", tag, detail)
    if args.out:
        lines = [f"[{s}] {t} — {d}" for t, s, d in results]
        out = Path(args.out)
        out.write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"证据写入 {out}")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
