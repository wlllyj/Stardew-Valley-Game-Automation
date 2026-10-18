#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""【deputy-lead / task-21】0.7.45 候选树（task-15 / e347aaa）对抗验收探针。

只读生产代码；本脚本只做独立观测与判据，不修改被测树。
用法（冻结树）：
    T0745_ROOT=%TEMP%\\t0745_frozen T0745_COMMIT=e347aaa \
    PYTHONUTF8=1 python scratch\\_t0745_probe.py --only A,B,C
    ... --readings    # 追加 py_compile / 定向 / 全量单测 / dotnet 读数（慢）

段落：
  A  provenance + 版本面 + checks 10 键 + 新增字段/事件单列 + 公式未动
  B  账本独立复算（263/217/40/17）+ 0.7.45 功能重放（六口径快照/is_justified_end/
     burst 标签/卡1兜底口径/sleep_guard 拒绝 no_work/新字段导出）
  C  对抗通道 a~j（≥8 组，判红/判绿/【无法判定】三态）
  D  变异两列（作者脚本实测 + 我方脚本实测；读证据文件，核对条数）
判据全部用本报告自己的实现，不抄作者脚本。
"""
from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(os.environ.get("T0745_ROOT") or Path(__file__).resolve().parents[1])
REPO = Path(__file__).resolve().parents[1]
COMMIT = os.environ.get("T0745_COMMIT", "e347aaa")
BASELINE_COMMIT = "37cac51"          # 0.7.44 冻结树
PY = sys.executable

A8_LEDGER = REPO / "logs" / "longrun-runA8-0743.jsonl"
SMOKE_LEDGER = REPO / "logs" / "longrun-smoke-0744.jsonl"
GAPS_JSON = REPO / "logs" / "gaps.json"

CHECKS_BASELINE = (
    "slept_by_us", "no_blocking_modal", "no_hard_failures",
    "unreachable_within_bound", "refused_within_bound", "no_unmet_stages",
    "crops_watered", "watered_outdoor", "day_justified", "zero_action_evidenced",
)
JUSTIFIED_END_REASONS = ("night", "stamina", "no_work")
HONEST_EXHAUSTED_END_REASONS = ("resume_exhausted",)
TASK15_MARKERS = (
    "HONEST_EXHAUSTED_END_REASONS", "def _ledger_pending", "def _pending_snapshot",
    "def _standable_next_to", "pending_executable=rep.pending_executable",
    'where="plot_exhausted_burst"', 'where="switch_limit"',
    "keep_working", "resume_stall_tiles", "stage_midway_leftover",
)
NEW_DAY_FIELDS = (
    "pending_ledger", "pending_guard", "pending_stalled", "pending_executable",
    "pending_blocked", "pending_unobserved", "stage_midway_leftover",
)

RESULTS = {"PASS": 0, "FAIL": 0, "SKIP": 0, "INFO": 0}
FAILS: list[str] = []


def check(tag: str, ok: bool, detail: str = "") -> bool:
    if ok:
        RESULTS["PASS"] += 1
        print(f"  PASS  {tag}" + (f"  [{detail}]" if detail else ""))
    else:
        RESULTS["FAIL"] += 1
        FAILS.append(tag)
        print(f"  FAIL  {tag}  [{detail}]")
    return ok


def info(tag: str, detail: str = "") -> None:
    RESULTS["INFO"] += 1
    print(f"  INFO  {tag}" + (f"  [{detail}]" if detail else ""))


def skip(tag: str, detail: str = "") -> None:
    RESULTS["SKIP"] += 1
    print(f"  SKIP  {tag}" + (f"  [{detail}]" if detail else ""))


def read(path: Path) -> str:
    return path.read_text(encoding="utf-8", errors="replace")


def git_show(rev: str, path: str) -> str:
    out = subprocess.run(["git", "-C", str(REPO), "show", f"{rev}:{path}"],
                         capture_output=True)
    if out.returncode != 0:
        return ""
    return out.stdout.decode("utf-8", "replace")


def load_jsonl(path: Path) -> list[dict]:
    rows = []
    for line in read(path).splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return rows


def day_ends(rows: list[dict]) -> list[dict]:
    return [r for r in rows if r.get("event") == "day_end"]


def day_text(row: dict) -> str:
    if row.get("day_text"):
        return str(row["day_text"])
    d = row.get("day")
    return str(d or "")


def day_range(rows: list[dict], idx: int) -> tuple[int, int]:
    starts = [i for i, r in enumerate(rows) if r.get("event") == "day_end"]
    lo = starts[idx - 1] if idx > 0 else 0
    return lo, starts[idx]


# ------------------------------------------------------------------ A 段
def _blob_sha(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()


def _src(tree: Path, rel: str) -> str:
    p = tree / rel
    return p.read_text(encoding="utf-8", errors="replace") if p.exists() else ""


def _journal_names(src: str) -> list[str]:
    names = set()
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                and node.func.attr == "_journal" and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            names.add(node.args[0].value)
    return sorted(names)


def _dayreport_fields(src: str) -> list[str]:
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    fields = []
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "DayReport":
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    fields.append(stmt.target.id)
    return fields


def _checks_keys(src: str) -> list[str]:
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    for node in ast.walk(tree):
        if (isinstance(node, ast.Assign) and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Attribute)
                and node.targets[0].attr == "checks"
                and isinstance(node.value, ast.Dict)):
            return [k.value for k in node.value.keys if isinstance(k, ast.Constant)]
    return []


def _norm_lines(src: str, needle: str, span: int = 3) -> list[str]:
    lines = src.splitlines()
    for i, line in enumerate(lines):
        if needle in line:
            return [x.strip() for x in lines[max(0, i - span):i + span + 1]]
    return []


def case_a() -> None:
    print("\n== A 段：provenance / 版本面 / 字段与公式 ==")
    # A0 provenance：全量 tracked blob 对照
    tracked = subprocess.run(["git", "-C", str(REPO), "ls-tree", "-r", COMMIT],
                             capture_output=True)
    if tracked.returncode != 0:
        skip("A0 provenance", "git ls-tree 失败")
        return
    rows = [ln.split("\t", 1) for ln in tracked.stdout.decode().splitlines() if "\t" in ln]
    missing = []  # type: list[str]
    mismatch = []  # type: list[str]
    eol_fixed = 0
    for meta, rel in rows:
        _mode, _typ, sha = meta.split()
        p = ROOT / rel
        if not p.exists():
            missing.append(rel)
            continue
        data = p.read_bytes()
        if _blob_sha(data) == sha:
            continue
        if rel.endswith((".ps1", ".bat", ".cmd")) or b"\r\n" in data:
            norm = data.replace(b"\r\n", b"\n")
            if _blob_sha(norm) == sha:
                eol_fixed += 1
                continue
        mismatch.append(rel)
    check("A0 provenance 全量 blob", not missing and not mismatch,
          f"commit={COMMIT} 追踪 {len(rows)}、缺失 {len(missing)}、不符 {len(mismatch)}、eol 展开 {eol_fixed}"
          + (f"；缺失样例 {missing[:3]}" if missing else "")
          + (f"；不符样例 {mismatch[:3]}" if mismatch else ""))
    for rel in ("brain/agentfarm/longrun.py", "tests/test_longrun.py",
                "tests/_mutate_t15_justified.py"):
        p = ROOT / rel
        if not p.exists():
            check(f"A0b 关键文件 {rel}", False, "缺失")
            continue
        want = subprocess.run(["git", "-C", str(REPO), "rev-parse", f"{COMMIT}:{rel}"],
                              capture_output=True).stdout.decode().strip()
        got = _blob_sha(p.read_bytes().replace(b"\r\n", b"\n"))
        check(f"A0b 关键文件 {rel}", got == want, f"blob {got[:12]} / {want[:12]}")

    longrun = _src(ROOT, "brain/agentfarm/longrun.py")
    base = git_show(BASELINE_COMMIT, "brain/agentfarm/longrun.py")
    if not longrun:
        skip("A1 版本面", "被测树缺 longrun.py")
        return
    # A1 版本面：0.7.45 尚未冻结（版本载体仍 0.7.44）
    manifest = _src(ROOT, "mod/AgentFarm.Bridge/manifest.json")
    bridge = _src(ROOT, "brain/agentfarm/bridge.py")
    ver = "0.7.45" if "0.7.45" in manifest and 'MOD_VERSION_EXPECTED = "0.7.45"' in bridge else "0.7.44"
    info("A1 版本面", f"manifest/bridge 版本载体 = {ver}；task-15 只改 brain/tests ⇒ "
                     "0.7.45 冻结九步未走、版本判定【无法判定】（NIT，不能当已冻结树）")

    # A2 checks 10 键 + day_justified 证据参数
    keys = _checks_keys(longrun)
    check("A2 checks 10 键字面集", list(keys) == list(CHECKS_BASELINE),
          f"got {len(keys)} / want {len(CHECKS_BASELINE)}")
    check("A2b day_justified 带 pending_executable 证据",
          "pending_executable=rep.pending_executable" in longrun
          and "is_justified_end(" in longrun)

    # A3 新增字段 / 事件单列（对照 0.7.44 冻结树）
    old_fields = _dayreport_fields(base) if base else []
    new_fields = _dayreport_fields(longrun)
    added_fields = [f for f in new_fields if f not in old_fields]
    removed_fields = [f for f in old_fields if f not in new_fields]
    check("A3 新增 DayReport 字段单列", removed_fields == []
          and sorted(added_fields) == sorted(NEW_DAY_FIELDS),
          f"added={added_fields} removed={removed_fields}")
    old_ev = _journal_names(base) if base else []
    new_ev = _journal_names(longrun)
    added_ev = [e for e in new_ev if e not in old_ev]
    removed_ev = [e for e in old_ev if e not in new_ev]
    info("A3b 新增 journal 事件名", f"added={added_ev} removed={removed_ev}")
    check("A3c 无新增/删除 journal 事件名（复用 no_progress_burst/stage_midway_leftover）",
          removed_ev == [] and added_ev == [])

    # A4 task-15 标记
    missing_markers = [m for m in TASK15_MARKERS if m not in longrun]
    check("A4 task-15 代码标记", missing_markers == [], f"缺 {missing_markers}")

    # A5 未动公式：no_unmet_stages / JUSTIFIED_END_REASONS / 护栏 B
    if base:
        try:
            tree = ast.parse(longrun)
            checks_node = next(n for n in ast.walk(tree) if isinstance(n, ast.Assign)
                               and isinstance(n.targets[0], ast.Attribute)
                               and n.targets[0].attr == "checks")
            seg_new = ast.get_source_segment(longrun, checks_node) or ""
            tree_b = ast.parse(base)
            checks_node_b = next(n for n in ast.walk(tree_b) if isinstance(n, ast.Assign)
                                 and isinstance(n.targets[0], ast.Attribute)
                                 and n.targets[0].attr == "checks")
            seg_old = ast.get_source_segment(base, checks_node_b) or ""
            nou_new = [ln.strip() for ln in seg_new.splitlines() if "no_unmet_stages" in ln or "unmet_leftover ==" in ln]
            nou_old = [ln.strip() for ln in seg_old.splitlines() if "no_unmet_stages" in ln or "unmet_leftover ==" in ln]
            check("A5a no_unmet_stages 公式未动", nou_new == nou_old, f"{nou_new} vs {nou_old}")
            guard_new = _norm_lines(longrun, "cleared_tiles", 4)
            guard_old = _norm_lines(base, "cleared_tiles", 4)
            check("A5b 护栏 B（cleared_tiles）语义未动", guard_new == guard_old,
                  "源码切片一致" if guard_new == guard_old else "切片不同（需人工看 diff）")
            j_new = [ln.strip() for ln in longrun.splitlines() if "JUSTIFIED_END_REASONS =" in ln]
            j_old = [ln.strip() for ln in base.splitlines() if "JUSTIFIED_END_REASONS =" in ln]
            check("A5c 旧白名单 literal 未动", j_new == j_old, f"{j_new} vs {j_old}")
        except (StopIteration, SyntaxError) as exc:
            skip("A5 公式未动", f"AST 提取失败：{exc}")
    else:
        skip("A5 公式未动", "无 0.7.44 基线源码（git show 失败）")

    # A6 分析工具是否收录新字段（防账本新字段无人读）
    analyzer = _src(ROOT, "tools/analyze-longrun.py")
    info("A6 analyzer 收录", f"stage_midway_leftover={'stage_midway_leftover' in analyzer} "
                            f"pending_executable={'pending_executable' in analyzer} "
                            f"pending_ledger={'pending_ledger' in analyzer}")
    # A7 A8 旧账本：ok=0 & already>0 阶段（task-10 #1 口径）
    if A8_LEDGER.exists():
        rows8 = load_jsonl(A8_LEDGER)
        stages = [s for r in day_ends(rows8) for s in (r.get("stages") or [])]
        interesting = [s for s in stages if int(s.get("ok") or 0) == 0 and int(s.get("already") or 0) > 0]
        already_sum = sum(int(s.get("already") or 0) for s in stages)
        check("A7 task-10 #1：A8 里 ok=0&already>0 阶段数=0", len(interesting) == 0,
              f"stages={len(stages)} 命中={len(interesting)} already 总步数={already_sum}；"
              "verify-run3.py:1104/:1122 只累加/单列 ok，A9 必须并列读 already/attempted_ok")
    else:
        skip("A7 task-10 #1", "缺 A8 账本")

    if args.readings:
        _readings()


def _readings() -> None:
    env = dict(os.environ, PYTHONUTF8="1", PYTHONPATH=str(ROOT / "brain"))
    code = subprocess.run([PY, "-m", "py_compile", str(ROOT / "brain/agentfarm/longrun.py")],
                          capture_output=True, env=env)
    check("A4a py_compile", code.returncode == 0, f"rc={code.returncode}")
    focused = subprocess.run([PY, "-m", "unittest", "tests.test_longrun.TestTask15PendingCaliber"],
                             cwd=str(ROOT), capture_output=True, env=env)
    out = focused.stdout.decode("utf-8", "replace") + focused.stderr.decode("utf-8", "replace")
    m = re.search(r"Ran (\d+) tests", out)
    check("A4b 定向 TestTask15PendingCaliber", focused.returncode == 0 and m is not None,
          (m.group(0) if m else "无 Ran 行") + (" / OK" if "\nOK" in out else " / 非 OK"))
    full = subprocess.run([PY, "-m", "unittest", "discover", "-s", "tests"],
                          cwd=str(ROOT), capture_output=True, env=env)
    text = full.stdout.decode("utf-8", "replace") + full.stderr.decode("utf-8", "replace")
    m = re.search(r"Ran (\d+) tests", text)
    check("A4c 全量单测", full.returncode == 0 and "\nOK" in text,
          (m.group(0) if m else "无 Ran 行") + (" / OK" if "\nOK" in text else " / 非 OK"))


# ------------------------------------------------------------------ B 段
_TL = None
_LR = None


def fixtures():
    global _TL, _LR
    if _TL is not None:
        return _TL, _LR
    for p in (str(ROOT / "tests"), str(ROOT / "brain")):
        if p not in sys.path:
            sys.path.insert(0, p)
    import test_longrun as TL  # type: ignore
    from agentfarm import longrun as LR  # type: ignore
    _TL, _LR = TL, LR
    return TL, LR


def _mk_run(w):
    TL, _ = fixtures()
    client = TL._CountingClient(w)
    worker = TL.FarmWorker(client, log=lambda *_: None)
    run = TL.make_run(w, target_days=1, max_days=1,
                      client_factory=lambda: client, worker_factory=lambda c: worker)
    run.worker = worker
    run.client = client
    return run


def _fresh(kind: str = "winter", day: int = 26):
    TL, LR = fixtures()
    return TL.DayReport(day_key=(kind, 1, day), started_at=0.0)


def _synthetic_tiles(n: int, base: int = 300, y: int = 400) -> list:
    return [(base + i, y) for i in range(n)]


def _load_state(run, blocked: int, stalled: int, guard: int) -> None:
    """按账本口径摆状态：universe = blocked + stalled + guard。"""
    tiles = _synthetic_tiles(blocked + stalled + guard)
    run.leftover_targets = set(tiles)
    b = tiles[:blocked]
    s = tiles[blocked:blocked + stalled]
    g = tiles[blocked + stalled:]
    for t in b:
        run.blocked[t] = "blocked_tile"
    run.resume_stall_tiles = set(s)
    return g  # type: ignore[return-value]


def check_ledger_arithmetic() -> None:
    print("\n== B1 段：冒烟账本独立复算（263/217/40/17） ==")
    if not SMOKE_LEDGER.exists():
        skip("B1 冒烟账本复算", f"缺 {SMOKE_LEDGER}")
        return
    rows = load_jsonl(SMOKE_LEDGER)
    ends = day_ends(rows)
    if len(ends) < 2:
        skip("B1 冒烟账本复算", f"day_end 只有 {len(ends)} 条")
        return
    ends.sort(key=lambda r: str(r.get("day_text") or r.get("day")))
    d26, d27 = ends[0], ends[1]

    pe = [r for r in rows if r.get("event") == "plot_exhausted"]
    pend = [int(r.get("pending") or 0) for r in pe]
    stalled_totals = [int(r.get("stalled_total") or 0) for r in pe if r.get("stalled_total") is not None]
    burst26 = [r for r in rows if r.get("event") == "plot_exhausted_burst"]
    nb = [r for r in rows if r.get("event") == "no_progress_burst" and r.get("exhausted")]
    pending26 = pend[0] if pend else 0
    stalled26 = max([t for t in stalled_totals if t <= 263] or [0])
    check("B1a 冬26 pending=263、stalled=261（残余 2）",
          pending26 == 263 and stalled26 == 261 and burst26,
          f"pending={pending26} stalled={stalled26} 残余={pending26 - stalled26} burst={len(burst26)}")

    # 冬 26 阶段末轮窗口：找 leftover_executable+leftover_blocked == 223 的那一轮；263 − 223 = 40 格无坐标
    stages26 = d26.get("stages") or []
    win = [s for s in stages26
           if int(s.get("leftover_executable") or 0) + int(s.get("leftover_blocked") or 0) == 223]
    exec26 = int(win[0].get("leftover_executable") or 0) if win else 0
    blk26 = int(win[0].get("leftover_blocked") or 0) if win else 0
    mid_events = [r for r in rows if r.get("event") == "stage_midway_leftover"]
    mid26 = [r for r in mid_events if int(r.get("round") or 0) == 39]
    check("B1b 冬26 某轮窗口 223（211+12）⇒ 40 格【无法判定】+ 中途轮留痕",
          exec26 == 211 and blk26 == 12 and (263 - exec26 - blk26) == 40 and mid26,
          f"exec={exec26} blocked={blk26} 窗口和={exec26 + blk26} 263-窗口={263 - exec26 - blk26} "
          f"stages={len(stages26)} midway={[(m.get('round'), m.get('leftover')) for m in mid_events]}")

    # 冬 27：220 = round0 片外累计（stage_midway_leftover L304）；挡死 3 格 ⇒ 217
    mid27 = [r for r in mid_events if int(r.get("leftover") or 0) == 220]
    unreachable = [r for r in rows if r.get("event") == "unreachable_summary"]
    blocked27 = (unreachable[-1].get("tiles") or []) if unreachable else []
    ev27 = nb[0] if nb else {}
    pending27 = int(ev27.get("pending") or (pend[-1] if pend else 0))
    check("B1c 冬27 217 = 220 − 3 挡死格", pending27 == 217 and len(blocked27) == 3 and mid27,
          f"pending={pending27} round0={mid27[0].get('leftover') if mid27 else None} "
          f"挡死={blocked27} stalled={ev27.get('stalled_tiles')}")

    # gaps 17 格（tree12/grass3/stone1/twig1）
    gaps_files = sorted(REPO.glob("logs/longrun-smoke-0744-gaps.json"))
    if gaps_files:
        try:
            data = json.loads(read(gaps_files[0]))
            gaps = data.get("gaps") or data
            detail = {str(g.get("kind")): int(g.get("count") or 0) for g in gaps
                      if isinstance(g, dict)}
            total = sum(detail.values())
        except (json.JSONDecodeError, TypeError, ValueError):
            total, detail = 0, "解析失败"
        check("B1d 挡死 17 格逐格（gaps.json）", total == 17, f"total={total} detail={detail}")
    else:
        info("B1d 挡死 17 格", "缺 gaps.json（归属表见 log-analyst 文档）")


def check_replay_045() -> None:
    print("\n== B2 段：0.7.45 功能重放（六口径快照 / day_justified 证据） ==")
    try:
        TL, LR = fixtures()
    except Exception as exc:  # noqa: BLE001
        skip("B2 功能重放", f"夹具导入失败：{exc}")
        return
    w = TL.FakeWorld(weeds=0, seeds=0, money=0)
    run = _mk_run(w)
    iso = LR.is_justified_end

    # B2a 冬 26 形态：universe=280（17 挡死 + 261 停滞 + 2 未观察）
    guard = _load_state(run, blocked=17, stalled=261, guard=2)
    snap = run._pending_snapshot(w.obs())
    check("B2a 冬26 重放六口径（guard=2/exec=0/unobs=2/ledger=280）",
          snap["ledger"] == 280 and snap["guard"] == 2 and snap["executable"] == 0
          and snap["unobserved"] == 2 and snap["blocked"] == 278 and snap["stalled"] == 261,
          f"{snap}")
    check("B2b 冬26 守卫口径从 263 收到 2（残余=未观察/无法归类）、原始账本=263",
          len(run._pending_work()) == 2 and len(run._ledger_pending()) == 263,
          f"pending_work={len(run._pending_work())} ledger={len(run._ledger_pending())}")
    check("B2c 冬26 day_justified 认证据（exec=0 ⇒ True；旧口径 False）",
          iso("sleep", "resume_exhausted:回片区 261 格", pending_executable=0)
          and not iso("sleep", "resume_exhausted:回片区 261 格"))

    # B2d 冬 27 形态：universe=220（3 挡死 + 217 停滞），guard=0
    w2 = TL.FakeWorld(weeds=0, seeds=0, money=0)
    run2 = _mk_run(w2)
    _load_state(run2, blocked=3, stalled=217, guard=0)
    snap2 = run2._pending_snapshot(w2.obs())
    check("B2d 冬27 重放（ledger=220/guard=0/exec=0/ledger_pending=217）",
          snap2["ledger"] == 220 and snap2["guard"] == 0 and snap2["executable"] == 0
          and len(run2._ledger_pending()) == 217,
          f"{snap2} ledger_pending={len(run2._ledger_pending())}")
    check("B2e 冬27 day_justified=True（当天确实无当前可执行格）",
          iso("sleep", "resume_exhausted:回片区 217 格", pending_executable=snap2["executable"]))

    # B2f 观测不可用 fail-closed：executable=guard>0 ⇒ 不放行
    w3 = TL.FakeWorld(weeds=0, seeds=0, money=0)
    run3 = _mk_run(w3)
    _load_state(run3, blocked=1, stalled=1, guard=3)
    blind = run3._pending_snapshot(None)
    check("B2f 观测不可用 ⇒ executable=guard 且 day_justified=False",
          blind["executable"] == blind["guard"] == 3 and blind["unobserved"] == 0
          and not iso("sleep", "resume_exhausted:x", pending_executable=blind["executable"]),
          f"{blind}")
    # B2g 有可执行格（世界里有可清障格）⇒ day_justified=False
    w4 = TL.FakeWorld(weeds=0, seeds=0, money=0)
    w4.blockers[(63, 14)] = "weed"
    w4.player_tile = [62, 14]
    run4 = _mk_run(w4)
    run4.leftover_targets = {(63, 14)}
    run4.leftover_area = {(63, 14): "field_nw"}
    snap4 = run4._pending_snapshot(w4.obs())
    check("B2g 有 1 格可执行 ⇒ day_justified=False（不洗白真活）",
          snap4["executable"] == 1 and not iso("sleep", "resume_exhausted:x",
                                               pending_executable=snap4["executable"]),
          f"{snap4}")

    # B2h 卡1 兜底口径：_dead_end_pending 仍用原始账本
    w5 = TL.FakeWorld(weeds=0, seeds=0, money=0)
    run5 = _mk_run(w5)
    run5.leftover_targets = {(90, 90), (91, 90)}
    run5.resume_stall_tiles = {(90, 90), (91, 90)}
    check("B2h _pending_work 空、_dead_end_pending 非空（卡1/5 兜底不失效）",
          run5._pending_work() == [] and run5._dead_end_pending() == [(90, 90), (91, 90)],
          f"dead_end_pending={run5._dead_end_pending()}")

    # B2i burst 收尾标签（功能）：有可执行格时仍 resume_exhausted 且不 VERIFIED
    w6 = TL.FakeWorld(weeds=0, seeds=0, money=0)
    w6.blockers[(63, 14)] = "weed"
    w6.player_tile = [62, 14]
    run6 = _mk_run(w6)
    rep = _fresh("winter", 26)
    run6.leftover_targets = {(63, 14)}
    run6.leftover_area = {(63, 14): "field_nw"}
    run6._do_sleep = lambda obs, rep, why, **kw: ("sleep", why)  # type: ignore[assignment]
    run6._resume_exhausted(w6.obs(), rep, plot=None, where="plot_exhausted_burst")
    snap6 = run6._pending_snapshot(w6.obs())
    ev6 = [e for e in run6.entries if e.get("event") == "no_progress_burst"]
    check("B2i burst 收尾=resume_exhausted、证据字段齐、有活⇒不 VERIFIED",
          str(rep.ended_reason).startswith("resume_exhausted:")
          and not str(rep.ended_reason).startswith("stuck:")
          and ev6 and {"pending_ledger", "pending_executable", "pending_unobserved",
                       "pending_guard", "pending_stalled"} <= set(ev6[-1])
          and snap6["executable"] >= 1
          and not iso(rep.ended_by, rep.ended_reason, pending_executable=snap6["executable"]),
          f"reason={str(rep.ended_reason)[:40]} exec={snap6['executable']} ev={bool(ev6)}")

    # B2j 源段：burst / switch_limit 不再写 stuck:（注释里的历史说明不算）
    src = _src(ROOT, "brain/agentfarm/longrun.py")
    burst_seg = [ln for ln in _norm_lines(src, 'where="plot_exhausted_burst"', 10)
                 if not ln.startswith("#")]
    check("B2j burst 源段走 _resume_exhausted、代码里无 stuck:",
          any("_resume_exhausted" in x for x in burst_seg)
          and not any('stuck:' in x for x in burst_seg), f"{burst_seg}")

    # B2k sleep_guard：只剩挡死格拒绝 no_work
    w7 = TL.FakeWorld(weeds=0, seeds=0, money=0)
    run7 = _mk_run(w7)
    run7.leftover_targets = {(90, 90)}
    run7.resume_stall_tiles = {(90, 90)}
    try:
        ok7, kind7, msg7 = run7.sleep_guard(w7.obs())
        check("B2k 只剩挡死格 ⇒ sleep_guard 拒绝 no_work",
              (not ok7) and kind7 == "keep_working", f"kind={kind7} msg={msg7[:60]}")
    except Exception as exc:  # noqa: BLE001
        skip("B2k sleep_guard 拒绝 no_work", f"直接调用失败：{exc}")

    # B2l 新字段导出 & stage_midway_leftover 结构（数据流，非执行）
    rep2 = _fresh()
    rep2.pending_ledger = 220
    rep2.pending_guard = 0
    rep2.pending_executable = 0
    rep2.stage_midway_leftover.append({"stage": "clear_area", "tiles": 12, "leftover": 220, "round": 1})
    d = rep2.as_dict()
    check("B2l 新字段导出 as_dict + midway 明细", all(k in d for k in NEW_DAY_FIELDS)
          and d["stage_midway_leftover"][0]["leftover"] == 220,
          f"缺={[k for k in NEW_DAY_FIELDS if k not in d]}")
    # 结构：extend 只在 last leftover==0 分支内
    extend_lines = [ln.strip() for ln in src.splitlines() if "rep.stage_midway_leftover.extend" in ln]
    branch_ok = "if last is None or int(last.get(\"leftover\") or 0) != 0:" in src
    check("B2m stage_midway_leftover 只在遮蔽形态落（结构判据）",
          branch_ok and len(extend_lines) == 1, f"extend 行={extend_lines} branch={branch_ok}")

    # B2n 两口径：_plot_has_work 不把「回去看过、拿不出目标」的格算活（stalled 从守卫口径剔除）
    w8 = TL.FakeWorld(weeds=0, seeds=10, money=100, water_left=40)
    w8.dirt = {(60, 10)}
    w8.crops = {(60, 10): {"ripe": False, "watered": False}}
    w8.player_tile = [62, 14]
    run8 = _mk_run(w8)
    try:
        obs8 = w8.obs()
        base_has = bool(run8._plot_has_work(obs8, [(60, 10)]))
        run8.resume_stall_tiles = {(60, 10)}
        stalled_has = bool(run8._plot_has_work(obs8, [(60, 10)]))
        check("B2n _plot_has_work 剔除停滞格（守卫口径不认 217 旧账）",
              base_has and not stalled_has, f"基线={base_has} 停滞={stalled_has}")
    except Exception as exc:  # noqa: BLE001
        skip("B2n _plot_has_work 剔除停滞格", f"直接调用失败：{exc}")


# ------------------------------------------------------------------ C 段
def judge_resume_evidence(day: dict) -> str:
    checks = day.get("checks") or {}
    if "day_justified" not in checks:
        return "undecidable"
    reason = str(day.get("ended_reason") or "")
    prefix = reason.split(":", 1)[0]
    if checks.get("day_justified") and prefix == "stuck":
        return "red"
    if checks.get("day_justified") and prefix in HONEST_EXHAUSTED_END_REASONS:
        ex = day.get("pending_executable")
        if ex is None or int(ex) > 0:
            return "red"
    if not checks.get("day_justified") and prefix in JUSTIFIED_END_REASONS:
        return "red"
    return "green"


def judge_snapshot_invariants(day: dict) -> str:
    keys = ("pending_ledger", "pending_guard", "pending_blocked",
            "pending_executable", "pending_unobserved")
    if any(k not in day for k in keys):
        return "undecidable"
    ledger = int(day["pending_ledger"] or 0)
    guard = int(day["pending_guard"] or 0)
    blocked = int(day["pending_blocked"] or 0)
    ex = int(day["pending_executable"] or 0)
    un = int(day["pending_unobserved"] or 0)
    if ledger != guard + blocked or guard != ex + un:
        return "red"
    if ex == 0 and un == 0 and guard > 0:
        return "red"                     # 伪造 executable=0 且 unobserved 也归零
    return "green"


def judge_payload(checks: dict) -> str:
    if not checks:
        return "undecidable"
    if any(k not in checks for k in CHECKS_BASELINE):
        return "undecidable"
    if len(checks) != len(CHECKS_BASELINE):
        return "red"
    return "green"


def judge_burst(day: dict, events: list[dict]) -> str:
    bursts = [e for e in events if e.get("event") == "plot_exhausted_burst"]
    if not bursts:
        return "undecidable"
    checks = day.get("checks") or {}
    if str(day.get("ended_reason") or "").startswith("stuck:"):
        return "red"
    ex = day.get("pending_executable")
    if ex is None:
        ex = (bursts[-1] or {}).get("pending_executable")
    if ex is not None and int(ex) > 0 and checks.get("day_justified"):
        return "red"
    return "green"


def judge_midway(day: dict, stages: list[dict]) -> str:
    if "stage_midway_leftover" not in day:
        return "undecidable"
    last: dict[str, dict] = {}
    early: dict[str, list[dict]] = {}
    for i, s in enumerate(stages):
        name = str(s.get("stage") or "")
        if int(s.get("tiles") or 0) > 0 and int(s.get("leftover") or 0) > 0:
            early.setdefault(name, []).append(
                {"stage": name, "tiles": s["tiles"], "leftover": s["leftover"], "round": i + 1})
        last[name] = s
    expect = []
    for name, rec in last.items():
        if int(rec.get("leftover") or 0) == 0 and name in early:
            expect.extend(early[name])
    got = day.get("stage_midway_leftover") or []
    if any(int(g.get("leftover") or 0) == 0 for g in got):
        return "red"                     # 把"没有中途剩格"的阶段伪造进遮蔽清单
    return "green" if len(got) == len(expect) else "red"


def judge_obs_missing_field(snap: dict) -> str:
    """通道 d：可见但单字段缺失 ⇒ 归 unobserved；若此时 exec=0 ⇒ day_justified 会放行。"""
    if snap.get("executable") == 0 and snap.get("unobserved", 0) > 0 and snap.get("guard", 0) > 0:
        return "red"                     # fail-open 通道成立（需在报告单列 NIT）
    return "green"


def case_c() -> None:
    print("\n== C 段：对抗通道（a~j，判红/判绿/【无法判定】三态） ==")
    _, LR = fixtures()
    iso = LR.is_justified_end
    checks_ok = {k: True for k in CHECKS_BASELINE}

    # a) 伪造 pending_executable=0：函数本身被证据挡住（None/正数）
    check("C-a1 is_justified_end 无证据 ⇒ False（fail-closed）",
          not iso("sleep", "resume_exhausted:x", pending_executable=None))
    check("C-a2 有可执行格（3）⇒ False", not iso("sleep", "resume_exhausted:x", pending_executable=3))
    # b) resume_exhausted 无条件进白名单 ⇒ 变异必须杀（D 段实测）；判据侧：stuck:/其他前缀不放行
    check("C-b1 stuck: 永不认", not iso("sleep", "stuck:同一秒连发 5 次", pending_executable=0))
    check("C-b2 no_plot 不在白名单", not iso("sleep", "no_plot:配额到顶", pending_executable=0))
    # c) 观测缺失 fail-closed（B2f 已动态证）；判据侧
    check("C-c1 观测不可用口径 = executable=guard", True, "B2f 动态验证")
    # d) 单字段缺失归 unobserved（真实 fail-open 通道，NIT）
    try:
        TL, _ = fixtures()
        w = TL.FakeWorld(weeds=0, seeds=0, money=0)
        run = _mk_run(w)
        run.leftover_targets = {(60, 10)}
        obs = w.obs()
        obs.setdefault("tiles", []).append({"tile": [60, 10]})  # 有 tile 无 kind/crop
        snap = run._pending_snapshot(obs)
        verdict = judge_obs_missing_field(snap)
        check("C-d1 单字段缺失 ⇒ unobserved（洗白通道，判红=NIT）", verdict == "red", f"{snap}")
        check("C-d2 该通道下 day_justified 确实会放行（风险确认）",
              iso("sleep", "resume_exhausted:x", pending_executable=snap["executable"]))
    except Exception as exc:  # noqa: BLE001
        skip("C-d 单字段缺失通道", f"构造失败：{exc}")
    # e) burst 有可执行格不得 VERIFIED（B2i 动态证）；判据侧
    check("C-e1 burst 有 exec>0 且 day_justified=True ⇒ 判红",
          judge_burst({"ended_reason": "resume_exhausted:x", "checks": {"day_justified": True},
                       "pending_executable": 2}, [{"event": "plot_exhausted_burst"}]) == "red")
    check("C-e2 burst 已写 stuck: ⇒ 判红",
          judge_burst({"ended_reason": "stuck:同一秒连发", "checks": {"day_justified": False}},
                      [{"event": "plot_exhausted_burst"}]) == "red")
    # f) 卡1 兜底口径（B2h 动态证）；判据侧：dead_end_pending 必须非空
    check("C-f1 _dead_end_pending 保留原始账本口径", True, "B2h 动态验证")
    # g) stage_midway_leftover 不伪造（judge 三态 + 结构 B2m）
    stages_ok = [
        {"stage": "clear_area", "tiles": 12, "leftover": 5},
        {"stage": "clear_area", "tiles": 12, "leftover": 0},
    ]
    day_ok = {"stage_midway_leftover": [{"stage": "clear_area", "tiles": 12, "leftover": 5, "round": 1}]}
    check("C-g1 遮蔽形态判绿", judge_midway(day_ok, stages_ok) == "green")
    check("C-g2 伪造中途 leftover=0 进清单判红",
          judge_midway({"stage_midway_leftover": [{"leftover": 0}]}, stages_ok) == "red")
    check("C-g3 缺字段判【无法判定】", judge_midway({}, stages_ok) == "undecidable")
    # h) checks 10 键不污染
    check("C-h1 checks 恰 10 键判绿", judge_payload(checks_ok) == "green")
    check("C-h2 checks 塞 slept_ok 判红", judge_payload({**checks_ok, "slept_ok": True}) == "red")
    check("C-h3 checks 缺键判【无法判定】",
          judge_payload({k: True for k in CHECKS_BASELINE[:-1]}) == "undecidable")
    # i) no_unmet_stages 不放宽（judge：assigned_undone>0 + 非诚实停 + exec>0 ⇒ 红）
    def judge_no_unmet(day: dict, stages: list[dict]) -> str:
        checks = day.get("checks") or {}
        if "no_unmet_stages" not in checks:
            return "undecidable"
        if not checks.get("no_unmet_stages"):
            return "green"
        honest = {"night", "stamina", "no_work", "resume_exhausted"}
        for s in stages:
            if int(s.get("assigned_undone") or 0) > 0 and str(s.get("stopped") or "") not in honest:
                return "red"
        if int(day.get("pending_executable") or 0) > 0:
            return "red"
        return "green"

    check("C-i1 有未做完阶段却 no_unmet_stages=True ⇒ 判红",
          judge_no_unmet({"checks": {"no_unmet_stages": True}, "pending_executable": 0},
                         [{"assigned_undone": 2, "stopped": ""}]) == "red")
    check("C-i2 诚实停 stamina ⇒ 判绿",
          judge_no_unmet({"checks": {"no_unmet_stages": True}, "pending_executable": 0},
                         [{"assigned_undone": 2, "stopped": "stamina"}]) == "green")
    # j) 新字段不污染既有语义键 + day_justified 证据链（合成 day）
    day_good = {"checks": checks_ok, "pending_ledger": 220, "pending_guard": 0,
                "pending_blocked": 220, "pending_executable": 0, "pending_unobserved": 0,
                "ended_reason": "resume_exhausted:回片区 217 格"}
    day_forged = {"checks": {**checks_ok, "day_justified": True},
                  "pending_ledger": 220, "pending_guard": 3, "pending_blocked": 217,
                  "pending_executable": 0, "pending_unobserved": 0,
                  "ended_reason": "resume_exhausted:x"}
    check("C-j1 自洽 day 判绿（快照不变式+证据）",
          judge_snapshot_invariants(day_good) == "green" and judge_resume_evidence(day_good) == "green")
    check("C-j2 伪造 exec=0（guard=3/unobs=0）判红",
          judge_snapshot_invariants(day_forged) == "red")
    check("C-j3 day_justified=True 但 exec>0 判红",
          judge_resume_evidence({**day_good, "pending_executable": 2}) == "red")
    check("C-j4 字段缺失判【无法判定】", judge_snapshot_invariants({}) == "undecidable")
    # h2 键集与实际源码核对（B 段已做 AST）；这里补 tools 口径提示
    info("C-k task-10 #1 工具口径", "verify-run3.py 只累加/单列 ok（:1104/:1122）；"
                                    "A9 放行必须并列读 day_end.stages[].already/attempted_ok")


# ------------------------------------------------------------------ D 段
def case_d() -> None:
    print("\n== D 段：变异两列（作者自报 vs 实测；均为冻结树副本跑） ==")
    author = REPO / "scratch" / "_t0745_author_mut.txt"
    mine = REPO / "scratch" / "_t0745_my_mut.txt"
    if author.exists():
        text = read(author)
        killed = text.count("killed")
        survived = text.count("SURVIVED") + text.count("survived")
        check("D1 作者 4 条变异实测被杀 4/4", killed >= 4 and survived == 0,
              f"输出 killed={killed} survived={survived}")
        for line in text.splitlines():
            if line.strip().startswith("[m"):
                info("D1", line.strip()[:150])
    else:
        skip("D1 作者变异实测", f"缺证据 {author}")
    if mine.exists():
        text = read(mine)
        killed = text.count("KILLED") + text.count("killed")
        survived = text.count("SURVIVED") + text.count("survived")
        check("D2 我方变异实测全杀", survived == 0 and killed >= 5,
              f"killed={killed} survived={survived}")
        for line in text.splitlines():
            if line.strip().startswith("[m15"):
                info("D2", line.strip()[:150])
    else:
        skip("D2 我方变异实测", f"缺证据 {mine}")


def main() -> int:
    global args
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="A,B,C,D")
    ap.add_argument("--readings", action="store_true")
    args = ap.parse_args()
    only = {x.strip().upper() for x in args.only.split(",") if x.strip()}
    print(f"ROOT={ROOT}\nCOMMIT={COMMIT}\nBASELINE={BASELINE_COMMIT}")
    if "A" in only:
        case_a()
    if "B" in only:
        check_ledger_arithmetic()
        check_replay_045()
    if "C" in only:
        case_c()
    if "D" in only:
        case_d()
    print(f"\n汇总：PASS={RESULTS['PASS']} FAIL={RESULTS['FAIL']} "
          f"SKIP={RESULTS['SKIP']} INFO={RESULTS['INFO']}")
    if FAILS:
        print("FAIL 项：" + "、".join(FAILS))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
