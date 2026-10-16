"""task-172 回归矩阵：旧版（HEAD）vs 新版 analyze-longrun.py 在既有账本上的判决与计数。

只读；产物打到 stdout。用法：
  python scratch\\_t172_matrix.py
"""
import json
import os
import subprocess
import sys

sys.stdout.reconfigure(encoding="utf-8", errors="replace")
PY = sys.executable
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGERS = [
    "longrun-runA-0732",
    "longrun-runB-0732",
    "longrun-3day-llm-run9d",
    "longrun-3day-llm-run9c",
    "longrun-3day-llm-run9b",
    "longrun-3day-llm-run9",
]


def run(tool_path, ledger, args):
    return subprocess.run([PY, tool_path, "--journal", ledger, *args],
                          capture_output=True, text=True, encoding="utf-8", cwd=ROOT)


def summary(stdout):
    try:
        payload = json.loads(stdout)
    except Exception:
        return None
    red = (payload.get("red") or {}).get("total")
    return {
        "red": red,
        "unmapped": sorted((payload.get("unmapped_events") or {}).keys()),
        "gave_up": (payload.get("harvest_gave_up") or {}).get("events"),
        "ready_fields": bool((payload.get("crop_ready") or {}).get("has_fields")),
        "window_ready_true": (payload.get("crop_ready") or {}).get("window_ready_true"),
    }


def main() -> int:
    old_tool = os.path.join(ROOT, "scratch", "_t172_old_analyze.py")
    if not os.path.exists(old_tool):
        raise SystemExit("先准备 HEAD 版：git show HEAD:tools/analyze-longrun.py > scratch/_t172_old_analyze.py")
    print(f"{'ledger':32s} {'old rc/red':>10s} {'new rc/red':>10s}  new-extra")
    for name in LEDGERS:
        ledger = os.path.join(ROOT, "logs", name + ".jsonl")
        if not os.path.exists(ledger):
            print(f"{name:32s} (缺文件)")
            continue
        old = run(old_tool, ledger, ["--days", "7", "--json"])
        new = run(os.path.join(ROOT, "tools", "analyze-longrun.py"),
                  ledger, ["--days", "7", "--json"])
        os_, ns = summary(old.stdout), summary(new.stdout)
        old_txt = f"{old.returncode}/{os_['red'] if os_ else '?'}"
        new_txt = f"{new.returncode}/{ns['red'] if ns else '?'}"
        extra = ""
        if os_ and ns:
            extra = (f"unmapped {os_['unmapped']}->{ns['unmapped']}  "
                     f"gave_up={ns['gave_up']} ready_fields={ns['ready_fields']} "
                     f"window_ready_true={ns['window_ready_true']}")
        print(f"{name:32s} {old_txt:>10s} {new_txt:>10s}  {extra}")
        v = subprocess.run([PY, "tools/verify-run3.py", "--journal", ledger, "--days", "7"],
                           capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
        if v.returncode == 2:
            v = subprocess.run([PY, "tools/verify-run3.py", ledger, "--days", "7"],
                               capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
        last = [ln for ln in (v.stdout or "").splitlines() if ln.strip()][-1:]
        print(f"{'':32s} verify rc={v.returncode} {last[0].strip()[:120] if last else ''}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
