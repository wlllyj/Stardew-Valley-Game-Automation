r"""task-108 对抗脚本：task-104（`9b5b592`，"人不在农场时不去浇窗口外干作物"）能不能被打穿。

全部用**真代码**（真 `FarmWorker` + 真 `LongRun`，journal 写盘后喂进程内 `tools/verify-run3.py`）。

B 段（复跑 run8 day 12 的两个现场，必须 PASS）：
  B1 室内 + 窗口外干作物 ⇒ 不扣额度、不认输、收尾点名 not_on_farm、工具 needs_review
  B2 回得去 ⇒ 当天真浇上（water_far ok、far_dry_tries=1、世界真变）
C 段（朝修法本身进攻）：
  C1 伪装"人在农场"（`isOutdoorFarm=true`）+ 坐标够不着 ⇒ 额度会不会被骗扣、会不会白过
  C2 连续多天回不去（且有窗内活让游戏日往前走）⇒ goto/额度是否跨天有界
  C3 not_on_farm 与 given_up 是否混淆、次日是否仍会重试
  C4 0 农场动作 + 有活 + 回不去 ⇒ 与 `slept_without_work`/`no_day_progress` 组合会不会死循环
  C5 回不去之后人回到农场 ⇒ 当天还能不能浇（flag 会不会永久毒化）
  C6 `ensure_location` 在观测失败时抛 BridgeError ⇒ 是否 fail-closed（会不会炸掉整轮）
  C7 人在农场时逐字不改（pre/post 两棵树同世界对照）
用法：`python scratch\_t108_adv.py [case ...]`；pre 树对照：`$env:T92_ROOT=<pre>; python scratch\_t108_adv.py c7`
"""
import json
import os
import sys
from pathlib import Path

_here = Path(__file__).resolve().parent
ROOT = Path(os.environ.get("T92_ROOT") or _here.parent)
sys.path.insert(0, str(_here))
import _t103_adv as A  # noqa: E402

TL, VR = A.TL, A.VR
from agentfarm.bridge import BridgeError                      # noqa: E402
from agentfarm.farmwork import FarmWorker                     # noqa: E402

FAR = (61, 10)          # 离玩家 [62,14] 曼哈顿 5 > 观测半径 3 ⇒ 窗口外
NEAR = (62, 13)         # 窗口内（曼哈顿 1）
JDIR = ROOT / "scratch" / "_t108_j"
SEQ = {"n": 0}
CHECKS: list[tuple[bool, str]] = []


def check(ok: bool, msg: str) -> None:
    CHECKS.append((bool(ok), msg))
    print(f"  [{'PASS' if ok else 'FAIL'}] {msg}")


def ev(run, name: str) -> list[dict]:
    return A.ev(run, name)


def run_real(w, client, *, days: int = 1, worker_factory=None):
    JDIR.mkdir(parents=True, exist_ok=True)
    SEQ["n"] += 1
    jp = JDIR / f"t108_{SEQ['n']:02d}.jsonl"
    if jp.exists():
        jp.unlink()
    wf = worker_factory or (lambda c: FarmWorker(c, log=lambda _s: None, pause=lambda _s: None))
    run = TL.make_run(w, target_days=1, max_days=days, journal_path=str(jp),
                      client_factory=lambda: client, worker_factory=wf)
    run.run()
    run._probe_journal = str(jp)
    return run


