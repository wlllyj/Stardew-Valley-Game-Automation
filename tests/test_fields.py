# -*- coding: utf-8 -*-
"""田区/作业区（`brain\\agentfarm\\fields.py`）的离线单元测试。

原则与 `tests\\test_runner.py` / `tests\\test_watchdog.py` 一致：**不连游戏、不发网络请求**。
观测用合成 dict（字段名照抄协议 §5 的真机结构），于是每个分支都能在毫秒级断言。
这里刻意**不 import `agentfarm.bridge`**：`fields.py` 必须是纯计算
（没有网络、没有时钟、没有随机），一旦它哪天开始依赖桥接层，
这组测试会在 import 处直接失败——那正是我们想要的告警。

【为什么用合成观测而不是真机 dump】真机快照随存档/季节/玩家位置变化，
断言只能写得又松又脆；合成观测才能把"边界怎么切、并列怎么破、贴边怎么裁"钉死。

覆盖点：
  1. 2×2 分区命名与象限（x 越小越西、y 越小越北，不硬编码坐标）；
  2. 坐标包络只来自 tiles[] ∪ tillable[]；
  3. 非户外农场 → []；
  4. tilesTruncated → 返回的 note 必须承认数据不完整；
  5. 玩家位置变了 → choose_zone(prefer="nearest") 跟着变；
  6. choose_zone 并列 → 按 name 字典序稳定、与列表顺序无关；
  7. resolve_zone 别名命中与失败返回 None（绝不抛异常）；
  8. zone_brief_lines / area_hint_text **不含任何坐标**（正则断言）；
  9. plot_in_zone 的格数与越界裁剪；
 10. 空区/空观测的诚实处理；
 11. 统计数字与 tillable[]/tiles[] 完全一致（不猜、不造）；
 12. 锚点优先级：可锄最多 → 要干的活最多 → 最靠左上，且可复现。

运行：`python -m unittest discover -s tests -v`
"""

from __future__ import annotations

import re
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "brain"))

from agentfarm import fields as fields_mod  # noqa: E402  # 反事实测试要临时替换模块级常量
from agentfarm.fields import (  # noqa: E402
    BLOCKER_KINDS,
    CLUMP_KIND,
    CLUMP_SUBKINDS,
    ZONE_BLOCKER_KINDS,
    Zone,
    area_hint_text,
    choose_zone,
    normalize_hint,
    plot_in_zone,
    resolve_zone,
    zone_blockers_total,
    zone_brief_lines,
    zone_unknown_total,
    zones_from_observe,
)

#: 形如 `[12,34]` 或 `12,34` 的坐标串。简报里出现任何一种都算违规。
COORD_RE = re.compile(r"\[\s*-?\d+\s*,\s*-?\d+\s*\]|-?\d+\s*,\s*-?\d+")


def make_tile(x: int, y: int, kind: str = "dirt", **kw) -> dict:
    """一个 TileView。字段就是协议 §5 的那几个，一个不多一个不少。"""
    tv = {"tile": [x, y], "kind": kind, "tool": "hoe", "objId": None, "feature": None,
          "standable": True, "actionable": False, "crop": None, "ripe": False,
          "dead": False, "watered": False, "plantable": False}
    tv.update(kw)
    return tv


def farm_obs(*, x0: int = -10, y0: int = -10, x1: int = 9, y1: int = 9,
             player=(-9, -9), kinds=None, crops=None, tillable=None,
             outdoor: bool = True, truncated: bool = False, tile_xs=None,
             name: str = "Farm") -> dict:
    """合成一份 `observe("full")` 快照。

    * `tile_xs` 只给某些列铺 tiles[]（模拟观测覆盖不全）；
    * `kinds` 覆盖 kind；`crops` 是 {(x,y): watered}；`tillable` 直接进 tillable[]；
    * `player=None` 模拟玩家坐标缺失。
    """
    kinds = dict(kinds or {})
    crops = dict(crops or {})
    xs = list(tile_xs) if tile_xs is not None else list(range(x0, x1 + 1))
    tiles: dict[tuple[int, int], dict] = {}
    for y in range(y0, y1 + 1):
        for x in xs:
            tiles[(x, y)] = make_tile(x, y, kind=kinds.get((x, y), "dirt"))
    for xy, watered in crops.items():
        xy = tuple(xy)
        tv = tiles.get(xy) or make_tile(xy[0], xy[1])
        tv["crop"] = "24"          # 作物 id 非空即"这格有作物"
        tv["watered"] = bool(watered)
        tiles[xy] = tv
    return {
        "schema": "agentfarm-world/6",
        "location": {
            "name": name,
            "isOutdoorFarm": bool(outdoor),
            "tiles": list(tiles.values()),
            "tilesTruncated": bool(truncated),
            "tillable": [list(t) for t in (tillable or [])],
            "doors": [],
        },
        "player": {} if player is None else {"tile": list(player)},
        "clock": {"year": 1, "season": "spring", "day": 6, "timeOfDay": 610},
    }


