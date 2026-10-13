"""task-44 独立验收的**变异证伪**工具（deputy-lead 自写）。

把 `brain/agentfarm` 复制到 `scratch/_t44_mut/agentfarm`，在副本里注入一处 bug，
然后**先预导入副本包**（绕开 `tests/test_farmwork.py:22` 的 `sys.path.insert(0, brain)`
劫持）再跑指定用例 —— 用来证明那些用例真的能证伪，而不是"照着实现写的顺拐断言"。

用法：
  & $py scratch\_t44_falsify.py <mode> [测试ID...]
  mode ∈ none | m1 | m2 | m3 | m4
不传测试 ID 时按 mode 用默认集合。跑完生产文件字节不变（只碰 scratch/ 副本）。
"""
from __future__ import annotations

import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "brain" / "agentfarm"
MUT_ROOT = ROOT / "scratch" / "_t44_mut"
MUT = MUT_ROOT / "agentfarm"

# mode -> (说明, [(文件, 原文, 替换后)], 默认测试 ID)
MUTATIONS: dict[str, tuple[str, list[tuple[str, str, str]], list[str]]] = {
    "none": ("不注入（对照组）", [], [
        "tests.test_farmwork.TestTask42Sell",
        "tests.test_farmwork.TestTask43LongPathRecovery",
    ]),
    "m1": ("sell() 只看回执：把『槽位空 + 计数下降』改成恒真",
           [("farmwork.py",
             "        if (not still) and n_after < n_before:",
             "        if True:  # MUT m1")],
           ["tests.test_farmwork.TestTask42Sell"]),
    "m2": ("白名单不再要求『背包真的变多』：任何一件都算收获",
           [("farmwork.py",
             "            d = int(n) - int((before or {}).get(qid, 0))\n"
             "            if d > 0:\n"
             "                out[qid] = d",
             "            d = int(n) - int((before or {}).get(qid, 0))\n"
             "            if True:  # MUT m2\n"
             "                out[qid] = max(1, d)")],
           ["tests.test_farmwork.TestTask42Sell"]),
    "m3": ("砍掉两段式接近（回执里有源格也不先 move_to）",
           [("farmwork.py",
             "            if src is not None:\n"
             "                try:\n"
             "                    side = self._neighbour_to_walk(self.snap(), src)",
             "            if False:  # MUT m3\n"
             "                try:\n"
             "                    side = self._neighbour_to_walk(self.snap(), src)")],
           ["tests.test_farmwork.TestTask43LongPathRecovery"]),
    "m4": ("脑侧默认预算退回 30000ms（Mod 放宽到 60000 也白搭）",
           [("farmwork.py",
             "                        timeout_ms: int = 60000) -> StepResult:",
             "                        timeout_ms: int = 30000) -> StepResult:  # MUT m4")],
           ["tests.test_farmwork.TestTask43LongPathRecovery"]),
}


def build(mode: str) -> str:
    desc, patches, _ = MUTATIONS[mode]
    if MUT_ROOT.exists():
        shutil.rmtree(MUT_ROOT)
    MUT_ROOT.mkdir(parents=True)
    shutil.copytree(SRC, MUT)
    for name, old, new in patches:
        p = MUT / name
        text = p.read_text(encoding="utf-8")
        if old not in text:
            raise SystemExit(f"变异锚点没找到（{mode} / {name}）：{old[:60]!r}")
        if text.count(old) != 1:
            raise SystemExit(f"变异锚点不唯一（{mode} / {name}）：{text.count(old)} 处")
        p.write_text(text.replace(old, new), encoding="utf-8")
    return desc


def main() -> int:
    mode = sys.argv[1] if len(sys.argv) > 1 else "none"
    if mode not in MUTATIONS:
        raise SystemExit(f"未知 mode={mode}；可选：{', '.join(MUTATIONS)}")
    desc = build(mode)
    ids = sys.argv[2:] or MUTATIONS[mode][2]

    sys.path.insert(0, str(MUT_ROOT))     # 副本包优先
    sys.path.insert(0, str(ROOT))
    import agentfarm.farmwork as fw      # noqa: E402  —— 必须先于 tests 导入，占住 sys.modules
    print(f"mode={mode}  {desc}")
    print(f"USED_MODULE {fw.__file__}")
    if "_t44_mut" not in str(fw.__file__):
        raise SystemExit("变异副本没有生效（假绿风险）")

    loader = unittest.TestLoader()
    suite = unittest.TestSuite()
    for tid in ids:
        if tid.endswith((".TestTask42Sell", ".TestTask43LongPathRecovery")):
            suite.addTests(loader.loadTestsFromName(tid))
        else:
            suite.addTests(loader.loadTestsFromName(tid))
    res = unittest.TextTestRunner(verbosity=2).run(suite)
    red = [t.id().split(".")[-1] for t, _ in res.failures + res.errors]
    print(f"SUMMARY mode={mode} run={res.testsRun} failures={len(res.failures)} "
          f"errors={len(res.errors)} RED={red}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
