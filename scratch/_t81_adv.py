r"""task-81 对抗反例（卡面第 6 条）：拿 `bound_basis` 这条新口径去洗白，工具必须判红。

三个反例都在"账本层面自洽"（checks 全 true、verified=true、finish 自称达标）：
  ADV-1  账本 `bound_basis` 谎报成 `attempted`（= 把 encircled 从分母里偷偷洗掉）
  ADV-2  账本干脆不写 `bound_basis`，用旧口径 `0.2*attempted` 的上界
  ADV-3  新口径写对，但想用"encircled 很大"解释掉 leftover、拿 verified

工具 = **仓库里的** `tools/verify-run3.py`（HEAD 版本）。
用法：$env:PYTHONUTF8="1"; python scratch\_t81_adv.py
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PY = sys.executable
TOOL = os.path.join(ROOT, "tools", "verify-run3.py")


def _load(name: str, path: str):
    spec = importlib.util.spec_from_file_location(name, path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


F = _load("t54f", os.path.join(HERE, "_t54_forge.py"))


def write(tag: str, day: list[dict], de: dict, days: int = 1) -> str:
    de["t"] = 2400.0
    for r in day:
        if r.get("event") == "day_end":
            r.clear()
            r.update(de)
            break
    path = os.path.join(HERE, f"review-t81-{tag}.jsonl")
    with open(path, "w", encoding="utf-8") as fh:
        for r in day:
            fh.write(json.dumps(r, ensure_ascii=False) + "\n")
        fh.write(json.dumps(F.finish_line(days), ensure_ascii=False) + "\n")
    return path


def big_stage(**kw) -> dict:
    st = {"stage": "clear_area", "tiles": 539, "ok": 0, "skipped": 0, "failed": 0,
          "failed_any": 0, "proven_inert": 0, "env_block": 0, "inconclusive": 0,
          "unreachable": 0, "unreachable_tiles": [], "unreachable_leftover": 0,
          "refused": 0, "refused_tiles": [], "refused_leftover": 0,
          "encircled": 539, "encircled_tiles": F.coords(19, x0=61, y0=9),
          "encircled_leftover": 539, "attempted": 564, "bound_basis": 25,
          "encircled_tried": 433, "engaged": 11, "stopped": "", "leftover": 0}
    st.update(kw)
    return st


def common_day():
    day, _ds, de = F.base_day()
    day = [copy.deepcopy(r) for r in day]
    de = copy.deepcopy(de)
    de.update({"verified": True, "ok_steps": 564, "failed_steps": 0, "skipped_steps": 0,
               "checks": F.all_true_checks(), "ended_by": "sleep",
               "ended_reason": "no_work:确实找不到可做的活（地里的活干完了）",
               "attempted": 564, "encircled": 539,
               "encircled_tiles": F.coords(19, x0=61, y0=9),
               "unreachable": 0, "unreachable_tiles": [], "unreachable_bound": 5,
               "unreachable_exempt": 0, "refused": 0, "refused_tiles": [],
               "refused_bound": 5, "refused_exempt": 0})
    return day, de


def adv1() -> str:
    day, de = common_day()
    st = big_stage(bound_basis=564)          # 谎报：把 encircled 从分母里洗掉
    de.update({"stages": [st], "bound_basis": 564, "unreachable_bound": 112})
    return write("adv1-bound-basis-lie", day, de)


def adv2() -> str:
    day, de = common_day()
    st = big_stage()
    st.pop("bound_basis", None)
    de.update({"stages": [st], "unreachable_bound": 112})   # 不写 bound_basis，用旧口径上界
    return write("adv2-bound-basis-missing", day, de)


def adv3() -> str:
    day, de = common_day()
    st = big_stage(leftover=539, ok=0)       # 想用"encircled 很大"解释掉 leftover
    de.update({"stages": [st], "bound_basis": 25})
    return write("adv3-encircled-excuses-leftover", day, de)


def adv4() -> str:
    """账本把 `bound_basis` 谎报成 `attempted`，但上界写成自算值 ⇒ 看工具报不报"账本值 > 自算"。"""
    day, de = common_day()
    st = big_stage(bound_basis=564)
    de.update({"stages": [st], "bound_basis": 564, "unreachable_bound": 5})
    return write("adv4-bound-basis-lie-bound-ok", day, de)


def run(path: str) -> tuple[int, str]:
    p = subprocess.run([PY, TOOL, "--journal", path, "--days", "1"],
                       capture_output=True, text=True, encoding="utf-8", cwd=ROOT)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def main() -> int:
    bad = 0
    for tag, mk in (("ADV-1", adv1), ("ADV-2", adv2), ("ADV-3", adv3)):
        path = mk()
        code, out = run(path)
        probs = [ln.strip() for ln in out.splitlines() if "问题" in ln or "⇒" in ln]
        print(f"== {tag} {os.path.basename(path)} ⇒ exit {code}")
        for ln in probs[-6:]:
            print("   ", ln)
        if code == 0:
            bad += 1
    print()
    print("判定：", "PASS（三个反例全被工具拦住）" if bad == 0 else f"FAIL（{bad} 个反例白过）")
    # ADV-4 是"账本 bound_basis 字段本身谎报"的单独取证：看它有没有被点名。
    p4 = adv4()
    c4, o4 = run(p4)
    named = [ln.strip() for ln in o4.splitlines() if "上界基数" in ln]
    print()
    print(f"== ADV-4 {os.path.basename(p4)} ⇒ exit {c4}")
    print(f"   点名『上界基数账本 bound_basis > 自算』的行数 = {len(named)}")
    for ln in named:
        print("   ", ln)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