def zone_named(zones: list[Zone], name: str) -> Zone:
    for z in zones:
        if z.name == name:
            return z
    raise AssertionError(f"没有 {name} 这个区：{[z.name for z in zones]}")


def bare_zone(name: str, bounds=(0, 0, 0, 0), **kw) -> Zone:
    """手搓一个 Zone，用来测"与观测无关"的纯逻辑（选区/并列）。"""
    base = {"label": "测试区", "tillable": 0, "blockers": 0, "crops": 0,
            "unwatered": 0, "distance": 0}
    base.update(kw)
    return Zone(name=name, bounds=bounds, **base)


class ZonesFromObserveTest(unittest.TestCase):
    """① 分区命名/象限 ② 坐标包络 ③ 非农场 ⑪ 统计一致性 ⑮ 空区省略。"""

    def test_split2_names_and_quadrants(self):
        zones = zones_from_observe(farm_obs(tillable=[(-9, -9)]), split=2)
        self.assertEqual([z.name for z in zones],
                         ["field_nw", "field_ne", "field_sw", "field_se"])
        self.assertEqual([z.label for z in zones],
                         ["农场西北田区", "农场东北田区", "农场西南田区", "农场东南田区"])
        nw, ne, sw, se = zones
        # 20×20 的包络 -10..9：split=2 切成 [-10,-1] 与 [0,9]
        self.assertEqual(nw.bounds, (-10, -10, -1, -1))
        self.assertEqual(ne.bounds, (0, -10, 9, -1))
        # y 越小越北：北半区的 y1 必须严格小于南半区的 y0（不重叠、不留缝）
        self.assertLess(nw.bounds[3], sw.bounds[1])
        self.assertEqual(sw.bounds[1], nw.bounds[3] + 1)
        # x 越小越西：西半区的 x1 必须严格小于东半区的 x0
        self.assertLess(nw.bounds[2], ne.bounds[0])
        self.assertEqual(ne.bounds[0], nw.bounds[2] + 1)
        self.assertEqual(se.bounds, (0, 0, 9, 9))
        for z in zones:
            self.assertRegex(z.name, r"^[a-z0-9_]+$")   # id 只用小写/数字/下划线

    def test_bounds_envelope_comes_from_tiles_and_tillable(self):
        # tiles[] 只有 0..4，但 tillable[] 里有一个 (10,10)：包络必须吃掉它
        obs = farm_obs(x0=0, y0=0, x1=4, y1=4, player=(0, 0), tillable=[(10, 10)])
        zones = zones_from_observe(obs, split=1)
        self.assertEqual([z.name for z in zones], ["field_all"])
        self.assertEqual(zones[0].bounds, (0, 0, 10, 10))
        self.assertEqual(zones[0].tillable, 1)
        self.assertEqual(zones[0].label, "农场全境田区")
        # 只给两列 tiles[]：包络仍然等于真实出现过的坐标的 min/max
        obs2 = farm_obs(x0=-6, y0=-6, x1=6, y1=6, player=(0, 0), tile_xs=[-6, 6])
        self.assertEqual(zones_from_observe(obs2, split=1)[0].bounds, (-6, -6, 6, 6))
        self.assertEqual(len(zones_from_observe(obs2, split=2)), 4)

    def test_non_outdoor_farm_returns_empty(self):
        self.assertEqual(zones_from_observe(farm_obs(outdoor=False)), [])
        self.assertEqual(zones_from_observe(farm_obs(name="FarmHouse", outdoor=False)), [])
        # isOutdoorFarm 缺失（旧 Mod 快照）当"不是户外农场"，不能瞎切
        self.assertEqual(zones_from_observe({"location": {"name": "FarmHouse"}}), [])
        self.assertEqual(zones_from_observe({}), [])
        self.assertEqual(zones_from_observe(None), [])
        # 户外农场但一个格都没看到 → 给不出区，而不是给空壳
        self.assertEqual(zones_from_observe(
            {"location": {"isOutdoorFarm": True, "tiles": [], "tillable": []}}), [])
        with self.assertRaises(ValueError):
            zones_from_observe(farm_obs(), split=0)

    def test_counts_come_from_tillable_and_tiles(self):
        obs = farm_obs(
            tillable=[(-9, -9), (-8, -9), (-9, -8), (5, 5), (6, 6)],
            kinds={(2, -8): "weed", (3, -8): "stone", (4, -8): "tree",
                   (0, 0): "bush", (-1, 0): "twig", (0, 5): "grass"},
            crops={(-3, 2): True, (-2, 2): False, (1, 1): True},
        )
        zones = zones_from_observe(obs, split=2)
        nw, ne, sw, se = zones
        self.assertEqual((nw.tillable, nw.blockers, nw.crops, nw.unwatered), (3, 0, 0, 0))
        self.assertEqual((ne.tillable, ne.blockers, ne.crops, ne.unwatered), (0, 3, 0, 0))
        self.assertEqual((sw.tillable, sw.blockers, sw.crops, sw.unwatered), (0, 1, 2, 1))
        self.assertEqual((se.tillable, se.blockers, se.crops, se.unwatered), (2, 1, 1, 0))
        # 分区统计必须"守恒"：一格被算进两个区或漏掉都会在这里露馅
        self.assertEqual(sum(z.tillable for z in zones), 5)
        self.assertEqual(sum(z.blockers for z in zones), 5)
        self.assertEqual(sum(z.crops for z in zones), 3)
        self.assertEqual(sum(z.unwatered for z in zones), 1)
        # 待清理只认这几类；grass/dirt 不是"要清理的东西"
        self.assertIn("weed", BLOCKER_KINDS)
        self.assertNotIn("grass", BLOCKER_KINDS)
        self.assertNotIn("dirt", BLOCKER_KINDS)

    def test_bands_without_observation_are_omitted(self):
        # 只给 x=-10/-9/-8 与 x=9 四列：中间那一列带里一个格都没有 → 该列的分区省略
        obs = farm_obs(player=(0, 0), tile_xs=[-10, -9, -8, 9])
        zones = zones_from_observe(obs, split=3)
        names = [z.name for z in zones]
        self.assertEqual(names, ["field_nw", "field_ne", "field_cw",
                                 "field_ce", "field_sw", "field_se"])
        self.assertNotIn("field_nc", names)
        self.assertNotIn("field_cc", names)
        self.assertNotIn("field_sc", names)
        for z in zones:                      # 空区间（首尾反了）的区绝不能出现在结果里
            self.assertLessEqual(z.bounds[0], z.bounds[2])
            self.assertLessEqual(z.bounds[1], z.bounds[3])
        self.assertEqual(zone_named(zones, "field_cw").label, "农场西部田区")


