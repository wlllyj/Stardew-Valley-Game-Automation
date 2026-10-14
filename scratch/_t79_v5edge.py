r"""task-79 附加：关闭后的边界尝试（防止"换个写法绕过 bound_basis 口径"）。

W1：账本显式写 `bound_basis=1000`（> 自算 200）⇒ 应 problem。
W2：`bound_basis` 写对（200）但把 `unreachable_bound` 压到自算值 40、仍写 `unreachable=200`
    + `unreachable_exempt=40` + `unreachable_within_bound=true` + `no_unmet_stages` 谎报 ⇒ 看是否还能白过。
W3 = 对照：本来的 V5（无 `bound_basis` 字段、bound=200）⇒ 应 problem（已被 `_t79_replay.py` 证明）。

用法：$env:PYTHONUTF8="1"; python scratch\_t79_v5edge.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable
NEW = os.path.join(ROOT, "tools", "verify-run3.py")


def _load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


F = _load("t54f2", os.path.join(HERE, "_t54_forge.py"))


def build(tag: str, *, basis_field, bound, exempt, checks_unmet, verified, leftover=200,
          unreachable=200, ok_steps=1):
    day, ds, de = F.base_day()
    day = [dict(r) for r in F.body(day)]
    enc_n = 800
    enc = [{"event": "encircled", "t": 2000.0 + i, "action": "clear", "stage": "clear_dead",
            "tile": [30 + i, 20], "zone": "field", "reason": "四邻无落脚点"} for i in range(enc_n)]
    un_c = [[100 + i, 30] for i in range(unreachable)]
    st_enc = F.set_stage(de, "clear_dead", tiles=0, attempted=enc_n, encircled=enc_n, ok=ok_steps)
    st_enc["encircled_tiles"] = [[e["tile"][0], e["tile"][1]] for e in enc]
    st_un = F.set_stage(de, "till_area", tiles=unreachable, leftover=leftover,
                        attempted=unreachable, unreachable=unreachable,
                        unreachable_leftover=leftover, ok=0, stopped="unreachable")
    st_un["unreachable_tiles"] = un_c
    checks = F.all_true_checks()
    checks["no_unmet_stages"] = checks_unmet
    de.update({"verified": verified, "ok_steps": ok_steps, "failed_steps": 0, "skipped_steps": 0,
               "stages": [st_enc, st_un], "ended_by": "sleep", "ended_reason": "night:到点了",
               "checks": checks, "encircled": enc_n, "encircled_tiles": st_enc["encircled_tiles"],
               "unreachable": unreachable, "unreachable_tiles": un_c,
               "unreachable_bound": bound, "unreachable_exempt": exempt,
               "refused": 0, "refused_tiles": [], "refused_bound": bound, "refused_exempt": 0})
    if basis_field is not None:
        de["bound_basis"] = basis_field
    day += enc
    day += [{"event": "unreachable", "t": 4000.0 + i, "action": "till", "stage": "till_area",
             "tile": un_c[i], "zone": "field", "reason": "四邻都站不过去"} for i in range(unreachable)]
    de["t"] = 6000.0
    day.append(de)
    path = os.path.join(HERE, f"review-t79-{tag}.jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        for r in day:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        fh.write(json.dumps(F.finish_line(1), ensure_ascii=False) + "\n")
    return path


def run(ledger: str):
    cp = subprocess.run([PY, NEW, "--journal", ledger, "--days", "1"],
                        capture_output=True, text=True, encoding="utf-8", errors="replace")
    out = (cp.stdout or "") + (cp.stderr or "")
    probs, seen = [], False
    for ln in out.splitlines():
        s = ln.strip()
        if s.startswith("问题"):
            seen = True
            continue
        if seen:
            if s.startswith("结论"):
                break
            if s.startswith("-"):
                probs.append(s)
    return cp.returncode, probs


cases = [
    ("W1 账本 bound_basis=1000（>自算 200）", dict(basis_field=1000, bound=200, exempt=200,
                                                checks_unmet=True, verified=True)),
    ("W2 bound_basis=200 写对、bound 压到 40、仍报 200 且 within_bound=true",
     dict(basis_field=200, bound=40, exempt=40, checks_unmet=False, verified=False)),
    ("W2' 同 W2 但把 no_unmet_stages 谎报 true/verified=true",
     dict(basis_field=200, bound=40, exempt=40, checks_unmet=True, verified=True)),
]
for label, kw in cases:
    p = build(label.split()[0].lower().replace("'", ""), **kw)
    rc, probs = run(p)
    print(f"--- {label}")
    print(f"    exit={rc}  问题 {len(probs)} 条")
    for x in probs[:4]:
        print("      ! " + x[:170])
print("DONE")
