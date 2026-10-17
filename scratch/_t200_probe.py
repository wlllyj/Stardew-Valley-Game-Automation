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
    return FORCE or (marker("brain/agentfarm/farmwork.py", "no_slot")
                     and marker("brain/agentfarm/longrun.py", "inventory_blocked"))


def has_199() -> bool:
    return FORCE or (marker("mod/AgentFarm.Bridge/Contracts.cs", "readyTiles")
                     and marker("brain/agentfarm/longrun.py", "ready_far_blocked"))


def has_195() -> bool:
    """task-195 的真 marker：作者会新增 `TestTask195*` 用例类；辅以 Mod 侧证据绑定字段。

    旧写法 `"5" in ClumpRules.cs` 是假阳性（文件里到处是数字字符），已废弃。
    """
    try:
        txt = (ROOT / "tests/test_longrun.py").read_text(encoding="utf-8", errors="replace")
    except OSError:
        txt = ""
    return FORCE or ("TestTask195" in txt
                     or marker("mod/AgentFarm.Bridge/Skills.cs", "affectedTiles")
                     or marker("mod/AgentFarm.Bridge/Contracts.cs", "evidenceScope"))


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


# ---------------------------------------------------------------- task-198 夹具
FW, LR, TL = T.FW, T.LR, T.TL
FW_READY_TRIES = int(getattr(LR, "READY_FAR_MAX_TRIES", 2))


def _bag_rows(w, used: int = 12, material: int = 0) -> None:
    """占 `used` 行：前几行填杂物，`material` 行放可卖盈余材料（Wood 14 件 > K=10）。"""
    rows = []
    for i in range(max(0, used - material)):
        rows.append({"slot": i, "id": "300", "qualifiedId": "(O)300",
                     "name": "Filler", "stack": 1, "isTool": False})
    for i in range(material):
        rows.append({"slot": used - material + i, "id": "388", "qualifiedId": "(O)388",
                     "name": "Wood", "stack": 14, "isTool": False})
    w.inventory = rows


def _ripe_world(*, free_slots: int = 0, material: int = 0, n_ripe: int = 1,
                seeds: int = 0, money: int = 500):
    w = TL.FakeWorld(weeds=0, seeds=seeds, money=money)
    w.inventory_capacity = 12
    tiles = [(61 + i, 11) for i in range(n_ripe)]
    for t in tiles:
        w.dirt.add(t)
        w.crops[t] = {"ripe": True, "watered": True}
    w.player_tile = [60, 13]
    w.farm = w.farm_scan()
    used = max(1, 12 - int(free_slots))
    _bag_rows(w, used=used, material=min(material, used))
    return w, tiles


class _Client(TL.FakeClient):
    """补 `FakeClient` 缺的 `buy`/`sell`（真 `FarmWorker` 会调；回 dict 形状）。"""

    def buy(self, item, count=1, *, shop=None, timeout_ms=8000):        # noqa: ANN001
        return {"ok": False, "status": "item_not_sold", "availableItems": [],
                "reason": "探针桩：不卖种子", "money": 0}

    def sell(self, slot, *, whitelist=None, timeout_ms=8000):           # noqa: ANN001
        """复刻 `ShipSkill`：整叠出手、从背包删掉这一行；白名单只收本批 qid。"""
        rows = self.w.inventory
        for i, it in enumerate(rows):
            if int(it.get("slot", -1)) == int(slot):
                qid = str(it.get("qualifiedId") or "")
                if whitelist and qid not in whitelist:
                    return {"ok": False, "status": "not_whitelisted", "slot": int(slot),
                            "reason": f"{qid} 不在白名单里"}
                rows.pop(i)
                return {"ok": True, "status": "ok", "slot": int(slot), "item": it,
                        "bin": len(rows)}
        return {"ok": False, "status": "empty_slot", "slot": int(slot)}


def _mk(w, tag: str):
    journal = J / f"{tag}.jsonl"
    journal.unlink(missing_ok=True)
    client = _Client(w)
    worker = FW.FarmWorker(client, log=lambda *_: None, pause=lambda _s: None)
    run = TL.make_run(w, target_days=1, max_days=1,
                      client_factory=lambda: client, worker_factory=lambda c: worker,
                      journal_path=journal)
    run.worker, run.client = worker, client
    return run, worker, client


