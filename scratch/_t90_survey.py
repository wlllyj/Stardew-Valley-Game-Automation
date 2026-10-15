"""task-90：同类洞普查（日标签注入之外，还有没有"按文本解析结构化字段"可被账本打穿）。

三部分：
  S1–S4  在**窗口内**的那一天塞各种脏标签（`]` / 换行 / 制表 / `[` / 空串）⇒ 修复版必须一律 fatal。
  S5     让**窗口外**那天与窗口内那天共用同一个标签（跨会话重名）⇒ 观测是"保守多报"还是"漏报"。
  S6     兜底分支普查：把修复版 `problem_day` 包一层间谍，跑全部账本（scratch+logs）× days=1/3，
         统计有多少条问题靠"最长前缀匹配"上来、有多少条走了会截断的 fallback、其中几条 head 不在已知日集合。

账本形状：前 3 天真失败（verified=False，会被降级成 history）+ 后 3 天干净 ⇒ streak=3、窗口=后 3 天。

用法：python scratch/_t90_survey.py
"""
from __future__ import annotations

import glob
import importlib.util
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import tests.test_verify_run3 as T  # noqa: E402

BASE_DAY = 10
N_BAD, N_GOOD = 3, 3


def load(path: str):
    spec = importlib.util.spec_from_file_location("vr3_" + os.path.basename(path), path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


FIXED = load(os.path.join(ROOT, "scratch", "_t90_tool_fixed.py"))
BUGGY = load(os.path.join(ROOT, "scratch", "_t90_tool_buggy.py"))


def relabel(rows, day_num: int, season: str):
    out = []
    for r in rows:
        nr = dict(r)
        if nr.get("event") == "day_start" and list(nr.get("day") or [0, 0, 0])[2] == day_num:
            nr["day"] = [1, season, day_num]
            nr["final"] = {"day": [1, season, day_num]}
        elif nr.get("event") == "day_end" and nr["final"]["day"][2] == day_num:
            nr["final"] = dict(nr["final"], day=[1, season, day_num])
            if nr.get("day_after"):
                nr["day_after"] = [1, season, day_num + 1]
        out.append(nr)
    return out


def make_bad(rows, day_num: int):
    """真失败的一天（verified=False，问题应被降级成 history）。"""
    out = []
    for r in rows:
        nr = dict(r)
        if nr.get("event") == "day_end" and nr["final"]["day"][2] == day_num:
            nr["verified"] = False
            nr["checks"] = dict(nr["checks"], crops_watered=False, watered_outdoor=False,
                                no_unmet_stages=False)
            nr["final"] = dict(nr["final"], unwatered_crops=9)
            nr["stages"] = [T.stage(tiles=10, ok=0, leftover=9)]
            nr["ok_steps"] = 0
        out.append(nr)
    return out


def make_contradiction(rows, day_num: int):
    """自称达标（verified=True）但账目自相矛盾的一天 ⇒ 必须是一条 problem（在窗口内时 fatal）。"""
    out = []
    for r in rows:
        nr = dict(r)
        if nr.get("event") == "day_end" and nr["final"]["day"][2] == day_num:
            nr["stages"] = [T.stage(tiles=10, ok=8, leftover=2)]
            nr["ok_steps"] = 8
            nr["unreachable"] = 2
            nr["unreachable_bound"] = 5
            nr["attempted"] = 10
        out.append(nr)
    return out


def base_book():
    rows = T.green_rows(N_BAD + N_GOOD)
    for i in range(N_BAD):
        rows = make_bad(rows, BASE_DAY + i)
    return rows


def run(mod, rows, days=3):
    ok, s = mod.report(rows, target_days=days)
    return {"rc": 0 if ok else 1, "verdict": s.get("verdict"),
            "n_problems": len(s.get("problems") or []), "n_history": len(s.get("history_problems") or []),
            "streak": s.get("verified_streak_tail"),
            "problems": s.get("problems") or [], "history": s.get("history_problems") or []}


def main() -> int:
    b0 = base_book()
    r0 = run(FIXED, b0)
    print(f"== 基座（前 {N_BAD} 天真失败 + 后 {N_GOOD} 天干净）==")
    print(f"  rc={r0['rc']} verdict={r0['verdict']} streak={r0['streak']} "
          f"#prob={r0['n_problems']} #hist={r0['n_history']}（history 应 >0：坏日在窗口外）")

    print("\n== S1–S4 窗口内（spring 14）脏标签：修复版必须一律 fatal ==")
    variants = [("正常 spring", "spring"), ("含 ]", "spring]x"), ("含换行", "spring\n14"),
                ("含 [ 与制表", "sp[ring\t14"), ("空串", "")]
    for tag, season in variants:
        rows = relabel(make_contradiction(b0, 14), 14, season)
        r = run(FIXED, rows)
        key = FIXED.day_key({"day": [1, season, 14]})
        print(f"  {tag:<12} key={key!r:<14} rc={r['rc']} verdict={r['verdict']:<13} "
              f"#prob={r['n_problems']} #hist={r['n_history']} streak={r['streak']}")

    print("\n== S5 标签重名（跨会话同一天）的方向性 ==")
    # S5a：谓词级 —— 窗口外的日与窗口内的日共用同一标签时，会往哪个方向错？
    known = {"spring 10", "spring 15"}
    tail = {"spring 15"}

    def demote(text: str) -> bool:  # 复刻工具 :940-950 的降级条件
        head = FIXED.problem_day(text, known)
        return bool(head and head in known and head not in tail)

    print(f"  S5a [spring 10]（真属于窗口外）⇒ 降级={demote('[spring 10] boom')}（期望 True）")
    print(f"  S5a [spring 15]（假称属于窗口外那天，标签与窗口内日同名）⇒ 降级="
          f"{demote('[spring 15] boom')}（False ⇒ 保守保留为 fatal，绝不漏报）")
    # S5b：把窗口外那天的日号也改成窗口内那天的日号 ⇒ 日链 +1 必然断
    rows = list(b0)
    rows = relabel(rows, BASE_DAY + N_BAD - 1, "spring")
    for i, r in enumerate(rows):
        nr = dict(r)
        if nr.get("event") in ("day_start", "day_end") and \
                list((nr.get("day") or (nr.get("final") or {}).get("day") or [0, 0, 0]))[2] == 12:
            arr = [1, "spring", 15]
            nr["day"] = arr
            if isinstance(nr.get("final"), dict):
                nr["final"] = dict(nr["final"], day=list(arr))
            rows[i] = nr
    r = run(FIXED, rows)
    print(f"  S5b 把坏日 12 改成 15（真同名）⇒ rc={r['rc']} verdict={r['verdict']} "
          f"#prob={r['n_problems']} #hist={r['n_history']}")
    for p in r["problems"][:2]:
        print(f"    PROBLEM: {p}")

    print("\n== S6 兜底分支普查（全部账本 × days=1/3）==")
    books = sorted(glob.glob(os.path.join(ROOT, "scratch", "*.jsonl")) +
                   glob.glob(os.path.join(ROOT, "logs", "*.jsonl")))
    stats = {"books": 0, "runs": 0, "calls": 0, "prefix": 0, "fallback": 0, "fallback_unknown": 0}
    orig = FIXED.problem_day

    def spy(text, known):
        stats["calls"] += 1
        head = None
        if text.startswith("["):
            for name in sorted(known, key=len, reverse=True):
                if name and text.startswith(f"[{name}]"):
                    head = name
                    break
            if head:
                stats["prefix"] += 1
            else:
                stats["fallback"] += 1
                if text[1:].split("]", 1)[0] not in known:
                    stats["fallback_unknown"] += 1
        return orig(text, known)

    FIXED.problem_day = spy
    try:
        for b in books:
            try:
                rows = FIXED.load(b)
            except Exception:  # noqa: BLE001
                continue
            stats["books"] += 1
            for days in (1, 3):
                try:
                    FIXED.report(rows, target_days=days)
                    stats["runs"] += 1
                except Exception:  # noqa: BLE001
                    pass
    finally:
        FIXED.problem_day = orig
    print(f"  账本 {stats['books']} 本 / report() {stats['runs']} 次；problem_day 调用 {stats['calls']} 次")
    print(f"  最长前缀命中 {stats['prefix']} 次；走 fallback {stats['fallback']} 次"
          f"（其中 head 不在已知日集合 {stats['fallback_unknown']} 次 ⇒ 会被判 fatal）")

    print("\n== helper 级：未知/伪造标签的判定 ==")
    known = {"spring 10", "springx 11"}
    for text in ("[spring 10] boom", "[springx 11] boom", "[spring]x 11] boom",
                 "[summer 99] boom", "全局问题不带前缀"):
        got = FIXED.problem_day(text, known)
        print(f"  problem_day({text!r}) = {got!r} ⇒ {'fatal(不在已知日集合)' if got not in known else '可降级'}")

    print("\n== S7 对照：同样输入在带洞副本（7c4ff68）上 ==")
    for tag, rows in (("窗口内脏标签 spring]x", relabel(make_contradiction(b0, 14), 14, "spring]x")),
                      ("基座", b0)):
        r = run(BUGGY, rows)
        print(f"  {tag:<24} buggy rc={r['rc']} verdict={r['verdict']} #prob={r['n_problems']} #hist={r['n_history']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