class ChooseZoneTest(unittest.TestCase):
    """⑤ 距离随玩家变 ⑥ 并列按名字稳定 ④ 空输入的确定性兜底。"""

    def test_nearest_follows_player(self):
        west = zones_from_observe(farm_obs(player=(-9, -9)), split=2)
        east = zones_from_observe(farm_obs(player=(8, 8)), split=2)
        self.assertEqual(choose_zone(west, prefer="nearest").name, "field_nw")
        self.assertEqual(choose_zone(east, prefer="nearest").name, "field_se")
        # 同名的区在两份观测里距离不同 —— 说明确实是"跟着玩家走"而不是"总挑名字最小的"
        self.assertEqual(zone_named(west, "field_nw").distance, 6)
        self.assertEqual(zone_named(east, "field_nw").distance, 28)
        self.assertLess(zone_named(west, "field_nw").distance,
                        zone_named(west, "field_se").distance)

    def test_choose_zone_prefers(self):
        obs = farm_obs(tillable=[(-9, -8), (-8, -9), (5, 5)],
                       crops={(-9, -9): True, (1, -9): True, (-9, 1): True})
        zones = zones_from_observe(obs, split=2)
        self.assertEqual(choose_zone(zones, prefer="most_tillable").name, "field_nw")
        self.assertEqual(choose_zone(zones, prefer="empty").name, "field_se")
        self.assertIsNone(choose_zone([], prefer="nearest"))
        with self.assertRaises(ValueError):
            choose_zone(zones, prefer="脑筋急转弯")

    def test_choose_zone_ties_break_by_name(self):
        zones = [bare_zone("field_sw"), bare_zone("field_ne"), bare_zone("field_nw")]
        for prefer in ("nearest", "most_tillable", "empty"):
            self.assertEqual(choose_zone(zones, prefer=prefer).name, "field_ne", prefer)
        # 与列表顺序无关：只依赖输入内容
        self.assertEqual(choose_zone(list(reversed(zones)), prefer="nearest").name, "field_ne")
        self.assertEqual(choose_zone(list(reversed(zones)), prefer="empty").name, "field_ne")


