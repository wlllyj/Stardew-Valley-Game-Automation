"""task-198 变异自检：把 brain/+tests/ 拷到临时目录，施加一条变异，跑定向用例，数杀了几个。

用法：python scratch/_t198_mutate.py
只读工作树；临时目录跑完即删。
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = [
    "tests.test_longrun.TestTask198SlotRelief",
    "tests.test_longrun.TestTask198InventoryDay",
    "tests.test_farmwork.TestTask198NoSlot",
]


def _copy() -> tempfile.TemporaryDirectory:
    tmp = tempfile.TemporaryDirectory()
    base = Path(tmp.name)
    shutil.copytree(ROOT / "brain", base / "brain")
    shutil.copytree(ROOT / "tests", base / "tests")
    return tmp


def _run(base: Path) -> tuple[int, int, str]:
    env = {"PYTHONUTF8": "1", "PYTHONPATH": str(base / "brain"),
           "PATH": str(Path(sys.executable).parent), "SYSTEMROOT": "C:\\Windows"}
    proc = subprocess.run([sys.executable, "-m", "unittest", *TESTS],
                          cwd=base, env=env, capture_output=True, text=True,
                          encoding="utf-8", errors="replace")
    out = (proc.stdout or "") + (proc.stderr or "")
    ran = 0
    for line in out.splitlines():
        if line.startswith("Ran "):
            try:
                ran = int(line.split()[1])
            except Exception:
                pass
    fails = sum(1 for line in out.splitlines()
                if line.startswith(("FAIL:", "ERROR:")))
    return ran, fails, out


MUTATIONS = [
    # ① 腾格回路整个失效（`_slot_relief` 永远不腾）⇒ 收不进来只能靠诚实收尾顶住
    ("m198a_no_relief",
     "brain/agentfarm/longrun.py",
     "        free_slots, need, status = self._bag_state(obs)\n"
     "        if status != \"ok\" or need <= 0:\n            return False",
     "        free_slots, need, status = self._bag_state(obs)\n"
     "        if True:\n            return False"),
    # ② day 级 failed 又把 no_slot 算成硬失败（回归 run A′ 的 no_hard_failures=false）
    ("m198b_no_slot_counts_as_hard_failure",
     "brain/agentfarm/longrun.py",
     'failed_any = [s for s in all_steps\n'
     '                      if s.failed and not getattr(s, "no_slot", False)]',
     "failed_any = [s for s in all_steps if s.failed]"),
    # ③ 守卫在背包满时继续拿熟作物当"还能干活"
    ("m198c_guard_claims_ripe_work_when_bag_full",
     "brain/agentfarm/longrun.py",
     "                if (tile_ready(tv) and t not in self.harvest_gave_up\n"
     "                        and not bag_blocked):",
     "                if (tile_ready(tv) and t not in self.harvest_gave_up):"),
    # ④ 每格配额又把 no_slot 当"这一格没做成"（吃配额 ⇒ 误封格）
    ("m198d_no_slot_consumes_quota",
     "brain/agentfarm/longrun.py",
     '            if getattr(s, "no_slot", False):\n'
     "                # 【task-198】背包满 = **全局**阻塞（不是这一格的属性，也不是\"没拿到结论\"）：",
     '            if False:\n'
     "                # 【task-198】背包满 = **全局**阻塞（不是这一格的属性，也不是\"没拿到结论\"）："),
    # ⑤ 低水位退回"0 格才腾"（deputy 预检的第二条病灶）
    ("m198e_low_water_waits_for_zero",
     "brain/agentfarm/longrun.py",
     "        need = 1 if (free_slots <= SLOT_RESERVE and ready > free_slots) else 0",
     "        need = 1 if (free_slots <= 0 and ready > free_slots) else 0"),
    # ⑥ 背包堵住时守卫退化成 `no_work`（= 假达标：verified 会被洗成 True）
    ("m198f_guard_falls_back_to_no_work",
     "brain/agentfarm/longrun.py",
     "            if self.inventory_blocked_today:\n"
     "                free_slots, _need, _status = self._bag_state(obs)\n"
     '                return True, "inventory_blocked", (',
     "            if False:\n"
     "                free_slots, _need, _status = self._bag_state(obs)\n"
     '                return True, "inventory_blocked", ('),
    # ⑦ `inventory_blocked` 被算成"达标收工"（假 VERIFIED 通道）
    ("m198g_inventory_blocked_counts_as_justified",
     "brain/agentfarm/longrun.py",
     '            "day_justified": is_justified_end(rep.ended_by, rep.ended_reason),',
     '            "day_justified": is_justified_end(rep.ended_by, rep.ended_reason)\n'
     '            or rep.ended_by == "inventory_blocked",'),
]


def main() -> int:
    tmp = _copy()
    base = Path(tmp.name)
    ran, fails, out = _run(base)
    print(f"基线：Ran {ran} / fails={fails}")
    if fails:
        print(out[-3000:])
    for name, rel, old, new in MUTATIONS:
        path = base / rel
        text = path.read_text(encoding="utf-8")
        if old not in text:
            print(f"{name}: 【没找到锚点】")
            continue
        path.write_text(text.replace(old, new, 1), encoding="utf-8")
        ran, fails, out = _run(base)
        print(f"{name}: Ran {ran} / 杀 {fails} 条")
        path.write_text(text, encoding="utf-8")
    tmp.cleanup()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
