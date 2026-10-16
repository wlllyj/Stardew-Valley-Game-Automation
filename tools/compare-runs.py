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
本工具恒退出 0；文件读不到时退出 2 并说明缺哪个文件（缺文件 ≠ 通过）。

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


def load_rows(path: Path) -> list[dict]:
    rows: list[dict] = []
    with path.open("r", encoding="utf-8") as fh:
        for lineno, line in enumerate(fh, 1):
            line = line.strip()
            if not line:
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise SystemExit(f"[exit 2] {path}:{lineno} 不是合法 JSON：{exc}")
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
    }
    for row in rows:
        ev = row.get("ev") or row.get("event") or ""
        if ev == "day_start":
            info["day_start"] += 1
        elif ev == "day_end":
            info["day_end"] += 1
            info["days"].append({
                "day": row.get("day_key") or row.get("day"),
                "ended_by": row.get("ended_by"),
                "verified": row.get("verified"),
                "ok_steps": row.get("ok_steps"),
                "failed_steps": row.get("failed_steps"),
            })
            # 阶段结果在 day_end.stages[]（不是独立的 stage 事件；tiles 是整数不是坐标列表）
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
            raw = json.loads(path.read_text(encoding="utf-8"))
            entries = raw.get("lessons") if isinstance(raw, dict) else raw
            if not isinstance(entries, list):
                entries = []
        return [e for e in entries if isinstance(e, dict)], str(path)
    return [], ""


def lesson_text(entry: dict) -> str:
    for key in ("lesson", "text", "summary", "note", "why", "reason"):
        val = entry.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    parts = [str(v) for v in entry.values() if isinstance(v, (str, int, float))]
    return " / ".join(parts).strip()


def prompts_of(journal: Path) -> list[str]:
    path = sidecar(journal, "-llm.jsonl")
    if not path.exists():
        return []
    out = []
    for row in load_rows(path):
        prompt = row.get("prompt")
        if isinstance(prompt, str):
            out.append(prompt)
    return out


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
    ap.add_argument("--json", dest="json_out", default="", help="把结构化对照结果写到这个文件")
    args = ap.parse_args(argv)

    ja, jb = Path(args.run_a), Path(args.run_b)
    for path in (ja, jb):
        if not path.exists():
            print(f"[exit 2] 账本不存在：{path}")
            return 2

    rows_a, rows_b = load_rows(ja), load_rows(jb)
    info_a, info_b = harvest(rows_a), harvest(rows_b)

    lessons, lessons_path = lessons_of(ja)
    prompts_b = prompts_of(jb)
    info_a["trace_rows"] = len(prompts_of(ja))
    info_b["trace_rows"] = len(prompts_b)
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
        print(f"  ⇒ {hits}/{len(lessons)} 条教训文本出现在 run B 的 {len(prompts_b)} 次 LLM 调用提示词里"
              "（子串比对；注入后被裁掉的部分算未见）")
        if prompts_b and hits == 0:
            print("  ❌ 注入口径警告：run A 有教训、run B 也有 LLM 调用，却一条教训都没进提示词")
            print("     —— 这不是「未观察到演进」，而是「教训根本没送到」；先查文件发现路径/裁切顺序。")
    if not prompts_b:
        print(f"  ⚠ 读不到 run B 的 LLM 留痕（期望 {sidecar(jb, '-llm.jsonl')}）"
              " ⇒ 无法核对注入；若 run B 未开 --boundary-llm，此处属预期")
    injection_effective = bool(lessons) and bool(prompts_b) and hits > 0

    verdict = {
        "run_a": {"journal": str(ja), "info": info_a},
        "run_b": {"journal": str(jb), "info": info_b},
        "lessons": [{"text": lesson_text(e), "in_b_prompt": bool(norm(lesson_text(e)))
                     and norm(lesson_text(e)) in joined_b_norm} for e in lessons],
        "lessons_total": len(lessons),
        "lessons_hits": hits,
        "injection_effective": injection_effective,
        "b_prompt_calls": len(prompts_b),
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
    return 0


if __name__ == "__main__":
    sys.exit(main())
