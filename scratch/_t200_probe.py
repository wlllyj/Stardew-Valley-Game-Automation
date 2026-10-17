r"""task-200：0.7.37 批次（task-198/199/195/196/197 + 193）独立对抗验收探针。

用法：
  & $py -W error::SyntaxWarning scratch\_t200_probe.py            # 跑当前树
  $env:T200_ROOT = "$PWD\scratch\_t200_pre198"; & $py ...          # 跑冻结快照树（pre）
  $env:T200_FORCE = "1"                                           # 未交付也照跑（拿 pre 侧 FAIL 原文）

纪律：只写 `scratch/`；不改生产代码；`T200_ROOT` 只指向 `git archive` 出来的冻结快照。
设计：夹具/工具调用复用 `scratch\_t185_probe.py`（成熟脚手架），本文件只写本批的用例。
"""
from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
ROOT = Path(os.environ.get("T200_ROOT") or WS)
FORCE = bool(os.environ.get("T200_FORCE"))

# _t185_probe 在 import 时就按 T185_ROOT 解析 brain/tests 的 import ⇒ 必须先设环境
os.environ["T185_ROOT"] = str(ROOT)
_spec = importlib.util.spec_from_file_location("t185", WS / "scratch" / "_t185_probe.py")
T = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(T)
T.ROOT = ROOT
J = WS / "scratch" / "_t200_j"
J.mkdir(parents=True, exist_ok=True)

check, skip = T.check, T.skip
NOTES: list[tuple[str, bool, str]] = []


def info(tag: str, ok: bool, detail: str = "") -> None:
    """只记录、不计入 PASS/FAIL（版本号这类"冻结后必然变化"的口径）。"""
    NOTES.append((tag, ok, detail))
    print(("  info " if ok else "  WARN ") + tag + (f" :: {detail}" if detail else ""))


def finding(tag: str, ok: bool, detail: str = "") -> None:
    NOTES.append((tag, ok, detail))
    print(("  info " if ok else "  WARN ") + tag + (f" :: {detail}" if detail else ""))


def marker(rel: str, needle: str) -> bool:
    p = ROOT / rel
    try:
        return needle in p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False


def has_198() -> bool:
    return (FORCE or marker("brain/agentfarm/farmwork.py", "no_slot")) \
        and marker("brain/agentfarm/longrun.py", "inventory_blocked")


def has_199() -> bool:
    return FORCE or (marker("mod/AgentFarm.Bridge/Contracts.cs", "readyTiles")
                     and marker("brain/agentfarm/farmwork.py", "ready_far_blocked"))


def has_195() -> bool:
    return FORCE or marker("mod/AgentFarm.Bridge/ClumpRules.cs", "5")


def has_196() -> bool:
    return FORCE or marker("brain/agentfarm/farmwork.py", "collateral_loot")


def has_197() -> bool:
    # 197 判据只能实测：子进程抓 stdout 是否显式编码 / 是否有 ASCII 标记
    p = ROOT / "tests" / "test_longrun.py"
    try:
        txt = p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return False
    return "SELFTEST_OK" in txt or 'encoding="utf-8"' in txt and "test_csharp_rules_self_test" in txt


# ---------------------------------------------------------------- A 段（批次级）
CHECKS_10 = {
    "crops_watered", "day_justified", "no_blocking_modal", "no_hard_failures",
    "no_unmet_stages", "refused_within_bound", "slept_by_us", "unreachable_within_bound",
    "watered_outdoor", "zero_action_evidenced",
}


def case_a() -> None:
    print("== A 段：批次级不变量（不 bump / checks 10 键 / JUSTIFIED_END_REASONS 不变）==")
    import json
    try:
        man = json.loads((ROOT / "mod/AgentFarm.Bridge/manifest.json").read_text(encoding="utf-8"))
        ver = str(man.get("Version") or "")
    except Exception as exc:                              # noqa: BLE001
        ver = f"(读不到: {exc})"
    info("A1 本批不 bump（manifest 仍是冻结的 0.7.36；冻结后变 0.7.37 属正常）", ver == "0.7.36", f"manifest={ver}")
    try:
        br = (ROOT / "brain/agentfarm/bridge.py").read_text(encoding="utf-8")
        exp = [ln for ln in br.splitlines() if ln.startswith("MOD_VERSION_EXPECTED")]
        info("A2 MOD_VERSION_EXPECTED 未越界 bump", '"0.7.36"' in (exp[0] if exp else ""), exp[0][:70] if exp else "缺")
    except OSError:
        info("A2 MOD_VERSION_EXPECTED 未越界 bump", False, "bridge.py 读不到")
    if has_198() or has_199() or has_196():
        lr = ROOT / "brain/agentfarm/longrun.py"
        txt = lr.read_text(encoding="utf-8", errors="replace")
        info("A3 JUSTIFIED_END_REASONS 语义未变", 'JUSTIFIED_END_REASONS = ("night", "stamina", "no_work")' in txt)
        info("A4 checks 键集仍 10 键（不许新增/删）", all(k in txt for k in CHECKS_10))
    else:
        skip("A3/A4 差量不变量", "本批卡未交付")


# ---------------------------------------------------------------- task-198
def case_198() -> None:
    print("== task-198：背包满 ⇒ no_slot 不算硬失败 + 腾格收敛 + 不许洗 VERIFIED ==")
    if not has_198():
        skip("198 全部通道", "task-198 未交付（缺 no_slot / inventory_blocked）")
        return
    todo = [
        "198a 无空格 harvest ⇒ code=no_slot、不进 failed_steps、不封格、不吃 harvest_gave_up 上限",
        "198b 无空格日 ⇒ checks.no_hard_failures 不被它拉 false；但当天仍不许 VERIFIED（洗白检查）",
        "198c freeSlots==0 ⇒ 策略把 ship/sell 提前（腾格优先），journal slot_relief",
        "198d 腾格回路收敛：伪造每轮腾 0 格 ⇒ 被 inventory_blocked/轮数上限拦住，不自旋",
        "198e 腾格后同一天能收成（正对照收成成功）",
        "198f checks 键集仍 10 键、JUSTIFIED_END_REASONS 不变",
    ]
    for t in todo:
        skip(t, "待 task-198 交付后实现")


