# -*- coding: utf-8 -*-
"""0.7.41 装机后「7 步真机冒烟」编排骨架（machine-runner 待命期准备，可提前 py_compile 自测）。

7 步来源：`docs/_release-0.7.41.md` §2（2026-10-18 按 Lead m04100 再升级：2 次跨日 + 落盘守卫 + 两条新验收面）：
  1. `debug_dump table=crafting_recipes key=Furnace` ⇒ 不得 `unknown_skill`，且 matchedCount>=1
  2. `debug_dump table=trigger_actions` ⇒ 能读（task-222 目标；仍 `InvalidCastException` ⇒ 本批 smoke 判红回炉）
  3. 单技能砍树（**A2 判据**）：`kind=="tree"` 的格有界连续 `use_tool(axe)` **≤3 次调用**（≈≤18 刀）直到 `kind` 变 `stump`/消失；`tool_ineffective` 只留痕、不作失败证据；3 次后仍 `tree` 才 FAIL
  4. 跑 **2 个游戏日**（`tools/start-detached-longrun.py --days 2`）⇒ `day_end.intent_coverage` 出现、`<journal>-gaps.json` 生成
  5. `day_end.stages[]` 的 `clear_area` 每个 ok 步都有 `cleared_tiles`/kind 变化（P0-1 逐格判据活）
  6. **跨日落盘守卫**：调 `scratch/save-chain-check.py`（本工具不再自己数六串）—— 六串 6/6 配对 + **末次跨日也必须落盘**（`NewDay > Save called` ⇒ FAIL；缺 SMAPI/窗口不完整 ⇒ 无法判定）
  7. `tools/analyze-longrun.py --days 2` 判 §8 无「意图 executed_steps==0 且无原因码」、且 **`missed:intent_no_reason:*` 必须消失**；`slot_relief` 事件必须带 `demand`/`target_free`/`reached` 且**至少一天 `harvest` ok>0**（task-236/237 验收面）；`tools/verify-run3.py` 对 §8 只出 info

设计取舍（为什么是骨架而不是一条龙）
------------------------------------------------
* 第 3 步要动世界（挥一次斧头）；第 4 步是**长跑**（必须脱离式起跑，不能挂在 DSH 托管作业里，见条目 040/041）。
  所以拆成四个 phase，每个 phase 独立可重入、各留证据：
    pre    = 1,2,3（要求游戏在跑 + 桥健康，**最多一次** use_tool）
    launch = 4 的 `--dry-run` + 真起跑（写 `logs/longrun-smoke-0741.pid`）
    wait   = 只读轮询到 `finish` 或 PID 消失（受 `--wait-minutes` 预算约束）
    post   = 5,6,7（纯离线：账本 + SMAPI + 两个检查器）
* 任何一步 **无法判定** 时如实写 `无法判定`，绝不因为"没报错"就算过（缺失 ≠ 通过）。
* 安全底线：不 `load_save`、不 `craft/place/buy/sell`、不 dismiss 事件、不退出游戏（退出由 Lead 按 m02833 决定）。

用法
----
  python scratch\\smoke-0741.py --dry-run                 # 只打印计划 + 环境体检（无任何副作用，游戏没开也能跑）
  python scratch\\smoke-0741.py --phase pre               # 步骤 1-3
  python scratch\\smoke-0741.py --phase launch            # 步骤 4 起跑（先 --dry-run）
  python scratch\\smoke-0741.py --phase wait --wait-minutes 40
  python scratch\\smoke-0741.py --phase post              # 步骤 5-7
  python scratch\\smoke-0741.py --phase all --wait-minutes 40   # 一次跑完（分阶段之间不重启游戏）

分阶段跑时结果**按步骤号合并**进 --json（`phases_run` 记录已跑过的 phase），不会互相覆盖；
`--only` 只跑相关 phase（不会因为 `--only 1` 就把 step4 真起跑起来）。
退出码只反映**本次 phase** 的结果，累计状态看打印的"累计"表或 JSON 的 `results_all_steps`。

退出码：0 = 全部 PASS；10 = 有 FAIL；11 = 环境阻塞（版本/桥/前置文件不满足）；12 = 证据缺失（无法判定）。
结果 JSON：`scratch/smoke-0741.json`（每次覆盖，含每步 verdict + 原文摘录）。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
LOGS = REPO / "logs"
PY = sys.executable
SMOKE_JOURNAL = LOGS / "longrun-smoke-0741.jsonl"
SMOKE_GAPS = LOGS / "longrun-smoke-0741-gaps.json"
SMAPI_LATEST = Path(os.environ.get("APPDATA", "")) / "StardewValley" / "ErrorLogs" / "SMAPI-latest.txt"
SMOKE_SMAPI = LOGS / "smoke-0741-smapi-window.txt"

# 六串（顺序即流水线顺序；第 3 串的"修正"判别式见 count_six）
SIX = ("newday", "before_save", "save_called", "save_task", "completed", "after_save")

EXPECT_VERSION = "0.7.41"
L16_RULE = "有 `[HH:MM:SS LEVEL CHANNEL]` 前缀 且 不含 ` by AgentFarm ` / `| v0.`"


def sh(cmd: list[str], timeout: int = 180) -> tuple[int, str, str]:
    """子进程跑外部脚本：强制 UTF-8，避免 pwsh 重定向写 UTF-16 的坑。"""
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env.setdefault("PYTHONPATH", str(REPO / "brain"))
    p = subprocess.run(cmd, capture_output=True, timeout=timeout, env=env)
    return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")


def bridge():
    sys.path.insert(0, str(REPO / "brain"))
    from agentfarm.bridge import BridgeClient  # noqa: PLC0415
    return BridgeClient()


def step_record(n: int, name: str) -> dict:
    return {"step": n, "name": name, "verdict": "无法判定", "reason": "", "evidence": {}}


# ---------------------------------------------------------------- 1 & 2：debug_dump
def probe_dump(table: str, key: str | None = None, limit: int | None = None) -> dict:
    cmd = [PY, str(HERE / "_t213_probe.py"), "--table", table]
    if key:
        cmd += ["--key", key]
    if limit:
        cmd += ["--limit", str(limit)]
    rc, out, err = sh(cmd)
    return {"rc": rc, "out": out, "err": err, "cmd": " ".join(cmd), "tail": (out or err)[-1500:]}


def step1(rec: dict) -> dict:
    d = probe_dump("crafting_recipes", "Furnace", 5)
    rec["evidence"] = d
    text = d["out"] + d["err"]
    if "unknown_skill" in text:
        rec["verdict"], rec["reason"] = "FAIL", "回归：又出现 unknown_skill（Mod 白名单/技能名没同步）"
        return rec
    if d["rc"] != 0:
        rec["verdict"], rec["reason"] = "FAIL", f"探针退出码 {d['rc']}（原文见 evidence.tail）"
        return rec
    m = re.search(r'"matched(?:Count)?"\s*:\s*(\d+)', text) or re.search(r"matched(?:Count)?\D{0,3}(\d+)", text)
    matched = int(m.group(1)) if m else None
    rec["evidence"]["matchedCount"] = matched
    if matched is None:
        rec["verdict"] = "无法判定"
        rec["reason"] = "输出里没找到 matched/matchedCount 字段 —— 按 task-222 的三态口径要显式报数，不能靠猜"
    elif matched >= 1:
        rec["verdict"] = "PASS"
        rec["reason"] = f"table=crafting_recipes 读到 Furnace（matchedCount={matched}），无 unknown_skill"
    else:
        rec["verdict"], rec["reason"] = "FAIL", "matchedCount=0：Furnace 配方没出现在 dump 里"
    return rec


def step2(rec: dict) -> dict:
    d = probe_dump("trigger_actions", None, 5)
    rec["evidence"] = d
    text = d["out"] + d["err"]
    if "unknown_skill" in text:
        rec["verdict"], rec["reason"] = "FAIL", "回归：trigger_actions 被 unknown_skill 拒（白名单没同步）"
        return rec
    if "InvalidCastException" in text or "invalid_cast" in text:
        rec["verdict"], rec["reason"] = "FAIL", "仍 InvalidCastException ⇒ 按 §2 第 2 条本批 smoke 判红、回炉"
        return rec
    if d["rc"] != 0:
        rec["verdict"], rec["reason"] = "FAIL", f"探针退出码 {d['rc']}（原文见 evidence.tail）"
        return rec
    has_type = '"type"' in text or "'type'" in text
    rec["evidence"]["has_type_field"] = has_type
    if has_type or "rows" in text or "matched" in text:
        rec["verdict"] = "PASS"
        rec["reason"] = "trigger_actions 可读、无 InvalidCastException（逐表 fail-closed 的 type/error 字段" + ("在场" if has_type else "未见（需人看 tail）") + "）"
    else:
        rec["verdict"] = "无法判定"
        rec["reason"] = "退出码 0 但输出里既没有 type 也没有 rows/matched —— 无法证明表真的读出来了"
    return rec


# ---------------------------------------------------------------- 3：单技能砍树
def step3(rec: dict) -> dict:
    c = bridge()
    obs = c.observe(detail="full")
    loc = obs.get("location") or {}
    rec["evidence"]["location"] = loc.get("name")
    rec["evidence"]["isOutdoorFarm"] = loc.get("isOutdoorFarm")
    if not loc.get("isOutdoorFarm"):
        rec["verdict"], rec["reason"] = "无法判定", f"当前不在户外农场（location={loc.get('name')}）⇒ 先 goto Farm 再跑本步"
        return rec
    tiles_all = {tuple(x["tile"]): x for x in (loc.get("tiles") or [])}
    trees = [t for t in tiles_all.values() if t.get("kind") == "tree"]
    rec["evidence"]["tree_tiles_in_window"] = len(trees)
    if not trees:
        rec["verdict"] = "无法判定"
        rec["reason"] = "窗口（400 格）内没有 kind==tree 的格 ⇒ 需先站到树旁；不许扫全图乱走"
        return rec
    # Lead m03672：优先挑「四邻有可站格」的树（否则斧头挥不到），并记候选统计
    dirs = ((0, -1), (1, 0), (0, 1), (-1, 0))

    def standable_nbrs(t):
        x, y = t["tile"]
        out = []
        for dx, dy in dirs:
            n = tiles_all.get((x + dx, y + dy))
            if n is not None and n.get("standable") is True:
                out.append([x + dx, y + dy])
        return out

    cand = [(t, standable_nbrs(t)) for t in trees]
    with_nbr = [c for c in cand if c[1]]
    rec["evidence"]["tree_candidates"] = {"total": len(trees),
                                          "with_standable_neighbor": len(with_nbr)}
    if with_nbr:
        pick, nbrs = sorted(with_nbr, key=lambda c: (c[0]["tile"][0], c[0]["tile"][1]))[0]
    else:
        pick, nbrs = sorted(trees, key=lambda x: (x["tile"][0], x["tile"][1]))[0], []
        rec["evidence"]["picked_without_standable_neighbor"] = True
    tile = tuple(pick["tile"])
    rec["evidence"]["tile"] = list(tile)
    rec["evidence"]["standable_neighbors"] = nbrs
    # Lead 裁定(A)：先走到可站邻格 —— 行走单独计，**不算「单技能」的结论**。
    # use_tool 不负责行走；首跑就是因为玩家在 (64,15)、目标在 (39,14)（相距 ~25 格）
    # 导致 Mod 6 次重试全在「够不着」里空挥、被判 FAIL（那是测试前置不成立，不是技能坏）。
    if nbrs:
        nbr = nbrs[0]
        try:
            mv = c.move_to(nbr[0], nbr[1], timeout_ms=30000)
            rec["evidence"]["walk"] = {"to": nbr, "ok": True, "result": mv}
        except Exception as exc:  # noqa: BLE001
            rec["evidence"]["walk"] = {"to": nbr, "ok": False, "error": f"{type(exc).__name__}: {exc}"}
            rec["verdict"] = "无法判定"
            rec["reason"] = f"走不到可站邻格 {nbr}（行走单独计，不并入单技能结论）：{type(exc).__name__}: {exc}"
            return rec
        obs = c.observe(detail="full")
        tiles_all = {tuple(x["tile"]): x for x in (((obs.get("location") or {}).get("tiles")) or [])}
        refreshed = tiles_all.get(tile)
        if refreshed is not None:
            pick = refreshed
        rec["evidence"]["worldSeq_after_walk"] = obs.get("worldSeq")
        rec["evidence"]["player_after_walk"] = (obs.get("player") or {}).get("tile")
    before_kind = pick.get("kind")
    rec["evidence"]["worldSeq_before"] = obs.get("worldSeq")
    rec["evidence"]["before"] = {k: pick.get(k) for k in ("kind", "tool", "feature", "objId", "actionable", "standable")}
    # Lead m03933 裁（A2）：树 ~10 刀才倒，一次 use_tool 内部只挥 6 下 ⇒ 单发放倒树是不可能的。
    # A2 = **有界连续 use_tool（最多 3 次调用，每次内部最多 6 下 ⇒ ≤18 刀）**，直到 kind 变 stump/消失；
    # 记 calls / stamina / worldSeq / 每次的 kind；3 次后仍 tree 才判 FAIL。
    # `tool_ineffective` **不是失败证据**（它只说明这一批没打倒），只作过程留痕。
    receipts: list = []
    kind_trace: list = []
    stamina_before = (obs.get("player") or {}).get("stamina")
    r: dict = {}
    calls = 0
    for i in range(3):
        calls += 1
        obs_i = None
        try:
            r = c.use_tool(tile, tool="axe", timeout_ms=20000)
            receipts.append(r)
        except Exception as exc:  # noqa: BLE001
            # tool_ineffective 不是失败证据（只说明这一批没打倒）⇒ 记留痕后**继续下一次调用**
            receipts.append({"call": calls, "error": f"{type(exc).__name__}: {exc}"})
            rec["evidence"].setdefault("use_tool_errors", []).append(f"{type(exc).__name__}: {exc}")
            obs_i = c.observe(detail="full")
        if obs_i is None:
            obs_i = c.observe(detail="full")
        tiles_i = {tuple(x["tile"]): x for x in ((obs_i.get("location") or {}).get("tiles") or [])}
        t_i = tiles_i.get(tile)
        k_i = None if t_i is None else t_i.get("kind")
        kind_trace.append({"call": calls, "kind": k_i, "worldSeq": obs_i.get("worldSeq"),
                           "stamina": (obs_i.get("player") or {}).get("stamina")})
        obs = obs_i
        if k_i is None or k_i != before_kind:
            break
    rec["evidence"]["receipt"] = r if isinstance(r, dict) else {}
    rec["evidence"]["use_tool_calls"] = calls
    rec["evidence"]["kind_trace"] = kind_trace
    rec["evidence"]["receipts"] = receipts
    obs2 = c.observe(detail="full")
    rec["evidence"]["stamina_before"] = stamina_before
    rec["evidence"]["stamina_after"] = (obs2.get("player") or {}).get("stamina")
    rec["evidence"]["worldSeq_after"] = obs2.get("worldSeq")
    # Lead m03672：before/after 同时记 StepResult.after 的 kind 字段（0.7.41 护栏 B 靠它）
    step_after = r.get("after") if isinstance(r, dict) else None
    if isinstance(step_after, dict):
        keep = ("kind", "kind_before", "kind_after", "before_kind", "after_kind",
                "tile", "objId", "tool", "feature", "changed")
        rec["evidence"]["step_after"] = {k: step_after.get(k) for k in keep if k in step_after}
    else:
        rec["evidence"]["step_after"] = step_after
    tiles2 = {tuple(x["tile"]): x for x in ((obs2.get("location") or {}).get("tiles") or [])}
    after = tiles2.get(tile)
    rec["evidence"]["after"] = None if after is None else {
        k: after.get(k) for k in ("kind", "tool", "feature", "objId", "actionable", "standable")}
    after_kind = None if after is None else after.get("kind")
    rec["evidence"]["before_kind"], rec["evidence"]["after_kind"] = before_kind, after_kind
    if after_kind is not None and after_kind != before_kind and after_kind in ("stump", "log", "none", None):
        rec["verdict"] = "PASS"
        rec["reason"] = f"({tile[0]},{tile[1]}) kind {before_kind} → {after_kind}（calls={calls}，after 带 before/after kind）"
    elif after is None or after.get("kind") != before_kind:
        rec["verdict"] = "PASS"
        rec["reason"] = f"({tile[0]},{tile[1]}) kind {before_kind} → {after_kind}（calls={calls}；kind 已变化即算 progress）"
    else:
        rec["verdict"] = "FAIL"
        rec["reason"] = (f"连续 {calls} 次 use_tool（每次内部最多 6 下 ⇒ ≤{calls * 6} 刀）后 kind 仍是 {before_kind}"
                         f"（kind_trace={kind_trace}）—— 3 次调用仍未倒，才按失败记")
    return rec


# ---------------------------------------------------------------- 4：1 日长跑（脱离式）
def step4_launch(rec: dict, args) -> dict:
    launcher = REPO / "tools" / "start-detached-longrun.py"
    if not launcher.exists():
        rec["verdict"], rec["reason"] = "无法判定", f"起跑器不存在：{launcher}"
        return rec
    base = [PY, str(launcher), "--journal", str(SMOKE_JOURNAL), "--expect-version", EXPECT_VERSION,
            "--days", str(args.days), "--size", str(args.size),
            "--max-minutes", str(int(args.max_minutes)), "--max-days", str(args.max_days)]
    rc, out, err = sh(base + ["--dry-run"], timeout=300)
    rec["evidence"]["dry_run"] = {"rc": rc, "tail": (out + err)[-2500:]}
    if rc != 0:
        rec["verdict"], rec["reason"] = "FAIL", f"起跑器 --dry-run 退出码 {rc}（四要素没打全，见 evidence.dry_run）"
        return rec
    if args.dry_run_only:
        rec["verdict"], rec["reason"] = "无法判定", "--dry-run-only：只验了起跑器四要素，未真起跑"
        return rec
    rc2, out2, err2 = sh(base, timeout=300)
    rec["evidence"]["launch"] = {"rc": rc2, "tail": (out2 + err2)[-2500:]}
    pidf = SMOKE_JOURNAL.with_suffix(".pid")
    if rc2 != 0:
        rec["verdict"], rec["reason"] = "FAIL", f"起跑器退出码 {rc2}（2=环境缺/3=已有长跑/4=preflight 红/5=90s 内自退）"
        return rec
    for _ in range(30):
        if pidf.exists() and pidf.read_text(encoding="utf-8").strip():
            break
        time.sleep(2)
    pid = pidf.read_text(encoding="utf-8").strip() if pidf.exists() else ""
    rec["evidence"]["pid"] = pid
    rec["evidence"]["pid_file"] = str(pidf)
    rec["verdict"] = "PASS" if pid else "无法判定"
    rec["reason"] = f"起跑器已拉起（PID={pid or '未读到'}，journal={SMOKE_JOURNAL.name}）" if pid else "起跑器返回 0 但 PID 文件为空"
    return rec


def step4_wait(rec: dict, args) -> dict:
    pidf = SMOKE_JOURNAL.with_suffix(".pid")
    pid = int(pidf.read_text(encoding="utf-8").strip()) if pidf.exists() and pidf.read_text(encoding="utf-8").strip() else None
    deadline = time.time() + args.wait_minutes * 60
    last = None
    while time.time() < deadline:
        alive = pid_alive(pid) if pid else False
        n, last_ev, fin = journal_state(SMOKE_JOURNAL)
        cur = (alive, n, last_ev, fin)
        if cur != last:
            print(f"  [wait] alive={alive} journal={n}行 last={last_ev} finish={'有' if fin else '无'}")
            last = cur
        if fin:
            rec["verdict"], rec["reason"] = "PASS", f"跑出 finish（journal {n} 行）"
            break
        if pid and not alive:
            rec["verdict"], rec["reason"] = "FAIL", f"PID {pid} 消失了但账本里没有 finish（非正常结束）"
            break
        time.sleep(10)
    else:
        rec["verdict"], rec["reason"] = "无法判定", f"{args.wait_minutes} 分钟预算内没等到 finish"
    rec["evidence"] = {"pid": pid, "journal_lines": n, "last_event": last_ev, "finish": fin}
    return rec


def journal_state(path: Path) -> tuple[int, str | None, dict | None]:
    if not path.exists():
        return 0, None, None
    rows = [ln for ln in path.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
    last = fin = None
    for ln in rows:
        try:
            rec = json.loads(ln)
        except json.JSONDecodeError:
            continue
        last = rec.get("event")
        if rec.get("event") == "finish":
            fin = rec
    return len(rows), last, fin


def pid_alive(pid: int | None) -> bool:
    if not pid:
        return False
    sys.path.insert(0, str(REPO / "brain"))
    from agentfarm.bridge import pid_alive as _pa  # noqa: PLC0415
    return bool(_pa(pid))


# ---------------------------------------------------------------- 5：逐格判据（护栏 B）
def step5(rec: dict) -> dict:
    if not SMOKE_JOURNAL.exists():
        rec["verdict"], rec["reason"] = "无法判定", f"账本不存在：{SMOKE_JOURNAL}"
        return rec
    rows = [json.loads(ln) for ln in SMOKE_JOURNAL.read_text(encoding="utf-8", errors="replace").splitlines() if ln.strip()]
    ends = [r for r in rows if r.get("event") == "day_end"]
    rec["evidence"]["day_end_count"] = len(ends)
    if not ends:
        rec["verdict"], rec["reason"] = "无法判定", "账本里没有 day_end（跑批没跑完一天）"
        return rec
    # 账本层能拿到的逐格证据只可能在 outcome / stage 步记录里；先按 outcome 扫
    clear_ok, clear_with, clear_without = 0, 0, []
    for r in rows:
        if r.get("event") not in ("outcome", "stage_step", "blocked"):
            continue
        kind = r.get("kind") or r.get("stage")
        if kind not in ("clear_area", "clear", "clear_dead", "clear_neighbor", "frontier_clear"):
            continue
        if not r.get("ok"):
            continue
        clear_ok += 1
        has = bool(r.get("cleared_tiles")) or bool(r.get("kind_changes")) or bool(r.get("before") or r.get("after"))
        if has:
            clear_with += 1
        else:
            clear_without.append(r.get("tile") or r.get("tiles") or r.get("t"))
    rec["evidence"].update({"clear_area_ok_steps": clear_ok, "with_tile_evidence": clear_with,
                            "without_tile_evidence": clear_without[:10]})
    # 补（Lead 复核后修）：账本没有逐格 clear 事件时，退到 day_end.stages[] 的阶段级证据
    # —— 阶段里 ok>0 且 cleared_tiles 条数 >= ok 同样证「逐格判据活」。
    stage_ok, stage_with, stage_without = 0, 0, []
    for r in rows:
        if r.get("event") != "day_end":
            continue
        for s in (r.get("stages") or []):
            if s.get("stage") not in ("clear_area", "clear_dead", "clear_neighbor", "frontier_clear"):
                continue
            n = int(s.get("ok") or 0)
            if n <= 0:
                continue
            tiles = s.get("cleared_tiles") or []
            stage_ok += n
            if len(tiles) >= n:
                stage_with += n
            else:
                stage_without.append({"day": r.get("day"), "stage": s.get("stage"),
                                      "ok": n, "cleared_tiles": len(tiles)})
    total_ok, total_with = clear_ok + stage_ok, clear_with + stage_with
    rec["evidence"].update({"clear_stage_ok_tiles": stage_ok, "clear_stage_with_tiles": stage_with,
                            "clear_stage_without_tiles": stage_without[:10],
                            "clear_total_ok": total_ok, "clear_total_with": total_with})
    if total_ok == 0:
        rec["verdict"] = "无法判定"
        rec["reason"] = "整跑没有 clear_area 的 ok 步/ok 格 ⇒ 无法验证「逐格判据活」（不是失败，是这天/这跑没清障）"
    elif clear_without or stage_without:
        rec["verdict"] = "FAIL"
        rec["reason"] = (f"{len(clear_without) + len(stage_without)}/{total_ok} 个 clear_area ok 动作没有逐格证据"
                         f"（cleared_tiles/kind 变化）：{clear_without[:5] or stage_without[:5]}")
    else:
        rec["verdict"] = "PASS"
        rec["reason"] = f"{total_with}/{total_ok} 个 clear_area ok 动作都带逐格证据（cleared_tiles/kind 变化）"
    return rec


# ---------------------------------------------------------------- 6：跨日落盘六串
def count_six(path: Path) -> dict:
    txt = path.read_text(encoding="utf-8", errors="replace").splitlines()
    pats = {
        "newday": re.compile(r"Synchronizing 'NewDay' task"),
        "before_save": re.compile(r"Context:\s*before save"),
        "save_called": re.compile(r"SaveGame\.Save\(\) called"),
        "save_task": re.compile(r"Synchronizing 'Save' task"),
        "completed": re.compile(r"SaveGame\.Save\(\) completed without exceptions"),
        "after_save": re.compile(r"Context:\s*after save"),
    }
    out = {k: {"count": 0, "lines": []} for k in pats}
    noise = 0
    for i, ln in enumerate(txt, 1):
        m = re.match(r"^\[(\d{2}:\d{2}:\d{2})\s+([A-Z]+)\s+([A-Za-z ]+?)\]\s*(.*)$", ln)
        for k, p in pats.items():
            if p.search(ln):
                # 插件描述行（L16 类）不算：无时间戳前缀或含 " by AgentFarm " / "| v0."
                is_real = bool(m) and " by AgentFarm " not in ln and "| v0." not in ln
                if not is_real:
                    noise += 1
                    continue
                out[k]["count"] += 1
                out[k]["lines"].append(i)
    return {"counts": {k: v["count"] for k, v in out.items()}, "lines": {k: v["lines"] for k, v in out.items()},
            "excluded_plugin_description_lines": noise, "rule": L16_RULE, "total_lines": len(txt)}


def step6(rec: dict, args) -> dict:
    """跨日落盘守卫：改成调 `scratch/save-chain-check.py`（本工具不再自己数六串）。

    Lead m04100：六串计数与配对判据收口到那个离线检查器；这里只做
    "找窗口文件 → 调它 → 翻译判决 → 留原文"，判据口径只认检查器的 verdict。
    """
    src = Path(args.smapi) if args.smapi else SMOKE_SMAPI
    if not src.exists():
        # 允许直接用活的 SMAPI-latest（只读，不冻结）；冻结是收尾步骤
        src = SMAPI_LATEST
    if not src or not src.exists():
        rec["verdict"], rec["reason"] = "无法判定", "找不到 SMAPI 窗口文件，也没有 SMAPI-latest.txt"
        return rec
    checker = REPO / "scratch" / "save-chain-check.py"
    if not checker.exists():
        rec["verdict"], rec["reason"] = "无法判定", f"检查器不存在：{checker}"
        return rec
    out_json = HERE / "smoke-0741-save-chain.json"
    rc, out, err = sh([PY, "-X", "utf8", str(checker), "--smapi", str(src),
                       "--journal", str(SMOKE_JOURNAL), "--out", str(out_json)], timeout=180)
    payload: dict = {}
    if out_json.exists():
        try:
            payload = json.loads(out_json.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            payload = {}
    verdict_doc = payload.get("verdict") or {}
    counts = verdict_doc.get("counts") or {}
    rec["evidence"] = {
        "checker": str(checker), "checker_rc": rc, "checker_json": str(out_json),
        "smapi_used": str(src), "counts": counts, "checker_reasons": verdict_doc.get("reasons") or [],
        "checker_tail": (out + err)[-2500:],
    }
    if not payload:
        rec["verdict"] = "无法判定"
        rec["reason"] = f"save-chain-check 没有产出 JSON（rc={rc}）⇒ 缺失≠通过"
        return rec
    pair = "/".join(str(counts.get(k)) for k in SIX)
    verdict = verdict_doc.get("verdict")
    if verdict == "PASS":
        rec["verdict"] = "PASS"
        rec["reason"] = f"save-chain-check PASS：六串 {pair} 全配对（末次跨日已落盘）"
    elif verdict == "FAIL":
        rec["verdict"] = "FAIL"
        rec["reason"] = "save-chain-check FAIL：" + ("；".join(verdict_doc.get("reasons") or []) or f"六串 {pair}")
    else:
        rec["verdict"] = "无法判定"
        rec["reason"] = "save-chain-check 无法判定：" + ("；".join(verdict_doc.get("reasons") or []) or f"六串 {pair}")
    return rec


# ---------------------------------------------------------------- 7：两个检查器
def _journal_records(path: Path) -> list[dict]:
    recs: list[dict] = []
    for ln in path.read_text(encoding="utf-8", errors="replace").splitlines():
        ln = ln.strip()
        if not ln:
            continue
        try:
            recs.append(json.loads(ln))
        except Exception:  # noqa: BLE001
            continue
    return recs


def _slot_relief_check(recs: list[dict]) -> dict:
    """task-237 验收面：`slot_relief` 事件必须带 demand/target_free/reached。

    字段位置做容错（顶层或嵌套都认）：把整条记录的 JSON 串出来按键名搜。
    """
    rel = [r for r in recs if r.get("event") == "slot_relief"]
    if not rel:
        return {"count": 0, "status": "无法判定",
                "reason": "账本里没有 slot_relief 事件 ⇒ 空间压力通道本批没被触发（缺失≠通过）"}
    need = ("demand", "target_free", "reached")
    missing: list[dict] = []
    for i, r in enumerate(rel):
        blob = json.dumps(r, ensure_ascii=False)
        lack = [k for k in need if f'"{k}"' not in blob]
        if lack:
            missing.append({"index": i, "day": r.get("day"), "t": r.get("t"), "missing": lack})
    if missing:
        return {"count": len(rel), "status": "FAIL", "missing": missing,
                "reason": f"slot_relief 共 {len(rel)} 条，其中 {len(missing)} 条缺字段"}
    return {"count": len(rel), "status": "PASS", "reason": f"slot_relief 共 {len(rel)} 条，demand/target_free/reached 齐全"}


def _harvest_ok_check(recs: list[dict]) -> dict:
    """task-237 验收面：至少一天 `harvest` 的 ok>0（从 day_end.intent_coverage 取）。"""
    per_day: dict[str, int | None] = {}
    for r in recs:
        if r.get("event") != "day_end":
            continue
        day = str(r.get("day"))
        for e in (r.get("intent_coverage") or []):
            blob = json.dumps(e, ensure_ascii=False)
            if "harvest" not in blob:
                continue
            ok = None
            if isinstance(e, dict):
                for k in ("ok", "ok_count", "ok_steps"):
                    if isinstance(e.get(k), int):
                        ok = e[k]
                        break
            if ok is None:
                m = re.search(r'"ok"\s*:\s*(\d+)', blob)
                ok = int(m.group(1)) if m else None
            per_day[day] = ok if per_day.get(day) is None else max(per_day.get(day) or 0, ok or 0)
    if not per_day:
        return {"per_day": {}, "status": "无法判定",
                "reason": "day_end.intent_coverage 里找不到 harvest 记录 ⇒ 缺失≠通过"}
    best = max((v or 0) for v in per_day.values())
    if best > 0:
        return {"per_day": per_day, "status": "PASS", "reason": f"至少一天 harvest ok>0（最大值 {best}）"}
    return {"per_day": per_day, "status": "FAIL", "reason": f"所有天的 harvest ok 都 = 0：{per_day}"}


def step7(rec: dict) -> dict:
    if not SMOKE_JOURNAL.exists():
        rec["verdict"], rec["reason"] = "无法判定", f"账本不存在：{SMOKE_JOURNAL}"
        return rec
    rc_a, out_a, err_a = sh([PY, str(REPO / "tools" / "analyze-longrun.py"),
                             "--journal", str(SMOKE_JOURNAL), "--days", "2"], timeout=300)
    rc_v, out_v, err_v = sh([PY, str(REPO / "tools" / "verify-run3.py"),
                             "--journal", str(SMOKE_JOURNAL), "--days", "2"], timeout=300)
    rec["evidence"] = {
        "analyze_rc": rc_a, "analyze_tail": (out_a + err_a)[-3000:],
        "verify_rc": rc_v, "verify_tail": (out_v + err_v)[-3000:],
        "gaps_exists": SMOKE_GAPS.exists(),
        "gaps_path": str(SMOKE_GAPS),
        "intent_coverage_in_journal": _has_intent_coverage(SMOKE_JOURNAL),
    }
    problems: list[str] = []
    # §8 第 7 类「意图对账」：**从 analyzer 头部「未执行意图:」行取计数**，
    # 不去 grep 判据说明里的字（首跑就是这么误命中说明行、把「executed_steps=0 无原因码 ⇒ 红」当成真红）。
    m = re.search(r"未执行意图:\s*意图\s*(\d+)\s*条.*?0 步\s*(\d+)\s*条\s*/\s*其中无原因码\s*(\d+)\s*条；"
                  r"计划无对账\s*(\d+)\s*条", out_a or "")
    if not m:
        problems.append("analyzer 输出里找不到「未执行意图:」对账行 ⇒ §8 【无法判定】")
    else:
        intents, zero_step, zero_step_no_reason, no_recon = (int(x) for x in m.groups())
        rec["evidence"]["intent_reconciliation"] = {
            "intents": intents, "zero_step": zero_step,
            "zero_step_no_reason": zero_step_no_reason, "plans_no_reconciliation": no_recon}
        if zero_step_no_reason > 0:
            problems.append(f"§8 意图对账有红：0 步且无原因码 {zero_step_no_reason} 条（analyzer 头部计数）")
        if no_recon > 0:
            problems.append(f"§8 意图对账有红：计划无对账 {no_recon} 条（analyzer 头部计数）")
    # analyzer 的红清单里，只有 §8 专属红算冒烟 FAIL（`missed:intent*` / `missed:gaps*`）；
    # 日级 `missed:check:*` / `missed:env_fail` / `missed:harvest` / `missed:seeds` 等是「当天没达标」，不是 §8 管道问题。
    s8_bad: list[str] = []
    for ln in (out_a or "").splitlines():
        if ln.strip().startswith("退出码:"):
            s8_bad = [tok.strip() for tok in re.findall(r"missed:(?:intent[^,）\s]*|gaps[^,）\s]*)", ln)]
            if s8_bad:
                rec["evidence"]["s8_red_tokens"] = s8_bad
    if s8_bad:
        problems.append("§8 专属红（analyzer 红清单）：" + ", ".join(s8_bad)
                        + "（日级 missed:check:* / env_fail / harvest / seeds 不计入 §8）")
    # verify-run3 对 §8 只许出 info：若出现含 intent_coverage 的 problem 行 ⇒ 分工破坏
    for ln in (out_v or "").splitlines():
        if "intent_coverage" in ln and re.search(r"^\s*[-*]?\s*\[?问题|^\s*问题", ln):
            problems.append("verify-run3 把 intent_coverage 当 problem（应只出 info）：" + ln.strip()[:160])
    if not rec["evidence"]["intent_coverage_in_journal"]:
        problems.append("账本 day_end 里没有 intent_coverage（task-219 的字段没生效）")
    if not SMOKE_GAPS.exists():
        problems.append(f"没有生成 gaps 文件：{SMOKE_GAPS.name}")

    # ---- 新增验收面（Lead m04100）：missed:intent_no_reason 必消失 + slot_relief 字段 + 至少一天 harvest ok>0
    undetermined: list[str] = []
    no_reason_tokens = [t for t in s8_bad if "intent_no_reason" in t]
    if no_reason_tokens:
        problems.append("`missed:intent_no_reason:*` 仍出现（task-236 验收面未达标）：" + ", ".join(no_reason_tokens))
    else:
        rec["evidence"]["no_reason_check"] = "✓ analyzer 输出里没有 `missed:intent_no_reason:*`"

    try:
        recs = _journal_records(SMOKE_JOURNAL)
    except Exception as exc:  # noqa: BLE001
        recs = []
        undetermined.append(f"读账本失败：{type(exc).__name__}: {exc}")
    sr = _slot_relief_check(recs)
    rec["evidence"]["slot_relief"] = sr
    if sr["status"] == "FAIL":
        problems.append(sr["reason"] + "（task-237：必须带 demand/target_free/reached）")
    elif sr["status"] == "无法判定":
        undetermined.append(sr["reason"])
    hk = _harvest_ok_check(recs)
    rec["evidence"]["harvest_ok"] = hk
    if hk["status"] == "FAIL":
        problems.append(hk["reason"] + "（task-237：腾格后至少要有一天真的收成）")
    elif hk["status"] == "无法判定":
        undetermined.append(hk["reason"])

    if problems:
        rec["verdict"], rec["reason"] = "FAIL", "；".join(problems[:4])
    elif undetermined:
        rec["verdict"], rec["reason"] = "无法判定", "；".join(undetermined[:4])
    else:
        rec["verdict"] = "PASS"
        rec["reason"] = (f"analyzer rc={rc_a}（§8 无红，无 missed:intent_no_reason）、verify-run3 rc={rc_v}（§8 只 info）、"
                         f"intent_coverage 在场、gaps 文件已生成、slot_relief 字段齐全（{sr['count']} 条）、"
                         f"harvest ok>0（{hk['per_day']}）")
    return rec


def _has_intent_coverage(path: Path) -> bool:
    for ln in path.read_text(encoding="utf-8", errors="replace").splitlines():
        if "intent_coverage" in ln:
            return True
    return False


# ---------------------------------------------------------------- 环境体检 / 计划
def env_check(expect: str) -> dict:
    sys.path.insert(0, str(REPO / "brain"))
    rep: dict = {"tools": {}, "env": {}}
    for rel in ("tools/start-detached-longrun.py", "tools/analyze-longrun.py", "tools/verify-run3.py",
                "tools/preflight.py", "tools/stop-game.py", "scratch/_t213_probe.py"):
        rep["tools"][rel] = (REPO / rel).exists()
    bj = Path(os.environ.get("APPDATA", "")) / "StardewValley" / "AgentFarm" / "bridge.json"
    rep["env"]["bridge_json"] = str(bj)
    rep["env"]["bridge_json_exists"] = bj.exists()
    try:
        h = bridge().health(timeout=3.0)
        rep["env"]["health_ok"] = bool(h.get("ok"))
        rep["env"]["mod_version"] = h.get("modVersion")
        rep["env"]["version_matches"] = (h.get("modVersion") == expect)
        rep["env"]["hasSaveLoaded"] = (h.get("runtime") or {}).get("hasSaveLoaded")
    except Exception as exc:  # noqa: BLE001
        rep["env"]["health_ok"] = False
        rep["env"]["health_error"] = f"{type(exc).__name__}: {exc}"
    rep["env"]["smapi_latest"] = str(SMAPI_LATEST)
    rep["env"]["smapi_latest_exists"] = SMAPI_LATEST.exists()
    return rep


PLAN = [
    (1, "debug_dump crafting_recipes/Furnace 可读（无 unknown_skill、matchedCount>=1）"),
    (2, "debug_dump trigger_actions 可读（无 InvalidCastException）"),
    (3, "单技能砍树：kind==tree 的格 use_tool(axe) ⇒ tree→stump/消失，after 带前后 kind"),
    (4, "2 日长跑：start-detached-longrun --days 2 ⇒ intent_coverage + <journal>-gaps.json（跨 2 次日切）"),
    (5, "逐格判据活：clear_area 每个 ok 步都有 cleared_tiles/kind 变化"),
    (6, "跨日落盘守卫：save-chain-check.py 判六串 6/6 且末次跨日也落盘（NewDay>Save called ⇒ FAIL）"),
    (7, "analyzer §8 无红 + `missed:intent_no_reason:*` 必消失 + slot_relief 带 demand/target_free/reached 且≥1 天 harvest ok>0 + verify-run3 对 §8 只 info"),
]


def print_plan(env: dict) -> None:
    print("=" * 78)
    print(f"0.7.41 真机冒烟 7 步（期望版本 {EXPECT_VERSION}）")
    print("=" * 78)
    for n, text in PLAN:
        print(f"  {n}. {text}")
    print("-" * 78)
    print("前置文件：")
    for k, v in env["tools"].items():
        print(f"  {'OK ' if v else '缺 '} {k}")
    print("环境：")
    for k, v in env["env"].items():
        print(f"  {k} = {v}")
    print("-" * 78)
    print("phase 编排：pre(1-3) → launch(4) → wait(4 完成) → post(5-7)")
    print(f"账本：{SMOKE_JOURNAL}")
    print(f"结果：{HERE / 'smoke-0741.json'}；SMAPI 收尾冻结建议：{SMOKE_SMAPI}")


# ---------------------------------------------------------------- main
def main() -> int:
    global SMOKE_JOURNAL, SMOKE_GAPS
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", default="all", choices=("pre", "launch", "wait", "post", "all"))
    ap.add_argument("--only", default="", help="只跑指定步骤号（如 1,2,3；仅 pre/post 内生效）")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划 + 环境体检（零副作用，游戏没开也能跑）")
    ap.add_argument("--dry-run-only", action="store_true", help="launch 阶段只跑起跑器 --dry-run，不真起跑")
    ap.add_argument("--expect-version", default=EXPECT_VERSION)
    ap.add_argument("--journal", default=str(SMOKE_JOURNAL))
    ap.add_argument("--smapi", default="", help="SMAPI 窗口文件（默认用冻结的 smoke-0741-smapi-window.txt，退回活的 SMAPI-latest）")
    ap.add_argument("--wait-minutes", type=float, default=40.0)
    # 步 4 长跑参数（Lead m04100 口径：--days 2 —— 要跨 2 次日切、验证"跑尾声关框 ⇒ 末次也落盘"）
    ap.add_argument("--days", type=int, default=2)
    ap.add_argument("--size", type=int, default=5)
    ap.add_argument("--max-minutes", type=int, default=40)
    ap.add_argument("--max-days", type=int, default=3)
    ap.add_argument("--json", dest="json_out", default=str(HERE / "smoke-0741.json"))
    args = ap.parse_args()

    SMOKE_JOURNAL = Path(args.journal)
    SMOKE_GAPS = SMOKE_JOURNAL.with_name(SMOKE_JOURNAL.stem + "-gaps.json")

    env = env_check(args.expect_version)
    if args.dry_run:
        print_plan(env)
        return 0

    want = {int(x) for x in args.only.split(",") if x.strip()} if args.only else None
    results: list[dict] = []
    blocked_env = False
    # --only 时不跑无关 phase（否则 `--only 1` 也会把 step4 真起跑起来）
    if want is not None:
        phases: set[str] = set()
        if want & {1, 2, 3}:
            phases.add("pre")
        if 4 in want:
            phases |= {"launch", "wait"}
        if want & {5, 6, 7}:
            phases.add("post")
    else:
        phases = {"pre", "launch", "wait", "post"} if args.phase == "all" else {args.phase}
    print(f"[plan] phases={sorted(phases)} only={sorted(want) if want else '全部'}")

    def run_pre() -> None:
        nonlocal blocked_env
        if not env["env"].get("health_ok"):
            blocked_env = True
            print(f"[BLOCKED] 桥不可达：{env['env'].get('health_error')}")
            return
        if not env["env"].get("version_matches"):
            blocked_env = True
            print(f"[BLOCKED] 版本不匹配：modVersion={env['env'].get('mod_version')}，期望 {args.expect_version}")
            return
        if not env["env"].get("hasSaveLoaded"):
            blocked_env = True
            print("[BLOCKED] hasSaveLoaded=False（没读档）")
            return
        recs = [step1(step_record(1, PLAN[0][1])), step2(step_record(2, PLAN[1][1])), step3(step_record(3, PLAN[2][1]))]
        results.extend([r for r in recs if want is None or r["step"] in want])

    def run_post() -> None:
        recs = [step5(step_record(5, PLAN[4][1])), step6(step_record(6, PLAN[5][1]), args),
                step7(step_record(7, PLAN[6][1]))]
        results.extend([r for r in recs if want is None or r["step"] in want])

    if "pre" in phases:
        run_pre()
    if not blocked_env and "launch" in phases:
        results.append(step4_launch(step_record(4, PLAN[3][1]), args))
    if not blocked_env and "wait" in phases:
        results.append(step4_wait(step_record(4, PLAN[3][1]), args))
    if not blocked_env and "post" in phases:
        run_post()

    print("\n" + "=" * 78)
    for r in results:
        print(f"[{r['verdict']:6}] 步骤 {r['step']}：{r['name'][:60]}")
        if r.get("reason"):
            print(f"          {r['reason']}")
    print("=" * 78)

    # 分阶段跑时**合并**已有结果（否则 --phase pre→launch→post 会互相覆盖）
    out_path = Path(args.json_out)
    merged: dict[int, dict] = {}
    phases_run: list[str] = []
    if out_path.exists():
        try:
            old = json.loads(out_path.read_text(encoding="utf-8"))
            for r in (old.get("results_all_steps") or old.get("results") or []):
                merged[int(r["step"])] = r
            phases_run = [str(x) for x in (old.get("phases_run") or ([old["phase"]] if old.get("phase") else []))]
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] 旧结果读取失败（本次覆盖写）：{type(exc).__name__}: {exc}")
    for r in results:
        merged[int(r["step"])] = r
    phases_run.append(args.phase)

    print("\n=== 累计（含之前 phase 已跑的步骤）===")
    for step in range(1, 8):
        r = merged.get(step)
        print(f"  步骤 {step}: " + ("未执行" if r is None else f"[{r['verdict']}] {r['name'][:52]}"))

    payload = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "expect_version": args.expect_version,
               "journal": str(SMOKE_JOURNAL), "phase": args.phase, "phases_run": phases_run,
               "env": env, "results": results,
               "results_all_steps": [merged[k] for k in sorted(merged)]}
    try:
        out_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"结果已写 {out_path}（本次 {len(results)} 条 / 累计 {len(merged)} 条 / phases_run={phases_run}）")
    except OSError as exc:
        print(f"[warn] 结果写盘失败：{exc}")

    # 退出码只反映**本次 phase** 的结果；累计状态看上面的表与 JSON

    if blocked_env:
        return 11
    verdicts = [r["verdict"] for r in results]
    if "FAIL" in verdicts:
        return 10
    if any(v == "无法判定" for v in verdicts):
        return 12
    return 0


if __name__ == "__main__":
    sys.exit(main())
