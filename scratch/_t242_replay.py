"""task-242 离线重放：把 0.7.42 冒烟账本里 9 个 ok≠cleared 的 clear_area 阶段，
按它们自己的数字（engaged = 真变化格数，ok - engaged = already 步数）重放一遍
`LongRun._step_stage` 的记账路径，打印修后是否全部 conforming。

用法：PYTHONUTF8=1 PYTHONPATH=<repo>/brain python scratch/_t242_replay.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "brain"))
sys.path.insert(0, str(REPO))

from agentfarm.farmwork import StepResult  # noqa: E402
from agentfarm.longrun import DayReport  # noqa: E402
from tests.test_longrun import (FakeClient, FakeWorld, FakeWorker,  # noqa: E402
                                make_run)

LEDGER = REPO / "logs" / "longrun-smoke-0742.jsonl"


class _MixedClearWorker(FakeWorker):
    def __init__(self, world, *, n_real):
        super().__init__(world, log=lambda *_: None)
        self.n_real = n_real

    def run_stage(self, stage, tiles, *, min_stamina=12.0, max_steps=200):
        from agentfarm.farmwork import StageResult

        res = StageResult(stage=stage, tiles=list(tiles))
        for i, tile in enumerate(tiles):
            t = (int(tile[0]), int(tile[1]))
            if i < self.n_real:
                st = StepResult(action="clear", tile=t, ok=True, code="ok", reason="清掉了",
                                before={"kind": "weed"},
                                after={"kind": "none", "kind_after": "none", "cleared": True})
            else:
                st = StepResult(action="clear", tile=t, ok=True, code="already",
                                reason="本来就没障碍")
            res.steps.append(st)
        return res


def main() -> int:
    if not LEDGER.exists():
        print(f"账本不在：{LEDGER} ⇒ 无法判定（不当 PASS）")
        return 2
    rows = []
    for line in LEDGER.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    stages = [st for r in rows if r.get("event") == "day_end"
              for st in (r.get("stages") or [])
              if st.get("stage") == "clear_area"
              and int(st.get("ok") or 0) != len(st.get("cleared_tiles") or [])]
    print(f"账本里 ok≠cleared 的 clear_area 阶段：{len(stages)}")
    all_tiles = [(60 + i, 10 + j) for j in range(5) for i in range(5)]
    bad = 0
    for n, st in enumerate(stages, 1):
        ok_old = int(st.get("ok") or 0)
        engaged = int(st.get("engaged") or 0)
        cleared = [tuple(t) for t in (st.get("cleared_tiles") or [])]
        delta = ok_old - engaged
        need = len(cleared) + delta
        coords = all_tiles[:need]
        w = FakeWorld(weeds=0, seeds=0, money=0)
        for t in coords:
            w.blockers[(int(t[0]), int(t[1]))] = "weed"
        run = make_run(w)
        run.client = FakeClient(w)
        run.worker = _MixedClearWorker(w, n_real=len(cleared))
        rep = DayReport(day_key=("spring", 1, 9), started_at=0.0)
        run._step_stage("clear_area", w.obs(),
                        {"anchor": list(coords[0]), "tiles": [list(t) for t in coords],
                         "zone": "", "label": "", "size": 5}, rep)
        stage = rep.stages[-1]
        conforming = (stage["ok"] == len(stage["cleared_tiles"]) == len(cleared)
                      and stage["already"] == delta and stage["unclear"] == 0)
        if not conforming:
            bad += 1
        print(f"  #{n}: 旧 ok={ok_old} cleared={len(cleared)} engaged={engaged} "
              f"Δ={delta} ⇒ 新 ok={stage['ok']} cleared={len(stage['cleared_tiles'])} "
              f"already={stage['already']} unclear={stage['unclear']} "
              f"{'conforming' if conforming else 'FAIL'}")
    print(f"结论：{len(stages) - bad}/{len(stages)} conforming，FAIL={bad}")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
