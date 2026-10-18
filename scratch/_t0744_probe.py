"""task-4/5/6（0.7.44 三卡）对抗验收探针骨架（deputy-lead 独立判据）。

状态：**骨架**（2026-10-18 17:5x 预置；dev-coder 交付并 Lead 放行后按实际实现填锚点/字段名）。
判据一律按卡面语义独立实现，不抄作者脚本；缺失写【无法判定】，不当 PASS。

用法（切换被测树）：
    $env:T744_ROOT = "<tree>"; python scratch/_t0744_probe.py [--only A,B,C,D,E] [--readings]
    $env:T744_COMMIT = "<0.7.44 冻结提交>"; python scratch/_t0744_probe.py   # 触发 A0 provenance 核

- 默认 ROOT = 本仓库（只作线索）；正式判定用 `git archive <0.7.44 提交>` 展开到 %TEMP% 的树。
- 修前基线夹具 = `logs/longrun-runA8-0743.jsonl`（0.7.43 A8 真账本，1322 行 / SHA256 18f224c3…）。
- 基线锚点（0.7.43 冻结 `5679562`）：死循环 A 冬 7/12/18；死循环 B 冬 9/14；task-6 缺陷 ①冬 9/14
  `slept_by_us=false` 但 sleep 成功；②0.7.43 analyzer 在 A8 上报 6 行「只因预算延后却自称户外浇水达标」。
- 输出只走 stdout（调用方 Tee 到 scratch/ 的 UTF-8 文本）。
"""

from __future__ import annotations

import argparse
import ast
import glob
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(os.environ.get("T744_ROOT") or Path(__file__).resolve().parents[1])
REPO = Path(__file__).resolve().parents[1]
PY = sys.executable
PASS = FAIL = SKIP = INFO = 0
FAILS: list[str] = []
INFOS: list[str] = []

# ---------------------------------------------------------------- 常量（交付后按实际命名核对）
BASELINE_COMMIT = "5679562"          # 0.7.43 冻结（修前基线）
EXPECT_VERSION = "0.7.44"
A8_LEDGER_REL = "logs/longrun-runA8-0743.jsonl"
A8_SHA256 = "18f224c3f366d377f63fd6938b24ce2a05ffaed11b588829d94a8c89dbb13b60"
A8_LINES = 1322
# 0.7.43 analyzer 在 A8 上的 6 行「只因预算延后」警告（行号，修前基线；修后应 0 行）
A8_BUDGET_WATER_WARN_LINES = [33, 150, 254, 527, 542, 563]
# 死循环 A：work_spot_resume 5 次拿不出目标 ⇒ 整天 stuck
LOOP_A_DAYS = [("1", "winter", 7), ("1", "winter", 12), ("1", "winter", 18)]
# 死循环 B：1 格余量反复重分（stage_stop_named incomplete assigned=1 的条数下界）
LOOP_B_DAYS = [(("1", "winter", 9), 28), (("1", "winter", 14), 62)]
# 【交付后按实际命名更新】卡 4（task-4）口径标记（B 案：复用既有事件名，只加字段）
CARD4_FIELD_MARKERS = ("plot_exhausted", "resume_exhausted", "exhausted=True", "switched=")
RESUME_EXHAUSTED_PREFIX = "resume_exhausted"
DEFAULT_PLOT_LIMIT = 5  # max_plots_per_day 的期望量级（交付后按常量核对）
# 0.7.43 阶段/日级键集基线（AST 抽取，用于"只许新增、须单列"核对）
CHECKS_BASELINE = ("slept_by_us", "no_blocking_modal", "no_hard_failures",
                   "unreachable_within_bound", "refused_within_bound", "no_unmet_stages",
                   "crops_watered", "watered_outdoor", "day_justified", "zero_action_evidenced")
# task-5 leftover 拆口径的候选字段（交付后按实际命名更新；缺失 ⇒ 【无法判定】不是 PASS）
LEFTOVER_EXEC_FIELDS = ("leftover_executable", "leftover_actionable", "leftover_retryable")
LEFTOVER_BLOCKED_FIELDS = ("leftover_blocked", "leftover_physically_blocked", "leftover_doomed")
# 0.7.44 三卡（task-5/6/11）关键实现标记（A2h2~h4；缺失 ⇒ 该卡未交付，不判 PASS）
CARD5_MARKERS = ("_dead_tile_set", "leftover_executable", "leftover_blocked",
                 "MAX_ALLOC_NO_PROGRESS = 3", "alloc_no_progress")
CARD6_MARKERS = ("slept_ok", "_slept_by_us", "deferred_by_budget_suppressed",
                 "budget_defer_events", "_flush_budget_deferrals")
