#!/usr/bin/env python
"""compare-runs.py —— run A vs run B 的「LLM 决策演进」对照取证（Lead 侧，只读）。

为什么有这个工具：
    用户的诉求是"让模型再玩这个游戏的时候具备决策演进的能力"（m12553）。
    代码侧由 task-58（`<journal>-lessons.json` 教训库 + 注入提示词）与 task-82（决策→结果 join）
    负责；但"演进"必须能被**外部复核**，否则又是一句自我声明。
    本工具把两本账本 + 两份 LLM 留痕并排，只回答三件事：
      ① run A 的教训库到底写了什么；
      ② 这些教训文本有没有真的出现在 run B 的 LLM 提示词里；
      ③ run A 里被取消/做不成的意图形态，在 run B 里的次数有没有变化（变了不等于因果，
         但"没变"是硬事实）。

它**不改判据、不参与验收 rc**：真正的判决仍以
`tools/verify-run3.py`（尾部窗口 + 严格整本第二判决）与 `tools/analyze-longrun.py` 为准。
**退出码承诺（task-217 统一）**：账本/sidecar 读不到或读坏 ⇒ `rc=2` 并说明是哪个文件
（缺文件/坏文件 ≠ 通过）；只要能读，L 级结论只进文本与 `--json`，**恒 `rc=0`**。
**L1 分母**只算 `-llm.jsonl` 的**决策行**（`kind="review"` 复盘行单独报数、不计入）。

用法：
    python tools/compare-runs.py --run-a logs\\longrun-3day-llm-run9.jsonl \\
                                --run-b logs\\longrun-3day-llm-run10.jsonl
    python tools/compare-runs.py --run-a ... --run-b ... --json scratch\\evolve.json
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

# 与 longrun 的 stage/verdict 词汇表对齐（只用于汇总展示，不参与判红）
PROBLEM_STOPPED = {
    "stamina", "budget", "no_seed", "need_refill", "world", "fading",
    "given_up_dry", "no_target", "sow_failed",
}


class LedgerReadError(Exception):
    """读不到/读坏账本或 sidecar。

    task-217：本工具的退出码承诺统一为——**读不到/读坏 ⇒ rc=2；能读 ⇒ 恒 rc=0**
    （L 级结论只进文本与 `--json`，不参与验收 rc）。以前这里 `raise SystemExit("[exit 2] …")`
    会被 Python 当成"错误消息 + rc=1"，文案却写着 `[exit 2]`，自相矛盾。
    """


def load_rows(path: Path) -> list[dict]:
    rows: list[dict] = []
    try:
        fh = path.open("r", encoding="utf-8")
    except OSError as exc:
        raise LedgerReadError(f"读不到 {path}：{exc}") from exc
    with fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise LedgerReadError(f"{path}:{lineno} 不是合法 JSON：{exc}") from exc
            if isinstance(row, dict):
                rows.append(row)
    return rows


def sidecar(journal: Path, suffix: str) -> Path:
    """`...-llm.jsonl` / `...-lessons.json` 与账本同目录同前缀。"""
    name = journal.name
    stem = name[:-6] if name.endswith(".jsonl") else name
    return journal.with_name(stem + suffix)


def norm(text: str) -> str:
    """归一化：去掉空白与常见标点，便于"教训是否进了提示词"的子串比对。"""
    return re.sub(r"[\s，。、；：（）()\[\]【】\"'`·…—,.;:]+", "", text or "")


def intents_of(decision: dict) -> list[dict]:
    out = []
    for item in decision.get("intents") or []:
        if isinstance(item, dict):
            out.append(item)
    return out


def shape_of(tasks: list[str]) -> str:
    return "+".join(sorted(t for t in tasks if t)) or "(空)"


def harvest(rows: list[dict]) -> dict:
    """把一本账本压成对照所需的计数。"""
    info: dict = {
        "rows": len(rows),
        "day_start": 0, "day_end": 0, "finish": None,
        "decisions": 0, "decisions_llm": 0, "shapes": {},
        "cancel_by_task": {}, "stage_fail_by_task": {}, "stage_ok_by_task": {},
        "days": [], "trace_rows": 0,
        # task-58/59/82 的演进对照（L1–L5）要用到的信号
        "ended_by": {}, "event_counts": {}, "checks_false": [], "decision_texts": [],
        # task-217：L2 按**现行形态**取信号（旧版 `ended_by:stuck` 在 0.7.37 起恒 0）
        "stage_stopped": {}, "stage_stopped_total": {},
        "stage_leftover": {}, "leftover_days_total": 0, "dead_crops_days": 0,
    }
    for row in rows:
        ev = row.get("ev") or row.get("event") or ""
        if ev:
            info["event_counts"][ev] = info["event_counts"].get(ev, 0) + 1
        if ev == "day_start":
            info["day_start"] += 1
        elif ev == "day_end":
            info["day_end"] += 1
            ended = str(row.get("ended_by") or "")
            info["ended_by"][ended] = info["ended_by"].get(ended, 0) + 1
            checks = row.get("checks") or {}
            false_keys = sorted(k for k, v in checks.items() if v is False) if isinstance(checks, dict) else []
            for k in false_keys:
                if k not in info["checks_false"]:
                    info["checks_false"].append(k)
            info["days"].append({
                "day": row.get("day_key") or row.get("day"),
                "ended_by": row.get("ended_by"),
                "verified": row.get("verified"),
                "ok_steps": row.get("ok_steps"),
                "failed_steps": row.get("failed_steps"),
                "checks_false": false_keys,
            })
            # 阶段结果在 day_end.stages[]（不是独立的 stage 事件；tiles 是整数不是坐标列表）
            if int(row.get("dead_crops") or 0) > 0:
                info["dead_crops_days"] += 1
            day_has_leftover = False
            for st in row.get("stages") or []:
                if not isinstance(st, dict):
                    continue
                stage = str(st.get("stage") or "?")
                ok = int(st.get("ok") or 0)
                bad = int(st.get("failed") or 0) or int(st.get("failed_any") or 0)
                if ok:
                    info["stage_ok_by_task"][stage] = info["stage_ok_by_task"].get(stage, 0) + ok
                if bad or str(st.get("stopped") or "") in PROBLEM_STOPPED:
                    info["stage_fail_by_task"][stage] = info["stage_fail_by_task"].get(stage, 0) + max(1, bad)
                # task-217：现行"卡住带 leftover"的真实形态 = 阶段 stopped + leftover>0
                stopped = str(st.get("stopped") or "")
                if stopped:
                    info["stage_stopped"][f"{stage}|{stopped}"] = (
                        info["stage_stopped"].get(f"{stage}|{stopped}", 0) + 1)
                    info["stage_stopped_total"][stopped] = (
                        info["stage_stopped_total"].get(stopped, 0) + 1)
                if int(st.get("leftover") or 0) > 0:
                    info["stage_leftover"][stage] = info["stage_leftover"].get(stage, 0) + 1
                    day_has_leftover = True
            if day_has_leftover:
                info["leftover_days_total"] += 1
        elif ev == "finish":
            info["finish"] = {
                "code": row.get("code"),
                "verified_streak": row.get("verified_streak"),
                "actions": row.get("actions"),
                "minutes": row.get("minutes"),
                "stuck_flushes": row.get("stuck_flushes"),
                "no_unmet_stages": row.get("no_unmet_stages"),
            }
        elif ev == "decision":
            info["decisions"] += 1
            if row.get("llm"):
                info["decisions_llm"] += 1
            tasks = [str(i.get("task") or "") for i in intents_of(row)]
            key = shape_of(tasks)
            info["shapes"][key] = info["shapes"].get(key, 0) + 1
            if len(info["decision_texts"]) < 400:
                bits = [key]
                for i in intents_of(row):
                    bits.append(str(i.get("reason") or ""))
                    bits.append(str(i.get("expected_evidence") or ""))
                info["decision_texts"].append(" ".join(b for b in bits if b))
        elif ev == "intent_verdict":
            for v in row.get("verdicts") or []:
                if isinstance(v, dict) and v.get("verdict") == "cancel":
                    task = str(v.get("task") or "?")
                    info["cancel_by_task"][task] = info["cancel_by_task"].get(task, 0) + 1
        elif ev == "stage" or ev == "stage_end":
            stage = str(row.get("stage") or "?")
            ok = int(row.get("ok") or 0)
            failed = int(row.get("failed") or 0)
            if ok:
                info["stage_ok_by_task"][stage] = info["stage_ok_by_task"].get(stage, 0) + ok
            if failed or str(row.get("stopped") or "") in PROBLEM_STOPPED:
                info["stage_fail_by_task"][stage] = info["stage_fail_by_task"].get(stage, 0) + max(1, failed)
    return info


def lessons_of(journal: Path) -> tuple[list[dict], str]:
    """读 run A 的教训库（task-82 的产物）。

    卡面允许 `<journal>-lessons.json` 或 `.jsonl`，也允许 `{"lessons": [...]}` 包裹；
    这里三种都认，认不出就当"没有教训库"（**缺文件 ≠ 通过**，由调用方如实报）。
    """
    for suffix in ("-lessons.json", "-lessons.jsonl"):
        path = sidecar(journal, suffix)
        if not path.exists():
            continue
        if suffix.endswith(".jsonl"):
            entries = [r for r in load_rows(path) if isinstance(r, dict)]
            jsonl_wrapped = [e for r in entries for e in (r.get("lessons") or [])
                             if isinstance(e, dict)]
            entries = jsonl_wrapped or entries
        else:
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
            except OSError as exc:
                raise LedgerReadError(f"读不到 {path}：{exc}") from exc
            except json.JSONDecodeError as exc:
                raise LedgerReadError(f"{path} 不是合法 JSON：{exc}") from exc
            entries = raw.get("lessons") if isinstance(raw, dict) else raw
            if not isinstance(entries, list):
                entries = []
        return [e for e in entries if isinstance(e, dict)], str(path)
    return [], ""


# 教训节在提示词里的固定抬头（brain 侧 `planner`/`longrun` 渲染；用于**结构性**判注入）
LESSON_SECTION_MARK = "从过去几天的账本里总结的教训"


def lesson_text(entry: dict) -> str:
    """取"这条教训被渲染进提示词"的那段文本。

    ⚠ 2026-10-17 事故（run A/B 对照误报「教训根本没送到」）：brain 写进
    `<journal>-lessons.json` 的字段是 `id/symptom/evidence/hint/count/day`，
    而这里原先只认 `lesson/text/summary/note/why/reason` ⇒ 取不到 ⇒ 退化成
    "把所有字段拼成一长串"，那一长串当然不是提示词的子串 ⇒ `hits=0`。
    实际提示词渲染的是 `- {symptom}〈{evidence}〉…{hint}`，**hint 与 symptom 都是逐字出现**。
    所以这里按"渲染时最可能逐字出现"的顺序取键，并把 `hint`（模型自述）放在前面。
    """
    for key in ("hint", "lesson", "text", "summary", "note", "why", "reason", "symptom"):
        val = entry.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    parts = [str(v) for v in entry.values() if isinstance(v, (str, int, float))]
    return " / ".join(parts).strip()


def lesson_full_text(entry: dict) -> str:
    """L3 旁证与展示用的**完整**教训文本（症状 + 证据 + 模型自述）。

    与 `lesson_text` 分工：`lesson_text` 负责"能不能在提示词里逐字找到"（子串命中），
    `lesson_full_text` 负责"这条教训在讲什么"（同指涉词表）。混用会两头出错：
    用完整文本做子串比对 ⇒ 拼出来的长串永不是提示词子串（2026-10-17 误报事故）；
    用单字段做词表 ⇒ 丢掉 `evidence` 里的 `leftover=12` 这类可核对的具体数字。
    """
    parts: list[str] = []
    for key in ("symptom", "evidence", "hint", "lesson", "text", "summary", "note", "why", "reason"):
        val = entry.get(key)
        if isinstance(val, str) and val.strip():
            parts.append(val.strip())
    if not parts:
        return lesson_text(entry)
    return " / ".join(dict.fromkeys(parts))


def lesson_section_present(prompts: list[str]) -> bool:
    """提示词里有没有「教训」这一节（结构性判据，不依赖逐条文本比对）。

    与 `lesson_text` 的逐条命中互为交叉核对：节在 + 逐条 0 命中 ⇒ 是**比对口径**问题
    （或该条被裁掉），不是"教训根本没送到"。
    """
    return any(LESSON_SECTION_MARK in p for p in prompts if isinstance(p, str))


def prompt_rows_of(journal: Path) -> list[dict]:
    """读 `<journal>-llm.jsonl` 的每行 `{kind, prompt}`（缺文件 ⇒ 空列表，不算读坏）。

    task-217：L1 的**分母只算决策行**。0.7.37 起 brain 把夜间复盘的 review 调用也写进
    同一份留痕（`kind="review"`）；把它算进"LLM 调用数"会稀释命中率（runB-0732 实测
    70 决策 + 2 review ⇒ 旧版报 72 次）。缺 `kind` 的旧留痕按决策行算（兼容）。
    """
    path = sidecar(journal, "-llm.jsonl")
    if not path.exists():
        return []
    out = []
    for row in load_rows(path):
        prompt = row.get("prompt")
        if isinstance(prompt, str):
            out.append({"kind": str(row.get("kind") or ""), "prompt": prompt})
    return out


def split_prompts(rows: list[dict]) -> tuple[list[str], list[str]]:
    """`(决策行提示词, review 行提示词)`。L1 三信号只用前者。"""
    decision = [r["prompt"] for r in rows if r["kind"] != "review"]
    review = [r["prompt"] for r in rows if r["kind"] == "review"]
    return decision, review


def prompts_of(journal: Path) -> list[str]:
    """兼容旧调用：只返回**决策行**提示词（review 复盘行不计入 L1 分母）。"""
    return split_prompts(prompt_rows_of(journal))[0]


def counter_table(title: str, left: dict, right: dict, la: str, lb: str,
                  limit: int = 20) -> None:
    keys = sorted(set(left) | set(right), key=lambda k: (-(left.get(k, 0) + right.get(k, 0)), k))
    print(f"\n{title}")
    print(f"  {'key':<44} {la:>6} {lb:>6}   变化")
    for key in keys[:limit]:
        a, b = left.get(key, 0), right.get(key, 0)
        flag = "→" if b == a else ("↓" if b < a else "↑")
        print(f"  {key:<44} {a:>6} {b:>6}   {flag}")
    if len(keys) > limit:
        print(f"  …另有 {len(keys) - limit} 项（省略）")


# ---------------------------------------------------------------------------
# 演进判据 L0–L5（`docs/_run10-criteria.md`）：把"带教训再玩"的对照做成**机械可算**的部分，
# 不能机械判定的（L3 决策是否真受影响）只给旁证，并在结论里如实标注。
# task-217：L2 的信号表必须跟着**现行账本形态**走。
# 旧表把"卡住带 leftover"映射到 `ended_by:stuck`，但 0.7.37 起该形态落在
# `day_end.stages[].stopped/leftover`（`ended_by` 只是 sleep/sleep_failed）⇒ 旧信号恒 0，
# 叠加旧的 `count_a == 0 ⇒ improved` 假阳性，L2 就永远"✅ 减少"。这里改为多候选、现行形态优先。
_LESSON_SIGNALS: dict[str, list[tuple[str, str]]] = {
    "stuck_with_leftover": [("stage_leftover", ""), ("stage_stopped", "incomplete"), ("ended_by", "stuck")],
    "plot_exhausted": [("event", "plot_exhausted"), ("stage_stopped", "no_target")],
    "slept_without_work": [("ended_by", "slept_without_work")],
    "far_dry_given_up": [("ended_by", "gave_up_dry")],
    "no_inventory_space": [("event", "buy_no_space"), ("event", "inventory_blocked")],
    "stage_incomplete": [("stage_stopped", "incomplete")],
    "dead_crops": [("day_dead_crops", "")],
    # task-217：run A 的教训 id 实际是 `dead_crops_blocking|farm`（不是 `dead_crops`）⇒ 旧表查不到任何信号
    "dead_crops_blocking": [("day_dead_crops", "")],
}

# L4「无新增硬失败类别」只认这些 checks 键；其它 check（如 `zero_action_evidenced`）只作附注
HARD_FAILURE_CHECKS = {
    "no_hard_failures", "no_unmet_stages", "no_blocking_modal",
    "watered_outdoor", "unreachable_within_bound", "refused_within_bound",
}


def lesson_kind(entry: dict) -> str:
    return str(entry.get("id") or "").split("|", 1)[0]


def tail_verified(days: list[dict]) -> int:
    """尾部连续 `verified is True` 的天数（`None`/缺字段一律中断计数）。"""
    count = 0
    for day in reversed(days):
        if day.get("verified") is True:
            count += 1
        else:
            break
    return count


def _signal_count(info: dict, kind: str, name: str = "", scope: str = "") -> int:
    """数一种"同形态"在账本里出现了几次（task-217：支持现行阶段形态与 scope）。"""
    if kind == "ended_by":
        return int((info.get("ended_by") or {}).get(name, 0))
    if kind == "event":
        return int((info.get("event_counts") or {}).get(name, 0))
    if kind == "stage_leftover":
        table = info.get("stage_leftover") or {}
        if scope:
            return int(table.get(scope, 0))
        return sum(int(v) for v in table.values())
    if kind == "stage_stopped":
        if scope:
            return int((info.get("stage_stopped") or {}).get(f"{scope}|{name}", 0))
        return int((info.get("stage_stopped_total") or {}).get(name, 0))
    if kind == "day_dead_crops":
        return int(info.get("dead_crops_days") or 0)
    return 0


def _signal_candidates(entry: dict, info_a: dict) -> list[tuple[str, str, str]]:
    """教训 → 候选信号 `[(kind, name, scope)]`；scope 优先，但只在 run A 真出现过该阶段时生效。

    文档 L20 要求按 `(kind, scope)` 匹配：scope 是阶段名（如 `harvest`）时只数该阶段；
    不是阶段名（如田区名）或 run A 里没有该阶段 ⇒ 退回全阶段聚合，避免"scope 不匹配 ⇒ 恒 0"。
    """
    kind = lesson_kind(entry)
    scope_raw = str(entry.get("scope") or "")
    stages_a = set((info_a.get("stage_leftover") or {}).keys())
    stopped_a = info_a.get("stage_stopped") or {}
    scope_ok = bool(scope_raw) and (
        scope_raw in stages_a or any(k.startswith(scope_raw + "|") for k in stopped_a))
    out: list[tuple[str, str, str]] = []
    for sig_kind, name in _LESSON_SIGNALS.get(kind) or []:
        use_scope = scope_raw if (scope_ok and sig_kind in ("stage_leftover", "stage_stopped")) else ""
        out.append((sig_kind, name, use_scope))
    return out


def _tokens(text: str) -> set[str]:
    """L3 旁证用：田区名 + 两位以上数字（教训文本里最可能被复述的具体指涉）。"""
    return set(re.findall(r"field_[a-z]{2,}", text)) | set(re.findall(r"\d{2,}", text))


def criteria(info_a: dict, info_b: dict, lessons: list[dict], hits: int,
             prompts_b: list[str], la: str = "runA", lb: str = "runB",
             section_present: bool | None = None, window: int = 3,
             review_calls: int = 0) -> dict:
    """L0–L5 的机械判定（task-217 修订）。

    修订要点：
      * L0 补「至少 1 条 `count >= 1`」（文档 §1 一直这么要求，代码旧版漏了）；
      * L2 改**严格三态**（减少 / 未变 / 增加；两边都没有 ⇒ 无可比），并按现行形态取信号 + scope；
      * L4 只看尾部 `window` 天（= 验收窗口），新增失败只认 `HARD_FAILURE_CHECKS`；
      * L5 门禁补齐 L0–L3 + 尾部达标（旧版只串行门 L0/L1/L2 且 `tail_b < 3` 硬编码）。
    """
    tail_a = tail_verified((info_a.get("days") or [])[-window:])
    tail_b = tail_verified((info_b.get("days") or [])[-window:])
    signals: list[dict] = []
    for entry in lessons:
        kind = lesson_kind(entry)
        cands = _signal_candidates(entry, info_a)
        if not cands:
            signals.append({"kind": kind, "lesson": lesson_full_text(entry)[:96], "signal": None,
                            "a": None, "b": None, "status": "无可数信号（需人工看账本）",
                            "improved": None, "comparable": False})
            continue
        chosen: tuple[str, str, str, int, int] | None = None
        for sig_kind, name, scope in cands:  # 优先选 run A 真出现过的形态
            a = _signal_count(info_a, sig_kind, name, scope)
            if a > 0:
                chosen = (sig_kind, name, scope, a, _signal_count(info_b, sig_kind, name, scope))
                break
        if chosen is None:  # 两边都没有该形态（或 run A 无基线）
            sig_kind, name, scope = cands[0]
            chosen = (sig_kind, name, scope, 0, _signal_count(info_b, sig_kind, name, scope))
        sig_kind, name, scope, count_a, count_b = chosen
        if count_a == 0 and count_b == 0:
            status, improved, comparable = "两边都没有（无可比）", None, False
        elif count_a == 0:
            status, improved, comparable = f"run A 无基线、run B={count_b}（更差）", False, False
        elif count_b < count_a:
            status, improved, comparable = "减少", True, True
        elif count_b == count_a:
            status, improved, comparable = "未变", False, True
        else:
            status, improved, comparable = "增加", False, True
        label = f"{sig_kind}:{name}" + (f"@{scope}" if scope else "")
        signals.append({
            "kind": kind, "lesson": lesson_full_text(entry)[:96],
            "signal": label, "a": count_a, "b": count_b,
            "status": status, "improved": improved, "comparable": comparable,
        })
    mapped = [s for s in signals if s["signal"]]
    comparable = [s for s in mapped if s.get("comparable")]
    new_false = sorted(set(info_b.get("checks_false") or []) - set(info_a.get("checks_false") or []))
    new_hard_false = [k for k in new_false if k in HARD_FAILURE_CHECKS]
    other_new_false = [k for k in new_false if k not in HARD_FAILURE_CHECKS]
    counts = [int(e.get("count") or 0) for e in lessons if isinstance(e.get("count"), int)]
    l0_count_ok = any(c >= 1 for c in counts) if counts else None
    l0 = len(lessons) >= 1 and l0_count_ok is True
    if section_present is None:
        section_present = lesson_section_present(prompts_b)
    l1 = bool(lessons) and bool(prompts_b) and hits > 0
    if not mapped or not comparable:
        l2: bool | None = None  # 无法判定：没有任何 run A 里真出现过的可比形态
    else:
        l2 = all(bool(s["improved"]) for s in comparable)
    l4 = (tail_b >= tail_a) and not new_hard_false
    # L3 只给旁证：教训里的具体指涉有没有出现在 run B 的决策理由/预期证据里
    influence: list[dict] = []
    for entry in lessons:
        toks = _tokens(lesson_full_text(entry))
        mentioned = 0
        if toks:
            for text in info_b.get("decision_texts") or []:
                if toks & _tokens(text):
                    mentioned += 1
        influence.append({"lesson": lesson_full_text(entry)[:96], "decision_mentions": mentioned,
                          "note": "旁证：只在「理由/预期证据里出现同一指涉」意义上成立，不等于决策被改变"})
    l3_evidence = any(int(item["decision_mentions"]) > 0 for item in influence)
    if not l0:
        why = ("run A 没产出教训" if not lessons
               else "教训库没有任何 count>=1 的条目" if l0_count_ok is False
               else "教训库缺 count 字段，无法证明有可注入教训")
        verdict = f"不足以判定自我进化（L0：{why} ⇒ A→B 对照作废）"
    elif not l1:
        verdict = "不足以判定自我进化（L1：教训没有进 run B 的决策提示词）"
    elif l2 is None:
        verdict = "不足以判定自我进化（L2：教训对应的形态在 run A 里没出现过，无可比基线）"
    elif not l2:
        verdict = "不足以判定自我进化（L2：同形态在 run B 没有减少）"
    elif not l4:
        verdict = ("不足以判定自我进化（L4：run B 尾部窗口 VERIFIED 未达标"
                   + (f"，新增硬失败类别 {new_hard_false}" if new_hard_false else "") + "）")
    elif not l3_evidence:
        verdict = "不足以判定自我进化（L3：没有任何决策受影响的旁证）"
        if tail_b < window:
            verdict += f"；且 run B 尾部连续 VERIFIED {tail_b} < {window} 天"
    elif tail_b < window:
        verdict = f"有演进痕迹，但 run B 未达标（尾部连续 VERIFIED {tail_b} < {window} 天）"
    else:
        verdict = "有演进证据（L0/L1/L2/L4 机械成立且 L3 有旁证；正式结论仍需人工核对）"
    return {
        "l0_lessons_exist": l0,
        "l0_count_ok": l0_count_ok,
        "l1_injection_effective": l1,
        "l2_same_shape_decreased": l2,
        "l2_comparable_signals": len(comparable),
        "l3_influence_evidence": influence,
        "l3_evidence_present": l3_evidence,
        "l4_no_regression": l4,
        "l5_verdict": verdict,
        "tail_verified": {la: tail_a, lb: tail_b},
        "tail_window_days": window,
        "signals": signals,
        "new_false_checks_in_b": new_false,
        "new_hard_false_checks_in_b": new_hard_false,
        "other_new_false_checks_in_b": other_new_false,
        "lesson_hits": hits,
        "lessons_total": len(lessons),
        "lesson_section_present": bool(section_present),
        "b_prompt_calls": len(prompts_b),
        "b_review_calls": review_calls,
    }


def print_criteria(crit: dict, la: str, lb: str) -> None:
    print("\n[6] 演进判据（L0–L5，机械可算部分 + 旁证）")
    def mark(ok: object) -> str:
        if ok is None:
            return "❓"
        return "✅" if ok else "❌"

    count_note = ("count 字段缺失（无法证明有 count>=1）" if crit["l0_count_ok"] is None
                  else f"至少 1 条 count>=1：{crit['l0_count_ok']}")
    print(f"  L0 run A 有教训库（≥1 条且 ≥1 条 count>=1）: {mark(crit['l0_lessons_exist'])}"
          f"  ({crit['lessons_total']} 条；{count_note})")
    print(f"  L1 教训确实进了 run B 决策提示词      : {mark(crit['l1_injection_effective'])}"
          f"  ({crit['lesson_hits']}/{crit['lessons_total']} 命中，run B {crit['b_prompt_calls']} 次决策调用"
          f"；另有 {crit['b_review_calls']} 次 review 复盘调用不计入分母)")
    print(f"  L2 同形态在 run B 减少                : {mark(crit['l2_same_shape_decreased'])}"
          f"  （可比信号 {crit['l2_comparable_signals']} 条）")
    status_flag = {
        "减少": "✅ 减少", "未变": "❌ 未减少", "增加": "⚠ 增加",
        "两边都没有（无可比）": "➖ 无可比（两边都没有）",
    }
    for sig in crit["signals"]:
        if sig["signal"]:
            flag = status_flag.get(sig["status"], f"❌ {sig['status']}")
            print(f"       · {sig['kind']:<20} {sig['signal']:<34} {la}={sig['a']} → {lb}={sig['b']}"
                  f"  {flag}")
        else:
            print(f"       · {sig['kind']:<20} （无可数信号，需人工看账本）")
    tails = crit["tail_verified"]
    print(f"  L4 无回归（尾部 {crit['tail_window_days']} 天 VERIFIED 不降 + 无新硬失败类）: "
          f"{mark(crit['l4_no_regression'])}"
          f"  尾部 {la}={tails.get(la)} → {lb}={tails.get(lb)}"
          + (f"；新增硬失败项 {crit['new_hard_false_checks_in_b']}"
             if crit["new_hard_false_checks_in_b"] else ""))
    if crit["other_new_false_checks_in_b"]:
        print(f"       附注（不判 L4）：新增的非硬失败 check 项 "
              f"{crit['other_new_false_checks_in_b']}（如 `zero_action_evidenced`，只作线索）")
    print("  L3 决策受影响的旁证（需人工确认）    :")
    for item in crit["l3_influence_evidence"]:
        print(f"       · 决策理由里同指涉出现 {item['decision_mentions']} 次 ｜ {item['lesson'][:72]}")
    print(f"  L5 结论：{crit['l5_verdict']}")
    print("  ⚠ 本工具的 L 判据只做机械对照；「自我进化」的正式结论必须并列"
          " `verify-run3`/`analyze-longrun` 的判决与 L3 的人工核对。")


def main(argv: list[str] | None = None) -> int:
    try:  # 与 verify-run3.py 同款：Windows 控制台 cp1252 下中文会 UnicodeEncodeError
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:  # noqa: BLE001
        pass
    ap = argparse.ArgumentParser(description="run A vs run B：教训库 / 提示词注入 / 意图形态 对照")
    ap.add_argument("--run-a", required=True, help="run A 账本（积累教训的那次）")
    ap.add_argument("--run-b", required=True, help="run B 账本（带着教训再玩的那次）")
    ap.add_argument("--label-a", default="runA")
    ap.add_argument("--label-b", default="runB")
    ap.add_argument("--days", type=int, default=3,
                    help="验收窗口天数（L4 尾部窗口 / L5 尾部达标都按它算；默认 3）")
    ap.add_argument("--json", dest="json_out", default="", help="把结构化对照结果写到这个文件")
    args = ap.parse_args(argv)

    ja, jb = Path(args.run_a), Path(args.run_b)
    for path in (ja, jb):
        if not path.exists():
            print(f"[exit 2] 账本不存在：{path}")
            return 2

    try:
        rows_a, rows_b = load_rows(ja), load_rows(jb)
        lessons, lessons_path = lessons_of(ja)
        prompt_rows_a = prompt_rows_of(ja)
        prompt_rows_b = prompt_rows_of(jb)
    except LedgerReadError as exc:  # task-217：读不到/读坏统一 rc=2
        print(f"[exit 2] {exc}")
        return 2

    info_a, info_b = harvest(rows_a), harvest(rows_b)
    prompts_a, review_a = split_prompts(prompt_rows_a)
    prompts_b, review_b = split_prompts(prompt_rows_b)
    info_a["trace_rows"] = len(prompt_rows_a)
    info_b["trace_rows"] = len(prompt_rows_b)
    joined_b = "\n".join(prompts_b)
    joined_b_norm = norm(joined_b)

    print("=" * 78)
    print(f"run A = {args.label_a}  {ja}")
    print(f"run B = {args.label_b}  {jb}")
    print("=" * 78)
    for label, info in ((args.label_a, info_a), (args.label_b, info_b)):
        fin = info["finish"] or {}
        print(f"\n[{label}] 行 {info['rows']} ｜ 日 {info['day_end']} ｜ decision {info['decisions']}"
              f"（LLM {info['decisions_llm']}）｜ llm-trace 行 {info['trace_rows']}")
        print(f"        finish = code {fin.get('code')} / streak {fin.get('verified_streak')}"
              f" / actions {fin.get('actions')} / {fin.get('minutes')} min"
              f" / stuck_flush {fin.get('stuck_flushes')} / no_unmet_stages {fin.get('no_unmet_stages')}"
              f" / 目标 {info['day_end']} 天")
        for day in info["days"]:
            print(f"        · {day['day']}  ended_by={day['ended_by']}  verified={day['verified']}"
                  f"  ok={day['ok_steps']} failed={day['failed_steps']}")

    counter_table("[1] 决策意图形态（每个 decision 的 task 集合）",
                  info_a["shapes"], info_b["shapes"], args.label_a, args.label_b)
    counter_table("[2] 被校验取消的意图（intent_verdict=cancel，按任务）",
                  info_a["cancel_by_task"], info_b["cancel_by_task"], args.label_a, args.label_b)
    counter_table("[3] 阶段失败/异常收尾（按 stage）",
                  info_a["stage_fail_by_task"], info_b["stage_fail_by_task"],
                  args.label_a, args.label_b)
    counter_table("[4] 阶段成功格数（按 stage）",
                  info_a["stage_ok_by_task"], info_b["stage_ok_by_task"],
                  args.label_a, args.label_b)

    print("\n[5] run A 教训库 → run B 提示词命中")
    hits = 0
    section_present = lesson_section_present(prompts_b)
    if not lessons:
        print(f"  ⚠ 读不到 run A 的教训库（期望 {sidecar(ja, '-lessons.json')} 或 `-lessons.jsonl`）"
              " ⇒ 无法证明「带教训再玩」，按未观察到演进处理")
    else:
        print(f"  教训库 {lessons_path}：{len(lessons)} 条")
        for idx, entry in enumerate(lessons, 1):
            text = lesson_text(entry)
            key = norm(text)
            hit = bool(key) and key in joined_b_norm
            hits += 1 if hit else 0
            mark = "✅ 进提示词" if hit else "❌ 未见"
            print(f"  {idx:>2}. [{mark}] {text[:96]}")
        print(f"  ⇒ {hits}/{len(lessons)} 条教训文本出现在 run B 的 {len(prompts_b)} 次**决策**调用提示词里"
              f"（另 {len(review_b)} 次 review 复盘调用不计入 L1 分母）"
              "（子串比对；注入后被裁掉的部分算未见）")
        print(f"  教训节抬头「{LESSON_SECTION_MARK}」在 run B 提示词里："
              f"{'✅ 出现' if section_present else '❌ 未见'}")
        if prompts_b and hits == 0:
            if section_present:
                print("  ⚠ 比对口径警告：**教训节确实在提示词里**，但逐条文本一条都没匹配上")
                print("     ⇒ 优先怀疑本工具的取文本口径（字段名/裁切/改写），不要断言「教训没送到」；")
                print("        请把 `lessons_total/lessons_hits/section_present` 三个值一起看。")
            else:
                print("  ❌ 注入口径警告：run A 有教训、run B 也有 LLM 调用，提示词里既没有教训节、"
                      "也没有任何一条教训文本")
                print("     —— 这不是「未观察到演进」，而是「教训根本没送到」；先查文件发现路径/裁切顺序。")
    if not prompts_b:
        print(f"  ⚠ 读不到 run B 的 LLM 留痕（期望 {sidecar(jb, '-llm.jsonl')}）"
              " ⇒ 无法核对注入；若 run B 未开 --boundary-llm，此处属预期")
    # L1 = 教训文本确实进了 run B 提示词（逐条子串命中）。
    # 教训节抬头只作**交叉核对**：节在 + 逐条 0 命中 ⇒ 报"比对口径"，不断言"没送到"
    # （2026-10-17 事故：本工具取文本的字段名与 brain 的 `hint/symptom` 不一致 ⇒ 误报 0/6）。
    injection_effective = bool(lessons) and bool(prompts_b) and hits > 0

    crit = criteria(info_a, info_b, lessons, hits, prompts_b, args.label_a, args.label_b,
                    section_present, window=args.days, review_calls=len(review_b))
    print_criteria(crit, args.label_a, args.label_b)

    verdict = {
        "run_a": {"journal": str(ja), "info": info_a},
        "run_b": {"journal": str(jb), "info": info_b},
        "lessons": [{"text": lesson_text(e), "in_b_prompt": bool(norm(lesson_text(e)))
                     and norm(lesson_text(e)) in joined_b_norm} for e in lessons],
        "lessons_total": len(lessons),
        "lessons_hits": hits,
        "lesson_section_present": section_present,
        "injection_effective": injection_effective,
        "b_prompt_calls": len(prompts_b),
        "b_decision_calls": len(prompts_b),
        "b_review_calls": len(review_b),
        "b_trace_rows": len(prompt_rows_b),
        "a_decision_calls": len(prompts_a),
        "a_review_calls": len(review_a),
        "window_days": args.days,
        "criteria": crit,
    }
    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(verdict, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"\n结构化结果已写：{out}")

    print("\n注：本工具只做对照取证，不改判据。正式判决请跑：")
    print(f"  python tools/verify-run3.py --journal {ja} --days 3")
    print(f"  python tools/verify-run3.py --journal {jb} --days 3")
    print(f"  python tools/analyze-longrun.py --journal {ja} --days 3")
    print(f"  python tools/analyze-longrun.py --journal {jb} --days 3")
    print("\n注：本工具读不到/读坏账本或 sidecar ⇒ rc=2；其余恒 rc=0"
          "（L 级结论只进文本与 --json，不参与验收 rc）。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