class T108Client(A.CapClient):
    """真桥语义 + 三个可注入故障：goto 被模态挡住 / 指定格 unreachable / 观测失败。"""

    def __init__(self, world, *, goto: str = "ok", unreachable=(), fail_observe_at=None,
                 flip_indoor_at=None, flip_farm_at=None, **kw):
        super().__init__(world, **kw)
        self.goto = goto
        self.unreachable = {tuple(t) for t in unreachable}
        self.fail_observe_at = fail_observe_at
        self.flip_indoor_at = flip_indoor_at
        self.flip_farm_at = flip_farm_at
        self.goto_calls = 0
        self.observes = 0
        self.flipped = False
        self.flipped_back = False

    def move_to_location(self, name, *, tile=None, timeout_ms=None):
        self.goto_calls += 1
        if self.goto == "ui_modal":
            raise BridgeError("[ui_modal] 有菜单/对话挡着（'ShippingMenu'），所有技能都会被拒",
                              status="ui_modal")
        self.w.location = str(name)
        if str(name) == "Farm":
            self.w.is_outdoor_farm = True
        return super().move_to_location(name, tile=tile, timeout_ms=timeout_ms)

    def move_to(self, x, y, *, timeout_ms=None, allow_bed=None):
        if (int(x), int(y)) in self.unreachable:
            raise BridgeError(f"假世界：({x},{y}) 走不到（unreachable）", status="unreachable")
        return super().move_to(x, y, timeout_ms=timeout_ms, allow_bed=allow_bed)

    def observe(self, detail="summary", *, timeout=None):
        self.observes += 1
        if (self.flip_indoor_at is not None and not self.flipped
                and self.observes >= self.flip_indoor_at):
            # run8 day 12 形态：开工后人被留在室内（晨间 ShippingMenu 把 move_to_location 挡成
            # ui_modal，人留在 FarmHouse）；这里在"日循环已经跑起来之后"把世界翻成室内。
            self.flipped = True
            self.w.location = "FarmHouse"
            self.w.is_outdoor_farm = False
            print(f"  （flip：第 {self.observes} 次观测后世界翻成室内 FarmHouse）")
        if (self.flip_farm_at is not None and not self.flipped_back
                and self.observes >= self.flip_farm_at):
            # 人后来又回到农场（同一天内）——测 flag 会不会永久毒化当天
            self.flipped_back = True
            self.w.location = "Farm"
            self.w.is_outdoor_farm = True
            print(f"  （flip-back：第 {self.observes} 次观测后世界翻回农场 Farm）")
        if self.fail_observe_at is not None and self.observes >= self.fail_observe_at:
            raise BridgeError("假世界：观测失败（bridge 断）", status="bridge_down")
        return super().observe(detail, timeout=timeout)


def indoor_world(**kw):
    w = TL.DryTilesWorld(seeds=0, money=0, weeds=0, water_left=40, with_dry_tiles=True, **kw)
    w.dirt.add(FAR)
    w.crops[FAR] = {"watered": False, "ripe": False}
    w.player_tile = [62, 14]
    w.location = "FarmHouse"
    w.is_outdoor_farm = False
    return w


def on_farm_world(**kw):
    """开工时人在农场（`_prepare` 才能过），窗口外仍有一格干作物。"""
    w = indoor_world(**kw)
    w.location = "Farm"
    w.is_outdoor_farm = True
    return w


FAR_NEIGHBOURS = ((FAR[0] - 1, FAR[1]), (FAR[0] + 1, FAR[1]),
                  (FAR[0], FAR[1] - 1), (FAR[0], FAR[1] + 1))


class FarBlockedWorld(TL.DryTilesWorld):
    """把窗口外目标格的**四邻**全标成站不住的树 ⇒ `_ensure_reachable` 找不到落脚点（真够不着）。"""

    def obs(self):
        o = super().obs()
        tiles = o["location"]["tiles"]
        for n in FAR_NEIGHBOURS:
            hit = next((t for t in tiles if tuple(t["tile"]) == n), None)
            if hit is None:
                tiles.append({"tile": list(n), "kind": "tree", "standable": False,
                              "actionable": False})
            else:
                hit["standable"] = False
                hit["kind"] = "tree"
        return o


def far_blocked_world(*, lie: bool = False):
    """`lie=True` = Mod 字段谎报"在户外农场"（`isOutdoorFarm=true`）而人其实在 FarmHouse。"""
    w = FarBlockedWorld(seeds=0, money=0, weeds=0, water_left=40, with_dry_tiles=True)
    w.dirt.add(FAR)
    w.crops[FAR] = {"watered": False, "ripe": False}
    w.player_tile = [62, 14]
    w.location = "FarmHouse" if lie else "Farm"
    w.is_outdoor_farm = True
    return w


def last_end(run):
    ends = ev(run, "day_end")
    return ends[-1] if ends else {}


# ------------------------------------------------------------------ B 段


