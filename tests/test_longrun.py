# -*- coding: utf-8 -*-
"""长跑控制器（`brain\\agentfarm\\longrun.py`）的离线单元测试。

原则与前几份一样：**不连游戏、不联网、不睡觉** —— 假桥 + 假执行层 + 假时钟。
而且这里更进一步：`FakeWorld` 是一个**真会变**的微型农场（清障/锄地/播种/浇水/买种子/
补水/睡觉都会改世界，观测也真的反映变化），所以长跑控制器能被端到端地跑完一整天甚至三天，
断言的正是"世界有没有真的被改"。

覆盖点（对应"无人值守 3 天"最怕的几件事）：
  1. 决策的**输入必须限定在作业区**（否则永远停在清障）—— `plot_observe` / `_plot_brief`；
  2. 作物格在 `tiles[]` 里 kind 也是 dirt，**不能把作物算两遍**（否则 `unprepared` 提前归零 → stuck）；
  3. "没种子又买不起"时**不许再锄新地**（纯烧体力），而且守卫与策略必须同口径；
  4. **没事就睡**要被否决（用户 2026-10-11 的明确要求）；
  5. 一整天只有在"我们主动睡 + 0 硬失败 + 作物全浇过"时才算 VERIFIED，被系统 pass-out 不算；
  6. 连续 N 天达标才返回 0；起不来返回 2；watchdog 判 STOP 时落事故报告并停。

运行：`python -m unittest discover -s tests -v`
"""

from __future__ import annotations

import json
import sys
import tempfile
import time
import unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "brain"))

from agentfarm.bridge import MOD_VERSION_EXPECTED  # noqa: E402
from agentfarm.farmwork import (  # noqa: E402
    FarmWorker, STAGE_ACTION, StepResult, StageResult, seed_items,
)
from agentfarm.longrun import (  # noqa: E402
    DEFAULT_LLM_MAX_TOKENS, MAX_TILE_ATTEMPTS, DayReport, LongRun, _till_blocked_by, plot_observe,
)
from agentfarm.planner import BoundaryPlanner, TaskIntent, deterministic_plan  # noqa: E402

SEED_ID = "472"
SEED_NAME = "Parsnip Seeds"


