# -*- coding: utf-8 -*-
r"""task-81 独立探针 —— **跑真代码**（不是读代码）复核 task-78 的两条修法。

用法（pwsh，必须 UTF-8）：
  $env:PYTHONUTF8="1"
  & $py scratch\_t81_probe.py farmwork     # A 段：encircled 判据的文案/字段（真 FarmWorker + MiniWorld）
  & $py scratch\_t81_probe.py day          # B 段：日级 `bound_basis` 公式（真 LongRun + 假 worker）

设计纪律：只 import 生产代码与测试既有的假世界，**不改任何生产文件**；每个断言都打印原文。
"""
from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

#: `T81_ROOT` 可以指向另一棵树（例如 task-78 之前的快照），用来证明本探针**能变红**。
ROOT = Path(os.environ.get("T81_ROOT") or Path(__file__).resolve().parents[1]).resolve()
sys.path.insert(0, str(ROOT / "brain"))


def _load(path: Path, name: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


def _ok(flag: bool, label: str, detail: str = "") -> bool:
    print(f"[{'PASS' if flag else 'FAIL'}] {label}{('：' + detail) if detail else ''}")
    return bool(flag)


# ---------------------------------------------------------------- A 段
def part_farmwork() -> int:
    tw = _load(ROOT / "tests" / "test_farmwork.py", "_t81_tw")
    fw = importlib.import_module("agentfarm.farmwork")
    target = (62, 10)
    # 5x5 的杂草块：全部观测为 `standable=False`，且**都走不过去**（`unwalkable`）⇒ 真机 run6 的
    # `field_ne`「四邻都站不过去」形态。判据应只看观测 + 1 层开路启发式，**不该挥一刀**。
    block = [(x, y) for x in range(60, 65) for y in range(8, 13)]
    recs = []
    for t in block:
        rec = tw.weed_rec(t)
        rec["standable"] = False
        recs.append(rec)
    w = tw.MiniWorld(records=recs, inventory=tw.INV_WITH_SCYTHE, tools=tw.TOOLS_WITH_SCYTHE)
    w.player_tile = [60, 15]
    w.unwalkable = set(block)
    r = tw.make_worker(w).clear(target)
    d = r.as_dict()
    reason = str(r.reason or "")
    print("A1 code=%r ok=%r stood=%r tried_open=%r" % (r.code, r.ok, r.stood,
                                                      getattr(r, "tried_open", None)))
    print("A1 reason=%s" % reason)
    print("A1 as_dict keys=%s" % sorted(d.keys()))
    print("A1 use_tool calls=%s opened=%s" % (len(w.calls), getattr(r, "opened", None)))

    allok = True
    allok &= _ok(r.code == fw.ENCIRCLED_CODE, "A1 判为 encircled",
                 f"code={r.code!r} 期望 {fw.ENCIRCLED_CODE!r}")
    allok &= _ok("weed" in reason, "A1 reason 写出真实 kind（weed）", reason[:200])
    allok &= _ok(not any(s in reason for s in ("树", "桩", "大石")),
                 "A1 reason 不再断言『树/桩/大石』", reason[:200])
    allok &= _ok("tried_open" in d, "A1 步级 `as_dict()` 带 tried_open",
                 f"keys={sorted(d.keys())}")
    allok &= _ok(getattr(r, "tried_open", 0) == 0, "A1 tried_open=0（真的没挥过）",
                 f"tried_open={getattr(r, 'tried_open', None)}")
    allok &= _ok(len(w.calls) == 0, "A1 一次 `use_tool` 都没发", f"calls={w.calls}")

    # A2 对照：把 (61,10) 改成"站着得过去、且不在 unwalkable 里" ⇒ 开路应当真的挥刀（不再 encircled）
    recs2 = []
    for t in block:
        rec = tw.weed_rec(t)
        rec["standable"] = (t == (61, 10))
        recs2.append(rec)
    w2 = tw.MiniWorld(records=recs2, inventory=tw.INV_WITH_SCYTHE, tools=tw.TOOLS_WITH_SCYTHE)
    w2.player_tile = [60, 15]
    w2.unwalkable = set(block) - {(61, 10)}
    r2 = tw.make_worker(w2).clear(target)
    print("A2 code=%r reason=%s" % (r2.code, str(r2.reason or "")[:200]))
    allok &= _ok(r2.code != fw.ENCIRCLED_CODE, "A2 对照：有落脚点时不判 encircled",
                 f"code={r2.code!r}")
    return 0 if allok else 1


def main() -> int:
    which = (sys.argv[1] if len(sys.argv) > 1 else "farmwork").lower()
    if which == "farmwork":
        return part_farmwork()
    print("未知段：%s（可用 farmwork / day）" % which)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
