# -*- coding: utf-8 -*-
"""【task-23 / 0.7.45 合并回归】deputy-lead 独立对抗探针（冻结树 2feb1f8）。

只读：被测树由 T0745B_ROOT 指定（默认仓库根）。判据全部是 deputy 自己的实现，
不 import 作者测试的断言结论；B 段动态重放用 tests/test_longrun.py 的夹具
（FakeWorld / make_run / FakeClient）——夹具只提供世界，判据在本文件里。

用法：
    PYTHONUTF8=1 python scratch/_t0745b_probe.py --only A,B,C,D
    T0745B_ROOT=%TEMP%\\t0745b_frozen T0745B_COMMIT=2feb1f8 ... --readings
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
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("T0745B_ROOT", str(REPO)))
COMMIT = os.environ.get("T0745B_COMMIT", "2feb1f8")
BASELINE = os.environ.get("T0745B_BASELINE", "37cac51")   # 0.7.44 冻结
PY = sys.executable
LONG = ROOT / "brain" / "agentfarm" / "longrun.py"
FARM = ROOT / "brain" / "agentfarm" / "farmwork.py"
TESTS = ROOT / "tests" / "test_longrun.py"
A8 = REPO / "logs" / "longrun-runA8-0743.jsonl"
SMOKE = REPO / "logs" / "longrun-smoke-0744.jsonl"
GAPS = REPO / "logs" / "longrun-smoke-0744-gaps.json"

CHECKS_BASELINE = (
    "slept_by_us", "no_blocking_modal", "no_hard_failures",
    "unreachable_within_bound", "refused_within_bound", "no_unmet_stages",
    "crops_watered", "watered_outdoor", "day_justified", "zero_action_evidenced",
)
JUSTIFIED_END_REASONS = ("night", "stamina", "no_work")
HONEST_EXHAUSTED_END_REASONS = ("resume_exhausted",)

# task-15 七字段 + task-16 七字段 + task-22 一字段
NEW_DAY_FIELDS = {
    "pending_ledger", "pending_guard", "pending_stalled", "pending_executable",
    "pending_blocked", "pending_unobserved", "stage_midway_leftover",
    "free_slots_start", "free_slots_last", "free_slots_min", "free_slots_status",
    "loot_lost_steps", "loot_lost_tiles", "loot_lost_items",
    "pending_malformed",
}
KEY_FILES = [
    "brain/agentfarm/longrun.py",
    "brain/agentfarm/farmwork.py",
    "tests/test_longrun.py",
    "tests/_mutate_t15_justified.py",
    "tests/_mutate_t16_inventory.py",
    "tests/_mutate_t22_malformed.py",
    "brain/agentfarm/bridge.py",
    "mod/AgentFarm.Bridge/manifest.json",
]

COUNT = {"PASS": 0, "FAIL": 0, "SKIP": 0, "INFO": 0}


def _emit(kind: str, tag: str, detail: str = "") -> None:
    COUNT[kind] += 1
    line = f"  {kind:<4} {tag}"
    if detail:
        line += f" —— {detail}"
    print(line)


def check(tag: str, ok: bool, detail: str = "") -> bool:
    _emit("PASS" if ok else "FAIL", tag, detail)
    return bool(ok)


def info(tag: str, detail: str = "") -> None:
    _emit("INFO", tag, detail)


def skip(tag: str, detail: str = "") -> None:
    _emit("SKIP", tag, detail)


def read(p: Path) -> str:
    return p.read_text(encoding="utf-8", errors="replace")


def sh(args: list[str], cwd: Path | None = None, timeout: int = 900) -> subprocess.CompletedProcess:
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = str(ROOT / "brain") + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(args, cwd=str(cwd or REPO), env=env, text=True,
                          encoding="utf-8", errors="replace",
                          capture_output=True, timeout=timeout)


def git_show(commit: str, path: str) -> str:
    p = subprocess.run(["git", "-C", str(REPO), "show", f"{commit}:{path}"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.stdout if p.returncode == 0 else ""


def blob_sha(data: bytes) -> str:
    h = hashlib.sha1()
    h.update(b"blob %d\0" % len(data))
    h.update(data)
    return h.hexdigest()


def load_jsonl(p: Path) -> list[dict]:
    rows = []
    for line in read(p).splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows


def day_text_of(row: dict) -> str:
    txt = row.get("day_text")
    if isinstance(txt, str) and txt:
        return txt
    day = row.get("day")
    if isinstance(day, list) and len(day) == 3:
        return f"{day[1]} {day[2]}"
    if isinstance(day, dict):
        return f"{day.get('season')} {day.get('day')}"
    return ""


# ---------------------------------------------------------------- A 段
def case_a() -> None:
    print("\n== A 段：provenance / 字段 / 公式 / 顺序 ==")
    if not (ROOT / ".git").exists() and ROOT != REPO:
        pass
    # A0 全量 provenance
    p = subprocess.run(["git", "-C", str(REPO), "ls-tree", "-r", COMMIT],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    if p.returncode != 0:
        skip("A0 provenance", f"git ls-tree {COMMIT} 失败：{p.stderr[:160]}")
    else:
        tracked = 0
        missing = 0
        mismatch = 0
        eol = 0
        for line in p.stdout.splitlines():
            if not line.strip():
                continue
            meta, _, path = line.partition("\t")
            tracked += 1
            f = ROOT / path
            if not f.is_file():
                missing += 1
                continue
            data = f.read_bytes()
            want = meta.split()[2]
            if blob_sha(data) == want:
                continue
            if blob_sha(data.replace(b"\r\n", b"\n")) == want:
                eol += 1
                continue
            mismatch += 1
        check("A0 provenance", missing == 0 and mismatch == 0,
              f"{COMMIT} 追踪 {tracked}、缺失 {missing}、不符 {mismatch}、eol 展开 {eol}")
    # A0b 关键文件
    key_bad = []
    for rel in KEY_FILES:
        f = ROOT / rel
        if not f.is_file():
            key_bad.append(f"{rel}: 缺")
            continue
        got = blob_sha(f.read_bytes())
        q = subprocess.run(["git", "-C", str(REPO), "rev-parse", f"{COMMIT}:{rel}"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        want = q.stdout.strip()
        if got != want:
            key_bad.append(f"{rel}: {got[:12]}!={want[:12]}")
    check("A0b 关键文件 blob", not key_bad, "; ".join(key_bad) or f"{len(KEY_FILES)}/{len(KEY_FILES)} 相等")

    bridge = ROOT / "brain" / "agentfarm" / "bridge.py"
    if bridge.is_file():
        src = read(bridge)
        check("A1 bridge 版本", 'MOD_VERSION_EXPECTED = "0.7.45"' in src,
              "MOD_VERSION_EXPECTED=0.7.45" if 'MOD_VERSION_EXPECTED = "0.7.45"' in src else "未命中")
    else:
        skip("A1 bridge 版本", "bridge.py 缺失")
    man = ROOT / "mod" / "AgentFarm.Bridge" / "manifest.json"
    if man.is_file():
        try:
            mv = str(json.loads(read(man)).get("Version") or "")
        except Exception:
            mv = "解析失败"
        check("A1b manifest 版本", mv == "0.7.45", f"Version={mv}")
    else:
        skip("A1b manifest 版本", "manifest.json 缺失")

    src = read(LONG)
    # A2 checks 10 键
    try:
        tree = ast.parse(src)
        checks_keys = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                tgt = node.targets[0]
                if isinstance(tgt, ast.Attribute) and tgt.attr == "checks" and isinstance(node.value, ast.Dict):
                    keys = []
                    for k in node.value.keys:
                        if isinstance(k, ast.Constant) and isinstance(k.value, str):
                            keys.append(k.value)
                    checks_keys = tuple(keys)
        if checks_keys is None:
            skip("A2 checks 10 键", "AST 未找到 rep.checks 字面")
        else:
            check("A2 checks 10 键", checks_keys == CHECKS_BASELINE,
                  f"{len(checks_keys)} 键：{','.join(checks_keys)}")
    except SyntaxError as exc:
        skip("A2 checks 10 键", f"AST 失败：{exc}")

    # A3 DayReport 新增字段 = 15（task-15 七 + task-16 七 + task-22 一）
    def dr_fields(text: str) -> set[str]:
        try:
            t = ast.parse(text)
        except SyntaxError:
            return set()
        for node in ast.walk(t):
            if isinstance(node, ast.ClassDef) and node.name == "DayReport":
                out = set()
                for st in node.body:
                    if isinstance(st, ast.AnnAssign) and isinstance(st.target, ast.Name):
                        out.add(st.target.id)
                return out
        return set()

    base_src = git_show(BASELINE, "brain/agentfarm/longrun.py")
    cur_fields = dr_fields(src)
    base_fields = dr_fields(base_src)
    if not base_fields:
        skip("A3 DayReport 字段差集", f"读不到 {BASELINE} 基线")
    else:
        added = cur_fields - base_fields
        removed = base_fields - cur_fields
        check("A3 DayReport 字段差集", added == NEW_DAY_FIELDS and not removed,
              f"新增 {sorted(added)}；删除 {sorted(removed)}；期望新增 {len(NEW_DAY_FIELDS)} 个")
        to_dict_added = all(k in src for k in ("\"pending_malformed\":", "\"loot_lost_steps\":"))
        check("A3b to_dict 导出", to_dict_added, "pending_malformed/loot_lost_steps 均在 to_dict")

    # A4 新 journal 事件名（0 个）
    def journal_names(text: str) -> set[str]:
        try:
            t = ast.parse(text)
        except SyntaxError:
            return set()
        names = set()
        for node in ast.walk(t):
            if (isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute)
                    and node.func.attr == "_journal" and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and isinstance(node.args[0].value, str)):
                names.add(node.args[0].value)
        return names

    new_events = journal_names(src) - journal_names(base_src)
    check("A4 新 journal 事件名", not new_events, f"新增 {sorted(new_events)}")

    # A5 checks 公式未动（no_unmet_stages / 护栏 B / 旧白名单）
    def _formula(text: str) -> str:
        i = text.find("unmet_leftover == 0 and (")
        if i < 0:
            return ""
        seg = text[i:i + 400]
        cut = seg.find("make_any_progress")
        if cut < 0:
            cut = seg.find("made_any_progress")
        depth = 0
        for j, ch in enumerate(seg):
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    seg = seg[:j + 1]
                    break
        return re.sub(r"\s+", " ", seg).strip()

    cur_f = _formula(src)
    base_f = _formula(base_src)
    check("A5a no_unmet_stages 公式", bool(cur_f) and cur_f == base_f,
          f"当前={cur_f[:120]} | 基线={base_f[:120]}")
    m_cur = re.search(r'"cleared_tiles":\s*([^\n]+)', src)
    m_base = re.search(r'"cleared_tiles":\s*([^\n]+)', base_src)
    same_clear = bool(m_cur and m_base and m_cur.group(1) == m_base.group(1))
    check("A5b 护栏 B cleared_tiles", same_clear,
          (m_cur.group(1).strip() if m_cur else "冻结树无") + " | 基线：" + (m_base.group(1).strip() if m_base else "无"))
    check("A5c 旧白名单字面", f"JUSTIFIED_END_REASONS = {JUSTIFIED_END_REASONS!r}" in src
          or "JUSTIFIED_END_REASONS = (\"night\", \"stamina\", \"no_work\")" in src,
          "JUSTIFIED_END_REASONS 未变" if "JUSTIFIED_END_REASONS = (\"night\", \"stamina\", \"no_work\")" in src else "字面变化")

    # A6 malformed 一票否决在全部白名单之前
    m = re.search(r"def is_justified_end\(.*?\n(?=\ndef |\nclass )", src, re.S)
    if not m:
        skip("A6 malformed 否决顺序", "找不到 is_justified_end 函数段")
    else:
        body = m.group(0)
        i_mal = body.find("if int(malformed_tiles) > 0")
        i_end = body.find('if ended_by != "sleep"')
        i_jus = body.find("if prefix in JUSTIFIED_END_REASONS")
        i_hon = body.find("if prefix in HONEST_EXHAUSTED_END_REASONS")
        order = [i for i in (i_mal, i_end, i_jus, i_hon)]
        check("A6 malformed 否决顺序", all(x >= 0 for x in order) and order == sorted(order),
              f"malformed={i_mal} ended_by={i_end} justified={i_jus} honest={i_hon}")

    # A7 day_justified 调用带证据
    seg = re.search(r'"day_justified":\s*is_justified_end\((.*?)\),', src, re.S)
    if not seg:
        skip("A7 day_justified 证据参数", "找不到 checks.day_justified 调用")
    else:
        a = seg.group(1)
        check("A7 day_justified 证据参数",
              "pending_executable=rep.pending_executable" in a and "malformed_tiles=rep.pending_malformed" in a,
              a.replace("\n", " ")[:160])

    # A8 三卡源码标记
    long_markers = ("_pending_snapshot", "_dead_end_pending", "_resume_exhausted",
                    "pending_malformed", "player_free_slots", "_note_loot_lost",
                    "_slot_relief", "free_slots_status")
    miss = [x for x in long_markers if x not in src]
    check("A8a longrun 标记", not miss, f"缺 {miss}" if miss else f"{len(long_markers)}/{len(long_markers)} 命中")
    fsrc = read(FARM)
    fmark = ("def player_free_slots", "loot_risk", "loot_lost", "slot_relief_plan")
    fmiss = [x for x in fmark if x not in fsrc]
    check("A8b farmwork 标记", not fmiss, f"缺 {fmiss}" if fmiss else f"{len(fmark)}/{len(fmark)} 命中")
    ts = read(TESTS)
    tmark = ("TestTask15PendingCaliber", "TestTask16InventoryFull", "TestTask22MalformedTiles")
    tmiss = [x for x in tmark if x not in ts]
    check("A8c 作者测试类在树内", not tmiss, f"缺 {tmiss}" if tmiss else "3/3 命中")

    # A9 旧账本 ok/already 口径（task-10 #1）
    if A8.is_file():
        rows = load_jsonl(A8)
        ends = [r for r in rows if r.get("event") == "day_end"]
        n_bad = 0
        n_stage = 0
        already = 0
        for r in ends:
            for st in (r.get("stages") or []):
                n_stage += 1
                try:
                    ok = int(st.get("ok") or 0)
                except (TypeError, ValueError):
                    ok = 0
                try:
                    al = int(st.get("already") or 0)
                except (TypeError, ValueError):
                    al = 0
                already += al
                if ok == 0 and al > 0:
                    n_bad += 1
        check("A9 A8 账本 ok=0&already>0", n_bad == 0,
              f"阶段 {n_stage} 条、违规 {n_bad} 条、already 总步数 {already}")
        info("A9b 工具口径", "tools/verify-run3.py 只累加/单列 stages[].ok；A9 必须并列读 already/attempted_ok")
    else:
        skip("A9 A8 旧账本", f"缺 {A8}")


# ---------------------------------------------------------------- B 段
def _tree_eol_bytes(rel: str) -> bytes:
    return (ROOT / rel).read_bytes()


def _smoke_day_blocks(rows: list[dict]) -> dict[str, list[dict]]:
    ends = [(i, r) for i, r in enumerate(rows) if r.get("event") == "day_end"]
    out: dict[str, list[dict]] = {}
    for n, (i, r) in enumerate(ends):
        start = ends[n - 1][0] + 1 if n else 0
        out[day_text_of(r)] = rows[start:i + 1]
    return out


def case_b1() -> None:
    print("\n== B1 段：A8/smoke 账本独立复算（263/217 归属表） ==")
    if not SMOKE.is_file():
        skip("B1 smoke 账本", f"缺 {SMOKE}")
        return
    rows = load_jsonl(SMOKE)
    blocks = _smoke_day_blocks(rows)
    d26 = next((v for k, v in blocks.items() if "winter" in k and "26" in k), [])
    d27 = next((v for k, v in blocks.items() if "winter" in k and "27" in k), [])
    check("B1a smoke 两天日界", bool(d26) and bool(d27),
          f"日界 {sorted(blocks)[:4]}… 共 {len(blocks)} 天")

    if d26:
        bursts = [e for e in d26 if e.get("event") == "plot_exhausted_burst"]
        anchor = max((float(e.get("t") or 0) for e in bursts), default=0.0)
        burst = [e for e in d26 if e.get("event") == "plot_exhausted"
                 and 0 <= anchor - float(e.get("t") or 0) <= 1.5]
        ts = [float(e.get("t") or 0) for e in burst]
        same_sec = len(burst) >= 5 and (max(ts) - min(ts) <= 1.0)
        notes_263 = all("263" in str(e.get("note") or "") for e in burst)
        ok = same_sec and notes_263 and any(int(e.get("count") or 0) >= 5 for e in bursts)
        check("B1b 冬26 263/5连发", ok,
              f"burst 时刻 {anchor:.2f} 前 1.5s 内 plot_exhausted {len(burst)} 条、跨度 "
              f"{(max(ts) - min(ts)) if ts else -1:.2f}s、守卫文本含 263={notes_263}")
        end26 = d26[-1] if d26 else {}
        info("B1c 冬26 旧形态", f"ended_by={end26.get('ended_by')} reason={str(end26.get('ended_reason'))[:52]}")
    if d27:
        end27 = d27[-1]
        npb = [e for e in d27 if e.get("event") == "no_progress_burst"]
        sml = [e for e in d27 if e.get("event") == "stage_midway_leftover"]
        us = [e for e in d27 if e.get("event") == "unreachable_summary"]
        unreach = (us[-1].get("tiles") if us else []) or []
        e = npb[-1] if npb else {}
        pend = int(e.get("pending") or 0)
        stalled = int(e.get("stalled_tiles") or 0)
        arith = [int(s.get("leftover") or 0) for s in sml]
        ok = (pend == 217 and stalled == 217 and "work_spot_resume" in str(e.get("source") or "")
              and str(end27.get("ended_reason") or "").startswith("resume_exhausted")
              and any(a == 220 for a in arith) and len(unreach) == 3)
        check("B1d 冬27 217=220-3", ok,
              f"burst pending={pend} stalled={stalled} source={e.get('source')} "
              f"midway leftover={arith} 挡死格={len(unreach)}")
        info("B1e 40 格【无法判定】", f"263 − 223(211 exec+12 blocked) = 40；unreachable_summary={len(unreach)} 格")
    if GAPS.is_file():
        try:
            g = json.loads(read(GAPS))
            total = sum(int(x.get("count") or 0) for x in (g.get("gaps") or []))
            kinds = {x.get("kind"): int(x.get("count") or 0) for x in (g.get("gaps") or [])}
        except Exception as exc:
            total, kinds = -1, {"parse": str(exc)}
        check("B1f gaps 17 格", total == 17, f"总计 {total}：{kinds}")
    else:
        skip("B1f gaps", "缺 gaps.json")


def _fixtures():
    sys.path.insert(0, str(ROOT / "tests"))
    sys.path.insert(0, str(ROOT / "brain"))
    import test_longrun as TL  # noqa: PLC0415
    from agentfarm import farmwork as FW  # noqa: PLC0415
    return TL, FW


def _world(TL, **kw):
    allowed = {"seeds", "money", "weeds", "water_left", "stamina", "scythe"}
    kw = {k: v for k, v in kw.items() if k in allowed}
    return TL.FakeWorld(**kw)


def _mk_run(TL, FW, world):
    client = TL._CountingClient(world) if hasattr(TL, "_CountingClient") else TL.FakeClient(world)
    worker = FW.FarmWorker(client, log=lambda *a, **k: None)
    run = TL.make_run(world, target_days=1, max_days=1,
                      client_factory=lambda: client, worker_factory=lambda _c: worker)
    run.worker = worker
    run.client = client
    return run


def _fresh(TL, day: int = 26):
    return TL.DayReport(day_key=("winter", 1, day), started_at=0.0)


def _why(event: dict) -> str:
    return str(event.get("ended_reason") or event.get("why") or "")


def case_b2() -> None:
    print("\n== B2 段：0.7.45 日终快照/判据动态重放 ==")
    try:
        TL, FW = _fixtures()
    except Exception as exc:  # pragma: no cover
        skip("B2 夹具", f"import 失败：{exc}")
        return
    world = _world(TL, weeds=1, seeds=0, money=0)
    run = _mk_run(TL, FW, world)
    obs = world.obs()
    tmap = FW.FarmWorker.tiles_of(obs)
    weed_tiles = [t for t, v in tmap.items() if v.get("kind")]
    base_iso = getattr(TL, "is_justified_end", None)
    if base_iso is None:
        skip("B2 判据入口", "tests 里没有导出 is_justified_end")
        return
    if not weed_tiles:
        skip("B2 夹具杂草", "FakeWorld 没造出杂草格")
        return
    weed = weed_tiles[0]

    # B2a 冬26 形态：账本 2 格都看不见 ⇒ exec=0, unobs=2 ⇒ 诚实收工放行
    run.leftover_targets = {(120, 120), (121, 121)}
    run.blocked = {}
    run.resume_stall_tiles = set()
    run.encircled_day = set()
    snap = run._pending_snapshot(obs)
    ok = (snap.get("ledger") == 2 and snap.get("guard") == 2 and snap.get("executable") == 0
          and snap.get("unobserved") == 2 and snap.get("malformed") == 0)
    check("B2a 冬26 形态 exec=0", ok, f"snap={snap}")
    check("B2a2 冬26 判据放行", base_iso("sleep", "resume_exhausted:x", pending_executable=0, malformed_tiles=0),
          "is_justified_end(exec=0, malformed=0) 应为 True")

    # B2b 冬27 形态：217 格全停滞 ⇒ guard=0 ⇒ 放行
    stalled = {(200 + i, 300 + i) for i in range(217)}
    run.leftover_targets = set(stalled)
    run.resume_stall_tiles = set(stalled)
    snap = run._pending_snapshot(obs)
    ok = (snap.get("ledger") == 217 and snap.get("stalled") == 217 and snap.get("guard") == 0
          and snap.get("executable") == 0 and snap.get("unobserved") == 0)
    check("B2b 冬27 形态 217 全停滞", ok, f"snap={snap}")
    check("B2b2 冬27 判据放行", base_iso("sleep", "resume_exhausted:x", pending_executable=0, malformed_tiles=0),
          "is_justified_end(exec=0) 应为 True")

    # B2c 真活：1 格看得见的杂草 ⇒ exec=1 ⇒ 不许放行
    run.leftover_targets = {weed}
    run.resume_stall_tiles = set()
    snap = run._pending_snapshot(obs)
    check("B2c 看得见真活 exec=1", snap.get("executable") == 1, f"snap={snap}")
    check("B2c2 真活不放行", not base_iso("sleep", "resume_exhausted:x", pending_executable=1, malformed_tiles=0),
          "is_justified_end(exec=1) 必须 False")

    # B2d 观测缺失 fail-closed：executable=guard（不可声称没活）
    run.leftover_targets = {(120, 120), (121, 121)}
    snap_none = run._pending_snapshot(None)
    check("B2d 观测缺失 fail-closed", snap_none.get("executable") == snap_none.get("guard") == 2,
          f"snap(None)={snap_none}")
    check("B2d2 观测缺失不放行",
          not base_iso("sleep", "resume_exhausted:x", pending_executable=None, malformed_tiles=0),
          "pending_executable=None ⇒ False（fail-closed）")

    # B2e task-22 残缺 1 格 ⇒ malformed=1，既不 unobserved 也不放行
    bad_obs = world.obs()
    bad_obs["location"].setdefault("tiles", []).append({"tile": [70, 70]})   # 只有坐标，无 kind/crop
    run.leftover_targets = {(70, 70)}
    run.resume_stall_tiles = set()
    snap = run._pending_snapshot(bad_obs)
    check("B2e 残缺 tile ⇒ malformed=1", snap.get("malformed") == 1 and snap.get("executable") == 0,
          f"snap={snap}")
    check("B2e2 malformed 一票否决",
          not base_iso("sleep", "resume_exhausted:x", pending_executable=0, malformed_tiles=1),
          "malformed_tiles=1 & exec=0 ⇒ 必须 False")
    # 反向：malformed=0 才允许放行
    check("B2e3 malformed=0 才放行",
          base_iso("sleep", "resume_exhausted:x", pending_executable=0, malformed_tiles=0),
          "对照：malformed=0 且 exec=0 ⇒ True")
    # 2 格残缺、1 格可见真活 ⇒ malformed=2, exec=1
    bad2 = world.obs()
    bad2["location"].setdefault("tiles", []).extend([{"tile": [70, 70]}, {"tile": [71, 71]}])
    run.leftover_targets = {(70, 70), (71, 71), weed}
    snap = run._pending_snapshot(bad2)
    check("B2e4 残缺+真活并列", snap.get("malformed") == 2 and snap.get("executable") == 1,
          f"snap={snap}")

    # B2f 不变式（每个快照都必须满足）
    inv_bad = []
    for name, o, lt in (("a", obs, {(120, 120), (121, 121)}), ("b", obs, set(stalled)),
                        ("c", obs, {weed}), ("d", None, {(120, 120), (121, 121)}),
                        ("e", bad_obs, {(70, 70)})):
        run.leftover_targets = set(lt)
        s = run._pending_snapshot(o)
        if s["ledger"] != s["guard"] + s["blocked"]:
            inv_bad.append((name, "ledger"))
        if s["guard"] != s["executable"] + s["unobserved"] + s["malformed"]:
            inv_bad.append((name, "guard"))
    check("B2f 快照不变式", not inv_bad, f"违反 {inv_bad}" if inv_bad else "ledger==guard+blocked 且 guard==exec+unobs+malformed")

    # B2g 进度口径：_pending_work 剔停滞/被围，_ledger_pending 保留
    t1, t2 = weed, (121, 121)
    run.leftover_targets = {t1, t2}
    run.resume_stall_tiles = {t1}
    run.encircled_day = set()
    pw = list(run._pending_work())
    lp = list(run._ledger_pending())
    check("B2g 两套待做口径", pw == [t2] or set(pw) == {t2}, f"_pending_work={pw}")
    check("B2g2 账本保留停滞", set(lp) == {t1, t2}, f"_ledger_pending={lp}")

    # B2h dead_end_pending：全停滞才返回，且不用 _pending_work
    run.resume_stall_tiles = {t1, t2}
    dp = list(run._dead_end_pending())
    check("B2h dead_end_pending 全停滞", set(dp) == {t1, t2}, f"got={dp}")
    run.resume_stall_tiles = {t1}
    check("B2h2 dead_end_pending 非全停滞", list(run._dead_end_pending()) == [],
          "部分可做 ⇒ []（不许把可做格洗成死局）")

    # B2i 换片守卫：停滞格不算"有活"
    obs2 = world.obs()
    run.encircled_day = set()
    run.resume_stall_tiles = set()
    before = run._plot_has_work(obs2, [weed])
    run.resume_stall_tiles = {weed}
    after = run._plot_has_work(obs2, [weed])
    check("B2i 停滞格不算有活", before is True and after is False, f"before={before} after={after}")

    # B2j burst 只写 resume_exhausted 前缀，绝不 stuck:
    burst = re.search(r"def _resume_exhausted\(.*?\n(?=\n    def )", read(LONG), re.S)
    body = burst.group(0) if burst else ""
    body = re.sub(r'""".*?"""', "", body, flags=re.S)      # 去掉 docstring（其中引用了 stuck: 反例）
    code_lines = [ln for ln in body.splitlines() if not ln.lstrip().startswith("#")]
    body_code = "\n".join(code_lines)
    check("B2j burst 不带 stuck:", "stuck:" not in body_code and "resume_exhausted:" in body_code,
          "函数体（去注释）无 stuck: 且理由前缀 resume_exhausted" if body else "找不到 _resume_exhausted")


def case_b3() -> None:
    print("\n== B3 段：task-16 背包口径/掉落留痕/腾格顺序 ==")
    try:
        TL, FW = _fixtures()
    except Exception as exc:  # pragma: no cover
        skip("B3 夹具", f"import 失败：{exc}")
        return
    # B3a player_free_slots 口径
    got = []
    cases = [
        ({"inventory": [], "inventoryCount": 12}, (12, "ok")),
        ({"inventory": [{}] * 12, "inventoryCount": 12}, (0, "ok")),
        ({"inventory": [{}] * 3, "inventoryCount": 12}, (9, "ok")),
        ({"inventory": []}, (0, "unavailable")),
        ({"inventory": [], "inventoryCount": 0}, (0, "unavailable")),
    ]
    bad = []
    for player, want in cases:
        try:
            got = FW.player_free_slots(player)
        except Exception as exc:
            got = f"异常 {exc}"
        if got != want:
            bad.append((player, want, got))
    check("B3a free_slots 口径", not bad, f"不符 {bad}" if bad else "5/5 例（含 unavailable 不猜 0）")

    # B3b _observe_free_slots：unavailable 不写数值
    world = _world(TL, weeds=2)
    run = _mk_run(TL, FW, world)
    obs = world.obs()
    rep = _fresh(TL)
    obs_u = world.obs()
    obs_u["player"] = {}
    got = run._observe_free_slots(rep, obs_u)
    unavail_ok = (got[0] is None and got[1] == "unavailable" and rep.free_slots_start is None
                  and rep.free_slots_status == "unavailable")
    cap_obs = world.obs()
    cap_obs["player"]["inventory"] = [{}] * 5
    cap_obs["player"]["inventoryCount"] = 12
    want_free, want_status = FW.player_free_slots(cap_obs["player"])
    rep2 = _fresh(TL)
    got2 = run._observe_free_slots(rep2, cap_obs)
    avail_ok = (got2[0] == want_free and got2[1] == want_status
                and rep2.free_slots_start == want_free
                and rep2.free_slots_last == want_free and rep2.free_slots_min == want_free)
    check("B3b 空格观测不猜 0", unavail_ok and avail_ok,
          f"unavailable={got} start={rep.free_slots_start}；ok={got2} want={want_free}")

    # B3c 满包清障：ok 不变 + loot_lost=True（不算 failed）
    w2 = _world(TL, weeds=2)
    run2 = _mk_run(TL, FW, w2)
    obs2 = w2.obs()
    tm = FW.FarmWorker.tiles_of(obs2)
    weeds = [t for t, v in tm.items() if v.get("kind")]
    if len(weeds) >= 2:
        run2.worker.player_of = lambda _o: {"inventory": [{}] * 20, "inventoryCount": 20}
        r_full = run2.worker.clear(weeds[0])
        run2.worker.player_of = lambda _o: {"inventory": [{}] * 2, "inventoryCount": 20}
        r_free = run2.worker.clear(weeds[1])
        check("B3c 满包清障留痕", bool(r_full.ok) and bool(r_full.loot_lost) and r_full.code != "failed",
              f"满包 ok={r_full.ok} loot_lost={r_full.loot_lost} code={r_full.code}")
        check("B3c2 有钱格不误报", bool(r_free.ok) and not r_free.loot_lost,
              f"空包 ok={r_free.ok} loot_lost={r_free.loot_lost}")
    else:
        skip("B3c 满包清障", f"杂草不足：{weeds}")

    # B3d _note_loot_lost 聚合（不新增事件名，只 info）
    rep3 = _fresh(TL)
    sr = FW.StepResult(action="clear", tile=(60, 10), ok=True, loot_lost=True,
                       loot_items=["Weeds"], loot_free_slots=0)
    run3 = _mk_run(TL, FW, _world(TL, weeds=1))
    try:
        run3._note_loot_lost([sr], rep3, stage="clear_area")
        ok = (rep3.loot_lost_steps == 1 and len(rep3.loot_lost_tiles) == 1
              and rep3.loot_lost_items == ["Weeds"])
    except Exception as exc:
        ok = False
        rep3.loot_lost_items = [f"异常 {exc}"]
    check("B3d loot_lost 聚合", ok,
          f"steps={rep3.loot_lost_steps} tiles={rep3.loot_lost_tiles} items={rep3.loot_lost_items}")

    # B3e 买种前先腾格：_preconditions_apply 里先 relief 后 buy
    src = read(LONG)
    m = re.search(r"def _preconditions_apply\(.*?\n(?=\n    def )", src, re.S)
    if not m:
        skip("B3e 买种前腾格顺序", "找不到 _preconditions_apply")
    else:
        seg = m.group(0)
        i_relief = seg.find("_sell_surplus_for_space(obs, rep, max_stacks=1)")
        i_buy = seg.find("self._buy_seed(")
        check("B3e 买种前腾格顺序", 0 <= i_relief < i_buy,
              f"relief@{i_relief} buy@{i_buy}")

    # B3f _slot_relief fail-closed：不够格/状态不可用一律不动手
    run4 = _mk_run(TL, FW, _world(TL, weeds=1))
    called = []
    run4.worker.sell = lambda *a, **k: called.append("sell")
    obs4 = _world(TL, weeds=1).obs()
    rep4 = _fresh(TL)
    run4._bag_state = lambda _o: (5, 0, "ok")
    r_a = run4._slot_relief(obs4, rep4)
    run4._bag_state = lambda _o: (0, 0, "unavailable")
    r_b = run4._slot_relief(obs4, rep4)
    check("B3f 腾格 fail-closed", r_a is False and r_b is False and not called,
          f"free>0 ⇒ {r_a}；unavailable ⇒ {r_b}；sell 调用 {called}")


# ---------------------------------------------------------------- C 段
HONEST_STOPPED = ("stamina", "budget", "night", "inventory_blocked", "unreachable", "refused")


def judge_snapshot(snap: dict | None):
    if not isinstance(snap, dict):
        return None
    keys = ("ledger", "guard", "stalled", "blocked", "executable", "unobserved", "malformed")
    if any(k not in snap for k in keys):
        return None
    vals = [snap[k] for k in keys]
    if any(not isinstance(v, int) or v < 0 for v in vals):
        return False
    if snap["ledger"] != snap["guard"] + snap["blocked"]:
        return False
    if snap["guard"] != snap["executable"] + snap["unobserved"] + snap["malformed"]:
        return False
    return True


def judge_day_justified(day: dict):
    checks = day.get("checks") or {}
    if "day_justified" not in checks and "pending_executable" not in day:
        return None
    dj = bool(checks.get("day_justified"))
    mal = int(day.get("pending_malformed") or 0)
    ex = day.get("pending_executable")
    if dj and (mal > 0 or (ex is not None and int(ex) > 0)):
        return False
    if mal > 0 and dj:
        return False
    if (not dj and ex is not None and int(ex) == 0 and mal == 0
            and str(day.get("ended_reason") or "").startswith("resume_exhausted")):
        return False
    return True


def judge_checks_payload(checks: dict | None):
    if not isinstance(checks, dict):
        return None
    keys = set(checks)
    if keys - set(CHECKS_BASELINE):
        return False
    if set(CHECKS_BASELINE) - keys:
        return False
    return True


def judge_old_bug_forms(day: dict):
    reason = str(day.get("ended_reason") or "")
    checks = day.get("checks") or {}
    if reason.startswith("stuck:同一秒连发"):
        return False
    ex = day.get("pending_executable")
    mal = int(day.get("pending_malformed") or 0)
    if (checks.get("day_justified") is False and ex is not None and int(ex) == 0
            and mal == 0 and reason.startswith("resume_exhausted")):
        return False
    if checks.get("verified") and ex is not None and int(ex) > 0:
        return False
    return True


def judge_loot_not_failed(day: dict):
    if "loot_lost_steps" not in day:
        return None
    lost = int(day.get("loot_lost_steps") or 0)
    failed = int(day.get("failed_steps") or 0)
    if lost > 0 and failed >= lost:
        return False
    return True


def judge_free_slots(day: dict):
    status = day.get("free_slots_status")
    if status not in ("ok", "unavailable"):
        return None
    vals = [day.get("free_slots_start"), day.get("free_slots_last"), day.get("free_slots_min")]
    if status == "unavailable":
        return not any(v == 0 for v in vals)
    return all(isinstance(v, int) for v in vals)


def judge_sell_double_diff(events: list[dict]):
    rows = [e for e in events if e.get("event") in ("sell", "slot_relief")]
    rows = [e for e in rows if e.get("strategy") == "slot_relief_space" or e.get("pressure")]
    if not rows:
        return None
    for e in rows:
        if e.get("failed"):
            continue
        rb, ra = e.get("rows_before"), e.get("rows_after")
        mb, ma = e.get("money_before"), e.get("money_after")
        if isinstance(rb, int) and isinstance(ra, int) and ra >= rb and e.get("sold"):
            return False
        if isinstance(mb, int) and isinstance(ma, int) and ma != mb:
            return False
    return True


def judge_burst_labels(day: dict, events: list[dict]):
    npb = [e for e in events if e.get("event") == "no_progress_burst"]
    if not npb:
        return None
    e = npb[-1]
    src = str(e.get("source") or "")
    checks = day.get("checks") or {}
    ex = day.get("pending_executable")
    if not e.get("exhausted"):
        return False
    if "stuck:" in str(day.get("ended_reason") or ""):
        return False
    if checks.get("verified") and ex is not None and int(ex) > 0:
        return False
    return "work_spot_resume" in src or "guard" in src or "review" in src


def judge_no_unmet_relax(day: dict):
    checks = day.get("checks") or {}
    if "no_unmet_stages" not in checks:
        return None
    if not checks.get("no_unmet_stages"):
        return True
    ex = day.get("pending_executable")
    if ex is not None and int(ex) > 0:
        return False
    und = int(day.get("assigned_undone") or 0)
    if und > 0 and day.get("ended_by") not in ("sleep",):
        return False
    return True


def judge_relief_whitelist(events: list[dict]):
    rows = [e for e in events if e.get("event") == "sell" and e.get("strategy") == "slot_relief_space"]
    if not rows:
        return None
    for e in rows:
        wl = e.get("whitelist") or e.get("sold") or []
        for item in wl:
            name = str(item).lower()
            if any(x in name for x in ("pickaxe", "axe", "hoe", "can", "sword", "工具", "seed", "种子")):
                return False
    return True


def case_c() -> None:
    print("\n== C 段：对抗通道（≥8 组，防洗白） ==")
    src = read(LONG)
    ts = read(TESTS)

    # C-a malformed 否决顺序（源码通道；去 docstring/注释，防止把反例文字当代码）
    m = re.search(r"def is_justified_end\(.*?\n(?=\ndef |\nclass )", src, re.S)
    body = m.group(0) if m else ""
    body = re.sub(r'""".*?"""', "", body, flags=re.S)
    body = "\n".join(ln for ln in body.splitlines() if not ln.lstrip().startswith("#"))
    i_mal = body.find("if int(malformed_tiles) > 0")
    i_white = body.find("if prefix in JUSTIFIED_END_REASONS")
    check("C-a malformed 一票否决在最先", 0 <= i_mal < i_white,
          f"malformed@{i_mal} 白名单@{i_white}")

    # C-b day_justified 调用必须带 malformed/pending 证据
    seg = re.search(r'"day_justified":\s*is_justified_end\((.*?)\),', src, re.S)
    call = seg.group(1) if seg else ""
    check("C-b 判据证据参数", "pending_executable=rep.pending_executable" in call
          and "malformed_tiles=rep.pending_malformed" in call,
          call.replace("\n", " ")[:150])

    # C-c checks 键集从源码重算（新字段污染必杀）
    keys = None
    try:
        for node in ast.walk(ast.parse(src)):
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                tgt = node.targets[0]
                if (isinstance(tgt, ast.Attribute) and tgt.attr == "checks"
                        and isinstance(node.value, ast.Dict)):
                    keys = tuple(k.value for k in node.value.keys
                                 if isinstance(k, ast.Constant) and isinstance(k.value, str))
                    break
    except SyntaxError:
        keys = None
    check("C-c checks 恰 10 键（源码）", keys == CHECKS_BASELINE, f"got={keys}")

    # C-d satisfied 三条作者钉死用例仍在冻结树内（防作者删用例）
    need = ("test_is_justified_end_resume_exhausted_requires_zero_executable",
            "test_earlier_round_leftover_is_not_masked_by_clean_last_round",
            "test_burst_close_is_resume_exhausted_not_stuck",
            "test_ledger_pending_keeps_stalled_guard_does_not",
            "test_full_day_resume_exhausted_with_zero_executable_is_justified_but_not_verified")
    miss = [x for x in need if x not in ts]
    check("C-d 钉死用例未删", not miss, f"缺 {miss}" if miss else "5/5 在")

    # C-e~C-l 三态判据
    good_snap = {"ledger": 2, "guard": 2, "stalled": 0, "blocked": 0,
                 "executable": 0, "unobserved": 2, "malformed": 0}
    bad_snap = dict(good_snap, ledger=3)
    neg_snap = dict(good_snap, executable=-1)
    for tag, snap, want in (
        ("C-e1 快照自洽判绿", good_snap, True),
        ("C-e2 快照 ledger 不符判红", bad_snap, False),
        ("C-e3 快照负数判红", neg_snap, False),
        ("C-e4 快照缺键【无法判定】", {"ledger": 1}, None),
    ):
        got = judge_snapshot(snap)
        check(tag, got == want, f"got={got} want={want}")

    day_good = {"checks": {"day_justified": True}, "pending_executable": 0,
                "pending_malformed": 0, "ended_reason": "resume_exhausted:x"}
    day_mal = {"checks": {"day_justified": True}, "pending_executable": 0,
               "pending_malformed": 1, "ended_reason": "resume_exhausted:x"}
    day_exec = {"checks": {"day_justified": True, "verified": True}, "pending_executable": 2,
                "pending_malformed": 0, "ended_reason": "night"}
    day_false = {"checks": {"day_justified": False}, "pending_executable": 0,
                 "pending_malformed": 0, "ended_reason": "resume_exhausted:x"}
    for tag, day, want in (
        ("C-f1 exec=0&mal=0 判绿", day_good, True),
        ("C-f2 malformed=1 判红", day_mal, False),
        ("C-f3 exec=2 判红", day_exec, False),
        ("C-f4 exec=0 却 day_justified=false 判红", day_false, False),
        ("C-f5 缺字段【无法判定】", {"checks": {}}, None),
    ):
        got = judge_day_justified(day)
        check(tag, got == want, f"got={got} want={want}")

    ok_checks = {k: True for k in CHECKS_BASELINE}
    polluted = dict(ok_checks, pending_malformed=0)
    for tag, checks, want in (
        ("C-g1 恰 10 键判绿", ok_checks, True),
        ("C-g2 新字段污染 checks 判红", polluted, False),
        ("C-g3 缺键判红", {k: ok_checks[k] for k in CHECKS_BASELINE[:9]}, False),
        ("C-g4 checks 缺失【无法判定】", None, None),
    ):
        got = judge_checks_payload(checks)
        check(tag, got == want, f"got={got} want={want}")

    old_stuck = {"ended_reason": "stuck:同一秒连发 5 次换片都没有目标", "checks": {}}
    old_false = {"ended_reason": "resume_exhausted:x", "checks": {"day_justified": False},
                 "pending_executable": 0, "pending_malformed": 0}
    verified_live = {"ended_reason": "night", "checks": {"verified": True}, "pending_executable": 1}
    for tag, day, want in (
        ("C-h1 0.7.44 stuck burst 判红", old_stuck, False),
        ("C-h2 0.7.44 false 判红", old_false, False),
        ("C-h3 有活仍 VERIFIED 判红", verified_live, False),
        ("C-h4 合法规避判绿", day_good, True),
    ):
        got = judge_old_bug_forms(day)
        check(tag, got == want, f"got={got} want={want}")

    loot_ok = {"loot_lost_steps": 2, "failed_steps": 0}
    loot_bad = {"loot_lost_steps": 2, "failed_steps": 2}
    check("C-i1 loot_lost 不算失败判绿", judge_loot_not_failed(loot_ok) is True)
    check("C-i2 loot_lost 被算失败判红", judge_loot_not_failed(loot_bad) is False)
    check("C-i3 无 loot 字段【无法判定】", judge_loot_not_failed({}) is None)

    fs_ok = {"free_slots_status": "ok", "free_slots_start": 3, "free_slots_last": 1, "free_slots_min": 1}
    fs_unavail = {"free_slots_status": "unavailable", "free_slots_start": None,
                  "free_slots_last": None, "free_slots_min": None}
    fs_guess = {"free_slots_status": "unavailable", "free_slots_start": 0,
                "free_slots_last": 0, "free_slots_min": 0}
    for tag, day, want in (
        ("C-j1 空格状态自洽判绿", fs_ok, True),
        ("C-j2 unavailable 不猜 0 判绿", fs_unavail, True),
        ("C-j3 unavailable 却写 0 判红", fs_guess, False),
        ("C-j4 状态缺失【无法判定】", {}, None),
    ):
        got = judge_free_slots(day)
        check(tag, got == want, f"got={got} want={want}")

    sell_ok = [{"event": "sell", "strategy": "slot_relief_space", "rows_before": 5,
                "rows_after": 4, "sold": [1], "failed": False}]
    sell_bad = [{"event": "sell", "strategy": "slot_relief_space", "rows_before": 5,
                 "rows_after": 5, "sold": [1], "failed": False}]
    sell_money = [{"event": "sell", "strategy": "slot_relief_space", "rows_before": 5,
                   "rows_after": 4, "money_before": 100, "money_after": 130,
                   "sold": [1], "failed": False}]
    for tag, ev, want in (
        ("C-k1 双差分成立判绿", sell_ok, True),
        ("C-k2 行数没减却自称卖掉判红", sell_bad, False),
        ("C-k3 钱变了判红（钱只能 NewDay 结算）", sell_money, False),
        ("C-k4 无卖货事件【无法判定】", [], None),
    ):
        got = judge_sell_double_diff(ev)
        check(tag, got == want, f"got={got} want={want}")

    burst_day = {"checks": {"verified": True}, "pending_executable": 0,
                 "ended_reason": "resume_exhausted:x"}
    burst_ev = [{"event": "no_progress_burst", "exhausted": True, "source": "回片区（work_spot_resume）"}]
    burst_stuck = {"checks": {}, "ended_reason": "stuck:回片区"}
    for tag, day, ev, want in (
        ("C-l1 诚实 burst 判绿", burst_day, burst_ev, True),
        ("C-l2 stuck 标签判红", burst_stuck, burst_ev, False),
        ("C-l3 无 burst【无法判定】", {}, [], None),
    ):
        got = judge_burst_labels(day, ev)
        check(tag, got == want, f"got={got} want={want}")

    relaxed = {"checks": {"no_unmet_stages": True}, "pending_executable": 2, "assigned_undone": 0}
    honest = {"checks": {"no_unmet_stages": True}, "pending_executable": 0, "ended_by": "sleep",
              "assigned_undone": 0}
    check("C-m1 有活却 no_unmet_stages 判红", judge_no_unmet_relax(relaxed) is False)
    check("C-m2 诚实停判绿", judge_no_unmet_relax(honest) is True)

    # C-n 腾格白名单：工具/种子类不许进卖单
    wl_bad = [{"event": "sell", "strategy": "slot_relief_space", "sold": ["Pickaxe", "Wheat Seeds"]}]
    wl_ok = [{"event": "sell", "strategy": "slot_relief_space", "sold": ["Sap"]}]
    check("C-n1 工具/种子进卖单判红", judge_relief_whitelist(wl_bad) is False)
    check("C-n2 普通盈余材料判绿", judge_relief_whitelist(wl_ok) is True)


# ---------------------------------------------------------------- D 段
def case_d() -> None:
    print("\n== D 段：变异证据（作者自报 vs 冻结副本实测） ==")
    for tag, names in (
        ("D1 作者变异证据", ["_t0745b_author_mut.txt", "_t0745b_author_mut"]),
        ("D2 我方变异证据", ["_t0745b_my_mut.txt", "_t0745b_my_mut"]),
    ):
        hit = None
        for n in names:
            for cand in (REPO / "scratch" / n, REPO / "scratch" / (n if n.endswith(".txt") else n + ".txt")):
                if cand.is_file():
                    hit = cand
                    break
            if hit:
                break
        if hit is None:
            skip(tag, "证据文件缺失（变异脚本输出需先落盘）")
            continue
        txt = read(hit)
        m = re.search(r"结论[：:]\s*(\d+)\s*/\s*(\d+)", txt)
        if tag.startswith("D2"):
            ok = "未杀/异常 0" in txt and "合计：11 条" in txt
            check(tag, ok,
                  f"我方变异 11 条，未杀/异常 0（{hit.name}）" if ok else f"有存活/异常或条数不符：{hit.name}")
        elif tag.startswith("D1"):
            t16 = re.search(r"结论：5/5 条变异被杀", txt) is not None
            t22 = re.search(r"结论：3/3 条变异被杀", txt) is not None
            t15_bad = "锚点出现 0 次" in txt
            check(tag, t16 and t22, f"t16 5/5={t16}、t22 3/3={t22}（{hit.name}）")
            info("D1b 作者 t15 脚本", "2/2 已达锚点被杀；m3 锚点失效（0 次）、m4 未执行 —— 脚本未随 task-22 更新" if t15_bad else "未见锚点失效")
        elif m:
            check(tag, int(m.group(1)) == int(m.group(2)),
                  f"{m.group(1)}/{m.group(2)} 被杀（{hit.name}）")
        else:
            skip(tag, f"证据无结论行：{hit.name}")


# ---------------------------------------------------------------- A4 读数
def case_readings() -> None:
    print("\n== A4 段：独立读数（py_compile / 定向 / 全量） ==")
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = str(ROOT / "brain")
    files = [str(ROOT / "brain" / "agentfarm" / "longrun.py"),
             str(ROOT / "brain" / "agentfarm" / "farmwork.py")]
    p = subprocess.run([PY, "-W", "error::SyntaxWarning", "-m", "py_compile", *files],
                       cwd=str(ROOT), env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    check("A4a py_compile", p.returncode == 0, f"rc={p.returncode} {p.stderr[:160]}")
    targets = ["tests.test_longrun.TestTask15PendingCaliber",
               "tests.test_longrun.TestTask16InventoryFull",
               "tests.test_longrun.TestTask22MalformedTiles"]
    p = subprocess.run([PY, "-m", "unittest", *targets], cwd=str(ROOT), env=env,
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = p.stdout + p.stderr
    m = re.search(r"^Ran (\d+) tests? in ", out, re.M)
    ok = bool(m) and "OK" in out and "FAILED" not in out
    check("A4b 定向单测", ok, f"Ran {m.group(1) if m else '?'} tests；{'OK' if 'OK' in out else out[-160:]}")
    p = subprocess.run([PY, "-m", "unittest", "discover", "-s", "tests"],
                       cwd=str(ROOT), env=env, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=1800)
    out = p.stdout + p.stderr
    m = re.search(r"^Ran (\d+) tests? in ", out, re.M)
    red = len(re.findall(r"^(?:FAIL|ERROR): ", out, re.M))
    check("A4c 全量单测", bool(m) and red == 0,
          f"Ran {m.group(1) if m else '?'} tests；红 {red}；rc={p.returncode}；{out[-120:] if not m else ''}")
    if red:
        info("A4c 红名单", "; ".join(sorted(set(re.findall(r"^(?:FAIL|ERROR): (\S+)", out, re.M)))[:10]))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="A,B,C,D")
    ap.add_argument("--readings", action="store_true")
    args = ap.parse_args()
    only = {x.strip().upper() for x in args.only.split(",") if x.strip()}
    print(f"被测树：{ROOT}\n冻结提交：{COMMIT}；基线：{BASELINE}")
    if "A" in only:
        case_a()
    if "B" in only:
        case_b1()
        case_b2()
        case_b3()
    if "C" in only:
        case_c()
    if "D" in only:
        case_d()
    if args.readings:
        case_readings()
    print(f"\n汇总：PASS={COUNT['PASS']} FAIL={COUNT['FAIL']} SKIP={COUNT['SKIP']} INFO={COUNT['INFO']}")
    return 1 if COUNT["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
