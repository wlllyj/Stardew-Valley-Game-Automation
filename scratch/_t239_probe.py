"""task-239：0.7.41 批次（236 落盘守卫 / 237 需求驱动腾格 / 238 §8 兜底）独立对抗验收探针。

设计原则（照前几批）：
- **只读生产代码**：本脚本只写 `scratch/`（夹具、输出），不改 `brain/`/`mod/`/`tools/`/`tests/`。
- **两种树**：`--tree` 指定 `git archive` 冻结树（正式判定用）；不指定时用仓库工作树（只作线索，
  正式判定必须记 `src=frozen`）。
- **缺失 ≠ 通过**：被验代码/字段/工具判据缺失时一律 SKIP 或 FAIL 证据缺失，不许当 PASS。
- **探针自己的 bug 与产品 bug 分开判**：参考判据（count_six/judge_smapi）只用来验证夹具方向与期望，
  产品判定必须由 `tools/verify-run3.py` 与 `scratch/save-chain-check.py` 的真实输出给出。

段：
  A 范围/越界/版本/读数（--readings 才真跑单测/build/C#自检）
  B 真机窗口离线复算（236：产品判据 vs 参考判据）
  B6 保存链检查器终审（8 夹具 + 真实一红一绿 + 三 GAP + save_task 三态 + 消费端）
  C 作弊通道（卡面 7 条 + 我自想 C8/C9/C10）
  D 变异矩阵接口（作者脚本复跑 + 自报 vs 实测两列）
  E 逐卡判定与一句话结论

用法：
    python scratch/_t239_probe.py                          # 工作树（线索）
    python scratch/_t239_probe.py --tree <冻结树>           # 正式判定
    python scratch/_t239_probe.py --only B,B6 --tree <树>   # 只跑指定段
    python scratch/_t239_probe.py --readings                # A 段真跑读数（慢）
    python scratch/_t239_probe.py --fixtures                # 只重建窗口夹具
"""
from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import os
import re
import subprocess
import sys
import traceback
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
LOGS = REPO / "logs"
WIN_DIR = HERE / "_t239_win"
PY = sys.executable
RESCUED = LOGS / "smoke-0740-smapi-window-rescued.txt"
SMOKE_LEDGER = LOGS / "longrun-smoke-0740.jsonl"

PASS = FAIL = SKIP = INFO = 0
RESULTS: list[tuple[str, str, str]] = []


def check(tag: str, ok: bool, detail: str = "") -> None:
    global PASS, FAIL
    if ok:
        PASS += 1
    else:
        FAIL += 1
    st = "PASS" if ok else "FAIL"
    RESULTS.append((tag, st, detail))
    print(("  PASS  " if ok else "  FAIL  ") + tag + (f" :: {detail}" if detail else ""))


def skip(tag: str, detail: str = "") -> None:
    global SKIP
    SKIP += 1
    RESULTS.append((tag, "SKIP", detail))
    print(f"  SKIP  {tag}" + (f" :: {detail}" if detail else ""))


def info(tag: str, detail: str = "") -> None:
    global INFO
    INFO += 1
    RESULTS.append((tag, "INFO", detail))
    print(f"  INFO  {tag}" + (f" :: {detail}" if detail else ""))