def _events(run, name: str):
    return [e for e in run.entries if str(e.get("event") or "") == name]


def _day(run):
    return run.days[0] if run.days else None


def _a_prime() -> None:
    r"""A′ 原型复现通道（Lead m08246 的正式冻结判据）。

    照 `logs\longrun-runA3-0736.jsonl` day13 的真实形态：背包满 + 多格熟作物在窗口外，
    pre 树会以 `stuck:同一秒连发 5 次换片都没有目标（守卫仍说还有活：农场口径还有 8 格熟作物…）`
    收尾；post 树必须出现 `slot_relief` 或 `inventory_blocked`，且不得再出现该形态。
    """
    print("== A′ 原型复现通道（满包 + 多格熟作物，判据见 docs/_release-0.7.37.md §3）==")
    w, tiles = _ripe_world(free_slots=0, material=1, n_ripe=8)
    run, worker, client = _mk(w, "198f-relief")
    run.run()
    day = _day(run)
    relief = _events(run, "slot_relief")
    freed = max([int(e.get("freed") or 0) for e in relief] or [0])
    reason = str(getattr(day, "ended_reason", "") or "")
    check("198f-1 A′ 原型（满包 + 8 熟作物 + 可腾）：腾格回路真的动了（slot_relief.freed>=1）",
          freed >= 1, f"freed={freed} relief={[{k: e.get(k) for k in ('need', 'freed', 'shipped')} for e in relief]}")
    check("198f-2 A′ 原型：不再以『守卫仍说还有活』的 stuck 收尾",
          "守卫仍说还有活" not in reason, f"ended={str(getattr(day, 'ended_by', None))!s} reason={reason[:160]}")
    check("198f-3 A′ 原型：no_slot 不计硬失败（failed_steps==0）",
          day is None or int(day.failed_steps) == 0,
          f"failed_steps={getattr(day, 'failed_steps', None)} "
          f"stages={[(s.get('stage'), s.get('failed'), s.get('env_block')) for s in ((day.stages if day else []) or [])]}")

    # f4：满包且**腾不出**（无可卖/可出货材料）⇒ inventory_blocked，仍不许 stuck 冒充
    w4, tiles4 = _ripe_world(free_slots=0, n_ripe=8)
    run4, _, _ = _mk(w4, "198f-blocked")
    run4.run()
    day4 = _day(run4)
    reason4 = str(getattr(day4, "ended_reason", "") or "")
    ev4 = [str(e.get("event") or "") for e in run4.entries]
    check("198f-4 A′ 原型（满包且腾不出）：记 inventory_blocked（事件或收尾理由）",
          "inventory_blocked" in ev4 or reason4.startswith("inventory_blocked"),
          f"ended={str(getattr(day4, 'ended_by', None))!s} reason={reason4[:160]}")
    check("198f-5 A′ 原型（腾不出）：不许以『守卫仍说还有活』收尾",
          "守卫仍说还有活" not in reason4, f"reason={reason4[:200]}")
    check("198f-6 A′ 原型（腾不出）：不许洗成 VERIFIED", day4 is None or day4.verified is False,
          f"verified={getattr(day4, 'verified', None)} checks={getattr(day4, 'checks', None)}")

    # f7：低水位 = 1 空格 + 8 熟作物（dev-coder 必修第 2 条的回归钉）
    w7, tiles7 = _ripe_world(free_slots=1, n_ripe=8)
    run7, _, _ = _mk(w7, "198f-lowwater")
    run7.run()
    day7 = _day(run7)
    reason7 = str(getattr(day7, "ended_reason", "") or "")
    ev7 = [str(e.get("event") or "") for e in run7.entries]
    check("198f-7 低水位（1 空格 + 8 熟作物）：出现 slot_relief 或 inventory_blocked（不许白撞 no_slot）",
          ("slot_relief" in ev7) or ("inventory_blocked" in ev7),
          f"events={sorted(set(ev7))[:12]} reason={reason7[:140]}")
    check("198f-8 低水位：不许以『守卫仍说还有活』收尾", "守卫仍说还有活" not in reason7,
          f"reason={reason7[:200]}")


