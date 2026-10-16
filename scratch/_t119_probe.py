"""task-119 独立二次 delta 复验：task-118（`9df8c3b`）能否堵住我 task-115 的三个反例。

只写 scratch/。用法：
    $env:PYTHONUTF8="1"; & $py scratch\\_t119_probe.py
可用 T119_ROOT 指向别的工作树做 pre/post 对照。

判据（Lead m05419）：
  B 段 ①  我的反例正向化：20 条可信 + 伪造 ⇒ 可信 20/20、伪造不进提示词、不占首位
  防洗白  回写只持久化可信条目；重新载入仍不可信、伪造文本不进文件
  来源面  make_lesson 带 src；合并取最保守；旧格式整库不可信但可见（带前缀）
  C 段    零判定影响四形态未回退（复用 task-115 探针）
  D 段    F2 四档丢弃顺序 + NIT-1 真值 evidence 未回退（复用 task-115 探针）
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(os.environ.get("T119_ROOT") or Path(__file__).resolve().parents[1])
for p in (str(ROOT), str(ROOT / "brain"), str(ROOT / "tests"), str(ROOT / "scratch")):
    if p not in sys.path:
        sys.path.insert(0, p)

import test_longrun as TL  # noqa: E402
import agentfarm.planner as P  # noqa: E402
import _t112_probe as A  # noqa: E402
import _t115_probe as B  # noqa: E402  复用 FORGED / run_with_lessons / part_b / part_c / part_d

RESULTS = A.RESULTS
CARD_FIVE = B.CARD_FIVE
FORGED = B.FORGED


def check(tag: str, ok: bool, detail: str = "") -> None:
    A.check(tag, ok, detail)


def trusted(n: int, *, kind: str = "stage_incomplete", text: str = "真教训"):
    return [dict(P.make_lesson(kind=kind, scope=f"g{i}", day_seq=i, symptom=f"{text}{i}"), last_seq=i)
            for i in range(1, n + 1)]


def run_led(items):
    """同一份库跑一天；返回 (run, prompts, 库文件 Path, holder)。"""
    return B.run_with_lessons(items, days=1, max_days=1)


def rej_of(run):
    ev = A.events(run, "lessons_rejected")
    return ev[0] if ev else {}


def prompt_text(prompts) -> str:
    return "\n".join(prompts)


# --------------------------------------------------------------------------
def part_reverse() -> None:
    print("\n===== B 段 ①：task-115 反例正向化（20 条可信 + 伪造）=====")
    cases = [
        ("B1 单喂 last_seq=999999（我的 A2b 原反例）", [FORGED["last_seq=999999（kind 合法）"][0]],
         "MARKER-EVICT"),
        ("B2 单喂 last_seq=21（我的 A2c）",
         [dict(FORGED["last_seq=999999（kind 合法）"][0], last_seq=21, symptom="MARKER-EVICT-21")],
         "MARKER-EVICT-21"),
        ("B3 单喂 last_seq=1+count=10**9（我的 A2d）",
         [dict(FORGED["last_seq=999999（kind 合法）"][0], last_seq=1, count=10 ** 9,
               symptom="MARKER-EVICT-COUNT")],
         "MARKER-EVICT-COUNT"),
        ("B4 卡面五类一起喂（我的 A1c）", [FORGED[k][0] for k in CARD_FIVE], None),
    ]
    for tag, forged_items, marker in cases:
        run, prompts, jp, holder = run_led(trusted(P.LESSONS_MAX) + forged_items)
        ids = [it.get("id") for it in run.lessons]
        kept_genuine = [i for i in ids if str(i).startswith("stage_incomplete|g")]
        rej = rej_of(run)
        text = prompt_text(prompts)
        markers = [marker] if marker else [FORGED[k][2] for k in CARD_FIVE]
        leaked = [m for m in markers if m and m in text]
        check(f"{tag}：可信教训必须 20/20 存活",
              len(kept_genuine) == P.LESSONS_MAX, f"存活 {len(kept_genuine)}/{P.LESSONS_MAX} ids={ids[:3]}")
        check(f"{tag}：伪造条目一个都不许占名额 / 进提示词 / 排首位",
              not leaked and "unreachable|clear_area" not in ids and not any(m in ids for m in ("x|y",)),
              f"leaked={leaked} 伪造在库内={'unreachable|clear_area' in ids} rank0={ids[:1]}")
        if marker:
            # last_seq 已在跨条目上界内（≤ max(可信)+1）时不产生 clamped 理由，属预期 ⇒ 只要求如实记 untrusted
            check(f"{tag}：留痕 untrusted=1（clamped 理由视是否真的越界而定）",
                  int(rej.get("untrusted") or 0) == len(forged_items),
                  f"untrusted={rej.get('untrusted')} reasons={rej.get('reasons')}")
        else:
            check(f"{tag}：留痕 untrusted=5（五类里结构合法的三条 + 拒收的两条）",
                  int(rej.get("untrusted") or 0) >= 3,
                  f"untrusted={rej.get('untrusted')} dropped={rej.get('dropped')} reasons={rej.get('reasons')}")
        holder.cleanup()


def part_source() -> None:
    print("\n===== 来源面：make_lesson / 合并保守性 / 钳位 / 前缀 / 旧格式 =====")
    mk = P.make_lesson(kind="unreachable", scope="clear_area", day_seq=3, symptom="可信")
    check("S1 make_lesson 写出的条目带 src=agentfarm", mk.get("src") == P.LESSON_SRC, f"src={mk.get('src')!r}")

    # 合并取最保守：可信 + 不可信 同 id ⇒ 合并后不许还带 src
    forged_same = {"id": "unreachable|clear_area", "kind": "unreachable", "scope": "clear_area",
                   "symptom": "MARKER-LAUNDER", "count": 5, "last_seq": 99,
                   "first_day": [1, "summer", 1], "last_day": [1, "summer", 2]}
    merged = P.prune_lessons([mk, forged_same], max_lessons=10)
    check("S2 合并取最保守：可信+不可信同 id ⇒ 合并条目丢掉 src（不得沾上可信身份）",
          len(merged) == 1 and merged[0].get("src") != P.LESSON_SRC,
          f"merged={[(it.get('id'), it.get('src')) for it in merged]}")
    both = P.prune_lessons([mk, dict(mk, last_seq=4)], max_lessons=10)
    check("S3 两条都可信 ⇒ 合并后仍带 src",
          len(both) == 1 and both[0].get("src") == P.LESSON_SRC, f"src={both[0].get('src')!r}")

    # 钳位 + 排序 + 前缀（1 条可信[不同 id] + 2 条不可信 ⇒ 不可信只能填位）
    t2 = P.make_lesson(kind="far_dry_given_up", scope="water_far", day_seq=5, symptom="可信-干格认输")
    holder = tempfile.TemporaryDirectory()
    p = Path(holder.name) / "run9-lessons.json"
    items = [t2,
             {"id": "unreachable|clear_area", "kind": "unreachable", "scope": "clear_area",
              "symptom": "MARKER-OUT-1", "count": 10 ** 9, "last_seq": 10 ** 9,
              "first_day": [1, "summer", 1], "last_day": [1, "summer", 2]},
             {"id": "encircled|clear_area", "kind": "encircled", "scope": "clear_area",
              "symptom": "MARKER-OUT-2", "count": 7, "last_seq": 10 ** 9,
              "first_day": [1, "summer", 1], "last_day": [1, "summer", 2]}]
    p.write_text(json.dumps({"lessons": items}, ensure_ascii=False), encoding="utf-8")
    rep: dict = {}
    loaded, err = P.load_lessons_file(p, report=rep)
    order = [("T" if it.get("src") == P.LESSON_SRC else "U") + str(it.get("id")) for it in loaded]
    untrusted_items = [it for it in loaded if it.get("src") != P.LESSON_SRC]
    check("S4 钳位：不可信 last_seq ≤ max(可信)+1、count ≤ LESSON_COUNT_MAX，且可信排第一",
          err == "" and order and order[0].startswith("T")
          and all(int(it.get("last_seq") or 0) <= 6 for it in untrusted_items)
          and all(int(it.get("count") or 0) <= P.LESSON_COUNT_MAX for it in untrusted_items),
          f"order={order} seqs={[it.get('last_seq') for it in untrusted_items]} "
          f"counts={[it.get('count') for it in untrusted_items]}")
    check("S5 report 如实：untrusted=2 + reasons 含 clamped:last_seq",
          int(rep.get("untrusted") or 0) == 2 and "clamped:last_seq" in list(rep.get("reasons") or []),
          f"report={rep}")
    text = P.render_lessons(loaded, max_items=3, max_chars=400)
    check("S6 渲染前缀：不可信行带 [外部条目·未验证]，可信行不带",
          f"- {P.UNTRUSTED_LESSON_PREFIX}" in text and "- 可信-干格认输" in text
          and f"- {P.UNTRUSTED_LESSON_PREFIX}可信-干格认输" not in text,
          f"text={text!r}")

    # S8 合并累加能否越过 count 钳位（NIT 证据）
    dup = [{"id": "unreachable|dup", "kind": "unreachable", "scope": "dup", "symptom": "U1",
            "count": P.LESSON_COUNT_MAX, "last_seq": 1,
            "first_day": [1, "summer", 1], "last_day": [1, "summer", 2]},
           {"id": "unreachable|dup", "kind": "unreachable", "scope": "dup", "symptom": "U2",
            "count": P.LESSON_COUNT_MAX, "last_seq": 2,
            "first_day": [1, "summer", 1], "last_day": [1, "summer", 3]}]
    p.write_text(json.dumps({"lessons": dup}, ensure_ascii=False), encoding="utf-8")
    loaded3, _ = P.load_lessons_file(p, report={})
    merged_count = int((loaded3[0].get("count") if loaded3 else 0) or 0)
    check(f"S8 NIT 证据：逐条钳位后合并累加可越过 LESSON_COUNT_MAX（实测 {merged_count} / 上限 {P.LESSON_COUNT_MAX}）",
          merged_count >= P.LESSON_COUNT_MAX, f"merged_count={merged_count}")

    # 旧格式整库（无 src）⇒ 全不可信、可见但不抢位
    legacy = [{k: v for k, v in dict(mk, scope=f"L{i}", id=f"unreachable|L{i}").items() if k != "src"}
              for i in range(1, 4)]
    p.write_text(json.dumps({"lessons": legacy}, ensure_ascii=False), encoding="utf-8")
    rep2 = {}
    loaded2, _ = P.load_lessons_file(p, report=rep2)
    legacy_text = P.render_lessons(loaded2, max_items=1, max_chars=200)
    check("S7 旧格式整库无 src ⇒ 全部 untrusted、last_seq 钳到 1、仍可见（带前缀）",
          len(loaded2) == 3 and int(rep2.get("untrusted") or 0) == 3
          and all(int(it.get("last_seq") or 0) == 1 for it in loaded2)
          and f"- {P.UNTRUSTED_LESSON_PREFIX}" in legacy_text,
          f"n={len(loaded2)} report={rep2} seqs={[it.get('last_seq') for it in loaded2]} text={legacy_text!r}")
    holder.cleanup()


def part_merge_loss() -> None:
    print("\n===== 同 id 合并造成的持久化损失（NIT 取证）=====")
    t = P.make_lesson(kind="unreachable", scope="clear_area", day_seq=4, symptom="真教训-会被合并掉")
    forged = {"id": "unreachable|clear_area", "kind": "unreachable", "scope": "clear_area",
              "symptom": "MARKER-MERGE-KILL", "count": 9, "last_seq": 99,
              "first_day": [1, "summer", 1], "last_day": [1, "summer", 2]}
    run, prompts, jp, holder = run_led([t, forged])
    lp = Path(str(jp)[:-6] + "-lessons.json")
    saved = json.loads(lp.read_text(encoding="utf-8")).get("lessons") or []
    check("W6 同 id 合并 ⇒ 真教训从持久化库里消失（不抢名额、但有损）",
          not any("真教训-会被合并掉" in json.dumps(it, ensure_ascii=False) for it in saved)
          and all(it.get("src") == P.LESSON_SRC for it in saved)
          and not any("MARKER-MERGE-KILL" in json.dumps(it, ensure_ascii=False) for it in saved),
          f"saved={[(it.get('id'), it.get('symptom'), it.get('src')) for it in saved]}")
    holder.cleanup()


def part_whitewash() -> None:
    print("\n===== 防洗白：回写只持久化可信条目 + 重载仍不可信 =====")
    forged = dict(FORGED["last_seq=999999（kind 合法）"][0], symptom="MARKER-LAUNDER")
    run, prompts, jp, holder = run_led(trusted(2) + [forged])
    lp = Path(str(jp)[:-6] + "-lessons.json")
    saved = json.loads(lp.read_text(encoding="utf-8")).get("lessons") or []
    ev = A.events(run, "lessons")
    check("W1 回写后文件里只有可信条目（伪造文本不落盘）",
          bool(saved) and all(it.get("src") == P.LESSON_SRC for it in saved)
          and all("MARKER-LAUNDER" not in json.dumps(it, ensure_ascii=False) for it in saved),
          f"saved={[(it.get('id'), it.get('src')) for it in saved]}")
    rep: dict = {}
    reloaded, _ = P.load_lessons_file(lp, report=rep)
    check("W2 重新载入：无 untrusted（证明没被洗成可信）",
          int(rep.get("untrusted") or 0) == 0
          and all(it.get("src") == P.LESSON_SRC for it in reloaded),
          f"report={rep} srcs={[it.get('src') for it in reloaded]}")
    check("W3 journal lessons 如实回填 written / skipped_untrusted",
          bool(ev) and int(ev[0].get("skipped_untrusted") or 0) >= 1
          and int(ev[0].get("written") or -1) == len(saved),
          f"written={ev[0].get('written') if ev else None} "
          f"skipped={ev[0].get('skipped_untrusted') if ev else None} saved={len(saved)}")
    vis = P.render_lessons(run.lessons, max_items=3, max_chars=400)
    check("W4 当天内存里伪造条目仍可见、但带外部前缀（可见≠可信）",
          "MARKER-LAUNDER" in vis and P.UNTRUSTED_LESSON_PREFIX in vis, f"vis={vis!r}")
    check("W5 伪造文本当晚不许进提示词时排在可信之前",
          vis.find("- 真教训") < vis.find("MARKER-LAUNDER"), f"vis={vis!r}")
    holder.cleanup()


def part_fill() -> None:
    print("\n===== B 段 ①补充：库内只有 5 条可信 ⇒ 不可信只能填补空位 =====")
    items = trusted(5) + [
        dict(FORGED["last_seq=999999（kind 合法）"][0], symptom="MARKER-FILL-1"),
        {"id": "encircled|clear_area", "kind": "encircled", "scope": "clear_area",
         "symptom": "MARKER-FILL-2", "count": 3, "last_seq": 10 ** 9,
         "first_day": [1, "summer", 1], "last_day": [1, "summer", 2]},
    ]
    run, prompts, jp, holder = run_led(items)
    ids = [str(it.get("id")) for it in run.lessons]
    genu = [i for i in ids if i.startswith("stage_incomplete|g")]
    idx = {i: n for n, i in enumerate(ids)}
    order_ok = all(idx[i] < idx[j] for i in genu for j in ids if j not in genu)
    text = prompt_text(prompts)
    check("B5 5 条可信 + 2 条不可信 ⇒ 可信 5/5 全留、不可信只补空位且全部排在可信之后",
          len(genu) == 5 and len(ids) == 7 and order_ok and idx[ids[0]] == 0,
          f"ids={ids} order_ok={order_ok}")
    check("B5 不可信只补库内空位：注入的前 3 条仍是可信，提示词里不出现外部前缀",
          P.UNTRUSTED_LESSON_PREFIX not in text and text.count("- 真教训") >= 3
          and len([i for i in ids if not i.startswith("stage_incomplete|g")]) == 2,
          f"untrusted_in_lib={len([i for i in ids if not i.startswith('stage_incomplete|g')])} "
          f"text_tail={text[-120:]!r}")
    holder.cleanup()


def main() -> int:
    print(f"ROOT={ROOT}")
    part_reverse()
    part_fill()
    part_source()
    part_whitewash()
    part_merge_loss()
    B.part_b()   # F2 四档（未回退）
    B.part_c()   # 零判定影响四形态（未回退）
    B.part_d()   # NIT-1 真值 evidence（未回退）
    bad = [r for r in RESULTS if not r[1]]
    print(f"\n===== task-119 二次 delta 探针汇总：{len(RESULTS) - len(bad)}/{len(RESULTS)} PASS =====")
    for tag, _ok, detail in bad:
        print(f"  FAIL: {tag} :: {detail}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
