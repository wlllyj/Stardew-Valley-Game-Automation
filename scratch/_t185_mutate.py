r"""task-185 自建变异矩阵（作者已删自己的变异脚本，这里独立重建）。

对 task-168 的"防洗白设计"逐点打掉，看 `scratch/_t185_probe.py` 是否变红。
每个 case：把冻结树 `scratch/_t185_post` 拷到 `scratch/_t185_mut/<case>`，
只改 `brain/agentfarm/longrun.py`（纯文本替换），再用 `T185_ROOT` 指向拷贝跑探针。
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
PY = sys.executable
SRC = WS / "scratch" / "_t185_post"
MUT = WS / "scratch" / "_t185_mut"
PROBE = WS / "scratch" / "_t185_probe.py"
TARGET = "brain/agentfarm/longrun.py"

MUTANTS: dict[str, list[tuple[str, str]]] = {
    "control": [],
    # F-X1 的原始形态：载入时不灌回格清单 ⇒ 重启后累计上界归零
    "m185a_no_hydration": [
        ("self.shed_zone_tiles[name] = loaded", "self.shed_zone_tiles[name] = set()"),
    ],
    # 上界按"区数"算而不是按格数算 ⇒ 跨进程上界被绕过
    "m185b_cap_counts_zones": [
        ('already = sum(int(z.get("tiles") or 0) for z in self.shed_zones.values())',
         "already = len(self.shed_zones)"),
    ],
    # 认输格从会计里被扣掉（`_leftover` 被改）⇒ 免罚额度通道
    "m185c_leftover_subtracts": [
        ("    def _leftover(self",
         "    def _leftover(self, *a, **kw):  # MUTANT\n"
         "        return [t for t in self._leftover_orig(*a, **kw)\n"
         "                if t not in self._shed_tile_set()]\n\n"
         "    def _leftover_orig(self"),
    ],
    # 认输记录把"还有活"一次扣光 ⇒ 守卫对别处也闭嘴
    "m185d_shed_deducts_everything": [
        ('"live_crops_at_shed": live_zone,', '"live_crops_at_shed": 10 ** 9,'),
    ],
    # 没有缺口也允许认输（正对照应被 P1 抓住）
    "m185e_no_deficit_gate": [
        ("if deficit <= 0:", "if False:"),
    ],
    # day_end 快照漏 tiles（卡面点名 day_end.scope_shed{zone,tiles,reason}）
    "m185f_snapshot_no_tiles": [
        ('rep.scope_shed = {"zone": zone_name, "tiles": len(tiles), "reason": reason,',
         'rep.scope_shed = {"zone": zone_name, "reason": reason,'),
    ],
}


def build(case: str, patches: list[tuple[str, str]]) -> tuple[Path, list[str]]:
    dst = MUT / case
    if dst.exists():
        shutil.rmtree(dst, ignore_errors=True)
    shutil.copytree(SRC, dst, ignore=shutil.ignore_patterns(
        "__pycache__", "scratch", "logs", ".git", "*.pyc"))
    notes: list[str] = []
    if patches:
        path = dst / TARGET
        text = path.read_text(encoding="utf-8")
        for old, new in patches:
            if old not in text:
                notes.append(f"PATCH-MISS: {old[:60]!r}")
                continue
            text = text.replace(old, new, 1)
        path.write_text(text, encoding="utf-8")
    return dst, notes


def run_probe(tree: Path) -> tuple[int, str, list[str]]:
    import os
    env = dict(os.environ, T185_ROOT=str(tree), PYTHONUTF8="1")
    proc = subprocess.run([PY, "-W", "error::SyntaxWarning", str(PROBE)],
                          cwd=str(WS), capture_output=True, text=True, timeout=1800, env=env)
    out = (proc.stdout or "") + (proc.stderr or "")
    reds = [ln.strip() for ln in out.splitlines() if ln.strip().startswith("FAIL")]
    return proc.returncode, out, reds


def main() -> int:
    MUT.mkdir(parents=True, exist_ok=True)
    rows: list[tuple[str, int, int, int, list[str], list[str]]] = []
    for case, patches in MUTANTS.items():
        tree, notes = build(case, patches)
        rc, out, reds = run_probe(tree)
        m = re.search(r"PASS=(\d+) FAIL=(\d+)", out)
        p, f = (int(m.group(1)), int(m.group(2))) if m else (-1, -1)
        rows.append((case, rc, p, f, reds, notes))
        (MUT / f"{case}.out.txt").write_text(out, encoding="utf-8")
        print(f"{case:32s} rc={rc:3d} PASS={p:3d} FAIL={f:3d} "
              f"红={len(reds)} {' '.join(notes) if notes else ''}")
        for r in reds[:4]:
            print(f"    {r[:160]}")
    print()
    base = rows[0]
    print(f"control: PASS={base[2]} FAIL={base[3]}（要求 FAIL=0）")
    for case, rc, p, f, reds, notes in rows[1:]:
        print(f"{case:32s} 杀 {len(reds)} 条 {'✅' if reds else '❌ 未被杀'}"
              f"{' ' + ' '.join(notes) if notes else ''}")
    bad = [c for c, _, _, f, reds, _ in rows[1:] if not reds]
    print("未被杀手：" + (", ".join(bad) if bad else "（无）"))
    return 1 if (base[3] != 0 or bad) else 0


if __name__ == "__main__":
    raise SystemExit(main())