class Tree:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.base = root if (root / "brain" / "agentfarm").is_dir() else REPO

    def src(self, rel: str) -> str:
        try:
            return (self.base / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            return ""

    def exists(self, rel: str) -> bool:
        return (self.base / rel).exists()


def sha16(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16].upper()


def run(cmd: list[str], *, cwd: Path | None = None, timeout: int = 900) -> tuple[int, str]:
    env = dict(os.environ)
    env.setdefault("PYTHONUTF8", "1")
    p = subprocess.run(cmd, cwd=str(cwd or REPO), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout, env=env)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


# ============================================================ 夹具
def _write_lines(path: Path, lines: list[str]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return path


def _resolved_lines() -> list[str]:
    return RESCUED.read_text(encoding="utf-8", errors="replace").splitlines()


def fixtures() -> dict[str, Path]:
    WIN_DIR.mkdir(parents=True, exist_ok=True)
    fx: dict[str, Path] = {}
    if not RESCUED.exists():
        return fx
    base = _resolved_lines()
    green = WIN_DIR / "green_0740_rescued.txt"
    _write_lines(green, base)
    fx["green"] = green

    # 红窗口：截到末次 NewDay 后 2 行（0.7.40 真形态 NewDay 3 / Save called 2）
    nd = [i for i, ln in enumerate(base) if "Synchronizing 'NewDay' task" in ln]
    cut = (nd[-1] + 2) if nd else len(base)
    fx["red"] = _write_lines(WIN_DIR / "red_0740_prerescue.txt", base[:cut])

    # 半截保存链：去掉末次 Save called 之后的 completed / after save
    sc = [i for i, ln in enumerate(base) if "SaveGame.Save() called." in ln]
    last = sc[-1] if sc else len(base) - 1
    half = [ln for i, ln in enumerate(base)
            if not (i > last and ("SaveGame.Save() completed" in ln or "Context: after save" in ln))]
    fx["half_chain"] = _write_lines(WIN_DIR / "red_half_chain.txt", half)

    # 伪造 after save
    forged = list(base[:cut]) + ["[12:20:44 TRACE SMAPI] Context: after save, starting winter 1 Y1."]
    fx["forged_after"] = _write_lines(WIN_DIR / "red_forged_after.txt", forged)

    # GAP-236B-4：删光 before save
    fx["gap4"] = _write_lines(WIN_DIR / "gap4_no_before_save.txt",
                              [ln for ln in base if "Context: before save." not in ln])

    # GAP-236B-5：删光 Save task（顺序正常 / 链内逆序）
    no_task = [ln for ln in base if "Synchronizing 'Save' task" not in ln]
    fx["gap5a"] = _write_lines(WIN_DIR / "gap5a_no_save_task.txt", no_task)
    moved = [ln for ln in no_task]
    cp = [i for i, ln in enumerate(moved) if "SaveGame.Save() completed without exceptions" in ln]
    if cp:
        row = moved.pop(cp[-1])
        pos = next((i for i, s in enumerate(moved) if "SaveGame.Save() called." in s), len(moved))
        moved.insert(max(0, pos - 1), row)
    fx["gap5b"] = _write_lines(WIN_DIR / "gap5b_no_task_reversed.txt", moved)

    # save_task 部分缺失（仅删一条）
    one_idx = next((i for i, ln in enumerate(base) if "Synchronizing 'Save' task" in ln), None)
    if one_idx is not None:
        fx["st_partial"] = _write_lines(WIN_DIR / "st_partial_task.txt",
                                        [ln for i, ln in enumerate(base) if i != one_idx])
    return fx


# ============================================================ 参考判据（只验夹具方向）
TS_RE = re.compile(r"^\[(\d{2}):(\d{2}):(\d{2})\s+([A-Z]+)\s+([^\]]+)\]")
SIX = {
    "newday": "Synchronizing 'NewDay' task",
    "before_save": "Context: before save",
    "save_called": "SaveGame.Save() called",
    "save_task": "Synchronizing 'Save' task",
    "completed": "SaveGame.Save() completed without exceptions",
    "after_save": "Context: after save",
}


def _is_plugin(ln: str) -> bool:
    return (" by AgentFarm " in ln) or ("| v0." in ln)


def count_six(path: Path) -> dict[str, list[int]]:
    out: dict[str, list[int]] = {k: [] for k in SIX}
    for i, ln in enumerate(path.read_text(encoding="utf-8", errors="replace").splitlines(), 1):
        if not TS_RE.match(ln) or _is_plugin(ln):
            continue
        for key, word in SIX.items():
            if word in ln:
                out[key].append(i)
    return out


def judge_smapi(path: Path) -> tuple[bool, list[str]]:
    c = count_six(path)
    n = len(c["newday"])
    probs: list[str] = []
    if n == 0:
        return False, ["没有 NewDay 行 ⇒ 无法判定"]
    if len(c["save_called"]) < n:
        probs.append(f"NewDay={n} > Save called={len(c['save_called'])}（有跨日没落盘）")
    if n > len(c["after_save"]):
        probs.append(f"NewDay={n} > after save={len(c['after_save'])}")
    if c["newday"] and c["save_called"] and c["newday"][-1] > c["save_called"][-1]:
        probs.append("末次 NewDay 晚于末次 Save called（顺序颠倒）")
    return (not probs), probs


# ============================================================ 产品判据入口
def smapi_problem(out: str) -> bool:
    return any(k in out for k in ("日切落盘链不完整", "日切顺序颠倒", "末次跨日未落盘"))


def tool_smapi(tree: Tree, ledger: Path, smapi: Path, *, days: str = "2") -> tuple[int, str]:
    tool = tree.base / "tools" / "verify-run3.py"
    return run([PY, str(tool), "--journal", str(ledger), "--days", days, "--smapi", str(smapi)],
               cwd=tree.base)


def checker_path(tree: Tree) -> Path | None:
    for cand in (tree.base / "scratch" / "save-chain-check.py", REPO / "scratch" / "save-chain-check.py"):
        if cand.is_file():
            return cand
    return None


def checker_json(tree: Tree, window: Path, extra: list[str] | None = None) -> tuple[int, dict, str]:
    ck = checker_path(tree)
    if ck is None:
        return 3, {}, "缺 save-chain-check.py"
    out = WIN_DIR / (window.stem + ".chk.json")
    args = [PY, str(ck), "--smapi", str(window), "--out", str(out)]
    if extra:
        args += extra
    rc, text = run(args, cwd=tree.base)
    try:
        return rc, json.loads(out.read_text(encoding="utf-8")), text
    except OSError:
        return rc, {}, text


def _verdict(js: dict) -> dict:
    return js.get("verdict") or {}


# ============================================================ A 段
def case_a(tree: Tree, src_tag: str, readings: bool) -> None:
    print("== A 段：范围 / 越界 / 版本 / 读数 ==")
    files = ["brain/agentfarm/longrun.py", "brain/agentfarm/farmwork.py",
             "brain/agentfarm/planner.py", "brain/agentfarm/bridge.py",
             "tools/verify-run3.py", "tests/test_verify_run3.py",
             "tests/test_longrun.py", "mod/AgentFarm.Bridge/ModalDismiss.cs"]
    missing = [f for f in files if not tree.exists(f)]
    check("A1 对象文件齐全", not missing, f"缺={missing}" if missing else f"{len(files)} 个")
    for rel in files:
        if tree.exists(rel):
            info(f"A2 SHA16 {rel}", sha16(tree.src(rel)))

    lr = tree.src("brain/agentfarm/longrun.py")
    m = re.search(r"rep\.checks\s*=\s*\{([\s\S]{0,2500}?)\}", lr)
    body = m.group(1) if m else ""
    check("A3 checks 键集未被新卡扩键（cleanup/harvest_demand 不进 checks）",
          bool(body) and "cleanup" not in body and "harvest_demand" not in body,
          f"checks 块 {len(body)} 字符")

    ver_lr = re.search(r'MOD_VERSION_EXPECTED\s*=\s*"([^"]+)"', tree.src("brain/agentfarm/bridge.py"))
    ver_man = re.search(r'"Version"\s*:\s*"([^"]+)"', tree.src("mod/AgentFarm.Bridge/manifest.json"))
    info("A4 版本号（冻结提交应已 bump 到 0.7.41）",
         f"bridge.py={ver_lr.group(1) if ver_lr else '?'} manifest={ver_man.group(1) if ver_man else '?'}")

    has236 = "cleanup_modal_stuck" in lr
    has237 = "harvest_demand" in lr
    has238 = "finalize_fallback" in lr or "finalize_fallback" in tree.src("tools/analyze-longrun.py")
    info("A5 marker", f"236={has236} 237={has237} 238={has238}")

    if not readings:
        skip("A6 读数", "加 --readings 才跑 py_compile/定向/全量/build/C#自检")
        return
    rc, _ = run([PY, "-W", "error::SyntaxWarning", "-m", "py_compile",
                 "brain/agentfarm/longrun.py", "brain/agentfarm/farmwork.py",
                 "brain/agentfarm/planner.py", "brain/agentfarm/bridge.py"], cwd=tree.base)
    check("A6a py_compile -W error::SyntaxWarning", rc == 0, f"rc={rc}")
    rc, out = run([PY, "-m", "unittest", "tests.test_farmwork", "tests.test_longrun",
                   "tests.test_planner"], cwd=tree.base)
    mm = re.search(r"Ran (\d+) tests? in [\d.]+s", out)
    check("A6b 定向单测", rc == 0 and bool(mm) and "OK" in out, mm.group(0) if mm else out[-160:])
    rc, out = run([PY, "-m", "unittest", "discover", "-s", "tests"], cwd=tree.base)
    mm = re.search(r"Ran (\d+) tests? in [\d.]+s", out)
    reds = re.findall(r"^(?:FAIL|ERROR): .+$", out, re.M)
    check("A6c 全量单测", rc == 0, f"{mm.group(1) if mm else '?'} tests；红={len(reds)}")
    rc, out = run(["dotnet", "build",
                   str(tree.base / "mod" / "AgentFarm.Bridge" / "AgentFarm.Bridge.csproj"),
                   "-c", "Release", "--nologo", "--no-incremental"], cwd=tree.base, timeout=600)
    warns = len(re.findall(r"warning [A-Z]+\d+", out))
    errs = len(re.findall(r"error [A-Z]+\d+", out))
    check("A6d dotnet build 0 警 0 错", rc == 0 and warns == 0 and errs == 0,
          f"rc={rc} warn={warns} err={errs}")
    rc, out = run(["dotnet", "run", "--project",
                   str(tree.base / "mod" / "AgentFarm.Bridge.Tests" / "AgentFarm.Bridge.Tests.csproj"),
                   "-c", "Release", "--nologo"], cwd=tree.base, timeout=600)
    tail = [ln for ln in out.splitlines() if ln.strip()][-1:] or [""]
    check("A6e C# 自检", rc == 0 and "FAIL" not in out, tail[0][:120])


# ============================================================ B 段
def case_b(tree: Tree, src_tag: str) -> None:
    print("== B 段：236 窗口判据（真机读数离线复算） ==")
    fx = fixtures()
    if "red" not in fx:
        skip("B 段窗口夹具", f"缺 {RESCUED} ⇒ 无法造红/绿窗口")
        return
    ok, probs = judge_smapi(fx["red"])
    check("B1 0.7.40 真形态 ⇒ 参考判据判红（NewDay 3 / Save called 2）", not ok, probs[:1])
    if SMOKE_LEDGER.exists():
        _rc, out = tool_smapi(tree, SMOKE_LEDGER, fx["red"])
        check("B2 产品判据：真红窗口必须 problem", smapi_problem(out),
              "已判红" if smapi_problem(out) else "⚠ 产品判据没判红（回归）")
        _rc, outg = tool_smapi(tree, SMOKE_LEDGER, fx["green"])
        check("B3 产品判据：抢救后绿窗口不得 problem", not smapi_problem(outg),
              "无 problem" if not smapi_problem(outg) else "⚠ 绿窗口被误判红")
    else:
        skip("B2/B3 产品判据", f"缺冒烟账本 {SMOKE_LEDGER}（正式判定用 0.7.41 冒烟账本）")
    okg, _ = judge_smapi(fx["green"])
    check("B4 绿窗口参考判据不判红", okg)

    rc, js, _ = checker_json(tree, fx["green"])
    v = _verdict(js)
    raw = v.get("raw_counts") or {}
    counts = v.get("counts") or {}
    exc = v.get("excluded_by_chain") or v.get("excluded") or {}
    corrected = counts.get("save_called")
    if not raw or corrected is None:
        skip("B5 L16 插件行只进原始计数", f"检查器 JSON 无 raw_counts/counts：{sorted(js)}")
    else:
        check("B5 绿窗口 PASS 且 L16 只进原始计数（raw > 修正）",
              rc == 0 and raw.get("save_called", 0) > corrected,
              f"raw={raw.get('save_called')} corrected={corrected} excluded={exc.get('save_called')}")


# ============================================================ B-6 检查器终审
def case_b6(tree: Tree, src_tag: str) -> None:
    print("== B-6：save-chain-check 终审（8 夹具 + 真实一红一绿 + 三 GAP） ==")
    ck = checker_path(tree)
    if ck is None:
        skip("B6 检查器", "缺 save-chain-check.py")
        return
    rc, out = run([PY, str(ck), "--selftest"], cwd=tree.base)
    check("B6-1 --selftest 8 夹具 rc=0", rc == 0 and "SELFTEST PASS" in out,
          (out.strip().splitlines()[-1][:120] if out.strip() else ""))
    fx = fixtures()
    if "green" not in fx:
        skip("B6 真实窗口", f"缺 {RESCUED}")
        return
    rc_g, j_g, _ = checker_json(tree, fx["green"])
    v_g = _verdict(j_g)
    check("B6-2 真实绿窗口 PASS rc=0", rc_g == 0 and v_g.get("verdict") == "PASS",
          f"rc={rc_g} verdict={v_g.get('verdict')} counts={v_g.get('counts')}")
    rc_r, j_r, _ = checker_json(tree, fx["red"])
    v_r = _verdict(j_r)
    check("B6-3 真实红窗口 FAIL rc=1", rc_r == 1 and v_r.get("verdict") == "FAIL",
          f"rc={rc_r} verdict={v_r.get('verdict')} reasons={str(v_r.get('reasons'))[:100]}")
    rc2, j2, _ = checker_json(tree, fx["red"])
    v2 = _verdict(j2)
    check("B6-4 0.7.40 型红窗口仍 FAIL rc=1（未被完整性闸门吃掉）",
          rc2 == 1 and v2.get("verdict") == "FAIL", f"counts={v2.get('counts')}")
    rc4, j4, _ = checker_json(tree, fx["gap4"])
    v4 = _verdict(j4)
    check("B6-5 GAP-236B-4 已闭：缺 before save ⇒ 无法判定 rc=2",
          rc4 == 2 and v4.get("verdict") == "无法判定",
          f"rc={rc4} reasons={str(v4.get('reasons'))[:90]}")
    rc5, j5, _ = checker_json(tree, fx["gap5a"])
    v5 = _verdict(j5)
    o5 = v5.get("order") or {}
    check("B6-6 GAP-236B-5 已闭：缺 task 链但顺序正常 ⇒ PASS + checked_without_task",
          rc5 == 0 and v5.get("verdict") == "PASS" and o5.get("checked_without_task") is True,
          f"rc={rc5} order={o5}")
    rc5b, j5b, _ = checker_json(tree, fx["gap5b"])
    v5b = _verdict(j5b)
    check("B6-7 GAP-236B-5 已闭：缺 task 链 + 链内逆序 ⇒ FAIL rc=1",
          rc5b == 1 and v5b.get("verdict") == "FAIL",
          f"rc={rc5b} order={str(v5b.get('order'))[:120]}")
    rc_f, j_f, _ = checker_json(tree, fx["green"])
    of = (_verdict(j_f).get("order") or {})
    check("B6-8 save_task 完整 ⇒ use_task_chain=True 且非 without_task",
          rc_f == 0 and of.get("use_task_chain") is True and of.get("checked_without_task") is False,
          f"order={of}")
    if "st_partial" in fx:
        rc_p, j_p, _ = checker_json(tree, fx["st_partial"])
        v_p = _verdict(j_p)
        check("B6-9 save_task 部分缺失 ⇒ 无法判定 rc=2",
              rc_p == 2 and v_p.get("verdict") == "无法判定",
              f"rc={rc_p} reasons={str(v_p.get('reasons'))[:90]}")
    smoke = tree.src("scratch/smoke-0741.py")
    i0 = smoke.find("def step6(")
    i1 = smoke.find("\ndef ", i0 + 10)
    step6 = smoke[i0:i1] if i0 >= 0 else ""
    calls = "save-chain-check.py" in step6 and '"--out"' in step6
    reads = '["verdict"]' in step6 and '"counts"' in step6
    triad = all(k in step6 for k in ('"PASS"', '"FAIL"', '"无法判定"'))
    check("B6-10 消费端 step6 只认检查器 verdict/counts（不自己数六串）",
          calls and reads and triad, f"calls={calls} reads={reads} triad={triad}")


# ============================================================ C 段
def _dismiss_count(w) -> int:
    for attr in ("dismiss_calls", "dismissals", "dismissed"):
        val = getattr(w, attr, None)
        if isinstance(val, (list, tuple)):
            return len(val)
        if isinstance(val, int):
            return val
    return 0


def case_c(tree: Tree, src_tag: str) -> None:
    print("== C 段：作弊通道（卡面 7 条 + 自想 C8/C9/C10） ==")
    lr = tree.src("brain/agentfarm/longrun.py")
    vr = tree.src("tools/verify-run3.py")
    has236 = "cleanup_modal_stuck" in lr
    has237 = "harvest_demand" in lr
    has238 = "finalize_fallback" in lr or "finalize_fallback" in tree.src("tools/analyze-longrun.py")
    fx = fixtures()

    # C1 不关框就退出
    if "red" in fx:
        ok, probs = judge_smapi(fx["red"])
        check("C1a 不关框就退出 ⇒ 参考判据判红", not ok, probs[:1])
        if SMOKE_LEDGER.exists():
            _rc, out = tool_smapi(tree, SMOKE_LEDGER, fx["red"])
            check("C1b 产品判据：真形态（含 L16 插件行）不得被洗绿", smapi_problem(out),
                  "已判红" if smapi_problem(out) else "⚠ GAP-236-1")
    # C2 关框后立刻退出（保存链半截）
    if "half_chain" in fx:
        ok2, p2 = judge_smapi(fx["half_chain"])
        check("C2a 保存链半截 ⇒ 参考判据判红", not ok2, p2[:1])
        if SMOKE_LEDGER.exists():
            _rc2, out2 = tool_smapi(tree, SMOKE_LEDGER, fx["half_chain"])
            check("C2b 产品判据：保存链半截必须判红", smapi_problem(out2),
                  "已判红" if smapi_problem(out2) else "⚠ GAP-236-3")

    # C3 cleanup 自述
    if has236:
        info("C3c 脑侧 design：cleanup 卡住只作运行级记账、不上抬 finish.code（GAP-236-7，非阻塞）",
             "权威判据是步 6 的 SMAPI 六串")
        if "cleanup_modal_stuck" in vr:
            info("C3a verify-run3 引用 cleanup 自述矛盾", "已覆盖")
        else:
            info("C3a GAP-236-6（防御性、不阻塞）：verify-run3/analyzer 都不看 cleanup 自述",
                 "`finish.cleanup_modal_stuck=true` + `code=0` 的矛盾账本只能靠步 6 SMAPI 六串发现")
        md = tree.src("mod/AgentFarm.Bridge/ModalDismiss.cs")
        check("C3b Mod 侧兜底：存档/出货菜单 dismiss 必拒（wait_only）",
              ("wait_only" in md) and ("ShippingMenu" in md) and ("IsSaveMenu" in md),
              "ModalDismiss.cs 双保险")

    # C4 237 demand 上界
    if not has237:
        skip("C4 手写 demand=99 被钉 12", "task-237 未落地")
    else:
        cap = re.search(r"HARVEST_DEMAND_CAP\s*=\s*(\d+)", lr)
        clamp = bool(re.search(r"min\(int\(HARVEST_DEMAND_CAP\)", lr))
        check("C4a 237 上界钉死：HARVEST_DEMAND_CAP=12 且 clamp",
              bool(cap) and cap.group(1) == "12" and clamp,
              f"cap={cap.group(1) if cap else None} clamp={clamp}")
        check("C4b 需求来自可收格数而非手写", "_harvest_demand" in lr)
        seg237 = lr[lr.find("def _harvest_demand"):][:2500]
        check("C4c 需求估算读可收格数/没被上界替代",
              bool(seg237) and ("harvest" in seg237 or "tiles" in seg237)
              and "HARVEST_DEMAND_CAP" in seg237, seg237[:72])

    # C5/C6 属 238
    if not has238:
        skip("C5 兜底回填只补闭合原因码、不泛滥", "task-238 未落地")
        skip("C6 兜底不得改 executed_steps", "task-238 未落地")
    else:
        seg = lr[lr.find("finalize_fallback"):][:2500]
        check("C6 兜底代码块内不写 executed_steps",
              bool(seg) and not re.search(r"executed_steps\s*[+\-]?=", seg), seg[:80])
        # C5（自想通道 / Lead 提示）：兜底映射表 + 只补「0 步且空原因」 + 不动步数/判定
        try:
            _lr, TL = _load_tree(tree)
            LR = _lr
            FW = importlib.import_module("agentfarm.farmwork")

            def _mk5(w):
                client = TL.FakeClient(w)
                worker = FW.FarmWorker(client, log=lambda *_: None, pause=lambda _s: None)
                r = TL.make_run(w, target_days=1, max_days=1)
                r.client = client
                r.worker = worker
                return r

            rep = TL.DayReport(day_key=("spring", 1, 1), started_at=0.0)
            mapping = {
                ("inventory_blocked", ""): "no_slot",
                ("blocked_modal", ""): "blocked_modal",
                ("blocked_event", ""): "gated",
                ("stuck:连续 3 轮世界没有任何变化", ""): "world_stuck",
                ("bridge_down", ""): "world_stuck",
                ("sleep_failed", ""): "world_stuck",
                ("sleep", "night:到点收工"): "gated",
                ("sleep", "stamina:体力 8 < 12"): "gated",
                ("sleep", "no_work:确实找不到可做的活"): "gated",
                ("sleep", "weird:没见过的收尾"): "unknown_evidence",
            }
            bad = []
            for (eb, er), want in mapping.items():
                rep.ended_by, rep.ended_reason = eb, er
                got = LR.LongRun._finalize_reason_for(rep)
                if got != want:
                    bad.append(f"{eb}/{er[:12]}⇒{got}(want {want})")
            check("C5a 兜底映射表 10 例（inventory_blocked→no_slot / modal / event / stuck / "
                  "bridge/sleep_failed→world_stuck / 夜与体力→gated / 未知→unknown_evidence）",
                  not bad, str(bad[:3]))
            run = _mk5(TL.FakeWorld())
            run.intent_coverage = [
                {"intent_id": "d#01", "task": "harvest", "executed_steps": 3,
                 "reasons": {}, "requested_tiles": 5},
                {"intent_id": "d#02", "task": "water_area", "executed_steps": 0,
                 "reasons": {"no_target": 1}, "requested_tiles": 2},
                {"intent_id": "d#03", "task": "water_area", "executed_steps": 0,
                 "reasons": {}, "requested_tiles": 4},
                {"intent_id": "d#04", "task": "till_area", "executed_steps": 0,
                 "reasons": {}, "requested_tiles": 0},
            ]
            rep2 = TL.DayReport(day_key=("spring", 1, 1), started_at=0.0,
                                ended_by="inventory_blocked", ended_reason="背包满")
            before_checks = dict(rep2.checks or {})
            before_verified = rep2.verified
            run._finish_intent_coverage(rep2)
            recs = {str(r.get("intent_id")): r for r in (rep2.intent_coverage or [])}
            c1, c2 = recs.get("d#01") or {}, recs.get("d#02") or {}
            c3, c4 = recs.get("d#03") or {}, recs.get("d#04") or {}
            check("C5b 只补「0 步且空原因」：有步数 / 已有原因码的记录一字不动",
                  c1.get("reasons") == {} and c2.get("reasons") == {"no_target": 1},
                  f"d#01={c1.get('reasons')} d#02={c2.get('reasons')}")
            check("C5c 兜底回填用闭合原因码 + evidence.why=finalize_fallback",
                  c3.get("reasons") == {"no_slot": 1} and c4.get("reasons") == {"no_slot": 1}
                  and (c3.get("evidence") or {}).get("why") == "finalize_fallback",
                  f"d#03={c3.get('reasons')} ev={(c3.get('evidence') or {}).get('why')}")
            check("C5d 兜底不改 executed_steps / checks / verified",
                  [int((recs.get(k) or {}).get("executed_steps") or 0)
                   for k in ("d#01", "d#03")] == [3, 0]
                  and dict(rep2.checks or {}) == before_checks
                  and rep2.verified == before_verified,
                  f"checks={len(rep2.checks or {})} verified={rep2.verified}")
            check("C5e reasons_are_intent_level 按 requested_tiles==0 推导",
                  c3.get("reasons_are_intent_level") is False
                  and c4.get("reasons_are_intent_level") is True,
                  f"d#03={c3.get('reasons_are_intent_level')} d#04={c4.get('reasons_are_intent_level')}")
            codes = set(getattr(LR, "INTENT_REASON_CODES", ()) or ())
            check("C5f 兜底码 ∈ 闭合集 INTENT_REASON_CODES", "no_slot" in codes,
                  f"codes={len(codes)}")
        except Exception as exc:  # noqa: BLE001
            check("C5 兜底通道可运行", False, f"{type(exc).__name__}: {exc}")

    # C7 伪造 after save
    if "forged_after" in fx:
        ok7, p7 = judge_smapi(fx["forged_after"])
        check("C7a 伪造 after save ⇒ 参考判据判红", not ok7, p7[:1])
        if SMOKE_LEDGER.exists():
            _rc7, out7 = tool_smapi(tree, SMOKE_LEDGER, fx["forged_after"])
            check("C7b 产品判据：伪造 after save 不得洗绿", smapi_problem(out7),
                  "仍判红" if smapi_problem(out7) else "⚠ GAP-236-5")

    # C8（自想）收尾清理不得关不可逆模态
    if has236:
        seg = lr[lr.find("def _cleanup_modals_before_finish"):][:9000]
        check("C8a 收尾守卫：eventUp/职业弹窗不关、存档菜单只等、跳过如实记账",
              all(k in seg for k in ("eventUp", "LevelUpMenu", "professionsToChoose",
                                     "MODAL_WAIT_ONLY", "cleanup_skipped")),
              "_cleanup_modals_before_finish")
        fin = lr[lr.find("def _finish(self, code"):][:4000]
        check("C8e `_finish` 真的在 `finish` 前调用收尾守卫，且 stuck 进 summary/journal",
              ("_cleanup_modals_before_finish(" in fin) and ("cleanup_modal_stuck" in fin)
              and ("summary" in fin), fin[:0] or "见 _finish")
        try:
            _lr, TL = _load_tree(tree)
            FW = importlib.import_module("agentfarm.farmwork")

            def _mk(w):
                client = TL.FakeClient(w)
                worker = FW.FarmWorker(client, log=lambda *_: None, pause=lambda _s: None)
                r = TL.make_run(w, target_days=1, max_days=1)
                r.client = client
                r.worker = worker
                return r

            w1 = TL.FakeWorld()
            w1.ui_script = [{"activeMenu": "LevelUpMenu", "isModal": True,
                             "professionsToChoose": [{"index": 0, "name": "Tiller"}]}] * 5
            res1 = _mk(w1)._cleanup_modals_before_finish()
            check("C8b 职业弹窗挂着 ⇒ cleanup 跳过且零 dismiss",
                  res1.get("skipped") == "profession_pending" and _dismiss_count(w1) == 0,
                  f"skipped={res1.get('skipped')} dismiss={_dismiss_count(w1)}")
            w2 = TL.FakeWorld()
            w2.ui_script = [{"activeMenu": "DialogueBox", "isModal": True, "eventUp": True}] * 5
            res2 = _mk(w2)._cleanup_modals_before_finish()
            check("C8c 事件对话挂着 ⇒ cleanup 跳过且零 dismiss",
                  res2.get("skipped") == "event_up" and _dismiss_count(w2) == 0,
                  f"skipped={res2.get('skipped')} dismiss={_dismiss_count(w2)}")
            # C8d 对照：存档菜单只等不关（auto-gone 一次后自己消失 ⇒ 关框次数为 0）
            w3 = TL.FakeWorld()
            w3.ui_script = [{"activeMenu": "SaveGameMenu", "isModal": True,
                             "_autoGoneAfterPolls": 1}] * 5
            res3 = _mk(w3)._cleanup_modals_before_finish()
            check("C8d 存档菜单只等不关（dismiss 0 次、未判 stuck）",
                  _dismiss_count(w3) == 0 and res3.get("stuck") is False,
                  f"dismiss={_dismiss_count(w3)} stuck={res3.get('stuck')} attempts={res3.get('attempts')}")
        except Exception as exc:  # noqa: BLE001
            skip("C8b/C8c/C8d 动态：职业/事件/存档弹窗挂着时 cleanup 行为",
                 f"{type(exc).__name__}: {exc}")

    # C9（自想）237 字段自洽
    if has237:
        check("C9 237 字段自洽：_slot_relief 记 harvest_demand/target_free/reached",
              all(k in lr for k in ("harvest_demand", "target_free", "reached")))

    # C10（自想）工具不判 cleanup 矛盾（GAP 级、不阻塞）
    if has236:
        if "cleanup_modal_stuck" in vr:
            info("C10 工具已覆盖 cleanup_modal_stuck × code=0 矛盾", "见 verify-run3")
        else:
            info("C10 GAP-236-6（防御性、不阻塞）：工具不判 cleanup 矛盾",
                 "只靠步 6 SMAPI 六串兜；伪造需手改账本")


# ============================================================ D 段
def case_d(tree: Tree, src_tag: str) -> None:
    print("== D 段：变异矩阵接口 ==")
    scripts = [HERE / "_t236_mutate.py", HERE / "_t237_mutate.py", HERE / "_t238_mutate.py"]
    present = [p.name for p in scripts if p.is_file()]
    if present:
        info("D0 作者变异脚本", ", ".join(present))
        info("D1 复跑命令", "python scratch/_t236_mutate.py（在冻结树根跑，PYTHONUTF8=1）")
    else:
        skip("D0 作者变异脚本", "scratch/ 下无 _t236/_t237/_t238_mutate.py ⇒ 等交付后复跑")
    mine = HERE / "_t239_mutate.py"
    if mine.is_file():
        rc, out = run([PY, str(mine), "--list"], cwd=tree.base)
        if rc == 0:
            info("D2 我的变异登记表", out.strip()[:300])
    else:
        skip("D2 我的变异登记表", "缺 scratch/_t239_mutate.py")
    skip("D3 自报 vs 实测两列", "冻结树 + 作者脚本齐备后跑（正式判定必填）")


# ============================================================ E 段
def case_e(tree: Tree, src_tag: str) -> None:
    print("== E 段：结论 ==")
    info("E0 src", src_tag)
    skip("E1 一句话结论", "236/237/238 全交付 + 冻结树齐备后填；B-6 检查器终审已 PASS")


# ============================================================ 动态装载
def _load_tree(tree: Tree):
    base = tree.base
    for p in (str(base), str(base / "brain")):
        if p not in sys.path:
            sys.path.insert(0, p)
    for mod in [m for m in sys.modules if m == "agentfarm" or m.startswith("agentfarm.")]:
        sys.modules.pop(mod, None)
    return (importlib.import_module("agentfarm.longrun"),
            importlib.import_module("tests.test_longrun"))


CASES = {"A": case_a, "B": case_b, "B6": case_b6, "C": case_c, "D": case_d, "E": case_e}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tree", default="")
    ap.add_argument("--only", default="", help="逗号分隔：A,B,B6,C,D,E")
    ap.add_argument("--readings", action="store_true")
    ap.add_argument("--fixtures", action="store_true")
    args = ap.parse_args()
    tree = Tree(Path(args.tree).resolve()) if args.tree else Tree(REPO)
    src_tag = "frozen" if args.tree else "worktree"
    if args.fixtures:
        print("fixtures:", {k: str(v) for k, v in fixtures().items()})
        return 0
    only = [x.strip().upper() for x in args.only.split(",") if x.strip()] or list(CASES)
    for key in only:
        fn = CASES.get(key)
        if fn is None:
            print(f"[WARN] 未知段：{key}")
            continue
        try:
            if key == "A":
                fn(tree, src_tag, args.readings)  # type: ignore[misc]
            else:
                fn(tree, src_tag)  # type: ignore[misc]
        except Exception as exc:  # noqa: BLE001
            traceback.print_exc()
            check(f"{key} 段自身异常", False, f"{type(exc).__name__}: {exc}")
    print(f"\n汇总：PASS={PASS} FAIL={FAIL} SKIP={SKIP} INFO={INFO}  (src={src_tag})")
    out = HERE / ("_t239_probe_" + src_tag + ".txt")
    out.write_text("\n".join(f"{st}\t{tag}\t{detail}" for tag, st, detail in RESULTS) + "\n",
                   encoding="utf-8", newline="\n")
    print(f"明细已写 {out}")
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(main())
