"""task-41 变异证伪（deputy-lead 自己写、自己跑）：把三处修复分别改坏，确认**红在预期用例**上。

用法（cwd = 仓库根）：
    python scratch/_t41_falsify.py <none|a|b|c> <test1> [test2 ...]
      none 对照（不注入）；a = `sleep_guard` 把 fail-closed 退回放行 `no_work`；
      b = `work_reasons` 不再给出 "farm 证据不可用"（rev4 §10 的"改了等于没改"路径）；
      c = 去掉 `_clear_modals` 的 eventUp ⓪ 闸门。
只在副本 `scratch/_t41_mut/agentfarm` 上注入，生产 `brain/` 全程只读。
坑①：`tests/test_longrun.py` 会 `sys.path.insert(0, brain)` 劫持 ⇒ 必须先导入副本包。
坑②：测试名必须写全（裸方法名会变 _FailedTest 而退出码照样 1）。
"""
import pathlib
import shutil
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
MUT = ROOT / "scratch" / "_t41_mut"
SRC = ROOT / "brain" / "agentfarm"

mode = sys.argv[1]
names = sys.argv[2:]
if mode not in ("none", "a", "b", "c"):
    raise SystemExit(f"unknown mode {mode}")
if not names:
    raise SystemExit("need at least one test name")

if MUT.exists():
    shutil.rmtree(MUT)
MUT.mkdir(parents=True)
shutil.copytree(SRC, MUT / "agentfarm")

target = MUT / "agentfarm" / "longrun.py"
text = target.read_text(encoding="utf-8")

MUTATIONS = {
    # a：fail-closed 退回"放行 no_work"（run3 连睡路径）
    "a": ('            return False, "keep_working", self._farm_evidence_reason(obs)',
          '            return True, "no_work", "MUT-a"  # noqa'),
    # b：work_reasons 不再给出"farm 证据不可用"⇒ _run_day 的 why 落回 no_work
    "b": ('            reasons.append(self._farm_evidence_reason(obs))',
          '            pass  # MUT-b'),
    # c：去掉 eventUp ⓪ 闸门 ⇒ 事件被当普通 DialogueBox 关掉
    "c": ('            if ui.get("eventUp") is True:',
          '            if False:  # MUT-c'),
}

if mode != "none":
    old, new = MUTATIONS[mode]
    if old not in text:
        raise SystemExit(f"注入点没找到（mode={mode}），源码变了？")
    target.write_text(text.replace(old, new, 1), encoding="utf-8")
    print(f"INJECTED {mode} into {target}", flush=True)

sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(MUT))
import agentfarm.longrun as ml  # noqa: E402

print(f"USED_MODULE {ml.__file__}", flush=True)
if str(MUT) not in ml.__file__:
    raise SystemExit("副本没抢到，结果无效")

suite = unittest.TestLoader().loadTestsFromNames(names)
res = unittest.TextTestRunner(verbosity=2).run(suite)
failed = sorted(t.id().split(".")[-1] for t, _ in res.failures + res.errors)
print(
    f"RESULT mode={mode} successful={res.wasSuccessful()} "
    f"failures={len(res.failures)} errors={len(res.errors)} run={res.testsRun} "
    f"RED={failed}",
    flush=True,
)
sys.exit(0 if res.wasSuccessful() else 1)