# ---------------------------------------------------------------- task-199
def case_199() -> None:
    print("== task-199：readyTiles 与 readyCrops 同源 + 走不到不空转 + 缺字段 fail-closed ==")
    if not has_199():
        skip("199 全部通道", "task-199 未交付（缺 readyTiles / ready_far_blocked）")
        return
    todo = [
        "199a readyTiles 与 readyCrops 同源一致（伪造不一致 ⇒ 必须被拦/不可采信）",
        "199b 窗口外熟作物有坐标 ⇒ 走过去收（harvest_far 系列留痕）",
        "199c 走不到 ⇒ 如实 ready_far_blocked、当天有界（不许同秒连发换片 5 次 stuck）",
        "199d 缺 readyTiles 字段 ⇒ fail-closed 老行为（不许凭空多出目标）",
        "199e Mod 侧 C# 自检含 readyTiles/readyCrops 同源 + 截断标志断言",
    ]
    for t in todo:
        skip(t, "待 task-199 交付后实现")


# ---------------------------------------------------------------- task-195
def case_195() -> None:
    print("== task-195：use_tool 证据绑定目标格 + 原始技能不许静默连带 ==")
    if not has_195():
        skip("195 全部通道", "task-195 未交付")
        return
    todo = [
        "195a 目标格 ready!=true + use_tool ⇒ 回执不得声称该格已空/已完成",
        "195b 连带影响必须入回执（affected/collateral 字段）",
        "195c 证据能区分目标格证据与聚合证据（scope/tile）",
        "195d C# 自检 ≥3 条新断言实测（含变异杀数）",
    ]
    for t in todo:
        skip(t, "待 task-195 交付后实现")


# ---------------------------------------------------------------- task-196
def case_196() -> None:
    print("== task-196：附带掉落分栏（loot/collateral_loot）+ 不进白名单 + 口径说明 ==")
    if not has_196():
        skip("196 全部通道", "task-196 未交付")
        return
    todo = [
        "196a 目标掉落 + 附带掉落同动作 ⇒ 两栏分别正确",
        "196b 附带掉落不进白名单 harvested（下游 sell 白名单不含它）",
        "196c 全量背包差 ≠ 白名单逐 qid 差 ⇒ 不判失败",
        "196d 口径说明已写进 docs（_run10-criteria.md / _analyze-longrun-caliber.md）",
    ]
    for t in todo:
        skip(t, "待 task-196 交付后实现")


# ---------------------------------------------------------------- task-197
def _suite(env: dict[str, str], timeout: int = 900) -> tuple[int, str]:
    e = {k: v for k, v in os.environ.items()
         if k not in ("PYTHONUTF8", "PYTHONIOENCODING", "LC_ALL", "PYTHONPATH")}
    e.update(env)
    e["PYTHONPATH"] = str(ROOT / "brain") + os.pathsep + str(ROOT)
    r = subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", "tests"],
                       cwd=ROOT, env=e, capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    err = r.stderr or ""
    fails = [ln.strip() for ln in err.splitlines()
             if ln.startswith(("FAIL:", "ERROR:"))]
    tail = "\n".join(err.strip().splitlines()[-2:])
    return r.returncode, f"{tail} :: " + (" / ".join(fails)[:400] if fails else "无 FAIL/ERROR 行")


def case_197() -> None:
    print("== task-197：带/不带 PYTHONUTF8 都绿 + 故意注入 cp1252 也绿 ==")
    rc1, t1 = _suite({"PYTHONUTF8": "1"})
    check("197a 带 PYTHONUTF8=1 全量绿（基线）", rc1 == 0, f"rc={rc1} :: {t1}")
    rc2, t2 = _suite({})                                  # 完全不设 PYTHONUTF8
    check("197b 不带 PYTHONUTF8 全量绿（task-197 的目标）", rc2 == 0, f"rc={rc2} :: {t2}")
    rc3, t3 = _suite({"PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0", "LC_ALL": "C"})
    check("197c 故意注入 cp1252/cp1252 环境仍绿（护栏）", rc3 == 0, f"rc={rc3} :: {t3}")
    t = ROOT / "tests" / "test_longrun.py"
    txt = t.read_text(encoding="utf-8", errors="replace") if t.exists() else ""
    check("197d 子进程抓 stdout 处显式编码或 ASCII 标记（源码核查）",
          "SELFTEST_OK" in txt or 'encoding="utf-8"' in txt,
          "既无 SELFTEST_OK 也无 encoding=utf-8")


# ---------------------------------------------------------------- main
def main() -> int:
    print(f"ROOT={ROOT}")
    print("markers: " + ", ".join(
        f"{c}={'Y' if fn() else 'n'}" for c, fn in
        (("198", has_198), ("199", has_199), ("195", has_195), ("196", has_196), ("197", has_197))))
    for fn in (case_a, case_198, case_199, case_195, case_196, case_197):
        try:
            fn()
        except Exception as exc:                          # noqa: BLE001
            import traceback
            traceback.print_exc()
            check(f"{fn.__name__} 跑完不抛异常", False, f"{type(exc).__name__}: {exc}")
    print(f"\n== 汇总：PASS={T.PASS} FAIL={T.FAIL} SKIP={T.SKIP} ==")
    return 1 if T.FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