# --------------------------------------------------------------------------- 假世界
class FakeWorld:
    """25 格微型农场（60..64 × 10..14）：技能真的改它，`obs()` 真的反映它。"""

    STAMINA_COST = {"clear": 2.0, "till": 5.0, "plant": 1.0, "water": 1.0, "harvest": 1.0}

    def __init__(self, *, seeds: int = 10, money: int = 500, weeds: int = 4,
                 water_left: int = 40, stamina: float = 270.0, scythe: bool = False) -> None:
        self.year, self.season, self.day, self.time_of_day = 1, "spring", 6, 600
        self.stamina, self.max_stamina = stamina, 270.0
        self.money = money
        self.water_left = water_left
        self.tillable = {(60 + x, 10 + y) for x in range(5) for y in range(5)}
        self.blockers: dict[tuple[int, int], str] = {}
        for t in sorted(self.tillable)[:weeds]:
            self.blockers[t] = "weed"
        self.dirt: set[tuple[int, int]] = set()
        self.crops: dict[tuple[int, int], dict[str, bool]] = {}
        self.player_tile = [62, 14]
        self.is_in_bed = True
        self.seq = 1
        self.sleeps = 0
        self.refills = 0
        self.buys: list[int] = []
        # 睡前那一刻"还有几格没浇" —— 跨日会把 watered 全部清零（世界语义），
        # 所以"这天有没有浇完"只能在睡前问，事后问必然为假。
        self.unwatered_at_sleep: list[int] = []
        # task-4：`use_tool` 的计数与"白挥"集合（真机 run1：镰刀在背包里、挥了世界不变）。
        self.swings: dict[tuple[int, int], int] = {}
        self.stuck: set[tuple[int, int]] = set()
        self.scythe = scythe
        self.inventory = [
            {"slot": 0, "id": "Axe", "qualifiedId": "(T)Axe", "name": "Axe", "stack": 1, "isTool": True},
            {"slot": 1, "id": "Hoe", "qualifiedId": "(T)Hoe", "name": "Hoe", "stack": 1, "isTool": True},
            {"slot": 2, "id": "WateringCan", "qualifiedId": "(T)WateringCan",
             "name": "Watering Can", "stack": 1, "isTool": True},
            {"slot": 5, "id": SEED_ID, "qualifiedId": f"(O){SEED_ID}",
             "name": SEED_NAME, "stack": seeds, "isTool": False},
        ]
        if scythe:
            # 真机快照口径（`logs\\observe-farm-sample.json`）：镰刀 id "47" 在背包 slot4。
            self.inventory.insert(3, {"slot": 4, "id": "47", "qualifiedId": "(W)47",
                                      "name": "Scythe", "stack": 1, "isTool": True})

    # ---- 观测 ----
    def obs(self) -> dict:
        tiles: list[dict] = []
        for t, kind in sorted(self.blockers.items()):
            tiles.append({"tile": list(t), "kind": kind, "standable": True, "actionable": True})
        for t in sorted(self.dirt):
            tv: dict = {"tile": list(t), "kind": "dirt", "feature": "HoeDirt",
                        "standable": True, "actionable": True}
            c = self.crops.get(t)
            if c:
                tv.update({"crop": "24", "ripe": bool(c["ripe"]), "watered": bool(c["watered"]),
                           "plantable": False})
            else:
                tv.update({"plantable": True, "watered": False})
            tiles.append(tv)
        free = sorted(self.tillable - self.dirt - set(self.blockers))
        return {
            "ok": True, "status": "ok", "schema": "agentfarm-world/6",
            "worldSeq": self.seq, "hasSaveLoaded": True,
            "clock": {"year": self.year, "season": self.season, "day": self.day,
                      "timeOfDay": self.time_of_day, "weather": "sunny", "weatherOnFarm": "sunny"},
            "player": {"name": "测试员", "location": "Farm", "tile": list(self.player_tile), "facing": 2,
                       "stamina": self.stamina, "maxStamina": self.max_stamina, "money": self.money,
                       "isInBed": self.is_in_bed, "inventory": [dict(i) for i in self.inventory],
                       "wateringCan": {"present": True, "waterLeft": self.water_left,
                                       "max": 40, "bottomless": False, "upgradeLevel": 0}},
            "location": {"name": "Farm", "isOutdoorFarm": True, "tiles": tiles, "tilesTruncated": False,
                         "tillable": [list(t) for t in free], "refillTiles": [[70, 10], [70, 11]],
                         "refillTilesTruncated": False, "furniture": [], "doors": []},
            "ui": {"isModal": False, "eventUp": False},
            "liveness": {"worldAdvancing": True, "secondsSinceClockMoved": 1.0},
        }

    # ---- 技能（真的改世界）----
    def spend(self, action: str) -> None:
        self.stamina -= self.STAMINA_COST[action]

    def clear(self, tile):
        kind = self.blockers.get(tile)
        if kind is None:
            return StepResult("clear", tile, code="already", reason="本来就没障碍")
        del self.blockers[tile]
        self.spend("clear")
        return StepResult("clear", tile, ok=True, reason=f"清掉 {kind}")

    def use_tool(self, tile, tool=None):
        """`use_tool` 的假世界版（与 Mod 同口径：**成功=这一格真的变了**，回执不算数）。

        `stuck` 里的格子模拟真机 run1 的镰刀白挥：回执 `status="tool_ineffective"`、
        世界一动不动。`swings` 记每格被挥了几次 —— task-4 的验收证据就在这里。
        """
        t = tuple(tile)
        self.swings[t] = self.swings.get(t, 0) + 1
        if t in self.stuck:
            return {"ok": True, "status": "tool_ineffective", "reason": f"工具对 {t} 无效"}
        if self.blockers.pop(t, None) is None:
            return {"ok": True, "status": "ok", "reason": "挥了，但这格本来就没东西"}
        self.spend("clear")
        return {"ok": True, "status": "ok", "reason": "清掉"}

    def till(self, tile):
        if tile in self.dirt:
            return StepResult("till", tile, code="already", reason="已经是耕地")
        if tile not in self.tillable or tile in self.blockers:
            return StepResult("till", tile, code="skipped", reason="这格不能锄")
        self.dirt.add(tile)
        self.spend("till")
        return StepResult("till", tile, ok=True, reason="锄成耕地")

    def plant(self, tile):
        if self.crops.get(tile):
            return StepResult("plant", tile, code="already", reason="已经有作物")
        slot = self._seed_slot()
        if slot is None:
            return StepResult("plant", tile, code="no_seed", reason=f"没种子了（item {SEED_ID} 堆叠 0）")
        slot["stack"] -= 1
        self.crops[tile] = {"watered": False, "ripe": False}
        self.spend("plant")
        return StepResult("plant", tile, ok=True, reason="种下")

    def water(self, tile):
        c = self.crops.get(tile)
        if c is None:
            return StepResult("water", tile, code="skipped", reason="这格没作物")
        if c["watered"]:
            return StepResult("water", tile, code="already", reason="已经浇过")
        if self.water_left <= 0:
            return StepResult("water", tile, code="need_refill", reason="水壶空了（0），得先去补水")
        c["watered"] = True
        self.water_left -= 1
        self.spend("water")
        return StepResult("water", tile, ok=True, reason="浇过")

    def sow(self, tile):
        """播种 + 立刻浇这一格（`farmwork.sow` 的假世界版，语义与生产代码对齐）。"""
        pr = self.plant(tile)
        if not pr.ok:
            return pr
        wr = self.water(tile)
        if wr.ok:
            pr.reason = f"{pr.reason}；紧接着浇水：{wr.reason}"
            return pr
        pr.ok = False
        pr.code = "need_refill" if wr.code == "need_refill" else "failed"
        pr.reason = f"{pr.reason}；但浇水没成：{wr.reason}"
        return pr

    def harvest(self, tile):
        c = self.crops.get(tile)
        if not c or not c["ripe"]:
            return StepResult("harvest", tile, code="skipped", reason="还没熟")
        del self.crops[tile]
        return StepResult("harvest", tile, ok=True, reason="收了")

    def refill(self):
        self.water_left = 40
        self.refills += 1
        return StepResult("refill_can", ok=True, reason="补到 40")

    def sleep(self):
        self.sleeps += 1
        self.unwatered_at_sleep.append(sum(1 for c in self.crops.values() if not c["watered"]))
        self.day += 1
        self.time_of_day = 600
        self.stamina = self.max_stamina
        for c in self.crops.values():
            c["watered"] = False
        return StepResult("sleep", ok=True, reason=f"跨到第 {self.day} 天")

    def buy(self, item, count, shop):
        price = 20
        can = min(int(count), self.money // price)
        if can < 1:
            return StepResult("buy", code="failed", reason=f"钱不够（{self.money}g < {price}g）")
        self.money -= price * can
        slot = self._seed_slot()
        if slot is None:
            self.inventory.append({"slot": 9, "id": SEED_ID, "qualifiedId": f"(O){SEED_ID}",
                                   "name": SEED_NAME, "stack": can, "isTool": False})
        else:
            slot["stack"] += can
        self.buys.append(can)
        return StepResult("buy", ok=True, reason=f"买到 {can} 个，钱 {self.money}g")

    def _seed_slot(self):
        for it in self.inventory:
            if SEED_ID in (str(it.get("id")), str(it.get("qualifiedId"))) and int(it.get("stack") or 0) > 0:
                return it
        return None


class MyopicWorld(FakeWorld):
    """观测**以玩家为中心**的假世界：离得远的格子根本不在观测里（真机行为）。

    真机证据（`scratch\\obs-full.json`，spring 9 11:10）：151 个可锄格，`tillable[]` 只覆盖
    玩家周围一带，`tiles[]`（上限 400、近处优先）里一个都没有。`revealed=True` 表示"人已经
    走进作业区" —— 这时候传感器才看得见那片地。
    """

    def __init__(self, **kw) -> None:
        super().__init__(**kw)
        self.revealed = False
        self.radius = 3

    def obs(self) -> dict:
        o = super().obs()
        if self.revealed:
            return o
        pt = tuple(self.player_tile)
        loc = o["location"]
        loc["tillable"] = [c for c in loc["tillable"]
                           if abs(c[0] - pt[0]) + abs(c[1] - pt[1]) <= self.radius]
        loc["tiles"] = [t for t in loc["tiles"]
                        if abs(t["tile"][0] - pt[0]) + abs(t["tile"][1] - pt[1]) <= self.radius]
        return o


class FakeClient:
    def __init__(self, world: FakeWorld, *, mod_version: str = MOD_VERSION_EXPECTED) -> None:
        self.w = world
        self.mod_version = mod_version
        self.details: list[str] = []

    def health(self, *, timeout=None):
        return {"ok": True, "status": "ok", "modVersion": self.mod_version,
                "runtime": {"worldSeq": self.w.seq, "hasSaveLoaded": True}}

    def observe(self, detail="summary", *, timeout=None):
        self.details.append(detail)
        return self.w.obs()

    # ---- 供**真的** FarmWorker 直接驱动的两个动作（task-4 端到端复现用）----
    def move_to(self, x, y, *, timeout_ms=None):
        self.w.player_tile = [int(x), int(y)]
        if hasattr(self.w, "revealed"):
            self.w.revealed = True
        return {"ok": True, "status": "ok", "tile": [int(x), int(y)]}

    def use_tool(self, tile, *, tool=None, timeout_ms=None):
        return self.w.use_tool(tuple(tile), tool)


class FakeWorker:
    """假执行层：把 `run_stage` 直接落到 `FakeWorld` 上（语义与 farmwork 对齐）。"""

    def __init__(self, world: FakeWorld, *, log=print) -> None:
        self.w = world
        self.log = log
        self.steps: list[StepResult] = []
        self.walk_steps = 0

    def snap(self):
        return self.w.obs()

    def run_stage(self, stage, tiles, *, min_stamina=12.0, max_steps=200):
        action = STAGE_ACTION.get(stage, stage)
        res = StageResult(stage=stage, tiles=list(tiles))
        for i, tile in enumerate(tiles):
            if i >= max_steps:
                res.stopped, res.stopped_reason = "budget", f"达到格数上限 {max_steps}"
                break
            if action in ("clear", "till", "water", "harvest", "sow") and self.w.stamina < min_stamina:
                res.stopped, res.stopped_reason = "stamina", f"体力 {self.w.stamina:g} < {min_stamina:g}"
                break
            st = getattr(self.w, action)(tile)
            self.steps.append(st)
            res.steps.append(st)
            if st.code in ("no_seed", "need_refill"):
                res.stopped, res.stopped_reason = st.code, st.reason
                break
        return res

    def stand_next_to(self, tile, *, timeout_ms=15000):
        self.walk_steps += 1
        # 走到目标格旁边：对"近视世界"来说，这一步之后传感器才看得见那片地
        x, y = tile
        self.w.player_tile = [x, y + 1]
        if hasattr(self.w, "revealed"):
            self.w.revealed = True
        return True

    def move_to(self, tile, *, timeout_ms=15000, **kw):
        self.walk_steps += 1
        self.w.player_tile = [int(tile[0]), int(tile[1])]
        if hasattr(self.w, "revealed"):
            self.w.revealed = True
        return StepResult("move_to", tuple(tile), ok=True, reason="假世界瞬移到位")

    def refill_can(self, *, timeout_ms=15000):
        st = self.w.refill()
        self.steps.append(st)
        return st

    def sleep(self, *, home="FarmHouse", timeout_ms=180000):
        st = self.w.sleep()
        self.steps.append(st)
        return st

    def buy(self, item, count=10, *, shop="SeedShop", timeout_ms=25000):
        st = self.w.buy(item, count, shop)
        self.steps.append(st)
        return st

    def load_save(self, save=None):
        return StepResult("load_save", ok=True, reason="假世界已经在存档里了")

    def ensure_location(self, name, *, tile=None, timeout_ms=30000):
        return StepResult("move_to_location", ok=True, reason=f"假世界已经在 {name}")


class FakePlanner:
    """固定意图的假策略层（用来逼出"边界决策说了不该说的话"这类分支）。"""

    def __init__(self, *intents: TaskIntent) -> None:
        self.intents = list(intents)
        self.calls = 0

    def decide(self, state, brief):
        self.calls += 1
        return SimpleNamespace(boundary="recovery", intents=list(self.intents), source="llm",
                               llm_called=True, problems=[], fallback_reason=None)


def make_run(world: FakeWorld | None = None, **kw) -> LongRun:
    world = world if world is not None else FakeWorld()
    logs: list[str] = []
    params = dict(
        client_factory=lambda: FakeClient(world),
        worker_factory=lambda c: FakeWorker(world),
        target_days=1, plot_size=5, zone_split=2,
        log=logs.append, sleep_fn=lambda _s: None, supervise_every=0,
        # 生产默认是"大模型开着"（用户 m02320），但单测**绝不允许碰网络**：
        # 这里显式关掉，要测 LLM 路径的用例自己注入假 seam 并把 llm_enabled 打开。
        llm_enabled=False,
    )
    params.update(kw)
    run = LongRun(**params)
    run.logs = logs
    return run


# --------------------------------------------------------------------------- 测试
class TestPlotObserve(unittest.TestCase):
    def test_clips_to_plot_and_drops_unactionable(self):
        w = FakeWorld(weeds=0)
        obs = w.obs()
        # 塞一棵树进去：它不是"活"（farmwork 会跳过它），不该进局部简报
        obs["location"]["tiles"].append({"tile": [60, 10], "kind": "tree", "standable": False})
        local = plot_observe(obs, [(60, 10), (60, 11)])
        kinds = {tuple(t["tile"]): t["kind"] for t in local["location"]["tiles"]}
        self.assertEqual(kinds, {})                      # 树被丢掉、空格子本来就不在 tiles 里
        self.assertEqual(len(local["location"]["tillable"]), 2)
        self.assertFalse(local["location"]["tilesTruncated"])


class TestSleepGuard(unittest.TestCase):
    def test_vetoes_when_work_remains(self):
        w = FakeWorld(weeds=4, money=100)
        run = make_run(w)
        run.worker = FakeWorker(w)
        allow, code, text = run.sleep_guard(w.obs())
        self.assertFalse(allow)
        self.assertEqual(code, "keep_working")
        self.assertIn("清", text)

    def test_vetoes_when_seeds_runnable_and_money_enough(self):
        w = FakeWorld(weeds=0, seeds=0, money=100)
        run = make_run(w)
        run.worker = FakeWorker(w)
        allow, code, text = run.sleep_guard(w.obs())
        self.assertFalse(allow)
        self.assertIn("买", text)

    def test_allows_no_work(self):
        w = FakeWorld(weeds=0, seeds=0, money=0)
        for t in sorted(w.tillable)[:6]:
            w.dirt.add(t)
            w.crops[t] = {"watered": True, "ripe": False}
        # 剩下的可锄格也锄掉，才算"真的没活"
        for t in sorted(w.tillable):
            w.dirt.add(t)
        run = make_run(w)
        run.worker = FakeWorker(w)
        allow, code, _ = run.sleep_guard(w.obs())
        self.assertTrue(allow)
        self.assertEqual(code, "no_work")

    def test_night_and_stamina(self):
        w = FakeWorld(weeds=0)
        run = make_run(w)
        run.worker = FakeWorker(w)
        w.time_of_day = 2300
        self.assertEqual(run.sleep_guard(w.obs())[:2], (True, "night"))
        w.time_of_day = 700
        w.stamina = 5.0
        self.assertEqual(run.sleep_guard(w.obs())[:2], (True, "stamina"))


class TestPlotBrief(unittest.TestCase):
    def _plot(self, w, run):
        cands = run._plot_candidates(w.obs())
        self.assertTrue(cands, "假农场应该切得出田区")
        return cands[0]

    def test_does_not_double_count_crop_tiles(self):
        w = FakeWorld(weeds=0, seeds=10, money=500)
        run = make_run(w)
        run.worker = FakeWorker(w)
        plot = self._plot(w, run)
        # 先在这片地里锄 4 格并种下（作物格的 kind 也是 dirt，真机证据一致）
        done = 0
        for t in plot["tiles"]:
            if done >= 4:
                break
            w.dirt.add(t)
            # 浇过水的作物：这样策略不会先被"浇水优先"（用户 m01774 的政策）挡在前面，
            # 这条用例要验的是 dirt 不把作物格算两遍 ⇒ unprepared 仍然 > 0。
            w.crops[t] = {"watered": True, "ripe": False}
            done += 1
        brief = run._plot_brief(w.obs(), plot)
        self.assertEqual(brief.counts["crops"], 4)
        self.assertEqual(brief.counts["dirt"], 0)        # 作物格不算"空地"
        # 目标 = min(可用格, 已种 + 种子)；未开垦 = 目标 - 空地 - 作物 ⇒ 应该 > 0
        self.assertGreater(brief.target_tiles, 4)
        self.assertGreater(brief.unprepared, 0)
        self.assertIn("till_area", [i.task for i in deterministic_plan(brief)])

    def test_broken_when_no_seed_and_no_money(self):
        w = FakeWorld(weeds=0, seeds=0, money=5)
        run = make_run(w)
        run.worker = FakeWorker(w)
        plot = self._plot(w, run)
        for t in plot["tiles"][:3]:
            w.dirt.add(t)
            w.crops[t] = {"watered": True, "ripe": False}
        brief = run._plot_brief(w.obs(), plot)
        self.assertEqual(brief.counts["plantable"], 0)
        self.assertEqual(brief.target_tiles, brief.counts["crops"])
        self.assertNotIn("till_area", [i.task for i in deterministic_plan(brief)])

    def test_plot_work_ignores_tillable_without_affordable_seed(self):
        """守卫与策略同口径：没种子又买不起 ⇒ 可锄格不算"活"（否则一整天耗成 stuck）。"""
        w = FakeWorld(weeds=0, seeds=0, money=5)
        run = make_run(w)
        run.worker = FakeWorker(w)
        plot = run._plot_candidates(w.obs())[0]
        self.assertFalse(run._plot_has_work(w.obs(), plot["tiles"]))
        w.money = 100
        self.assertTrue(run._plot_has_work(w.obs(), plot["tiles"]))

    def test_plot_work_sees_blockers_and_unwatered(self):
        w = FakeWorld(weeds=1, seeds=0, money=0)
        run = make_run(w)
        run.worker = FakeWorker(w)
        self.assertIn("weed", {t["kind"] for t in w.obs()["location"]["tiles"]})
        # 有障碍 ⇒ 是活（清障不花种子）。注意：要按**候选作业区逐个**判 ——
        # 障碍在哪个区由切区算法决定（障碍可能在第一个候选区之外），守卫是逐区问的。
        obs = w.obs()
        self.assertTrue(any(run._plot_has_work(obs, c["tiles"]) for c in run._plot_candidates(obs)))

        w2 = FakeWorld(weeds=0, seeds=0, money=0)
        w2.dirt.add((60, 10))
        w2.crops[(60, 10)] = {"watered": False, "ripe": False}
        run2 = make_run(w2)
        run2.worker = FakeWorker(w2)
        obs2 = w2.obs()
        cands2 = run2._plot_candidates(obs2)
        self.assertTrue(any(run2._plot_has_work(obs2, c["tiles"]) for c in cands2))
        # 那格所在的区必须被认成"有活"（未浇水的作物）
        with_crop = [c for c in cands2 if (60, 10) in {tuple(t) for t in c["tiles"]}]
        self.assertTrue(with_crop, "应该有一个候选区包含那格作物")
        self.assertTrue(all(run2._plot_has_work(obs2, c["tiles"]) for c in with_crop))


class TestOneDay(unittest.TestCase):
    def test_single_day_verified_and_world_changed(self):
        w = FakeWorld(weeds=4, seeds=10, money=500)
        run = make_run(w, target_days=1)
        code = run.run()
        self.assertEqual(code, 0, run.logs)
        self.assertEqual(len(run.days), 1)
        rep = run.days[0]
        self.assertEqual(rep.ended_by, "sleep")
        self.assertTrue(rep.verified, f"{rep.checks} notes={rep.notes}")
        # 世界真的变了：障碍清光、25 格全种下
        self.assertEqual(w.blockers, {})
        self.assertEqual(len(w.crops), 25)
        self.assertEqual(w.day, 7)
        self.assertEqual(w.sleeps, 1)
        # "这天浇完了"只能在睡前问 —— 跨日会把 watered 清零（第二天要重浇）
        self.assertEqual(w.unwatered_at_sleep, [0])
        self.assertEqual(rep.final["unwatered_crops"], 0)
        self.assertTrue(rep.checks["crops_watered"])
        # 阶段走全了三步：浇水不再单独出现 —— `plant_area` 走 `sow`（种一个立刻浇一个，
        # 用户 m01847），所以"浇过"体现在 `unwatered_at_sleep == [0]` 上（上一行）。
        self.assertEqual(set(rep.stages_seen), {"clear_area", "till_area", "plant_area"})

    def test_water_first_when_crops_are_dry(self):
        """用户 m01774/m01770：每天第一个任务就是浇水（除雨天）。

        昨天种下、今天还没浇的作物 ⇒ 睡觉闸门必须否决，且当天的第一个阶段就是 `water_area`。
        """
        w = FakeWorld(weeds=4, seeds=10, money=500)
        # ⚠️ 干作物必须放在**不是障碍**的格子上：(60,10) 同时是 weed 障碍格，`obs()` 会对同一格
        # 产出两条 tiles 记录（weed + dirt），`Brief.from_observe` 按列表都算（blockers=1）而
        # `tiles_of` 按 dict 只认最后一条（dirt）⇒ 策略一直喊 clear_area 而执行层一格都拿不出来。
        # 假世界的 bug 不该用来考生产代码：换到干净的 (61,10)。
        w.dirt.add((61, 10))
        w.crops[(61, 10)] = {"watered": False, "ripe": False}
        run = make_run(w, target_days=1)
        allow, code, text = run.sleep_guard(w.obs())
        self.assertFalse(allow, f"{code}: {text}")
        self.assertEqual(code, "keep_working")
        self.assertIn("没浇水", text)
        self.assertEqual(run.run(), 0, run.logs)
        # ⚠️ `stages_seen` 是**去重后按字母排序**的集合（给人看的），不是执行顺序 ——
        # "谁先做的"只能看 `rep.stages` 的追加顺序。
        self.assertEqual(run.days[0].stages[0]["stage"], "water_area")
        self.assertEqual(run.days[0].final["unwatered_crops"], 0)

    def test_till_targets_skip_unknown_feature_tiles(self):
        """真机 (73,25) 一带：Mod 的 `tillable[]` 会把"有未知特征"的格也算进来，锄不动。"""
        self.assertIn("未知", _till_blocked_by({"kind": "unknown", "feature": "Stone", "objId": "-1"}))
        self.assertEqual(_till_blocked_by({"kind": "dirt", "feature": "HoeDirt"}), "")
        self.assertEqual(_till_blocked_by(None), "")
        w = FakeWorld(weeds=0, seeds=10, money=500)
        run = make_run(w, target_days=1)
        # 作业区得挑**含 (60,10) 的那一片**：`_plot_candidates` 的第一片是另一区（真机同理）。
        candidates = run._plot_candidates(w.obs())
        plot = next(p for p in candidates
                    if (60, 10) in {tuple(t) for t in (p.get("tiles") or [])})
        self.assertIn((60, 10), run._stage_tiles("till_area", w.obs(), plot))
        run.blocked[(60, 10)] = "till 无效：锄完不是 dirt"
        # 封格只免掉**重试**：目标集合里不再出现这一格……
        self.assertNotIn((60, 10), run._stage_tiles("till_area", w.obs(), plot))
        # ……但后置条件复核**必须**看得见它。否则"动了没用"会被从剩余集合里抹掉 ⇒
        # `met=true` ⇒ 硬失败洗成 VERIFIED（task-9：真机 run2 第 1 天就是这么中的招）。
        self.assertIn((60, 10), run._leftover("till_area", w.obs(), plot))

    def test_mark_blocked_records_only_no_effect_groundwork(self):
        """一格最多白试一次；但浇水失败**不封格**（封掉就成了自欺）。"""
        w = FakeWorld(weeds=0, seeds=0, money=0)
        run = make_run(w, target_days=1)
        before = w.obs()
        rep = DayReport(day_key=("spring", 1, 6), started_at=0.0)
        run._mark_blocked(before, w.obs(),
                          [StepResult("till", (60, 10), code="failed", reason="锄完不是 dirt（kind=未知）")],
                          rep)
        self.assertIn((60, 10), run.blocked)
        run.blocked.clear()
        run._mark_blocked(before, w.obs(),
                          [StepResult("water", (61, 10), code="failed", reason="水少了但没浇上")],
                          rep)
        self.assertNotIn((61, 10), run.blocked)

    def test_day_start_asks_llm_then_only_on_boundaries(self):
        """用户 m01860：**一天的第一次决策**要让大模型先判断今天做什么。

        判据：注入的假 seam 调用次数 + 决策事件里的 `boundary`/`source`/`llm`。
        设计上只有三种边界会联网（跨日 / 失败计数上升 / 代码策略阶段切换），
        所以一天是"1 次跨日 + 每次换阶段 1 次"，**不是每个动作都问**。
        """
        w = FakeWorld(weeds=4, seeds=10, money=500)
        calls: list[str] = []

        def fake_chat(messages, **kwargs):
            calls.append("".join(str(m.get("content", "")) for m in messages))
            return json.dumps({"tasks": [
                {"task": "water_area", "area_hint": "tiles.unwatered_crops",
                 "reason": "作物要浇水", "expected_evidence": "unwatered_crops 数量下降"},
                {"task": "clear_area", "area_hint": "field_nw",
                 "reason": "这片田区还有草", "expected_evidence": "blockers 数量下降"},
            ]}, ensure_ascii=False)

        planner = BoundaryPlanner(llm_enabled=True, llm_chat=fake_chat)
        run = make_run(w, target_days=2, planner=planner)
        self.assertEqual(run.run(), 0, run.logs)

        decisions = [e for e in run.entries if e["event"] == "decision"]
        self.assertTrue(decisions)
        # 第一天的第一次决策就是跨日边界，且真的用了大模型
        self.assertEqual(decisions[0]["boundary"], "new_day")
        self.assertEqual(decisions[0]["source"], "llm")
        self.assertTrue(decisions[0]["llm"])
        # 大模型给的意图被原样采纳（含具名田区引用），没有任何一次降级
        self.assertEqual(decisions[0]["intents"][1]["area_hint"], "field_nw")
        self.assertTrue(all(not d["fallback"] for d in decisions),
                        [d["fallback"] for d in decisions if d["fallback"]])
        # 联网次数 = 真调了 LLM 的决策数，且**远少于**决策总数（不是每步都问）
        llm_decisions = [d for d in decisions if d["llm"]]
        self.assertEqual(len(calls), len(llm_decisions))
        self.assertLess(len(calls), len(decisions))
        self.assertTrue(any(not d["llm"] for d in decisions), "常规区间必须一次都不联网")
        # 方向由模型给、坐标由代码落：被点名的田区排在尝试顺序第一位
        run.pending_zone_hint = "field_nw"
        zones = run._zones(w.obs())
        self.assertEqual(run._ordered_zones(zones)[0].name, "field_nw")

    def test_three_days_streak_returns_zero(self):
        w = FakeWorld(weeds=4, seeds=10, money=500, water_left=12)
        run = make_run(w, target_days=3)
        code = run.run()
        self.assertEqual(code, 0, run.logs)
        self.assertEqual([d.ended_by for d in run.days], ["sleep", "sleep", "sleep"])
        self.assertTrue(all(d.verified for d in run.days), [d.checks for d in run.days])
        # 水壶会空：必须走"补水"这条路（而不是让每一格都 tool_ineffective）
        self.assertGreaterEqual(w.refills, 1)
        self.assertEqual(w.day, 9)

    def test_buys_seeds_when_run_out(self):
        w = FakeWorld(weeds=0, seeds=0, money=100)
        run = make_run(w, target_days=1)
        code = run.run()
        self.assertEqual(code, 0, run.logs)
        self.assertTrue(w.buys, "没种子时应该去买")
        self.assertGreater(len(w.crops), 0)
        self.assertTrue(any(e["event"] == "buy" for e in run.entries))

    def test_no_buy_flag(self):
        w = FakeWorld(weeds=0, seeds=0, money=100)
        run = make_run(w, target_days=1, allow_buy=False)
        code = run.run()
        self.assertEqual(code, 0, run.logs)
        self.assertEqual(w.buys, [])
        self.assertEqual(w.crops, {})

    def test_pass_out_day_is_not_verified(self):
        """日期自己变了（不是我们睡的）⇒ 这天不算数。"""
        w = FakeWorld(weeds=4, seeds=10, money=500)
        run = make_run(w, target_days=1)

        # 【为什么假的是 worker 而不是 client】生产代码 `LongRun._snap()` 走的是 `self.worker.snap()`
        # （worker 再去问桥），所以测试里装假 worker 时，观测就地产生 —— 在 client 上做手脚根本不会被调用。
        class PassingOutWorker(FakeWorker):
            def __init__(self, world):
                super().__init__(world)
                self.n = 0

            def snap(self):
                obs = super().snap()
                self.n += 1
                # 第 3 次观测 = _prepare 1 次 + _run_day 开头 1 次 + 循环里第 1 次
                if self.n == 3:            # 中途被系统 pass-out（昏倒/强制跨日）
                    self.w.day += 1
                    self.w.time_of_day = 600
                    return self.w.obs()
                return obs

        run.worker_factory = lambda c: PassingOutWorker(w)
        # 用 max_days=1 把长跑限死在"那一天"上：被动跨日 ⇒ 没有一天是我们自己睡过去的 ⇒ 达不了标。
        # （若不限天数，长跑会继续下一天，而那一天是我们正常睡的 ⇒ 仍会返回 0，这是对的。）
        run.max_days = 1
        code = run.run()
        self.assertEqual(code, 1)
        self.assertEqual(run.days[0].ended_by, "pass_out")
        self.assertFalse(run.days[0].verified)
        self.assertEqual(w.unwatered_at_sleep, [], "我们没睡过 —— 这天不能算")

    def test_mod_version_mismatch_refuses_to_run(self):
        w = FakeWorld()
        run = make_run(w, client_factory=lambda: FakeClient(w, mod_version="0.7.20"))
        code = run.run()
        self.assertEqual(code, 2)
        self.assertIn("0.7.20", run.summary.get("prepare_error", ""))
        self.assertEqual(run.days, [])


class TestDiscipline(unittest.TestCase):
    def test_sleep_intent_is_vetoed_while_work_remains(self):
        """慢脑说"睡"，但地里还有活 ⇒ 必须否决并记 intent_vetoed（用户 2026-10-11 的要求）。"""
        w = FakeWorld(weeds=4, seeds=10, money=500)
        planner = FakePlanner(TaskIntent(task="sleep", area_hint="", reason="模型想睡"))
        run = make_run(w, target_days=1, planner=planner)
        code = run.run()
        self.assertEqual(code, 1)
        rep = run.days[0]
        self.assertNotEqual(rep.ended_by, "sleep")
        self.assertTrue(any(e["event"] == "intent_vetoed" for e in run.entries))
        self.assertEqual(w.sleeps, 0)
        # 不是假装干完了：如实报 stuck
        self.assertEqual(rep.ended_by, "stuck")

    def test_review_intent_is_recorded(self):
        w = FakeWorld(weeds=4, seeds=10, money=500)
        planner = FakePlanner(TaskIntent(task="review", area_hint="anchor:current_location",
                                         reason="复盘"))
        run = make_run(w, target_days=1, planner=planner)
        code = run.run()
        self.assertEqual(code, 1)                 # 只复盘不干活 ⇒ 不算数
        self.assertEqual(run.days[0].ended_by, "stuck")

    def test_zone_hint_from_llm_is_used_next_time(self):
        w = FakeWorld(weeds=0, seeds=4, money=20)
        # 先让 LLM 给一个具名田区：应被记进 pending_zone_hint，而不是被当成坐标
        planner = FakePlanner(TaskIntent(task="plant_area", area_hint="field_se", reason="种东南"))
        run = make_run(w, target_days=1, planner=planner)
        run.run()
        self.assertTrue(any(e["event"] == "decision" for e in run.entries))

    def test_watchdog_stop_aborts_and_reports(self):
        import agentfarm.longrun as lr
        from agentfarm.watchdog import Finding

        w = FakeWorld(weeds=4, seeds=10, money=500)
        reports: list[dict] = []
        orig = (lr.assess, lr.verdict, lr.write_stop_report)
        lr.assess = lambda health, observe, **kw: [
            Finding("world_stuck", lr.LEVEL_STOP, "世界不动了", "假造")]
        lr.verdict = lambda findings: lr.LEVEL_STOP
        lr.write_stop_report = lambda findings, **kw: reports.append(kw)
        try:
            run = make_run(w, target_days=1, supervise_every=1, report_dir="logs")
            code = run.run()
        finally:
            lr.assess, lr.verdict, lr.write_stop_report = orig
        self.assertEqual(code, 1)
        self.assertEqual(run.days[0].ended_by, "stop")
        self.assertTrue(reports, "watchdog 判 STOP 必须落事故报告")
        self.assertTrue(any(e["event"] == "watchdog_stop" for e in run.entries))

    def test_journal_jsonl_written(self):
        w = FakeWorld(weeds=4, seeds=10, money=500)
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sub" / "longrun.jsonl"
            run = make_run(w, target_days=1, journal_path=path)
            run.run()
            self.assertTrue(path.exists())
            lines = [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines() if x.strip()]
        events = [x["event"] for x in lines]
        self.assertIn("day_start", events)
        self.assertIn("day_end", events)
        self.assertIn("finish", events)
        self.assertTrue(all("t" in x for x in lines))

    def test_budget_exhausted_stops(self):
        w = FakeWorld(weeds=4, seeds=10, money=500)
        run = make_run(w, target_days=1, max_minutes=0.0, max_steps=1)
        code = run.run()
        self.assertEqual(code, 1)
        self.assertTrue(run.days[0].ended_by in ("budget", "stuck", "sleep"))

    def test_stage_refill_retry_uses_worker_refill(self):
        w = FakeWorld(weeds=0, seeds=10, money=500, water_left=2)
        run = make_run(w, target_days=1)
        code = run.run()
        self.assertEqual(code, 0, run.logs)
        self.assertGreaterEqual(w.refills, 1)
        # 补水之后要把这一天的作物浇完才睡（睡前口径，不是第二天）
        self.assertEqual(w.unwatered_at_sleep, [0])


class TestHelpers(unittest.TestCase):
    def test_seed_items_reads_names_not_ids(self):
        player = {"inventory": [{"id": "999", "name": "Rare Seed", "stack": 3},
                                {"id": SEED_ID, "name": SEED_NAME, "stack": 4},
                                {"id": "1", "name": "Hoe", "stack": 1, "isTool": True}]}
        got = seed_items(player)
        self.assertEqual(sum(n for _i, _n, n in got), 7)

    def test_run_returns_two_when_bridge_missing(self):
        run = make_run(client_factory=lambda: (_ for _ in ()).throw(
            __import__("agentfarm.bridge", fromlist=["BridgeError"]).BridgeError("no file")))
        self.assertEqual(run.run(), 2)


class TestLlmDefaultOn(unittest.TestCase):
    """用户 m02320："大模型改成长跑默认开启"；m01184：开始介入时必须明确告知。"""

    def test_longrun_defaults_to_llm_enabled(self):
        w = FakeWorld(weeds=2, seeds=10, money=500)
        run = LongRun(client_factory=lambda: FakeClient(w),
                      worker_factory=lambda c: FakeWorker(w),
                      target_days=1, log=lambda _s: None, sleep_fn=lambda _s: None,
                      supervise_every=0)
        self.assertTrue(run.llm_enabled)
        self.assertTrue(run.planner.llm_enabled)

    def test_token_budget_is_consistent_across_modules(self):
        """三处默认值必须一致：真机上 4096 被推理吃光过（plan-llm-manual-5）。"""
        from agentfarm import llm
        from agentfarm.planner import BoundaryPlanner
        self.assertEqual(DEFAULT_LLM_MAX_TOKENS, llm.DEFAULT_MAX_TOKENS)
        self.assertEqual(BoundaryPlanner().max_tokens, llm.DEFAULT_MAX_TOKENS)

    def test_llm_on_is_announced_before_anything_else(self):
        w = FakeWorld(weeds=2, seeds=10, money=500)
        run = make_run(w, llm_enabled=False)
        self.assertEqual(run.run(), 0, run.logs)
        self.assertTrue(any("大模型已关闭" in line for line in run.logs), run.logs[:4])
        self.assertFalse(any(e["event"] == "llm_on" for e in run.entries))

        w2 = FakeWorld(weeds=2, seeds=10, money=500)
        calls: list[dict] = []

        def fake_chat(messages, **kwargs):
            calls.append(kwargs)
            return json.dumps({"tasks": [
                {"task": "water_area", "area_hint": "tiles.unwatered_crops",
                 "reason": "作物要浇水", "expected_evidence": "unwatered_crops 下降"},
            ]}, ensure_ascii=False)

        run2 = make_run(w2, llm_enabled=True, llm_chat=fake_chat)
        self.assertEqual(run2.run(), 0, run2.logs)
        self.assertTrue(any("大模型已开启" in line for line in run2.logs), run2.logs[:4])
        self.assertTrue(any(e["event"] == "llm_on" for e in run2.entries), run2.entries[:3])
        # 播报里给的 token 上限就是真正发出去的那个
        self.assertTrue(all(c["max_tokens"] == DEFAULT_LLM_MAX_TOKENS for c in calls), calls)


class TestIntentBackstop(unittest.TestCase):
    """用户 m02591：策略/大模型的决定必须先过校验 —— 做得了就继续，做不了就取消换任务，
    绝不能"啥也没做就掉头睡觉"（m02532 当场抓到的现象）。"""

    def test_verify_intents_cancels_when_visible_and_keeps_unknown_when_far(self):
        w = MyopicWorld(weeds=0)
        run = make_run(w, target_days=1)
        plot = {"anchor": [60, 10], "tiles": [list(t) for t in sorted(w.tillable)]}
        # 玩家就在旁边、看得见 25 格可锄地 ⇒ 继续
        kept, verdicts = run._verify_intents([TaskIntent("till_area", "", "", ())], w.obs(), plot)
        self.assertEqual([i.task for i in kept], ["till_area"])
        self.assertEqual(verdicts[0]["verdict"], "keep")
        self.assertGreater(verdicts[0]["targets"], 0)
        # 看得见、但一格熟作物都没有 ⇒ 取消（不是"今天收工"）
        kept, verdicts = run._verify_intents([TaskIntent("harvest", "", "", ())], w.obs(), plot)
        self.assertEqual(kept, [])
        self.assertEqual(verdicts[0]["verdict"], "cancel")
        # 走远了：观测看不见这片地，"没有目标"这句话不可信 ⇒ 继续（由执行层走过去再看）
        w.player_tile = [90, 40]
        kept, verdicts = run._verify_intents([TaskIntent("till_area", "", "", ())], w.obs(), plot)
        self.assertEqual([i.task for i in kept], ["till_area"])
        self.assertEqual(verdicts[0]["verdict"], "unknown")
        # review / sleep 这类意图不按"有没有目标格"判，永远放行
        kept, verdicts = run._verify_intents([TaskIntent("review", "", "", ())], w.obs(), plot)
        self.assertEqual([i.task for i in kept], ["review"])
        self.assertEqual(verdicts, [])

    def test_stage_walks_into_plot_when_targets_are_invisible(self):
        w = MyopicWorld(weeds=0)                 # 25 格全是可锄空地
        w.player_tile = [90, 40]                 # 站在很远的地方 ⇒ 观测里一格可锄都看不见
        run = make_run(w, target_days=1)
        run.worker = FakeWorker(w)
        rep = DayReport(day_key=("spring", 1, 6), started_at=0.0)
        plot = {"anchor": [60, 10], "tiles": [list(t) for t in sorted(w.tillable)]}
        self.assertEqual(run._stage_tiles("till_area", w.obs(), plot), [])
        met = False
        for _ in range(5):                        # 每轮最多 12 格（per_stage_tiles）
            out = run._step_stage("till_area", w.obs(), plot, rep)
            met = met or out.postcondition_met
            if met:
                break
        self.assertTrue(met, out.reason)
        self.assertEqual(len(w.dirt), 25, "走过去之后应当把这一片全锄开")
        self.assertGreaterEqual(run.worker.walk_steps, 1)
        self.assertTrue(any(e["event"] == "plot_walk" for e in run.entries), run.entries)
        self.assertNotIn("till_area", run.no_target)

    def test_empty_intents_does_not_sleep_when_guard_says_keep_working(self):
        # 没种子但买得起 ⇒ 守卫认为"还有活"（该去补种子），绝不允许直接回屋睡
        w = FakeWorld(weeds=0, seeds=0, money=500)
        run = make_run(w, target_days=1,
                       planner=FakePlanner(TaskIntent("harvest", "tiles.ripe", "收成熟的", "ripe>0")))
        code = run.run()
        self.assertGreaterEqual(len(w.buys), 1, ("应当去补种子，而不是掉头睡觉", run.entries))
        self.assertEqual(run.days[0].ended_by, "sleep")   # 一天如实收尾（不是崩在半路）
        self.assertEqual(code, 0, run.logs)

    def test_cancel_falls_back_to_another_task_instead_of_sleeping(self):
        """校验取消之后要**换别的任务**（用户 m02591）：不是原地空转，更不是掉头睡觉。

        这里的假策略永远只要 `harvest`（一格熟作物都没有）⇒ 校验必须取消它，并且由确定性策略
        接手把地真的开出来。"""
        w = FakeWorld(weeds=0, seeds=10, money=500)
        run = make_run(w, target_days=1,
                       planner=FakePlanner(TaskIntent("harvest", "tiles.ripe", "收成熟的", "ripe>0")))
        code = run.run()
        self.assertEqual(code, 0, run.logs)
        rep = run.days[0]
        self.assertEqual(rep.ended_by, "sleep")
        # harvest 是**全场级**任务 ⇒ 取消一次就当天不再要（换片地也不该重问）
        self.assertIn("harvest", run.no_target_global)
        verdicts = [e for e in run.entries if e["event"] == "intent_verdict"][0]["verdicts"]
        self.assertEqual(verdicts[0], {"task": "harvest", "verdict": "cancel",
                                       "reason": verdicts[0]["reason"]})
        self.assertTrue(any(e["event"] == "policy_fallback" for e in run.entries), run.entries)
        self.assertGreaterEqual(len(w.dirt), 1, ("取消之后必须换任务真干活", run.entries))


class RestlessWorld(FakeWorld):
    """(60,10) 上的障碍每挥一次就换个样子：状态**一直在变** ⇒ `_mark_blocked` 永远封不掉它。

    `blocked` 的判据是"动手前后这一格没变"。世界在变、但目标状态永远达不到"是判据盖不住的
    缝隙（真机上也可能出现：工具等级/特征不匹配时 Mod 反复换工具、世界被搅动却没清掉）。
    这条缝由兜底不变量 `MAX_TILE_ATTEMPTS` 兜住：同一格一天最多被发起 2 次。
    """

    def __init__(self, **kw) -> None:
        super().__init__(weeds=0, **kw)
        self.blockers[(60, 10)] = "weed"

    def clear(self, tile):
        t = tuple(tile)
        if t == (60, 10):
            self.blockers[t] = "twig" if self.blockers.get(t) == "weed" else "weed"
            return StepResult("clear", t, code="failed", reason="挥了没清掉（这格换了样子）")
        return super().clear(t)


class TestDoomedWorkIsNotRepeated(unittest.TestCase):
    """task-4：注定失败的动作不重复发起（用户 m01758/m01804）。

    真机 run1：clear_area 的两格 grass 被连挥两次、随后两轮策略又各喊一次"周围还有 2 处障碍"，
    白烧体力之后这个阶段还判了 VERIFIED。把三件事钉住：判据前置、同一格一天最多发起 2 次、
    grass 成/败如实记。
    """

    def test_judged_impossible_tiles_never_enter_targets(self):
        """判据在**观测**里就成立 ⇒ 这些格根本不进目标池（不是"发起了再失败"）。"""
        w = FakeWorld(weeds=0, seeds=10, money=500)
        run = make_run(w, target_days=1)
        obs = w.obs()
        obs["location"]["tiles"] = [
            {"tile": [60, 10], "kind": "unknown", "feature": "Stone", "standable": True, "actionable": True},
            {"tile": [60, 11], "kind": "unknown", "objId": "42", "standable": True, "actionable": True},
            {"tile": [60, 12], "kind": "unknown", "objId": "-1", "standable": True, "actionable": True},
        ]
        obs["location"]["tillable"] = [[60, 10], [60, 11], [60, 12]]
        plot = {"anchor": [60, 10], "tiles": [[60, 10], [60, 11], [60, 12]]}
        # 有 feature / 有 objId 的格：Mod 说"可锄"，但观测判据说锄不动 ⇒ 0 次发起
        self.assertEqual(run._stage_tiles("till_area", obs, plot), [(60, 12)])
        self.assertEqual(run._leftover("till_area", obs, plot), [(60, 12)])

    def test_tile_at_attempt_cap_is_not_attempted_again(self):
        """同一格连续失败两次之后不再发起第三次（兜底不变量）。"""
        w = RestlessWorld()
        run = make_run(w, target_days=1)
        run.worker = FakeWorker(w)
        plot = next(p for p in run._plot_candidates(w.obs())
                    if (60, 10) in {tuple(t) for t in (p.get("tiles") or [])})
        rep = DayReport(day_key=("spring", 1, 6), started_at=0.0)
        for _ in range(4):
            run._step_stage("clear_area", w.obs(), plot, rep)
        self.assertEqual(run.tile_attempts.get((60, 10)), MAX_TILE_ATTEMPTS)
        # 状态一直在变 ⇒ 封格判据不成立；拦住重复发起的是次数上限，不是 blocked
        self.assertNotIn((60, 10), run.blocked)
        self.assertNotIn((60, 10), run._stage_tiles("clear_area", w.obs(), plot))
        # 地还是没清掉 ⇒ 后置条件如实为"未成立"（没有假进展）
        self.assertEqual(len(run._leftover("clear_area", w.obs(), plot)), 1)

    def test_stuck_grass_is_swung_once_then_blocked_for_the_day(self):
        """真机 run1（spring 9，(58,21)/(56,21)）复现：镰刀在背包，割了世界不变。

        验收：只挥**一次**（不是连挥两次、也不是下一轮策略再喊一次）、当天封格、
        如实记 skipped/proven_inert（不是 failed），并把判据写进 reason 与 journal。
        """
        w = FakeWorld(weeds=0, seeds=0, money=0, scythe=True)
        w.blockers[(60, 10)] = "grass"
        w.stuck.add((60, 10))
        run = make_run(w, target_days=1)
        run.worker = FarmWorker(FakeClient(w), log=lambda *_: None)
        plot = next(p for p in run._plot_candidates(w.obs())
                    if (60, 10) in {tuple(t) for t in (p.get("tiles") or [])})
        rep = DayReport(day_key=("spring", 1, 9), started_at=0.0)

        out = run._step_stage("clear_area", w.obs(), plot, rep)
        self.assertEqual(w.swings.get((60, 10)), 1, "这一格只允许白挥一次")
        stage = rep.stages[-1]
        self.assertEqual((stage["stage"], stage["ok"], stage["skipped"], stage["failed"]),
                         ("clear_area", 0, 1, 0), stage)
        self.assertEqual(stage["proven_inert"], 1, stage)
        self.assertIn("干不动", out.reason)
        self.assertIn((60, 10), run.blocked)
        # 判据进 journal：`blocked` 事件带 tile/action/no_effect/reason（可事后复核）
        ev = [e for e in run.entries if e["event"] == "blocked"]
        self.assertEqual(len(ev), 1, run.entries)
        self.assertEqual(ev[0]["tile"], [60, 10])
        self.assertEqual(ev[0]["action"], "clear")
        self.assertFalse(ev[0]["no_effect"], "proven_inert 不是「花了体力没变」")
        # 判据本身（"kind 离开 grass"没满足）+ 现场（体力/工具）都进了 journal
        self.assertIn("kind 离开 grass", ev[0]["reason"])
        self.assertIn("scythe", ev[0]["reason"])
        # ⚠️ task-9：封格**只免掉重试**，不许把这次"没做成"洗成功。这一格世界 0 变化、
        # 目标 kind 仍是 grass ⇒ 后置条件必须**不成立**，阶段终态是 needs_review。
        # 判据（哪条判据说它干不动）留在 reason/`proven_inert`/journal `blocked` 里供复核。
        self.assertFalse(out.postcondition_met, out.reason)
        self.assertNotEqual(out.terminal, "VERIFIED", out.reason)
        self.assertIn("还剩 1 格", out.reason)
        self.assertIn("1 格已判定干不动", out.reason)
        self.assertIn("kind 离开 grass", out.reason)
        self.assertNotIn("还剩 0 格", out.reason, "不许出现自相矛盾的文案")
        # 干不动的原因也进 journal（单独一条 `stage_exhausted`，带格与理由）
        ex = [e for e in run.entries if e["event"] == "stage_exhausted"]
        self.assertEqual(len(ex), 1, run.entries)
        self.assertEqual((ex[0]["stage"], ex[0]["leftover"], ex[0]["doomed"]),
                         ("clear_area", 1, 1), ex[0])

        # 策略下一轮再要 clear_area：该格当天已封 ⇒ 一次都不再发起
        run._step_stage("clear_area", w.obs(), plot, rep)
        self.assertEqual(w.swings.get((60, 10)), 1, "当天不允许第二次发起")
        self.assertEqual(run.tile_attempts.get((60, 10)), 1)

    def test_grass_clear_success_is_recorded_as_ok(self):
        """grass 成：镰刀割掉、kind 变了 ⇒ ok（不是 skipped/proven_inert）。"""
        w = FakeWorld(weeds=0, seeds=0, money=0, scythe=True)
        w.blockers[(60, 10)] = "grass"
        run = make_run(w, target_days=1)
        run.worker = FarmWorker(FakeClient(w), log=lambda *_: None)
        plot = next(p for p in run._plot_candidates(w.obs())
                    if (60, 10) in {tuple(t) for t in (p.get("tiles") or [])})
        rep = DayReport(day_key=("spring", 1, 9), started_at=0.0)
        out = run._step_stage("clear_area", w.obs(), plot, rep)
        self.assertEqual(w.swings.get((60, 10)), 1)
        self.assertNotIn((60, 10), w.blockers)
        stage = rep.stages[-1]
        self.assertEqual((stage["ok"], stage["failed"], stage["proven_inert"]), (1, 0, 0), stage)
        self.assertTrue(out.postcondition_met)


class CountingWorker(FakeWorker):
    """假执行层 + 记下 `run_stage` 被叫过几次。

    "没种子不垦地"的验收不能只看"世界没变"（锄了地世界就变了）：必须证明执行层**根本没人叫**，
    所以要在 `run_stage` 上挂计数器。真机 run2 的教训正是"上层说要垦、执行层就真锄"。
    """

    def __init__(self, world: FakeWorld) -> None:
        super().__init__(world)
        self.stage_calls: list[tuple[str, list[tuple[int, int]]]] = []

    def run_stage(self, stage, tiles, *, min_stamina=12.0, max_steps=200):
        self.stage_calls.append((stage, [tuple(t) for t in tiles]))
        return super().run_stage(stage, tiles, min_stamina=min_stamina, max_steps=max_steps)


class TestAccountingTask9(unittest.TestCase):
    """task-9 的三处账目/资源缺陷（全部来自真机 run2）：

    ① `blocked` 只许"不再重试"，**不许**把"没做成"洗成 VERIFIED；
    ② 没种子又买不起时**不许**再开垦/播种（白烧体力 270→74、60 格空 dirt）；
    ③ 提示词预算 8192 被推理吃光（`LlmError:truncated`）⇒ 默认 16384 且降级要标出"是不是截断"。
    """

    def test_blocked_leftover_is_not_verified(self):
        """只剩"已判定干不动"的格子 ⇒ 后置条件不成立、needs_review，且文案不说"还剩 0 格"。"""
        w = FakeWorld(weeds=0, seeds=10, money=500)
        w.tillable = {(60, 10)}          # 只留一格：它一封，整个阶段就只剩"干不动"的格子
        run = make_run(w, target_days=1)
        run.worker = FakeWorker(w)
        plot = {"zone": "", "label": "", "anchor": [60, 10], "tiles": [(60, 10)], "note": ""}
        run.blocked[(60, 10)] = "till 无效：锄完不是 dirt"
        rep = DayReport(day_key=("spring", 1, 6), started_at=0.0)

        out = run._step_stage("till_area", w.obs(), plot, rep)

        # 这一格世界 0 变化、目标 kind 也没达标 ⇒ 后置条件必须**不成立**
        self.assertFalse(out.postcondition_met, out.reason)
        self.assertEqual(out.terminal, "needs_review", out.reason)
        self.assertNotEqual(out.terminal, "VERIFIED")
        # 文案：报剩余格数 + 其中几格干不动（判据留在 reason 里供复核），且不许自相矛盾
        n = len(run._leftover("till_area", w.obs(), plot))
        self.assertEqual(n, 1, "复核集合必须看得见被封的格子")
        self.assertIn("还剩 1 格", out.reason)
        self.assertIn("1 格已判定干不动", out.reason)
        self.assertIn("锄完不是 dirt", out.reason)
        self.assertNotIn("还剩 0 格", out.reason)
        self.assertNotIn("后置条件成立", out.reason)
        # 记账的**唯一**作用是不再空转：策略这天不再要 till_area（但它不是"成功"）
        self.assertIn("till_area", run.no_target)
        ex = [e for e in run.entries if e["event"] == "stage_exhausted"]
        self.assertEqual(len(ex), 1, run.entries)
        self.assertEqual((ex[0]["stage"], ex[0]["leftover"], ex[0]["doomed"]),
                         ("till_area", 1, 1), ex[0])

    def test_no_seed_no_money_never_tills(self):
        """种子 0 且钱 < 单价 ⇒ 三道口径都说"没活"，`run_stage` 一次都不被叫。"""
        w = FakeWorld(weeds=0, seeds=0, money=5)
        w.dirt = {(60, 10)}              # 留一格已锄开的地：不设闸门时 plant_area 本会去播种
        run = make_run(w, target_days=1)
        run.worker = CountingWorker(w)
        plot = next(p for p in run._plot_candidates(w.obs())
                    if (60, 10) in {tuple(t) for t in (p.get("tiles") or [])})

        # ① 目标集合：两阶段都空（不是因为"本来就没地"——复核集合非空，见下）
        self.assertEqual(run._stage_tiles("till_area", w.obs(), plot), [])
        self.assertEqual(run._stage_tiles("plant_area", w.obs(), plot), [])
        self.assertTrue(run._leftover("plant_area", w.obs(), plot),
                        "地还在（复核看得见），是种子闸门把目标掐掉了")
        # ② 守卫层同口径：这片地"没活"
        self.assertFalse(run._plot_has_work(w.obs(), [tuple(t) for t in plot["tiles"]]))

        rep = DayReport(day_key=("spring", 1, 6), started_at=0.0)
        out = run._step_stage("till_area", w.obs(), plot, rep)
        # ③ 执行层：一格都没动（`run_stage` 根本没被叫）
        self.assertEqual(run.worker.stage_calls, [], "没种子还去垦地 = 白烧体力")
        self.assertFalse(out.postcondition_met)
        self.assertNotEqual(out.terminal, "VERIFIED")
        self.assertNotIn("后置条件成立", out.reason)
        # 人话 + 判据都留下：播报一次、journal 带 seeds/money/单价
        self.assertTrue(any("不再开垦" in n for n in rep.notes), rep.notes)
        gate = [e for e in run.entries if e["event"] == "seed_gate"]
        self.assertEqual(len(gate), 1, run.entries)
        self.assertEqual((gate[0]["seeds"], gate[0]["money"], gate[0]["seed_price"]),
                         (0, 5, run.seed_price), gate[0])

    def test_default_max_tokens_is_16384(self):
        """提示词预算：默认 16384（三处同一个真值源），且降级要能标出"是不是被截断"。"""
        from agentfarm import llm
        from agentfarm.llm import LlmError
        from agentfarm.planner import Brief, PlannerState

        self.assertEqual(llm.DEFAULT_MAX_TOKENS, 16384)
        self.assertEqual(DEFAULT_LLM_MAX_TOKENS, llm.DEFAULT_MAX_TOKENS)
        self.assertEqual(BoundaryPlanner().max_tokens, llm.DEFAULT_MAX_TOKENS)
        self.assertEqual(BoundaryPlanner(max_tokens=4096).max_tokens, 4096)
        # 播报/journal 报的是**生效值**（用户 `--max-tokens` 调小了，日志不许还写 16384）
        self.assertEqual(make_run(FakeWorld(), llm_max_tokens=4096).llm_max_tokens, 4096)

        def boom(*_a, **_kw):
            raise LlmError("回答被 max_tokens 截断（reasoning 吃光预算、content 为空）",
                           status="truncated")

        planner = BoundaryPlanner(llm_chat=boom, max_llm_attempts=1)
        decision = planner.decide(PlannerState(day_key=(1, "spring", 5)),
                                  Brief(day_key=(1, "spring", 6), counts={"blockers": 1}))
        self.assertEqual(decision.source, "deterministic_fallback")
        self.assertIn("truncated", decision.fallback_reason or "")
        self.assertTrue(decision.truncated, "降级原因里有 truncated ⇒ 必须标出来")
        self.assertTrue(decision.as_dict()["truncated"])
        # 反例：网络类失败不许被误标成"该调大预算"
        def boom2(*_a, **_kw):
            raise LlmError("超时", status="network")

        d2 = BoundaryPlanner(llm_chat=boom2, max_llm_attempts=1).decide(
            PlannerState(day_key=(1, "spring", 5)),
            Brief(day_key=(1, "spring", 6), counts={"blockers": 1}))
        self.assertFalse(d2.truncated)
        self.assertFalse(d2.as_dict()["truncated"])


if __name__ == "__main__":
    unittest.main()