class ResolveZoneTest(unittest.TestCase):
    """⑦ 别名与失败返回 None。"""

    def setUp(self):
        self.zones = zones_from_observe(farm_obs(tillable=[(-9, -9)]), split=2)

    def test_resolve_zone_aliases(self):
        for hint in ("field_nw", "FIELD_NW", " nw ", "northwest", "north_west",
                     "west_north", "西北", "西北角", "西北田区", "农场西北田区",
                     "anchor: field_nw", "锚点：field_nw"):
            got = resolve_zone(hint, self.zones)
            self.assertIsNotNone(got, hint)
            self.assertEqual(got.name, "field_nw", hint)
        self.assertEqual(resolve_zone("field_ne（东北）", self.zones).name, "field_ne")
        self.assertEqual(resolve_zone("south_east", self.zones).name, "field_se")
        self.assertEqual(resolve_zone("se", self.zones).name, "field_se")
        self.assertEqual(resolve_zone("field_all", self.zones), None)

    def test_resolve_zone_failures_return_none(self):
        for bad in (None, "", "   ", "north", "field_xx", "火星", "12,34", 123, "[]"):
            self.assertIsNone(resolve_zone(bad, self.zones), repr(bad))
        self.assertIsNone(resolve_zone("field_nw", []))       # 没有区可解析
        # 解析不出来必须是 None 而**不是**抛异常：调用方要能安全退回 choose_zone()
        self.assertEqual(choose_zone(self.zones, prefer="nearest").name, "field_nw")

    def test_normalize_hint(self):
        self.assertEqual(normalize_hint(None), "")
        self.assertEqual(normalize_hint(""), "")
        self.assertEqual(normalize_hint("   "), "")
        self.assertEqual(normalize_hint(" Anchor: field_NW "), "field_nw")
        self.assertEqual(normalize_hint("锚点：field_nw"), "field_nw")
        self.assertEqual(normalize_hint("field-nw!!"), "fieldnw")
        self.assertEqual(normalize_hint("field_nw（西北）"), "field_nw西北")


class BriefTextTest(unittest.TestCase):
    """⑧ 简报/方向文本不含坐标（LLM 只能选方向，坐标归代码）。"""

    def test_brief_and_hint_carry_no_coordinates(self):
        obs = farm_obs(tillable=[(-9, -9), (5, 5)], crops={(-3, 2): False}, player=(3, 3))
        zones = zones_from_observe(obs, split=2)
        lines = zone_brief_lines(zones)
        self.assertEqual(len(lines), len(zones))
        self.assertEqual(
            lines[0],
            "field_nw 农场西北田区：可锄 1 格、待清理 0 格、已有作物 0 格、"
            "待浇水 0 格、离你约 18 格",
        )
        both = "\n".join(lines) + "\n" + area_hint_text(zones)
        self.assertIsNone(COORD_RE.search(both), both)
        self.assertIn("field_nw", area_hint_text(zones))
        self.assertIn("农场西北田区", area_hint_text(zones))
        self.assertIn("field_se", area_hint_text(zones))

    def test_empty_hint_text(self):
        self.assertIsNone(COORD_RE.search(area_hint_text([])))
        self.assertEqual(zone_brief_lines([]), [])
        self.assertIn("没有可用的田区", area_hint_text([]))


