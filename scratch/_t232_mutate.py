"""【task-232】变异自检：空格压力通道的每一条纪律都必须被用例钉死。

三个变异（都只该让**本卡新增用例**变红）：

  * m232a：关掉 `_slot_relief` 的"空格压力"第三层（真机死锁形态复活）；
  * m232b：去掉"每 qid 留 K"（任何叠都当盈余卖 ⇒ 会把背包卖空）；
  * m232c：放开 `SLOT_RELIEF_NEVER_SELL_IDS`（升级锭也会被卖）。

用法：`python scratch/_t232_mutate.py`（自动拷 brain+tests 到临时目录，跑完删）。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = [
    "tests.test_farmwork.TestTask232SlotReliefPlan",
    "tests.test_longrun.TestTask232SpacePressure",
]
MUTATIONS = {
    "m232a_no_space_channel": (
        "brain/agentfarm/longrun.py",
        "        if int(self._bag_state(obs)[0]) <= SLOT_RESERVE:",
        "        if False:  # mutation：关掉空格压力通道",
    ),
    "m232b_ignore_keep": (
        "brain/agentfarm/farmwork.py",
        '        if totals[st["qid"]] - int(st["stack"]) >= eff_keep:',
        "        if True:  # mutation：不看 keep（任何叠都当盈余）",
    ),
    "m232c_sell_unknown_items": (
        "brain/agentfarm/farmwork.py",
        "        else:\n            continue                          # 表外一律不卖（fail-closed）",
        '        else:\n            tier, why = 9, "unknown"  # mutation：表外也卖（fail-closed 被破坏）',
    ),
    "m232d_ignore_building_reserve": (
        "brain/agentfarm/farmwork.py",
        '        reserve = reserves.get(str(st["qid"]))',
        "        reserve = None  # mutation：关掉建造预留覆盖",
    ),
}


def run(cmd: list[str], *, cwd: Path, env: dict[str, str]) -> tuple[int, str]:
    proc = subprocess.run(cmd, cwd=str(cwd), env=env, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def main() -> int:
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = str(ROOT / "brain")
    code, out = run([sys.executable, "-m", "unittest", *TESTS], cwd=ROOT, env=env)
    base_red = [ln for ln in out.splitlines() if ln.startswith(("FAIL:", "ERROR:"))]
    print(f"基线：rc={code} 红={len(base_red)}")
    if base_red:
        print("\n".join(base_red))
        return 1
    total = 0
    for name, (rel, old, new) in MUTATIONS.items():
        with tempfile.TemporaryDirectory(prefix="t232-mut-") as tmp:
            tmpd = Path(tmp)
            shutil.copytree(ROOT / "brain", tmpd / "brain")
            shutil.copytree(ROOT / "tests", tmpd / "tests")
            target = tmpd / rel
            src = target.read_text(encoding="utf-8")
            if old not in src:
                print(f"{name}: 锚点失效（未找到待替换文本）")
                continue
            target.write_text(src.replace(old, new, 1), encoding="utf-8")
            env2 = dict(env)
            env2["PYTHONPATH"] = str(tmpd / "brain")
            _code, mout = run([sys.executable, "-m", "unittest", *TESTS], cwd=tmpd, env=env2)
            killed = [ln for ln in mout.splitlines() if ln.startswith(("FAIL:", "ERROR:"))]
            total += len(killed)
            print(f"{name}: 杀 {len(killed)}")
            for line in killed:
                print(f"    {line}")
    print(f"合计杀 {total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
