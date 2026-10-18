"""task-244：task-242（clear_area 逐格证据记账完整性）独立对抗验收探针。

用法（切换树）：
    $env:T244_ROOT = "<tree>"; python scratch/_t244_probe.py [--only A,B,C,D,E] [--readings]

- 默认 ROOT = 本仓库（worktree 只作线索）；正式判定用 `git archive <0.7.43 冻结提交>` 的树。
- 只读生产代码；日志/输出只写 stdout（由调用方 Tee 到 scratch/）。
"""

from __future__ import annotations

import argparse
import glob
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(os.environ.get("T244_ROOT") or Path(__file__).resolve().parents[1])
PY = sys.executable
PASS = FAIL = SKIP = INFO = 0
FAILS: list[str] = []
INFOS: list[str] = []


def check(tag: str, ok: bool, detail: str = "") -> bool:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  PASS  {tag}" + (f" :: {detail}" if detail else ""))
    else:
        FAIL += 1
        FAILS.append(tag)
        print(f"  FAIL  {tag}" + (f" :: {detail}" if detail else ""))
    return ok


def info(tag: str, detail: str = "") -> None:
    global INFO
    INFO += 1
    INFOS.append(tag)
    print(f"  INFO  {tag}" + (f" :: {detail}" if detail else ""))


def skip(tag: str, detail: str = "") -> None:
    global SKIP
    SKIP += 1
    print(f"  SKIP  {tag}" + (f" :: {detail}" if detail else ""))


def read(rel: str) -> str:
    p = ROOT / rel
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def sh(argv: list[str], *, cwd: Path | None = None, timeout: int = 900) -> tuple[int, str]:
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    try:
        r = subprocess.run(argv, cwd=str(cwd or ROOT), capture_output=True, text=True,
                           timeout=timeout, env=env)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception as exc:  # noqa: BLE001
        return 99, f"{type(exc).__name__}: {exc}"


# ---------------------------------------------------------------- 判据（我方独立实现）

def explainable(stage: dict) -> int:
    """账本里能解释「ok 但不在 cleared_tiles」的显式字段之和（新字段由 task-242 定名）。"""
    total = 0
    for key in ("unclear_steps", "kind_unchanged_steps", "cleared_unclear",
                "no_kind_change_steps", "collateral_steps"):
        try:
            total += int(stage.get(key) or 0)
        except (TypeError, ValueError):
            pass
    return total


def judge_stage(stage: dict) -> list[str]:
    """对一条 clear_area 阶段记录做逐格证据完整性判定（返回违规列表；空=绿）。

    规则（卡面语义，允许"目标格 + 连带格"显式区分，不允许静默丢 ok）：
    1) 不得有 ok 步静默缺失：`ok > len(cleared_tiles) + explainable` ⇒ 违规；
    2) 落进清单的格必须真的对应 ok 证据：`len(cleared_tiles) > ok + collateral` ⇒ 违规；
    3) 清单里的格必须属于该阶段分下去的格（或显式 collateral_tiles）：越界 ⇒ 违规。
    """
    v: list[str] = []
    ok = int(stage.get("ok") or 0)
    cleared = [tuple(t) for t in (stage.get("cleared_tiles") or [])]
    collateral = [tuple(t) for t in (stage.get("collateral_tiles") or [])]
    explained = explainable(stage)
    if ok > len(cleared) + explained:
        v.append(f"ok={ok} > cleared={len(cleared)} + explained={explained}（有 ok 步没有逐格证据）")
    if len(cleared) > ok + len(collateral):
        v.append(f"cleared={len(cleared)} > ok={ok} + collateral={len(collateral)}（清单多出未 ok 的格）")
    assigned = {tuple(t) for t in (stage.get("tiles_list") or [])}
    if assigned:
        outside = [t for t in cleared if t not in assigned and t not in set(collateral)]
        if outside:
            v.append(f"清单格不在阶段 tiles 内: {outside[:6]}")
    return v


def judge_ledger_stage(stage: dict) -> list[str]:
    """同 judge_stage，但用真账本的键名（ok/cleared_tiles/…）。"""
    return judge_stage(stage)


# ---------------------------------------------------------------- A 段

