# -*- coding: utf-8 -*-
"""T5 deputy-lead harness: git-archive provenance + write-side independence probe.

Read-only w.r.t. the repo: never mutates the working tree. All experiments run on
`git archive` exports in a temp dir.

Usage:
  PYTHONUTF8=1 <py> scratch/_t5_prov.py compare-journals     # 5.1: fix-independent ledger rc/red
  PYTHONUTF8=1 <py> scratch/_t5_prov.py prov <ref> [--tests]  # 5.2/5.3: freeze-tree provenance
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path

PY = r"C:\Users\admin\.dsh\dsh-runtimes\dsh-primary-runtime\dependencies\python\python.exe"
REPO = Path(r"D:\OpenCode Workspace\星露谷游戏自动化")
LOGS = REPO / "logs"
JOURNALS = [
    "longrun-runA-0732.jsonl",
    "longrun-runB-0732.jsonl",
    "longrun-3day-llm-run9.jsonl",
    "longrun-3day-llm-run9b.jsonl",
    "longrun-3day-llm-run9c.jsonl",
    "longrun-3day-llm-run9d.jsonl",
]
# the exact production fix under test (card-237 field parity at the clear_gate write site)
OLD = ("target_free=SLOT_RELIEF_TARGET_FREE, freed=0, stage=task,")
NEW = ("target_free=SLOT_RELIEF_TARGET_FREE, reached=False, freed=0,\n"
       "                      stage=task,")


def _env():
    return {**os.environ, "PYTHONUTF8": "1"}


def sh(args, cwd=None):
    return subprocess.run([str(a) for a in args], cwd=str(cwd) if cwd else None,
                          capture_output=True, text=True, errors="replace", env=_env())


def export(ref: str, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    tar = Path(tempfile.gettempdir()) / f"_t5_{uuid.uuid4().hex}.tar"
    r = sh(["git", "archive", "--format=tar", ref, "-o", tar], cwd=REPO)
    if r.returncode != 0:
        raise SystemExit(f"git archive failed: {r.stderr}")
    r = sh([os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "tar.exe"),
            "-xf", tar, "-C", dest])
    if r.returncode != 0:
        r = sh(["tar", "-xf", tar, "-C", dest])
    if r.returncode != 0:
        raise SystemExit(f"tar extract failed: {r.stderr}")
    tar.unlink(missing_ok=True)


def manifest(root: Path):
    out = {}
    for p in sorted(root.rglob("*")):
        if p.is_file():
            b = p.read_bytes()
            out[p.relative_to(root).as_posix()] = (len(b), hashlib.sha256(b).hexdigest().upper())
    return out


def analyze(tree: Path, journal: Path):
    r = sh([PY, tree / "tools" / "analyze-longrun.py", "--journal", journal,
            "--days", "3", "--json"], cwd=tree)
    red = und = subj = None
    if r.stdout.strip():
        try:
            d = json.loads(r.stdout)
            red = (d.get("red") or {}).get("total")
            subj = (d.get("red") or {}).get("subjects")
            u = d.get("undecidable")
            if isinstance(u, dict):
                und = u.get("total")
            elif isinstance(u, (list, tuple)):
                und = len(u)
            else:
                und = u
        except Exception as e:  # noqa: BLE001
            subj = f"<parse error {e}>"
    return r.returncode, red, und, subj


def verify(tree: Path, journal: Path):
    r = sh([PY, tree / "tools" / "verify-run3.py", "--journal", journal, "--days", "3"], cwd=tree)
    return r.returncode


def cmd_compare_journals():
    base = Path(tempfile.gettempdir()) / f"_t5_cmp_{uuid.uuid4().hex}"
    ta = base / "A_head"
    tb = base / "B_fixed"
    export("HEAD", ta)
    shutil.copytree(ta, tb)

    lr_a = ta / "brain" / "agentfarm" / "longrun.py"
    lr_b = tb / "brain" / "agentfarm" / "longrun.py"
    sa = lr_a.read_text(encoding="utf-8")
    print(f"A(HEAD) clear_gate has reached? {'reached=False, freed=0' in sa}")
    sb = sa.replace(OLD, NEW, 1)
    assert sb != sa, "patch anchor not found"
    lr_b.write_text(sb, encoding="utf-8")
    print(f"B(fixed) clear_gate has reached? {'reached=False, freed=0' in sb}")

    print(f"\n{'journal':34s} | {'A rc/red/und':16s} | {'B rc/red/und':16s} | same  | verifyA/verifyB")
    all_same = True
    rows = []
    for j in JOURNALS:
        jp = LOGS / j
        a = analyze(ta, jp)
        b = analyze(tb, jp)
        va = verify(ta, jp)
        vb = verify(tb, jp)
        same = (a == b) and (va == vb)
        all_same &= same
        print(f"{j:34s} | {str(a[:3]):16s} | {str(b[:3]):16s} | {str(same):5s} | {va}/{vb}")
        rows.append({"journal": j, "A": a, "B": b, "verifyA": va, "verifyB": vb, "same": same})
    print(f"\nALL IDENTICAL: {all_same}")
    out = REPO / "scratch" / "_t5_journals.json"
    out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"JOURNALS_JSON -> {out}")
    shutil.rmtree(base, ignore_errors=True)
    return 0 if all_same else 1


def cmd_prov(ref: str, run_tests: bool):
    dest = Path(tempfile.gettempdir()) / f"_t5_prov_{uuid.uuid4().hex}"
    export(ref, dest)
    m = manifest(dest)
    print(f"ref={ref} files={len(m)}")
    for key in ["mod/AgentFarm.Bridge/manifest.json", "brain/agentfarm/longrun.py",
                "brain/agentfarm/bridge.py", "tools/analyze-longrun.py",
                "tools/verify-run3.py", "tools/deploy-mod.py"]:
        if key in m:
            print(f"  {m[key][1]}  {m[key][0]:8d}  {key}")
        else:
            print(f"  <ABSENT>  {key}")
    dll = [k for k in m if k.lower().endswith("agentfarm.bridge.dll")]
    print(f"  dll blobs in tree: {dll or 'NONE (build artifact, not tracked)'}")
    # 冻结树（git archive）缺 gitignore 的夹具：.gitignore:19 `scratch/*` + `!scratch/*.py`
    # ⇒ scratch/_ledger_*.jsonl、scratch/obs-full.json 等不进 git；tests 依赖它们，
    # 不同步会 ERROR（FileNotFoundError）。这里从 REPO/scratch 同步非 .py 文件。
    synced = 0
    if (REPO / "scratch").is_dir():
        (dest / "scratch").mkdir(exist_ok=True)
        for p in (REPO / "scratch").rglob("*"):
            if p.is_file() and p.suffix != ".py":
                t = dest / p.relative_to(REPO)
                t.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(p, t)
                synced += 1
    print(f"  fixture sync: +{synced} gitignored scratch files -> {dest / 'scratch'}")
    if run_tests:
        # 本仓约定：tests/ 无 __init__.py（PEP420 命名空间包），
        # `discover -s tests -t .` 会 ImportError；正确姿势 = cwd=tests + discover -p test_*.py
        r = sh([PY, "-m", "unittest", "discover", "-p", "test_*.py"], cwd=dest / "tests")
        tail = [l for l in (r.stderr or "").splitlines()
                if l.startswith(("Ran ", "OK", "FAILED", "FAIL:", "ERROR:")) and not l.startswith("AssertionError")]
        print("TESTS rc=%d" % r.returncode)
        for l in tail:
            print("    " + l)
    print("DEST=" + str(dest))
    return 0


def main(argv):
    if not argv:
        print(__doc__)
        return 2
    if argv[0] == "compare-journals":
        return cmd_compare_journals()
    if argv[0] == "prov":
        return cmd_prov(argv[1], "--tests" in argv)
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