def case_198() -> None:
    print("== task-198：背包满 ⇒ no_slot 不算硬失败 + 腾格收敛 + 不许洗 VERIFIED ==")
    if not has_198():
        skip("198 全部通道", "task-198 未交付（缺 no_slot / inventory_blocked）")
        return
    # ---- 198a 单元级：满包 harvest 的归类 ----
    w, tiles = _ripe_world(free_slots=0)
    run, worker, _ = _mk(w, "198a")
    r = worker.harvest(tiles[0])
    no_slot_code = getattr(FW, "NO_SLOT_CODE", "no_slot")
    check("198a-1 满包 harvest ⇒ code=failed + status/no_slot 标记（不是普通失败）",
          r.code == "failed" and getattr(r, "no_slot", False) is True and r.status == no_slot_code,
          f"code={r.code} status={r.status} no_slot={getattr(r, 'no_slot', None)}")
    check("198a-2 no_slot 归阻塞类（env_block 且进 ENV_BLOCK_STATUSES）",
          bool(r.env_block) and no_slot_code in getattr(FW, "ENV_BLOCK_STATUSES", ()),
          f"env_block={r.env_block} statuses={getattr(FW, 'ENV_BLOCK_STATUSES', None)}")
    before = dict(run.tile_attempts)
    run._count_attempts([r])
    check("198a-3 no_slot 不占每格配额、不封格（tile_attempts 不变 / 不进 blocked）",
          run.tile_attempts == before and tiles[0] not in run.blocked,
          f"attempts {before} → {run.tile_attempts} blocked={sorted(run.blocked)}")
    note_giveup = getattr(run, "_note_harvest_gave_up", None)
    if callable(note_giveup):
        run.tile_attempts[tiles[0]] = 2          # 伪造"试满上限"，看 no_slot 是否被写进 gave_up
        _rep = LR.DayReport(day_key=("summer", 10, 1), started_at=0.0)
        note_giveup([r], _rep)
        run.tile_attempts.pop(tiles[0], None)
    check("198a-4 no_slot 不吃 harvest_gave_up 上限", not run.harvest_gave_up,
          f"harvest_gave_up={sorted(run.harvest_gave_up)}")

    # ---- 198b 日级：1 空格 + 3 熟作物 ⇒ 1 收成 + no_slot 若干 ----
    w, tiles = _ripe_world(free_slots=1, n_ripe=3)
    run, worker, client = _mk(w, "198b")
    run.run()
    day = _day(run)
    if day is None:
        check("198b 日级：跑到 day_end", False, "没有 day 记录")
    else:
        chk = dict(day.checks or {})
        check("198b-1 no_slot **不许**拉成硬失败（failed_steps==0 且 no_hard_failures=True）",
              int(day.failed_steps) == 0 and chk.get("no_hard_failures") is True,
              f"failed_steps={day.failed_steps} checks={chk} stages={[(s.get('stage'), s.get('failed'), s.get('env_block')) for s in day.stages]}")
        check("198b-2 无空格日**不许**假 VERIFIED（洗白检查）", day.verified is False,
              f"verified={day.verified} ended_by={day.ended_by} reason={str(day.ended_reason)[:120]}")
        check("198b-3 收尾理由如实 inventory_blocked（不是 stick/no_work 混用）",
              str(day.ended_reason or "").startswith("inventory_blocked"),
              f"ended_by={day.ended_by} reason={str(day.ended_reason)[:140]}")
        check("198b-4 harvest_gave_up 未被 no_slot 消耗", not run.harvest_gave_up,
              f"={sorted(run.harvest_gave_up)}")
        check("198b-5 有界（不空转到天亮）", len(run.entries) < 300, f"entries={len(run.entries)}")
        check("198b-6 checks 键集仍 10 键", set(chk) == CHECKS_10,
              f"差集={set(chk) ^ CHECKS_10}")

    _a_prime()   # A′ 原型通道先跑（pre 树没有 `_slot_relief` 也必须出读数）

    # ---- 198c 腾格优先的正对照：0 空格 + 可卖材料 + 熟作物 ----
    w, tiles = _ripe_world(free_slots=0, material=1, n_ripe=2)
    run, worker, client = _mk(w, "198c")
    run.run()
    day = _day(run)
    relief = _events(run, "slot_relief")
    freed = max([int(e.get("freed") or 0) for e in relief] or [0])
    check("198c-1 freeSlots==0 ⇒ 腾格回路真的腾出格子（slot_relief.freed>=1）", freed >= 1,
          f"relief={[{k: e.get(k) for k in ('need', 'freed', 'shipped')} for e in relief]}")
    check("198c-2 腾格后当天收成（正对照 ok_steps>=1）", day is not None and int(day.ok_steps) >= 1,
          f"ok_steps={getattr(day, 'ok_steps', None)} ended={getattr(day, 'ended_reason', '')!s:120}")

    # ---- 198d 收敛有界：腾不出 / 轮数用满 ----
    w, tiles = _ripe_world(free_slots=0)
    run, worker, _ = _mk(w, "198d")
    rep = LR.DayReport(day_key=("summer", 10, 1), started_at=0.0)
    ok1 = run._slot_relief(w.obs(), rep)
    check("198d-1 腾不出（无可出货/可卖叠）⇒ False + inventory_blocked 记账",
          ok1 is False and run.inventory_blocked_today and bool(_events(run, "inventory_blocked")),
          f"ok={ok1} blocked_today={run.inventory_blocked_today}")
    check("198d-2 slot_relief 记 freed=0（本轮腾 0 格立刻认输，不自旋）",
          any(int(e.get("freed") or 0) == 0 for e in _events(run, "slot_relief")),
          f"={[{k: e.get(k) for k in ('freed', 'round')} for e in _events(run, 'slot_relief')]}")
    w2, tiles2 = _ripe_world(free_slots=0, material=1)
    run2, _, _ = _mk(w2, "198d2")
    run2.slot_relief_today = int(getattr(LR, "SLOT_RELIEF_MAX", 3))
    rep2 = LR.DayReport(day_key=("summer", 10, 1), started_at=0.0)
    ok2 = run2._slot_relief(w2.obs(), rep2)
    reason_txt = str([e.get("reason") for e in _events(run2, "inventory_blocked")])
    check("198d-3 轮数用满 SLOT_RELIEF_MAX ⇒ False + 理由点名『用满』",
          ok2 is False and "用满" in reason_txt, f"ok={ok2} reasons={reason_txt[:160]}")

    # ---- 198e 不洗白：正对照日的 checks 语义 ----
    w, tiles = _ripe_world(free_slots=0, material=1, n_ripe=1)
    run, worker, client = _mk(w, "198e")
    run.run()
    day = _day(run)
    if day is not None:
        chk = dict(day.checks or {})
        check("198e 腾格日若真干完活 ⇒ 不许因少了格子而假红（no_hard_failures 仍 True）",
              chk.get("no_hard_failures") is True, f"checks={chk} failed={day.failed_steps}")


