# -*- coding: utf-8 -*-
"""task-239 三审补测（终审要点 ②③⑤）。

① 0.7.40 型窗口（NewDay 3 / Save called 2，末次 NewDay 晚于末次 Save）
   必须判 **FAIL rc=1**，不能被完整性闸门退化成【无法判定 rc=2】。
② save_task 三态：=0（五串齐 ⇒ PASS + checked_without_task）、部分
   （0<n<NewDay ⇒ 无法判定 rc=2）、完整（⇒ use_task_chain=True）。
③ `scratch/smoke-0741.py` 步 6 消费端在新 JSON 结构下读 verdict/counts/reasons。
④ 手工复算夹具 F（插件行 L16）：save_called 原始 4 / 修正 3 / 排除 1。
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CHECKER = ROOT / "scratch" / "save-chain-check.py"
GREEN = ROOT / "logs" / "smoke-0740-smapi-window-rescued.txt"
OUT = ROOT / "scratch" / "_t239_win"
PY = sys.executable
results: list[tuple[str, bool, str]] = []


def check(tag: str, ok: bool, detail: str = "") -> None:
    results.append((tag, ok, detail))
    print(("  PASS  " if ok else "  FAIL  ") + tag + (f" :: {detail}" if detail else ""))


def run_checker(window: Path) -> tuple[int, dict]:
    out = OUT / (window.stem + ".json")
    proc = subprocess.run([PY, str(CHECKER), "--smapi", str(window), "--out", str(out)],
                          capture_output=True, text=True, encoding="utf-8",
                          errors="replace", cwd=str(ROOT))
    try:
        return proc.returncode, json.loads(out.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return proc.returncode, {}


def derive(name: str, drop=None, edit=None) -> Path:
    lines = GREEN.read_text(encoding="utf-8", errors="replace").splitlines()
    kept = [ln for ln in lines if not (drop and drop(ln))]
    if edit:
        kept = edit(kept)
    p = OUT / name
    p.write_text("\n".join(kept) + "\n", encoding="utf-8", newline="\n")
    return p


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    src = GREEN.read_text(encoding="utf-8", errors="replace").splitlines()
    ts = re.compile(r"^\[(\d{2}:\d{2}:\d{2})\s+[A-Z]+\s+[^\]]+\]")

    # ① 0.7.40 型红窗口：只保留到第三次 NewDay（截掉抢救补齐的 before/called/task/completed/after）
    idx_new = [i for i, ln in enumerate(src) if "Synchronizing 'NewDay' task" in ln]
    cut = idx_new[-1] + 2 if idx_new else len(src)
    red = OUT / "red_0740_third_newday_only.txt"
    red.write_text("\n".join(src[:cut]) + "\n", encoding="utf-8", newline="\n")
    rc_red, j_red = run_checker(red)
    v_red = j_red.get("verdict") or {}
    counts_red = v_red.get("counts") or {}
    check("① 0.7.40 型窗口 ⇒ FAIL rc=1（未被完整性闸门吃掉）",
          rc_red == 1 and v_red.get("verdict") == "FAIL",
          f"rc={rc_red} verdict={v_red.get('verdict')} counts={counts_red} reasons={str(v_red.get('reasons'))[:120]}")

    # ②a save_task 全 0 ⇒ PASS + checked_without_task
    p0 = derive("st_zero_no_task.txt", drop=lambda ln: "Synchronizing 'Save' task" in ln)
    rc0, j0 = run_checker(p0)
    v0 = j0.get("verdict") or {}
    o0 = v0.get("order") or {}
    check("②a save_task=0（五串齐）⇒ PASS + checked_without_task",
          rc0 == 0 and (v0.get("verdict") == "PASS") and o0.get("checked_without_task") is True,
          f"rc={rc0} verdict={v0.get('verdict')} order={o0}")

    # ②b save_task 部分（删 1 条，剩 2 < 3）⇒ 无法判定 rc=2
    def _drop_one_task(lines: list[str]) -> list[str]:
        out, dropped = [], False
        for ln in lines:
            if (not dropped) and "Synchronizing 'Save' task" in ln:
                dropped = True
                continue
            out.append(ln)
        return out

    p_part = derive("st_partial_task.txt", edit=_drop_one_task)
    rc_p, j_p = run_checker(p_part)
    v_p = j_p.get("verdict") or {}
    c_p = v_p.get("counts") or {}
    check("②b save_task 部分（2 < NewDay 3）⇒ 无法判定 rc=2",
          rc_p == 2 and c_p.get("save_task") == 2,
          f"rc={rc_p} verdict={v_p.get('verdict')} counts={c_p} reasons={str(v_p.get('reasons'))[:120]}")

    # ②c save_task 完整（基线）⇒ use_task_chain=True 且 order 覆盖 task
    rc_full, j_full = run_checker(GREEN)
    v_full = j_full.get("verdict") or {}
    o_full = v_full.get("order") or {}
    check("②c save_task 完整 ⇒ use_task_chain=True / checked_without_task=False",
          rc_full == 0 and o_full.get("use_task_chain") is True
          and o_full.get("checked_without_task") is False,
          f"order={o_full}")

    # ④ 手工复算夹具 F：插件行 L16（rescued 窗口本身已有 1 条真 L16 行 ⇒ raw save_called=4）
    #    再插入 1 条假插件行 ⇒ raw=5 / 排除=2 / 修正后仍是 3
    txt = OUT / "red_plugin_line2.txt"
    lines = src[:]
    insert_at = next(i for i, ln in enumerate(lines) if "SaveGame.Save() called." in ln)
    lines.insert(insert_at, "[23:46:36 INFO  SMAPI] AgentFarm Bridge by AgentFarm | v0.7.40"
                            "（更新说明：SaveGame.Save() called.）")
    txt.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    rc_f, j_f = run_checker(txt)
    v_f = j_f.get("verdict") or {}
    c_f = v_f.get("counts") or {}
    raw_f = v_f.get("raw_counts") or {}
    exc_f = v_f.get("excluded_by_chain") or {}
    check("④ 夹具 F 手工复算：再插 1 条假 L16 ⇒ 原始 save_called 4→5 / 排除 1→2 / 修正仍 3",
          raw_f.get("save_called") == 5 and c_f.get("save_called") == 3
          and exc_f.get("save_called") == 2,
          f"raw={raw_f.get('save_called')} corrected={c_f.get('save_called')} excluded={exc_f.get('save_called')}")

    # ③ 消费端：smoke-0741.py 步 6 调检查器 + 只认 verdict/counts/reasons；自己不再数六串
    smoke = ROOT / "scratch" / "smoke-0741.py"
    s = smoke.read_text(encoding="utf-8", errors="replace") if smoke.exists() else ""
    step6 = s[s.find("def step6("):s.find("def _journal_records")]
    calls_checker = "save-chain-check.py" in step6 and '"--out"' in step6
    reads_json = 'payload.get("verdict")' in step6 and '"counts"' in step6 and 'verdict_doc.get("reasons")' in step6
    triad = all(k in step6 for k in ('rec["verdict"] = "PASS"', 'rec["verdict"] = "FAIL"', 'rec["verdict"] = "无法判定"'))
    # count_six 定义了但全文件无调用（dead code ⇒ NIT，不参与判决）
    dead_count_six = s.count("count_six(") <= 1
    check("③ smoke-0741.py 步 6 调检查器并只认 verdict/counts/reasons（自身不数六串）",
          calls_checker and reads_json and triad,
          f"calls={calls_checker} reads_json={reads_json} triad={triad} count_six_dead={dead_count_six}")

    fails = [r for r in results if not r[1]]
    print(f"\n汇总：PASS={len(results) - len(fails)} FAIL={len(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
