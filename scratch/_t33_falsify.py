"""task-33 条款 6 的执行器：在**副本变异**的 `agentfarm` 上跑 `tests/test_farmwork.py` 的睡眠用例。

为什么要这么绕：`tests/test_farmwork.py:22` 自己会把 `brain/` 插到 `sys.path[0]`，
所以光设 `PYTHONPATH` 指副本没用（实测：变异与对照读数一模一样）。这里先把副本的
`agentfarm` 预导入占住 `sys.modules`，再加载测试模块 ⇒ 测试用的是副本。

用法：
    python scratch/_t33_mutate.py m1_blind_send
    python scratch/_t33_falsify.py TestSleepCrossDay.test_no_question_fails_fast_without_asking_mod
    python scratch/_t33_falsify.py            # 默认跑整个 TestSleepCrossDay
"""

import importlib
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MUT = ROOT / "scratch" / "_t33_mut"

if not (MUT / "agentfarm" / "farmwork.py").exists():
    print("先跑：python scratch/_t33_mutate.py <mutation>")
    raise SystemExit(2)

sys.path.insert(0, str(MUT))
import agentfarm.farmwork as fw  # noqa: E402  —— 必须来自副本

if str(MUT) not in fw.__file__:
    print(f"❌ 用的是生产包，不是副本：{fw.__file__}")
    raise SystemExit(2)

sys.path.insert(0, str(ROOT))
importlib.import_module("tests.test_farmwork")  # 它会把 brain/ 插到前面，但 agentfarm 已缓存

names = [f"tests.test_farmwork.{a}" for a in (sys.argv[1:] or ["TestSleepCrossDay"])]
suite = unittest.defaultTestLoader.loadTestsFromNames(names)
res = unittest.TextTestRunner(verbosity=2).run(suite)
print(f"USED_MODULE {fw.__file__}")
raise SystemExit(0 if res.wasSuccessful() else 1)
