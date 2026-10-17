r"""task-200 / task-198 NIT 复核：inventory_blocked 日 `_leftover` / `no_unmet_stages` 是否如实。

问题：背包满、地里还有熟作物时，harvest 阶段的 leftover 会不会被静默清掉 ⇒
`checks.no_unmet_stages` 被洗成 True。只读探针，产物落 scratch/。
用法：& $py scratch\_t200_198_nit.py   （T200_ROOT 默认 scratch\_t200_post198）
"""
from __future__ import annotations

import os
import pathlib
import sys

ROOT = pathlib.Path(os.environ.get("T200_ROOT") or
                     (pathlib.Path(__file__).resolve().parent / "_t200_post198")).resolve()
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "brain"))
sys.path.insert(0, str(ROOT / "tests"))

import importlib.util  # noqa: E402

spec = importlib.util.spec_from_file_location(
    "p200", pathlib.Path(__file__).resolve().parent / "_t200_probe.py")
P = importlib.util.module_from_spec(spec)
spec.loader.exec_module(P)                                              # noqa: E402


def show(tag: str, w, day, tiles) -> None:
    stages = list(getattr(day, "stages", []) or [])
    print(f"\n--- {tag} ---")
    print(f"  ended_by={getattr(day, 'ended_by', None)!r} reason={str(getattr(day, 'ended_reason', ''))[:140]!r}")
    print(f"  verified={getattr(day, 'verified', None)} checks={getattr(day, 'checks', None)}")
    print(f"  failed_steps={getattr(day, 'failed_steps', None)} ok_steps={getattr(day, 'ok_steps', None)}")
    print("  stages=" + str([(s.get("stage"), s.get("assigned"), s.get("assigned_undone"),
                             s.get("leftover"), s.get("stopped"), s.get("failed"), s.get("env_block"))
                            for s in stages]))
    plot = {"zone": "", "label": "", "anchor": list(tiles[0]) if tiles else [0, 0],
            "tiles": [list(t) for t in tiles], "note": ""}
    print(f"  _leftover(harvest, 全部片地格)={P.LR.LongRun._leftover(P.RUN_REF, 'harvest', w.obs(), plot)}")
    print(f"  farm.readyCrops={((w.obs().get('farm') or {}).get('readyCrops'))}")


def main() -> int:
    # N1：满包 + 8 熟作物 + 可腾（slot_relief 生效）
    w1, tiles1 = P._ripe_world(free_slots=0, material=1, n_ripe=8)
    run1, _, _ = P._mk(w1, "198nit-relief")
    run1.run()
    day = P._day(run1)
    P.RUN_REF = run1
    show("N1 满包+可腾", w1, day, tiles1)

    # N2：满包 + 8 熟作物 + 腾不出（inventory_blocked 收尾）
    w2, tiles2 = P._ripe_world(free_slots=0, n_ripe=8)
    run2, _, _ = P._mk(w2, "198nit-blocked")
    run2.run()
    day2 = P._day(run2)
    P.RUN_REF = run2
    show("N2 满包+腾不出", w2, day2, tiles2)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
