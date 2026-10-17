r"""task-185 骨架 v2：task-168「规模取舍（`reduce_scope` / `scope_shed`）」的独立对抗验收探针。

**状态：骨架（未验收）** —— task-168 交付 + Lead reassign 后正式跑三棵树并写报告。
只写 `scratch/`；生产代码只读。

五组通道（含 Lead 点名的三条 + 我补的正对照/有界/释放）：
  * **C-a 认输区被当成已浇**：shed 格不许进 `watered_outdoor` 的"已浇"、不许让 `final_water.dry` 变小。
  * **C-b `scope_shed` 变免罚额度**：`_leftover` 一字不改、不许从 `assigned_undone`/`unmet_leftover`
    静默扣减、不许与 `unreachable`/`refused`/延后重复扣减；`_shed_live_crops()` 只在
    `live_crops_at_shed` 是 int 时扣（记不清 ⇒ 0 ⇒ 不扣）。
  * **C-c 用认输洗白**：认输当天不得 `verified=true`；`checks` 不许新增可被写成 true 的键。
  * **P 正对照**：`deficit == 0` ⇒ `scope_shed_refused{no_deficit}`，不许 shed。
  * **B 有界性**：一天 ≤1 区、累计 ≤34%、同秒不许空转。
  * **R 释放**：`_release_scope_if_converged` 在两个条件（区内无未浇活苗 / 全农场 deficit==0）
    下必须撤销认输（`scope_released` + 重新进目标池）；判不了 ⇒ 粘住（fail-closed）。
  * **X 跨进程/文件**：`_scope_load` 后累计计数是否漏计（34% 上界是否只在单进程内成立）。

用法：
    $env:T185_ROOT = "<树>"                  # 缺省 = 本仓库工作树
    & $py scratch\_t185_probe.py                      # 全跑
    & $py scratch\_t185_probe.py --list
    & $py scratch\_t185_probe.py --case A2
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(os.environ.get("T185_ROOT") or Path(__file__).resolve().parents[1])
for _p in (ROOT, ROOT / "brain", ROOT / "tests"):
    sys.path.insert(0, str(_p))

import test_longrun as TL                        # noqa: E402
import agentfarm.longrun as LR                   # noqa: E402
import agentfarm.planner as PL                   # noqa: E402
import agentfarm.farmwork as FW                  # noqa: E402

WORKSPACE = Path(__file__).resolve().parents[1]
JOURNALS = WORKSPACE / "scratch" / "_t185_j"        # 产物永远落在真仓库 scratch/，不污染快照树
PASS = 0
FAIL = 0
SKIP = 0
FINDINGS: list[str] = []


def check(tag: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
        print(f"  ok   {tag}")
    else:
        FAIL += 1
        print(f"  FAIL {tag}  :: {detail}")


def finding(tag: str, reproduced: bool, detail: str = "") -> None:
    if reproduced:
        FINDINGS.append(tag)
        print(f"  发现 {tag}  :: {detail}")
    else:
        print(f"  （未复现）{tag}  :: {detail}")


def info(tag: str, detail: str = "") -> None:
    print(f"  info {tag}  :: {detail}")


def skip(tag: str, why: str) -> None:
    global SKIP
    SKIP += 1
    print(f"  SKIP {tag}  :: {why}")


# ───────────────────────── task-168 特性探测 / API 适配层 ─────────────────────────
def has_168() -> bool:
    return ("scope_shed" in getattr(LR.DayReport, "__dataclass_fields__", {})
            or hasattr(LR, "SCOPE_SHED_MAX_PER_DAY"))


def api() -> dict:
    """task-168 的私有接口集中在此 —— 交付时若改名，只改这一处。"""
    return {
        "shed_one": getattr(LR.LongRun, "_shed_scope", None),
        "shed_tiles": getattr(LR.LongRun, "_shed_tile_set", None),
        "shed_live": getattr(LR.LongRun, "_shed_live_crops", None),
        "release": getattr(LR.LongRun, "_release_scope_if_converged", None),
        "scope_load": getattr(LR.LongRun, "_scope_load", None),
        "budget_facts": getattr(LR.LongRun, "_work_budget_facts", None),
        "zone_live": getattr(LR.LongRun, "_zone_live_crops", None),
        "zones": getattr(LR.LongRun, "_zones", None),
        "max_per_day": getattr(LR, "SCOPE_SHED_MAX_PER_DAY", None),
        "max_fraction": getattr(LR, "SCOPE_SHED_MAX_FRACTION", None),
        "brief_fields": set(getattr(PL.Brief, "__dataclass_fields__", {})),
        "plan": getattr(PL, "deterministic_plan", None),
    }


# ───────────────────────────────── 夹具 ─────────────────────────────────
def world(crops: int = 200, *, water_left: int = 40, seeds: int = 0, money: int = 0,
          weeds: int = 0, revealed: bool = True):
    """`DryTilesWorld`：`crops` 个未浇活苗铺成 20 列网格（farm 块按真实作物现算）。"""
    w = TL.DryTilesWorld(seeds=seeds, money=money, weeds=weeds, water_left=water_left,
                         with_dry_tiles=True)
    tiles = [(60 + i % 20, 10 + i // 20) for i in range(int(crops))]
    w.dirt |= set(tiles)
    for t in tiles:
        w.crops[t] = {"watered": False, "ripe": False, "dead": False}
    w.player_tile = [60, 12]
    w.location = "Farm"
    w.is_outdoor_farm = True
    if revealed:
        w.revealed = True                       # MyopicWorld 的逃逸口：让整农场进观测（否则半径 3）
    return w


class NoFarmWorld(TL.DryTilesWorld):
    """farm 计数不可用（`complete=false` / 整块缺失）——`DryTilesWorld.obs()` 会重算 farm，故须覆盖。"""

    def __init__(self, *a, mode: str = "incomplete", **kw):
        super().__init__(*a, **kw)
        self._mode = mode

    def obs(self):
        o = super().obs()
        if self._mode == "missing":
            o.pop("farm", None)
        else:
            o["farm"] = {"loaded": True, "complete": False, "crops": None, "dryCrops": None}
        return o


def plot(zone, tiles):
    return {"zone": zone, "label": zone, "anchor": list(tiles[0]),
            "tiles": [list(t) for t in tiles], "note": ""}


def mk(w, *, llm=False, journal=None, zone_split=2, **kw):
    kw.setdefault("target_days", 1)
    kw.setdefault("max_days", 1)
    kw.setdefault("zone_split", zone_split)
    kw.setdefault("llm_enabled", bool(llm))
    if journal is not None:
        JOURNALS.mkdir(parents=True, exist_ok=True)
        kw.setdefault("journal_path", str(journal))
    return TL.make_run(w, **kw)


def zones(run, obs) -> list:
    return list(run._zones(obs)) if run._zones(obs) else []


def zone_names(run, obs) -> list[str]:
    return [str(z.name) for z in zones(run, obs)]


def events(run, name: str) -> list[dict]:
    return [e for e in run.entries if e.get("event") == name]


def rep_for(day: int = 10) -> LR.DayReport:
    return LR.DayReport(day_key=("summer", day, 1), started_at=0.0)


def tool_run(journal: Path, *, days: int = 1) -> tuple[int, str]:
    """工具侧必须走 **CLI**（进程内 load/build_days/report 会给真账本也返回 problems=[]）。"""
    tool = ROOT / "tools" / "verify-run3.py"
    if not tool.exists():
        tool = WORKSPACE / "tools" / "verify-run3.py"
    if not tool.exists():
        return -1, "no tool"
    proc = subprocess.run([sys.executable, str(tool), "--journal", str(journal),
                           "--days", str(days)],
                          cwd=str(ROOT), capture_output=True, text=True, timeout=600)
    return proc.returncode, (proc.stdout or "") + (proc.stderr or "")


def forge(src: Path, dst: Path, *, patch_day_end: dict | None = None,
          drop_events: tuple[str, ...] = (), add_events: list[dict] | None = None,
          which: str = "all") -> Path:
    """拿一本真账本改 day_end 字段 / 删事件 / 插事件（工具侧伪造通道）。

    `which`：`all` / `first` / `last` —— 改哪一天的 day_end。
    `add_events` 插在该日 day_end **之前**（`scope_shed` 事件要与该日同 session 才被认）。
    """
    rows = [json.loads(ln) for ln in src.read_text(encoding="utf-8").splitlines() if ln.strip()]
    idx = [i for i, r in enumerate(rows) if r.get("event") == "day_end"]
    target = None
    if (patch_day_end or add_events) and idx:
        target = {"all": None, "first": idx[0], "last": idx[-1]}[which]
    out: list[dict] = []
    for i, r in enumerate(rows):
        if r.get("event") in drop_events:
            continue
        if r.get("event") == "day_end":
            hit = bool(patch_day_end or add_events) and (target is None or i == target)
            if hit:
                if add_events:
                    pos = len(out)
                    out[pos:pos] = add_events
                if patch_day_end:
                    r.update(patch_day_end)
        out.append(r)
    dst.parent.mkdir(parents=True, exist_ok=True)
    dst.write_text("\n".join(json.dumps(r, ensure_ascii=False) for r in out) + "\n",
                   encoding="utf-8")
    return dst


def _shed_setup(crops: int = 200, *, zone_split: int = 2, water_left: int = 40,
                tag: str = "s"):
    """造一个"一天浇不完"的世界，返回 (world, run, obs, 第一个区名, 该区观测格数)。"""
    w = world(crops, water_left=water_left)
    run = mk(w, journal=JOURNALS / f"{tag}.jsonl", zone_split=zone_split)
    obs = w.obs()
    names = zone_names(run, obs)
    assert names, "夹具没造出田区（观测里看不到可作业格）"
    z0 = names[0]
    return w, run, obs, z0, len(run._zone_observed_tiles(z0, obs))


# ───────────────────────────────── 用例 ─────────────────────────────────
def case_P1() -> None:
    """正对照：deficit == 0（作物少）⇒ 不许 shed，拒绝理由 no_deficit。"""
    print("== P1 正对照：deficit=0 不许认输 ==")
    A = api()
    if A["shed_one"] is None:
        return skip("P1", "task-168 未交付（没有 _shed_scope）")
    w = world(3)
    run = mk(w, journal=JOURNALS / "p1.jsonl")
    rep = rep_for()
    ok = run._shed_scope(zone_names(run, w.obs())[0] if zone_names(run, w.obs()) else "field_nw",
                         w.obs(), rep)
    check("P1 deficit=0 ⇒ shed 被拒", ok is False, f"ok={ok}")
    ref = events(run, "scope_shed_refused")
    check("P1 拒绝理由 = no_deficit",
          bool(ref) and ref[-1].get("reason") == "no_deficit", str(ref[-1:] if ref else []))
    check("P1 不写 scope_shed 事件", not events(run, "scope_shed"), str(events(run, "scope_shed")))
    check("P1 rep.scope_shed 空", not rep.scope_shed and rep.scope_shed_tiles == 0,
          f"{rep.scope_shed} {rep.scope_shed_tiles}")


def case_A2() -> None:
    """卡面验收①：活苗 200 / 容量 129（缺口 71）⇒ 允许认输 1 个区并如实留痕。"""
    print("== A2 卡面验收①：缺口语境下认输 ==")
    A = api()
    if A["shed_one"] is None:
        return skip("A2", "task-168 未交付")
    w, run, obs, z0, ztiles = _shed_setup(200, tag="a2")
    rep = rep_for()
    live, cap, deficit = run._work_budget_facts(obs)
    info("A2 预算", f"live={live} cap={cap} deficit={deficit} zone={z0} tiles={ztiles}")
    ok = run._shed_scope(z0, obs, rep)
    check("A2 有缺口 ⇒ 允许认输", bool(ok), f"ok={ok} refused={events(run, 'scope_shed_refused')}")
    sh = events(run, "scope_shed")
    check("A2 journal scope_shed 有 zone/tiles/reason",
          bool(sh) and all(k in sh[-1] for k in ("zone", "tiles", "reason", "deficit")),
          str(sh[-1:] if sh else []))
    snap = rep.scope_shed if isinstance(rep.scope_shed, dict) else {}
    check("A2 day_end.scope_shed 是当次认输快照（zone/tiles/reason/live_crops/deficit/since_day）",
          snap.get("zone") == z0 and all(k in snap for k in ("zone", "tiles", "reason", "live_crops",
                                                            "deficit", "since_day")),
          str(snap))
    check("A2 认输格数 = 该区观测格数",
          rep.scope_shed_tiles == ztiles and int(snap.get("tiles") or 0) == ztiles,
          f"rep={rep.scope_shed_tiles} snap={snap.get('tiles')} zone={ztiles}")
    check("A2 认输格 ⊆ 目标池剔除集（_shed_tile_set）",
          len(run._shed_tile_set()) == ztiles, str(len(run._shed_tile_set())))
    dry = [t for t, v in w.crops.items() if not v.get("watered")]
    check("A2 shed 的格仍是干的（认输 ≠ 已浇）", len(dry) == len(w.crops),
          f"dry={len(dry)} crops={len(w.crops)}")


def case_A3() -> None:
    """C-a：认输区不许被算成"已浇"（`watered_outdoor` 必须 false 且 `final_water.dry > 0`）。"""
    print("== A3 C-a：认输区被当成已浇？==")
    A = api()
    if A["shed_one"] is None or not hasattr(LR.LongRun, "_water_evidence"):
        return skip("A3", "task-168 未交付 / 没有 _water_evidence")
    w, run, obs, z0, ztiles = _shed_setup(200, tag="a3")
    rep = rep_for()
    run._shed_scope(z0, obs, rep)
    watery, evidence = run._water_evidence(w.obs())
    check("A3 认输后 watered_outdoor=false（dry>0）", watery is False,
          f"watered_outdoor={watery} evidence={evidence}")
    check("A3 final_water.dry 不为 0", int((evidence or {}).get("dry") or 0) > 0, str(evidence))
    check("A3 认输不等于把 dryCrops 抹掉",
          int(((w.obs().get("farm") or {}).get("dryCrops")) or 0) >= ztiles,
          str((w.obs().get("farm") or {}).get("dryCrops")))


def case_A4() -> None:
    """C-b/C-c：`_leftover` 一字不改 + `checks` 不许出现可写成 true 的 scope 键。"""
    print("== A4 认输不动会计（_leftover / checks）==")
    A = api()
    if A["shed_one"] is None:
        return skip("A4", "task-168 未交付")
    w, run, obs, z0, ztiles = _shed_setup(200, tag="a4")
    rep = rep_for()
    pl = plot(z0, run._zone_observed_tiles(z0, obs))
    before = run._leftover("water_area", obs, pl)
    run._shed_scope(z0, obs, rep)
    after = run._leftover("water_area", obs, pl)
    check("A4 认输前后 _leftover 逐字相同（认输 ≠ 免罚额度）", before == after,
          f"before={len(before)} after={len(after)}")
    check("A4 认输格仍在 leftover 里", set(after) >= set(run._shed_tile_set()),
          f"leftover={len(after)} shed={len(run._shed_tile_set())}")
    check("A4 shed 不进 checks", not any("scope" in k or "shed" in k for k in (rep.checks or {})),
          str(list((rep.checks or {}).keys())))
    live_now = run._shed_live_crops()
    live_rec = sum(max(0, int(z.get("live_crops_at_shed") or 0)) for z in run.shed_zones.values()
                   if isinstance(z.get("live_crops_at_shed"), int)
                   and not isinstance(z.get("live_crops_at_shed"), bool))
    check("A4 `_shed_live_crops` = 认输记录里 live_crops_at_shed 之和（只认 int）",
          live_now == live_rec and live_now > 0, f"{live_now} vs {live_rec}")
    run.shed_zones[z0]["live_crops_at_shed"] = "unknown"
    check("A4 记录里 live_crops_at_shed 不是 int ⇒ 扣减归 0（不许凭认输抹掉『还有活』）",
          run._shed_live_crops() == 0, str(run._shed_live_crops()))


def case_B1() -> None:
    """有界性：一天只认输 1 个区；上界常量存在。"""
    print("== B1 有界性 ==")
    A = api()
    if A["shed_one"] is None:
        return skip("B1", "task-168 未交付")
    w, run, obs, z0, ztiles = _shed_setup(200, tag="b1")
    names = zone_names(run, obs)
    rep = rep_for()
    ok1 = run._shed_scope(names[0], obs, rep)
    ok2 = run._shed_scope(names[1], obs, rep)
    check("B1 第一个区可以认输", bool(ok1), f"ok1={ok1} refused={events(run, 'scope_shed_refused')[:1]}")
    check("B1 同一天第二个区被拒（already_today）",
          ok2 is False and any(e.get("reason") == "already_today"
                               for e in events(run, "scope_shed_refused")),
          str(events(run, "scope_shed_refused")[-2:]))
    check("B1 journal scope_shed 恰好 1 条", len(events(run, "scope_shed")) == 1,
          str(len(events(run, "scope_shed"))))
    check("B1 SCOPE_SHED_MAX_PER_DAY == 1", A["max_per_day"] == 1, str(A["max_per_day"]))
    check("B1 SCOPE_SHED_MAX_FRACTION ∈ (0,1)", isinstance(A["max_fraction"], float)
          and 0 < A["max_fraction"] < 1, str(A["max_fraction"]))


def case_B2() -> None:
    """累计上界：单区格数 > 34% 农场可作业格 ⇒ `refused{cap}`、如实不认输。"""
    print("== B2 累计 34% 上界 ==")
    A = api()
    if A["shed_one"] is None:
        return skip("B2", "task-168 未交付")
    # 200 格 + `zone_split=1` ⇒ 单区 200 格 > 34% 上界（0.34*200=68）
    w = world(200)
    run = mk(w, journal=JOURNALS / "b2.jsonl", zone_split=1)
    obs = w.obs()
    names = zone_names(run, obs)
    zt = len(run._zone_observed_tiles(names[0], obs)) if names else 0
    workable = len(run._farm_workable_tiles(obs))
    live, cap, deficit = run._work_budget_facts(obs)
    info("B2 规模", f"zones={names} zone_tiles={zt} workable={workable} "
                    f"cap={int(0.34 * workable)} live={live} capacity={cap} deficit={deficit}")
    check("B2 上界分母来自观测可作业格", workable > 0, f"workable={workable}")
    if names and zt > int(0.34 * workable):
        ok = run._shed_scope(names[0], obs, rep_for())
        check("B2 单区超 34% ⇒ 拒绝", ok is False, f"ok={ok}")
        check("B2 拒绝理由 = cap",
              any(e.get("reason") == "cap" for e in events(run, "scope_shed_refused")),
              str(events(run, "scope_shed_refused")[-1:]))
    else:
        info("B2 该规模下未触发 cap", f"zone={zt} cap={int(0.34 * workable)}（需缺口语境才可达）")


def case_A7() -> None:
    """无 farm 证据 / 不在农场 ⇒ 不许认输，且 deficit 不许当 0。"""
    print("== A7 没有 farm 证据时不许认输 ==")
    A = api()
    if A["shed_one"] is None:
        return skip("A7", "task-168 未交付")
    w = NoFarmWorld(seeds=0, money=0, weeds=0, water_left=40, with_dry_tiles=True,
                    mode="incomplete")
    tiles = [(60 + i % 20, 10 + i // 20) for i in range(200)]
    w.dirt |= set(tiles)
    for t in tiles:
        w.crops[t] = {"watered": False, "ripe": False, "dead": False}
    w.player_tile = [60, 12]
    w.location = "Farm"
    w.is_outdoor_farm = True
    w.revealed = True
    run = mk(w, journal=JOURNALS / "a7.jsonl")
    obs = w.obs()
    _live, _cap, deficit = run._work_budget_facts(obs)
    check("A7 farm 不可用 ⇒ deficit 必须是 None（不许当 0）", deficit is None,
          f"live={_live} cap={_cap} deficit={deficit}")
    names = zone_names(run, obs)
    ok = run._shed_scope(names[0] if names else "field_nw", obs, rep_for())
    check("A7 farm 不可用 ⇒ 拒绝认输", ok is False, f"ok={ok}")
    check("A7 拒绝理由 = no_farm_evidence",
          any(e.get("reason") == "no_farm_evidence" for e in events(run, "scope_shed_refused")),
          str(events(run, "scope_shed_refused")[-1:]))


def case_R1() -> None:
    """释放：区内活苗浇完（live==0）或全农场 deficit==0 ⇒ 撤销认输并写 scope_released。"""
    print("== R1 认输可释放（粘但可释放）==")
    A = api()
    if A["shed_one"] is None or A["release"] is None:
        return skip("R1", "task-168 未交付 / 没有 _release_scope_if_converged")
    w, run, obs, z0, ztiles = _shed_setup(200, tag="r1")
    rep = rep_for()
    run._shed_scope(z0, obs, rep)
    check("R1 认输先成立", z0 in run.shed_zones and bool(run._shed_tile_set()))
    # 让该区活苗全部消失（收完了）⇒ 必须释放
    bounds = run._zone_bounds(z0, obs)
    assert bounds, "夹具该区没有 bounds"
    x0, y0, x1, y1 = bounds
    for t in list(w.crops):
        if x0 <= t[0] <= x1 and y0 <= t[1] <= y1:
            w.crops[t]["watered"] = True
    obs2 = w.obs()
    run._release_scope_if_converged(obs2, rep)
    check("R1 区内无未浇活苗 ⇒ 撤销认输", z0 not in run.shed_zones, str(list(run.shed_zones)))
    check("R1 撤销后该区格不再被剔除", not (run._shed_tile_set() & set(run._zone_observed_tiles(z0, obs2))),
          str(sorted(run._shed_tile_set())[:5]))
    check("R1 写 scope_released",
          any(e.get("reason") == "zone_has_no_unwatered_crops" for e in events(run, "scope_released")),
          str(events(run, "scope_released")[-1:]))
    # NIT-1 证据：释放不改 day_end 快照 ⇒ 快照仍自称认输 N 格，而实时剔除集已空
    check("R1 释放后 day_end 快照仍自称认输（快照与实时状态不一致 = NIT-1）",
          int(rep.scope_shed_tiles) > 0 and not run._shed_tile_set(),
          f"rep.scope_shed_tiles={rep.scope_shed_tiles} live_shed={len(run._shed_tile_set())}")
    info("NIT-1（非阻塞，报 Lead）",
         "释放后 `rep.scope_shed_tiles` 不归零；工具对『scope_shed_tiles>0 + verified=true』判 problem "
         "⇒ 雨天「先认输、后来雨浇好了并释放」的诚实账本可能被误判；修法：释放时同步扣减快照，"
         "或工具侧把同日的 scope_released 认作对冲")


def case_X1() -> None:
    """跨进程：`_scope_load` 之后累计 34% 计数是否漏计（上界是否只在单进程内成立）。"""
    print("== X1 重启后累计上界是否仍成立 ==")
    A = api()
    if A["scope_load"] is None:
        return skip("X1", "task-168 未交付 / 没有 _scope_load")
    w, run, obs, z0, ztiles = _shed_setup(200, tag="x1")
    rep = rep_for()
    run._shed_scope(z0, obs, rep)
    path = getattr(run, "scope_path", None)
    check("X1 scope 文件已落盘", bool(path) and Path(path).exists(), str(path))
    if not path or not Path(path).exists():
        return
    on_disk = json.loads(Path(path).read_text(encoding="utf-8"))
    zones_raw = on_disk.get("zones") if isinstance(on_disk.get("zones"), dict) else {}
    disk_tiles = sum(int((v or {}).get("tiles") or 0) for v in zones_raw.values())
    fresh = mk(world(200), journal=JOURNALS / "x1b.jsonl")
    fresh.scope_path = Path(path)
    fresh._scope_load()
    loaded_tiles = sum(len(v) for v in fresh.shed_zone_tiles.values())
    info("X1 载入后的累计计数",
         f"shed_zone_tiles 合计={loaded_tiles} 文件自述 tiles 合计={disk_tiles} "
         f"载入区={sorted(fresh.shed_zones)}")
    check("X1 重启后 `shed_zone_tiles` 被灌回（不归零）",
          loaded_tiles == disk_tiles and loaded_tiles > 0,
          f"loaded={loaded_tiles} disk={disk_tiles}")
    check("X1 重启后 `shed_zones` 仍在（粘性记忆跨进程）", z0 in fresh.shed_zones,
          str(sorted(fresh.shed_zones)))
    # 上界跨进程仍成立：小农场 cap=68，已用 50 + 新 50 > 68 ⇒ 必须 refused{cap}
    obs2 = world(200).obs()
    names2 = zone_names(fresh, obs2)
    other = next((n for n in names2 if n != z0), None)
    if other is None:
        return info("X1 没有第二个区可试", str(names2))
    ok = fresh._shed_scope(other, obs2, rep_for(day=11))
    check("X1 重启后累计上界仍生效（已用 50 + 新 50 > 68 ⇒ 拒绝）", ok is False,
          f"ok={ok} refused={events(fresh, 'scope_shed_refused')[-1:]}")
    check("X1 拒绝理由 = cap",
          any(e.get("reason") == "cap" for e in events(fresh, "scope_shed_refused")),
          str(events(fresh, "scope_shed_refused")[-1:]))
    finding("F-X1 重启后 `shed_zone_tiles` 为空 ⇒ 34% 累计上界只在单进程内成立（已修则不复现）",
            loaded_tiles == 0 and disk_tiles > 0,
            f"loaded={loaded_tiles} disk={disk_tiles}")


def case_T1() -> None:
    """工具侧：新字段/事件是否被认（缺 ⇒ INFO/finding，不算 FAIL）。"""
    print("== T1 工具侧对 scope_shed 的认知（INFO）==")
    tool = ROOT / "tools" / "verify-run3.py"
    if not tool.exists():
        tool = WORKSPACE / "tools" / "verify-run3.py"
    tool = tool.read_text(encoding="utf-8")
    if "scope_shed" in tool:
        check("T1 tools/verify-run3.py 认 scope_shed（day_end 白名单）", True)
    else:
        info("T1 工具对 `scope_shed`/`scope_shed_tiles` 全盲",
             "既不核对留痕也不据此放宽 ⇒ 记 INFO（卡面要求口径变更报 Lead 转 analyzer 卡）")
    analyzer = (ROOT / "tools" / "analyze-longrun.py").read_text(encoding="utf-8")
    miss = [ev for ev in ("scope_shed", "scope_shed_refused", "scope_released", "scope_loaded",
                          "scope_saved", "scope_rejected", "scope_harvest")
            if ev not in analyzer]
    finding(f"F-T1 analyzer EVENT_BUCKETS 缺新事件 {miss}", bool(miss),
            "缺桶 ⇒ 全量会漂移红（task-165/160 同类）")


BASE_LEDGER = ROOT / "logs" / "longrun-3day-llm-run9c.jsonl"
if not BASE_LEDGER.exists():                     # 快照树不含 gitignore 的 logs/
    BASE_LEDGER = WORKSPACE / "logs" / "longrun-3day-llm-run9c.jsonl"


def case_A6() -> None:
    """免罚额度通道：认输后守卫仍要为**别的**活保留理由（不许对全农场闭嘴）。"""
    print("== A6 C-b：认输会不会让守卫对别处也闭嘴 ==")
    A = api()
    if A["shed_one"] is None:
        return skip("A6", "task-168 未交付")
    w, run, obs, z0, ztiles = _shed_setup(200, tag="a6")
    rep = rep_for()
    before = list(run.work_reasons(obs))
    run._shed_scope(z0, obs, rep)
    after = list(run.work_reasons(obs))
    info("A6 守卫理由", f"before={len(before)} after={len(after)} :: {after[:3]}")
    check("A6 认输后守卫仍为'还有活'保留理由（别处还有未浇活苗）", bool(after), f"after={after}")
    farm_reasons = [r for r in after
                    if "格作物没浇水" in r or "格耕地空着" in r or "干作物" in r]
    check("A6 农场级『还有 N 格活苗/耕地』理由仍在（认输只扣该区，不许一次扣光）",
          bool(farm_reasons), f"farm_reasons={farm_reasons} after={after}")
    check("A6 守卫与 unfinished 一致（不因认输把当天判没活）",
          bool(run._unfinished_work(obs)) == bool(after), f"after={after}")


def case_A6b() -> None:
    """C-b 深一层：人回室内后，farm 级干作物理由必须只扣认输区（1e9 变异杀手）。"""
    print("== A6b C-b：农场级理由只扣认输区、不许一次扣光 ==")
    A = api()
    if A["shed_one"] is None:
        return skip("A6b", "task-168 未交付")
    w, run, obs, z0, ztiles = _shed_setup(200, tag="a6b")
    rep = rep_for()
    run._shed_scope(z0, obs, rep)
    w.revealed = False                      # 回室内：窗口空，只剩 farm 级读数
    w.location = "FarmHouse"
    w.is_outdoor_farm = False
    w.player_tile = [5, 5]
    reasons = list(run.work_reasons(w.obs()))
    dry_reasons = [r for r in reasons if "格干作物" in r]
    info("A6b 室内守卫理由", f"{reasons}")
    check("A6b 人回室内后仍有 farm 级干作物理由（认输区之外还有 150 格没浇）",
          bool(dry_reasons), f"reasons={reasons}")
    check("A6b 理由里的格数 = farm 干作物 − 认输区活苗（150，不是 0）",
          any("150" in r for r in dry_reasons), f"dry_reasons={dry_reasons}")


def case_C2() -> None:
    """卡面 C③④⑤⑥⑦⑧：不许洗 `no_unmet_stages`、不许换名、不许跨 run 继承、不许藏观测、理由不许幻觉、多天不许自洽成 true。"""
    print("== C2 洗白面：no_unmet/换名/跨 run/观测/理由/多天 ==")
    A = api()
    if A["shed_one"] is None:
        return skip("C2", "task-168 未交付")
    # ④ 换名躲：认输不许被当成"主动收工"的理由
    justified = tuple(getattr(LR, "JUSTIFIED_END_REASONS", ()) or ())
    check("C2a `scope_shed`/`reduce_scope` 不在 JUSTIFIED_END_REASONS（认输 ≠ 收工理由）",
          not any("shed" in str(x) or "scope" in str(x) for x in justified), str(justified))
    w, run, obs, z0, ztiles = _shed_setup(200, tag="c2")
    rep = rep_for()
    pl = plot(z0, run._zone_observed_tiles(z0, obs))
    run._shed_scope(z0, obs, rep)
    # ③ 洗白 no_unmet_stages：认输后该区仍是"有目标但没做完" ⇒ 当天 leftover 只能非空
    left = run._leftover("water_area", obs, pl)
    check("C2b 认输后该区 leftover 仍非空 ⇒ 当天 no_unmet_stages 只能 False（洗不白）",
          bool(left) and len(left) >= ztiles, f"leftover={len(left)} zone={ztiles}")
    check("C2c 认输格在观测里仍是未浇活苗（dry 未被抹）",
          all(not (w.crops.get(t) or {}).get("watered") for t in run._shed_tile_set()),
          str(sorted(run._shed_tile_set())[:3]))
    # ⑥ 不许把认输格从窗口观测里藏掉
    check("C2d 认输后该区在窗口观测里格数不变（没被静默藏掉）",
          len(run._zone_observed_tiles(z0, obs)) == ztiles,
          f"now={len(run._zone_observed_tiles(z0, obs))} before={ztiles}")
    check("C2e farm 口径 dryCrops 不减（认输 ≠ 作物消失）",
          int(((obs.get("farm") or {}).get("dryCrops")) or 0) >= ztiles,
          str((obs.get("farm") or {}).get("dryCrops")))
    # ⑧ 理由不许含坐标/未观测事实
    reason = str((rep.scope_shed or {}).get("reason") or "")
    check("C2f 认输理由不含坐标（只有 zone/格数/原因）",
          not re.search(r"\[\s*\d+\s*,", reason) and str(run._zone_bounds(z0, obs)) not in reason,
          reason[:140])
    # ⑤ 持久层不许被别的 run 继承（scope 文件按 journal 命名）
    run2 = mk(world(200), journal=JOURNALS / "c2_other.jsonl")
    run2._scope_load()
    check("C2g 换一本 journal ⇒ 认输状态不继承",
          not run2.shed_zones and not run2._shed_tile_set(),
          f"zones={sorted(run2.shed_zones)} path={getattr(run2, 'scope_path', None)}")
    # ⑦ 连续多天认输：第二天仍不许自洽成 true（要么被 34% 上界拒，要么仍留 leftover）
    run.scope_shed_today = False                      # 模拟日切重置（longrun.py:5405-5407）
    obs3 = world(200).obs()
    others = [n for n in zone_names(run, obs3) if n != z0]
    ok2 = bool(run._shed_scope(others[0], obs3, rep_for(day=11))) if others else False
    cap_refused = any(e.get("reason") == "cap" for e in events(run, "scope_shed_refused"))
    left2 = (run._leftover("water_area", obs3, plot(others[0], run._zone_observed_tiles(others[0], obs3)))
             if others else [])
    check("C2h 第二天再认输仍不许自洽成 true（被 34% 上界拒 或 仍留 leftover）",
          (not ok2 and cap_refused) or (ok2 and bool(left2)),
          f"ok2={ok2} cap_refused={cap_refused} leftover2={len(left2)}")


def case_T3() -> None:
    """工具侧交叉（Lead 的 task-168 口径核对）：自述 vs journal 逐条、认输却自称 VERIFIED。"""
    print("== T3 工具侧交叉核对（verify-run3）==")
    base = BASE_LEDGER
    if not base.exists():
        return skip("T3", "缺基准账本 logs/longrun-3day-llm-run9c.jsonl")
    rc0, out0 = tool_run(base, days=3)
    verdict0 = "VERIFIED" if "VERIFIED" in out0 else "?"
    info("T3 基准账本（run9c 旧口径，无 scope_shed 字段）", f"rc={rc0} verdict={verdict0}")
    ev = [{"event": "scope_shed", "t": 1200.0, "zone": "field_ne", "tiles": 5,
           "live_crops": 20, "water_capacity": 129, "deficit": 71, "reason": "伪造"}]
    # (a) 账本自称认输但 journal 无事件 ⇒ 认输量对不上
    a = forge(base, JOURNALS / "t3a.jsonl",
              patch_day_end={"scope_shed_tiles": 7,
                             "scope_shed": {"fake": {"tiles": 7, "reason": "伪造"}}},
              which="last")
    rca, outa = tool_run(a, days=3)
    check("T3a 账本自称认输 7 格而 journal 无 scope_shed ⇒ problem（认输量对不上）",
          rca != 0 and "认输量对不上" in outa, f"rc={rca}")
    # (b) journal 有事件而账本缺字段 ⇒ 缺失≠通过
    b = forge(base, JOURNALS / "t3b.jsonl", patch_day_end={}, add_events=ev, which="last")
    rcb, outb = tool_run(b, days=3)
    check("T3b journal 有 scope_shed 而账本没写 scope_shed_tiles ⇒ problem（缺失 ≠ 通过）",
          rcb != 0 and "没写 scope_shed_tiles" in outb,
          f"rc={rcb} :: " + " / ".join(ln for ln in outb.splitlines() if "scope_shed" in ln)[:400])
    # (c) 自述与 journal 一致 ⇒ 只作 info，不改判决
    c = forge(base, JOURNALS / "t3c.jsonl",
              patch_day_end={"scope_shed_tiles": 5, "scope_shed": {"field_ne": {"tiles": 5}}},
              add_events=ev, which="last")
    rcc, outc = tool_run(c, days=3)
    check("T3c 自述与 journal 一致 ⇒ 不因此判红（与基准同码）",
          "认输量对不上" not in outc and "没写 scope_shed_tiles" not in outc and rcc == rc0,
          f"rc={rcc} 基准={rc0}")
    # (d) 认输 + 自称 VERIFIED ⇒ 自相矛盾
    d = forge(base, JOURNALS / "t3d.jsonl",
              patch_day_end={"scope_shed_tiles": 5, "scope_shed": {"field_ne": {"tiles": 5}}},
              add_events=ev, which="last")
    rcd, outd = tool_run(d, days=3)
    check("T3d 认输 5 格却自称 VERIFIED ⇒ problem（scope_shed 与 verified 自相矛盾）",
          "却自称 VERIFIED" in outd, f"rc={rcd} verdict={'VERIFIED' if 'VERIFIED' in outd else '?'}")
    # 与脑侧同向：对不上/矛盾类判红；一致类与基准同码（基准 rc=1 来自 run9c 别的历史问题，与 scope_shed 无关）
    check("T3e 四条伪账本与脑侧同向（a/b/d 判红、c 与基准同码）",
          rca != 0 and rcb != 0 and rcd != 0 and rcc == rc0,
          f"rc a/b/c/d={rca}/{rcb}/{rcc}/{rcd} 基准={rc0}")


CASES = {
    "P1": case_P1, "A2": case_A2, "A3": case_A3, "A4": case_A4,
    "B1": case_B1, "B2": case_B2, "A7": case_A7, "R1": case_R1,
    "X1": case_X1, "T1": case_T1, "T3": case_T3, "A6": case_A6, "A6b": case_A6b,
    "C2": case_C2,
}


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--case", default=None)
    args = ap.parse_args(argv)
    if args.list:
        for k in CASES:
            print(k)
        return 0
    print(f"task-185 骨架 v2 · 树 = {ROOT}")
    print(f"task-168 特性探测：has_168={has_168()}")
    names = [args.case] if args.case else list(CASES)
    for name in names:
        try:
            CASES[name]()
        except Exception as exc:                      # noqa: BLE001
            check(f"{name} 未抛异常", False, f"{type(exc).__name__}: {exc}")
    print(f"\n== 汇总：PASS={PASS} FAIL={FAIL} SKIP={SKIP}；复现发现 {len(FINDINGS)} 条 ==")
    for f in FINDINGS:
        print(f"   - {f}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
