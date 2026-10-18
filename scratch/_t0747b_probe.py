#!/usr/bin/env python
"""task-37（0.7.47 增量验收：冻结树 a03a564）对抗验收探针 —— deputy-lead 独立实现。

范围：0.7.46 `737c4a5` → 0.7.47 `a03a564` 的**小增量**（task-35：背包升级对话购买默认关闭，
opt-in）。A 段 provenance/delta 范围；B 段默认关闭/opt-in/checks/旧账本回归；C 段 ≥6 条
对抗通道；D 段变异两列（作者自报 vs 我在冻结副本实测 + 自建变异）。

纪律：判据本人自写；只 import 冻结树 `tests/test_longrun.py` 的 FakeWorld/FakeClient/
FakeWorker/DayReport/`make_run` 当夹具。只读生产代码，不写生产代码。

用法：
  PYTHONUTF8=1 python scratch\\_t0747b_probe.py --only A,B,C[,D][,E] [--readings] [--full]
环境：
  T0747_ROOT   冻结树根（默认仓库根；正式判定必须指向 `git archive a03a564` 解出的树）
  T0747_COMMIT 冻结提交（默认 a03a564）
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
from typing import Any, Mapping

ROOT = Path(os.environ.get("T0747_ROOT") or Path(__file__).resolve().parents[1]).resolve()
REPO = Path(__file__).resolve().parents[1]
COMMIT = os.environ.get("T0747_COMMIT") or "a03a564"
PREV = "737c4a5"                     # 0.7.46 冻结（delta 基线）
PY = sys.executable

CHECKS_BASELINE = (
    "slept_by_us", "no_blocking_modal", "no_hard_failures",
    "unreachable_within_bound", "refused_within_bound", "no_unmet_stages",
    "crops_watered", "watered_outdoor", "day_justified", "zero_action_evidenced",
)
ENV_TRUTHY = ("1", "true", "yes", "on")
DLL_EXPECT_SHA = "C9B3BD6CE42BEFE87E75DD64857A5C92F5B9F317940BDC3091D42D5E039A662A"
DLL_EXPECT_SIZE = 293888
KEY_FILES = [
    "brain/agentfarm/longrun.py",
    "tools/run-longrun.py",
    "tests/test_longrun.py",
    "tests/_mutate_t35_backpack.py",
    "brain/agentfarm/bridge.py",
    "mod/AgentFarm.Bridge/manifest.json",
]
DELTA_EXPECT = {
    "brain/agentfarm/bridge.py",
    "brain/agentfarm/longrun.py",
    "mod/AgentFarm.Bridge/manifest.json",
    "tests/_mutate_t35_backpack.py",
    "tests/test_longrun.py",
    "tools/_note-0747.txt",
    "tools/run-longrun.py",
}
ALLOWED_LONGRUN_CHANGED = {
    "class:LongRun.__init__",
    "class:LongRun._backpack_skip",
    "class:LongRun._maybe_buy_backpack_upgrade",
}
ALLOWED_RUNNER_CHANGED = {
    "backpack_upgrade_enabled_from_env",
    "build_parser",
    "main",
    "import:os",
}
ALLOWED_RUNNER_ASSIGNS = {"BACKPACK_UPGRADE_ENV", "BACKPACK_ENV_TRUTHY"}

RESULTS: list[tuple[str, str, str]] = []


def check(tag: str, ok: Any, detail: str = "") -> None:
    state = "PASS" if ok else "FAIL"
    RESULTS.append((tag, state, detail))
    print(f"  {state:<4} {tag}" + (f" —— {detail}" if detail else ""))


def info(tag: str, detail: str = "") -> None:
    RESULTS.append((tag, "INFO", detail))
    print(f"  INFO {tag}" + (f" —— {detail}" if detail else ""))


def skip(tag: str, detail: str = "") -> None:
    RESULTS.append((tag, "SKIP", detail))
    print(f"  SKIP {tag}" + (f" —— {detail}" if detail else ""))


def read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8", errors="replace")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _git(args: list[str]) -> str:
    proc = subprocess.run(["git", "-C", str(REPO), *args], text=True,
                          encoding="utf-8", errors="replace", capture_output=True)
    return proc.stdout


def prev_src(rel: str) -> str:
    return _git(["show", f"{PREV}:{rel}"])


def _norm_lines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


# ------------------------------------------------------------------ AST 差集
def _body_flat(body: list[ast.stmt], prefix: str, out: dict[str, str]) -> None:
    for node in body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            out[prefix + node.name] = ast.dump(node)
        elif isinstance(node, ast.ClassDef):
            out[prefix + "class:" + node.name] = "present"
            _body_flat(node.body, prefix + "class:" + node.name + ".", out)
        elif isinstance(node, (ast.Assign, ast.AnnAssign)):
            targets: list[str] = []
            if isinstance(node, ast.Assign):
                for t in node.targets:
                    targets.extend(_target_names(t))
            else:
                targets.extend(_target_names(node.target))
            for t in targets:
                out[prefix + "assign:" + t] = ast.dump(node)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in node.names]
            for n in names:
                out[prefix + "import:" + n] = "import"
        elif isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant):
            continue                       # docstring / 空语句不算语义
        elif isinstance(node, ast.Pass):
            continue
        else:
            out[prefix + f"stmt:{type(node).__name__}"] = ast.dump(node)


def _target_names(t: ast.expr) -> list[str]:
    if isinstance(t, ast.Name):
        return [t.id]
    if isinstance(t, (ast.Tuple, ast.List)):
        out: list[str] = []
        for e in t.elts:
            out.extend(_target_names(e))
        return out
    return ["<complex>"]


def flat_ast(src: str) -> dict[str, str]:
    out: dict[str, str] = {}
    _body_flat(ast.parse(src).body, "", out)
    return out


def changed_ast_keys(old: str, new: str) -> list[str]:
    a, b = flat_ast(old), flat_ast(new)
    keys = set(a) | set(b)
    return sorted(k for k in keys if a.get(k) != b.get(k))


# ------------------------------------------------------------------ 夹具
_FIX: dict[str, Any] = {}


def fixtures() -> dict[str, Any]:
    if _FIX:
        return _FIX
    for p in (ROOT / "tests", ROOT / "brain"):
        if str(p) not in sys.path:
            sys.path.insert(0, str(p))
    import test_longrun as TL              # noqa: F401
    import agentfarm.longrun as LR        # noqa: F401
    _FIX.update(TL=TL, LR=LR)
    return _FIX


def new_pair(*, money: int = 3264, purchase_mode: str = "ok",
             talk_mode: str = "ok") -> tuple[Any, Any, Any]:
    TL = fixtures()["TL"]
    w = TL.FakeWorld(money=int(money), weeds=0)
    w.inventory_capacity = 12
    w.purchase_mode = purchase_mode
    w.talk_mode = talk_mode
    run = TL.make_run(w)
    run.client = TL.FakeClient(w)
    run.worker = TL.FakeWorker(w)
    rep = TL.DayReport(day_key=("spring", 1, 6), started_at=0.0)
    return w, run, rep


def buy_events(run: Any) -> list[dict[str, Any]]:
    return [e for e in run.entries if e.get("event") == "buy"]


# ------------------------------------------------------------------ A 段
def case_a() -> None:
    print("\n== A 段：provenance 与 delta 范围 ==")
    tracked = {}
    for line in _git(["ls-tree", "-r", COMMIT]).splitlines():
        meta, _, path = line.partition("\t")
        parts = meta.split()
        if len(parts) >= 3 and parts[1] == "blob":
            tracked[path] = parts[2]
    missing, mismatch, eol = [], [], []
    present = 0
    for rel, blob in tracked.items():
        p = ROOT / rel
        if not p.is_file():
            missing.append(rel)
            continue
        present += 1
        raw = p.read_bytes()
        norm = raw.replace(b"\r\n", b"\n")
        # 用 git cat-file 取原始字节做 \n 归一（与 git hash-object 口径一致）
        raw_git = subprocess.run(["git", "-C", str(REPO), "cat-file", "blob", blob],
                                 capture_output=True).stdout
        if raw_git.replace(b"\r\n", b"\n") != norm:
            mismatch.append(rel)
        elif raw_git != raw:
            eol.append(rel)
    check("A0 冻结树全量 blob 对照",
          not missing and not mismatch,
          f"tracked={len(tracked)} present={present} missing={len(missing)} "
          f"mismatch={len(mismatch)} eol展开={len(eol)}")
    extra = [p for p in ROOT.rglob("*") if p.is_file()
             and str(p.relative_to(ROOT)).replace("\\", "/") not in tracked]
    info("A0b 非追踪文件（夹具/缓存）", f"{len(extra)} 个（例：{[str(p.relative_to(ROOT)) for p in extra[:3]]}）")

    # A1 delta 文件清单
    numstat = _git(["diff", "--numstat", PREV, COMMIT, "--", "brain/", "tools/", "tests/", "mod/"])
    changed: dict[str, tuple[int, int]] = {}
    for line in numstat.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3:
            changed[parts[2]] = (int(parts[0] or 0) if parts[0].isdigit() else 0,
                                 int(parts[1] or 0) if parts[1].isdigit() else 0)
    extra_files = sorted(set(changed) - DELTA_EXPECT)
    missing_files = sorted(DELTA_EXPECT - set(changed))
    check("A1 delta 文件集合只含 task-35 + 版本载体",
          not extra_files and not missing_files,
          f"changed={len(changed)} extra={extra_files} missing={missing_files}")

    # A2 逐文件语义范围（AST / JSON）
    for rel, allowed in (
        ("brain/agentfarm/longrun.py", ALLOWED_LONGRUN_CHANGED),
        ("tools/run-longrun.py", ALLOWED_RUNNER_CHANGED),
    ):
        try:
            diff_keys = changed_ast_keys(prev_src(rel), read(rel))
        except SyntaxError as exc:      # pragma: no cover
            check(f"A2 {rel} AST 可解析", False, str(exc))
            continue
        bad = [k for k in diff_keys if k not in allowed and not k.startswith("assign:")]
        assigns = [k for k in diff_keys if k.startswith("assign:")]
        bad_assign = [k for k in assigns
                      if k.replace("assign:", "") not in
                      (ALLOWED_RUNNER_ASSIGNS if "run-longrun" in rel else {"MOD_VERSION_EXPECTED"})]
        ok = not bad and not bad_assign and "stmt:" not in " ".join(diff_keys)
        check(f"A2 {rel} 只改允许的符号",
              ok, f"changed={diff_keys} 非允许={bad} 非允许赋值={bad_assign}")
    # tests：只允许新增 TestTask35BackpackGate（+ task-35 对 TestTask25 的显式开启一行）
    ALLOWED_TEST_CHANGED = {"class:TestTask25BackpackUpgrade._run"}
    tkeys = changed_ast_keys(prev_src("tests/test_longrun.py"), read("tests/test_longrun.py"))
    bad_t = [k for k in tkeys if not k.startswith("class:TestTask35BackpackGate")
             and k not in ALLOWED_TEST_CHANGED]
    check("A2 tests/test_longrun.py 只新增 TestTask35BackpackGate（+task-25 显式开启）",
          not bad_t, f"changed={len(tkeys)} 非允许={bad_t[:6]}")
    # bridge：只允许 MOD_VERSION_EXPECTED 赋值变化 + 注释
    bkeys = changed_ast_keys(prev_src("brain/agentfarm/bridge.py"), read("brain/agentfarm/bridge.py"))
    bad_b = [k for k in bkeys if k not in {"assign:MOD_VERSION_EXPECTED"}]
    check("A2 bridge.py 只改版本常量/注释", not bad_b, f"changed={bkeys}")
    # manifest：除 Version 外 JSON 全同
    old_man = json.loads(prev_src("mod/AgentFarm.Bridge/manifest.json"))
    new_man = json.loads(read("mod/AgentFarm.Bridge/manifest.json"))
    diffs = [k for k in set(old_man) | set(new_man) if old_man.get(k) != new_man.get(k)]
    check("A2 manifest 只改版本载体（Version+Description；仓库口径 Description 即版本 changelog）",
          set(diffs) == {"Version", "Description"}, f"diff_keys={diffs}")

    # A3 关键文件 blob 对照
    key_bad = []
    for rel in KEY_FILES:
        want = _git(["rev-parse", f"{COMMIT}:{rel}"]).strip()
        raw = (ROOT / rel).read_bytes()
        norm = raw.replace(b"\r\n", b"\n")
        got = hashlib.sha1(f"blob {len(norm)}\0".encode() + norm).hexdigest()
        if got != want:
            key_bad.append(f"{rel}:{got[:8]}!={want[:8]}")
    check("A3 关键文件 blob 6/6", not key_bad, ";".join(key_bad) or "6/6")

    # A4 版本载体
    bridge = read("brain/agentfarm/bridge.py")
    mv = re.search(r'MOD_VERSION_EXPECTED\s*=\s*"([^"]+)"', bridge)
    man_ver = str(new_man.get("Version"))
    note = read("tools/_note-0747.txt").splitlines()[0] if (ROOT / "tools/_note-0747.txt").exists() else ""
    check("A4 版本载体一致",
          (mv.group(1) if mv else None) == "0.7.47" and man_ver == "0.7.47" and "v0.7.47" in note,
          f"bridge={mv.group(1) if mv else None} manifest={man_ver} note={note[:24]}")
    dll = REPO / "mod/AgentFarm.Bridge/bin/Release/AgentFarm.Bridge.dll"
    if dll.is_file():
        got = sha256_bytes(dll.read_bytes())
        check("A4b dll 与 0.7.46 逐字节相同",
              got.upper() == DLL_EXPECT_SHA and dll.stat().st_size == DLL_EXPECT_SIZE,
              f"{dll.stat().st_size}B {got[:16]}…")
        info("A4b2 dll 取证来源", "本地构建产物 bin/Release（git 不追踪；冻结树无 bin）——Mod 源码 diff 为空可交叉印证")
    else:
        skip("A4b dll 逐字节比对", f"本地无 {dll}")

    # A5 checks/公式/事件名/DayReport 字段
    new_src, old_src = read("brain/agentfarm/longrun.py"), prev_src("brain/agentfarm/longrun.py")

    def checks_block(src: str) -> str:
        lines = src.splitlines()
        for i, ln in enumerate(lines):
            if re.search(r"rep\.checks\s*=\s*\{", ln):
                out, depth = [ln], ln.count("{") - ln.count("}")
                for ln2 in lines[i + 1:]:
                    out.append(ln2)
                    depth += ln2.count("{") - ln2.count("}")
                    if depth <= 0:
                        break
                return "\n".join(out)
        return ""

    check("A5 checks 10 键字面与 0.7.46 逐字相同",
          checks_block(old_src) == checks_block(new_src) and checks_block(new_src) != "",
          f"len(old)={len(checks_block(old_src))} len(new)={len(checks_block(new_src))}")
    ksound = re.search(r"rep\.checks\s*=\s*\{(.*?)\n\s*\}\s*\n", new_src, re.S)
    keys = re.findall(r'"([a-z_]+)":', ksound.group(1)) if ksound else []
    check("A5b checks 键集合 = 10 基线",
          tuple(keys) == CHECKS_BASELINE, f"keys={keys}")
    _old_f = re.search(r'"no_unmet_stages":\s*(.+?),\n', old_src, re.S)
    _new_f = re.search(r'"no_unmet_stages":\s*(.+?),\n', new_src, re.S)
    check("A5c no_unmet_stages 公式逐字未动",
          _old_f is not None and _new_f is not None and _old_f.group(1) == _new_f.group(1),
          "formula identical")

    def journal_names(src: str) -> set[str]:
        return set(re.findall(r'_journal\(\s*"([a-z_]+)"', src))

    added = sorted(journal_names(new_src) - journal_names(old_src))
    removed = sorted(journal_names(old_src) - journal_names(new_src))
    check("A5d 无新 journal 事件名", not added and not removed, f"added={added} removed={removed}")

    def dayreport_fields(src: str) -> set[str]:
        tree = ast.parse(src)
        for node in tree.body:
            if isinstance(node, ast.ClassDef) and node.name == "DayReport":
                out = set()
                for sub in node.body:
                    if isinstance(sub, ast.AnnAssign) and isinstance(sub.target, ast.Name):
                        out.add(sub.target.id)
                return out
        return set()

    f_added = sorted(dayreport_fields(new_src) - dayreport_fields(old_src))
    f_removed = sorted(dayreport_fields(old_src) - dayreport_fields(new_src))
    check("A5e DayReport 字段 0 增删", not f_added and not f_removed,
          f"added={f_added} removed={f_removed}")

    # A6 默认关闭源码形态
    tree = ast.parse(new_src)
    default_val: Any = "<absent>"
    found_kwonly = False
    for node in tree.body:
        if isinstance(node, ast.ClassDef) and node.name == "LongRun":
            for sub in node.body:
                if isinstance(sub, ast.FunctionDef) and sub.name == "__init__":
                    for arg, dflt in zip(sub.args.kwonlyargs, sub.args.kw_defaults):
                        if arg.arg == "backpack_upgrade_enabled":
                            found_kwonly = True
                            if isinstance(dflt, ast.Constant):
                                default_val = dflt.value
    check("A6 构造器默认 backpack_upgrade_enabled=False",
          found_kwonly and default_val is False,
          f"kwonly={found_kwonly} default={default_val!r}")
    runner = read("tools/run-longrun.py")
    check("A6b env 真值表只认 1/true/yes/on",
          'BACKPACK_ENV_TRUTHY = ("1", "true", "yes", "on")' in runner
          and "in BACKPACK_ENV_TRUTHY" in runner,
          "literal + membership")
    body = _func_body(new_src, "_maybe_buy_backpack_upgrade")
    i_dis = body.find("if not self.backpack_upgrade_enabled:")
    i_goto = body.find("ensure_location(")
    i_talk = body.find("_backpack_talk_once(")
    check("A6c 关闭分支在 goto/talk 之前", 0 <= i_dis < i_goto and 0 <= i_dis < i_talk,
          f"disabled@{i_dis} goto@{i_goto} talk@{i_talk}")


def _func_body(src: str, name: str) -> str:
    lines = src.splitlines()
    start = None
    indent = 0
    for i, ln in enumerate(lines):
        m = re.match(r"(\s*)def " + re.escape(name) + r"\(", ln)
        if m:
            start, indent = i, len(m.group(1))
            break
    if start is None:
        return ""
    out = [lines[start]]
    for ln in lines[start + 1:]:
        if ln.strip() and (len(ln) - len(ln.lstrip())) <= indent and not ln.lstrip().startswith("#"):
            if len(ln) - len(ln.lstrip()) <= indent:
                break
        out.append(ln)
    return "\n".join(out)


# ------------------------------------------------------------------ B 段
def case_b() -> None:
    print("\n== B 段：默认关闭 / opt-in / checks / 旧账本回归 ==")
    TL = fixtures()["TL"]
    # B1 默认关闭：零请求 + skip 留痕
    w, run, rep = new_pair()
    called: list[str] = []
    run.client.talk = lambda *a, **k: called.append("talk") or (_ for _ in ()).throw(RuntimeError("默认关闭不许 talk"))
    w.talk_calls.clear()
    ret = run._maybe_buy_backpack_upgrade(w.obs(), rep)
    ev = buy_events(run)
    check("B1 默认关闭零请求 + status=skipped/code=disabled",
          ret is False and not w.talk_calls and not called
          and len(ev) == 1 and ev[0].get("status") == "skipped"
          and ev[0].get("code") == "disabled",
          f"ret={ret} talk={len(w.talk_calls)} buy={[(e.get('status'), e.get('code')) for e in ev]}")
    check("B1b day_end 只读 skip=disabled 且不加 notes",
          rep.backpack_upgrade_skip == "disabled"
          and not any("背包升级" in str(n) for n in rep.notes)
          and run.backpack_attempts_today == 0,
          f"skip={rep.backpack_upgrade_skip!r} notes={rep.notes[:2]} attempts={run.backpack_attempts_today}")
    run._maybe_buy_backpack_upgrade(w.obs(), rep)
    check("B1c 每天最多 1 条 skipped 留痕", len([e for e in run.entries if e.get("event") == "buy"]) == 1,
          f"buy={len([e for e in run.entries if e.get('event') == 'buy'])}")

    # B2 显式开启：与 0.7.46 行为一致（双差分）
    w, run, rep = new_pair()
    run.backpack_upgrade_enabled = True
    ret = run._maybe_buy_backpack_upgrade(w.obs(), rep)
    ev = buy_events(run)
    check("B2 开启后成功（钱−2000 且容量 12→24）",
          ret is True and w.money == 1264 and w.inventory_capacity == 24
          and rep.backpack_upgrade_ok is True
          and any(e.get("status") == "ok" and e.get("source") == "backpack_dialogue" for e in ev),
          f"ret={ret} money={w.money} cap={w.inventory_capacity} ok={rep.backpack_upgrade_ok}")

    # B2b 失败面：钱没少 / 容量没变 / 跨日窗口歧义
    for mode, want_code in (("money_unchanged", "money_not_deducted"),
                            ("capacity_unchanged", "capacity_not_changed"),
                            ("dismiss_new_day", "money_diff_ambiguous")):
        w, run, rep = new_pair(purchase_mode=mode)
        run.backpack_upgrade_enabled = True
        money0, cap0 = w.money, w.inventory_capacity
        ret = run._maybe_buy_backpack_upgrade(w.obs(), rep)
        ev = buy_events(run)
        codes = [e.get("code") for e in ev if e.get("status") != "skipped"]
        check(f"B2b {mode} ⇒ {want_code}（不得认成功）",
              ret is False and rep.backpack_upgrade_ok is False and want_code in codes,
              f"ret={ret} money={money0}->{w.money} cap={cap0}->{w.inventory_capacity} codes={codes}")

    # B2c gate 频控：已是 24 格 / 钱不够 / 无 talk
    for cap, money, want in ((24, 3264, "already_upgraded"), (12, 100, "cannot_afford")):
        w, run, rep = new_pair(money=money)
        w.inventory_capacity = cap
        run.backpack_upgrade_enabled = True
        ret = run._maybe_buy_backpack_upgrade(w.obs(), rep)
        check(f"B2c gate 跳过 {want}",
              ret is False and rep.backpack_upgrade_skip == want and not w.talk_calls,
              f"skip={rep.backpack_upgrade_skip!r} talk={len(w.talk_calls)}")
    w, run, rep = new_pair()
    run.backpack_upgrade_enabled = True
    run.client.talk = None
    ret = run._maybe_buy_backpack_upgrade(w.obs(), rep)
    check("B2c2 gate 跳过 talk_unavailable",
          ret is False and rep.backpack_upgrade_skip == "talk_unavailable",
          f"skip={rep.backpack_upgrade_skip!r}")
    # B2d 同一天失败后不再重试（≤2 次 talk/天）
    w, run, rep = new_pair(purchase_mode="money_unchanged")
    run.backpack_upgrade_enabled = True
    run._maybe_buy_backpack_upgrade(w.obs(), rep)
    n1 = len(w.talk_calls)
    run._maybe_buy_backpack_upgrade(w.obs(), rep)
    check("B2d 同一天失败后不再重试", len(w.talk_calls) == n1 and n1 <= 2,
          f"talk={n1}->{len(w.talk_calls)}")

    # B3 checks / 判据公式未变（动态抽 5 例）
    LR = fixtures()["LR"]
    cases = [
        (("sleep", "night"), True), (("stuck", "stuck:回片区"), False),
        (("inventory_blocked", "inventory_blocked:背包满"),
         True),
    ]
    dyn_ok = True
    for (ended, reason), want in cases:
        got = LR.is_justified_end(ended, reason, pending_executable=0, malformed_tiles=0)
        dyn_ok = dyn_ok and (got == want)
    got_mal = LR.is_justified_end("sleep", "night", pending_executable=0, malformed_tiles=1)
    got_exec = LR.is_justified_end("inventory_blocked", "inventory_blocked:背包满",
                                   pending_executable=3, malformed_tiles=0)
    check("B3 is_justified_end 边界未变（含 malformed 否决）",
          dyn_ok and got_mal is False and got_exec is False,
          f"malformed_veto={got_mal} exec_veto={got_exec}")

    # B4 旧账本回归（smoke-0745 + A8）：我自己的重放基线 rc0 / FAIL=0
    out = ROOT / "scratch" / "_t0747_old_ledger.txt"
    proc = subprocess.run([PY, "scratch/_t0746_prep_replay.py", "--out", str(out)],
                          cwd=str(REPO), text=True, encoding="utf-8", errors="replace",
                          capture_output=True, env={**os.environ, "PYTHONUTF8": "1"})
    txt = proc.stdout or ""
    m = re.search(r"汇总：FAIL=(\d+)", txt)
    check("B4 旧账本回归（smoke-0745/A8）rc0 且 FAIL=0",
          proc.returncode == 0 and m is not None and m.group(1) == "0",
          f"rc={proc.returncode} {m.group(0) if m else 'no summary'}")


# ------------------------------------------------------------------ C 段：对抗通道
def judge_disabled(talk_calls: int, attempts: int, events: list[dict[str, Any]]) -> str:
    if talk_calls or attempts:
        return "red"
    if not events:
        return "none"
    if all(e.get("status") == "skipped" and e.get("code") == "disabled" for e in events):
        return "green"
    return "red"


def judge_enabled_outcome(code: str, money_delta: int, cap_delta: int) -> str:
    if code == "ok":
        return "green" if (money_delta == -2000 and cap_delta == 12) else "red"
    return "red" if (money_delta != 0 or cap_delta != 0) else "green"


def judge_env(raw: str) -> bool:
    return str(raw).strip().lower() in ENV_TRUTHY


def judge_success_count(events: list[dict[str, Any]]) -> int:
    return sum(1 for e in events if e.get("status") == "ok" and e.get("ok") is True)


def judge_version(bridge: str, manifest: str) -> str:
    return "green" if bridge == manifest == "0.7.47" else "red"


def case_c() -> None:
    print("\n== C 段：对抗通道（≥6） ==")
    # 自检：判据自身先验三态
    st = [
        ("C0a judge_disabled green", judge_disabled(0, 0, [{"status": "skipped", "code": "disabled"}]) == "green"),
        ("C0b judge_disabled red(talk)", judge_disabled(1, 0, [{"status": "skipped", "code": "disabled"}]) == "red"),
        ("C0c judge_enabled green", judge_enabled_outcome("ok", -2000, 12) == "green"),
        ("C0d judge_enabled red(缺差分)", judge_enabled_outcome("ok", 0, 0) == "red"),
        ("C0e judge_env 真值", judge_env(" On ") and judge_env("TRUE") and not judge_env("0")
         and not judge_env("y")),
        ("C0f judge_success 忽略 skipped", judge_success_count(
            [{"status": "skipped", "code": "disabled", "ok": False}]) == 0),
        ("C0g judge_version 不一致红", judge_version("0.7.47", "0.7.46") == "red"),
    ]
    for tag, ok in st:
        check("C 自检 " + tag, ok)

    # C1 默认值改回 True 必抓：源码 + 动态双证
    TL = fixtures()["TL"]
    w, run, _ = new_pair()
    dyn_default = getattr(run, "backpack_upgrade_enabled", None)
    src = read("brain/agentfarm/longrun.py")
    dflt = re.search(r"backpack_upgrade_enabled: bool = (True|False)", src)
    check("C1 默认关闭（源码+动态）",
          dflt is not None and dflt.group(1) == "False" and dyn_default is False
          and judge_disabled(0, 0, [{"status": "skipped", "code": "disabled"}]) == "green",
          f"src={dflt.group(1) if dflt else None} run={dyn_default}")

    # C2 关闭分支被删必抓：源码顺序 + 动态 raise 证明零调用
    w, run, rep = new_pair()
    run.client.talk = lambda *a, **k: (_ for _ in ()).throw(AssertionError("默认关闭不许 talk"))
    ret = run._maybe_buy_backpack_upgrade(w.obs(), rep)
    ev = buy_events(run)
    check("C2 关闭分支存在且真实零调用",
          ret is False and judge_disabled(len(w.talk_calls), run.backpack_attempts_today, ev) == "green",
          f"ret={ret} talk={len(w.talk_calls)} attempts={run.backpack_attempts_today}")

    # C3 开启后丢双差分必抓（失败必须 False 且账本不得出现成功购买）
    bad = []
    for mode, code in (("money_unchanged", "money_not_deducted"),
                       ("capacity_unchanged", "capacity_not_changed")):
        w, run, rep = new_pair(purchase_mode=mode)
        run.backpack_upgrade_enabled = True
        m0, c0 = w.money, w.inventory_capacity
        ret = run._maybe_buy_backpack_upgrade(w.obs(), rep)
        won = judge_success_count(buy_events(run))
        if ret is not False or won != 0:
            bad.append((mode, ret, won, w.money - m0, w.inventory_capacity - c0))
    check("C3 开启后双差分缺口必抓", not bad, f"bad={bad}")

    # C4 skipped 冒领购买必抓
    fake = [{"event": "buy", "status": "skipped", "code": "disabled", "ok": False},
            {"event": "buy", "status": "ok", "ok": True}]
    check("C4 skipped 不计真实购买", judge_success_count(fake) == 1,
          f"count={judge_success_count(fake)}")

    # C5 env 解析放宽必抓：源码字面 + 运行时真值表（含独立重实现对照）
    runner_src = read("tools/run-longrun.py")
    import importlib.util
    mod_path = ROOT / "tools" / "run-longrun.py"
    spec = importlib.util.spec_from_file_location("_t47_runner", mod_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)          # type: ignore[union-attr]
    truth = ["1", "true", "TRUE", "yes", "on", " On "]
    falsy = ["", "0", "false", "no", "off", "2", "y", "tru", "truee"]
    mism = []
    for v in truth:
        if mod.backpack_upgrade_enabled_from_env({"AGENTFARM_ENABLE_BACKPACK_UPGRADE": v}) is not True:
            mism.append(v)
    for v in falsy:
        if mod.backpack_upgrade_enabled_from_env({"AGENTFARM_ENABLE_BACKPACK_UPGRADE": v}) is not False:
            mism.append(v)
    check("C5 env 真值表与独立判据一致", not mism and judge_env("y") is False,
          f"mismatch={mism}")

    # C6 版本不一致必抓
    m_ver = re.search(r'"Version"\s*:\s*"([^"]+)"', read("mod/AgentFarm.Bridge/manifest.json"))
    b_ver = re.search(r'MOD_VERSION_EXPECTED\s*=\s*"([^"]+)"', read("brain/agentfarm/bridge.py"))
    check("C6 bridge/manifest 版本一致且=0.7.47",
          b_ver is not None and m_ver is not None and "green" == judge_version(b_ver.group(1), m_ver.group(1)),
          f"bridge={b_ver.group(1) if b_ver else None} manifest={m_ver.group(1) if m_ver else None}")

    # C7 新字段污染 checks 必抓（只查字面键名；day_justified 调 is_justified_end 传参不算污染）
    cb = re.search(r"rep\.checks\s*=\s*\{(.*?)\n\s*\}\s*\n", src, re.S)
    check_keys = re.findall(r'"([a-z_]+)":', cb.group(1)) if cb else []
    poll = [k for k in check_keys
            if k.startswith(("backpack_", "loot_lost", "relief_exhausted",
                             "bag_evidence", "pending_"))]
    check("C7 checks 未被 task-35 字段污染", not poll and bool(check_keys), f"polluted={poll}")

    # C8 dll 与冻结产物一致（本地构建产物）
    dll = REPO / "mod/AgentFarm.Bridge/bin/Release/AgentFarm.Bridge.dll"
    if dll.is_file():
        got = sha256_bytes(dll.read_bytes())
        check("C8 dll 哈希与冻结产物一致", got.upper() == DLL_EXPECT_SHA and dll.stat().st_size == DLL_EXPECT_SIZE,
              f"{dll.stat().st_size}B {got[:12]}…")
    else:
        skip("C8 dll 哈希", "本地无 bin/Release dll")


# ------------------------------------------------------------------ D/E 段
def _evidence(name: str) -> str:
    p = REPO / "scratch" / name
    return p.read_text(encoding="utf-8", errors="replace") if p.is_file() else ""


def case_d() -> None:
    print("\n== D 段：变异两列（证据文件） ==")
    txt = _evidence("_t0747b_author_mut.txt")
    if not txt:
        skip("D1 作者变异两列", "缺 scratch/_t0747b_author_mut.txt（先跑作者脚本）")
    else:
        m = re.search(r"结论：(\d+)/(\d+) 条变异被杀", txt)
        check("D1 作者 task-35 变异实测 3/3 被杀",
              m is not None and m.group(1) == "3" and m.group(2) == "3",
              m.group(0) if m else "未解析到结论")
    txt2 = _evidence("_t0747b_my_mut.txt")
    if not txt2:
        skip("D2 我方变异两列", "缺 scratch/_t0747b_my_mut.txt（先跑我方变异）")
    else:
        m = re.search(r"合计：(\d+)/(\d+) 条变异被杀；未杀 (\d+)", txt2)
        check("D2 我方自建变异全部被杀",
              m is not None and m.group(1) == m.group(2) and m.group(3) == "0",
              m.group(0) if m else "未解析到结论")


def case_e(run_readings: bool, full: bool) -> None:
    print("\n== E 段：读数 ==")
    if not run_readings:
        skip("E 读数", "未加 --readings")
        return
    env = {**os.environ, "PYTHONUTF8": "1", "PYTHONPATH": str(ROOT / "brain")}
    files = ["brain/agentfarm/longrun.py", "brain/agentfarm/bridge.py", "tools/run-longrun.py"]
    proc = subprocess.run([PY, "-W", "error::SyntaxWarning", "-m", "py_compile", *files],
                          cwd=str(ROOT), env=env, text=True, capture_output=True)
    check("E1 py_compile -W error::SyntaxWarning rc=0", proc.returncode == 0,
          proc.stderr.strip()[:160])
    targets = ["tests.test_longrun.TestTask35BackpackGate", "tests.test_longrun.TestTask25BackpackUpgrade"]
    proc = subprocess.run([PY, "-m", "unittest", *targets, "-v"], cwd=str(ROOT), env=env,
                          text=True, encoding="utf-8", errors="replace", capture_output=True)
    out = (proc.stdout or "") + (proc.stderr or "")
    m = re.search(r"^Ran (\d+) tests? in ", out, re.M)
    check("E2 定向单测 Ran N / OK", bool(m) and re.search(r"^OK", out, re.M) and proc.returncode == 0,
          m.group(0) if m else f"rc={proc.returncode}")
    if full:
        proc = subprocess.run([PY, "-m", "unittest", "discover", "-s", "tests"], cwd=str(ROOT),
                              env=env, text=True, encoding="utf-8", errors="replace", capture_output=True)
        out = (proc.stdout or "") + (proc.stderr or "")
        m = re.search(r"^Ran (\d+) tests? in ", out, re.M)
        ok = bool(m) and re.search(r"^OK", out, re.M) and proc.returncode == 0
        check("E3 冻结树全量单测 Ran N / OK", ok, m.group(0) if m else f"rc={proc.returncode}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="A,B,C,D,E")
    ap.add_argument("--readings", action="store_true")
    ap.add_argument("--full", action="store_true")
    args = ap.parse_args()
    only = {s.strip().upper() for s in args.only.split(",") if s.strip()}
    print(f"frozen ROOT={ROOT}\ncommit={COMMIT} prev={PREV} repo={REPO}")
    if "A" in only:
        case_a()
    if "B" in only:
        case_b()
    if "C" in only:
        case_c()
    if "D" in only:
        case_d()
    if "E" in only:
        case_e(args.readings, args.full)
    p = sum(1 for _, s, _ in RESULTS if s == "PASS")
    f = sum(1 for _, s, _ in RESULTS if s == "FAIL")
    sk = sum(1 for _, s, _ in RESULTS if s == "SKIP")
    i = sum(1 for _, s, _ in RESULTS if s == "INFO")
    print(f"\n== 汇总：PASS={p} FAIL={f} SKIP={sk} INFO={i} ==")
    return 1 if f else 0


if __name__ == "__main__":
    raise SystemExit(main())
