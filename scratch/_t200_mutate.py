r"""task-200 变异实测器：把每张卡"自报的变异 ⇒ 杀死"逐条**亲自实测**，给「自报 vs 实测」两列。

纪律（task-180 GAP-2 / task-190 NIT-2 的教训）：自报数字一律不信，只认实测。

用法：
  & $py scratch\_t200_mutate.py --list                 # 列已登记的变异（含自报杀数）
  & $py scratch\_t200_mutate.py --all                  # 建树 + 跑 + 出表（默认）
  & $py scratch\_t200_mutate.py --only m198a           # 只跑一条
  & $py scratch\_t200_mutate.py --base scratch\_t200_post198   # 指定基线树（默认 _t200_base）

机制：`git archive` 出来/已建好的**冻结树** → 复制到 `scratch/_t200_mut/<case>` → 文本替换（必须恰好命中一次）
     → 按 kind 跑：
       probe   : T200_ROOT=<mutant> T200_SKIP_SUITE=1 T200_FORCE=1 跑 `_t200_probe.py`，数 `  FAIL ` 行
       csharp  : 在 mutant 里 `dotnet run --project mod/AgentFarm.Bridge.Tests/... -c Release --nologo`，数 `^FAIL ` 行
       unittest: 在 mutant 里跑指定 dotted test，数 `FAIL:`/`ERROR:` 行
只写 `scratch/`。
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
MUT_ROOT = WS / "scratch" / "_t200_mut"
PROBE = WS / "scratch" / "_t200_probe.py"
PY = sys.executable

# ---------------------------------------------------------------- 变异登记表
# 每项：name, card, claimed(作者自报杀数), kind, edits[(relpath, old, new)], note
CASES: list[dict] = []


def reg(name: str, card: str, claimed: int | str, kind: str, edits: list[tuple[str, str, str]],
        note: str = "") -> None:
    CASES.append({"name": name, "card": card, "claimed": claimed, "kind": kind,
                  "edits": edits, "note": note})


# ===== task-198（dev-coder 自报 7 条，自报杀数 10/4/2/1/2/3/1；实测用全量套件失败数）=====
reg("m198a_no_relief", "198", 10, "suite",
    [("brain/agentfarm/longrun.py",
      "        free_slots, need, status = self._bag_state(obs)\n"
      "        if status != \"ok\" or need <= 0:\n            return False",
      "        free_slots, need, status = self._bag_state(obs)\n"
      "        if True:\n            return False")],
    "腾格回路整个失效（永远不腾）⇒ 应收不进来、只能诚实收尾")
reg("m198b_no_slot_counts_as_hard_failure", "198", 4, "suite",
    [("brain/agentfarm/longrun.py",
      'failed_any = [s for s in all_steps\n'
      '                      if s.failed and not getattr(s, "no_slot", False)]',
      "failed_any = [s for s in all_steps if s.failed]")],
    "day 级 failed 又把 no_slot 算成硬失败（回归 A′ 的 no_hard_failures=false）")
reg("m198c_guard_claims_ripe_work_when_bag_full", "198", 2, "suite",
    [("brain/agentfarm/longrun.py",
      "                if (tile_ready(tv) and t not in self.harvest_gave_up\n"
      "                        and not bag_blocked):",
      "                if (tile_ready(tv) and t not in self.harvest_gave_up):")],
    "守卫在背包满时继续拿熟作物当『还能干活』")
reg("m198d_no_slot_consumes_quota", "198", 1, "suite",
    [("brain/agentfarm/longrun.py",
      '            if getattr(s, "no_slot", False):\n'
      "                # 【task-198】背包满 = **全局**阻塞（不是这一格的属性，也不是\"没拿到结论\"）：",
      '            if False:\n'
      "                # 【task-198】背包满 = **全局**阻塞（不是这一格的属性，也不是\"没拿到结论\"）：")],
    "每格配额又把 no_slot 当『这一格没做成』（吃配额 ⇒ 误封格）")
reg("m198e_low_water_waits_for_zero", "198", 2, "suite",
    [("brain/agentfarm/longrun.py",
      "        need = 1 if (free_slots <= SLOT_RESERVE and ready > free_slots) else 0",
      "        need = 1 if (free_slots <= 0 and ready > free_slots) else 0")],
    "低水位退回『0 格才腾』（是我第二轮预检打到的第二处病灶）")
reg("m198f_guard_falls_back_to_no_work", "198", 3, "suite",
    [("brain/agentfarm/longrun.py",
      "            if self.inventory_blocked_today:\n"
      "                free_slots, _need, _status = self._bag_state(obs)\n"
      '                return True, "inventory_blocked", (',
      "            if False:\n"
      "                free_slots, _need, _status = self._bag_state(obs)\n"
      '                return True, "inventory_blocked", (')],
    "背包堵住时守卫退化成 no_work（= 假达标：verified 会被洗成 True）")
reg("m198g_inventory_blocked_counts_as_justified", "198", 1, "suite",
    [("brain/agentfarm/longrun.py",
      '            "day_justified": is_justified_end(rep.ended_by, rep.ended_reason),',
      '            "day_justified": is_justified_end(rep.ended_by, rep.ended_reason)\n'
      '            or rep.ended_by == "inventory_blocked",')],
    "inventory_blocked 被算成『达标收工』（假 VERIFIED 通道）")

# ===== task-199 / 195 / 196 / 197 交付后逐条登记 =====
reg("m198a_no_slot_not_env_block", "198", "?", "probe",
    [("brain/agentfarm/farmwork.py",
      "            r.env_block = True\n            r.no_slot = True",
      "            r.env_block = False\n            r.no_slot = True")],
    "【我的补充】把 no_slot 从 env 族摘掉 ⇒ 198a-2/3/4 应变红")
reg("m198e_no_slot_check_disabled", "198", "?", "probe",
    [("brain/agentfarm/farmwork.py",
      '        if free_status == "ok" and free_rows <= 0:',
      "        if False:")],
    "【我的补充】满包判定失效（照常发请求）⇒ 198a-1 应变红")

# ===== task-199 / 195 / 196 / 197 交付后逐条登记 =====


def sh(cmd: list[str], cwd: Path, env: dict[str, str] | None = None, timeout: int = 1800):
    e = {k: v for k, v in os.environ.items()}
    if env:
        e.update(env)
    return subprocess.run(cmd, cwd=cwd, env=e, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", timeout=timeout)


def build_mutant(case: dict, base: Path) -> Path:
    dest = MUT_ROOT / case["name"]
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(base, dest, ignore=shutil.ignore_patterns(
        "__pycache__", "_t200_mut", "_t200_pre*", "_t200_post*", "_t185_pre", "*.pyc"))
    hits = 0
    for rel, old, new in case["edits"]:
        p = dest / rel
        txt = p.read_text(encoding="utf-8")
        n = txt.count(old)
        if n != 1:
            raise SystemExit(f"[{case['name']}] 变异锚点命中 {n} 次（要求恰好 1 次）：{rel} :: {old[:60]}")
        p.write_text(txt.replace(old, new, 1), encoding="utf-8")
        hits += 1
    print(f"  [build] {case['name']}（{hits} 处替换）")
    return dest


def run_case(case: dict, tree: Path) -> tuple[int, list[str]]:
    """返回（杀死条数, 被杀/失败行）。"""
    kind = case["kind"]
    if kind == "probe":
        r = sh([PY, "-W", "error::SyntaxWarning", str(PROBE)], cwd=WS, env={
            "T200_ROOT": str(tree), "T200_FORCE": "1", "T200_SKIP_SUITE": "1",
            "PYTHONUTF8": "1", "PYTHONPATH": str(tree / "brain") + os.pathsep + str(tree)})
        out = (r.stdout or "") + "\n" + (r.stderr or "")
        killed = [ln.strip() for ln in out.splitlines() if ln.strip().startswith("FAIL ")]
        return len(killed), killed
    if kind == "csharp":
        r = sh(["dotnet", "run", "--project",
                "mod/AgentFarm.Bridge.Tests/AgentFarm.Bridge.Tests.csproj",
                "-c", "Release", "--nologo"], cwd=tree)
        out = (r.stdout or "") + "\n" + (r.stderr or "")
        killed = [ln.strip() for ln in out.splitlines() if re.match(r"^FAIL\s", ln)]
        return len(killed), killed
    if kind.startswith("unittest:"):
        dotted = kind.split(":", 1)[1]
        r = sh([PY, "-m", "unittest", dotted], cwd=tree, env={
            "PYTHONUTF8": "1", "PYTHONPATH": str(tree / "brain") + os.pathsep + str(tree)})
        out = (r.stdout or "") + "\n" + (r.stderr or "")
        killed = [ln.strip() for ln in out.splitlines()
                  if ln.startswith(("FAIL:", "ERROR:"))]
        return len(killed), killed
    if kind == "suite":
        r = sh([PY, "-m", "unittest", "discover", "-s", "tests"], cwd=tree, env={
            "PYTHONUTF8": "1", "PYTHONIOENCODING": "utf-8",
            "PYTHONPATH": str(tree / "brain") + os.pathsep + str(tree)})
        out = (r.stdout or "") + "\n" + (r.stderr or "")
        killed = [ln.strip() for ln in out.splitlines()
                  if ln.startswith(("FAIL:", "ERROR:"))]
        return len(killed), killed
    raise SystemExit(f"未知 kind：{kind}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="scratch/_t200_base")
    ap.add_argument("--only", default="")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--kind", default="", help="覆盖登记里的 kind（如 suite / probe）")
    ap.add_argument("--check-anchors", action="store_true",
                    help="只校验每条变异的文本锚点在基线树里恰好命中 1 次（不建树、不跑）")
    a = ap.parse_args()
    if a.check_anchors:
        base = (WS / a.base) if not Path(a.base).is_absolute() else Path(a.base)
        bad = 0
        for c in CASES:
            for rel, old, _new in c["edits"]:
                p = base / rel
                n = p.read_text(encoding="utf-8").count(old) if p.exists() else -1
                if n != 1:
                    bad += 1
                    print(f"  [锚点坏] {c['name']} :: {rel} 命中 {n} 次 :: {old[:60]!r}")
        print(f"锚点校验：{len(CASES)} 条变异、坏 {bad} 处")
        return 1 if bad else 0
    if a.list or not CASES:
        print(f"已登记变异 {len(CASES)} 条：")
        for c in CASES:
            print(f"  {c['name']:<34} card={c['card']:<4} kind={c['kind']:<10} 自报杀={c['claimed']}  {c['note']}")
        if not CASES:
            print("  （空：等各卡交付后登记；结构见文件头注释）")
        return 0
    base = (WS / a.base) if not Path(a.base).is_absolute() else Path(a.base)
    if not base.is_dir():
        raise SystemExit(f"基线树不存在：{base}（先跑 scratch\\_t200_trees.py）")
    MUT_ROOT.mkdir(parents=True, exist_ok=True)
    sel = [dict(c, kind=(a.kind or c["kind"])) for c in CASES
           if not a.only or c["name"] == a.only]
    rows = []
    for c in sel:
        tree = build_mutant(c, base)
        n, killed = run_case(c, tree)
        rows.append((c, n, killed))
        shutil.rmtree(tree, ignore_errors=True)          # 省盘：跑完即删（可重建）
    print("\n== 变异实测（自报 vs 实测）==")
    print(f"{'case':<34} {'card':<5} {'kind':<10} {'自报':>4} {'实测':>4}  判定")
    bad = 0
    for c, n, killed in rows:
        claimed = c["claimed"]
        ok = "一致" if str(claimed) == "?" or int(claimed) == n else "**不符**"
        if ok != "一致":
            bad += 1
        print(f"{c['name']:<34} {c['card']:<5} {c['kind']:<10} {str(claimed):>4} {n:>4}  {ok}")
        for ln in killed[:4]:
            print(f"      └ {ln[:140]}")
    print(f"\n合计 {len(rows)} 条；自报/实测不符 {bad} 条")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
