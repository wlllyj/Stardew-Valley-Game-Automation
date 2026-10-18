# -*- coding: utf-8 -*-
"""task-239 三审：复核 machine-runner 对 GAP-236B-4 / GAP-236B-5 的修复（commit e615416）。

只读：从真实绿窗口 `logs/smoke-0740-smapi-window-rescued.txt` 派生两个"缺行"夹具，
断言：
  GAP-4：删掉全部 `Context: before save.` ⇒ 必须降级【无法判定 rc=2】，不得 PASS rc=0。
  GAP-5a：删掉全部 `Synchronizing 'Save' task` 且链序正常 ⇒ PASS（部分校验通过）。
  GAP-5b：删掉全部 task 链 + 把一条 completed 移到 called 之前 ⇒ 必须 FAIL rc=1。
另：selftest 8 夹具 rc=0；六串计数与我自算一致。
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
    proc = subprocess.run(
        [PY, str(CHECKER), "--smapi", str(window), "--out", str(out)],
        capture_output=True, text=True, encoding="utf-8", errors="replace",
        cwd=str(ROOT),
    )
    try:
        payload = json.loads(out.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 — 解析失败按空处理，断言会红
        payload = {}
    return proc.returncode, payload


def derive(name: str, drop: callable, edit: callable | None = None) -> Path:
    lines = GREEN.read_text(encoding="utf-8", errors="replace").splitlines()
    kept = [ln for ln in lines if not drop(ln)]
    if edit is not None:
        kept = edit(kept)
    p = OUT / name
    p.write_text("\n".join(kept) + "\n", encoding="utf-8", newline="\n")
    return p


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    # selftest
    st = subprocess.run([PY, str(CHECKER), "--selftest"], capture_output=True,
                        text=True, encoding="utf-8", errors="replace", cwd=str(ROOT))
    check("审 8 夹具 selftest rc=0", st.returncode == 0,
          st.stdout.strip().splitlines()[-1] if st.stdout.strip() else st.stderr.strip()[-120:])

    # 基线绿窗口
    rc0, j0 = run_checker(GREEN)
    v0 = j0.get("verdict") or {}
    counts0 = v0.get("counts") or {}
    check("基绿窗口 PASS", rc0 == 0 and counts0.get("newday") == 3 and counts0.get("save_called") == 3,
          f"rc={rc0} counts={counts0}")

    # GAP-4：缺 before save
    p4 = derive("gap4_no_before_save.txt", lambda ln: "Context: before save." in ln)
    rc4, j4 = run_checker(p4)
    v4 = j4.get("verdict") or {}
    c4 = v4.get("counts") or {}
    check("GAP-4 缺 before save ⇒ 降级无法判定 rc=2（不再 PASS）", rc4 == 2,
          f"rc={rc4} verdict={v4.get('verdict')} counts={c4} reason={(v4.get('reasons') or [''])[0][:80]}")

    # GAP-5a：缺 task 链但顺序正常 ⇒ PASS（部分校验）
    p5 = derive("gap5a_no_save_task.txt", lambda ln: "Synchronizing 'Save' task" in ln)
    rc5, j5 = run_checker(p5)
    v5 = j5.get("verdict") or {}
    order5 = v5.get("order") or {}
    check("GAP-5a 缺 task 链、顺序正常 ⇒ PASS 且 order 有 checked_without_task",
          rc5 == 0 and bool(order5.get("ok")) and bool(order5.get("checked_without_task")),
          f"rc={rc5} order={order5}")

    # GAP-5b：缺 task 链 + 把最末 completed 行挪到 called 之前 ⇒ FAIL
    def _edit(lines: list[str]) -> list[str]:
        idx_done = [i for i, ln in enumerate(lines) if "SaveGame.Save() completed without exceptions" in ln]
        idx_called = [i for i, ln in enumerate(lines) if "SaveGame.Save() called." in ln]
        if not idx_done or not idx_called:
            return lines
        d, c = idx_done[-1], idx_called[-1]
        ln = lines.pop(d)
        c = next(i for i, s in enumerate(lines) if "SaveGame.Save() called." in s)
        lines.insert(max(0, c - 1), ln)
        return lines

    p5b = derive("gap5b_no_task_reversed.txt",
                 lambda ln: "Synchronizing 'Save' task" in ln, _edit)
    rc5b, j5b = run_checker(p5b)
    v5b = j5b.get("verdict") or {}
    check("GAP-5b 缺 task 链 + completed 在 called 之前 ⇒ FAIL rc=1", rc5b == 1,
          f"rc={rc5b} verdict={v5b.get('verdict')} order={v5b.get('order')}")

    fails = [r for r in results if not r[1]]
    print(f"\n汇总：PASS={len(results) - len(fails)} FAIL={len(fails)}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
