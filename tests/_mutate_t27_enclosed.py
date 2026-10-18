# -*- coding: utf-8 -*-
"""【task-27 / 0.7.46 卡 C】"被围死"口径 + 前置过滤的**变异自检**。

对 `brain/agentfarm/farmwork.py` / `brain/agentfarm/longrun.py` 注入变异，验证
`tests/test_longrun.py::TestTask27EnclosedBatch` 能全部杀掉：

* `m1_old_unreachable`：把"没有落脚点证据也写 unreachable"的旧口径塞回去
  （冬26 的 12 格 till + 20 格 clear 又会被算成本该可达）⇒ 必须红；
* `m2_prefilter_disabled`：目标池前置过滤关掉 ⇒ 已证明围死的格又会被塞回目标池；
* `m3_foothold_optimistic`：把"证据口径"换成 `_standable_near` 的乐观口径
  （四邻没观测到也算可能能站）⇒ 又回到打穿 bound 的老 bug，必须红；
* `m4_dead_as_ok`：被围住的格记成 ok/already（洗白成"干成了"）⇒ 必须红；
* `m5_burst_lists_removed`：`no_progress_burst` 的逐格坐标证据被删 ⇒ 必须红；
* `m6_day_end_lists_removed`：`day_end` 的逐格坐标证据被删 ⇒ 必须红。

怎么跑（仓库根；PYTHONUTF8=1 + DSH 运行时）：

    $env:PYTHONUTF8='1'
    & "C:\\Users\\admin\\.dsh\\dsh-runtimes\\dsh-primary-runtime\\dependencies\\python\\python.exe" `
        tests\\_mutate_t27_enclosed.py --from-worktree

默认基线 = `git archive HEAD` 冻结树（只取 `brain/` 与 `tests/`）；`--from-worktree` 供提交前自检。
"""

from __future__ import annotations

import argparse
import io
import os
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = "tests.test_longrun.TestTask27EnclosedBatch"
FARMWORK_REL = Path("brain") / "agentfarm" / "farmwork.py"
LONGRUN_REL = Path("brain") / "agentfarm" / "longrun.py"

MUTATIONS: list[tuple[str, Path, str, str, str]] = [
    (
        "m1_old_unreachable",
        FARMWORK_REL,
        "        if not env_failed and not self._observed_foothold(self.snap(), tile):\n",
        "        if False:\n",
        "没有落脚点证据也写 unreachable（旧口径）⇒ 冬26 的批量失败又打穿日级 bound",
    ),
    (
        "m2_prefilter_disabled",
        LONGRUN_REL,
        "        if task in (\"clear_area\", \"clear_dead\", \"till_area\", \"plant_area\"):\n"
        "            pool = self._prefilter_known_enclosed(task, obs, pool)\n",
        "        if False:\n"
        "            pool = self._prefilter_known_enclosed(task, obs, pool)\n",
        "目标池前置过滤被关掉 ⇒ 观测已证明围死的格又进目标池",
    ),
    (
        "m3_foothold_optimistic",
        FARMWORK_REL,
        "        if not env_failed and not self._observed_foothold(self.snap(), tile):\n",
        "        if not env_failed and not self._standable_near(self.snap(), tile):\n",
        "证据口径换回乐观口径（四邻没观测到也算可能能站）⇒ 又能把挡死算成走不到",
    ),
    (
        "m4_dead_as_ok",
        FARMWORK_REL,
        "        r.code = ENCIRCLED_CODE\n"
        "        r.tried_open = len(cleared)\n",
        "        r.ok = True\n"
        "        r.code = ENCIRCLED_CODE\n"
        "        r.tried_open = len(cleared)\n",
        "挡死格记成 ok ⇒ 洗白成已做成（必须被杀）",
    ),
    (
        "m5_burst_lists_removed",
        LONGRUN_REL,
        "            pending_executable_tiles=list(snap.get(\"executable_tiles\") or [])[:8],\n"
        "            pending_stalled_tiles=list(snap.get(\"stalled_tiles\") or [])[:8],\n",
        "",
        "no_progress_burst 的逐格坐标证据被删",
    ),
    (
        "m6_day_end_lists_removed",
        LONGRUN_REL,
        "        rep.pending_executable_tiles = list(snap.get(\"executable_tiles\") or [])[:8]\n"
        "        rep.pending_stalled_tiles = list(snap.get(\"stalled_tiles\") or [])[:8]\n",
        "",
        "day_end 的逐格坐标证据被删",
    ),
    (
        "m7_prefiltered_not_assigned",
        LONGRUN_REL,
        "            for _r in self._prefiltered_encircled_today[prefiltered_before:]:\n"
        "                if str(_r.get(\"stage\") or \"\") != task:\n"
        "                    continue\n"
        "                try:\n"
        "                    assigned.add((int(_r[\"tile\"][0]), int(_r[\"tile\"][1])))\n"
        "                except (TypeError, ValueError, IndexError, KeyError):\n"
        "                    continue\n",
        "            pass  # 变异：前置过滤判死格不进 assigned\n",
        "预过滤判死格从 assigned 蒸发 ⇒ 挡死被洗成「没活」",
    ),
    (
        "m8_dead_reason_unknown",
        LONGRUN_REL,
        "            if not steps_here and key in self.encircled_day:\n"
        "                # 【task-27 / 0.7.46】目标池前置过滤判死的格没有 step：既不是\"做成了\"，\n"
        "                # 也不是\"没试过\"，如实归 `blocked_tile`（闭合集内，不落 unknown_evidence）。\n"
        "                reason = \"blocked_tile\"\n"
        "            else:\n"
        "                reason = self._tile_reason(key, steps_here, stopped=stopped, obs=obs)\n",
        "            reason = self._tile_reason(key, steps_here, stopped=stopped, obs=obs)\n",
        "判死格的原因码落回 unknown_evidence（证据缺口被吞）",
    ),
]