class PlotInZoneTest(unittest.TestCase):
    """⑨ 格数与裁剪 ⑩ 空区 ④ 截断提示 ⑫ 锚点优先级。"""

    def test_plot_in_zone_full_block(self):
        obs = farm_obs(tillable=[(-9, -9), (-8, -9), (-9, -8)])
        zones = zones_from_observe(obs, split=2)
        nw = zone_named(zones, "field_nw")
        plot = plot_in_zone(nw, obs, size=5)
        self.assertEqual(len(plot["tiles"]), 25)          # 装得下就一格不少
        self.assertEqual(plot["anchor"], [-10, -10])      # 并列时取最靠左上
        self.assertEqual(sorted(map(tuple, plot["tillable"])),
                         [(-9, -9), (-9, -8), (-8, -9)])
        self.assertEqual(plot["blockers"], [])
        self.assertEqual(plot["crops"], [])
        self.assertEqual(plot["unwatered"], [])
        self.assertIn("可锄 3", plot["note"])
        self.assertIn("共 25 格", plot["note"])
        # 同样的输入必须给出同样的输出（无人值守时"稳定"比"聪明"重要）
        self.assertEqual(plot, plot_in_zone(nw, obs, size=5))
        with self.assertRaises(ValueError):
            plot_in_zone(nw, obs, size=0)

    def test_plot_in_zone_clips_at_zone_edge(self):
        obs = farm_obs(x0=0, y0=0, x1=2, y1=2, player=(0, 0), tillable=[(0, 0)])
        narrow = bare_zone("field_nw", bounds=(0, 0, 2, 2), tillable=1)
        plot = plot_in_zone(narrow, obs, size=5)
        self.assertEqual(len(plot["tiles"]), 9)           # 5×5 装不进 3×3，裁到 9 格
        self.assertEqual(plot["anchor"], [0, 0])
        self.assertEqual(plot["tillable"], [[0, 0]])
        self.assertIn("裁剪", plot["note"])
        self.assertIn("16", plot["note"])                 # 越界 16 格，明说而不是假装
        self.assertEqual(plot_in_zone(narrow, obs, size=1)["tiles"], [[0, 0]])

    def test_anchor_prefers_tillable_then_work(self):
        # nw 左上角一堆杂草 vs 右下角两个可锄格：可锄优先（第一权重）
        obs = farm_obs(tillable=[(-3, -3), (-3, -2)],
                       kinds={(-10, -10): "weed", (-9, -10): "weed", (-8, -10): "weed"})
        nw = zone_named(zones_from_observe(obs, split=2), "field_nw")
        plot = plot_in_zone(nw, obs, size=3)
        self.assertEqual(plot["anchor"], [-5, -4])
        self.assertEqual(sorted(map(tuple, plot["tillable"])), [(-3, -3), (-3, -2)])
        self.assertEqual(plot["blockers"], [])            # 没跑去框那三个杂草
        # 该区没有可锄格时，才轮到"这次要处理的格最多"
        obs2 = farm_obs(kinds={(-10, -10): "weed", (-9, -10): "weed", (-8, -10): "weed"})
        nw2 = zone_named(zones_from_observe(obs2, split=2), "field_nw")
        plot2 = plot_in_zone(nw2, obs2, size=3)
        self.assertEqual(plot2["tillable"], [])
        self.assertEqual(sorted(map(tuple, plot2["blockers"])),
                         [(-10, -10), (-9, -10), (-8, -10)])
        for x, y in plot2["tiles"]:                       # 落点必须在区内
            self.assertTrue(-10 <= x <= -1 and -10 <= y <= -1)

    def test_truncated_snapshot_is_declared_incomplete(self):
        obs = farm_obs(truncated=True, tillable=[(-9, -9)])
        nw = zone_named(zones_from_observe(obs, split=2), "field_nw")
        note = plot_in_zone(nw, obs, size=3)["note"]
        self.assertIn("截断", note)
        self.assertIn("不完整", note)
        # 没截断时不许哭穷
        obs_ok = farm_obs(tillable=[(-9, -9)])
        nw_ok = zone_named(zones_from_observe(obs_ok, split=2), "field_nw")
        self.assertNotIn("截断", plot_in_zone(nw_ok, obs_ok, size=3)["note"])

    def test_unknown_cells_are_disclosed(self):
        # tiles[] 只覆盖西边三列和最东一列（等于只看了地块两端），(0,0) 是唯一可锄格：
        # 于是锚点必然落在 (0,0)，而它那块 5×5 里绝大多数格子本次观测没返回——
        # note 必须如实说明，不能让调用方以为"这 25 格都看过了"。
        obs = farm_obs(x0=-10, y0=-10, x1=4, y1=4, player=(-9, -9),
                       tile_xs=[-10, -9, -8, 4], tillable=[(0, 0)])
        zone = zones_from_observe(obs, split=1)[0]
        self.assertEqual(zone.bounds, (-10, -10, 4, 4))
        plot = plot_in_zone(zone, obs, size=5)
        self.assertEqual(plot["anchor"], [0, 0])
        self.assertEqual(len(plot["tiles"]), 25)          # 全在区内，一格没裁
        known = {(x, y) for x in (-10, -9, -8, 4) for y in range(-10, 5)} | {(0, 0)}
        unknown = [c for c in map(tuple, plot["tiles"]) if c not in known]
        self.assertEqual(len(unknown), 19)         # 25 格里只有 6 格本次观测见过
        self.assertIn("没返回", plot["note"])
        self.assertIn(str(len(unknown)), plot["note"])
        self.assertEqual(plot["tillable"], [[0, 0]])

    def test_empty_zone_is_reported_not_faked(self):
        obs = farm_obs(tillable=[(-9, -9)])
        far = bare_zone("field_se", bounds=(100, 100, 110, 110))
        plot = plot_in_zone(far, obs, size=5)
        self.assertIsNone(plot["anchor"])
        for key in ("tiles", "tillable", "blockers", "crops", "unwatered"):
            self.assertEqual(plot[key], [], key)
        self.assertIn("没有任何已观测到的格", plot["note"])
        # bounds 首尾反了（空区间）也不能抛异常
        broken = bare_zone("field_x", bounds=(5, 5, 1, 1))
        self.assertIsNone(plot_in_zone(broken, obs)["anchor"])
        self.assertIn("空区间", plot_in_zone(broken, obs)["note"])
        # 观测里一个格都没有：不给区、也不给作业区
        nothing = farm_obs(x0=0, y0=0, x1=0, y1=0, tile_xs=[])
        self.assertEqual(zones_from_observe(nothing, split=2), [])
        self.assertEqual(plot_in_zone(bare_zone("field_all", bounds=(0, 0, 4, 4)), nothing)["anchor"], None)

    def test_missing_player_tile_still_deterministic(self):
        with_player = zones_from_observe(farm_obs(player=(0, 0)), split=2)
        without = zones_from_observe(farm_obs(player=None), split=2)
        self.assertEqual([z.distance for z in without], [z.distance for z in with_player])
        self.assertEqual(choose_zone(without, prefer="nearest").name,
                         choose_zone(with_player, prefer="nearest").name)


