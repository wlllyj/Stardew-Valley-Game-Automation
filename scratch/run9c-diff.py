# -*- coding: utf-8 -*-
"""run9c 逐日世界差分表（只读，Lead m01912 硬要求）。

输入 = `scratch\\run9c-observe-<day_key>[-n].json`（由 `scratch\\run9c-observe.py` 抓的独立观测）
     + `logs\\longrun-3day-llm-run9c.jsonl`（账本，只作旁证/对照）
输出 = `logs\\run9c-diff.txt`（markdown）+ stdout。

核心口径（Lead m01912）：**判据 = observe?detail=full 差分，不信回执**；
只有账本自述、没有独立观测差分的天**不算世界差分证据**。

用法
----
    python scratch\\run9c-diff.py --journal logs\\longrun-3day-llm-run9c.jsonl \
        [--dir scratch] [--prefix run9c-observe-] [--smapi logs\\run9c-smapi-window.txt] [--out logs\\run9c-diff.txt]
"""
from __future__ import annotations

import argparse
import glob
import io
import json
import os
import re
import sys
import time

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))
DEFAULT_JOURNAL = os.path.join(ROOT, "logs", "longrun-3day-llm-run9c.jsonl")
DEFAULT_DIR = os.path.join(ROOT, "scratch")
DEFAULT_PREFIX = "run9c-observe-"
DEFAULT_OUT = os.path.join(ROOT, "logs", "run9c-diff.txt")

KEY_RE = re.compile(r"^(?P<season>[a-z]+)(?P<day>\d+)", re.I)
CROP_KEYS = ("crop", "crops", "cropId", "cropName", "crop_id", "harvestId")
FARM_COUNTERS = ("crops", "unwateredCrops", "dryCrops", "deadCrops", "dryDeadCrops", "ripeCrops",
                 "hoeDirt", "emptyDirt", "weeds", "stones", "twigs", "trees", "grass")


def now_iso() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def coord(t):
    v = t.get("tile")
    if isinstance(v, list) and len(v) >= 2:
        return (int(v[0]), int(v[1]))
    if isinstance(v, str) and "," in v:
        a, b = v.split(",")[:2]
        return (int(a), int(b))
    if "x" in t and "y" in t:
        return (int(t["x"]), int(t["y"]))
    return None


SEASON_ORDER = {"spring": 0, "summer": 1, "fall": 2, "winter": 3}


def day_sort_key(day_key: str):
    m = KEY_RE.match(day_key)
    if not m:
        return (9, 99)
    return (SEASON_ORDER.get(m.group("season").lower(), 9), int(m.group("day")))


def crop_marks(t) -> bool:
    for k in CROP_KEYS:
        if k in t and t.get(k) not in (None, "", 0, False, "-1", []):
            return True
    return False


def load_captures(d: str, prefix: str):
    out = []
    for p in sorted(glob.glob(os.path.join(d, f"{prefix}*.json"))):
        name = os.path.basename(p)
        rest = name[len(prefix):]
        m = KEY_RE.match(rest)
        if not m:
            continue
        try:
            with io.open(p, encoding="utf-8") as fh:
                payload = json.load(fh)
        except Exception as exc:  # noqa: BLE001
            print(f"[warn] {name} 读取失败：{type(exc).__name__}: {exc}", file=sys.stderr)
            continue
        obs = payload.get("observe")
        if obs is None:
            # 兼容"裸 observe 原文"（直接就是 observe 字典）
            obs = payload if isinstance(payload, dict) and ("clock" in payload or "player" in payload) else {}
        at = payload.get("captured_at") or obs.get("generatedAt") or ""
        out.append({
            "path": p,
            "name": name,
            "day_key": f"{m.group('season').lower()}{int(m.group('day'))}",
            "at": at,
            "obs": obs,
            "payload": payload,
        })
    return out


def tile_map(obs):
    loc = (obs.get("location") or {})
    tiles = loc.get("tiles") or []
    m = {}
    for t in tiles:
        c = coord(t)
        if c is not None:
            m[c] = t
    return m, len(tiles), bool(loc.get("tilesTruncated")), loc.get("name"), bool(loc.get("isFarm"))


def crop_coords(obs):
    loc = (obs.get("location") or {})
    farm = (obs.get("farm") or {})
    coords = set()
    any_field = False
    for src in (loc.get("tiles") or [], farm.get("tiles") or []):
        for t in src:
            for k in CROP_KEYS:
                if k in t:
                    any_field = True
            if crop_marks(t):
                c = coord(t)
                if c is not None:
                    coords.add(c)
    return coords, any_field