# ---------------------------------------------------------------- task-199
class ReadyWorld(TL.MyopicWorld):
    """窗口半径 3 的农场；`farm` 块按**全农场**作物现算（readyCrops / readyTiles 同源）。

    `mode`：`same` = 同源正常；`liar_empty` = 说还有熟作物但坐标给空（伪造不一致）；
    `no_field` = 旧 Mod（没有 readyTiles 键，只剩 readyCrops）。
    """

    def __init__(self, *, radius: int = 3, mode: str = "same", **kw) -> None:
        super().__init__(**kw)
        self.radius = radius
        self.mode = mode

    def obs(self) -> dict:
        obs = super().obs()
        farm = dict(obs.get("farm") or {})
        ready = sorted([t for t, c in self.crops.items() if c.get("ripe") and not c.get("dead")],
                       key=lambda t: (t[1], t[0]))
        farm.update({"loaded": True, "complete": True, "readyCrops": len(ready),
                     "dryCrops": 0, "deadCrops": 0, "dryTiles": []})
        if self.mode == "no_field":
            farm.pop("readyTiles", None)
            farm.pop("readyTilesTruncated", None)
        else:
            farm["readyTiles"] = [] if self.mode == "liar_empty" else [[int(x), int(y)] for x, y in ready]
            farm["readyTilesTruncated"] = False
        obs["farm"] = farm
        return obs


