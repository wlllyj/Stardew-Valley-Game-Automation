#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""task-224 验收探针骨架（0.7.39 批次）—— 覆盖 task-225 的 P0-1..P0-5。

只写 `scratch/`；不碰生产码。用 `T224_ROOT` 切树（照 `_t200_probe.py`）：**正式验收必须指向 `git archive` 冻结树**，
在制工作树只作线索（dev-coder 的 task-218/222 还没交付时，绝大多数用例应显示 SKIP/PENDING 而不是 FAIL）。

跑法（仓库根）：
    $env:PYTHONUTF8="1"; $env:T224_ROOT="$PWD\scratch\_t224_frozen"; python scratch\_t224_probe.py
    $env:T224_ROOT="$PWD"; python scratch\_t224_probe.py   # 在制工作树（只作线索）

设计说明：
- 每个 P0 组先做 **marker 探测**：特性没交付 ⇒ SKIP（pending），交付后才有 FAIL 资格（避免"没测到"写成"通过"，也避免在制树把骨架烧红）。
- 断言尽量走**可执行路径**（合成观测 → 真模块函数），源码级检查只用于"注册表/映射表/白名单快照/工具分工"这类无运行入口的约束。
- 输出三态：PASS / FAIL / SKIP（SKIP 会打印 pending 列表，供 task-224 报告 §2 逐条对账）。
"""
from __future__ import annotations

import importlib
import inspect
import os
import re
import sys
import traceback
from pathlib import Path

ROOT = Path(os.environ.get("T224_ROOT") or ".").resolve()

# 不依赖 PYTHONUTF8：Windows 控制台默认 gbk，遇到 arrow/tilde 等字符会崩
try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[attr-defined]
except Exception:  # noqa: BLE001
    pass

PASS: list[str] = []
FAIL: list[str] = []
SKIP: list[str] = []
INFO: list[str] = []


def check(tag: str, ok: bool, detail: str = "") -> None:
    (PASS if ok else FAIL).append(tag)
    print(("  PASS " if ok else "  FAIL ") + tag + (f" :: {detail}" if detail else ""))


def skip(tag: str, why: str = "") -> None:
    SKIP.append(tag)
    print(f"  SKIP {tag}" + (f" :: {why}" if why else ""))


def info(tag: str, detail: str = "") -> None:
    INFO.append(tag)
    print("  info " + tag + (f" :: {detail}" if detail else ""))


# ---------------------------------------------------------------- 加载


def _load_modules():
    for p in (str(ROOT), str(ROOT / "tests"), str(ROOT / "brain")):
        if p in sys.path:
            sys.path.remove(p)
        sys.path.insert(0, p)
    mods: dict[str, object] = {}
    for name, path in (("planner", "agentfarm.planner"), ("farmwork", "agentfarm.farmwork"),
                       ("longrun", "agentfarm.longrun")):
        try:
            mods[name] = importlib.import_module(path)
        except Exception as exc:  # noqa: BLE001
            mods[name] = exc
    try:
        mods["TL"] = importlib.import_module("test_longrun")
    except Exception as exc:  # noqa: BLE001
        mods["TL"] = exc
    try:
        mods["TF"] = importlib.import_module("test_farmwork")
    except Exception as exc:  # noqa: BLE001
        mods["TF"] = exc
    return mods


M = _load_modules()
PL = M.get("planner")
FW = M.get("farmwork")
LR = M.get("longrun")
TL = M.get("TL")
TF = M.get("TF")


def _ok(*keys: str) -> bool:
    """模块都 import 成功（切树时可能缺文件）。"""
    return all(not isinstance(M.get(k), Exception) for k in keys)


def mod_attr(mod, name: str):
    try:
        return getattr(mod, name)
    except Exception:  # noqa: BLE001
        return None


def _src(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _grep_tree(root: Path, pattern: str) -> list[tuple[Path, int, str]]:
    hits: list[tuple[Path, int, str]] = []
    for p in sorted((root / "tests").glob("*.py")) if (root / "tests").is_dir() else []:
        for i, line in enumerate(_src(p).splitlines(), 1):
            if re.search(pattern, line):
                hits.append((p, i, line.strip()))
    return hits


# ---------------------------------------------------------------- marker 探测


def markers() -> dict[str, bool]:
    """每个 P0 的"已交付"探测；未交付 ⇒ SKIP。"""
    m: dict[str, bool] = {}

    def a(mod, name):
        return mod_attr(mod, name) is not None

    m["P0-1a 逐格 after kind"] = bool(_ok("farmwork") and (
        "before_kind" in _src(ROOT / "brain/agentfarm/farmwork.py")
        or "after_kind" in _src(ROOT / "brain/agentfarm/farmwork.py")
        or "cleared_tiles" in _src(ROOT / "brain/agentfarm/farmwork.py")))
    m["P0-1b FarmView 障碍计数"] = "weeds" in _src(ROOT / "mod/AgentFarm.Bridge/Contracts.cs") and \
        "trees" in _src(ROOT / "mod/AgentFarm.Bridge/Contracts.cs")
    m["P0-2 DEFERRED_KINDS"] = bool(_ok("planner") and a(PL, "DEFERRED_KINDS"))
    m["P0-3 原因码/意图对账"] = "intent_coverage" in _src(ROOT / "brain/agentfarm/longrun.py")
    m["P0-4 gaps 文件"] = "-gaps.json" in _src(ROOT / "brain/agentfarm/longrun.py") or \
        "gaps_path" in _src(ROOT / "brain/agentfarm/longrun.py")
    m["P0-5 analyzer 判 §8"] = "intent_coverage" in _src(ROOT / "tools/analyze-longrun.py")
    m["P0-5 verify-run3 只 info"] = "intent_coverage" in _src(ROOT / "tools/verify-run3.py")
    return m


def pending(tag: str, detail: str = "") -> None:
    """特性未交付：SKIP（不是 FAIL，也不是 PASS）。"""
    skip(tag, detail)


def gates() -> dict[str, bool]:
    """整组用例的交付门槛：未交付 ⇒ 整组 SKIP 并打印 pending（避免在制树把骨架烧红）。"""
    g: dict[str, bool] = {}
    src_fw = _src(ROOT / "brain/agentfarm/farmwork.py")
    union = list(dict.fromkeys(list(mod_attr(PL, "OBSTACLE_KINDS") or ())
                               + list(mod_attr(FW, "CLUMP_KINDS") or ())))
    deferred = set(mod_attr(PL, "DEFERRED_KINDS") or {})
    skip_kinds = set(mod_attr(FW, "SKIP_KINDS") or {})
    hits = _grep_tree(ROOT, r"DEFERRED_KINDS")
    drift = any(re.search(r"[Dd]rift|漂移|registry|注册表", h[2]) for h in hits)
    tree_ok = False
    try:
        if _ok("farmwork") and _ok("TL"):
            world = TL.FakeWorld(weeds=0, seeds=0, money=0)
            world.blockers[(61, 11)] = "tree"
            res = FW.FarmWorker(TL.FakeClient(world), log=lambda *_: None, pause=lambda _s: None).clear((61, 11))
            tree_ok = bool(res.ok)
    except Exception:  # noqa: BLE001
        tree_ok = False
    g["218"] = bool(tree_ok and skip_kinds <= deferred and drift and (deferred == {"fruitTree", "bush"})
                  and ("before_kind" in src_fw or "after_kind" in src_fw or "cleared_tiles" in src_fw))
    cs = _src(ROOT / "mod/AgentFarm.Bridge/Contracts.cs")
    g["222"] = all(f'JsonPropertyName("{k}")' in cs for k in ("weeds", "stones", "twigs", "trees", "clumps"))
    g["219"] = "intent_coverage" in _src(ROOT / "brain/agentfarm/longrun.py")
    g["220"] = "intent_coverage" in _src(ROOT / "tools/analyze-longrun.py")
    g["union"] = bool(union)
    # 自测用：T224_ASSUME=218,219,220 强制视为已交付（验证断言真的"活"、不会静默跳过）
    assume = {x.strip() for x in os.environ.get("T224_ASSUME", "").split(",") if x.strip()}
    for k in list(g):
        if k in assume:
            g[k] = True
    return g


GATES = gates()


# ---------------------------------------------------------------- P0-1 护栏 B 逐格判据


def p01_after_kind_schema() -> None:
    print("[P0-1] clear() 的 StepResult.after 是否带 before/after kind / cleared_tiles（tree→stump = progress）")
    if not markers()["P0-1a 逐格 after kind"]:
        skip("P0-1a StepResult.after 逐格 kind 字段", "task-218 尚未交付（无 before_kind/after_kind/cleared_tiles）")
        return
    if not (_ok("farmwork") and _ok("TL")):
        skip("P0-1a 运行入口", "farmwork/test_longrun 导入失败")
        return
    world = TL.FakeWorld(weeds=0, seeds=0, money=0)
    tile = (61, 11)
    world.blockers[tile] = "tree"
    client = TL.FakeClient(world)
    worker = FW.FarmWorker(client, log=lambda *_: None, pause=lambda _s: None)
    res = worker.clear(tile)
    after = res.after or {}
    check("P0-1a-1 after 是 dict 且非空", isinstance(after, dict) and bool(after), f"after={after!r}")
    kind_keys = [k for k in after if "kind" in str(k)]
    check("P0-1a-2 after 含 before/after kind 键", len(kind_keys) >= 2, f"keys={sorted(after)!r}")
    check("P0-1a-3 tree→stump 记 progress 不算硬失败",
          bool(res.ok) or res.code not in ("failed",),
          f"ok={res.ok} code={res.code} after={after!r}")
    info("P0-1a-4 tree 砍倒后的 after", repr(after))


def p01_guard_b_fields() -> None:
    print("[P0-1] 护栏 B：阶段记录是否带 cleared_tiles / blocker_drop，且 farm 聚合不当判红主判据")
    lr_src = _src(ROOT / "brain/agentfarm/longrun.py")
    if not lr_src:
        skip("P0-1b longrun 源码", "读不到")
        return
    if not GATES["218"]:
        skip("P0-1b 阶段记录 cleared_tiles/blocker_drop",
             "task-218 尚未完整交付（tree clear / SKIP⊆DEFERRED / 漂移测试 / announce 未齐）")
        return
    has_cleared = "cleared_tiles" in lr_src
    has_drop = "blocker_drop" in lr_src
    if not (has_cleared or has_drop):
        skip("P0-1b 阶段记录 cleared_tiles/blocker_drop", "task-218 尚未交付")
        return
    check("P0-1b-1 阶段记录带 cleared_tiles 或 blocker_drop", has_cleared or has_drop,
          f"cleared_tiles={has_cleared} blocker_drop={has_drop}")
    # farm 级计数只作 info：判红分支里不许直接拿 farm.blockers 当唯一条件
    m = re.search(r"blocker_drop[^\n]{0,120}", lr_src)
    check("P0-1b-2 blocker_drop 允许 null（缺失 ≠ 0）", "None" in lr_src or "null" in lr_src, "证据不可用 ⇒ null")
    info("P0-1b-3 blocker_drop 上下文", (m.group(0) if m else "(未找到)")[:120])


def p01_farmview_counts() -> None:
    print("[P0-1] task-222 备选路线：FarmView 是否补了 weeds/stones/twigs/trees/clumps 计数（三态可辨）")
    cs = _src(ROOT / "mod/AgentFarm.Bridge/Contracts.cs")
    if not cs:
        skip("P0-1c Contracts.cs", "读不到")
        return
    need = ["weeds", "stones", "twigs", "trees", "clumps"]
    got = {k: (f'JsonPropertyName("{k}")' in cs) for k in need}
    if not GATES["222"]:
        skip("P0-1c FarmView 障碍计数", f"task-222 追加项尚未完整交付（P0 的备选路线）：{got}")
        return
    check("P0-1c-1 FarmView 五类障碍计数齐全", all(got.values()), f"{got}")
    check("P0-1c-2 三态可辨（Never 可空）", "JsonIgnoreCondition.Never" in cs, "缺失/null/0 可辨")


# ---------------------------------------------------------------- P0-2 护栏 A 六层矩阵


def _kinds() -> tuple[list[str], set[str], set[str]]:
    obstacle = list(mod_attr(PL, "OBSTACLE_KINDS") or ())
    clump = list(mod_attr(FW, "CLUMP_KINDS") or ())
    union = list(dict.fromkeys(list(obstacle) + list(clump)))
    return union, set(obstacle), set(clump)


def p02_registry_invariants() -> None:
    print("[P0-2] 注册表不变量：并集覆盖 / SKIP_KINDS ⊆ DEFERRED_KINDS / 白名单快照 {fruitTree,bush}")
    if not GATES["218"]:
        pending("P0-2 注册表不变量", "task-218 尚未完整交付（gates.218=False）")
        return
    union, obstacle, clump = _kinds()
    deferred = dict(mod_attr(PL, "DEFERRED_KINDS") or {})
    skip_kinds = set(mod_attr(FW, "SKIP_KINDS") or {})
    check("P0-2-1 并集非空且无重复归类冲突", len(union) >= 10, f"union={union}")
    check("P0-2-2 DEFERRED_KINDS 键都在并集内", set(deferred) <= set(union), f"deferred={sorted(deferred)}")
    check("P0-2-3 SKIP_KINDS ⊆ DEFERRED_KINDS", skip_kinds <= set(deferred), f"skip={sorted(skip_kinds)}")
    check("P0-2-4 DEFERRED_KINDS 白名单快照 == {fruitTree,bush}", set(deferred) == {"fruitTree", "bush"},
          f"实际={sorted(deferred)}（新增必须显式改快照+卡）")
    for kind in sorted(set(deferred)):
        reason = deferred.get(kind)
        check(f"P0-2-5 {kind} 登记含'缺什么能力/理由'", isinstance(reason, str) and len(reason) >= 8,
              f"reason={reason!r}")


def p02_six_layers() -> None:
    print("[P0-2] 端到端 6 层矩阵：planner→_plot_brief→_stage_tiles→clear()→_plot_has_work→_apply_policy")
    if not GATES["218"]:
        pending("P0-2 六层矩阵", "task-218 尚未完整交付（gates.218=False）")
        return
    if not (_ok("longrun") and _ok("TL")):
        skip("P0-2 六层矩阵-运行", "longrun/test_longrun 导入失败")
        return
    union, _, _ = _kinds()
    deferred = set(mod_attr(PL, "DEFERRED_KINDS") or {})
    for kind in sorted(set(union) - deferred):
        try:
            world = TL.FakeWorld(weeds=0, seeds=0, money=0)
            tile = (61, 11)
            world.blockers[tile] = kind
            obs = world.obs()
            # 层 1/2：planner 简报必须能"看见"这类障碍（tiles 在窗口内）
            brief = PL.Brief.from_observe(obs)
            seen = int((brief.counts or {}).get("blockers") or 0)
            # 层 3：_stage_tiles 必须能给出目标（或明确 deferred）
            run = TL.make_run(world, target_days=1, max_days=1)
            run.worker = TL.FakeWorker(world)
            run.client = TL.FakeClient(world)
            plot = {"zone": "", "label": "", "anchor": [tile[0], tile[1]],
                    "tiles": [list(tile)], "note": ""}
            tiles = run._stage_tiles("clear_area", obs, plot)
            # 层 4：clear() 能产出动作（tree 需要 218 的斧砍；这里至少不许抛异常）
            client = TL.FakeClient(world)
            worker = FW.FarmWorker(client, log=lambda *_: None, pause=lambda _s: None)
            res = worker.clear(tile)
            got_target = bool(tiles) or bool(res.ok)
            # clump 族按卡面走"toolOk==false ⇒ backlog 留痕"路线，不要求 clear() 真挥
            clump_family = kind in set(mod_attr(FW, "CLUMP_KINDS") or ())
            backlog = ("clump_blocked_backlog" in _src(ROOT / "brain/agentfarm/longrun.py")
                       or "toolOk" in _src(ROOT / "brain/agentfarm/farmwork.py"))
            if clump_family and not got_target:
                got_target = backlog
                info(f"P0-2-6 [{kind}] clump 族走 backlog 路线", f"backlog_marker={backlog}")
            # 层 5：_plot_has_work 必须认为是活
            has_work = run._plot_has_work(obs, [tile])
            # 层 6：_apply_policy 不许把 clear_area 意图丢掉（有目标时）
            decision = type("D", (), {"intents": [TL.TaskIntent("clear_area", "anchor:current_location", "清障")],
                                      "boundary": "recovery", "source": "llm", "llm_called": True,
                                      "problems": [], "fallback_reason": None})()
            applied, note = run._apply_policy(decision, obs)
            kept = [i.task for i in getattr(applied, "intents", [])]
            ok = got_target and (has_work or clump_family) and ("clear_area" in kept or not tiles)
            check(f"P0-2-6 [{kind}] 六层均可达", ok,
                  f"brief_blockers={seen} stage_tiles={len(tiles)} clear_ok={res.ok}/{res.code} "
                  f"plot_has_work={has_work} kept={kept} note={note}")
        except Exception as exc:  # noqa: BLE001
            FAIL.append(f"P0-2-6 [{kind}] EXC")
            print(f"  FAIL P0-2-6 [{kind}] EXC :: {exc!r}")


def p02_drift_and_announce() -> None:
    print("[P0-2] 注册表漂移测试存在 + tiles 缺失/截断时 deferred 也 announce（fail-closed）")
    if not GATES["218"]:
        pending("P0-2 漂移/announce", "task-218 尚未完整交付（gates.218=False）")
        return
    hits = _grep_tree(ROOT, r"DEFERRED_KINDS")
    drift = [h for h in hits if re.search(r"[Dd]rift|漂移|registry|注册表", h[2])]
    check("P0-2-7 存在 DEFERRED_KINDS 的漂移/注册表测试", bool(drift),
          f"命中={[(h[0].name, h[1]) for h in drift][:3]}")
    # fail-closed announce：没有 location.tiles，但 farm 计数显示有障碍
    world = TL.FakeWorld(weeds=0, seeds=0, money=0)
    obs = world.obs()
    obs["location"] = {"name": "Farm", "tiles": []}
    obs["farm"] = dict(obs.get("farm") or {})
    for k in ("weeds", "stones", "twigs", "trees"):
        obs["farm"][k] = 3
    brief = PL.Brief.from_observe(obs)
    text = brief.situation_text()
    announced = any(k in text for k in ("暂不支持", "果实树", "果树", "灌木"))
    check("P0-2-8 tiles 缺失时 deferred kind 仍被公告（fail-closed）", announced,
          f"text含暂不支持={announced}")


# ---------------------------------------------------------------- P0-3 原因码/单位对账


EXPECTED_REASON_CODES = {"no_target", "unknown_evidence", "superseded", "deferred_capability",
                         "tool_level", "budget", "blocked_tile", "blocked_modal", "no_slot",
                         "world_stuck", "gated", "failed"}
ACTIONLESS = {"sleep", "review", "wait_for_save", "recover_stamina"}


def _find_reason_codes():
    for mod, name in ((LR, "REASON_CODES"), (LR, "INTENT_REASON_CODES"), (LR, "REASON_CODE_SET")):
        got = mod_attr(mod, name)
        if got is not None:
            return name, got
    src = _src(ROOT / "brain/agentfarm/longrun.py")
    m = re.search(r"REASON[C_]*\w*\s*(?::[^=]+)?=\s*(\{[^}]*\}|\([^)]*\)|\[[^\]]*\])", src, re.S)
    return (None, m.group(1) if m else None)


def p03_reason_codes() -> None:
    print("[P0-3] 原因码闭合集 = 12 码（含 unknown_evidence/superseded/failed）+ 集外码判红")
    if not markers()["P0-3 原因码/意图对账"]:
        skip("P0-3 原因码", "task-219 尚未交付（无 intent_coverage）")
        return
    name, codes = _find_reason_codes()
    if not codes:
        skip("P0-3 原因码表", "找不到 REASON_CODES 常量（交付后需按约定命名，单一数据源）")
        return
    try:
        got = set(codes.keys()) if isinstance(codes, dict) else set(codes)
    except Exception:  # noqa: BLE001
        skip("P0-3 原因码表", f"无法解析 {name}={codes!r}")
        return
    check("P0-3-1 原因码集合 == §8.2 十二码", got == EXPECTED_REASON_CODES,
          f"缺={sorted(EXPECTED_REASON_CODES - got)} 多={sorted(got - EXPECTED_REASON_CODES)}")
    lr_src = _src(ROOT / "brain/agentfarm/longrun.py")
    check("P0-3-2 集外码判红逻辑存在（analyzer 侧）", "集外" in _src(ROOT / "tools/analyze-longrun.py"),
          "analyzer 需对集外码判红")


def p03_status_mapping() -> None:
    print("[P0-3] 完备映射表：每个 StepResult 状态码都能映射到原因码（漏码即缺陷）")
    src = _src(ROOT / "brain/agentfarm/longrun.py")
    if "intent_coverage" not in src:
        skip("P0-3 状态映射", "task-219 尚未交付")
        return
    # 单一数据源约定：名字里带 REASON 的 dict 且值为原因码之一
    candidates = re.findall(r"([A-Z_]*REASON[A-Z_]*)\s*(?::[^=]*)?=\s*\{", src)
    info("P0-3-3 候选映射表", repr(candidates))
    check("P0-3-4 存在状态→原因码映射表（单一数据源）", bool(candidates), f"candidates={candidates}")
    tests_hits = _grep_tree(ROOT, r"REASON|reason.*map|映射")
    check("P0-3-5 映射表有漂移测试", any("REASON" in h[2] for h in tests_hits),
          f"命中={[(h[0].name, h[1]) for h in tests_hits][:3]}")


def p03_no_target_evidence() -> None:
    print("[P0-3] no_target 证据 schema（stage_tiles_empty + obs_seq|counts）；证据不可用 ⇒ unknown_evidence")
    src = _src(ROOT / "brain/agentfarm/longrun.py")
    if "intent_coverage" not in src:
        skip("P0-3 no_target 证据", "task-219 尚未交付")
        return
    check("P0-3-6 有 stage_tiles_empty 证据字段", "stage_tiles_empty" in src, "no_target 必附证据")
    check("P0-3-7 证据不可用落到 unknown_evidence", "unknown_evidence" in src, "禁止裸用 no_target")


def p03_tile_invariants() -> None:
    print("[P0-3] 瓦片制不变式：requested = ok+failed+unexecuted；Σreasons = failed+unexecuted")
    src = _src(ROOT / "brain/agentfarm/longrun.py")
    if "intent_coverage" not in src:
        skip("P0-3 瓦片不变式", "task-219 尚未交付")
        return
    check("P0-3-8 代码含瓦片不变式校验/断言",
          ("requested_tiles" in src and "unexecuted_tiles" in src),
          "字段名存在")
    # 尝试运行校验函数（若交付时提供了 validator）
    fn = None
    for name in ("_intent_coverage_ok", "validate_intent_coverage", "_check_intent_coverage"):
        fn = mod_attr(LR, name)
        if fn:
            break
    if fn:
        good = type("E", (), {"requested_tiles": 5, "ok_tiles": 3, "failed_tiles": 1,
                              "unexecuted_tiles": 1, "reasons": {"failed": 1, "no_target": 1}})()
        bad = type("E", (), {"requested_tiles": 5, "ok_tiles": 3, "failed_tiles": 1,
                             "unexecuted_tiles": 5, "reasons": {"failed": 1}})()
        try:
            check("P0-3-9 validator 接受合法对账", bool(fn(good)), "5=3+1+1 / 2=1+1")
            check("P0-3-10 validator 拒绝非法对账", not bool(fn(bad)), "5 ?= 3+1+5")
        except Exception as exc:  # noqa: BLE001
            skip("P0-3 validator 调用", f"签名不符：{exc!r}")
    else:
        skip("P0-3 validator 运行", "交付时建议提供一个纯函数 validator 供验收直调")


def p03_intent_id_actionless() -> None:
    print("[P0-3] intent_id 跨日唯一 + ACTIONLESS 白名单")
    src = _src(ROOT / "brain/agentfarm/longrun.py")
    if "intent_coverage" not in src:
        skip("P0-3 intent_id/ACTIONLESS", "task-219 尚未交付")
        return
    check("P0-3-11 intent_id 由 day_key+seq 生成（跨日不复用）",
          bool(re.search(r"intent_id.*day|day.*intent_id", src)), "建议 <day_key>#<seq>")
    al = mod_attr(LR, "ACTIONLESS_TASKS")
    if al is None:
        skip("P0-3-12 ACTIONLESS_TASKS", "未找到常量（交付后应有）")
    else:
        got = set(al)
        check("P0-3-13 ACTIONLESS_TASKS 覆盖四类无动作意图", ACTIONLESS <= got,
              f"缺={sorted(ACTIONLESS - got)}")
    tests = _grep_tree(ROOT, r"ACTIONLESS|actionless")
    check("P0-3-14 ACTIONLESS 有测试", bool(tests), f"命中={[(h[0].name, h[1]) for h in tests][:3]}")


# ---------------------------------------------------------------- P0-4/5 gaps 分层 + 工具分工


def p04_gaps_layering() -> None:
    print("[P0-4] gaps：per-run 文件 + schema + 原子写 + 坏文件归档 + 写失败判问题 + 禁止转 lessons")
    src = _src(ROOT / "brain/agentfarm/longrun.py")
    if not markers()["P0-4 gaps 文件"]:
        skip("P0-4 gaps", "task-219 尚未交付（无 gaps 文件写入）")
        return
    check("P0-4-1 按 journal 派生 per-run gaps 路径", "gaps" in src and "journal" in src, "run 隔离")
    check("P0-4-2 有 schema 头", "schema" in src and "gaps" in src, "agentfarm-gaps/1 或等价")
    check("P0-4-3 原子写（tmp+replace）", "os.replace" in src or "replace(" in src, "半写防护")
    check("P0-4-4 坏文件归档（.bad./corrupt）", ".bad." in src or "corrupt" in src, "不覆盖坏文件")
    check("P0-4-5 写失败有 journal（gaps_write_failed/load_failed）",
          "gaps_write_failed" in src or "gaps_load_failed" in src, "缺失 ≠ 通过")
    # 跨 run 聚合层只能出现在工具侧，不许 brain 写全局
    tools_src = _src(ROOT / "tools/analyze-longrun.py") + _src(ROOT / "tools/compare-runs.py")
    check("P0-4-6 跨 run 聚合在工具侧（gaps-registry）", "gaps-registry" in tools_src or "gaps_registry" in tools_src,
          "brain 不写全局层")
    check("P0-4-7 brain 不把 gaps 自动转 lessons", not re.search(r"gap[^\n]{0,80}make_lesson", src),
          "转换须人工/Lead 卡")


def p05_tool_division() -> None:
    print("[P0-5] 工具分工：§8 由 analyzer 判红；verify-run3 只 info；能力缺口不进 hard checks")
    ana = _src(ROOT / "tools/analyze-longrun.py")
    ver = _src(ROOT / "tools/verify-run3.py")
    if not ana:
        skip("P0-5 analyzer 源码", "读不到")
        return
    if not GATES["220"]:
        pending("P0-5-1 analyzer 判 §8", "task-220 尚未交付（analyzer 无 intent_coverage）")
    else:
        check("P0-5-1 analyzer 读 day_end.intent_coverage 并判红", "intent_coverage" in ana and
              ("problem" in ana or "problems" in ana), "判红主体")
    if "intent_coverage" not in ver:
        check("P0-5-2 verify-run3 不判 §8（未出现在源码里）", True, "符合分工")
    else:
        # 出现也行，但只许在 info 文案：逐行看是否有 problem 伴生
        bad = [ln for ln in ver.splitlines() if "intent_coverage" in ln and "problem" in ln]
        check("P0-5-2 verify-run3 对 §8 只出 info", not bad, f"可疑行={bad[:2]}")
    lr_src = _src(ROOT / "brain/agentfarm/longrun.py")
    check("P0-5-3 能力缺口不进 checks/_leftover", "DEFERRED_KINDS" not in
          "\n".join(ln for ln in lr_src.splitlines() if "_leftover" in ln or "checks" in ln),
          "deferred 只提示、不豁免")
    if _ok("longrun"):
        try:
            keys = set(LR.DayReport(day_key=("spring", 1, 1), started_at=0.0).as_dict().get("checks") or {})
        except Exception:  # noqa: BLE001
            keys = set()
        if keys:
            check("P0-5-4 checks 键集未新增（无 intent 相关键）", not any("intent" in k for k in keys),
                  f"keys={sorted(keys)}")


CASES = [
    ("P0-1", p01_after_kind_schema),
    ("P0-1", p01_guard_b_fields),
    ("P0-1", p01_farmview_counts),
    ("P0-2", p02_registry_invariants),
    ("P0-2", p02_six_layers),
    ("P0-2", p02_drift_and_announce),
    ("P0-3", p03_reason_codes),
    ("P0-3", p03_status_mapping),
    ("P0-3", p03_no_target_evidence),
    ("P0-3", p03_tile_invariants),
    ("P0-3", p03_intent_id_actionless),
    ("P0-4", p04_gaps_layering),
    ("P0-5", p05_tool_division),
]


def main() -> int:
    print(f"T224_ROOT={ROOT}")
    print("markers: " + ", ".join(f"{k}={'Y' if v else 'n'}" for k, v in markers().items()))
    print(f"modules: planner={'ok' if _ok('planner') else M.get('planner')!r} "
          f"farmwork={'ok' if _ok('farmwork') else M.get('farmwork')!r} "
          f"longrun={'ok' if _ok('longrun') else M.get('longrun')!r}")
    only = os.environ.get("T224_ONLY")
    for name, fn in CASES:
        if only and name != only:
            continue
        try:
            fn()
        except Exception:  # noqa: BLE001
            FAIL.append(name + "-EXC")
            traceback.print_exc()
    print(f"\n== 合计 PASS={len(PASS)} FAIL={len(FAIL)} SKIP={len(SKIP)} ==")
    if FAIL:
        print("FAIL 明细：" + ", ".join(FAIL))
    if SKIP:
        print("SKIP/pending：" + ", ".join(SKIP))
    return 0 if not FAIL else 1


if __name__ == "__main__":
    sys.exit(main())
