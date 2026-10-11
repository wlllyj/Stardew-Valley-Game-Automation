# -*- coding: utf-8 -*-
"""具名田区（zone）与作业区（plot）落点：把 LLM 的"大致方向"翻译成确定坐标。

【为什么需要这个文件】
旧流程（`tools\\run-plot.py` 的 `pick_plot`）拿"离玩家最近的可锄格"当左下角：
人走到哪、田就开到哪，**选区跟着角色漂移**，跑两遍落点不同，既没法规划也没法复盘。
这里把两件事拆开、各归其位：
  * **方向由 LLM 给**（哪片田区、多大一块、什么排列意图），它只需要吐出 "field_nw" 这类具名 id；
  * **坐标由代码算**（`zones_from_observe()` / `plot_in_zone()`），同样的观测 + 同样的名字必然得到同样的坐标。

【为什么绝对不能硬编码坐标】
农场布局随存档、季节、玩家改造而变，写死 (x,y) 换个存档/换块地就是错的。
所以本模块**一个坐标常量都没有**：边界一律由本次观测里真实出现过的格
（`location.tiles[]` ∪ `location.tillable[]`）求坐标包络（min/max）现算。
观测里没出现过的格，代码不会凭空造——`plot_in_zone()` 打分只用真实存在的格。

【为什么给 LLM 的简报不许带坐标】
简报里一旦出现 (12,34) 这种数字，模型就会把它当事实去推理、复述、微调，
下一轮很容易抄错（幻觉坐标），也把"谁负责规划"的边界弄混了：
坐标是代码的确定性产物，LLM 只在"方向"这一层做选择。
=> `zone_brief_lines()` / `area_hint_text()` 只输出具名 id、中文标签与格数，不输出任何坐标。

【确定性】
LLM 关掉、超时、给的名字解析不出来时，`choose_zone()` 按固定规则（可锄数 / 作物数 / 距离，
并列一律 name 字典序）给出选区，落点可复现——无人值守时"稳定"比"聪明"更重要。

【诚实性】
`location.tiles[]` 有 400 格上限、`location.tillable[]` 有 200 格上限（按离玩家距离排序后截断），
被截断时统计是**不完整**的。这种时候 `plot_in_zone()` 会在 note 里明说不完整，
绝不假装自己看到了整个农场。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

__all__ = [
    "BLOCKER_KINDS",
    "TILE_CAP",
    "TILLABLE_CAP",
    "Zone",
    "area_hint_text",
    "choose_zone",
    "normalize_hint",
    "plot_in_zone",
    "resolve_zone",
    "zone_brief_lines",
    "zones_from_observe",
]

#: 需要"先清理再谈耕种"的格：Mod 观测里 kind 的取值（协议 §5）。
BLOCKER_KINDS = frozenset({"weed", "stone", "twig", "tree", "bush"})

#: Mod 侧的上限（协议 §5）：达到上限说明快照只是"附近的一片"，不是整个农场。
TILE_CAP = 400
TILLABLE_CAP = 200

#: `choose_zone()` 支持的确定性偏好。
PREFERS = ("nearest", "most_tillable", "empty")


@dataclass(frozen=True)
class Zone:
    """一块具名田区。名字是稳定 id（小写字母/数字/下划线），坐标由代码算，不由 LLM 给。"""

    name: str                          # 稳定具名 id，如 "field_nw"
    label: str                         # 中文标签，如 "农场西北田区"
    bounds: tuple[int, int, int, int]  # x0, y0, x1, y1（闭区间，游戏格坐标）
    tillable: int                      # 该区里可锄格数（来自 location.tillable[]，不猜）
    blockers: int                      # 该区里待清理的格数（kind ∈ BLOCKER_KINDS）
    crops: int                         # 该区里已有作物的格数
    unwatered: int                     # 该区里"有作物且 watered=False"的格数
    distance: int                      # 该区中心到玩家的曼哈顿距离


# ---------------------------------------------------------------- 观测解读小工具

def _loc(obs: Any) -> dict:
    """取 obs["location"]；结构不符就返回空 dict（宁可当"没看到"，也不要抛异常打断循环）。"""
    if not isinstance(obs, dict):
        return {}
    loc = obs.get("location")
    return loc if isinstance(loc, dict) else {}


def _coord(raw: Any) -> tuple[int, int] | None:
    """把 [x,y] 解析成 (x,y)；形状不对返回 None。"""
    if not isinstance(raw, (list, tuple)) or len(raw) != 2:
        return None
    try:
        return (int(raw[0]), int(raw[1]))
    except (TypeError, ValueError):
        return None


def _tile_index(raw: Any) -> dict[tuple[int, int], dict]:
    """location.tiles[] → {坐标: TileView}；坐标残缺的条目直接丢，不编造。"""
    out: dict[tuple[int, int], dict] = {}
    for tv in raw or []:
        if not isinstance(tv, dict):
            continue
        xy = _coord(tv.get("tile"))
        if xy is not None:
            out[xy] = tv
    return out


def _coord_set(raw: Any) -> set[tuple[int, int]]:
    """location.tillable[] → 坐标集合（同样丢掉形状不对的条目）。"""
    out: set[tuple[int, int]] = set()
    for item in raw or []:
        xy = _coord(item)
        if xy is not None:
            out.add(xy)
    return out


def _player_tile(obs: Any) -> tuple[int, int]:
    """玩家所在格；拿不到就按 (0,0) 算。

    【为什么不用 None 往下传】`Zone.distance` 是 int 且直接参与 `choose_zone()` 排序；
    玩家坐标缺失属于观测异常，给一个确定缺省值比让排序悬空更好——
    缺坐标时所有区同向偏移，谁"最近"的**次序**仍然稳定。
    """
    pt = _coord(((obs or {}).get("player") or {}).get("tile")) if isinstance(obs, dict) else None
    return pt if pt is not None else (0, 0)


def _crop_id(tv: dict | None) -> str | None:
    """该格上的作物 id；没有（None/False/0/空串）返回 None。"""
    if not tv:
        return None
    v = tv.get("crop")
    if v is None or v is False:
        return None
    s = str(v).strip()
    if s in ("", "0", "none", "null", "false"):
        return None
    return s


def _bands(lo: int, hi: int, split: int) -> list[tuple[int, int]]:
    """把闭区间 [lo,hi] 均分成 split 段，返回每段的闭区间。

    【为什么用这种取整】不能整除时余数分给靠前的段，结果只依赖 (lo,hi,split)，
    任何机器上算出的分区都一样——这正是"同一份观测 → 同一批坐标"的前提。
    跨度比 split 还小时会出现空段（a > b），
    这种段里不可能有观测到的格，调用方会自然把它省略掉。
    """
    span = hi - lo + 1
    out: list[tuple[int, int]] = []
    for i in range(split):
        a = lo + (span * i) // split
        b = lo + (span * (i + 1)) // split - 1
        if out and a <= out[-1][1]:      # 保底：分区之间绝不重叠，避免一格被算进两个区
            a = out[-1][1] + 1
        out.append((a, b) if b >= a else (a, a - 1))
    return out


# ---------------------------------------------------------------- 具名与别名

# 分区方位词：n/s/e/w 与中（c）。y 越小越"北"（游戏里 y 向下增长），x 越小越"西"。
_ROW_CN = {"n": "北", "c": "中", "s": "南"}
_COL_CN = {"w": "西", "c": "中", "e": "东"}
_ORIENT_WORDS = {
    "n": ("n", "north"),
    "s": ("s", "south"),
    "e": ("e", "east"),
    "w": ("w", "west"),
    "c": ("c", "center", "centre", "central", "mid", "middle"),
}


def _row_tag(r: int, split: int) -> str:
    if split == 2:
        return ("n", "s")[r]
    if split == 3:
        return ("n", "c", "s")[r]
    return f"r{r}"


def _col_tag(c: int, split: int) -> str:
    if split == 2:
        return ("w", "e")[c]
    if split == 3:
        return ("w", "c", "e")[c]
    return f"c{c}"


def _zone_label(row_tag: str, col_tag: str) -> str:
    """中文标签。例：n+w → "农场西北田区"（给人看的，和 id 一样不含坐标）。

    【为什么东西在前】汉语说"西南/东北"而不是"南西/北东"，
    所以拼标签时先列方位字再列南北字；id 仍是"先行后列"（field_sw），两者互不影响。
    """
    r = _ROW_CN.get(row_tag)
    c = _COL_CN.get(col_tag)
    if r is None or c is None:
        return f"农场分区({row_tag}{col_tag})"
    if r == "中" and c == "中":
        return "农场中央田区"
    if r == "中":
        return f"农场{c}部田区"
    if c == "中":
        return f"农场{r}部田区"
    return f"农场{c}{r}田区"


_ANCHOR_PREFIX_RE = re.compile(r"^(?:anchor|锚点)\s*[:：=]\s*")
_PUNCT_RE = re.compile(r"[^0-9a-z_\u4e00-\u9fff]+")


def normalize_hint(hint: str) -> str:
    """把 LLM 给的方向文本规范化成"可比较的候选名"。

    做法与原因：转小写 → 去掉 `anchor:` / `锚点：` 这类前缀（协议里锚点是代码的活，
    模型有时会顺手写上）→ 去掉除小写字母、数字、下划线、汉字之外的一切（空格/括号/标点）。
    保留汉字是为了让"农场西北田区""西北"这种中文方向也能被 `resolve_zone()` 认出来。
    `None`/空串/纯标点 → `""`（调用方据此退回确定性选区，而不是去猜）。
    """
    if hint is None:
        return ""
    s = str(hint).strip().lower()
    s = _ANCHOR_PREFIX_RE.sub("", s)
    return _PUNCT_RE.sub("", s)


def _spellings(zone: Zone) -> tuple[str, ...]:
    """一个区可被怎样称呼（已按 `normalize_hint()` 的规则归一过）。

    覆盖三类写法：具名 id（field_nw / nw）、英文方位（northwest / north_west / wn）、
    中文（西北 / 西北田区 / 西北角 / 农场西北田区）。
    【为什么不加单个方位字母】单独一个 "n"/"west" 是**半场**而不是某一块区，
    硬塞进某一块只会把"北边"错解成"西北"，所以只登记"行+列"的组合写法；
    解析不出来就让调用方安全退回 `choose_zone()`。
    """
    out = {zone.name, zone.name.removeprefix("field_"), normalize_hint(zone.label)}
    label = normalize_hint(zone.label)
    if label.startswith("农场"):
        out.add(label[2:])

    m = re.fullmatch(r"field_([a-z])([a-z])", zone.name)
    if m:
        row, col = m.group(1), m.group(2)
        for rw in _ORIENT_WORDS.get(row, (row,)):
            for cw in _ORIENT_WORDS.get(col, (col,)):
                for sep in ("", "_"):
                    out.add(rw + sep + cw)
                    out.add(cw + sep + rw)      # 也有人写 west_north
        r_cn, c_cn = _ROW_CN.get(row), _COL_CN.get(col)
        if r_cn and c_cn:
            for combo in (r_cn + c_cn, c_cn + r_cn):
                out.update({combo, combo + "田区", combo + "角", combo + "部"})
    if zone.name == "field_all":
        out.update({"all", "全部", "整个农场", "全境", "全场"})
    return tuple(sorted(x for x in out if x))


# ---------------------------------------------------------------- 分区

def zones_from_observe(obs: dict, *, split: int = 2) -> list[Zone]:
    """把户外农场按 split×split 切成具名田区（split=2 → field_nw/ne/sw/se）。

    边界取 `location.tiles[]` ∪ `location.tillable[]` 的坐标包络再等分：
    **不硬编码任何坐标**，因为农场大小/形状随存档和玩家改造而变。
    非户外农场（`location.isOutdoorFarm` 为假或缺失）→ 返回 []：
    室内、矿洞、镇上谈"田区"没有意义，硬切只会给 LLM 一堆假方向。
    一个观测量都没有的区直接省略（不产出"可锄 0、待清理 0"的空壳去污染简报）。
    """
    if split < 1:
        raise ValueError(f"split 至少为 1，收到 {split!r}")
    loc = _loc(obs)
    if not loc.get("isOutdoorFarm"):
        return []
    tiles = _tile_index(loc.get("tiles"))
    till = _coord_set(loc.get("tillable"))
    known = set(tiles) | till
    if not known:
        return []

    xs = [c[0] for c in known]
    ys = [c[1] for c in known]
    xb = _bands(min(xs), max(xs), split)
    yb = _bands(min(ys), max(ys), split)

    # 先排好 (name, label, bounds)，再逐区统计；顺序按"北→南、西→东"，与简报阅读顺序一致。
    if split == 1:
        plan = [("field_all", "农场全境田区", (xb[0][0], yb[0][0], xb[0][1], yb[0][1]))]
    else:
        plan = []
        for r in range(split):
            for c in range(split):
                rt, ct = _row_tag(r, split), _col_tag(c, split)
                plan.append((f"field_{rt}{ct}", _zone_label(rt, ct),
                             (xb[c][0], yb[r][0], xb[c][1], yb[r][1])))

    pt = _player_tile(obs)
    zones: list[Zone] = []
    for name, label, (x0, y0, x1, y1) in plan:
        if x0 > x1 or y0 > y1:
            continue
        inside = [k for k in known if x0 <= k[0] <= x1 and y0 <= k[1] <= y1]
        if not inside:
            continue
        tillable = sum(1 for t in till if x0 <= t[0] <= x1 and y0 <= t[1] <= y1)
        blockers = 0
        crops = 0
        unwatered = 0
        for xy, tv in tiles.items():
            if not (x0 <= xy[0] <= x1 and y0 <= xy[1] <= y1):
                continue
            if tv.get("kind") in BLOCKER_KINDS:
                blockers += 1
            if _crop_id(tv) is not None:
                crops += 1
                if not tv.get("watered"):
                    unwatered += 1
        cx, cy = (x0 + x1) // 2, (y0 + y1) // 2
        zones.append(Zone(name=name, label=label, bounds=(x0, y0, x1, y1),
                          tillable=tillable, blockers=blockers, crops=crops,
                          unwatered=unwatered,
                          distance=abs(cx - pt[0]) + abs(cy - pt[1])))
    return zones


def zone_brief_lines(zones: list[Zone]) -> list[str]:
    """给人/LLM 看的紧凑清单，每区一行。

    **绝对不能包含任何坐标数字**：LLM 只会复述和微调它看到的数字，
    一旦坐标进了简报，模型就会开始"自己算坐标"，而那正是我们要收回的职责。
    这里只给具名 id、中文标签和四个格数，让模型在"方向"这一层做选择。
    """
    return [
        f"{z.name} {z.label}：可锄 {z.tillable} 格、待清理 {z.blockers} 格、"
        f"已有作物 {z.crops} 格、待浇水 {z.unwatered} 格、离你约 {z.distance} 格"
        for z in zones
    ]


def area_hint_text(zones: list[Zone]) -> str:
    """给 LLM 的"可选方向"文本：只列 zone.name 与中文 label（同样**无坐标**）。"""
    if not zones:
        return "（本次观测里没有可用的田区：不在户外农场，或 tiles[]/tillable[] 都为空）"
    lines = ["可选方向（只报名字即可，坐标由代码算）："]
    lines.extend(f"- {z.name}（{z.label}）" for z in zones)
    return "\n".join(lines)


def choose_zone(zones: list[Zone], *, prefer: str = "nearest") -> Zone | None:
    """确定性选区：LLM 关掉/失败/给不出方向时就靠它。

    prefer:
      * "nearest"       —— 离玩家最近（少走路，省真实时间）；
      * "most_tillable" —— 可锄格最多（一次开出最大片）；
      * "empty"         —— 已有作物最少（优先没被动过的生地）。
    并列时一律按 `name` 字典序取第一个：只依赖输入本身，跑两遍结果一样。
    """
    if not zones:
        return None
    if prefer not in PREFERS:
        raise ValueError(f"prefer 只能是 {PREFERS} 之一，收到 {prefer!r}")
    if prefer == "nearest":
        key = lambda z: (z.distance, z.name)            # noqa: E731
    elif prefer == "most_tillable":
        key = lambda z: (-z.tillable, z.name)           # noqa: E731
    else:
        key = lambda z: (z.crops, z.name)               # noqa: E731
    return min(zones, key=key)


def resolve_zone(name: str, zones: list[Zone]) -> Zone | None:
    """把 LLM 给的具名田区解析成 Zone（大小写不敏感、认常用别名）。

    顺序：先精确命中 id（含省略 `field_` 前缀的 "nw"），再在归一化后的整串里
    找**最长的**已知别名（于是 "anchor: field_nw（西北）" 也能落到 field_nw）。
    长度并列时按 name 字典序取第一个，保证确定性。
    解析不出来一律返回 None —— 调用方会退回 `choose_zone()`，
    这里绝不能抛异常把整轮自动化打断。
    """
    if not zones:
        return None
    key = normalize_hint(name)
    if not key:
        return None
    ordered = sorted(zones, key=lambda z: z.name)
    for z in ordered:
        if key == z.name or key == z.name.removeprefix("field_"):
            return z
    best: tuple[int, Zone] | None = None
    for z in ordered:
        for sp in _spellings(z):
            if sp in key and (best is None or len(sp) > best[0]):
                best = (len(sp), z)
    return best[1] if best else None


# ---------------------------------------------------------------- 作业区落点

def _note_parts(zone: Zone, loc: dict, size: int, cells: list, unknown: int,
                tillable_n: int, blocker_n: int, unwatered_n: int, dropped: int,
                till_list_n: int) -> list[str]:
    """拼 note：先说数据完整性问题，再说裁剪，最后说这一块里有什么。"""
    parts: list[str] = []
    if loc.get("tilesTruncated"):
        parts.append(
            "⚠ 本次观测被截断（location.tilesTruncated=true）：tiles[] 只有 400 格上限，"
            "田区统计与锚点打分只覆盖已返回的格，实际可能还有更多可锄/待清理格——数据不完整"
        )
    elif till_list_n >= TILLABLE_CAP:
        parts.append(f"⚠ tillable[] 已达 {TILLABLE_CAP} 格上限，可能还有没返回的可锄格，统计偏少")
    if dropped > 0:
        parts.append(
            f"锚点贴边：{size}×{size} 里有 {dropped} 格越出本区边界，已按区界裁剪，实际给出 {len(cells)} 格"
        )
    if unknown > 0:
        parts.append(f"其中 {unknown} 格本次观测没返回（执行时逐格再判，能清就清、不能就跳过）")
    if not parts:
        parts.append(f"锚点取{zone.label}内可锄格最集中的一处")
    parts.append(
        f"这一块：可锄 {tillable_n}、待清理 {blocker_n}、待浇水 {unwatered_n}，共 {len(cells)} 格"
    )
    return parts


def plot_in_zone(zone: Zone, obs: dict, *, size: int = 5) -> dict:
    """在**该区内部**选一块紧凑的 size×size 作业区。

    【为什么锚点要由代码挑】LLM 给"哪片田区 + 多大"，代码负责"落在哪个格子"：
    锚点偏好（1）把区内可锄格尽量框进来，（2）其次让本次要处理的格数
    （blockers+tillable+unwatered）最多，（3）还并列就取该区左上角（y 小、x 小）。
    三条都是全序的，所以同一份观测必然给出同一个锚点。

    【只信真实存在的格】打分/分类只用 `tiles[]` ∪ `tillable[]` 里出现过的格；
    返回的 `tiles` 则是"锚点起 size×size 的全部格子"（含观测里没有的），
    因为执行器本来就是逐格再判（能锄就锄、不能就跳过并记账），
    少给格子反而会让它以为边界到了。

    返回 `{"anchor": [x,y] | None, "tiles": [...], "tillable": [...], "blockers": [...],
    "crops": [...], "unwatered": [...], "note": str}`；空区时 anchor=None、各列表为空，
    并在 note 里说明原因（不编造一块假的地出来）。
    """
    if size < 1:
        raise ValueError(f"size 至少为 1，收到 {size!r}")
    loc = _loc(obs)
    tiles = _tile_index(loc.get("tiles"))
    till = _coord_set(loc.get("tillable"))
    known = set(tiles) | till
    x0, y0, x1, y1 = zone.bounds
    empty = {"anchor": None, "tiles": [], "tillable": [], "blockers": [],
             "crops": [], "unwatered": [], "note": ""}

    if x0 > x1 or y0 > y1:
        return {**empty, "note": f"{zone.name} 的 bounds 是空区间（首尾反了），给不出作业区"}
    inside = [c for c in sorted(known) if x0 <= c[0] <= x1 and y0 <= c[1] <= y1]
    if not inside:
        return {**empty, "note": (
            f"{zone.name} 里没有任何已观测到的格（tiles[] 与 tillable[] 都没覆盖本区），"
            "给不出作业区——先走到该区附近再取一次 full 观测"
        )}

    best_key: tuple | None = None
    best_cells: list[tuple[int, int]] = []
    best_t: list[tuple[int, int]] = []
    best_b: list[tuple[int, int]] = []
    best_c: list[tuple[int, int]] = []
    best_u: list[tuple[int, int]] = []
    for ax, ay in inside:
        cells = [(ax + dx, ay + dy) for dy in range(size) for dx in range(size)
                 if x0 <= ax + dx <= x1 and y0 <= ay + dy <= y1]
        t_in: list[tuple[int, int]] = []
        b_in: list[tuple[int, int]] = []
        c_in: list[tuple[int, int]] = []
        u_in: list[tuple[int, int]] = []
        for c in cells:
            tv = tiles.get(c)
            if c in till:                      # tillable = 能锄出耕地的空格，优先按它归类
                t_in.append(c)
            elif tv is not None and tv.get("kind") in BLOCKER_KINDS:
                b_in.append(c)
            if tv is not None and _crop_id(tv) is not None:
                c_in.append(c)
                if not tv.get("watered"):
                    u_in.append(c)
        work = len(b_in) + len(t_in) + len(u_in)
        key = (-len(t_in), -work, ay, ax)      # 可锄最多 → 要干的活最多 → 最靠左上
        if best_key is None or key < best_key:
            best_key, best_cells = key, cells
            best_t, best_b, best_c, best_u = t_in, b_in, c_in, u_in

    unknown = sum(1 for c in best_cells if c not in known)
    note = "；".join(_note_parts(zone, loc, size, best_cells, unknown,
                                 len(best_t), len(best_b), len(best_u),
                                 size * size - len(best_cells), len(loc.get("tillable") or [])))
    return {
        "anchor": [best_cells[0][0], best_cells[0][1]] if best_cells else None,
        "tiles": [[x, y] for x, y in best_cells],
        "tillable": [[x, y] for x, y in best_t],
        "blockers": [[x, y] for x, y in best_b],
        "crops": [[x, y] for x, y in best_c],
        "unwatered": [[x, y] for x, y in best_u],
        "note": note,
    }