def b1_run8_day12() -> None:
    """run8 day 12 现场：开工后在室内 + 窗口外有干作物 + 回不去。"""
    w = on_farm_world()
    c = T108Client(w, goto="ui_modal", flip_indoor_at=3)
    run = run_real(w, c, days=1)
    A.report("B1 室内 + 窗口外干作物（run8 day12 复现）", run)
    ends, skips, wf, gos = ev(run, "day_end"), ev(run, "water_far_skipped"), ev(run, "water_far"), ev(run, "goto_farm")
    e = last_end(run)
    check(len(ends) == 1, f"B1 只跑了 1 天（max_days=1，实测 {len(ends)}）")
    check(run.far_dry_tries == {}, f"B1 一格额度都没扣（far_dry_tries={run.far_dry_tries}）")
    check(run.far_dry_given_up == set(), "B1 没有认输（far_dry_given_up 为空）")
    check(wf == [], "B1 没有对够不着的坐标发 water（无 water_far 事件）")
    check(len(skips) == 1 and skips[0].get("reason") == "not_on_farm"
          and skips[0].get("count") == 1 and skips[0].get("tiles") == [[61, 10]],
          f"B1 恰 1 条 water_far_skipped{{not_on_farm,count=1,tiles=[[61,10]]}}: {skips}")
    check(len([g for g in gos if g.get("where") == "water_far"]) == 1, "B1 goto_farm{water_far} 恰 1 次（一天只试一次）")
    check(len(gos) <= 2, f"B1 当天 goto_farm 总数 ≤2（实测 {len(gos)}）")
    check(e.get("ended_by") in ("slept_without_work", "stuck"), f"B1 收尾 ended_by={e.get('ended_by')!r}（不许 no_work）")
    check("not_on_farm" in str(e.get("ended_reason")), "B1 收尾理由点名 not_on_farm")
    check(e.get("verified") is False and (e.get("checks") or {}).get("day_justified") is False,
          "B1 verified=False 且 day_justified=False")
    check((e.get("checks") or {}).get("watered_outdoor") is False, "B1 watered_outdoor=False（没白拿达标）")
    check(w.crops.get(FAR, {}).get("watered") is False, "B1 世界那一格始终没浇（没有假动作）")


def b2_return_ok() -> None:
    """回得去：清模态 + 一次 ensure ⇒ 当天真浇上那一格。"""
    w = on_farm_world()
    c = T108Client(w, goto="ok", flip_indoor_at=3)
    run = run_real(w, c, days=1)
    A.report("B2 室内 → 回农场 → 浇上", run)
    wf, ends = ev(run, "water_far"), ev(run, "day_end")
    e = last_end(run)
    check(len(wf) == 1 and wf[0].get("ok") is True, f"B2 water_far 恰好 1 次且 ok：{wf}")
    check(run.far_dry_tries.get(FAR) == 1, f"B2 far_dry_tries[FAR]=1（实测 {run.far_dry_tries}）")
    check(run.far_dry_given_up == set(), "B2 没有认输")
    check(bool(wf) and wf[0].get("watered") is True and wf[0].get("dry_before") == 1
          and wf[0].get("dry_after") == 0,
          "B2 观测差分证明真浇上（watered=True、dry 1→0，跨日会清 watered 所以看 journal 不看末态）")
    check(ev(run, "water_far_skipped") == [] and run.water_far_not_on_farm is False,
          "B2 没有 not_on_farm 留痕（回得去就不算）")
    check((e.get("checks") or {}).get("watered_outdoor") is True, "B2 日级 watered_outdoor=True")


# ------------------------------------------------------------------ C 段


def c1_fake_on_farm() -> None:
    """⑤ 人在农场（或 Mod 谎报"在户外农场"）但那一格真够不着 ⇒ 额度会不会被骗扣/会不会白过。"""
    for lie in (False, True):
        tag = ("C1b Mod 谎报 isOutdoorFarm=true（人在 FarmHouse）" if lie
               else "C1a 真在农场但四邻站不住")
        w = far_blocked_world(lie=lie)
        c = T108Client(w, goto="ok", unreachable={FAR, *FAR_NEIGHBOURS})
        run = run_real(w, c, days=1)
        A.report(tag, run)
        e = last_end(run)
        triesn = int(run.far_dry_tries.get(FAR, 0))
        wf = ev(run, "water_far")
        check(triesn >= 2, f"{tag} 守卫被绕过 ⇒ 额度照扣（tries={triesn}）")
        check(FAR in run.far_dry_given_up, f"{tag} 两次不成 ⇒ 进 given_up（{run.far_dry_given_up}）")
        check(ev(run, "water_far_skipped") == [], f"{tag} 没有 not_on_farm 留痕（守卫只看 Mod 字段）")
        check(w.crops.get(FAR, {}).get("watered") is False, f"{tag} 世界那一格没被浇（没有假动作）")
        check(e.get("verified") is False and not (e.get("checks") or {}).get("day_justified"),
              f"{tag} verified=False / day_justified=False（**没有白过**）")
        check(bool(wf) and all(x.get("ok") is False for x in wf),
              f"{tag} water_far 全部 ok=False（code={[x.get('code') for x in wf]}）")
        print(f"  （{tag} 收尾：ended_by={e.get('ended_by')!r} reason={str(e.get('ended_reason'))[:90]!r}）")