def case_a(readings: bool) -> None:
    print("== A 段：范围 / 越界 / 版本 / 读数 ==")
    files = ["brain/agentfarm/longrun.py", "brain/agentfarm/farmwork.py", "tests/test_longrun.py"]
    check("A1 关键文件在树内", all((ROOT / f).exists() for f in files), str(ROOT))
    ver_manifest = read("mod/AgentFarm.Bridge/manifest.json")
    bridge = read("brain/agentfarm/bridge.py")
    info("A2 版本", f"manifest={'0.7.42' if '0.7.42' in ver_manifest else '?'} "
                    f"bridge={'0.7.42' if '0.7.42' in bridge else '?'}")
    new_fields = [k for k in ("unclear_steps", "cleared_unclear", "collateral_tiles",
                              "no_kind_change_steps") if f'"{k}":' in read("brain/agentfarm/longrun.py")]
    info("A3 task-242 新字段（只许新增、须单列）", new_fields or "（尚未交付/无新账本字段）")
    if not readings:
        skip("A4 读数", "加 --readings 才跑（py_compile / 定向 / 全量 / build）")
        return
    rc, out = sh([PY, "-W", "error::SyntaxWarning", "-m", "py_compile",
                  "brain/agentfarm/longrun.py", "brain/agentfarm/farmwork.py",
                  "brain/agentfarm/planner.py", "brain/agentfarm/bridge.py"])
    check("A4a py_compile -W error::SyntaxWarning", rc == 0, f"rc={rc}")
    rc, out = sh([PY, "-m", "unittest", "tests.test_farmwork", "tests.test_longrun",
                  "tests.test_planner"])
    ran = [ln for ln in out.splitlines() if ln.startswith("Ran ") or ln.strip() == "OK"]
    check("A4b 定向单测（以 Ran N / OK 为准）", "OK" in out and "FAILED" not in out, " | ".join(ran[-2:]))
    rc, out = sh([PY, "-m", "unittest", "discover", "-s", "tests"])
    red = out.count("\nFAIL:") + out.count("\nERROR:")
    check("A4c 全量单测（0 红）", "OK" in out and red == 0,
          f"{[ln for ln in out.splitlines() if ln.startswith('Ran ')][-1:]}")


# ---------------------------------------------------------------- B 段