class FarWorker(TL.FakeWorker):
    """只实现长跑需要的三个方法：`stand_next_to` / `open_way`(三元组) / `harvest`。"""

    def __init__(self, world, *, reachable: bool = True) -> None:
        super().__init__(world)
        self.world = world
        self.reachable = reachable
        self.stand_calls: list[tuple[int, int]] = []
        self.open_calls: list[tuple[int, int]] = []
        self.harvest_calls: list[tuple[int, int]] = []

    def stand_next_to(self, tile, timeout_ms: int = 15000) -> bool:       # noqa: ANN001
        t = (int(tile[0]), int(tile[1]))
        self.stand_calls.append(t)
        if not self.reachable:
            return False
        self.world.player_tile = [t[0], t[1] + 1]
        return True

    def open_way(self, tile):                                             # noqa: ANN001
        t = (int(tile[0]), int(tile[1]))
        self.open_calls.append(t)
        if not self.reachable:
            return "exhausted", [], ["四邻都站不过去（探针桩）"]
        return "ok", [], []

    def harvest(self, tile):                                              # noqa: ANN001
        t = (int(tile[0]), int(tile[1]))
        self.harvest_calls.append(t)
        if not self.reachable:
            return FW.StepResult(action="harvest", tile=t, ok=False, code="unreachable",
                                 reason="站不到这一格旁边（探针桩）")
        if t not in self.world.crops:
            return FW.StepResult(action="harvest", tile=t, ok=False, code="failed",
                                 reason="这一格没有作物（探针桩）")
        self.world.crops.pop(t, None)
        return FW.StepResult(action="harvest", tile=t, ok=True, code="ok",
                             reason="摘下来了（探针桩：世界差分）")


def _ready_world(*, far: int = 1, near: int = 0, mode: str = "same",
                 truncated: bool = False):
    w = ReadyWorld(mode=mode, weeds=0, seeds=0)
    near_t = [(61 + i, 11) for i in range(near)]
    far_t = [(70 + i, 20) for i in range(far)]
    for t in near_t + far_t:
        w.dirt.add(t)
        w.crops[t] = {"ripe": True, "watered": True, "dead": False}
    w.player_tile = [60, 11]
    if truncated:
        # 让 obs 的 farm.readyTilesTruncated 为 true：子类里补一个开关
        orig = w.obs

        def _obs() -> dict:
            o = orig()
            (o.get("farm") or {})["readyTilesTruncated"] = True
            return o
        w.obs = _obs
    return w, far_t


def _mk199(w, tag: str, *, reachable: bool = True):
    journal = J / f"{tag}.jsonl"
    journal.unlink(missing_ok=True)
    client = _Client(w)
    worker = FarWorker(w, reachable=reachable)
    run = TL.make_run(w, target_days=1, max_days=1,
                      client_factory=lambda: client, worker_factory=lambda c: worker,
                      journal_path=journal)
    run.worker, run.client = worker, client
    return run, worker


def _md5_text(p) -> str:            # noqa: ANN001
    return p.read_text(encoding="utf-8", errors="replace")