def c2_multi_day_bounded() -> None:
    """⑥ 连续多天回不去（窗内有活让游戏日往前走）⇒ goto/额度跨天有界。"""
    w = on_farm_world()
    w.dirt.add(NEAR)
    w.crops[NEAR] = {"watered": False, "ripe": False}   # 窗口内的活 ⇒ farm_actions>0 ⇒ 天数会推进
    c = T108Client(w, goto="ui_modal", flip_indoor_at=3)
    run = run_real(w, c, days=4)
    A.report("C2 连续多天回不去（窗内有活）", run)
    ends, skips, gos = ev(run, "day_end"), ev(run, "water_far_skipped"), ev(run, "goto_farm")
    ndays = len(ends)
    check(ndays <= 3, f"C2 没有无限跑：max_days=4 只产出 {ndays} 天（stuck_flush 有界）")
    check(len([g for g in gos if g.get("where") == "water_far"]) == ndays,
          f"C2 每天恰 1 次 goto_farm{{water_far}}（{len([g for g in gos if g.get('where') == 'water_far'])} vs {ndays} 天）")
    check(len(gos) <= 2 * ndays, f"C2 goto_farm 总数 ≤2/天（实测 {len(gos)}）")
    check(len(skips) == ndays, f"C2 每天 1 条 water_far_skipped（{len(skips)} vs {ndays}）")
    check(run.far_dry_given_up == set(), "C2 跨天都没认输（额度不算在 given_up）")
    check(all(not (d.get("checks") or {}).get("day_justified") for d in ends), "C2 没有一天 day_justified=True")
    check(all(d.get("verified") is False for d in ends), "C2 没有一天 VERIFIED")


def c3_not_on_farm_vs_given_up() -> None:
    """⑦ not_on_farm 与 given_up 不混淆、次日仍会重试同一格。"""
    w = on_farm_world()
    w.dirt.add(NEAR)
    w.crops[NEAR] = {"watered": False, "ripe": False}
    c = T108Client(w, goto="ui_modal", flip_indoor_at=3)
    run = run_real(w, c, days=4)
    A.report("C3 not_on_farm 与 given_up 的区分", run)
    ends, skips = ev(run, "day_end"), ev(run, "water_far_skipped")
    check(all(s.get("reason") == "not_on_farm" for s in skips), "C3 所有 skip 都是 not_on_farm")
    check(all((d.get("final_water") or {}).get("scope") != "farm" or True for d in ends), "C3 （记录）")
    check(all(not d.get("gave_up_tiles") for d in ends), f"C3 每天 gave_up_tiles 都空：{[d.get('gave_up_tiles') for d in ends]}")
    check(len(skips) >= 2, f"C3 次日仍在重试同一格（skip 条数 {len(skips)} ≥2 ⇒ 没被封死）")
    check(FAR not in run.far_dry_given_up, "C3 FAR 从未进 given_up")