def case_b() -> None:
    print("== B 段：根因（0742 账本复现）/ 修法覆盖 / 语义未动 ==")
    journal = Path("logs/longrun-smoke-0742.jsonl")
    rows: list[tuple[int, dict]] = []
    for cand in (ROOT / journal, Path(__file__).resolve().parents[1] / journal):
        if cand.exists():
            for i, line in enumerate(cand.read_text(encoding="utf-8").splitlines(), 1):
                if line.strip():
                    try:
                        rows.append((i, json.loads(line)))
                    except json.JSONDecodeError:
                        pass
            info("B0 夹具来源", str(cand))
            break
    if not rows:
        skip("B1 0742 账本复现（9 阶段 ok≠cleared）", "logs/longrun-smoke-0742.jsonl 缺失")
    else:
        mism: list[dict] = []
        for i, r in rows:
            if r.get("event") != "day_end":
                continue
            for st in r.get("stages") or []:
                if st.get("stage") != "clear_area":
                    continue
                ok = st.get("ok")
                cleared = st.get("cleared_tiles")
                if isinstance(ok, int) and isinstance(cleared, (list, type(None))) and ok != len(cleared or []):
                    mism.append({"line": i, "day": st.get("day"), "ok": ok,
                                 "cleared": len(cleared or []), "diff": ok - len(cleared or []),
                                 "failed": st.get("failed")})
        total_ok = sum(m["ok"] for m in mism)
        total_cleared = sum(m["cleared"] for m in mism)
        check("B1 0742 账本复现（修前红；修后应被新字段解释或为 0）",
              len(mism) > 0,
              f"mismatch={len(mism)} ok={total_ok} cleared={total_cleared} diff={total_ok - total_cleared} "
              f"样例行={mism[:2]}")
        if mism:
            info("B1b 复现的 9 阶段形状", json.dumps(mism, ensure_ascii=False)[:400])

    # B2/B3：用真代码跑一个 clear_area 阶段（FakeWorker 真的改世界）
    try:
        sys.path.insert(0, str(ROOT / "tests"))
        sys.path.insert(0, str(ROOT / "brain"))
        sys.path.insert(0, str(ROOT))
        import test_longrun as TL  # noqa: N813
        from agentfarm import farmwork as FW  # noqa: F401
        from agentfarm import longrun as LR  # noqa: F401
    except Exception as exc:  # noqa: BLE001
        skip("B2 假世界阶段复现", f"夹具 import 失败: {exc}")
        return

    def run_clear(worker_factory=None):
        world = TL.FakeWorld(seeds=0, money=0, weeds=0, water_left=40)
        tiles = [(60 + i, 10) for i in range(4)]
        for t in tiles:
            world.blockers[t] = "weed"
        client = TL.FakeClient(world)
        worker = (worker_factory or (lambda c: FW.FarmWorker(c, log=lambda *_: None,
                                                             pause=lambda _s: None)))(client)
        run = TL.make_run(world, client_factory=lambda: client,
                          worker_factory=lambda c: worker)
        run.worker = worker
        run.client = client
        obs = world.obs()
        plot = {"zone": "field_se", "label": "field_se", "anchor": list(tiles[0]),
                "tiles": [list(t) for t in tiles]}
        rep = TL.DayReport(day_key=("spring", 1, 9), started_at=0.0)
        run._step_stage("clear_area", obs, plot, rep)
        return [s for s in rep.stages if s.get("stage") == "clear_area"][-1]

    if not hasattr(TL, "FakeWorld"):
        skip("B2 假世界阶段复现", "夹具缺 FakeWorld")
        return
    stage = run_clear()
    ok = int(stage.get("ok") or 0)
    cleared = len(stage.get("cleared_tiles") or [])
    check("B2 普通清障阶段：ok 与逐格清单一致（修后必须 ok == cleared + explainable）",
          ok == cleared + explainable(stage), f"ok={ok} cleared={cleared} explained={explainable(stage)}")

    class LyingWorker(FW.FarmWorker):
        """(62,10) 回执 ok 但 after 里没有 kind 证据（模拟观测/桥给不出 kind 变化）。"""

        def clear(self, tile, *, cut_grass=True):  # noqa: ANN001
            res = super().clear(tile, cut_grass=cut_grass)
            if tuple(tile) == (62, 10):
                res.after = {"no_kind_evidence": True}
            return res

    stage2 = run_clear(lambda c: LyingWorker(c, log=lambda *_: None, pause=lambda _s: None))
    ok2 = int(stage2.get("ok") or 0)
    cleared2 = len(stage2.get("cleared_tiles") or [])
    explained2 = explainable(stage2)
    if ok2 > cleared2 + explained2:
        check("B3 ok 但无 kind 变化的格必须被显式解释（新字段），不许静默丢",
              False, f"ok={ok2} cleared={cleared2} explained={explained2}（修前即此形态）")
    else:
        check("B3 ok 但无 kind 变化的格必须被显式解释（新字段），不许静默丢", True,
              f"ok={ok2} cleared={cleared2} explained={explained2}")

    # B4：语义未动（checks 键集 / 事件名 / assigned_undone / plot_pending）
    base_checks = {"crops_watered", "day_justified", "no_blocking_modal", "no_hard_failures",
                   "no_unmet_stages", "refused_within_bound", "slept_by_us",
                   "unreachable_within_bound", "watered_outdoor", "zero_action_evidenced"}
    de = next((r for _, r in rows if r.get("event") == "day_end"), None) or {}
    if de:
        cur = set(de.get("checks") or {})
        check("B4 0742 账本 checks 键集 = 10 键基线", cur == base_checks, f"{sorted(cur - base_checks)} / {sorted(base_checks - cur)}")
    st_keys = set(stage.keys())
    info("B4b 阶段记录键集（新字段请单列）", sorted(st_keys - {
        "stage", "tiles", "ok", "skipped", "failed", "failed_any", "proven_inert",
        "env_block", "inconclusive", "unreachable", "unreachable_tiles", "unreachable_leftover",
        "refused", "refused_tiles", "refused_leftover", "encircled", "encircled_tiles",
        "encircled_leftover", "attempted", "requested_tiles", "ok_tiles", "failed_tiles",
        "unexecuted_tiles", "reasons", "bound_basis", "encircled_tried", "engaged", "stopped",
        "leftover", "cleared_tiles", "blocker_drop", "assigned", "assigned_undone",
        "stamina_after", "stamina_before", "stamina_spent"}))