def seeds(obs):
    inv = ((obs.get("player") or {}).get("inventory") or [])
    out = {}
    for it in inv:
        nm = str(it.get("name") or "")
        if "seed" in nm.lower():
            key = it.get("qualifiedId") or it.get("id") or nm
            out[key] = int(it.get("stack") or 0)
    return out


def day_end_for(journal: str):
    """返回 {day_key: day_end 记录}（账本旁证）。"""
    res = {}
    if not os.path.exists(journal):
        return res
    with io.open(journal, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line:
                continue
            try:
                rec = json.loads(line)
            except Exception:  # noqa: BLE001
                continue
            if rec.get("event") != "day_end":
                continue
            d = rec.get("day")
            if isinstance(d, list) and len(d) == 3:
                res[f"{str(d[1]).lower()}{int(d[2])}"] = rec
    return res


SMAPI_PREFIX_RE = re.compile(r"^\[\d\d:\d\d:\d\d\s+(?:TRACE|DEBUG|INFO|WARN|ERROR)\s+(?:game|SMAPI)\]\s")
DESC_MARKS = (" by AgentFarm ", "| v0.")


def smapi_real(line: str):
    """判定一行是不是真日志行；返回 (是否算真, 不算的原因)。"""
    if not SMAPI_PREFIX_RE.match(line):
        return False, "无 `[HH:MM:SS LEVEL CHANNEL]` 前缀"
    for mk in DESC_MARKS:
        if mk in line:
            return False, f"插件描述行（含 {mk!r}）"
    return True, ""


def smapi_counts(path: str):
    """原始计数 vs 修正计数。

    修正规则（run9b 实证）：插件描述行（`[HH:MM:SS INFO  SMAPI]   AgentFarm Bridge 0.7.29 by AgentFarm | v0.7.29
    （…改动日志里写着 "SaveGame.Save() called."…）`）会被字符串匹配命中，
    必须用「有日志前缀 + 不是插件描述行」两条一起过滤（**只判前缀不够**：描述行本身也有前缀）。
    """
    pats = {
        "NewDay": "Synchronizing 'NewDay' task",
        "before_save": "Context: before save.",
        "save_called": "SaveGame.Save() called.",
        "no_compression": "Saving without compression",
        "completed": "completed without exceptions",
    }
    raw = {k: 0 for k in pats}
    fixed = {k: 0 for k in pats}
    fake_lines = []
    if not os.path.exists(path):
        return None
    with io.open(path, encoding="utf-8", errors="replace") as fh:
        for i, line in enumerate(fh, 1):
            hits = [k for k, s in pats.items() if s in line]
            if not hits:
                continue
            real, why = smapi_real(line)
            for k in hits:
                raw[k] += 1
                if real:
                    fixed[k] += 1
            if not real:
                fake_lines.append((i, "/".join(hits), why, line.strip()[:150]))
    return raw, fixed, fake_lines


def kv_diff(a: dict, b: dict, keys):
    return [(k, a.get(k), b.get(k)) for k in keys if a.get(k) != b.get(k)]


def fmt_pair(x, y):
    return f"{x} → {y}" if x != y else f"{x}（不变）"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--journal", default=DEFAULT_JOURNAL)
    ap.add_argument("--dir", default=DEFAULT_DIR)
    ap.add_argument("--prefix", default=DEFAULT_PREFIX)
    ap.add_argument("--smapi", default=None)
    ap.add_argument("--out", default=DEFAULT_OUT)
    args = ap.parse_args()

    caps = load_captures(args.dir, args.prefix)
    ends = day_end_for(args.journal)
    L = []
    L.append(f"# run9c 逐日世界差分（判据 = observe?detail=full 差分，不信回执）")
    L.append("")
    L.append(f"- 生成时刻：`{now_iso()}`；输入目录：`{os.path.relpath(args.dir, ROOT)}\\{args.prefix}*`（{len(caps)} 份观测）")
    L.append(f"- 账本（旁证）：`{os.path.relpath(args.journal, ROOT)}`；`day_end` 记录 {len(ends)} 条")
    L.append("- 端点口径：每个游戏日 = **当日最早一份观测 → 当日最晚一份观测**；另给「两次都在 Farm 上」的端点对（tile 差分只在 Farm 端点对之间做，窗口是玩家中心的 400 格）。")
    L.append("- ⚠ 只有账本自述、没有独立观测的天**不算世界差分证据**（本表会写「缺观测」）。")
    L.append("")

    by_day = {}
    for c in caps:
        by_day.setdefault(c["day_key"], []).append(c)
    for k in by_day:
        by_day[k].sort(key=lambda c: c["at"])

    if not caps:
        L.append("**没有任何观测文件 ⇒ 无法产出世界差分表**（先跑 `scratch\\run9c-observe.py`）。")

    L.append("## 逐日差分表")
    L.append("")
    L.append("| 游戏日 | 观测数 | 起→止（文件名·时刻） | location | tiles(截断) | kind 迁移数 | farm 计数变化 | player | 种子叠 | 新增 crop 格 | 账本旁证 |")
    L.append("|---|---|---|---|---|---|---|---|---|---|---|")
    details = []
    undecided = []
    for k in sorted(by_day, key=day_sort_key):
        g = by_day[k]
        A, B = g[0], g[-1]
        ma, na, ta, la, fa = tile_map(A["obs"])
        mb, nb, tb, lb, fb = tile_map(B["obs"])
        common = set(ma) & set(mb)
        trans = []
        for c in sorted(common):
            ka, kb = ma[c].get("kind"), mb[c].get("kind")
            if ka != kb:
                trans.append((c, ka, kb))
        tcount = {}
        for c, ka, kb in trans:
            tcount[(ka, kb)] = tcount.get((ka, kb), 0) + 1
        appeared = len(set(mb) - set(ma))
        gone = len(set(ma) - set(mb))
        kind_txt = "；".join(f"{a}→{b}×{n}" for (a, b), n in sorted(tcount.items(), key=lambda x: -x[1])) or "无同格 kind 变化"
        if trans:
            samples = "；".join(f"({c[0]},{c[1]}) {a}→{b}" for c, a, b in trans[:3])
            kind_txt += f"｜例：{samples}"
        kind_txt += f"｜窗口新增/消失（不可区分世界变化或窗口位移）：+{appeared}/-{gone}"

        fa_c = (A["obs"].get("farm") or {})
        fb_c = (B["obs"].get("farm") or {})
        fdiff = "；".join(f"{kk} {fmt_pair(a, b)}" for kk, a, b in kv_diff(fa_c, fb_c, FARM_COUNTERS)) or "无变化"
        pa = (A["obs"].get("player") or {})
        pb = (B["obs"].get("player") or {})
        p_txt = f"体力 {fmt_pair(pa.get('stamina'), pb.get('stamina'))}；钱 {fmt_pair(pa.get('money'), pb.get('money'))}"
        sa, sb = seeds(A["obs"]), seeds(B["obs"])
        seed_keys = sorted(set(sa) | set(sb))
        seed_txt = "；".join(f"{kk}: {sa.get(kk, 0)}→{sb.get(kk, 0)}" for kk in seed_keys) or "（无种子叠）"
        ca, fa_field = crop_coords(A["obs"])
        cb, _ = crop_coords(B["obs"])
        if not (fa_field):
            crop_txt = "【无法判定】观测 schema 无 crop 字段"
            undecided.append(f"{k}：⑤ 新增 crop 格 —— 两份观测的 `tiles[]` 都没有 crop 类字段")
        else:
            new = sorted(cb - ca)
            crop_txt = f"新增 {len(new)} 格" + ("：" + "；".join(f"({x},{y})" for x, y in new[:5]) if new else "")
        end = ends.get(k)
        end_txt = "缺" if not end else f"{end.get('ended_by')}/verified={end.get('verified')}/dry={((end.get('final_water') or {}).get('dry'))}"
        L.append(f"| {k} | {len(g)} | {A['name']}@{A['at']} → {B['name']}@{B['at']} | {la}→{lb} | "
                 f"{na}/{nb}({ta}/{tb}) | {kind_txt} | {fdiff} | {p_txt} | {seed_txt} | {crop_txt} | {end_txt} |")

        # 明细
        det = [f"### {k}", ""]
        det.append(f"- 端点 A：`{A['name']}`（{A['at']}，`{A['obs'].get('worldSeq')}`）")
        det.append(f"- 端点 B：`{B['name']}`（{B['at']}，`{B['obs'].get('worldSeq')}`）")
        det.append(f"- ① `location.tiles[]` kind 迁移：{kind_txt}")
        for kk, a, b in kv_diff(fa_c, fb_c, FARM_COUNTERS):
            det.append(f"- ② `farm.{kk}`：**{a} → {b}**")
        if not kv_diff(fa_c, fb_c, FARM_COUNTERS):
            det.append("- ② `farm.*` 计数：无变化")
        det.append(f"- ③ `player.stamina`：{pa.get('stamina')} → {pb.get('stamina')}；`player.money`：{pa.get('money')} → {pb.get('money')}")
        det.append(f"- ④ 种子叠：{seed_txt}")
        det.append(f"- ⑤ 新增 crop 格：{crop_txt}")
        if end:
            fin = end.get("final") or {}
            money_now = pb.get("money")
            det.append(f"- ⑥ 账本旁证 `day_end.final`：money={fin.get('money')} seeds={fin.get('seeds')} crops={fin.get('crops')} "
                       f"unwatered={fin.get('unwatered_crops')}｜现场 B：money={money_now}")
            if fin.get("money") is not None and money_now is not None and fin.get("money") != money_now:
                det.append(f"  - ⚠ **`final` 与现场不一致（task-137）⇒ 以现场观测为准**（`final` 在非 `sleep` 收尾分支上可能滞后）")
            det.append(f"- ⑥ 收尾：`ended_by={end.get('ended_by')}`、`verified={end.get('verified')}`、"
                       f"`day_after={end.get('day_after')}`、`final_water={json.dumps(end.get('final_water'), ensure_ascii=False)}`")
        else:
            det.append("- ⑥ 账本旁证：**该日没有 `day_end` 记录**（当日未收尾或账本缺失）")
        details.append("\n".join(det))

    # Farm 端点对
    L.append("")
    L.append("## Farm 端点对（tile 差分的有效口径）")
    L.append("")
    L.append("| 游戏日 | Farm 观测数 | 端点 | 同格 kind 迁移 | 例 |")
    L.append("|---|---|---|---|---|")
    for k in sorted(by_day, key=day_sort_key):
        farm_caps = [c for c in by_day[k] if ((c["obs"].get("location") or {}).get("isFarm"))]
        if len(farm_caps) < 2:
            L.append(f"| {k} | {len(farm_caps)} | — | 【无法判定】当日 Farm 端点不足 2 份 | — |")
            undecided.append(f"{k}：① tile kind 迁移 —— 当日只有 {len(farm_caps)} 份 Farm 观测（需要 ≥2）")
            continue
        A, B = farm_caps[0], farm_caps[-1]
        ma = tile_map(A["obs"])[0]
        mb = tile_map(B["obs"])[0]
        trans = [(c, ma[c].get("kind"), mb[c].get("kind")) for c in sorted(set(ma) & set(mb)) if ma[c].get("kind") != mb[c].get("kind")]
        cnt = {}
        for _, a, b in trans:
            cnt[(a, b)] = cnt.get((a, b), 0) + 1
        txt = "；".join(f"{a}→{b}×{n}" for (a, b), n in sorted(cnt.items(), key=lambda x: -x[1])) or "无"
        ex = "；".join(f"({c[0]},{c[1]}) {a}→{b}" for c, a, b in trans[:3]) or "—"
        L.append(f"| {k} | {len(farm_caps)} | {A['name']}@{A['at']} → {B['name']}@{B['at']} | {txt} | {ex} |")

    # save_called 修正
    L.append("")
    L.append("## `save_called` 的原始计数 vs 修正计数")
    L.append("")
    if args.smapi:
        r = smapi_counts(args.smapi)
        if r is None:
            L.append(f"- `{args.smapi}` 不存在 ⇒ 【无法判定】")
        else:
            raw, fixed, fake = r
            L.append(f"- 窗口：`{os.path.relpath(args.smapi, ROOT)}`")
            L.append(f"- 原始计数：NewDay **{raw['NewDay']}** / before save **{raw['before_save']}** / "
                     f"Save called **{raw['save_called']}** / no compression **{raw['no_compression']}** / completed **{raw['completed']}**")
            L.append(f"- 修正计数（**有日志前缀 且 不是插件描述行**）：NewDay **{fixed['NewDay']}** / before save **{fixed['before_save']}** / "
                     f"Save called **{fixed['save_called']}** / no compression **{fixed['no_compression']}** / completed **{fixed['completed']}**")
            if fake:
                L.append(f"- 差异原因：{len(fake)} 行被字符串匹配但**不是真日志行**：")
                for ln, keys, why, txt in fake[:10]:
                    L.append(f"  - L{ln}（命中 {keys}，{why}）：`{txt}`")
            else:
                L.append("- 差异原因：无（原始 = 修正）")
    else:
        L.append("- 未传 `--smapi` ⇒ 【无法判定】（建议传 `logs\\run9c-smapi-window.txt`）")

    # 明细与无法判定
    L.append("")
    L.append("## 逐日明细")
    L.append("")
    L.extend(details)
    L.append("")
    L.append("## 【无法判定】清单（缺失 ≠ 通过）")
    L.append("")
    if undecided:
        for u in undecided:
            L.append(f"- {u}")
    else:
        L.append("- 无")
    L.append("")
    L.append("## 保留物")
    L.append("")
    for c in sorted(caps, key=lambda c: c["at"]):
        L.append(f"- `{os.path.relpath(c['path'], ROOT)}`（{os.path.getsize(c['path'])} B，{c['at']}，day_key={c['day_key']}）")

    text = "\n".join(L) + "\n"
    with io.open(args.out, "w", encoding="utf-8") as fh:
        fh.write(text)
    print(text)
    print(f"[written] {args.out}（{len(text)} 字符）", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