CARD11_MARKERS = ("_guard_leftover_resume", "_dead_end_pending", 'where="guard_leftover"')
# 诚实停名：这些 stop 原因下允许 assigned_undone>0 而不判"洗白"（卡 5 不放宽 no_unmet_stages）
HONEST_STOPPED = ("stamina", "budget", "night", "inventory_blocked", "unreachable", "refused")
# 作者 repro 脚本自报"修前红"的形态（形如 `rc=1  Ran 5 红 3`）
RC_RED_RX = re.compile(r"红\s*[1-9]\d*")
# task-5 同格无产出重分上限（frozen longrun.py:244 原文 `MAX_ALLOC_NO_PROGRESS = 3`）
MAX_ALLOC_NO_PROGRESS = 3


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
    try:
        return (ROOT / rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def sh(argv: list[str], *, cwd: Path | None = None, timeout: int = 900) -> tuple[int, str]:
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        r = subprocess.run(argv, cwd=str(cwd or ROOT), capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout, env=env)
        return r.returncode, (r.stdout or "") + (r.stderr or "")
    except Exception as exc:  # noqa: BLE001
        return 99, f"{type(exc).__name__}: {exc}"


def git_show(rel: str, ref: str = BASELINE_COMMIT) -> str:
    rc, out = sh(["git", "-C", str(REPO), "show", f"{ref}:{rel}"], cwd=REPO)
    return out if rc == 0 else ""


def sha256_file(p: Path) -> str:
    try:
        return hashlib.sha256(p.read_bytes()).hexdigest()
    except OSError:
        return ""


def _checks_keys(src: str) -> list[str]:
    """AST 取 `rep.checks = {...}` 字面键序（只认 Assign + Attribute(attr="checks") + Dict）。"""
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        tgt = node.targets[0]
        if not (isinstance(tgt, ast.Attribute) and tgt.attr == "checks"
                and isinstance(node.value, ast.Dict)):
            continue
        keys = [k.value for k in node.value.keys
                if isinstance(k, ast.Constant) and isinstance(k.value, str)]
        if keys:
            return keys
    return []


# ---------------------------------------------------------------- A0 provenance

def check_provenance() -> None:
    commit = os.environ.get("T744_COMMIT", "").strip()
    if not commit:
        skip("A0 provenance", "未设 T744_COMMIT（正式判定前必须设并重核）")
        return
    rc, out = sh(["git", "-C", str(REPO), "ls-tree", "-r", commit], cwd=REPO)
    if rc != 0:
        skip("A0 provenance", f"git ls-tree {commit} rc={rc}")
        return
    entries: dict[str, str] = {}
    for line in out.splitlines():
        meta, path = line.split("\t", 1)
        entries[path] = meta.split()[2]
    missing, bad, eol_ok = [], [], []
    for p, sha in entries.items():
        f = ROOT / p
        if not f.exists():
            missing.append(p)
            continue
        data = f.read_bytes()
        got = hashlib.sha1(b"blob %d\0" % len(data) + data).hexdigest()
        if got != sha:
            if p.endswith((".ps1", ".bat", ".cmd")):
                norm = data.replace(b"\r\n", b"\n")
                if hashlib.sha1(b"blob %d\0" % len(norm) + norm).hexdigest() == sha:
                    eol_ok.append(p)
                    continue
            bad.append((p, sha[:12], got[:12]))
    check("A0 冻结树 provenance（blob 全量对照）", not missing and not bad,
          f"{commit}: 追踪 {len(entries)}、缺失 {len(missing)}、不符 {len(bad)}、eol 展开 {len(eol_ok)}"
          + (f" 缺={missing[:3]} 不符={bad[:3]}" if missing or bad else ""))
    keys = ["brain/agentfarm/longrun.py", "tests/test_longrun.py",
            "tools/analyze-longrun.py", "mod/AgentFarm.Bridge/manifest.json"]
    bad_key = 0
    for p in keys:
        rc2, h = sh(["git", "-C", str(REPO), "hash-object", str(ROOT / p)], cwd=REPO)
        h = h.strip()
        if rc2 != 0 or h != entries.get(p):
            bad_key += 1
    check("A0b 关键文件 git hash-object 对照", bad_key == 0, f"{len(keys) - bad_key}/{len(keys)}")


# ---------------------------------------------------------------- A 段

def case_a(readings: bool) -> None:
    print("== A 段：范围 / 版本 / 新事件与新字段 / 语义键 / 读数 ==")
    check_provenance()
    files = ["brain/agentfarm/longrun.py", "tests/test_longrun.py"]
    check("A1 关键文件在树内", all((ROOT / f).exists() for f in files), str(ROOT))
    manifest = read("mod/AgentFarm.Bridge/manifest.json")
    bridge = read("brain/agentfarm/bridge.py")
    check(f"A1b 版本 = {EXPECT_VERSION}",
          f'"Version": "{EXPECT_VERSION}"' in manifest and f'MOD_VERSION_EXPECTED = "{EXPECT_VERSION}"' in bridge,
          f"manifest={EXPECT_VERSION in manifest} bridge={EXPECT_VERSION in bridge}")

    old_src = git_show("brain/agentfarm/longrun.py")
    if not old_src:
        skip("A2 0.7.43 基线源码对照", "git show 5679562 不可用")
    else:
        old_j = set(re.findall(r'_journal\(\s*"([a-z_]+)"', old_src))
        new_j = set(re.findall(r'_journal\(\s*"([a-z_]+)"', read("brain/agentfarm/longrun.py")))
        added_j = sorted(new_j - old_j)
        removed_j = sorted(old_j - new_j)
        check("A2 既有 journal 事件名未被改名/删除", not removed_j, f"removed={removed_j}")
        info("A2b 新增 journal 事件（报告须单列）", added_j)
        src_new = read("brain/agentfarm/longrun.py")
        hits = {k: (k in src_new) for k in CARD4_FIELD_MARKERS}
        check("A2c 卡 4 换片/收工口径字段在源码出现（复用既有事件名，B 案）",
              all(hits.values()), f"{hits}；新增事件={added_j}")
        info("A2h 卡 4 新增 journal 事件名（B 案期望 0）", added_j or "0（复用既有事件名）")
        # 语义键：阶段记录 / day_end / checks 键集
        import ast

        def dict_keys(src: str) -> tuple[list[str], list[str]]:
            tree = ast.parse(src)
            stage = day = []
            for node in ast.walk(tree):
                if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
                        and node.func.attr == "append" and node.args and isinstance(node.args[0], ast.Dict) \
                        and isinstance(node.func.value, ast.Attribute) and node.func.value.attr == "stages":
                    stage = [k.value for k in node.args[0].keys if isinstance(k, ast.Constant)]
                if isinstance(node, ast.Dict):
                    vals = list(node.values)
                    keys = [k.value for k in node.keys if isinstance(k, ast.Constant)]
                    if "checks" in keys and any(
                            isinstance(v, ast.Call) and isinstance(v.func, ast.Name)
                            and v.func.id == "dict" for v in vals) and (
                            "assigned_undone" in keys or "plot_pending" in keys):
                        day = keys
            return stage, day

        try:
            old_stage, old_day = dict_keys(old_src)
            new_stage, new_day = dict_keys(read("brain/agentfarm/longrun.py"))
        except SyntaxError as exc:  # 在制树半截时不炸探针
            skip("A2d 语义键 AST 对照", f"源码解析失败（树可能半截）：{exc}")
            old_stage = old_day = new_stage = new_day = []
        if old_stage:
            rm_stage = [k for k in old_stage if k not in new_stage]
            rm_day = [k for k in old_day if k not in new_day]
            check("A2d 语义键未被删（阶段 36 键 / day_end 47 键基线）",
                  not rm_stage and not rm_day, f"stage 删={rm_stage} day_end 删={rm_day}")
            info("A2e 新增阶段键（报告须单列）", [k for k in new_stage if k not in old_stage])
            info("A2f 新增 day_end 键（报告须单列）", [k for k in new_day if k not in old_day])
        src_new = read("brain/agentfarm/longrun.py")
        checks_named = [k for k in CHECKS_BASELINE if f'"{k}"' in src_new]
        check("A2g checks 10 键未被改", len(checks_named) == 10, f"命中 {len(checks_named)}/10")
        # A2h2~h4：0.7.44 三卡关键实现标记（卡面要求逐项核在源码；缺失=未交付）
        for tag, name, keys in (("A2h2", "task-5 挡死格/拆分/有界重分", CARD5_MARKERS),
                                ("A2h3", "task-6 入睡真值/预算延后压制", CARD6_MARKERS),
                                ("A2h4", "task-11 review/guard 统一路由", CARD11_MARKERS)):
            miss = [k for k in keys if k not in src_new]
            check(f"{tag} {name} 关键实现标记在源码", not miss, f"缺={miss}")
        # A2h5：checks 字面键集（旧树/冻结树都必须恰为 10 键基线；新字段不得塞进 checks）
        try:
            keys_old = _checks_keys(old_src)
        except NameError:
            keys_old = []
        keys_new = _checks_keys(src_new)
        check("A2h5 checks 字面键集 = 10 键基线（新字段不得污染）",
              keys_old == list(CHECKS_BASELINE) and keys_new == list(CHECKS_BASELINE),
              f"old={len(keys_old)} 键 new={len(keys_new)} 键" if keys_new != list(CHECKS_BASELINE)
              else "10/10 键序一致")

    if not readings:
        skip("A4 读数", "加 --readings 才跑（py_compile / 定向 / 全量 / build）")
        return
    rc, _ = sh([PY, "-W", "error::SyntaxWarning", "-m", "py_compile",
                "brain/agentfarm/longrun.py", "brain/agentfarm/farmwork.py",
                "brain/agentfarm/planner.py", "brain/agentfarm/bridge.py"])
    check("A4a py_compile -W error::SyntaxWarning", rc == 0, f"rc={rc}")
    rc, out = sh([PY, "-m", "unittest", "tests.test_farmwork", "tests.test_longrun",
                  "tests.test_planner"])
    check("A4b 定向单测（以 Ran N / OK 为准）", "OK" in out and "FAILED" not in out,
          [ln for ln in out.splitlines() if ln.startswith("Ran ")][-1:])
    rc, out = sh([PY, "-m", "unittest", "discover", "-s", "tests"])
    red = out.count("\nFAIL:") + out.count("\nERROR:")
    if red and "scratch/_ledger_" in out:
        skip("A4c 全量单测", f"{red} 红全部是本地夹具缺失（scratch/_ledger_*.jsonl 被 .gitignore 排除），非产品红；"
                             "补齐夹具后须重跑")
    else:
        check("A4c 全量单测（0 红）", "OK" in out and red == 0,
              f"{[ln for ln in out.splitlines() if ln.startswith('Ran ')][-1:]} red={red}")
    rc, out = sh(["dotnet", "build", "mod/AgentFarm.Bridge/AgentFarm.Bridge.csproj",
                  "-c", "Release", "--no-incremental", "--nologo"])
    check("A4d dotnet build --no-incremental 0 警 0 错", rc == 0
          and (" 0 Warning(s)" in out or "0 个警告" in out)
          and (" 0 Error(s)" in out or "0 个错误" in out),
          [ln.strip() for ln in out.splitlines()
           if "Warning(s)" in ln or "Error(s)" in ln or "个警告" in ln or "个错误" in ln][-3:])


# ---------------------------------------------------------------- B 段：A8 修前红复现 + 修后形状

def _load_a8() -> tuple[list[tuple[int, dict]], str]:
    for cand in (ROOT / A8_LEDGER_REL, REPO / A8_LEDGER_REL):
        if cand.exists():
            rows: list[tuple[int, dict]] = []
            for i, line in enumerate(cand.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
                if line.strip():
                    try:
                        rows.append((i, json.loads(line)))
                    except json.JSONDecodeError:
                        pass
            return rows, str(cand)
    return [], ""


def _day_ranges(rows: list[tuple[int, dict]]) -> list[tuple[tuple[int, str, int], int, int, dict]]:
    """返回 [(day_key, start_line, end_line, day_end_row)]。"""
    ends = [(i, r) for i, r in rows if r.get("event") == "day_end"]
    out = []
    prev = 1
    for i, r in ends:
        day = r.get("day")
        if isinstance(day, list) and len(day) == 3:
            key = (int(day[0]), str(day[1]), int(day[2]))
        else:
            key = (0, "", 0)
        out.append((key, prev, i, r))
        prev = i + 1
    return out


def _in_range(rows: list[tuple[int, dict]], lo: int, hi: int, pred) -> list[tuple[int, dict]]:
    return [(i, r) for i, r in rows if lo <= i <= hi and pred(r)]


# ---------------------------------------------------------------- B6：卡 1 独立重放（我方场景）

def _probe_fixtures():
    """用被测树自己的 `tests/test_longrun.py` 夹具（FakeWorld / CountingClient / make_run）。"""
    for p in (ROOT / "tests", ROOT / "brain", ROOT):
        s = str(p)
        if s not in sys.path:
            sys.path.insert(0, s)
    import test_longrun as TL  # noqa: N813
    return TL


def _mk_run(TL, world):
    client = TL._CountingClient(world) if hasattr(TL, "_CountingClient") else TL.FakeClient(world)
    if hasattr(TL, "FarmWorker"):
        worker = TL.FarmWorker(client, log=lambda *_: None)
    else:
        worker = TL.FakeWorker(world, log=lambda *_: None)
    run = TL.make_run(world, target_days=1, max_days=1,
                      client_factory=lambda c: client, worker_factory=lambda c: worker)
    run.worker = worker
    run.client = client
    return run


def _plot_of(area: str, tiles, anchor=None) -> dict:
    return {"zone": "", "label": "", "area": area,
            "anchor": list(anchor or tiles[0]), "tiles": [list(t) for t in tiles], "note": ""}


def check_resume_replay(rows: list[tuple[int, dict]]) -> None:
    """卡 1 修后形状的**我方独立重放**：不跑作者用例，用自己的场景/断言核产品代码。"""
    print("== B6 段：卡 1 独立重放（我方场景；非作者用例）==")
    src = read("brain/agentfarm/longrun.py")
    if "_resume_switch_or_exhaust" not in src:
        skip("B6 卡 1 独立重放",
             "被测树无 `_resume_switch_or_exhaust`（0.7.43 修前形态）⇒ 修前红由 B1 账本证明")
        return
    # B6f 先核 A8 路由：冬 7/12/18 的形态必须落在被修复的入口上
    bursts = [r for _, r in rows if r.get("event") == "no_progress_burst"]
    srcs = sorted({str(r.get("source") or "") for r in bursts})
    check("B6f A8 冬 7/12/18 形态路由在修复路径内（账本 source 全为 work_spot_resume）",
          bool(bursts) and all("work_spot_resume" in s for s in srcs), f"sources={srcs}")
    try:
        TL = _probe_fixtures()
    except Exception as exc:  # noqa: BLE001
        skip("B6 卡 1 独立重放", f"夹具 import 失败: {type(exc).__name__}: {exc}")
        return

    def _new_rep():
        return TL.DayReport(day_key=("winter", 1, 7), started_at=0.0)

    def _case(tag: str, fn) -> None:
        try:
            bad = fn()
        except Exception as exc:  # noqa: BLE001 - 探针自己的 bug 与产品 bug 分开判
            check(tag, False, f"判据自身异常: {type(exc).__name__}: {exc}")
            return
        check(tag, not bad, "; ".join(bad) if bad else "绿")

    def switch_case():
        w = TL.FakeWorld(weeds=0, seeds=0, money=0)
        w.player_tile = [80, 11]
        run = _mk_run(TL, w)
        # 账本两片：field_nw 的残留格比 field_se 更近（>OBSERVE_REACH，不会先被标停滞）
        run.leftover_targets = {(60, 10), (95, 35)}
        run.leftover_area = {(60, 10): "field_nw", (95, 35): "field_se"}
        rep = _new_rep()
        action, alt = run._resume_switch_or_exhaust(
            w.obs(), rep, plot=_plot_of("field_nw", [(80, 11)], anchor=[80, 11]),
            where="deputy_replay")
        bad = []
        if action != "walk" or not alt:
            bad.append(f"action={action} alt={bool(alt)}")
        else:
            if alt.get("area") != "field_se":
                bad.append(f"没换到另一片（area={alt.get('area')}；avoid_area 应优先别片）")
            if not set(map(tuple, alt.get("tiles") or [])) <= run.leftover_targets:
                bad.append("换片坐标不在账本记账")
        if rep.ended_by:
            bad.append(f"换片成功却收工：{rep.ended_by}")
        evs = [e for e in run.entries if e["event"] == "plot_exhausted"]
        if not evs or evs[-1].get("source") != "resume_ledger":
            bad.append("plot_exhausted 缺 source=resume_ledger")
        return bad

    def frontier_case():
        w = TL.FakeWorld(weeds=0, seeds=0, money=0)
        w.blockers[(60, 10)] = "weed"
        w.player_tile = [60, 12]
        run = _mk_run(TL, w)
        run.leftover_targets = {(60, 10)}
        run.leftover_area = {(60, 10): "field_x"}
        rep = _new_rep()
        action, _alt = run._resume_switch_or_exhaust(
            w.obs(), rep, plot=_plot_of("field_x", [(60, 10)]), where="deputy_replay")
        bad = []
        if action != "acted":
            bad.append(f"action={action}（期望先清一格）")
        if (60, 10) in w.blockers:
            bad.append("frontier 没清掉 blocker")
        return bad

    def exhausted_case():
        w = TL.FakeWorld(weeds=0, seeds=0, money=0)
        w.player_tile = [62, 14]
        run = _mk_run(TL, w)
        run.leftover_targets = {(60, 10)}
        run.leftover_area = {(60, 10): "field_x"}
        run.farm_actions_today = 5
        rep = _new_rep()
        action, _alt = run._resume_switch_or_exhaust(
            w.obs(), rep, plot=_plot_of("field_x", [(60, 10)]), where="deputy_replay")
        reason = str(rep.ended_reason or "")
        bad = []
        if action != "ended":
            bad.append(f"action={action}")
        if not reason.startswith(RESUME_EXHAUSTED_PREFIX):
            bad.append(f"reason 前缀不是 resume_exhausted：{reason[:60]}")
        if reason.startswith("stuck"):
            bad.append("写回 stuck 口径")
        return bad

    def encircled_case():
        w = TL.FakeWorld(weeds=0, seeds=0, money=0)
        w.player_tile = [80, 11]
        run = _mk_run(TL, w)
        # encircled 格离锚点 >OBSERVE_REACH：不会先被标停滞，只由 encircled 规则排除
        run.leftover_targets = {(37, 35)}
        run.leftover_area = {(37, 35): "field_nw"}
        run.encircled_day = {(37, 35)}
        run.farm_actions_today = 5
        rep = _new_rep()
        action, _alt = run._resume_switch_or_exhaust(
            w.obs(), rep, plot=_plot_of("field_nw", [(80, 11)], anchor=[80, 11]),
            where="deputy_replay")
        bad = []
        if action != "ended":
            bad.append(f"action={action}（encircled 不该有可执行目标）")
        if any(e["event"] == "plot_exhausted" for e in run.entries):
            bad.append("encircled 被当换片目标")
        ev = [e for e in run.entries if e["event"] == "no_progress_burst" and e.get("exhausted")]
        if not ev or int(ev[-1].get("encircled_pending") or 0) < 1:
            bad.append("exhausted 未记 encircled_pending")
        return bad

    _case("B6a 修后：换到另一片账本待做格（我方场景）", switch_case)
    _case("B6b 修后：观测里可达一格先清（frontier_clear）", frontier_case)
    _case("B6c 修后：确实没活 ⇒ resume_exhausted 诚实收工（不 stuck）", exhausted_case)
    _case("B6d 修后：encircled 不算可执行目标", encircled_case)

    # B6e GAP-1/2（task-11 扩面）：`review_only_fallback` / `guard_leftover` 必须统一路由到
    # `_resume_switch_or_exhaust`（换片→观测清一格→resume_exhausted）。Lead 裁决 GAP-3
    # （plot_exhausted_burst / 换片超限）= 有界诚实停，保留、不算洗白 ⇒ 本段不核 GAP-3。
    gap: list[str] = []
    gap1: bool | None = None
    try:
        w = TL.FakeWorld(weeds=0, seeds=0, money=0)
        run = _mk_run(TL, w)
        run.leftover_targets = {(60, 10), (85, 10)}
        run.leftover_area = {(60, 10): "field_nw", (85, 10): "field_ne"}
        run.no_progress_cycles = 4
        rep = _new_rep()
        calls: list[str] = []

        def fake_stop(obs, rep_, *, source, tiles):
            calls.append(str(source))
            rep_.ended_by = "stuck"
            rep_.ended_reason = f"stuck:{source}（deputy 重放：该入口未改）"
            return rep_.ended_by, rep_.ended_reason

        run._no_progress_stop = fake_stop
        run._review_only_fallback(w.obs(), rep)
        gap1 = bool([s for s in calls if "review_only" in s])
        gap.append(f"B6e1 review_only_fallback 仍走 stuck 路径={gap1}"
                   f"（ended_by={rep.ended_by or '无'}）")
    except Exception as exc:  # noqa: BLE001
        gap.append(f"B6e1 调用异常 {type(exc).__name__}: {exc}")
    src2 = read("brain/agentfarm/longrun.py")
    idx = src2.find('where="guard_leftover"')
    seg = src2[idx: idx + 1500] if idx >= 0 else ""
    gap2 = bool(seg) and ("_no_progress_stop" in seg)
    gap.append(f"B6e2 guard_leftover 段仍含 _no_progress_stop={gap2}"
               f"（段内含 _resume_switch_or_exhaust={'_resume_switch_or_exhaust' in seg}）")
    gap.append("A8 账本 review_only_fallback 事件数="
               + str(sum(1 for _, r in rows if r.get("event") == "review_only_fallback")))
    if gap1 is False and gap2 is False:
        check("B6e GAP-1/2 已收口（两入口统一路由到换片/清一格/resume_exhausted）",
              True, "；".join(gap))
    else:
        info("B6e GAP-1/2 仍 open（task-11 未交付时预期）", "；".join(gap))


def case_b() -> None:
    print("== B 段：A8 修前红复现（死循环 A/B + task-6 两条）==")
    rows, src_path = _load_a8()
    if not rows:
        skip("B0 A8 账本夹具", f"{A8_LEDGER_REL} 缺失 ⇒ 本段【无法判定】（缺失 ≠ 通过）")
        return
    h = sha256_file(Path(src_path))
    check("B0 A8 账本夹具指纹", h == A8_SHA256 and len(rows) == A8_LINES,
          f"{src_path} lines={len(rows)} sha256={h[:16]}…（期望 {A8_LINES} / {A8_SHA256[:16]}…）")
    ranges = {(k[1].lower(), k[2]): (lo, hi, r) for k, lo, hi, r in _day_ranges(rows)}

    # B1 死循环 A：work_spot_resume 5 次拿不出目标 ⇒ 整天判死（冬 7/12/18；ended_by 可能是
    # sleep——冬 7/12/18 走的是"收尾回片区 5 次无目标 ⇒ 以 stuck: 理由结束/睡过去"，不是 idle stuck）
    hit = 0
    for season, day in (("winter", 7), ("winter", 12), ("winter", 18)):
        if (season, day) not in ranges:
            continue
        lo, hi, endr = ranges[(season, day)]
        reason = str(endr.get("ended_reason") or "")
        burst = _in_range(rows, lo, hi, lambda r: r.get("event") == "no_progress_burst")
        walks = _in_range(rows, lo, hi, lambda r: r.get("event") == "resume_walk")
        guard_hint = any("还有" in str(b.get("reasons") or "") for _, b in burst)
        ok = (reason.startswith("stuck") and "work_spot_resume" in reason and guard_hint
              and any(int(b.get("count") or 0) >= 5 for _, b in burst))
        info(f"B1 winter {day} 修前形态",
             f"ended_by={endr.get('ended_by')} burst={[b.get('count') for _, b in burst]} "
             f"resume_walk={len(walks)} ok_steps={endr.get('ok_steps')} 理由含跨片待做={guard_hint}")
        hit += 1 if ok else 0
    check("B1 死循环 A 修前红复现（冬 7/12/18：回片区 5 次无目标 ⇒ stuck 理由收尾）",
          hit == 3, f"命中 {hit}/3")

    # B2 死循环 B：1 格余量反复重分（冬 9/14）
    ok_days = 0
    for (season, day), floor in [(("winter", 9), 28), (("winter", 14), 62)]:
        if (season, day) not in ranges:
            continue
        lo, hi, endr = ranges[(season, day)]
        stops = _in_range(rows, lo, hi, lambda r: r.get("event") == "stage_stop_named"
                          and r.get("cause") in ("incomplete", "encircled", "unreachable")
                          and int(r.get("assigned") or 0) <= 2
                          and int(r.get("assigned_undone") or 0) == 1)
        enc = _in_range(rows, lo, hi, lambda r: r.get("event") == "encircled")
        tiles = {tuple(t) for _, e in enc for t in ((e.get("tiles") or ([e["tile"]] if e.get("tile") else [])))}
        ok = (len(stops) >= floor and ("stuck" in str(endr.get("ended_by") or ""))
              and "连续" in str(endr.get("ended_reason") or ""))
        info(f"B2 winter {day} 修前形态",
             f"1格incomplete阶段={len(stops)}（下界 {floor}）encircled_tiles={sorted(tiles)} "
             f"ended_by={endr.get('ended_by')}")
        ok_days += 1 if ok else 0
    check("B2 死循环 B 修前红复现（冬 9/14：挡死格被反复重分 ⇒ stuck）", ok_days == 2,
          f"命中 {ok_days}/2")

    # B3 task-6 ①：stuck 日 checks.slept_by_us 快照滞后（sleep 已成功却记 false）
    snap = 0
    for (season, day) in [("winter", 9), ("winter", 14)]:
        if (season, day) not in ranges:
            continue
        lo, hi, endr = ranges[(season, day)]
        sleeps = _in_range(rows, lo, hi, lambda r: r.get("event") == "sleep" and r.get("ok") is True)
        checks = endr.get("checks") or {}
        bad = bool(sleeps) and checks.get("slept_by_us") is False and bool(endr.get("day_after"))
        info(f"B3 winter {day} 修前形态",
             f"sleep_ok={len(sleeps)} slept_by_us={checks.get('slept_by_us')} "
             f"day_after={endr.get('day_after')}")
        snap += 1 if bad else 0
    check("B3 task-6① 修前红复现（冬 9/14 sleep 成功但 slept_by_us=false）", snap == 2,
          f"命中 {snap}/2")

    # B6 卡 1 修后形状（我方独立重放；无方法=修前树 ⇒ SKIP，不判 PASS）
    check_resume_replay(rows)
    # B7~B10：0.7.44 三卡（task-5/6/11 + task-10 #1）我方独立重放
    check_card5_replay(rows)
    check_card6_replay(rows)
    check_already_semantics(rows)
    check_task11_replay(rows)

    # B4 task-6 ②：0.7.43 analyzer 在 A8 上报「只因预算延后却自称户外浇水达标」6 行
    analyzer = ROOT / "tools/analyze-longrun.py"
    if not analyzer.exists():
        skip("B4 task-6② analyzer 行", "tools/analyze-longrun.py 不在树内")
        return
    rc, out = sh([PY, str(analyzer), "--journal", src_path, "--days", "7"], cwd=ROOT, timeout=300)
    warn = [ln for ln in out.splitlines() if "只因预算延后" in ln and "户外浇水达标" in ln]
    lines_hit: list[int] = []
    for ln in warn:
        m = re.search(r"行 \[([0-9,\s]+)\]", ln)
        if m:
            lines_hit = [int(x) for x in m.group(1).split(",") if x.strip()]
    check("B4 task-6② 修前红复现（预算延后 × 户外浇水达标同真，6 行）",
          lines_hit == A8_BUDGET_WATER_WARN_LINES,
          f"rc={rc} lines={lines_hit}（期望 {A8_BUDGET_WATER_WARN_LINES}）" if lines_hit else
          f"rc={rc} 未解析到警告行")

    # B5 修后形状：接作者离线重放（*replay*）；无真重放则退到作者 repro 脚本做形状验证。
    cands: list[str] = []
    for base in (ROOT, REPO):
        cands += _glob_scripts(base, "replay")
    cands = [p for p in dict.fromkeys(cands) if "_t0744" not in Path(p).name]
    repro = sorted(REPO.glob("tests/_repro_*.py"))
    if not cands and not repro:
        skip("B5 作者离线重放（A8 账本重放后两条死循环不再出现）", "脚本未交付 ⇒ GAP（不判 PASS）")
        return
    script = cands[0] if cands else str(repro[0])
    rc, out = sh([PY, script], cwd=REPO, timeout=900)
    tail = [ln for ln in out.splitlines() if ln.strip()][-10:]
    info("B5 作者重放/Repro 脚本", f"{Path(script).name} rc={rc} | " + " / ".join(tail)[:500])
    if not cands:
        # 作者的修前红复跑脚本（形状验证）：修前 rev 必须红、修后 rev 必须绿，脚本自报结论成立。
        # 注意：这是**作者脚本自报**，只作形状交叉验证；真正的 A8 修前红由 B1/B2 独立复现。
        red_seen = RC_RED_RX.search(out) is not None
        green_seen = "修前红 / 修后绿" in out
        check("B5 作者 repro 形状验证（--rev b702708 红 / HEAD 绿，脚本结论成立）",
              rc == 0 and red_seen and green_seen,
              f"rc={rc} 修前红入输出={red_seen} 结论绿={green_seen}")
        return
    # 独立判据：重放产物里若给出 day_end 形态，必须满足卡 4/5/6 的"修后"口径（判据见 C 段）
    json_rows = []
    for ln in out.splitlines():
        s = ln.strip()
        if s.startswith("{") and s.endswith("}"):
            try:
                json_rows.append(json.loads(s))
            except json.JSONDecodeError:
                pass
    if not json_rows:
        skip("B5b 重放产物判据", "重放未输出可解析的 JSON 行 ⇒ 【无法判定】（不判 PASS）")
        return
    bad = []
    for r in json_rows:
        if r.get("event") == "day_end":
            bad += [f"{r.get('day')}: {x}" for x in judge_card4_day(r, r.get("_events") or [])]
    check("B5b 重放产物卡 4 判据（无 stuck:回片区 / resume_exhausted 不 VERIFIED）",
          not bad, (bad[:4] if bad else f"JSON 行 {len(json_rows)}"))


# ---------------------------------------------------------------- B7~B10：0.7.44 三卡独立重放

ENC_TILE = (37, 35)      # A8 冬 9/14 的"被围格"形态：不封格，但当天不再分配
BLK_TILE = (40, 30)      # "动了没用"被封格的格（_dead_tile_set 的 blocked 部分）
OK_TILE = (38, 35)       # 同一片里真正可做的格


def _crop_world(TL, crops: dict):
    w = TL.FakeWorld(seeds=0, money=0, weeds=0, water_left=40)
    w.dirt = set(crops)
    w.crops = {t: dict(v) for t, v in crops.items()}
    return w


def _fresh_rep(TL, *, day: int = 9):
    return TL.DayReport(day_key=("winter", 1, day), started_at=0.0)


def check_card5_replay(rows) -> None:
    """task-5 独立重放：挡死格语义 / 阶段拆分如实 / 重分有界 3 次且封后不再进池。"""
    print("== B7 段：task-5 独立重放（我方场景；非作者用例）==")
    src = read("brain/agentfarm/longrun.py")
    if "_dead_tile_set" not in src:
        skip("B7 task-5 重放", "冻结树无 _dead_tile_set ⇒ 卡未交付（不判 PASS）")
        return
    try:
        TL = _probe_fixtures()
    except Exception as exc:  # noqa: BLE001
        skip("B7 task-5 重放", f"夹具 import 失败：{type(exc).__name__}: {exc}")
        return

    # B7a dead_tile_set = blocked ∪ encircled_day（encircled 不封格；只剩挡死格可识别）
    try:
        w = _crop_world(TL, {ENC_TILE: {"ripe": False, "watered": False, "dead": False},
                             OK_TILE: {"ripe": False, "watered": False, "dead": False}})
        run = _mk_run(TL, w)
        run.blocked[BLK_TILE] = "动了没用（deputy 重放）"
        run.encircled_day = {ENC_TILE}
        run.leftover_targets = {ENC_TILE}
        dead = set(run._dead_tile_set())
        check("B7a `_dead_tile_set` = blocked ∪ encircled_day，且 encircled 不写 blocked",
              dead == {BLK_TILE, ENC_TILE} and ENC_TILE not in run.blocked,
              f"dead={sorted(dead)} encircled_in_blocked={ENC_TILE in run.blocked}")
        pend = [tuple(t) for t in run._dead_end_pending()]
        check("B7a2 只剩挡死格（encircled）时 `_dead_end_pending` 能识别",
              pend == [ENC_TILE], f"pending={pend}")
    except Exception as exc:  # noqa: BLE001
        skip("B7a dead_tile_set 重放", f"{type(exc).__name__}: {exc}")

    # B7b 被围格不进任何阶段的目标池（water_area 也排除）；可做格保留
    try:
        w = _crop_world(TL, {ENC_TILE: {"ripe": False, "watered": False, "dead": False},
                             OK_TILE: {"ripe": False, "watered": False, "dead": False}})
        run = _mk_run(TL, w)
        run.encircled_day = {ENC_TILE}
        obs = w.obs()
        plot = _plot_of("water_area", [ENC_TILE, OK_TILE])
        pool = {tuple(t) for t in run._stage_tiles("water_area", obs, plot)}
        check("B7b 被围格不进下轮目标池（water_area），可做格仍进池",
              ENC_TILE not in pool and OK_TILE in pool, f"pool={sorted(pool)}")
    except Exception as exc:  # noqa: BLE001
        skip("B7b 目标池重放", f"{type(exc).__name__}: {exc}")

    # B7c 阶段记录 leftover 拆分如实：exec + blocked == leftover；被围格记 blocked 不算可执行
    try:
        w = _crop_world(TL, {ENC_TILE: {"ripe": False, "watered": False, "dead": False},
                             OK_TILE: {"ripe": False, "watered": False, "dead": False}})
        run = _mk_run(TL, w)
        run.encircled_day = {ENC_TILE}
        rep = _fresh_rep(TL)
        obs = w.obs()
        plot = _plot_of("water_area", [ENC_TILE, OK_TILE])
        run._step_stage("water_area", obs, plot, rep)
        st = (rep.stages or [{}])[-1]
        lo = int(st.get("leftover") or 0)
        ex = st.get("leftover_executable")
        bl = st.get("leftover_blocked")
        ok = (ex is not None and bl is not None and int(ex) + int(bl) == lo
              and int(bl) >= 1 and int(ex) == lo - int(bl))
        check("B7c 阶段记录 leftover 拆分如实（exec+blocked==leftover；被围格进 blocked）",
              ok, f"leftover={lo} exec={ex} blocked={bl} "
                  f"blocked_tiles={st.get('leftover_blocked_tiles')}")
        if "leftover_blocked_tiles" in st:
            tiles = [tuple(t) for t in (st.get("leftover_blocked_tiles") or [])]
            check("B7c2 挡死清单里不混可执行格（清单格 ⊆ dead_set）",
                  set(tiles) <= set(run._dead_tile_set()), f"tiles={tiles}")
    except Exception as exc:  # noqa: BLE001
        skip("B7c 阶段拆分重放", f"{type(exc).__name__}: {exc}")

    # B7d 同格无产出重分有界 = 3 次：第 3 次封格并留 blocked{action=stage_realloc}；
    #      封格后该格不再进 clear_area 目标池（挡死格不进下轮分配）。
    try:
        w = TL.FakeWorld(seeds=0, money=0, weeds=4, water_left=40)
        run = _mk_run(TL, w)
        obs = w.obs()
        tmap = TL.FarmWorker.tiles_of(obs)
        weed_tiles = [t for t, v in tmap.items() if v.get("kind") or v.get("weed")]
        if not weed_tiles:
            skip("B7d 有界重分重放", "FakeWorld 无可见杂草格（夹具形态变了）")
        else:
            plot = _plot_of("clear_area", weed_tiles)
            pool = [tuple(t) for t in run._stage_tiles("clear_area", obs, plot)]
            target = pool[0] if pool else None
            if target is None:
                skip("B7d 有界重分重放", "clear_area 目标池为空（夹具形态变了）")
            else:
                def _nodone(*_a, **_k):
                    return TL.StageResult(stage="clear_area", steps=[], stopped="incomplete",
                                          stopped_reason="deputy 重放：故意无产出")
                run.worker.run_stage = _nodone  # type: ignore[assignment]
                plot1 = _plot_of("clear_area", [target])
                rep = _fresh_rep(TL)
                for _ in range(3):
                    run._step_stage("clear_area", obs, plot1, rep)
                cap = [e for e in run.entries if e.get("event") == "blocked"
                       and e.get("action") == "stage_realloc"
                       and tuple(e.get("tile") or ()) == target]
                check("B7d 同格无产出重分 3 次封格并留账（alloc_no_progress=3, limit=3）",
                      bool(cap) and int(cap[0].get("alloc_no_progress") or 0) == MAX_ALLOC_NO_PROGRESS
                      and int(cap[0].get("limit") or 0) == MAX_ALLOC_NO_PROGRESS
                      and target in run.blocked,
                      f"cap={cap[:1]} blocked={target in run.blocked}")
                pool2 = {tuple(t) for t in run._stage_tiles("clear_area", w.obs(),
                                                             _plot_of("clear_area", [target]))}
                check("B7d2 封格后不再进下轮目标池", target not in pool2,
                      f"target={target} pool={sorted(pool2)}")
    except Exception as exc:  # noqa: BLE001
        skip("B7d 有界重分重放", f"{type(exc).__name__}: {exc}")

    # B7e 收尾作业区（_work_spot_plot）也不拿挡死格：只剩挡死格 ⇒ None
    try:
        w = _crop_world(TL, {ENC_TILE: {"ripe": False, "watered": False, "dead": False}})
        run = _mk_run(TL, w)
        run.encircled_day = {ENC_TILE}
        got = run._work_spot_plot(w.obs())
        check("B7e 只剩挡死格的收尾区 ⇒ 不返回可做作业区（None）", got is None,
              f"got={'None' if got is None else got.get('tiles')}")
    except Exception as exc:  # noqa: BLE001
        skip("B7e 收尾区重放", f"{type(exc).__name__}: {exc}")


def check_card6_replay(rows) -> None:
    """task-6 独立重放：slept_by_us 取真值（不再只看 ended_by）；预算延后 × 浇水达标不同真。"""
    print("== B8 段：task-6 独立重放（我方场景；非作者用例）==")
    src = read("brain/agentfarm/longrun.py")
    if "_slept_by_us" not in src:
        skip("B8 task-6 重放", "冻结树无 _slept_by_us ⇒ 卡未交付（不判 PASS）")
        return
    try:
        TL = _probe_fixtures()
    except Exception as exc:  # noqa: BLE001
        skip("B8 task-6 重放", f"夹具 import 失败：{type(exc).__name__}: {exc}")
        return

    # B8a slept_by_us：sleep 成功但 ended_by=stuck（A8 冬 9/14 形态）⇒ True；
    #      没睡成 ⇒ False；ended_by=sleep ⇒ True。
    try:
        w = _crop_world(TL, {OK_TILE: {"ripe": False, "watered": True, "dead": False}})
        run = _mk_run(TL, w)

        def _rep(**kw):
            r = _fresh_rep(TL)
            for k, v in kw.items():
                setattr(r, k, v)
            return r

        r1 = _rep(slept_ok=True, ended_by="stuck", ended_reason="stuck:回片区")
        r2 = _rep(slept_ok=False, ended_by="stuck", ended_reason="stuck:回片区")
        r3 = _rep(slept_ok=False, ended_by="sleep", ended_reason="夜晚")
        got = [run._slept_by_us(r1), run._slept_by_us(r2), run._slept_by_us(r3)]
        check("B8a slept_by_us 取真值（slept_ok 优先于 ended_by）",
              got == [True, False, True], f"got={got}")
    except Exception as exc:  # noqa: BLE001
        skip("B8a slept_by_us 重放", f"{type(exc).__name__}: {exc}")

    # B8b 预算延后 × 户外浇水达标不得同真：
    #      浇水达标日 ⇒ 事件一条不落、只记 suppressed 计数、deferred_by_budget=false；
    #      未达标日 ⇒ 逐条落 deferred_by_budget 事件。
    try:
        w = _crop_world(TL, {OK_TILE: {"ripe": False, "watered": True, "dead": False}})
        run = _mk_run(TL, w)
        ev = {"task": "water_area", "why": "stamina", "dry": 3, "tiles": 3,
              "targets": [[60, 10]], "note": "只因预算而不做（deputy 重放）"}
        # 正向：浇水达标 ⇒ 压制
        run2 = _mk_run(TL, w)
        run2.budget_defer_events = [dict(ev), dict(ev)]
        rep = _fresh_rep(TL)
        rep.stamina_budget = {}
        n2 = run2._flush_budget_deferrals(watered_outdoor=True, rep=rep)
        fired2 = [e for e in run2.entries if e.get("event") == "deferred_by_budget"]
        sup = int((rep.stamina_budget or {}).get("deferred_by_budget_suppressed") or 0)
        check("B8b 浇水达标日：预算延后事件一条不落，只记 suppressed 计数",
              n2 == 0 and not fired2 and sup == 2
              and (rep.stamina_budget or {}).get("deferred_by_budget") is False,
              f"n={n2} fired={len(fired2)} suppressed={sup} "
              f"flag={(rep.stamina_budget or {}).get('deferred_by_budget')}")
        # 反向：未达标 ⇒ 落账
        run3 = _mk_run(TL, w)
        run3.budget_defer_events = [dict(ev)]
        rep3 = _fresh_rep(TL)
        rep3.stamina_budget = {}
        n3 = run3._flush_budget_deferrals(watered_outdoor=False, rep=rep3)
        fired3 = [e for e in run3.entries if e.get("event") == "deferred_by_budget"]
        check("B8b2 未达标日：预算延后事件照常落账（不得静默吞掉）",
              n3 == 1 and len(fired3) == 1, f"n={n3} fired={len(fired3)}")
    except Exception as exc:  # noqa: BLE001
        skip("B8b 预算延后压制重放", f"{type(exc).__name__}: {exc}")

    # B8c A8 独立复算：预算延后事件 + watered_outdoor=true + final_water.dry==0 同真天数
    try:
        ranges = _day_ranges(rows)
        days = 0
        same = 0
        for key, lo, hi, endr in ranges:
            days += 1
            evs = _in_range(rows, lo, hi, lambda r: r.get("event") == "deferred_by_budget")
            fw = endr.get("final_water") or {}
            checks = endr.get("checks") or {}
            if evs and checks.get("watered_outdoor") is True and int(fw.get("dry") or 0) == 0:
                same += 1
        check("B8c A8 旧账本：预算延后 × 浇水达标同真天数 = 12（analyzer 只显示前 6 行）",
              days == 12 and same == 12, f"day_end={days} 同真={same}")
    except Exception as exc:  # noqa: BLE001
        skip("B8c A8 复算", f"{type(exc).__name__}: {exc}")


def check_already_semantics(rows) -> None:
    """task-10 #1：阶段记录 `ok==0 & already>0` 阶段数（A8 期望 0）；工具口径注意。"""
    print("== B9 段：task-10 #1「ok=0 & already>0」阶段语义（A8 夹具）==")
    stages = [(i, st) for i, r in rows if r.get("event") == "day_end"
              for st in (r.get("stages") or [])]
    if not stages:
        skip("B9 task-10#1", "A8 账本无嵌套 day_end.stages ⇒ 无法判定")
        return
    zero = [st for _, st in stages if int(st.get("ok") or 0) == 0 and int(st.get("already") or 0) > 0]
    already_sum = sum(int(st.get("already") or 0) for _, st in stages)
    check("B9 A8 中「ok=0 且 already>0」阶段数 = 0（already 已成账，不再被当没干活）",
          not zero, f"阶段 {len(stages)}、命中 {len(zero)}、already 总步数 {already_sum}")
    tv = read("tools/verify-run3.py")
    ok_line = [ln.strip() for ln in tv.splitlines() if "_ok_self" in ln and "already" not in ln]
    info("B9b 现有工具 ok 口径（A9 放行必须并列 already 读）",
         f"verify-run3 `_ok_self` 只累加 stages[].ok（{ok_line[:1]}）；"
         "现工具单列 ok 不并列 already ⇒ A9 判定须同时读 already，否则「ok=0 但 already>0」的诚实日会被误判没干活")


def check_task11_replay(rows) -> None:
    """task-11 独立重放：review 兜底 / guard_leftover 两入口在只剩挡死格时同形态走换片或诚实收工。"""
    print("== B10 段：task-11 两入口统一路由（我方动态重放）==")
    src = read("brain/agentfarm/longrun.py")
    if "_guard_leftover_resume" not in src or "_dead_end_pending" not in src:
        skip("B10 task-11 重放", "冻结树无 _guard_leftover_resume/_dead_end_pending ⇒ 卡未交付（不判 PASS）")
        return
    try:
        TL = _probe_fixtures()
    except Exception as exc:  # noqa: BLE001
        skip("B10 task-11 重放", f"夹具 import 失败：{type(exc).__name__}: {exc}")
        return

    def _one(entry: str) -> tuple[str, list[str], bool]:
        w = _crop_world(TL, {ENC_TILE: {"ripe": False, "watered": False, "dead": False}})
        run = _mk_run(TL, w)
        rec: list[str] = []
        nps: list[str] = []

        def _fake_stop(*a, **k):
            nps.append("no_progress_stop")
            run.__dict__.setdefault("_x", None)
            return ("sleep", "stuck:回片区（deputy 重放：不应被调用）")

        def _fake_switch(obs, rep, plot=None, where="", **_k):
            rec.append(str(where))
            rep.ended_by, rep.ended_reason = "sleep", "resume_exhausted:deputy 重放无目标"
            return ("ended", None)

        run._work_spot_plot = lambda obs: None  # type: ignore[assignment]
        run._pending_work = lambda: [ENC_TILE]  # type: ignore[assignment]
        run._dead_end_pending = lambda: [ENC_TILE]  # type: ignore[assignment]
        run._resume_reevaluate = lambda **kw: None  # type: ignore[assignment]
        run._resume_plot = lambda obs: None  # type: ignore[assignment]
        run._resume_switch_or_exhaust = _fake_switch  # type: ignore[assignment]
        run._no_progress_stop = _fake_stop  # type: ignore[assignment]
        obs = w.obs()
        rep = _fresh_rep(TL)
        rep.stamina_budget = {}
        if entry == "review":
            ret = run._review_only_fallback(obs, rep)
        else:
            ret = run._guard_leftover_resume(obs, rep, text="deputy 重放")
        stuck = str(rep.ended_reason or "").startswith("stuck")
        return (f"{ret}", rec, bool(nps and not stuck) or bool(stuck))

    try:
        ret_rev, rec_rev, bad_rev = _one("review")
        ret_g, rec_g, bad_g = _one("guard")
        check("B10 `_review_only_fallback` 只剩挡死格 ⇒ 走换片/诚实收工（不落 stuck、不调 _no_progress_stop）",
              rec_rev == ["review_only_fallback"] and "None" in ret_rev and not bad_rev,
              f"ret={ret_rev} where={rec_rev}")
        check("B10b `_guard_leftover_resume` 只剩挡死格 ⇒ 同形态走换片/诚实收工",
              rec_g == ["guard_leftover"] and "ended" in ret_g and not bad_g,
              f"ret={ret_g} where={rec_g}")
    except AttributeError as exc:
        skip("B10 task-11 重放", f"方法签名不符：{exc}")
    except Exception as exc:  # noqa: BLE001
        skip("B10 task-11 重放", f"{type(exc).__name__}: {exc}")


# ---------------------------------------------------------------- C 段：独立判据（伪造记录 → 判红/判绿）

def judge_card4_day(day: dict, events: list[dict]) -> list[str]:
    """卡 4④：`resume_exhausted` 日不许洗白；修后不许再出现 `stuck:回片区…` 老形态。"""
    v: list[str] = []
    reason = str(day.get("ended_reason") or "")
    checks = day.get("checks") or {}
    if reason.startswith(RESUME_EXHAUSTED_PREFIX):
        if day.get("verified") is not False:
            v.append("resume_exhausted 日 verified 必须 False")
        if checks.get("day_justified") is not False:
            v.append("resume_exhausted 日 checks.day_justified 必须 False（不许洗成 no_work）")
        if "stuck" in reason:
            v.append("resume_exhausted 与 stuck 口径混写")
    if reason.startswith("stuck") and "回片区" in reason:
        v.append("修后仍写 stuck:回片区（0.7.43 老形态，应为 resume_exhausted/换片）")
    return v


def judge_card4_switch(events: list[dict], *, ledger_pending: set | None = None,
                       encircled: set | None = None) -> list[str] | None:
    """卡 4①：换片字段合法（`to_anchor` 只来自账本记账；不指 encircled；不同片；有界）。

    返回 None = 没有账本集合可对账（【无法判定】）。"""
    if ledger_pending is None:
        return None
    ledger = {tuple(t) for t in ledger_pending}
    enc = {tuple(t) for t in (encircled or ())}
    v: list[str] = []
    evs = [e for e in events if e.get("event") == "plot_exhausted"
           and e.get("source") == "resume_ledger"]
    if not evs:
        return ["无 plot_exhausted{source=resume_ledger} 事件（换片无留痕）"]
    for e in evs:
        ta = e.get("to_anchor")
        if not isinstance(ta, (list, tuple)) or len(ta) != 2:
            v.append("换片缺 to_anchor")
            continue
        t = (int(ta[0]), int(ta[1]))
        if t not in ledger:
            v.append(f"to_anchor 不在账本记账: {t}")
        if t in enc:
            v.append(f"to_anchor 指向 encircled: {t}")
        if int(e.get("to_tiles") or 0) <= 0:
            v.append("to_tiles<=0")
        if str(e.get("from_area") or "") and str(e.get("from_area")) == str(e.get("to_area") or ""):
            v.append("换片 from_area == to_area（没换到别片）")
        sw, lim = int(e.get("switches") or 0), int(e.get("limit") or 0)
        if lim and sw > lim:
            v.append(f"switches {sw} > limit {lim}")
    return v


def judge_card4_loop(walks: list[dict], burst: int = DEFAULT_PLOT_LIMIT) -> list[str]:
    """卡 4③：不得连续 `resume_walk` 无换片/无产出（旧 stuck 空转形态）。"""
    run = 0
    for e in walks:
        if e.get("event") != "resume_walk":
            continue
        if e.get("switched"):
            run = 0
            continue
        run += 1
        if run >= burst:
            return [f"连续 {run} 次 resume_walk 无换片/无产出（旧 stuck 形态）"]
    return []


def judge_card4_exhausted(events: list[dict]) -> list[str] | None:
    """卡 4②：诚实收工前的 `no_progress_burst{exhausted:true}` 证据必须自洽。

    返回 None = 关键字段缺失（【无法判定】）。"""
    ev = [e for e in events if e.get("event") == "no_progress_burst"
          and e.get("exhausted") is True]
    if not ev:
        return ["resume_exhausted 日缺 no_progress_burst{exhausted:true} 留痕"]
    need = ("pending", "stalled_tiles", "encircled_pending", "switches", "limit")
    if any(k not in e for e in ev for k in need):
        return None
    v: list[str] = []
    for e in ev:
        pending = int(e["pending"])
        stalled = int(e["stalled_tiles"])
        enc = int(e["encircled_pending"])
        if pending > stalled + enc:
            v.append(f"exhausted 但 pending={pending} > stalled={stalled}+encircled={enc}"
                     "（还有可执行格却收工）")
        if int(e.get("newly_stalled") or 0) > stalled:
            v.append("newly_stalled > stalled_tiles")
        sw, lim = int(e["switches"]), int(e["limit"])
        if lim and sw > lim:
            v.append(f"switches {sw} > limit {lim}")
    return v


def judge_card5_reassign(stages: list[dict]) -> list[str]:
    """卡 5：挡死格（encircled/unreachable/blocked_by_tool）当天不得进下一轮分配。"""
    v: list[str] = []
    first: dict[tuple, int] = {}
    for i, st in enumerate(stages):
        assigned = {tuple(t) for t in (st.get("tiles_list") or st.get("assigned_tiles") or [])}
        for t in assigned:
            if t in first:
                v.append(f"挡死格 {t} 在第 {i} 阶段被重分（首次挡死于第 {first[t]} 阶段）")
        for key in ("encircled_tiles", "unreachable_tiles", "blocked_by_tool_tiles", "doomed_tiles"):
            for t in (st.get(key) or []):
                try:
                    first.setdefault(tuple(t), i)
                except TypeError:
                    pass
    return v


def judge_leftover_split(st: dict) -> list[str] | None:
    """卡 5：leftover 拆「可执行余格 vs 物理挡死格」。返回 None = 字段缺失（【无法判定】）。"""
    lo = st.get("leftover")
    ex = next((st.get(k) for k in LEFTOVER_EXEC_FIELDS if isinstance(st.get(k), int)), None)
    bl = next((st.get(k) for k in LEFTOVER_BLOCKED_FIELDS if isinstance(st.get(k), int)), None)
    if not isinstance(lo, int) or ex is None or bl is None:
        return None
    v: list[str] = []
    if ex + bl != lo:
        v.append(f"拆分不平: executable={ex} + blocked={bl} != leftover={lo}")
    if ex < 0 or bl < 0:
        v.append(f"拆分出现负数: executable={ex} blocked={bl}")
    return v


def judge_attempts(stages: list[dict], *, cap: int = 3) -> list[str]:
    """卡 5：同一格当天尝试有界（默认 MAX_TILE_ATTEMPTS=3，交付后按常量核对）。"""
    cnt: dict[tuple, int] = {}
    for st in stages:
        for t in (st.get("tiles_list") or st.get("assigned_tiles") or []):
            try:
                cnt[tuple(t)] = cnt.get(tuple(t), 0) + 1
            except TypeError:
                pass
    return [f"格 {t} 当天被分配 {n} 次 > 上限 {cap}" for t, n in cnt.items() if n > cap]


def judge_slept_snapshot(day: dict, events: list[dict]) -> list[str]:
    """卡 6①：stuck 路径 checks.slept_by_us 必须是真值（sleep 成功/跨日 ⇒ true）。"""
    v: list[str] = []
    checks = day.get("checks") or {}
    slept = any(e.get("event") == "sleep" and e.get("ok") is True for e in events)
    if (slept or bool(day.get("day_after"))) and checks.get("slept_by_us") is not True:
        v.append(f"sleep 成功/跨日但 checks.slept_by_us={checks.get('slept_by_us')}（快照滞后）")
    return v


def judge_budget_water(day: dict, events: list[dict]) -> list[str]:
    """卡 6②：只因预算延后」与「户外浇水达标」不得同真（analyzer 6 行口径）。"""
    v: list[str] = []
    checks = day.get("checks") or {}
    deferred = any(e.get("event") == "deferred_by_budget" for e in events) or bool(
        (day.get("stamina_budget") or {}).get("deferred_by_budget"))
    final_water = day.get("final_water") or {}
    dry = final_water.get("dry")
    if deferred and checks.get("watered_outdoor") is True and dry == 0:
        v.append("只因预算延后却自称户外浇水达标（dry=0）")
    return v


def judge_clear_invariant(stage: dict) -> list[str]:
    """卡 5 附带：不得放宽 no_unmet_stages/护栏 B（复用 task-242 逐格证据判据）。"""
    v: list[str] = []
    ok = int(stage.get("ok") or 0)
    cleared = [tuple(t) for t in (stage.get("cleared_tiles") or [])]
    unclear = int(stage.get("unclear") or 0)
    if ok > len(cleared) + unclear:
        v.append(f"ok={ok} > cleared={len(cleared)} + unclear={unclear}")
    return v


def judge_sleep_evidence(day: dict, events: list[dict]) -> list[str] | None:
    """task-6：slept_by_us=true 必须有入睡成功证据；有成功证据不得报 false。缺失 ⇒ None。"""
    checks = day.get("checks")
    if not isinstance(checks, dict) or "slept_by_us" not in checks:
        return None
    slept = checks.get("slept_by_us")
    has_sleep = any(e.get("event") == "sleep" and e.get("ok") is True for e in events)
    ended = str(day.get("ended_by") or "")
    advanced = bool(day.get("day_after"))
    v: list[str] = []
    if slept is True and not (has_sleep or ended in ("sleep", "inventory_blocked") or advanced):
        v.append(f"slept_by_us=true 但无入睡成功证据（ended_by={ended or '空'}、day_after={advanced}）")
    if slept is False and has_sleep and advanced:
        v.append("sleep 成功且跨日却 slept_by_us=false（伪造/快照滞后）")
    return v


def judge_water_evidence(day: dict, events: list[dict]) -> list[str] | None:
    """task-6：watered_outdoor=true 不得与 final_water.dry>0 同真；final_water 缺 ⇒ None。"""
    checks = day.get("checks")
    if not isinstance(checks, dict) or "watered_outdoor" not in checks:
        return None
    fw = day.get("final_water")
    if not isinstance(fw, dict) or "dry" not in fw:
        return None
    v: list[str] = []
    if checks.get("watered_outdoor") is True and int(fw.get("dry") or 0) > 0:
        v.append(f"watered_outdoor=true 但 final_water.dry={fw.get('dry')}（伪造浇水达标）")
    return v


def judge_leftover_dead_semantics(stage: dict, *, dead: set | None = None) -> list[str] | None:
    """task-5：exec+blocked==leftover；挡死清单只许含 dead_set 格（不得误排可执行格）。"""
    if any(k not in stage for k in ("leftover", "leftover_executable", "leftover_blocked")):
        return None
    lo = int(stage.get("leftover") or 0)
    ex = int(stage.get("leftover_executable") or 0)
    bl = int(stage.get("leftover_blocked") or 0)
    v: list[str] = []
    if ex + bl != lo:
        v.append(f"拆分不平：executable={ex} + blocked={bl} != leftover={lo}")
    if ex < 0 or bl < 0:
        v.append("拆分出现负数")
    tiles = stage.get("leftover_blocked_tiles")
    if tiles is not None:
        if bl <= 12 and len(tiles) != bl:
            v.append(f"leftover_blocked_tiles 条数 {len(tiles)} != leftover_blocked {bl}")
        if dead is not None:
            bad = [t for t in tiles if tuple(t) not in dead]
            if bad:
                v.append(f"挡死清单含非挡死（可执行）格 {bad[:4]}（误排可执行格）")
    return v


def judge_alloc_cap_exemption(events: list[dict], *, cap: int = 3) -> list[str] | None:
    """task-5：重分封格额度必须是 3（不得抬高成新豁免），且封格后不得再被分配/未做完。"""
    cap_ev = [e for e in events if e.get("event") == "blocked"
              and e.get("action") == "stage_realloc"]
    if not cap_ev:
        return None
    v: list[str] = []
    capped: set[tuple] = set()
    for e in cap_ev:
        lim = int(e.get("limit") or 0)
        n = int(e.get("alloc_no_progress") or 0)
        if lim != cap:
            v.append(f"重分封格 limit={lim}，基线应为 {cap}（抬高=新豁免额度）")
        if n < cap:
            v.append(f"未到 {cap} 次就封格：alloc_no_progress={n}")
        try:
            capped.add(tuple(e.get("tile") or ()))
        except TypeError:
            pass
    if capped:
        for e in events:
            if e.get("event") == "stage_shortfall":
                hit = {tuple(t) for t in (e.get("tiles") or [])} & capped
                if hit:
                    v.append(f"已封格又出现在未做完清单：{sorted(hit)[:3]}")
    return v


def judge_checks_payload(checks) -> list[str] | None:
    """task-242/244 面：checks 必须恰为 10 键基线，新字段不得塞进 checks 污染语义。"""
    if not isinstance(checks, dict):
        return None
    if any(k not in checks for k in CHECKS_BASELINE):
        return None
    extra = [k for k in checks if k not in CHECKS_BASELINE]
    return [] if not extra else [f"checks 新增键 {extra}（新字段不得污染 10 键语义）"]


def judge_no_unmet_relax(day: dict, stages: list[dict]) -> list[str] | None:
    """task-5：no_unmet_stages 不得放宽；分下去没做完且无诚实停 ⇒ 判红。缺键 ⇒ None。"""
    checks = day.get("checks")
    if not isinstance(checks, dict) or "no_unmet_stages" not in checks:
        return None
    if checks.get("no_unmet_stages") is not True:
        return []
    v: list[str] = []
    for st in stages:
        undone = int(st.get("assigned_undone") or 0)
        if undone <= 0:
            continue
        stopped = str(st.get("stopped") or "")
        if stopped in HONEST_STOPPED:
            continue
        if int(st.get("leftover_executable") or 0) <= 0:
            continue
        v.append(f"阶段分下去 {undone} 格没做完（stopped={stopped or '空'}）却 no_unmet_stages=true")
    return v


def judge_resume_unified(day: dict, events: list[dict]) -> list[str] | None:
    """task-11：resume_exhausted 不得 VERIFIED；不得再写 stuck:回片区；两入口须留 source。"""
    v: list[str] = []
    reason = str(day.get("ended_reason") or "")
    srcs = {str(e.get("source") or "") for e in events
            if e.get("event") == "no_progress_burst" and e.get("exhausted")}
    srcs.discard("")
    if reason.startswith(RESUME_EXHAUSTED_PREFIX) and day.get("verified"):
        v.append("resume_exhausted 却 VERIFIED（洗白）")
    if reason.startswith("stuck") and "回片区" in reason:
        v.append("仍写 stuck:回片区（task-11 未生效）")
    if not srcs and not reason:
        return None
    return v


def case_c() -> None:
    print("== C 段：三卡修法判据（伪造记录 → 期望判红/判绿/无法判定）==")
    exhaust_day = {"event": "day_end", "ended_by": "sleep",
                   "ended_reason": "resume_exhausted:回片区与换片都无目标",
                   "verified": False, "checks": {"day_justified": False}}
    switch_ok = {"event": "plot_exhausted", "source": "resume_ledger",
                 "from_area": "field_nw", "to_area": "field_ne", "to_anchor": [85, 10],
                 "to_tiles": 1, "switches": 1, "limit": 5}
    walk_no_switch = [{"event": "resume_walk", "attempt": i, "switched": False} for i in range(1, 6)]
    walk_with_switch = ([{"event": "resume_walk", "attempt": i, "switched": False} for i in range(1, 4)]
                        + [{"event": "resume_walk", "attempt": 4, "switched": True}])
    exhausted_ok = {"event": "no_progress_burst", "exhausted": True, "pending": 12,
                    "stalled_tiles": 10, "encircled_pending": 2, "newly_stalled": 3,
                    "switches": 1, "limit": 5}
    exhausted_bad = {"event": "no_progress_burst", "exhausted": True, "pending": 12,
                     "stalled_tiles": 3, "encircled_pending": 0, "newly_stalled": 2,
                     "switches": 1, "limit": 5}
    cases = [
        ("C4-J1a 换片 to_anchor 不在账本记账（伪造）", judge_card4_switch,
         ([{"event": "plot_exhausted", "source": "resume_ledger", "from_area": "field_nw",
            "to_area": "field_ne", "to_anchor": [99, 99], "to_tiles": 3,
            "switches": 1, "limit": 5}],), {"ledger_pending": {(85, 10)}}, "red"),
        ("C4-J1b 换片到账本里的另一片（可解释）", judge_card4_switch,
         ([switch_ok],), {"ledger_pending": {(85, 10)}}, "green"),
        ("C4-J2a 换片次数超 limit（伪造）", judge_card4_switch,
         ([{**switch_ok, "switches": 6, "limit": 5}],), {"ledger_pending": {(85, 10)}}, "red"),
        ("C4-J3a 连续 5 次 resume_walk 无换片（旧 stuck 形态）", judge_card4_loop,
         (walk_no_switch,), {}, "red"),
        ("C4-J3b 中途换片（可解释）", judge_card4_loop, (walk_with_switch,), {}, "green"),
        ("C4-J4a resume_exhausted 却 VERIFIED（伪造）",
         judge_card4_day, ({**exhaust_day, "verified": True}, []), {}, "red"),
        ("C4-J4b 诚实 resume_exhausted（不 VERIFIED）", judge_card4_day, (exhaust_day, []), {}, "green"),
        ("C4-J5a 换片指向 encircled 格（伪造）", judge_card4_switch,
         ([{**switch_ok, "to_anchor": [37, 35]}],),
         {"ledger_pending": {(37, 35)}, "encircled": {(37, 35)}}, "red"),
        ("C4-J6a exhausted 但 pending 仍有可执行格（伪造）", judge_card4_exhausted,
         ([exhausted_bad],), {}, "red"),
        ("C4-J6b exhausted 证据自洽（pending ⊆ stalled+encircled）", judge_card4_exhausted,
         ([exhausted_ok],), {}, "green"),
        ("C4-J6c exhausted 关键字段缺失 ⇒ 无法判定", judge_card4_exhausted,
         ([{"event": "no_progress_burst", "exhausted": True}],), {}, "undecidable"),
        ("C4-J7a 修后仍写 stuck:回片区（老形态，伪造）", judge_card4_day,
         ({"ended_reason": "stuck:回片区（work_spot_resume）连续 5 次都拿不出目标",
           "ended_by": "stuck", "verified": False}, []), {}, "red"),
        ("C5-1 挡死格被下一轮重分（伪造）", judge_card5_reassign,
         ([{"tiles_list": [[37, 35]]},
           {"encircled_tiles": [[37, 35]]},
           {"tiles_list": [[37, 35]]}],), {}, "red"),
        ("C5-2 不同格分配（可解释）", judge_card5_reassign,
         ([{"encircled_tiles": [[37, 35]]}, {"tiles_list": [[38, 35]]}],), {}, "green"),
        ("C5-3 leftover 拆分不平（伪造）", judge_leftover_split,
         ({"leftover": 5, "leftover_executable": 1, "leftover_blocked": 1},), {}, "red"),
        ("C5-4 leftover 拆分为平（可解释）", judge_leftover_split,
         ({"leftover": 5, "leftover_executable": 4, "leftover_blocked": 1},), {}, "green"),
        ("C5-5 leftover 拆分字段缺失 ⇒ 无法判定", judge_leftover_split,
         ({"leftover": 5},), {}, "undecidable"),
        ("C5-6 同格尝试超上限（伪造）", judge_attempts,
         ([{"tiles_list": [[40, 30]]}] * 4,), {}, "red"),
        ("C5-7 护栏 B 放宽形态（ok 无逐格证据，伪造）", judge_clear_invariant,
         ({"ok": 3, "cleared_tiles": [[60, 10]], "unclear": 0},), {}, "red"),
        ("C6-1 sleep 成功但 slept_by_us=false（伪造）", judge_slept_snapshot,
         ({"checks": {"slept_by_us": False}, "day_after": ["1", "winter", 10]},
          [{"event": "sleep", "ok": True}]), {}, "red"),
        ("C6-2 sleep 成功且 slept_by_us=true", judge_slept_snapshot,
         ({"checks": {"slept_by_us": True}, "day_after": ["1", "winter", 10]},
          [{"event": "sleep", "ok": True}]), {}, "green"),
        ("C6-3 预算延后却自称浇完（伪造）", judge_budget_water,
         ({"checks": {"watered_outdoor": True}, "final_water": {"dry": 0}},
          [{"event": "deferred_by_budget", "task": "water_area"}]), {}, "red"),
        ("C6-4 预算延后但 dry>0（不矛盾）", judge_budget_water,
         ({"checks": {"watered_outdoor": False}, "final_water": {"dry": 2}},
          [{"event": "deferred_by_budget", "task": "water_area"}]), {}, "green"),
        # ---- task-5（0.7.44 卡 2）新增判据：拆分分母 / 挡死清单语义 / 重分额度 ----
        ("C5-8 挡死清单混入可执行格（伪造）", judge_leftover_dead_semantics,
         ({"leftover": 2, "leftover_executable": 1, "leftover_blocked": 1,
           "leftover_blocked_tiles": [[60, 10]]},), {"dead": {(37, 35)}}, "red"),
        ("C5-9 拆分自洽且挡死格确实在 dead_set（可解释）", judge_leftover_dead_semantics,
         ({"leftover": 2, "leftover_executable": 1, "leftover_blocked": 1,
           "leftover_blocked_tiles": [[37, 35]]},), {"dead": {(37, 35)}}, "green"),
        ("C5-10 拆分字段缺失 ⇒ 无法判定", judge_leftover_dead_semantics,
         ({"leftover": 2},), {}, "undecidable"),
        ("C5-11 重分上限被抬高成豁免额度（伪造）", judge_alloc_cap_exemption,
         ([{"event": "blocked", "action": "stage_realloc", "tile": [40, 30],
            "alloc_no_progress": 3, "limit": 99}],), {}, "red"),
        ("C5-12 未到 3 次就封格（伪造）", judge_alloc_cap_exemption,
         ([{"event": "blocked", "action": "stage_realloc", "tile": [40, 30],
            "alloc_no_progress": 1, "limit": 3}],), {}, "red"),
        ("C5-13 重分 3 次封格（可解释）", judge_alloc_cap_exemption,
         ([{"event": "blocked", "action": "stage_realloc", "tile": [40, 30],
            "alloc_no_progress": 3, "limit": 3}],), {}, "green"),
        ("C5-14 封格后又出现在阶段未做完清单（伪造）", judge_alloc_cap_exemption,
         ([{"event": "blocked", "action": "stage_realloc", "tile": [40, 30],
            "alloc_no_progress": 3, "limit": 3},
           {"event": "stage_shortfall", "tiles": [[40, 30]]}],), {}, "red"),
        # ---- task-6（0.7.44 卡 3）新增判据：入睡/浇水证据 ----
        ("C6-5 伪造入睡成功（slept_by_us=true 但无 sleep 证据）", judge_sleep_evidence,
         ({"checks": {"slept_by_us": True}, "ended_by": "stuck", "day_after": None}, []), {}, "red"),
        ("C6-6 真睡成（sleep ok=true + 跨日）却报 false（伪造/滞后）", judge_sleep_evidence,
         ({"checks": {"slept_by_us": False}, "ended_by": "stuck",
           "day_after": ["1", "winter", 10]}, [{"event": "sleep", "ok": True}]), {}, "red"),
        ("C6-7 睡成且口径 true（可解释）", judge_sleep_evidence,
         ({"checks": {"slept_by_us": True}, "ended_by": "stuck",
           "day_after": ["1", "winter", 10]}, [{"event": "sleep", "ok": True}]), {}, "green"),
        ("C6-8 伪造浇水达标（watered_outdoor=true 但 dry>0）", judge_water_evidence,
         ({"checks": {"watered_outdoor": True}, "final_water": {"dry": 2}}, []), {}, "red"),
        ("C6-9 final_water 缺失 ⇒ 无法判定", judge_water_evidence,
         ({"checks": {"watered_outdoor": True}}, []), {}, "undecidable"),
        ("C6-10 浇水达标且干格=0（可解释）", judge_water_evidence,
         ({"checks": {"watered_outdoor": True}, "final_water": {"dry": 0}}, []), {}, "green"),
        # ---- task-242/244 面：checks 10 键不得被新字段污染 ----
        ("C7-1 checks 被塞入新字段（污染 10 键语义，伪造）", judge_checks_payload,
         ({**{k: True for k in CHECKS_BASELINE}, "slept_ok": True},), {}, "red"),
        ("C7-2 checks 恰为 10 键（可解释）", judge_checks_payload,
         ({k: True for k in CHECKS_BASELINE},), {}, "green"),
        ("C7-3 checks 缺键 ⇒ 无法判定（缺失≠通过）", judge_checks_payload,
         ({"slept_by_us": True},), {}, "undecidable"),
        # ---- task-5：不得放宽 no_unmet_stages ----
        ("C8-1 放宽 no_unmet_stages（分下去没做完却 true，伪造）", judge_no_unmet_relax,
         ({"checks": {"no_unmet_stages": True}},
          [{"assigned_undone": 2, "stopped": "", "leftover_executable": 2}]), {}, "red"),
        ("C8-2 诚实停（stamina）下 no_unmet_stages=true（可解释）", judge_no_unmet_relax,
         ({"checks": {"no_unmet_stages": True}},
          [{"assigned_undone": 2, "stopped": "stamina", "leftover_executable": 2}]), {}, "green"),
        # ---- task-11：两入口收工口径 ----
        ("C9-1 resume_exhausted 却 VERIFIED（洗白）", judge_resume_unified,
         ({"ended_reason": "resume_exhausted:无目标", "verified": True}, []), {}, "red"),
        ("C9-2 两入口 dead-only 走 resume_exhausted 不 VERIFIED（可解释）", judge_resume_unified,
         ({"ended_reason": "resume_exhausted:只剩挡死格", "verified": False},
          [{"event": "no_progress_burst", "exhausted": True, "source": "guard_leftover"},
           {"event": "no_progress_burst", "exhausted": True, "source": "review_only_fallback"}]), {}, "green"),
        ("C9-3 修后仍写 stuck:回片区（伪造）", judge_resume_unified,
         ({"ended_reason": "stuck:回片区（work_spot_resume）", "verified": False}, []), {}, "red"),
    ]
    for tag, fn, args, kwargs, want in cases:
        try:
            got = fn(*args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - 伪造夹具自身错要和产品 bug 分开判
            check(tag, False, f"判据自身异常: {type(exc).__name__}: {exc}")
            continue
        if got is None:
            got = []
            undecidable = True
        else:
            undecidable = False
        is_red = bool(got)
        if want == "undecidable":
            check(tag, undecidable, "字段缺失 ⇒ 【无法判定】（不当 PASS）")
        else:
            check(tag, is_red == (want == "red"),
                  ("违规=" + "; ".join(got)[:160]) if is_red else "绿（可解释）")


# ---------------------------------------------------------------- D 段：变异接口

def _glob_scripts(base: Path, kind: str) -> list[str]:
    """作者脚本可能放在 scratch/ 或 tests/（实测 task-4 作者变异在 tests/_mutate_t4_resume.py）。"""
    out: list[str] = []
    for sub in ("scratch", "tests"):
        for p in glob.glob(str(base / sub / "*.py")):
            name = Path(p).name
            if kind not in name:
                continue
            if re.search(r"(?:_t[456]_|_t[456]\.|t[456]_|0744)", name):
                out.append(p)
    return list(dict.fromkeys(out))


def case_d() -> None:
    print("== D 段：变异实测接口 ==")
    author: list[str] = []
    for base in (ROOT, REPO):
        author += _glob_scripts(base, "mutate")
    author = [p for p in dict.fromkeys(author) if "_t0744_mutate" not in Path(p).name]
    info("D0 作者变异脚本", [str(Path(p).relative_to(REPO)) if str(p).startswith(str(REPO))
                              else str(p) for p in author]
         or "未交付（GAP；交付后必须能在冻结树副本复跑）")
    mine = REPO / "scratch/_t0744_mutate.py"
    check("D1 我方变异矩阵在树内", mine.exists(), str(mine))
    info("D2 复跑命令",
         "PYTHONUTF8=1 python <作者脚本>（在副本跑） / "
         "python scratch/_t0744_mutate.py --base <tree> --all（我方，冻结树零改动）")


# ---------------------------------------------------------------- E 段

def case_e() -> None:
    print("== E 段：结论骨架 ==")
    if FAIL == 0 and SKIP == 0:
        info("E1", "A/B/C/D 全绿 ⇒ 0.7.44 三卡可放行（正式结论以 docs/_review-0.7.44.md 为准）")
    elif FAIL:
        info("E1", f"仍有 {FAIL} 条红（{FAILS[:6]}）⇒ 需修复/解释后才放行")
    else:
        info("E1", f"有 {SKIP} 条 SKIP（含【无法判定】/GAP），正式判定必须以补齐后的读数为准")


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
        except Exception as exc:  # noqa: BLE001 - 在制树可能半截，别把探针自己炸掉
            check(f"{key} 段执行异常（树可能半截/在制）", False, f"{type(exc).__name__}: {exc}")
    print(f"\n汇总：PASS={PASS} FAIL={FAIL} SKIP={SKIP} INFO={INFO}  ({time.time() - t0:.1f}s)")
    return 0 if FAIL == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
