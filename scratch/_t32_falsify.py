"""task-32 条款 6 的执行器：在**副本变异**的 `agentfarm` 上跑 `tests/test_longrun.py` 的 task-32 用例。

为什么要这么绕：`tests/test_longrun.py` 自己会把 `brain/` 插到 `sys.path[0]`，光设 `PYTHONPATH`
指副本没用。这里先 import 副本的 `agentfarm.longrun` 占住 `sys.modules`，再加载测试模块 ⇒
测试用的是副本（`agentfarm` 包的 `__path__` 已指向副本，子模块也全从副本取）。

用法：
    python scratch/_t32_mutate.py m32a_no_plot_whitelisted
    python scratch/_t32_falsify.py test_no_plot_is_not_a_justified_reason
    python scratch/_t32_falsify.py            # 默认跑整个 TestTask32PlotsCap
"""

import importlib
import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MUT = ROOT / "scratch" / "_t32_mut"

if not (MUT / "agentfarm" / "longrun.py").exists():
    print("先跑：python scratch/_t32_mutate.py <mutation>")
    raise SystemExit(2)

sys.path.insert(0, str(MUT))
import agentfarm.longrun as lr  # noqa: E402  —— 必须来自副本

if str(MUT) not in lr.__file__:
    print(f"❌ 用的是生产包，不是副本：{lr.__file__}")
    raise SystemExit(2)

sys.path.insert(0, str(ROOT))
importlib.import_module("tests.test_longrun")  # 它会把 brain/ 插到前面，但 agentfarm 已缓存

names = [f"tests.test_longrun.{a}" for a in (sys.argv[1:] or ["TestTask32PlotsCap"])]
suite = unittest.defaultTestLoader.loadTestsFromNames(names)
res = unittest.TextTestRunner(verbosity=2).run(suite)
print(f"USED_MODULE {lr.__file__}")
raise SystemExit(0 if res.wasSuccessful() else 1)