class ZoneBlockerKindsTest(unittest.TestCase):
    """【0.7.48 P0-1 / D1】作业区"待清理"口径必须认得 ResourceClump 的**真实承载位**
    `tiles[].kind == "clump"`（不是 `clumpKind` 的子树类型），且 tilesTruncated 时 fail-closed。"""

    def test_zone_blocker_kinds_is_superset_of_blocker_kinds(self):
        """基本口径不回归：BLOCKER_KINDS 全在、`clump` 也在。"""
        self.assertTrue(BLOCKER_KINDS <= ZONE_BLOCKER_KINDS,
                        f"ZONE_BLOCKER_KINDS 必须包含 BLOCKER_KINDS：{sorted(ZONE_BLOCKER_KINDS)}")
        self.assertIn("clump", ZONE_BLOCKER_KINDS)

    def test_clump_carrier_is_tile_kind_not_clumpkind(self):
        """**漂移钉**：我们认的 clump 承载位 = `tiles[].kind` 的字面量 `"clump"`。

        Mod 侧证据（纯 Python 不便 import C#，靠这条钉 + 源码注释防漂移）：
          * `mod/AgentFarm.Bridge/WorldSnapshot.cs:807`：
            `else if (tf is StardewValley.TerrainFeatures.ResourceClump clump)
             { t.Kind = "clump"; FillClumpMeta(t, clump); }`  —— 大障碍的 kind 恒为 `"clump"`；
          * `mod/AgentFarm.Bridge/Contracts.cs:590`（kind 取值表含 `clump`）与
            `:598`（"只有 `kind="clump"` 时才填 clump* 元数据"）；
          * `mod/AgentFarm.Bridge/ClumpMeta.cs:38-73 KindOf()` 只返回
            `stump`/`log`/`boulder`/`rockPile`/`greenRain`/`unknown` —— **永不返回 `"clump"`**。

        ⇒ 若哪天有人把 `clumpKind` 的子类型当成 `kind`（D1 就是这么发生的）塞进这个集合，
        这条会红。
        """
        self.assertEqual(CLUMP_KIND, "clump")
        self.assertIn(CLUMP_KIND, ZONE_BLOCKER_KINDS)
        # clumpKind 的取值（含 unknown）**不是** tiles[].kind 的取值 ⇒ 一个都不许混进来。
        self.assertEqual(ZONE_BLOCKER_KINDS & CLUMP_SUBKINDS, frozenset(),
                         "clumpKind 的子类型是 clumpKind 的取值，不是 kind —— D1 就是错把它们当 kind")

    def test_zones_from_observe_counts_clump_tiles_as_blockers(self):
        """回归守卫：区内只剩大障碍（kind="clump"）时 blockers 必须 > 0（旧的死代码会报 0）。"""
        obs = farm_obs(kinds={(0, 0): "clump", (1, 0): "clump"})
        zones = zones_from_observe(obs, split=2)
        self.assertEqual(sum(z.blockers for z in zones), 2,
                         "大障碍（ResourceClump，kind=clump）必须计入 blockers")

    def test_zones_from_observe_counts_unknown_tiles(self):
        """Z3 回归：区内 kind=='unknown' 的格必须计入 Zone.unknown（曾静默忽略 ⇒ 假 PASS）。

        kind=='unknown' 不在 ZONE_BLOCKER_KINDS 桶里，旧代码直接跳过 ⇒ 区 blockers 报 0
        ⇒ 目标1② 假 PASS。现在单独计到 `unknown`，且不得污染 `blockers` 计数。
        """
        # split=2 下 field_nw = x∈[-10,-1] ∧ y∈[-10,-1]（西/北半区）。三格都落在 field_nw 内：
        # 两格 unknown（计入 unknown）、一格 weed（计入 blockers）。
        obs = farm_obs(kinds={(-1, -1): "unknown", (-2, -1): "unknown", (-1, -2): "weed"})
        nw = zone_named(zones_from_observe(obs, split=2), "field_nw")
        self.assertEqual(nw.unknown, 2, "两格 kind='unknown' 必须计入 Zone.unknown")
        self.assertEqual(nw.blockers, 1, "unknown 不得污染 blockers 计数")
        # 同时确认 zone_unknown_total 与 Zone.unknown 同口径。
        self.assertEqual(zone_unknown_total(nw, obs), 2)
        self.assertEqual(zone_blockers_total(nw, obs), 1)
        # 截断时 zone_unknown_total 必须 fail-closed 返回 None（不当 0）。
        obs_t = dict(obs)
        obs_t["location"] = dict(obs["location"]); obs_t["location"]["tilesTruncated"] = True
        self.assertIsNone(zone_unknown_total(nw, obs_t),
                          "tilesTruncated 时 unknown 也必须【无法判定】而非 0")

    def test_plot_in_zone_flags_clump_as_blocker(self):
        """plot_in_zone 的 blockers 名单也要含大障碍（与 zones_from_observe 同口径）。"""
        obs = farm_obs(kinds={(-10, -10): "clump", (-9, -10): "clump"})
        nw = zone_named(zones_from_observe(obs, split=2), "field_nw")
        plot = plot_in_zone(nw, obs, size=5)
        self.assertEqual(sorted(map(tuple, plot["blockers"])), [(-10, -10), (-9, -10)])

    def test_zone_blockers_total_counts_then_reports_zero_when_cleared(self):
        """清空前 > 0（含 clump）、清空后 == 0。"""
        obs_hot = farm_obs(kinds={(0, 0): "clump", (1, 0): "clump", (2, 0): "weed"})
        zone = zones_from_observe(obs_hot, split=1)[0]
        self.assertEqual(zone_blockers_total(zone, obs_hot), 3)
        obs_clear = farm_obs()                     # 同范围，全是 dirt
        self.assertEqual(zone_blockers_total(zone, obs_clear), 0)

    def test_zone_blockers_total_fail_closed_on_truncated(self):
        """tilesTruncated ⇒ None（调用方必须判【无法判定】），**绝不当 0**。"""
        zone = zones_from_observe(farm_obs(), split=1)[0]
        obs_trunc = farm_obs(kinds={(0, 0): "clump"}, truncated=True)
        self.assertIsNone(zone_blockers_total(zone, obs_trunc))
        # 反例：同样的观测但未截断时必须给得出数（证明是 truncated 令它 fail-closed）
        self.assertEqual(zone_blockers_total(zone, farm_obs(kinds={(0, 0): "clump"})), 1)

    def test_unknown_clumpkind_still_counts_as_blocker(self):
        """`clumpKind=="unknown"`（索引读不到/未知）的格**仍然算 blocker**：不知道用什么工具 ≠ 不存在。"""
        obs = farm_obs(kinds={(0, 0): "clump"})
        for t in obs["location"]["tiles"]:
            if t["tile"] == [0, 0]:
                t.update({"clumpKind": "unknown", "clumpTarget": None, "toolOk": None})
        zone = zones_from_observe(obs, split=1)[0]
        self.assertEqual(zone_blockers_total(zone, obs), 1)

    # ---- observer 的最小观测复现（scratch/observe_t15_d1_minobs.py）：同形态、同期望值 ----
    @staticmethod
    def _observer_minobs() -> dict:
        """observer 的最小观测：包络 0..19、split=2 ⇒ field_nw=(5,5)+(6,5)、field_ne=(15,5)+(15,6)。

        承载位一律是 `tiles[].kind == "clump"`；`clumpKind` 只作"是用什么工具"的原因说明，
        **不参与任何判定**（脑侧从不读 clumpKind）。tillable 与 observer 脚本一致铺 0..19 的两行。
        """
        kinds = {(5, 5): "clump", (6, 5): "weed", (15, 5): "stone", (15, 6): "clump"}
        tillable = [[x, y] for x in range(0, 20) for y in (0, 19)]
        obs = farm_obs(x0=0, y0=0, x1=19, y1=19, kinds=kinds, tillable=tillable)
        meta = {(5, 5): {"clumpKind": "stump", "clumpIndex": 600, "toolOk": True},
                (15, 6): {"clumpKind": "boulder", "clumpIndex": 672, "toolOk": False}}
        for t in obs["location"]["tiles"]:
            m = meta.get(tuple(t["tile"]))
            if m:
                t.update(m)
        return obs

    def test_observer_minobs_two_blockers_per_zone(self):
        """observer 实测（照抄）：field_nw={clump/stump, weed}=2、field_ne={stone, clump/boulder}=2。"""
        obs = self._observer_minobs()
        zones = {z.name: z for z in zones_from_observe(obs, split=2)}
        self.assertEqual(zones["field_nw"].blockers, 2, "field_nw 两格障碍（clump 必须计入）")
        self.assertEqual(zones["field_ne"].blockers, 2, "field_ne 两格障碍（clump 必须计入）")
        self.assertEqual(zones["field_sw"].blockers, 0)
        self.assertEqual(zones["field_se"].blockers, 0)
        self.assertEqual(zone_blockers_total(zones["field_nw"], obs), 2)
        self.assertEqual(zone_blockers_total(zones["field_ne"], obs), 2)

    def test_observer_minobs_truncated_reports_none(self):
        """observer 实测：tilesTruncated=True ⇒ zone_blockers_total 四个区一律 None（不许当 0）。"""
        obs = self._observer_minobs()
        obs["location"]["tilesTruncated"] = True
        zones = {z.name: z for z in zones_from_observe(obs, split=2)}
        for name in ("field_nw", "field_ne", "field_sw", "field_se"):
            self.assertIsNone(zone_blockers_total(zones[name], obs),
                              f"{name} 截断时必须【无法判定】而不是给一个数")

    def test_observer_minobs_counterfactual_old_set_misses_clump(self):
        """红/绿对照（反事实）：把 ZONE_BLOCKER_KINDS 换回 D1 之前的集合（误把 clumpKind 的
        子类型当 kind）⇒ nw/ne 各掉 1 —— 如实复现 observer 说的"现在是 1"；还原后回到 2。"""
        obs = self._observer_minobs()
        old = frozenset(BLOCKER_KINDS | {"stump", "log", "boulder", "rockPile", "greenRain"})
        saved = fields_mod.ZONE_BLOCKER_KINDS
        try:
            fields_mod.ZONE_BLOCKER_KINDS = old
            zones = {z.name: z for z in zones_from_observe(obs, split=2)}
            self.assertEqual(zones["field_nw"].blockers, 1, "D1 缺口：只剩 weed 一格（clump 漏计）")
            self.assertEqual(zones["field_ne"].blockers, 1, "D1 缺口：只剩 stone 一格（clump 漏计）")
        finally:
            fields_mod.ZONE_BLOCKER_KINDS = saved
        # 还原后必须回到 2 —— 证明这 1 的差确实只来自那个集合。
        zones = {z.name: z for z in zones_from_observe(obs, split=2)}
        self.assertEqual(zones["field_nw"].blockers, 2)
        self.assertEqual(zones["field_ne"].blockers, 2)


