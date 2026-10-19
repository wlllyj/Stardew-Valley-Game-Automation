# -*- coding: utf-8 -*-
"""【T16 / deputy-lead】0.7.49 冻结树对抗验收装置（provenance 双跑 + 变异独立复跑）。

- 一切基于 `git archive <ref>` 解出的**冻结树**（默认 ref=51ef0a7），不碰主工作树。
- 用法（DSH python + PYTHONUTF8=1）：
    $env:PYTHONUTF8="1"; & <DSH python> scratch\\_t16_accept.py [ref]

产物：scratch/_t16_accept_out.txt（同时打印到 stdout）。
"""
from __future__ import annotations

import hashlib
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(r"D:\OpenCode Workspace\星露谷游戏自动化")
PY = (r"C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime"
      r"\dependencies\python\python.exe")
REF = sys.argv[1] if len(sys.argv) > 1 else "51ef0a7"

KEY_BLOBS = [
    "brain/agentfarm/fields.py",
    "brain/agentfarm/longrun.py",
    "brain/agentfarm/bridge.py",
    "tests/test_fields.py",
    "tests/test_longrun.py",
    "tools/verify-zone-retention.py",
    "tools/_note-0749.txt",
    "mod/AgentFarm.Bridge/manifest.json",
]

# 作者 scratch/_p0_d1d2_mutate.py 的 MUTANTS 表（逐字复制，不改锚点）
MUTANTS = [
    ("M1_f1_d1_zblocker_revert", "brain/agentfarm/fields.py",
     'ZONE_BLOCKER_KINDS = frozenset(BLOCKER_KINDS | {CLUMP_KIND})',
     'ZONE_BLOCKER_KINDS = frozenset(BLOCKER_KINDS | {"stump", "log", "boulder", "rockPile", "greenRain"})',
     ["tests.test_fields.ZoneBlockerKindsTest", "tests.test_fields.VerifyZoneRetentionCliTest"]),
    ("M2_d2_buy_dict_truthiness", "brain/agentfarm/longrun.py",
     "changed = self._preconditions_apply(obs, rep)",
     "changed = self._preconditions(obs, rep)",
     ["tests.test_longrun.TestBuyUpgradeDispatch"]),
    ("M3_zone_blockers_total_failclosed_returns_zero", "brain/agentfarm/fields.py",
     '    if loc.get("tilesTruncated"):\n        return None',
     '    if loc.get("tilesTruncated"):\n        return 0',
     ["tests.test_fields.ZoneBlockerKindsTest", "tests.test_fields.VerifyZoneRetentionCliTest"]),
    ("M4_upgrade_tool_journal_drop_hardcoded_axe", "brain/agentfarm/longrun.py",
     'tool="axe", tool_hardcoded=True,\n                                  before=getattr(st, "before", None)',
     'before=getattr(st, "before", None)',
     ["tests.test_longrun.TestBuyUpgradeDispatch"]),
]

COUNT_RE = re.compile(r"Ran (\d+) tests?")
OUT: list[str] = []


def log(s: str = "") -> None:
    OUT.append(s)
    print(s)


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest().upper()


