"""task-54 独立变异证伪（deputy-lead 自写，不碰生产代码）。

把生产代码"改错"到副本 `scratch/_t54_mut/agentfarm`，再跑四卡用例，确认它们**真的会红**。
用法：
    python scratch/_t54_falsify.py <mode> <test...>
mode: none | m52a | m52b | m63a | m50a

坑（已内建）：`tests/test_farmwork.py:22` 会把 `brain/` 插到 `sys.path[0]`，
所以必须在导入 tests **之前**先把副本模块塞进 `sys.modules`（本脚本先 import）。
"""

from __future__ import annotations

import re
import shutil
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "brain" / "agentfarm"
MUT = ROOT / "scratch" / "_t54_mut" / "agentfarm"


def mutate_text(name: str, text: str) -> str:
    """按 mode 改坏源码（每处只改第一个匹配）。"""
    if name == "m52a":
        # StepResult.unreachable 恒 False ⇒ 不可达不再被识别 → 不可达豁免/计数失效
        pat = re.compile(
            r"(?ms)^    def unreachable\(self\) -> bool:.*?^        return self\.code == UNREACHABLE_CODE$"
        )
        new, n = pat.subn('    def unreachable(self) -> bool:\n        return False', text)
    elif name == "m52b":
        # 日级上界恒巨大 ⇒ 防洗白失效
        new, n = re.subn(
            r"unreachable_bound = max\(5, int\(0\.2 \* attempted_steps\)\)",
            "unreachable_bound = 10 ** 9",
            text,
        )
    elif name == "m63a":
        # 拒绝豁免被取消 ⇒ "游戏拒绝"退回硬失败
        new, n = re.subn(
            r"(?m)^TILE_INERT_STATUSES[^\n]*$",
            "TILE_INERT_STATUSES: tuple[str, ...] = ()",
            text,
        )
    elif name == "m50a":
        # 旧 Mod 缺 dryTiles 被当成"没有干格"（正是卡面禁止的）
        new, n = re.subn(
            r'    raw = farm\.get\("dryTiles"\)\n    if raw is None:\n        return \[\], "unavailable"',
            '    raw = farm.get("dryTiles")\n    if raw is None:\n        return [], "ok"',
            text,
        )
    elif name == "m51a":
        # 目标池不再过滤 dead ⇒ 活苗也会被"清死苗"盯上
        new, n = re.subn(
            r'if v\.get\("crop"\) and v\.get\("dead"\)\]',
            'if v.get("crop")]',
            text,
            count=1,
        )
    elif name == "m51b":
        # farmwork.clear_dead 的"活苗不碰"守卫被拆掉
        new, n = re.subn(
            r'(?m)^        if not \(tv or \{\}\)\.get\("dead"\):$',
            "        if False:",
            text,
            count=1,
        )
    else:
        raise SystemExit(f"unknown mode {name}")
    if n != 1:
        raise SystemExit(f"[{name}] 期望替换 1 处，实际 {n} 处 ⇒ 源码形状变了，先核对再改")
    return new


def build(mode: str) -> None:
    if MUT.parent.exists():
        shutil.rmtree(MUT.parent)
    MUT.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(SRC, MUT)
    if mode == "none":
        return
    target = "longrun.py" if mode in ("m52b", "m51a") else "farmwork.py"
    p = MUT / target
    p.write_text(mutate_text(mode, p.read_text(encoding="utf-8")), encoding="utf-8")


def main() -> int:
    if len(sys.argv) < 3:
        raise SystemExit(__doc__)
    mode, names = sys.argv[1], sys.argv[2:]
    build(mode)

    sys.path.insert(0, str(ROOT))
    sys.path.insert(0, str(MUT.parent))
    import agentfarm.farmwork  # noqa: F401
    import agentfarm.longrun  # noqa: F401

    print(f"MODE={mode} USED_LONGRUN={agentfarm.longrun.__file__}")
    print(f"MODE={mode} USED_FARMWORK={agentfarm.farmwork.__file__}")
    assert str(MUT) in agentfarm.longrun.__file__, "副本没生效 ⇒ 别信这次结果"

    suite = unittest.defaultTestLoader.loadTestsFromNames(names)
    res = unittest.TextTestRunner(verbosity=1).run(suite)
    print(
        f"MODE={mode} run={res.testsRun} failures={len(res.failures)} errors={len(res.errors)} "
        f"successful={res.wasSuccessful()}"
    )
    for t, _ in res.failures + res.errors:
        print(f"  RED {t.id()}")
    return 0 if res.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
