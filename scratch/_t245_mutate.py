"""task-245 变异自检：确认本卡的用例真的钉住了"有界等待 + eventId 归因"这条判据。

用法（仓库根目录）：
    $env:PYTHONUTF8=1
    $env:PYTHONPATH="<repo>\\brain"
    python scratch\\_t245_mutate.py

做法：把 `brain/agentfarm/longrun.py` 依次换成变异体、跑
`tests.test_longrun.TestTask245EventWait`、统计红了几条，然后**无论如何**都从备份还原。
基线（无变异）必须全绿；任何变异杀 0 条都说明用例没钉住判据（本卡不允许）。
"""
from __future__ import annotations

import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

REPO = pathlib.Path(__file__).resolve().parent.parent
TARGET = REPO / "brain" / "agentfarm" / "longrun.py"
BACKUP = pathlib.Path(tempfile.gettempdir()) / "_t245_longrun_backup.py"
TEST = "tests.test_longrun.TestTask245EventWait"

#: (名字, 旧片段, 新片段) —— 每个变异只改一处，且都必须是**行为**变异（不是文本断言）。
MUTATIONS = [
    (
        "m245a_去掉等待立刻收尾",
        "                obs, still_blocked, wait_tries = self._wait_event_up(obs)\n"
        "                if not still_blocked:\n"
        "                    rounds += 1\n"
        "                    continue\n"
        "                self._event_blocked(obs, rep, event_wait_tries=wait_tries)\n"
        "                return obs, True\n",
        "                self._event_blocked(obs, rep)\n"
        "                return obs, True\n",
    ),
    (
        "m245b_journal丢掉eventId",
        '            self._journal("event_wait", tries=tries, limit=EVENT_WAIT_TRIES,\n'
        '                          eventId=ui.get("eventId"), eventUp=bool(event_up),\n',
        '            self._journal("event_wait", tries=tries, limit=EVENT_WAIT_TRIES,\n'
        '                          eventUp=bool(event_up),\n',
    ),
    (
        "m245c_等满也当没挂住",
        "        return obs, True, tries\n",
        "        return obs, False, tries\n",
    ),
]


def _run_tests() -> tuple[bool, int, int]:
    proc = subprocess.run(
        [sys.executable, "-m", "unittest", TEST, "-v"],
        cwd=str(REPO), capture_output=True, text=True, encoding="utf-8", errors="replace",
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    ran = re.search(r"^Ran (\d+) tests", out, re.M)
    failures = re.search(r"FAILED \(failures=(\d+)", out)
    errors = re.search(r"errors=(\d+)", out)
    failed = (int(failures.group(1)) if failures else 0) + (int(errors.group(1)) if errors else 0)
    return proc.returncode == 0, int(ran.group(1)) if ran else 0, failed


def main() -> int:
    original = TARGET.read_text(encoding="utf-8")
    shutil.copyfile(TARGET, BACKUP)
    print(f"[baseline] 备份 {TARGET.name} -> {BACKUP}")
    try:
        ok, ran, failed = _run_tests()
        print(f"[baseline] Ran {ran} / {'OK' if ok else f'FAILED({failed})'}")
        if not ok:
            print("基线不是绿的 —— 先修用例/生产代码，再做变异。")
            return 2
        for name, old, new in MUTATIONS:
            if old not in original:
                print(f"[{name}] 跳过：源码片段没匹配上（代码改过？）")
                return 2
            TARGET.write_text(original.replace(old, new, 1), encoding="utf-8")
            ok, ran, failed = _run_tests()
            print(f"[{name}] Ran {ran} / {'OK（杀 0 条！）' if ok else f'红 {failed} 条'}")
            if ok:
                print("  ⚠ 该变异逃逸 ⇒ 用例没钉住这条判据。")
                return 1
        return 0
    finally:
        TARGET.write_text(original, encoding="utf-8")
        print(f"[restore] {TARGET.name} 已还原（与备份逐字一致：{TARGET.read_bytes() == BACKUP.read_bytes()}）")


if __name__ == "__main__":
    raise SystemExit(main())