def run_full(tree: Path):
    """全量：cd tree/tests && python -m unittest discover -p 'test_*.py'"""
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = str(tree / "brain")
    p = subprocess.run([PY, "-m", "unittest", "discover", "-p", "test_*.py"],
                       cwd=str(tree / "tests"), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    out = (p.stdout or "") + (p.stderr or "")
    m = COUNT_RE.search(out)
    ran = int(m.group(1)) if m else -1
    ok = bool(re.search(r"^OK\b", out, re.M))
    fails = len(re.findall(r"^(?:FAIL|ERROR): ", out, re.M))
    tail = out.strip().splitlines()[-1] if out.strip() else ""
    return ran, fails, ok, tail, out


def run_mods(tree: Path, mods: list[str]):
    env = dict(os.environ)
    env["PYTHONUTF8"] = "1"
    env["PYTHONPATH"] = str(tree / "brain")
    p = subprocess.run([PY, "-m", "unittest", "-v", *mods],
                       cwd=str(tree), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", env=env)
    out = (p.stdout or "") + (p.stderr or "")
    m = COUNT_RE.search(out)
    ran = int(m.group(1)) if m else -1
    failed = len(re.findall(r"^(?:FAIL|ERROR): ", out, re.M))
    ok = bool(re.search(r"^OK\b", out, re.M))
    return ran, failed, ok, out


def main() -> int:
    tmp = Path(tempfile.mkdtemp(prefix="t16_"))
    tree = tmp / "tree"
    tree.mkdir()
    tar = tmp / "frozen.tar"
    subprocess.run(["git", "archive", "--format=tar", REF, "-o", str(tar)],
                   cwd=str(REPO), check=True)
    subprocess.run(["tar", "-xf", str(tar), "-C", str(tree)], check=True)

    log(f"================ T16 冻结树对抗验收  ref={REF} ================")
    # ---- 1. provenance：文件数 + 关键 blob ----
    ls = subprocess.run(["git", "ls-tree", "-r", "--name-only", REF],
                        cwd=str(REPO), capture_output=True, text=True)
    tracked = [x for x in ls.stdout.splitlines() if x.strip()]
    log(f"[provenance] git ls-tree -r 文件数 = {len(tracked)}")
    extracted = sum(1 for _ in tree.rglob("*") if _.is_file())
    log(f"[provenance] 解出文件数 = {extracted}")
    for rel in KEY_BLOBS:
        f = tree / rel
        if not f.exists():
            log(f"[blob] {rel:44s} MISSING-IN-ARCHIVE")
            continue
        rp = subprocess.run(["git", "rev-parse", f"{REF}:{rel}"], cwd=str(REPO),
                            capture_output=True, text=True).stdout.strip()
        log(f"[blob] {rel:44s} git={rp[:12]} sha256={sha256(f)}")

    # ---- 2. provenance 双跑：全量单测 ----
    for i in (1, 2):
        ran, fails, ok, tail, out = run_full(tree)
        log(f"[full#{i}] Ran {ran} / failures+errors={fails} / OK={ok} / tail={tail!r}")
        if not ok:
            log("---- full#%d 失败行 ----" % i)
            for ln in out.splitlines():
                if re.match(r"^(FAIL|ERROR): ", ln):
                    log("  " + ln)

    # ---- 3. 变异独立复跑 ----
    base_mods = sorted({m for *_, ms in MUTANTS for m in ms})
    ran, failed, ok, _ = run_mods(tree, base_mods)
    log(f"\n[baseline] 定向 Ran {ran} / failed={failed} / OK={ok}")
    if not ok:
        log("!! 冻结树定向基线不是绿的 —— 装置不可信，中止")
        (REPO / "scratch" / "_t16_accept_out.txt").write_text("\n".join(OUT), encoding="utf-8")
        shutil.rmtree(tmp, ignore_errors=True)
        return 2

    results = []
    for name, rel, old, new, mods in MUTANTS:
        f = tree / rel
        src = f.read_text(encoding="utf-8")
        n = src.count(old)
        if n != 1:
            results.append((name, "ADAPTER-ERROR", f"锚点命中 {n} 次（应为 1）"))
            log(f"[{name}] ADAPTER-ERROR 锚点命中 {n} 次")
            continue
        f.write_text(src.replace(old, new), encoding="utf-8", newline="")
        try:
            jran, jfailed, jok, out = run_mods(tree, mods)
        finally:
            f.write_text(src, encoding="utf-8", newline="")
        verdict = "KILL" if (jfailed > 0 or not jok) else "SURVIVE(测试没盯住!)"
        results.append((name, verdict, f"Ran {jran} failed={jfailed}"))
        log(f"[{name}] {verdict}  Ran={jran} failed={jfailed}")
        if verdict.startswith("SURVIVE"):
            log(out[-2500:])

    log("\n================ 变异实测汇总 ================")
    for name, verdict, detail in results:
        log(f"{verdict:20s} {name:46s} {detail}")
    killed = sum(1 for _, v, _ in results if v == "KILL")
    log(f"杀数 = {killed} / {len(results)}")

    (REPO / "scratch" / "_t16_accept_out.txt").write_text("\n".join(OUT), encoding="utf-8")
    shutil.rmtree(tmp, ignore_errors=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
