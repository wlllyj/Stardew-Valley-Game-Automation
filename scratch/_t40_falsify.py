"""task-40 变异证伪：把 cc2988e 的两处修复分别改坏，确认**红在预期用例**上。

用法（cwd = 仓库根）：
    python scratch/_t40_falsify.py <none|A|B> <test1> [test2 ...]
      none 对照；A = `_ensure_on_farm` 恒 `return obs`；B = `_farm_scope_work` 恒 `None`。
只在副本 `scratch/_t40_mut/agentfarm` 上注入，生产 `brain/` 全程只读。
坑①：`tests/test_longrun.py` 会 `sys.path.insert(0, brain)` 劫持 ⇒ 必须**先**导入副本包。
坑②：测试名必须写全 `tests.test_longrun.TestMorningIndoor.test_xxx`（裸方法名会变 _FailedTest）。
"""
import pathlib
import shutil
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MUT = ROOT / "scratch" / "_t40_mut"
SRC = ROOT / "brain" / "agentfarm"

mode = sys.argv[1]
names = sys.argv[2:]
if mode not in ("none", "A", "B"):
    raise SystemExit(f"unknown mode {mode}")
if not names:
    raise SystemExit("need at least one test name")

if MUT.exists():
    shutil.rmtree(MUT)
MUT.mkdir(parents=True)
shutil.copytree(SRC, MUT / "agentfarm")

target = MUT / "agentfarm" / "longrun.py"
text = target.read_text(encoding="utf-8")

if mode == "A":
    old = "        if self._is_farm(obs):\n            return obs\n        assert self.worker is not None"
    new = "        if True:  # MUT-A\n            return obs\n        assert self.worker is not None"
elif mode == "B":
    old = "        if self._is_farm(obs):\n            return None\n        farm = obs.get(\"farm\") or {}"
    new = "        if True:  # MUT-B\n            return None\n        farm = obs.get(\"farm\") or {}"
else:
    old = new = None

if mode != "none":
    if old not in text:
        raise SystemExit("注入点没找到，源码变了？")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"INJECTED {mode} into {target}", flush=True)

# 抢在 tests 的 sys.path.insert 之前把副本包加载进 sys.modules
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(MUT))
import agentfarm.longrun as ml  # noqa: E402

print(f"USED_MODULE {ml.__file__}", flush=True)
if str(MUT) not in ml.__file__:
    raise SystemExit("副本没抢到，结果无效")

suite = unittest.TestLoader().loadTestsFromNames(names)
res = unittest.TextTestRunner(verbosity=2).run(suite)
print(
    f"RESULT successful={res.wasSuccessful()} failures={len(res.failures)} errors={len(res.errors)} "
    f"run={res.testsRun}",
    flush=True,
)
sys.exit(0 if res.wasSuccessful() else 1)