# ---------------------------------------------------------------- C 段：四把伪造

def case_c() -> None:
    print("== C 段：四把伪造（伪造阶段记录 → 期望判红/判绿） ==")
    base = {"stage": "clear_area", "ok": 4, "failed": 0, "cleared_tiles": [[60, 10], [61, 10], [62, 10], [63, 10]],
            "tiles_list": [[60, 10], [61, 10], [62, 10], [63, 10]], "ok_tiles": 4}
    cases = [
        ("C1 漏记一个 ok 格（ok=4 / cleared=3）",
         {**base, "cleared_tiles": [[60, 10], [61, 10], [62, 10]]}, True),
        ("C2 连带清多格只记目标格（ok=1 / cleared=2 无 collateral 解释）",
         {**base, "ok": 1, "ok_tiles": 1, "cleared_tiles": [[60, 10], [61, 10]]}, True),
        ("C2b 同 C2 但显式记 collateral ⇒ 可解释（绿）",
         {**base, "ok": 1, "ok_tiles": 1, "cleared_tiles": [[60, 10]],
          "collateral_tiles": [[61, 10]]}, False),
        ("C3 清单多出未 ok 的格（ok=3 / cleared=4）",
         {**base, "ok": 3, "ok_tiles": 3, "cleared_tiles": [[60, 10], [61, 10], [62, 10], [63, 10]]}, True),
        ("C4 len==ok 但格子不在阶段 tiles 内（[70,20] 越界）",
         {**base, "cleared_tiles": [[60, 10], [61, 10], [70, 20], [63, 10]]}, True),
    ]
    for tag, stage, want_red in cases:
        v = judge_stage(stage)
        got_red = bool(v)
        check(tag, got_red == want_red, ("违规=" + "; ".join(v)[:160]) if got_red else "绿（可解释）")


# ---------------------------------------------------------------- D 段

def case_d() -> None:
    print("== D 段：变异实测 ==")
    author = sorted(glob.glob(str(ROOT / "scratch/_t242_*mutate*.py"))) + \
             sorted(glob.glob(str(ROOT / "scratch/*_t242_*mutate*.py")))
    author = [Path(p).name for p in author]
    if author:
        info("D0 作者变异脚本", author)
    else:
        skip("D0 作者变异脚本", "未找到（GAP：作者自报杀数不可复跑）")
    mine = ROOT / "scratch/_t244_mutate.py"
    if mine.exists():
        info("D1 自建变异脚本", "scratch/_t244_mutate.py（--base <树> --all）")
    else:
        skip("D1 自建变异脚本", "骨架待补")
    info("D2 复跑命令", "python scratch/_t244_mutate.py --base <tree> --all（冻结树）")


# ---------------------------------------------------------------- E 段

def case_e() -> None:
    print("== E 段：结论 ==")
    if FAIL == 0:
        info("E1", "A/B/C/D 全绿 ⇒ 0.7.43 可以放行 A″/B″（本骨架待冻结树正式读数）")
    else:
        info("E1", f"仍有 {FAIL} 条红（{FAILS[:5]}）⇒ 需修复/解释后才放行；冻结树正式判定以报告为准")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="A,B,C,D,E")
    ap.add_argument("--readings", action="store_true")
    args = ap.parse_args()
    only = {x.strip() for x in args.only.split(",") if x.strip()}
    t0 = time.time()
    print(f"ROOT={ROOT} only={sorted(only)} py={PY}")
    for key, fn in (("A", lambda: case_a(args.readings)), ("B", case_b), ("C", case_c),
                    ("D", case_d), ("E", case_e)):
        if key not in only:
            continue
        try:
            fn()
        except Exception as exc:  # noqa: BLE001 - 在制工作树可能半截，别把探针自己炸掉
            check(f"{key} 段执行异常（树可能半截/在制）", False, f"{type(exc).__name__}: {exc}")
    print(f"\n汇总：PASS={PASS} FAIL={FAIL} SKIP={SKIP} INFO={INFO}  ({time.time() - t0:.1f}s)")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
