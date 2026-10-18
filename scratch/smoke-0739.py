# -*- coding: utf-8 -*-
"""0.7.39 装机后「7 步真机冒烟」编排骨架（machine-runner 待命期准备，可提前 py_compile 自测）。

7 步来源：`docs/_release-0.7.39.md` §2 末尾（2026-10-18 按 task-225 §6 升级）：
  1. `debug_dump table=crafting_recipes key=Furnace` ⇒ 不得 `unknown_skill`，且 matchedCount>=1
  2. `debug_dump table=trigger_actions` ⇒ 能读（task-222 目标；仍 `InvalidCastException` ⇒ 本批 smoke 判红回炉）
  3. 单技能砍树：对 `kind=="tree"` 的格发 `use_tool(axe)` ⇒ 该格必须 `tree`→`stump`（或消失），且 after 带 before/after kind
  4. 跑 1 个游戏日（`tools/start-detached-longrun.py --days 1`）⇒ `day_end.intent_coverage` 出现、`<journal>-gaps.json` 生成
  5. 该日 `day_end.stages[]` 的 `clear_area` 每个 ok 步都有 `cleared_tiles`/kind 变化（P0-1 逐格判据活）
  6. 该日跨日落盘**六串 6/6 配对**（NewDay ↔ before save ↔ Save called ↔ Save task ↔ completed ↔ after save）
  7. `tools/analyze-longrun.py --days 1` 判 §8 无「意图 executed_steps==0 且无原因码」；`tools/verify-run3.py` 对 §8 只出 info

设计取舍（为什么是骨架而不是一条龙）
------------------------------------------------
* 第 3 步要动世界（挥一次斧头）；第 4 步是**长跑**（必须脱离式起跑，不能挂在 DSH 托管作业里，见条目 040/041）。
  所以拆成四个 phase，每个 phase 独立可重入、各留证据：
    pre    = 1,2,3（要求游戏在跑 + 桥健康，**最多一次** use_tool）
    launch = 4 的 `--dry-run` + 真起跑（写 `logs/longrun-smoke-0739.pid`）
    wait   = 只读轮询到 `finish` 或 PID 消失（受 `--wait-minutes` 预算约束）
    post   = 5,6,7（纯离线：账本 + SMAPI + 两个检查器）
* 任何一步 **无法判定** 时如实写 `无法判定`，绝不因为"没报错"就算过（缺失 ≠ 通过）。
* 安全底线：不 `load_save`、不 `craft/place/buy/sell`、不 dismiss 事件、不退出游戏（退出由 Lead 按 m02833 决定）。

用法
----
  python scratch\\smoke-0739.py --dry-run                 # 只打印计划 + 环境体检（无任何副作用，游戏没开也能跑）
  python scratch\\smoke-0739.py --phase pre               # 步骤 1-3
  python scratch\\smoke-0739.py --phase launch            # 步骤 4 起跑（先 --dry-run）
  python scratch\\smoke-0739.py --phase wait --wait-minutes 40
  python scratch\\smoke-0739.py --phase post              # 步骤 5-7
  python scratch\\smoke-0739.py --phase all --wait-minutes 40   # 一次跑完（分阶段之间不重启游戏）

退出码：0 = 全部 PASS；10 = 有 FAIL；11 = 环境阻塞（版本/桥/前置文件不满足）；12 = 证据缺失（无法判定）。
结果 JSON：`scratch/smoke-0739.json`（每次覆盖，含每步 verdict + 原文摘录）。
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
SMOKE_JOURNAL = LOGS / "longrun-smoke-0739.jsonl"
SMOKE_GAPS = LOGS / "longrun-smoke-0739-gaps.json"
SMAPI_LATEST = Path(os.environ.get("APPDATA", "")) / "StardewValley" / "ErrorLogs" / "SMAPI-latest.txt"
SMOKE_SMAPI = LOGS / "smoke-0739-smapi-window.txt"

# 六串（顺序即流水线顺序；第 3 串的"修正"判别式见 count_six）
SIX = ("newday", "before_save", "save_called", "save_task", "completed", "after_save")

EXPECT_VERSION = "0.7.39"
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
    before_kind = pick.get("kind")
    rec["evidence"]["tile"] = list(tile)
    rec["evidence"]["standable_neighbors"] = nbrs
    rec["evidence"]["worldSeq_before"] = obs.get("worldSeq")
    rec["evidence"]["before"] = {k: pick.get(k) for k in ("kind", "tool", "feature", "objId", "actionable", "standable")}
    try:
        r = c.use_tool(tile, tool="axe", timeout_ms=20000)
        rec["evidence"]["receipt"] = r
    except Exception as exc:  # noqa: BLE001
        rec["verdict"], rec["reason"] = "FAIL", f"use_tool 抛错：{type(exc).__name__}: {exc}"
        return rec
    obs2 = c.observe(detail="full")
    rec["evidence"]["worldSeq_after"] = obs2.get("worldSeq")
    # Lead m03672：before/after 同时记 StepResult.after 的 kind 字段（0.7.39 护栏 B 靠它）
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
        rec["reason"] = f"({tile[0]},{tile[1]}) kind {before_kind} → {after_kind}（after 带 before/after kind）"
    elif after is None or after.get("kind") != before_kind:
        rec["verdict"] = "PASS"
        rec["reason"] = f"({tile[0]},{tile[1]}) kind {before_kind} → {after_kind}（kind 已变化即算 progress；tree→stump 记 progress 不算红）"
    else:
        rec["verdict"] = "FAIL"
        rec["reason"] = f"挥了一斧头但 kind 仍是 {before_kind} —— 单技能砍树没生效（护栏 B 会因此判红）"
    return rec


# ---------------------------------------------------------------- 4：1 日长跑（脱离式）
def step4_launch(rec: dict, args) -> dict:
    launcher = REPO / "tools" / "start-detached-longrun.py"
    if not launcher.exists():
        rec["verdict"], rec["reason"] = "无法判定", f"起跑器不存在：{launcher}"
        return rec
    base = [PY, str(launcher), "--journal", str(SMOKE_JOURNAL), "--expect-version", EXPECT_VERSION]
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
    if clear_ok == 0:
        rec["verdict"] = "无法判定"
        rec["reason"] = "该日没有 clear_area 的 ok 步 ⇒ 无法验证「逐格判据活」（不是失败，是这天没清障）"
    elif clear_without:
        rec["verdict"] = "FAIL"
        rec["reason"] = f"{len(clear_without)}/{clear_ok} 个 clear_area ok 步没有逐格证据（cleared_tiles/kind 变化）：{clear_without[:5]}"
    else:
        rec["verdict"] = "PASS"
        rec["reason"] = f"{clear_ok}/{clear_ok} 个 clear_area ok 步都带逐格证据"
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
    src = Path(args.smapi) if args.smapi else SMOKE_SMAPI
    if not src.exists():
        # 允许直接用活的 SMAPI-latest（只读，不冻结）；冻结是收尾步骤
        src = SMAPI_LATEST
    if not src or not src.exists():
        rec["verdict"], rec["reason"] = "无法判定", "找不到 SMAPI 窗口文件，也没有 SMAPI-latest.txt"
        return rec
    d = count_six(src)
    rec["evidence"] = d
    counts = d["counts"]
    if counts["newday"] == 0:
        rec["verdict"] = "无法判定"
        rec["reason"] = "窗口内没有 NewDay ⇒ 这一天没跨日（长跑可能没跑到日终）"
        return rec
    if counts["newday"] != counts["save_called"]:
        rec["verdict"] = "FAIL"
        rec["reason"] = f"NewDay {counts['newday']} ≠ Save called {counts['save_called']}（每次跨日必须落盘；新版硬问题）"
        return rec
    if len(set(counts[k] for k in SIX)) != 1:
        rec["verdict"] = "FAIL"
        rec["reason"] = f"六串不齐：{counts}"
        return rec
    rec["verdict"] = "PASS"
    rec["reason"] = f"六串 {counts['newday']}/" + "/".join(str(counts[k]) for k in SIX[1:]) + f" 全配对（排除插件描述行 {d['excluded_plugin_description_lines']} 条）"
    return rec


# ---------------------------------------------------------------- 7：两个检查器
def step7(rec: dict) -> dict:
    if not SMOKE_JOURNAL.exists():
        rec["verdict"], rec["reason"] = "无法判定", f"账本不存在：{SMOKE_JOURNAL}"
        return rec
    rc_a, out_a, err_a = sh([PY, str(REPO / "tools" / "analyze-longrun.py"),
                             "--journal", str(SMOKE_JOURNAL), "--days", "1"], timeout=300)
    rc_v, out_v, err_v = sh([PY, str(REPO / "tools" / "verify-run3.py"),
                             "--journal", str(SMOKE_JOURNAL), "--days", "1"], timeout=300)
    rec["evidence"] = {
        "analyze_rc": rc_a, "analyze_tail": (out_a + err_a)[-3000:],
        "verify_rc": rc_v, "verify_tail": (out_v + err_v)[-3000:],
        "gaps_exists": SMOKE_GAPS.exists(),
        "gaps_path": str(SMOKE_GAPS),
        "intent_coverage_in_journal": _has_intent_coverage(SMOKE_JOURNAL),
    }
    problems: list[str] = []
    # §8 判红只在 analyzer：意图 executed_steps==0 且无原因码
    for ln in (out_a or "").splitlines():
        if re.search(r"executed_steps\s*[=:]\s*0", ln) and "原因码" in ln and "红" in ln:
            problems.append("analyzer 把「意图 executed_steps==0 且无原因码」判红：" + ln.strip()[:160])
    # verify-run3 对 §8 只许出 info：若出现含 intent_coverage 的 problem 行 ⇒ 分工破坏
    for ln in (out_v or "").splitlines():
        if "intent_coverage" in ln and re.search(r"^\s*[-*]?\s*\[?问题|^\s*问题", ln):
            problems.append("verify-run3 把 intent_coverage 当 problem（应只出 info）：" + ln.strip()[:160])
    if not rec["evidence"]["intent_coverage_in_journal"]:
        problems.append("账本 day_end 里没有 intent_coverage（task-219 的字段没生效）")
    if not SMOKE_GAPS.exists():
        problems.append(f"没有生成 gaps 文件：{SMOKE_GAPS.name}")
    if problems:
        rec["verdict"], rec["reason"] = "FAIL", "；".join(problems[:4])
    else:
        rec["verdict"] = "PASS"
        rec["reason"] = (f"analyzer rc={rc_a}（§8 无红）、verify-run3 rc={rc_v}（§8 只 info）、"
                         f"intent_coverage 在场、gaps 文件已生成")
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
    (4, "1 日长跑：start-detached-longrun --days 1 ⇒ intent_coverage + <journal>-gaps.json"),
    (5, "逐格判据活：clear_area 每个 ok 步都有 cleared_tiles/kind 变化"),
    (6, "跨日落盘六串 6/6 配对（NewDay/before save/Save called/Save task/completed/after save）"),
    (7, "analyzer §8 无红 + verify-run3 对 §8 只 info"),
]


def print_plan(env: dict) -> None:
    print("=" * 78)
    print(f"0.7.39 真机冒烟 7 步（期望版本 {EXPECT_VERSION}）")
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
    print(f"结果：{HERE / 'smoke-0739.json'}；SMAPI 收尾冻结建议：{SMOKE_SMAPI}")


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
    ap.add_argument("--smapi", default="", help="SMAPI 窗口文件（默认用冻结的 smoke-0739-smapi-window.txt，退回活的 SMAPI-latest）")
    ap.add_argument("--wait-minutes", type=float, default=40.0)
    ap.add_argument("--json", dest="json_out", default=str(HERE / "smoke-0739.json"))
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
        recs = [step5(step_record(5, PLAN[4][1])), step6(step_record(6, PLAN[5][1])), step7(step_record(7, PLAN[6][1]))]
        results.extend([r for r in recs if want is None or r["step"] in want])

    if args.phase in ("pre", "all"):
        run_pre()
    if not blocked_env and args.phase in ("launch", "all"):
        results.append(step4_launch(step_record(4, PLAN[3][1]), args))
    if not blocked_env and args.phase in ("wait", "all"):
        results.append(step4_wait(step_record(4, PLAN[3][1]), args))
    if not blocked_env and args.phase in ("post", "all"):
        run_post()

    if want is not None:
        results = [r for r in results if r["step"] in want]

    print("\n" + "=" * 78)
    for r in results:
        print(f"[{r['verdict']:6}] 步骤 {r['step']}：{r['name'][:60]}")
        if r.get("reason"):
            print(f"          {r['reason']}")
    print("=" * 78)

    payload = {"generated_at": time.strftime("%Y-%m-%dT%H:%M:%S"), "expect_version": args.expect_version,
               "journal": str(SMOKE_JOURNAL), "phase": args.phase, "env": env, "results": results}
    try:
        Path(args.json_out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"结果已写 {args.json_out}")
    except OSError as exc:
        print(f"[warn] 结果写盘失败：{exc}")

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