def c4_zero_action_no_loop() -> None:
    """⑨ 0 农场动作 + 有活 + 回不去 ⇒ 有界翻篇，但绝不白拿 VERIFIED、不死循环。"""
    w = on_farm_world()
    c = T108Client(w, goto="ui_modal", flip_indoor_at=3)
    run = run_real(w, c, days=3)
    A.report("C4 0 动作 + 回不去（有界翻篇 vs 白拿达标）", run)
    ends, gos = ev(run, "day_end"), ev(run, "goto_farm")
    check(all(not (d.get("day_after") and (d.get("ok_steps") or 0) == 0 and d.get("verified"))
              for d in ends),
          "C4 不变量：day_after ∧ ok_steps==0 ∧ verified 三者绝不同时")
    check(all(d.get("verified") is False for d in ends), "C4 没有一天 VERIFIED")
    check(all("not_on_farm" in str(d.get("ended_reason")) for d in ends), "C4 每天收尾都点名 not_on_farm")
    check(len(ends) <= 3, f"C4 有界（MAX_STUCK_FLUSH=2）：只产出 {len(ends)} 天")
    check(len([g for g in gos if g.get("where") == "water_far"]) == len(ends),
          f"C4 每天至多 1 次 goto_farm{{water_far}}（{len([g for g in gos if g.get('where') == 'water_far'])} vs {len(ends)} 天）")
    check(len(ev(run, "no_day_progress")) <= 1, "C4 no_day_progress ≤1（停轮机制在）")
    # 直接钉 `_do_sleep` 的"0 动作不许睡"：世界还在 0 动作 + 有活状态
    rep = TL.DayReport(day_key=("summer", 12, 12), started_at=0.0)
    run.farm_actions_today = 0
    day_before = w.day
    by, why = run._do_sleep(w.obs(), rep, "test")
    check(by == "slept_without_work" and rep.slept_without_work is True,
          f"C4b _do_sleep 直接调：ended_by={by!r} slept_without_work={rep.slept_without_work}")
    check(w.day == day_before, f"C4b 游戏日没有推进（{day_before} → {w.day}）")
    check("not_on_farm" in run._not_on_farm_suffix(), "C4b 理由后缀仍会点名 not_on_farm")


def c5_flag_not_sticky_poison() -> None:
    """C5 回不去之后人回到农场 ⇒ 当天还能浇（flag 只挡"不在农场"那条路）。"""
    w = indoor_world()
    c = T108Client(w, goto="ui_modal")
    JDIR.mkdir(parents=True, exist_ok=True)
    run = TL.make_run(w, target_days=1, max_days=1, client_factory=lambda: c)
    run.client = c
    run.worker = FarmWorker(c, log=lambda _s: None, pause=lambda _s: None)
    rep = TL.DayReport(day_key=("summer", 12, 12), started_at=0.0)
    first = run._water_far_dry(w.obs(), rep)
    check(first is False and run.water_far_not_on_farm is True, "C5 第一次（室内）拒绝且置 flag")
    w.location = "Farm"
    w.is_outdoor_farm = True
    second = run._water_far_dry(w.obs(), rep)
    check(second is True and run.far_dry_tries.get(FAR) == 1,
          f"C5 回到农场后当天仍会去浇（far_dry_tries={run.far_dry_tries}）")
    check(bool(w.crops.get(FAR, {}).get("watered")) is True,
          f"C5 世界真浇上（crops[FAR]={w.crops.get(FAR)}；`watered_tiles` 只有夹具自己的 water() 才记）")
    suffix = run._not_on_farm_suffix()
    check(suffix != "", "C5【NIT-1】flag 是日级粘性的：当天后来真浇上了，收尾理由仍会说"
                        f"「这轮没去浇」{suffix!r}")
    print("  （C5b 注：端到端的「混合日」没有稳定复现——flip 的观测序号落在哪一轮取决于当天"
          "前面的作业轮数；NIT-1 的证据以本函数的直调探针为准，flag 只在次日重置 `:3320` 清）")


class RaisingEnsureWorker(FarmWorker):
    """`ensure_location` 直接抛 BridgeError（复刻"观测失败"在回归途中炸出来）。"""

    def ensure_location(self, name, *, tile=None, timeout_ms=60000):
        raise BridgeError("假世界：观测失败（bridge 断）", status="bridge_down")