def _run(cmd: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = str(cwd / "brain")
    return subprocess.run(cmd, cwd=str(cwd), env=env, text=True,
                          encoding="utf-8", errors="replace",
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT)


def _unittest(tree: Path) -> tuple[bool, int, list[str]]:
    proc = _run([sys.executable, "-m", "unittest", TARGET, "-v"], tree)
    out = proc.stdout or ""
    ran = re.search(r"^Ran (\d+) tests? in ", out, re.M)
    failures = re.findall(r"^(?:FAIL|ERROR): (\S+)", out, re.M)
    ok = bool(ran) and "OK" in out and proc.returncode == 0
    return ok, int(ran.group(1)) if ran else 0, failures


def _extract_head(dest: Path) -> None:
    proc = subprocess.run(
        ["git", "-C", str(ROOT), "archive", "--format=zip", "HEAD", "brain", "tests"],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if proc.returncode != 0:
        raise SystemExit("git archive 失败：" + proc.stderr.decode("utf-8", "replace")[:500])
    with zipfile.ZipFile(io.BytesIO(proc.stdout)) as zf:
        zf.extractall(dest)


def _copy_worktree(dest: Path) -> None:
    for name in ("brain", "tests"):
        shutil.copytree(ROOT / name, dest / name,
                        ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--from-worktree", action="store_true",
                    help="用当前工作树的 brain/ + tests/ 当基线（提交前自检用）")
    args = ap.parse_args()

    with tempfile.TemporaryDirectory(prefix="t27-mutate-") as tmp:
        tree = Path(tmp) / "frozen"
        tree.mkdir()
        if args.from_worktree:
            _copy_worktree(tree)
        else:
            _extract_head(tree)

        ok, ran, _ = _unittest(tree)
        if not ok:
            print(f"[baseline] × 基线不是绿的（Ran {ran}）——先修测试再谈变异")
            return 2
        print(f"[baseline] OK（{TARGET}：Ran {ran} tests）")

        killed = 0
        survived: list[str] = []
        for mid, rel, old, new, why in MUTATIONS:
            target = tree / rel
            original = target.read_text(encoding="utf-8")
            count = original.count(old)
            if count != 1:
                print(f"[{mid}] × 变异锚点出现 {count} 次（要求恰好 1 次）——脚本已过期")
                return 2
            try:
                target.write_text(original.replace(old, new, 1), encoding="utf-8")
                ok_mut, ran_mut, failures = _unittest(tree)
            finally:
                target.write_text(original, encoding="utf-8")
            if ok_mut:
                survived.append(mid)
                print(f"[{mid}] SURVIVED（Ran {ran_mut} tests）——{why}")
            else:
                killed += 1
                names = "、".join(f.split(".")[-1] for f in failures) or "（见输出）"
                print(f"[{mid}] killed（Ran {ran_mut} tests，红 {len(failures)}：{names}）")

        print(f"\n结果：{killed}/{len(MUTATIONS)} 条变异被杀；存活 "
              f"{'、'.join(survived) if survived else '无'}")
        return 0 if not survived else 1


if __name__ == "__main__":
    raise SystemExit(main())