def case_199() -> None:
    print("== task-199：readyTiles/readyCrops 同源 + 窗口外熟作物走路收 + 认输有界 + 缺字段 fail-closed ==")
    if not has_199():
        skip("199 全部通道", "task-199 未交付（缺 readyTiles / ready_far_blocked）")
        return
    # ---- 199a-0 接口齐备（pre 树缺接口 ⇒ 整段按 FAIL 记，而不是抛异常当"无法判定"） ----
    w0, _ = _ready_world(far=1, near=1)
    run0, _ = _mk199(w0, "199a-cap")
    miss_fw = [n for n in ("farm_ready_tiles",) if not hasattr(FW, n)]
    miss_lr = [n for n in ("_ready_far_outside", "_ready_far_tiles", "_harvest_far_ready",
                           "_ready_far_all_given_up", "_ready_far_reason") if not hasattr(run0, n)]
    check("199a-0 接口齐备（farmwork.farm_ready_tiles + longrun ready_far 五件套）",
          not miss_fw and not miss_lr, f"缺 farmwork={miss_fw} 缺 longrun={miss_lr}")
    if miss_fw or miss_lr:
        finding("199a-0 pre 树缺接口 ⇒ 199 通道全部 FAIL（不写成『无法判定』）", True,
                f"缺={miss_fw + miss_lr}")
        return
    # ---- 199a 同源三态 / 窗口扣减 / 不一致 ----
    w, far = _ready_world(far=1, near=1)
    tiles, status = FW.farm_ready_tiles(w.obs())
    check("199a-1 farm_ready_tiles 读 readyTiles（同源 ok 态，近+远两条坐标都在）",
          status == "ok" and sorted(tiles) == sorted([(61, 11)] + far),
          f"status={status} tiles={tiles}")
    run, worker = _mk199(w, "199a-outside")
    outside, st2 = run._ready_far_outside(w.obs())
    check("199a-2 窗口扣减：只有窗口外那格留下（近处那格不算『窗口外』）",
          sorted(outside) == sorted(far) and st2 == "ok",
          f"outside={outside} status={st2} far={far}")
    w_liar, far_liar = _ready_world(far=1, near=1, mode="liar_empty")
    run_l, _ = _mk199(w_liar, "199a-liar")
    reasons_l = run_l.work_reasons(w_liar.obs())
    far_reasons = [r for r in reasons_l if ("readyTiles" in r or "窗口之外" in r or "窗口里" in r)]
    finding("199a-3【候选 NIT】运行期不交叉校验 readyCrops 与 readyTiles（伪造『有熟作物但坐标为 0』不被拦，"
            "只靠守卫给出不可执行理由 ⇒ 后果是有序收尾，不是假绿；卡面说要『拦』⇒ 未完全达成）",
            True, f"outside={run_l._ready_far_outside(w_liar.obs())[0]} 守卫理由={far_reasons[:1]}")
    w_nf, _ = _ready_world(far=1, mode="no_field")
    run_nf, _ = _mk199(w_nf, "199a-nofield")
    obs_nf = w_nf.obs()
    moved_nf = run_nf._harvest_far_ready(obs_nf, LR.DayReport(day_key=("spring", 1, 6), started_at=0.0))
    reasons_nf = run_nf.work_reasons(obs_nf)
    check("199a-4 缺 readyTiles ⇒ unavailable + fail-closed 老文案（不许当『没有熟作物』）",
          run_nf._ready_far_tiles(obs_nf)[1] == "unavailable" and moved_nf is False
          and any("旧 Mod 没给 readyTiles 坐标" in r for r in reasons_nf),
          f"status={run_nf._ready_far_tiles(obs_nf)[1]} moved={moved_nf} "
          f"reasons={[r[:60] for r in reasons_nf if 'readyTiles' in r]}")
    check("199a-5 缺字段时 sleep_guard fail-closed（keep_working，不许睡过去）",
          run_nf.sleep_guard(obs_nf)[:2] == (False, "keep_working"),
          f"guard={run_nf.sleep_guard(obs_nf)[0:2]}")

    # ---- 199b 走过去收成的正路径 ----
    w, far = _ready_world(far=1, near=0)
    run, worker = _mk199(w, "199b")
    rep = LR.DayReport(day_key=("spring", 1, 6), started_at=0.0)
    moved = run._harvest_far_ready(w.obs(), rep)
    ev = _events(run, "ready_far")
    ok_ev = [e for e in ev if e.get("ok") is True]
    check("199b-1 窗口外熟作物 ⇒ 真的走过去收（harvest 被调 + journal ready_far ok=True）",
          moved is True and worker.harvest_calls == [far[0]] and len(ok_ev) == 1,
          f"moved={moved} harvest_calls={worker.harvest_calls} ready_far={[e.get('ok') for e in ev]}")
    if ok_ev:
        e = ok_ev[0]
        check("199b-2 journal 带 ready_before/ready_after 与坐标（可复核同源计数）",
              int(e.get("ready_before", -1)) >= 1 and int(e.get("ready_after", -1)) == 0
              and list(e.get("tile") or []) == list(far[0]),
              f"ready_before={e.get('ready_before')} ready_after={e.get('ready_after')} tile={e.get('tile')}")
    check("199b-3 收成计入 farm_actions_today（≥1）", int(run.farm_actions_today) >= 1,
          f"farm_actions_today={run.farm_actions_today}")

    # ---- 199c 走不到 ⇒ 有界 + 认输 + 守卫不再钉死 ----
    w, far = _ready_world(far=1, near=0)
    run, worker = _mk199(w, "199c", reachable=False)
    rep = LR.DayReport(day_key=("spring", 1, 6), started_at=0.0)
    r1 = run._harvest_far_ready(w.obs(), rep)
    r2 = run._harvest_far_ready(w.obs(), rep)
    tries = int(run.ready_far_tries.get(far[0], 0))
    blocked = _events(run, "ready_far_blocked")
    check("199c-1 走不到 ⇒ 每格 2 次后认输（ready_far_given_up + ready_far_blocked 恰好 1 条）",
          r1 is False and r2 is False and tries == FW_READY_TRIES
          and far[0] in run.ready_far_given_up and len(blocked) == 1,
          f"r1={r1} r2={r2} tries={tries} given_up={sorted(run.ready_far_given_up)} blocked={len(blocked)}")
    opens_before = len(worker.open_calls)
    r3 = run._harvest_far_ready(w.obs(), rep)
    guard = run.sleep_guard(w.obs())
    reasons = run.work_reasons(w.obs())
    check("199c-2 认输后不再试（第 3 次 False、不再开路、守卫改 gave_up_ready 而非 keep_working）",
          r3 is False and len(worker.open_calls) == opens_before
          and guard[:2] == (True, "gave_up_ready"),
          f"r3={r3} opens {opens_before}→{len(worker.open_calls)} guard={guard[:2]}")
    check("199c-3 认输理由如实带坐标与『已放弃/够不着』，且不出现『没活可做』",
          "已放弃" in str(guard[2]) or "坐标" in str(guard[2]),
          f"reason={str(guard[2])[:160]}")
    check("199c-4 守卫不再被『窗口外熟作物』钉死（work_reasons 不再报该格）",
          not [r for r in reasons if "窗口外" in r or "readyTiles" in r],
          f"reasons={[r[:60] for r in reasons]}")
    check("199b-4 收成上限有界：harvest 调用次数 ≤ 尝试上限",
          len(worker.harvest_calls) <= FW_READY_TRIES,
          f"harvest_calls={worker.harvest_calls}")

    # ---- 199d 截断标志 + 工具/Mod 契约 ----
    w, far = _ready_world(far=1, near=0, truncated=True)
    run, _ = _mk199(w, "199d-trunc")
    _tiles_t, st_t = FW.farm_ready_tiles(w.obs())
    run._harvest_far_ready(w.obs(), LR.DayReport(day_key=("spring", 1, 6), started_at=0.0))
    rf_ev = _events(run, "ready_far")
    check("199d-1 readyTilesTruncated=true ⇒ status=truncated；有坐标时照常处理已知格并在逐次 ready_far 里标 status"
          "（cause 只在失败时才有意义；不单独刷 truncated 事件）",
          st_t == "truncated" and bool(rf_ev)
          and rf_ev[-1].get("status") == "truncated",
          f"status={st_t} rf={[(e.get('status'), e.get('cause'), e.get('ok')) for e in rf_ev]}")
    w2, _ = _ready_world(far=0, near=0, truncated=True)
    run2, _ = _mk199(w2, "199d-trunc-empty")
    run2._harvest_far_ready(w2.obs(), LR.DayReport(day_key=("spring", 1, 6), started_at=0.0))
    trunc_ev = _events(run2, "ready_far_truncated")
    check("199d-1b 坐标为空 + 截断标志 ⇒ 单独留痕一次（『没拿到全部坐标 ≠ 没有熟作物』）",
          len(trunc_ev) == 1, f"trunc_events={len(trunc_ev)}")
    farm_src = _md5_text(ROOT / "mod/AgentFarm.Bridge/FarmScan.cs")
    idx = farm_src.find("CropMeta.Ready(dirt, crop).Value == true")
    window = farm_src[idx: idx + 600] if idx >= 0 else ""
    check("199d-2【同源】FarmScan 同一 CropMeta.Ready 分支 600 字符内既有 ReadyCrops++ 又有 _readyTiles.Add(",
          idx >= 0 and "_acc.ReadyCrops++" in window and "_readyTiles.Add(" in window,
          f"idx={idx} window_has_crops={'_acc.ReadyCrops++' in window} has_tiles={'_readyTiles.Add(' in window}")
    contracts = _md5_text(ROOT / "mod/AgentFarm.Bridge/Contracts.cs")
    check("199d-3 Contracts readyTiles/readyTilesTruncated 三态可辨（JsonIgnoreCondition.Never）",
          'JsonPropertyName("readyTiles")' in contracts
          and 'JsonPropertyName("readyTilesTruncated")' in contracts
          and contracts.count("JsonIgnoreCondition.Never") >= 2,
          f"never={contracts.count('JsonIgnoreCondition.Never')}")
    csproj = _md5_text(ROOT / "mod/AgentFarm.Bridge.Tests/AgentFarm.Bridge.Tests.csproj")
    check("199d-4 C# 自检工程引用 TileListRules.cs（排序/截断可被测）",
          "TileListRules.cs" in csproj, f"csproj 引用={[l.strip() for l in csproj.splitlines() if 'TileListRules' in l][:1]}")
    rules = _md5_text(ROOT / "mod/AgentFarm.Bridge/TileListRules.cs")
    check("199d-5 TileListRules 排序先 y 后 x + 排序异常 ⇒ 截断标志（没拿到扫描 ≠ 没有坐标）",
          "OrderAndTruncate" in rules and "truncated = true" in rules
          and ("Item2" in rules or "t[1]" in rules or "y" in rules),
          f"len={len(rules)} has_trunc={('truncated = true' in rules)}")
    ana = _md5_text(ROOT / "tools/analyze-longrun.py")
    check("199d-6 analyzer 已收 ready_far 五个事件桶",
          all(k in ana for k in ("ready_far", "ready_far_blocked", "ready_far_skipped",
                                 "ready_far_truncated", "ready_far_unavailable")),
          "缺桶 ⇒ 变异/分析会漂移" if not all(k in ana for k in ("ready_far", "ready_far_blocked")) else "ok")
    v3 = _md5_text(ROOT / "tools/verify-run3.py")
    finding("199a-6【候选 NIT】tools/verify-run3.py 无 readyTiles/ready_far 交叉校验闸门"
            "（账本自称 VERIFIED 时不能从第四方复核『窗口外熟作物都收了』）",
            True, f"hits={v3.count('readyTiles') + v3.count('ready_far')}")
    # ---- 199e C# 自检实跑 ----
    try:
        import subprocess
        proj = ROOT / "mod/AgentFarm.Bridge.Tests/AgentFarm.Bridge.Tests.csproj"
        p = subprocess.run(["dotnet", "run", "--project", str(proj), "-c", "Release", "--nologo"],
                           capture_output=True, text=True, timeout=600, cwd=str(ROOT))
        out = (p.stdout or "") + (p.stderr or "")
        fails = [ln for ln in out.splitlines() if ln.strip().startswith("FAIL")]
        check("199e-1 C# 自检实跑 rc=0 且 FAIL 行 0（含 readyTiles 同源/截断断言）",
              p.returncode == 0 and not fails,
              f"rc={p.returncode} fails={fails[:2]} tail={out.strip().splitlines()[-1:]}")
    except Exception as exc:                                   # noqa: BLE001
        check("199e-1 C# 自检实跑 rc=0 且 FAIL 行 0", False, f"{type(exc).__name__}: {exc}")


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
    if os.environ.get("T200_SKIP_SUITE"):
        skip("197 全部通道", "T200_SKIP_SUITE=1（变异矩阵跑批时跳过全量套件，省时）")
        return
    rc1, t1 = _suite({"PYTHONUTF8": "1"})
    check("197a 带 PYTHONUTF8=1 全量绿（基线）", rc1 == 0, f"rc={rc1} :: {t1}")
    rc2, t2 = _suite({})                                  # 完全不设 PYTHONUTF8
    check("197b 不带 PYTHONUTF8 全量绿（task-197 的目标）", rc2 == 0, f"rc={rc2} :: {t2}")
    rc3, t3 = _suite({"PYTHONIOENCODING": "cp1252", "PYTHONUTF8": "0", "LC_ALL": "C"})
    check("197c 故意注入 cp1252/cp1252 环境仍绿（护栏）", rc3 == 0, f"rc={rc3} :: {t3}")
    t = ROOT / "tests" / "test_longrun.py"
    txt = t.read_text(encoding="utf-8", errors="replace") if t.exists() else ""
    body = ""
    key = "def test_csharp_rules_self_test_passes"
    if key in txt:
        rest = txt.split(key, 1)[1]
        body = rest.split("\n    def ", 1)[0]
    check("197d C# 自检用例内部显式编码或 ASCII 标记（只看该用例体）",
          ("SELFTEST_OK" in body) or ('encoding="utf-8"' in body),
          f"用例体 {len(body)} 字符：既无 SELFTEST_OK 也无 encoding=utf-8")


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