def c6_ensure_raises() -> None:
    """C6 `ensure_location` 在观测失败时抛 BridgeError ⇒ 不炸整轮 / fail-closed。"""

    w = on_farm_world()
    c = T108Client(w, goto="ui_modal", flip_indoor_at=3)
    raised = ""
    try:
        run = run_real(w, c, days=2, worker_factory=lambda cc: RaisingEnsureWorker(
            cc, log=lambda _s: None, pause=lambda _s: None))
    except BridgeError as exc:
        raised = str(exc)
        run = None
    except Exception as exc:                                  # noqa: BLE001
        raised = f"{type(exc).__name__}: {exc}"
        run = None
    print(f"  C6 run.run() 抛出：{raised!r}")
    check(raised == "", f"C6 ensure_location 抛 BridgeError 时整轮**不该**抛出去（实测 {raised!r}）")
    # C6 归因：同样的形态在 task-104 之前就存在（`_ensure_on_farm` 的 day_start 路径，cc2988e）
    w2 = indoor_world()
    c2 = T108Client(w2, goto="ok")
    run2 = TL.make_run(w2, target_days=1, max_days=1, client_factory=lambda: c2,
                       worker_factory=lambda cc: RaisingEnsureWorker(
                           cc, log=lambda _s: None, pause=lambda _s: None))
    run2.client = c2
    run2.worker = RaisingEnsureWorker(c2, log=lambda _s: None, pause=lambda _s: None)
    rep2 = TL.DayReport(day_key=("summer", 6, 12), started_at=0.0)
    escaped2 = ""
    try:
        run2._ensure_on_farm(w2.obs(), rep2)
    except BridgeError as exc:
        escaped2 = str(exc)
    check(escaped2 != "",
          f"C6【归因】task-104 之前的老路径 `_ensure_on_farm`（cc2988e）同样会穿出去 ⇒ 老洞，"
          f"不是 task-104 新引入（实测 {escaped2!r}）")
    # C6b 观测在"回去的路上"失败（真代码 path）：ensure_location 内部 snap() 抛 ⇒ 同样穿出
    w3 = on_farm_world()
    c3 = T108Client(w3, goto="ok", flip_indoor_at=3, fail_observe_at=10)
    escaped3 = ""
    try:
        run_real(w3, c3, days=2)
    except BridgeError as exc:
        escaped3 = str(exc)
    check(escaped3 == "",
          "C6b 观测失败落在日循环自己的快照上 ⇒ 被兜住（graceful bridge_down）；"
          f"说明逃逸只发生在 `ensure_location` 内部那次**未被保护**的 `snap()`（实测 {escaped3!r}）")


def c7_on_farm_unchanged() -> None:
    """C7 人在农场时逐字不改（同世界在两棵树上跑，产物存 JSON 供比对）。"""
    w = TL.DryTilesWorld(seeds=0, money=0, weeds=0, water_left=40, with_dry_tiles=True)
    w.dirt.add(FAR)
    w.crops[FAR] = {"watered": False, "ripe": False}
    w.player_tile = [62, 14]
    w.location = "Farm"
    w.is_outdoor_farm = True
    c = T108Client(w, goto="ok")
    run = run_real(w, c, days=1)
    A.report("C7 人在农场（pre/post 对照）", run)
    e = last_end(run)
    art = {
        "water_far": [{k: v for k, v in x.items() if k not in ("t", "receipt")} for x in ev(run, "water_far")],
        "goto_farm": [x for x in ev(run, "goto_farm") if x.get("where") != "day_start_retry"],
        "water_far_skipped": ev(run, "water_far_skipped"),
        "day_end_checks": e.get("checks"),
        "day_end_ended_by": e.get("ended_by"),
        "day_end_ok_steps": e.get("ok_steps"),
        "watered_tiles": [list(t) for t in w.watered_tiles],
        "has_flag": hasattr(run, "water_far_not_on_farm"),
    }
    tag = os.environ.get("T108_TAG") or ("pre" if "pre" in str(ROOT) else "post")
    out = _here / f"_t108_c7_{tag}.json"
    out.write_text(json.dumps(art, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"  C7 产物写出：{out}")


CASES = {
    "b1": b1_run8_day12, "b2": b2_return_ok,
    "c1": c1_fake_on_farm, "c2": c2_multi_day_bounded, "c3": c3_not_on_farm_vs_given_up,
    "c4": c4_zero_action_no_loop, "c5": c5_flag_not_sticky_poison, "c6": c6_ensure_raises,
    "c7": c7_on_farm_unchanged,
}


def main() -> None:
    want = [a.lower() for a in sys.argv[1:]] or list(CASES)
    print(f"ROOT={ROOT}")
    for name in want:
        fn = CASES.get(name)
        if fn is None:
            print(f"?? 未知用例 {name}")
            continue
        print(f"\n=== {name.upper()} ===")
        fn()
    bad = [m for ok, m in CHECKS if not ok]
    print(f"\n=== 汇总：{len(CHECKS) - len(bad)}/{len(CHECKS)} PASS ===")
    for m in bad:
        print(f"  FAIL: {m}")


if __name__ == "__main__":
    main()