class VerifyZoneRetentionCliTest(unittest.TestCase):
    """P0-3 工具 `tools/verify-zone-retention.py` 的 rc 语义（只读观测，不采信 journal）。"""

    def _run(self, before: dict, after: dict, *extra: str):
        import json
        import subprocess
        import tempfile
        tool = Path(__file__).resolve().parents[1] / "tools" / "verify-zone-retention.py"
        with tempfile.TemporaryDirectory() as tmp:
            b = Path(tmp) / "b.json"
            a = Path(tmp) / "a.json"
            b.write_text(json.dumps(before, ensure_ascii=False), encoding="utf-8")
            a.write_text(json.dumps(after, ensure_ascii=False), encoding="utf-8")
            p = subprocess.run([sys.executable, str(tool), "--before", str(b), "--after", str(a), *extra],
                               capture_output=True, text=True, encoding="utf-8")
        return p.returncode, (p.stdout or "")

    def test_retained_clear_passes(self):
        obs = farm_obs()
        rc, out = self._run(obs, obs, "--zone", "field_nw")
        self.assertEqual(rc, 0, out)
        self.assertIn("PASS (retained clear)", out)

    def test_blockers_mean_fail(self):
        # (-5,-5) 落在 field_nw 内（split=2 的西/北半区）
        rc, out = self._run(farm_obs(kinds={(-5, -5): "clump"}), farm_obs(kinds={(-5, -5): "clump"}),
                            "--zone", "field_nw")
        self.assertEqual(rc, 1, out)
        self.assertIn("FAIL", out)

    def test_truncated_is_undecidable_not_pass(self):
        rc, out = self._run(farm_obs(truncated=True), farm_obs(truncated=True), "--zone", "field_nw")
        self.assertEqual(rc, 1, out)
        self.assertIn("【无法判定】tilesTruncated", out)

    def test_unknown_tile_after_blocks_pass(self):
        """Z3 回归：after 观测里残留 kind=='unknown' 格 ⇒ 工具必须 FAIL（exit=1），不能声明"清空并保持"。"""
        # before/after 都把 field_nw 内一格置为 unknown（blockers 均为 0）。
        rc, out = self._run(farm_obs(kinds={(-5, -5): "unknown"}),
                            farm_obs(kinds={(-5, -5): "unknown"}),
                            "--zone", "field_nw")
        self.assertEqual(rc, 1, out)
        self.assertIn("FAIL", out)
        self.assertIn("unknown tile present, cannot claim cleared", out)

    def test_unknown_tile_in_other_zone_does_not_fail_this_zone(self):
        """对照：unknown 落在 field_se（与 field_nw 无关）、field_nw 全清（含 unknown=0）⇒ field_nw PASS。"""
        before = farm_obs(kinds={(5, 5): "unknown"})   # (5,5) 落在 field_se
        after = farm_obs(kinds={(5, 5): "unknown"})
        rc, out = self._run(before, after, "--zone", "field_nw")
        self.assertEqual(rc, 0, out)
        self.assertIn("PASS (retained clear)", out)


if __name__ == "__main__":  # pragma: no cover
    unittest.main(verbosity=2)
