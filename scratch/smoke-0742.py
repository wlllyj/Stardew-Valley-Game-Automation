# -*- coding: utf-8 -*-
"""0.7.42 装机后「7 步真机冒烟 + 步 8 的 0.7.42 三条硬判据」编排骨架（由 smoke-0741.py 升级，可提前 py_compile 自测）。

7 步来源：`docs/_release-0.7.41.md` §2（2026-10-18 按 Lead m04100 再升级：2 次跨日 + 落盘守卫 + 两条新验收面）：
  1. `debug_dump table=crafting_recipes key=Furnace` ⇒ 不得 `unknown_skill`，且 matchedCount>=1
  2. `debug_dump table=trigger_actions` ⇒ 能读（task-222 目标；仍 `InvalidCastException` ⇒ 本批 smoke 判红回炉）
  3. 单技能砍树（**A2 判据**）：`kind=="tree"` 的格有界连续 `use_tool(axe)` **≤3 次调用**（≈≤18 刀）直到 `kind` 变 `stump`/消失；`tool_ineffective` 只留痕、不作失败证据；3 次后仍 `tree` 才 FAIL
  4. 跑 **2 个游戏日**（`tools/start-detached-longrun.py --days 2`）⇒ `day_end.intent_coverage` 出现、`<journal>-gaps.json` 生成
  5. `day_end.stages[]` 的 `clear_area` 每个 ok 步都有 `cleared_tiles`/kind 变化（P0-1 逐格判据活）
  6. **跨日落盘守卫**：调 `scratch/save-chain-check.py`（本工具不再自己数六串）—— 六串 6/6 配对 + **末次跨日也必须落盘**（`NewDay > Save called` ⇒ FAIL；缺 SMAPI/窗口不完整 ⇒ 无法判定）
  7. `tools/analyze-longrun.py --days 2` 判 §8 无「意图 executed_steps==0 且无原因码」、且 **`missed:intent_no_reason:*` 必须消失**；`slot_relief` 事件必须带 `demand`/`target_free`/`reached` 且**至少一天 `harvest` ok>0**（task-236/237 验收面）；`tools/verify-run3.py` 对 §8 只出 info
  8. **0.7.42 三条硬判据**（`docs/_release-0.7.42.md` §3，Lead m04423）：
     8.1 **冬季可验证性**：日报告里**至少 1 天 `verified=true`**（冬 0 作物时应是 `ended_by=night`/`no_work`、`day_justified=true`），且**不得再出现** `stuck:…守卫仍说还有活：…耕地空着（手上有 N 粒种子）⇒ 该去种` 这条文案（出现即 FAIL，task-240 验收面）
     8.2 **清障吞吐**：①`clear_area` 的 blocked 里「单发 `tool_ineffective` 就封格」条数 = **0**（合法放弃必须 reason 含 `tool_ineffective_bound` 且 calls≥2）；②`farm.trees` **日降幅 > 2 棵**（`observe?detail=full` 前后差）；③`deferred_by_budget` 理由必须含「预算 N / 已砍 M」
     8.3 **沿用 0.7.41**：步 3 A2（有界多次 `use_tool`）、步 6 只认 `save-chain-check --freeze-smapi` verdict、`harvest` 冬季记【无法判定·无作物】不改判

设计取舍（为什么是骨架而不是一条龙）
------------------------------------------------
* 第 3 步要动世界（挥一次斧头）；第 4 步是**长跑**（必须脱离式起跑，不能挂在 DSH 托管作业里，见条目 040/041）。
  所以拆成四个 phase，每个 phase 独立可重入、各留证据：
    pre    = 1,2,3（要求游戏在跑 + 桥健康，**最多一次** use_tool）
    launch = 4 的 `--dry-run` + 真起跑（写 `logs/longrun-smoke-0742.pid`）
    wait   = 只读轮询到 `finish` 或 PID 消失（受 `--wait-minutes` 预算约束）
    post   = 5,6,7（纯离线：账本 + SMAPI + 两个检查器）
* 任何一步 **无法判定** 时如实写 `无法判定`，绝不因为"没报错"就算过（缺失 ≠ 通过）。
* 安全底线：不 `load_save`、不 `craft/place/buy/sell`、不 dismiss 事件、不退出游戏（退出由 Lead 按 m02833 决定）。

用法
----
  python scratch\\smoke-0742.py --dry-run                 # 只打印计划 + 环境体检（无任何副作用，游戏没开也能跑）
  python scratch\\smoke-0742.py --phase pre               # 步骤 1-3
  python scratch\\smoke-0742.py --phase launch            # 步骤 4 起跑（先 --dry-run）
  python scratch\\smoke-0742.py --phase wait --wait-minutes 40
  python scratch\\smoke-0742.py --phase post --freeze-smapi   # 步 5-7（先时点冻结 SMAPI，步 6/7 用副本判）
  python scratch\\smoke-0742.py --phase all --wait-minutes 40   # 一次跑完（分阶段之间不重启游戏）

分阶段跑时结果**按步骤号合并**进 --json（`phases_run` 记录已跑过的 phase），不会互相覆盖；
`--only` 只跑相关 phase（不会因为 `--only 1` 就把 step4 真起跑起来）。
退出码只反映**本次 phase** 的结果，累计状态看打印的"累计"表或 JSON 的 `results_all_steps`。

退出码：0 = 全部 PASS；10 = 有 FAIL；11 = 环境阻塞（版本/桥/前置文件不满足）；12 = 证据缺失（无法判定）。
结果 JSON：`scratch/smoke-0742.json`（每次覆盖，含每步 verdict + 原文摘录）。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
LOGS = REPO / "logs"
PY = sys.executable
SMOKE_JOURNAL = LOGS / "longrun-smoke-0742.jsonl"
SMOKE_GAPS = LOGS / "longrun-smoke-0742-gaps.json"
SMAPI_LATEST = Path(os.environ.get("APPDATA", "")) / "StardewValley" / "ErrorLogs" / "SMAPI-latest.txt"
SMOKE_SMAPI = LOGS / "smoke-0742-smapi-window.txt"

# 六串（顺序即流水线顺序；第 3 串的"修正"判别式见 count_six）
SIX = ("newday", "before_save", "save_called", "save_task", "completed", "after_save")

EXPECT_VERSION = "0.7.42"
L16_RULE = "有 `[HH:MM:SS LEVEL CHANNEL]` 前缀 且 不含 ` by AgentFarm ` / `| v0.`"
# 结构性限制开关（Lead m04309）：冬季第 1 天农场 0 作物 ⇒ `harvest ok>0` 物理上不可能。
# 由 main() 按 --no-crops 置位；只影响 `_harvest_ok_check` 的判法（全 0 ⇒ 无法判定·无作物，不判 FAIL）。
NO_CROPS = False


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest().upper()


def freeze_smapi(dst: Path, *, refuse_overwrite: bool = True) -> dict:
    """SMAPI 时点冻结：**一次性读源** → 写副本 → 双侧 SHA256 → BYTE_IDENTICAL。

    Lead m04172：post 一开始就冻结，然后用副本跑步 6/步 7 判据，
    JSON 记 `smapi_copy`/`smapi_sha256`/`byte_identical`，彻底消掉"跑完源文件还在长"的口径争议。
    """
    info: dict = {"smapi_copy": str(dst), "source": str(SMAPI_LATEST), "frozen": False}
    if refuse_overwrite and dst.exists():
        info["error"] = f"副本已存在，拒绝覆盖（要覆盖加 --refreeze）：{dst}"
        return info
    if not SMAPI_LATEST or not SMAPI_LATEST.exists():
        info["error"] = f"SMAPI-latest.txt 不存在：{SMAPI_LATEST}"
        return info
    try:
        # 一次性读源（游戏运行时源文件被独占，分两次读会拿到长度不一致的两半）
        blob = open(SMAPI_LATEST, "rb").read()
        dst.parent.mkdir(parents=True, exist_ok=True)
        with open(dst, "wb") as fh:
            fh.write(blob)
    except OSError as exc:
        info["error"] = f"复制失败：{type(exc).__name__}: {exc}"
        return info
    src_sha = hashlib.sha256(blob).hexdigest().upper()
    dst_sha = sha256_file(dst)
    src_st = SMAPI_LATEST.stat()
    dst_st = dst.stat()
    info.update({
        "frozen": True,
        "source_size": src_st.st_size,
        "source_mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(src_st.st_mtime)),
        "copy_size": dst_st.st_size,
        "copy_mtime": time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(dst_st.st_mtime)),
        "source_sha256": src_sha,
        "smapi_sha256": dst_sha,
        "byte_identical": src_sha == dst_sha,
        "lines": blob.count(b"\n"),
    })
    return info


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


# ---------------------------------------------------------------- 观测抓取（步 8.2② 用；只读）
def _obs_day_key(obs: dict) -> str | None:
    c = obs.get("clock") or {}
    if not c:
        return None
    return f"{c.get('season')}{c.get('day')}"


def _capture_observe(tag: str) -> dict | None:
    """只读抓一份 `observe?detail=full` 落 `scratch/smoke-0742-observe-<day>-<tag>.json`（不写世界）。"""
    try:
        obs = bridge().observe(detail="full")
    except Exception as exc:  # noqa: BLE001
        print(f"  [obs] 抓取失败：{type(exc).__name__}: {exc}")
        return None
    day = _obs_day_key(obs) or "unknown"
    p = HERE / f"smoke-0742-observe-{day}-{tag}.json"
    try:
        p.write_text(json.dumps({"captured_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
                                 "tag": tag, "observe": obs}, ensure_ascii=False), encoding="utf-8")
    except OSError as exc:
        print(f"  [obs] 写盘失败：{exc}")
        return None
    return {"path": p.name, "day": day, "trees": (obs.get("farm") or {}).get("trees")}


# ---------------------------------------------------------------- 4：1 日长跑（脱离式）
def step4_launch(rec: dict, args) -> dict:
    launcher = REPO / "tools" / "start-detached-longrun.py"
    if not launcher.exists():
        rec["verdict"], rec["reason"] = "无法判定", f"起跑器不存在：{launcher}"
        return rec
    if getattr(args, "capture_observe", False):
        ob = _capture_observe("t0")
        rec["evidence"]["obs_baseline"] = None if ob is None else ob
        if ob:
            print(f"  [obs] 起跑前基线 {ob['path']} day={ob['day']} trees={ob['trees']}")
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
    next_obs = 0.0
    while time.time() < deadline:
        alive = pid_alive(pid) if pid else False
        n, last_ev, fin = journal_state(SMOKE_JOURNAL)
        cur = (alive, n, last_ev, fin)
        if cur != last:
            print(f"  [wait] alive={alive} journal={n}行 last={last_ev} finish={'有' if fin else '无'}")
            last = cur
        if getattr(args, "capture_observe", False) and time.time() >= next_obs:
            ob = _capture_observe(f"{int(time.time()) % 100000:05d}")
            if ob:
                print(f"  [obs] {ob['path']} day={ob['day']} trees={ob['trees']}")
            next_obs = time.time() + max(30.0, float(args.observe_every))
        if fin:
            rec["verdict"], rec["reason"] = "PASS", f"跑出 finish（journal {n} 行）"
            break
        if pid and not alive:
            rec["verdict"], rec["reason"] = "FAIL", f"PID {pid} 消失了但账本里没有 finish（非正常结束）"
            break
        time.sleep(10)
    else:
        rec["verdict"], rec["reason"] = "无法判定", f"{args.wait_minutes} 分钟预算内没等到 finish"
    rec["evidence"] = {"pid": pid, "journal_lines": n, "last_event": last_ev, "finish": fin,
                       "obs_files": len(list(LOGS.glob("smoke-0742-observe-*.json")))}
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
    out_json = SMOKE_SAVECHAIN_JSON
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
    freeze_info = getattr(args, "smapi_freeze", None)
    if freeze_info:
        rec["evidence"]["smapi_freeze"] = freeze_info
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
    """task-237 验收面：至少一天 `harvest` 的 ok>0（从 day_end.intent_coverage 取）。

    结构性限制（Lead m04309）：冬季第 1 天农场 0 作物 ⇒ `harvest ok>0` 物理上不可能；
    此时（`--no-crops`）全 0 记【无法判定·无作物】，**不判 FAIL**（不许为了 FAIL 而假装有作物）。
    """
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
        if NO_CROPS:
            return {"per_day": {}, "status": "无法判定",
                    "reason": ("无法判定·无作物（--no-crops：冬季第 1 天农场 crops==0，"
                               "`day_end.intent_coverage` 里根本没有 harvest 条目 ⇒ 该子项无法判定，不判 FAIL）")}
        return {"per_day": {}, "status": "无法判定",
                "reason": "day_end.intent_coverage 里找不到 harvest 记录 ⇒ 缺失≠通过"}
    best = max((v or 0) for v in per_day.values())
    if best > 0:
        return {"per_day": per_day, "status": "PASS", "reason": f"至少一天 harvest ok>0（最大值 {best}）"}
    if NO_CROPS:
        return {"per_day": per_day, "status": "无法判定",
                "reason": ("无法判定·无作物（--no-crops：preflight baseline farm.crops==0，冬季第 1 天没有作物可收 ⇒ "
                           f"harvest ok>0 物理上不可能，不判 FAIL；读数 {per_day}）")}
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


# ---------------------------------------------------------------- 8：0.7.42 三条硬判据
GUARD_PLANT_PAT = re.compile(r"耕地空着（手上有\s*\d+\s*粒种子）⇒\s*该去种")


def _step8_winter(recs: list[dict]) -> dict:
    """8.1 冬季可验证性：≥1 天 verified=true，且旧「该去种」守卫文案不得再出现（task-240 验收面）。"""
    ends = [r for r in recs if r.get("event") == "day_end"]
    verified = [r.get("day") for r in ends if r.get("verified") is True]
    guard_hits = []
    for r in recs:
        blob = json.dumps(r, ensure_ascii=False)
        if GUARD_PLANT_PAT.search(blob):
            guard_hits.append({"event": r.get("event"), "day": r.get("day"), "t": r.get("t")})
    out: dict = {"day_end": len(ends), "verified_days": verified,
                 "guard_text_hits": guard_hits[:5], "guard_text_hits_total": len(guard_hits)}
    if not ends:
        out.update(status="无法判定", reason="账本里没有 day_end ⇒ 冬季可验证性无法判定")
    elif guard_hits:
        out.update(status="FAIL", reason=(f"旧守卫文案「耕地空着（手上有 N 粒种子）⇒ 该去种」仍出现 "
                                          f"{len(guard_hits)} 次（task-240 验收面未过）：{guard_hits[:2]}"))
    elif not verified:
        out.update(status="FAIL", reason=f"{len(ends)} 个日报告里没有一天 verified=true（冬季必须能验证）")
    else:
        out.update(status="PASS", reason=f"{len(verified)}/{len(ends)} 天 verified=true（{verified}），旧守卫文案 0 次")
    return out


def _step8_clear_illegal(recs: list[dict]) -> dict:
    """8.2① 清障：单发 tool_ineffective 就封格 = 0；合法放弃 = reason 含 tool_ineffective_bound 且 calls>=2。"""
    illegal: list[dict] = []
    insufficient: list[dict] = []
    legal: list[dict] = []
    for r in recs:
        if r.get("event") != "blocked":
            continue
        blob = json.dumps(r, ensure_ascii=False)
        if "tool_ineffective" not in blob:
            continue
        m = re.search(r'"calls"\s*:\s*(\d+)', blob)
        calls = int(m.group(1)) if m else None
        item = {"day": r.get("day"), "t": r.get("t"), "zone": r.get("zone"),
                "tile": r.get("tile") or r.get("tiles"), "calls": calls}
        if "tool_ineffective_bound" not in blob:
            illegal.append(item)
        elif calls is None or calls < 2:
            insufficient.append(item)
        else:
            legal.append(item)
    out: dict = {"blocked_tool_ineffective": len(illegal) + len(insufficient) + len(legal),
                 "illegal_single_shot": illegal[:5], "illegal_total": len(illegal),
                 "bound_without_calls_or_lt2": insufficient[:5], "insufficient_total": len(insufficient),
                 "legal_bound_giveup": legal[:5], "legal_total": len(legal)}
    if illegal:
        out.update(status="FAIL", reason=(f"{len(illegal)} 条 blocked 是「单发 tool_ineffective 就封格」"
                                          f"（task-241 验收面未过）：{illegal[:2]}"))
    elif insufficient:
        out.update(status="无法判定", reason=(f"{len(insufficient)} 条 blocked 带 bound 但 calls 缺失/<2 "
                                             f"⇒ 无法判定是否合法放弃：{insufficient[:2]}"))
    elif not legal:
        out.update(status="无法判定", reason="整跑没有 tool_ineffective 类 blocked ⇒ 该判据本批无读数（缺失≠通过）")
    else:
        out.update(status="PASS", reason=f"{len(legal)} 条 tool_ineffective 类 blocked 全部是 bound 且 calls>=2")
    return out


def _load_obs_doc(path: Path) -> dict | None:
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return None
    o = doc.get("observe") if isinstance(doc.get("observe"), dict) else doc
    for _ in range(3):
        if isinstance(o, dict) and isinstance(o.get("observe"), dict):
            o = o["observe"]
        else:
            break
    return o if isinstance(o, dict) and isinstance(o.get("clock"), dict) else None


def _step8_trees(obs_files: list[Path]) -> dict:
    """8.2② 清障吞吐：farm.trees 日降幅 > 2 棵（只用 observe?detail=full 的全场计数）。

    排序按快照里的 `captured_at`（退化到文件 mtime）——**不能按文件名**：
    `-t0` 是起跑前基线，`-07120` 是 07:12:00 那份，文件名排序会把两者弄反。
    """
    rows: list[dict] = []
    for p in sorted(obs_files):
        o = _load_obs_doc(p)
        if not o:
            continue
        trees = (o.get("farm") or {}).get("trees")
        if not isinstance(trees, int):
            continue
        cap = ""
        try:
            cap = str(json.loads(p.read_text(encoding="utf-8")).get("captured_at") or "")
        except Exception:  # noqa: BLE001
            cap = ""
        if not cap:
            try:
                cap = time.strftime("%Y-%m-%dT%H:%M:%S", time.localtime(p.stat().st_mtime))
            except OSError:
                cap = ""
        rows.append({"path": p.name, "day": _obs_day_key(o), "trees": trees,
                     "worldSeq": o.get("worldSeq"), "captured_at": cap})
    if not rows:
        return {"observations": 0, "status": "无法判定",
                "reason": ("没有可用的 observe?detail=full 快照（farm.trees 是全场计数，账本 day_end 里没有）"
                           "⇒ 清障吞吐无法判定（缺失≠通过）；wait/launch 请带 --capture-observe")}
    rows.sort(key=lambda r: (str(r["day"]), str(r["captured_at"]), str(r["path"])))
    per_day: dict[str, list[dict]] = {}
    for r in rows:
        per_day.setdefault(str(r["day"]), []).append(r)
    deltas: dict[str, dict] = {}
    for day, rr in sorted(per_day.items()):
        if len(rr) < 2:
            continue
        deltas[day] = {"first": rr[0]["trees"], "last": rr[-1]["trees"],
                       "delta": rr[-1]["trees"] - rr[0]["trees"], "n": len(rr)}
    out: dict = {"observations": len(rows), "days_with_two_obs": len(deltas), "per_day_delta": deltas,
                 "interpretation": ("日降幅 = 当天最后一份 − 当天第一份（跨天看 absolute：first/last）；"
                                    "PASS 口径 = 至少一天降幅 ≥3 棵（即 >2 棵），全 <3 才 FAIL")}
    if not deltas:
        out.update(status="无法判定",
                   reason=f"有 {len(rows)} 份观测但没有一天有 ≥2 份同一天快照 ⇒ 算不出日降幅")
        return out
    best = min(v["delta"] for v in deltas.values())
    out["best_delta"] = best
    if best <= -3:
        out.update(status="PASS", reason=f"至少一天 farm.trees 日降幅 {best} 棵（>2 棵）：{deltas}")
    else:
        out.update(status="FAIL", reason=f"所有天 farm.trees 日降幅都 ≤2 棵（最好 {best}）：{deltas}")
    return out


def _step8_budget(recs: list[dict]) -> dict:
    """8.2③ deferred_by_budget 理由必须含「预算 N / 已砍 M」。"""
    evs = [r for r in recs if r.get("event") == "deferred_by_budget"]
    if not evs:
        return {"count": 0, "status": "无法判定",
                "reason": "整跑没有 deferred_by_budget 事件 ⇒ 预算理由文案本批无读数（缺失≠通过）"}
    bad: list[dict] = []
    for r in evs:
        blob = json.dumps(r, ensure_ascii=False)
        if not (re.search(r"预算\s*\d+", blob) and re.search(r"已砍\s*\d+", blob)):
            bad.append({"day": r.get("day"), "t": r.get("t"), "blob": blob[:220]})
    out: dict = {"count": len(evs), "bad": bad[:5], "bad_total": len(bad)}
    if bad:
        out.update(status="FAIL",
                   reason=f"{len(bad)}/{len(evs)} 条 deferred_by_budget 的理由缺「预算 N / 已砍 M」：{bad[:2]}")
    else:
        out.update(status="PASS", reason=f"{len(evs)} 条 deferred_by_budget 理由都含「预算 N / 已砍 M」")
    return out


def step8(rec: dict, args) -> dict:
    journal = Path(args.journal) if getattr(args, "journal", None) else SMOKE_JOURNAL
    if not journal.exists():
        rec["verdict"], rec["reason"] = "无法判定", f"账本不存在：{journal}"
        return rec
    recs = _journal_records(journal)
    w = _step8_winter(recs)
    c = _step8_clear_illegal(recs)
    t = _step8_trees(sorted(set(LOGS.glob("smoke-0742-observe-*.json"))
                            | set(HERE.glob("smoke-0742-observe-*.json"))))
    b = _step8_budget(recs)
    rec["evidence"] = {"winter": w, "clear_throughput": c, "trees": t, "budget_reason": b,
                       "inherit_0741": ("步 3 A2 / 步 6 只认 save-chain-check verdict / harvest 冬季【无法判定·无作物】"
                                        "—— 本步未改动这三条")}
    pairs = [("8.1 冬季可验证性", w), ("8.2① 清障单发封格", c),
             ("8.2② farm.trees 日降幅", t), ("8.2③ 预算理由", b)]
    fails = [(k, v["reason"]) for k, v in pairs if v.get("status") == "FAIL"]
    undet = [(k, v["reason"]) for k, v in pairs if v.get("status") == "无法判定"]
    if fails:
        rec["verdict"], rec["reason"] = "FAIL", "；".join(f"{k}：{why}" for k, why in fails)
    elif undet:
        rec["verdict"], rec["reason"] = "无法判定", "；".join(f"{k}：{why}" for k, why in undet)
    else:
        rec["verdict"] = "PASS"
        rec["reason"] = "；".join(f"{k} ✅" for k, _v in pairs)
    return rec


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
    (8, "0.7.42 三条硬判据：8.1 冬季≥1 天 verified 且旧守卫文案 0 次 / 8.2① 单发 tool_ineffective 封格 = 0 / 8.2② farm.trees 日降幅>2 / 8.2③ 预算理由含「预算 N/已砍 M」"),
]


def print_plan(env: dict) -> None:
    print("=" * 78)
    print(f"0.7.42 真机冒烟 8 步（期望版本 {EXPECT_VERSION}）")
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
    print("phase 编排：pre(1-3) → launch(4) → wait(4 完成) → post(5-8，建议带 --freeze-smapi 先冻结 SMAPI)")
    print(f"账本：{SMOKE_JOURNAL}")
    print(f"结果：{HERE / 'smoke-0742.json'}；SMAPI 冻结副本：{SMOKE_SMAPI}")


# ---------------------------------------------------------------- main
def main() -> int:
    global SMOKE_JOURNAL, SMOKE_GAPS
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", default="all", choices=("pre", "launch", "wait", "post", "all"))
    ap.add_argument("--only", default="", help="只跑指定步骤号（如 1,2,3；仅 pre/post 内生效）")
    ap.add_argument("--dry-run", action="store_true", help="只打印计划 + 环境体检（零副作用，游戏没开也能跑）")
    ap.add_argument("--dry-run-only", action="store_true", help="launch 阶段只跑起跑器 --dry-run，不真起跑")
    ap.add_argument("--expect-version", default=EXPECT_VERSION)
    ap.add_argument("--journal", default=None, help="账本路径（默认 logs/longrun-<tag>.jsonl）")
    ap.add_argument("--smapi", default="", help="SMAPI 窗口文件（默认用冻结的 smoke-0742-smapi-window.txt；都没有才退活的 SMAPI-latest）")
    ap.add_argument("--freeze-smapi", dest="freeze_smapi", action="store_true",
                    help="phase post 一开始先把 SMAPI-latest 时点冻结成副本（源→副本、双 SHA256、BYTE_IDENTICAL），步 6/7 用副本")
    ap.add_argument("--refreeze", action="store_true", help="允许覆盖已存在的 SMAPI 副本（默认拒绝，防误复冻）")
    ap.add_argument("--wait-minutes", type=float, default=40.0)
    ap.add_argument("--tag", default="smoke-0742", help="产物前缀（默认 smoke-0742）")
    ap.add_argument("--capture-observe", dest="capture_observe", action="store_true",
                    help="launch/wait 期间只读抓 observe?detail=full（步 8.2② 需要 farm.trees 逐日差）")
    ap.add_argument("--observe-every", type=float, default=120.0, help="抓观测间隔秒（默认 120）")
    # 步 4 长跑参数（Lead m04100 口径：--days 2 —— 要跨 2 次日切、验证"跑尾声关框 ⇒ 末次也落盘"）
    ap.add_argument("--days", type=int, default=2)
    ap.add_argument("--no-crops", dest="no_crops", action="store_true",
                    help="结构性限制（Lead m04309）：baseline 农场 0 作物（冬季第 1 天）⇒ "
                         "`harvest ok>0` 物理上不可能，该子项记【无法判定·无作物】而不是 FAIL")
    ap.add_argument("--size", type=int, default=5)
    ap.add_argument("--max-minutes", type=int, default=40)
    ap.add_argument("--max-days", type=int, default=3)
    ap.add_argument("--json", dest="json_out", default=None, help="结果 JSON（默认 scratch/<tag>.json）")
    args = ap.parse_args()

    global NO_CROPS, SMOKE_SMAPI, SMOKE_SAVECHAIN_JSON
    SMOKE_JOURNAL = Path(args.journal) if args.journal else LOGS / f"longrun-{args.tag}.jsonl"
    SMOKE_GAPS = SMOKE_JOURNAL.with_name(SMOKE_JOURNAL.stem + "-gaps.json")
    SMOKE_SMAPI = LOGS / f"{args.tag}-smapi-window.txt"
    SMOKE_SAVECHAIN_JSON = HERE / f"{args.tag}-save-chain.json"
    args.json_out = args.json_out or str(HERE / f"{args.tag}.json")
    NO_CROPS = bool(args.no_crops)

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
        if want & {5, 6, 7, 8}:
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
        # Lead m04172：post 一开始就做 SMAPI 时点冻结，然后步 6/7 一律用副本判
        if args.freeze_smapi and not args.smapi:
            info = freeze_smapi(SMOKE_SMAPI, refuse_overwrite=not args.refreeze)
            args.smapi_freeze = info
            if info.get("frozen"):
                args.smapi = str(SMOKE_SMAPI)
                print(f"[freeze] SMAPI 已时点冻结 → {SMOKE_SMAPI}")
                print(f"[freeze] {info.get('copy_size')} B / {info.get('lines')} 行 / mtime {info.get('copy_mtime')}")
                print(f"[freeze] sha256 src={str(info.get('source_sha256'))[:32]}… copy={str(info.get('smapi_sha256'))[:32]}… "
                      f"BYTE_IDENTICAL={info.get('byte_identical')}")
            else:
                print(f"[freeze][warn] 冻结未完成：{info.get('error')}")
        elif not args.smapi and SMOKE_SMAPI.exists():
            args.smapi = str(SMOKE_SMAPI)
            print(f"[info] 用已有 SMAPI 冻结副本：{SMOKE_SMAPI}")
        elif not args.smapi:
            print("[warn] 没有 SMAPI 冻结副本，步 6 会退活的 SMAPI-latest（口径风险；建议加 --freeze-smapi）")
        recs = [step5(step_record(5, PLAN[4][1])), step6(step_record(6, PLAN[5][1]), args),
                step7(step_record(7, PLAN[6][1])), step8(step_record(8, PLAN[7][1]), args)]
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
    for step in range(1, 9):
        r = merged.get(step)
        print(f"  步骤 {step}: " + ("未执行" if r is None else f"[{r['verdict']}] {r['name'][:52]}"))

    payload = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "expect_version": args.expect_version,
               "journal": str(SMOKE_JOURNAL), "phase": args.phase, "phases_run": phases_run,
               "smapi_used": args.smapi or None,
               "smapi_freeze": getattr(args, "smapi_freeze", None),
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
