"""【task-233】变异自检：非片区意图的 `no_target` 洗白通道必须被用例钉死。

两个变异（都只该让**本卡新增用例**变红，其它绿）：
  * m233a：把 `_execute` 的 ship 失败分支退回"裸 `no_target`"（真机事故原形）；
  * m233b：把 cancel 链路的"证据不可用 ⇒ 降级 `unknown_evidence`"退回裸 `no_target`。

用法：`python scratch/_t233_mutate.py`（自动拷 brain+tests 到临时目录，跑完删）。
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = [
    "tests.test_longrun.TestTask233NonPlotEvidence",
    "tests.test_longrun.TestTask233PlotNoTargetUnchanged",
]
MUTATIONS = {
    "m233a_ship_bare_no_target": (
        'reasons={"unknown_evidence": 1},\n                                        evidence=evidence, note=note)',
        'reasons={"no_target": 1},\n                                        note=note)',
    ),
    "m233b_no_target_evidence_always_none": (
        "        if plot is None:\n            return None\n        try:\n            tiles = self._stage_tiles(task, dict(obs), dict(plot))",
        "        if True:  # 变异：证据一律拿不到\n            return None\n        try:\n            tiles = self._stage_tiles(task, dict(obs), dict(plot))",
    ),
}


def run(cmd: list[str], *, cwd: Path, env: dict[str, str]) -> tuple[int, str]:
    proc = subprocess.run(cmd, cwd=str(cwd), env=env, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def main() -> int:
    env = dict(__import__("os").environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = str(ROOT / "brain")
    code, out = run([sys.executable, "-m", "unittest", *TESTS], cwd=ROOT, env=env)
    base_red = [ln for ln in out.splitlines() if ln.startswith(("FAIL:", "ERROR:"))]
    print(f"基线：rc={code} 红={len(base_red)}")
    if base_red:
        print("\n".join(base_red))
        return 1
    total = 0
    for name, (old, new) in MUTATIONS.items():
        with tempfile.TemporaryDirectory(prefix="t233-mut-") as tmp:
            tmpd = Path(tmp)
            shutil.copytree(ROOT / "brain", tmpd / "brain")
            shutil.copytree(ROOT / "tests", tmpd / "tests")
            shutil.copytree(ROOT / "tools", tmpd / "tools")
            target = tmpd / "brain" / "agentfarm" / "longrun.py"
            src = target.read_text(encoding="utf-8")
            if old not in src:
                print(f"{name}: 锚点失效（未找到待替换文本）")
                return 1
            target.write_text(src.replace(old, new, 1), encoding="utf-8")
            env2 = dict(env)
            env2["PYTHONPATH"] = str(tmpd / "brain")
            code2, out2 = run([sys.executable, "-m", "unittest", *TESTS], cwd=tmpd, env=env2)
            killed = [ln for ln in out2.splitlines() if ln.startswith(("FAIL:", "ERROR:"))]
            print(f"{name}: rc={code2} 杀={len(killed)}")
            for ln in killed:
                print(f"  · {ln}")
            if not killed:
                print(f"{name}: 没杀掉任何用例（变异逃逸）")
            total += len(killed)
    print(f"合计杀 {total}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
