"""task-156：清障基线取数（只读）。

用法：
  python scratch\\_t156_data.py                 # 全部
  python scratch\\_t156_data.py observe         # 只看 run9c 外部观测
  python scratch\\_t156_data.py ledger          # 只看账本 day_end.final.farm

输出自写 UTF-8 到 scratch\\_t156_data.txt（不用 pwsh 重定向，避免 UTF-16LE）。
"""
import json
import os
import sys
from collections import Counter

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "scratch", "_t156_data.txt")

OBSERVE = [
    "run9c-observe-summer18.json",
    "run9c-observe-summer19.json",
    "run9c-observe-summer19-2.json",
    "run9c-observe-summer21.json",
    "run9c-observe-summer22.json",
    "run9c-observe-summer22-2.json",
]
LEDGERS = [
    "logs/longrun-3day-llm-run7.jsonl",
    "logs/longrun-3day-llm-run8.jsonl",
    "logs/longrun-3day-llm-run9.jsonl",
    "logs/longrun-3day-llm-run9b.jsonl",
    "logs/longrun-3day-llm-run9c.jsonl",
]
FARM_KEYS = ("loaded", "complete", "hoeDirt", "crops", "ripeCrops", "unwateredCrops",
             "grass", "bush", "trees", "stumps", "logs", "boulders", "stones",
             "weeds", "twigs", "machines", "sprinklers", "animals", "scanSeq")


def w(fh, line=""):
    fh.write(str(line) + "\n")


def dump_observe(fh):
    for name in OBSERVE:
        path = os.path.join(ROOT, "scratch", name)
        if not os.path.exists(path):
            w(fh, f"--- {name}: 不存在")
            continue
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
        w(fh, f"=== {name} ({os.path.getsize(path)} B)")
        w(fh, f"  顶层键: {sorted(doc.keys())}")
        w(fh, f"  day_key = {json.dumps(doc.get('day_key'), ensure_ascii=False)}  captured_at = {json.dumps(doc.get('captured_at'), ensure_ascii=False)}")
        if isinstance(doc.get("observe"), dict):
            doc = doc["observe"]
            w(fh, f"  observe 键: {sorted(doc.keys())}")
        for k in ("worldSeq", "seq", "time", "clock", "day", "season", "year", "stamina", "money"):
            if k in doc:
                w(fh, f"  {k} = {json.dumps(doc[k], ensure_ascii=False)[:200]}")
        game = doc.get("game") if isinstance(doc.get("game"), dict) else {}
        if game:
            w(fh, f"  game 键: {sorted(game.keys())}")
            for k in ("day", "season", "year", "timeOfDay", "clock", "money", "stamina", "location"):
                if k in game:
                    w(fh, f"    game.{k} = {json.dumps(game[k], ensure_ascii=False)[:160]}")
        farm = doc.get("farm")
        if isinstance(farm, dict):
            w(fh, f"  farm 键: {sorted(farm.keys())}")
            for k in sorted(farm.keys()):
                if k in FARM_KEYS or not isinstance(farm[k], (dict, list)):
                    w(fh, f"    farm.{k} = {json.dumps(farm[k], ensure_ascii=False)[:160]}")
        loc = doc.get("location")
        if isinstance(loc, dict):
            tiles = loc.get("tiles")
            w(fh, f"  location 键: {sorted(loc.keys())}")
            for k in ("name", "isFarm", "isOutdoorFarm", "timeOfDay", "money"):
                if k in loc:
                    w(fh, f"    location.{k} = {json.dumps(loc[k], ensure_ascii=False)[:160]}")
            if isinstance(tiles, list):
                kinds = Counter(str(t.get("kind") or "") for t in tiles if isinstance(t, dict))
                w(fh, f"    location.tiles: {len(tiles)} 格；kind 直方图 {dict(kinds.most_common())}")
                tools = Counter(str(t.get("tool") or "") for t in tiles if isinstance(t, dict))
                w(fh, f"    其中 tool 直方图 {dict(tools.most_common())}")
                actionable = [t for t in tiles if isinstance(t, dict) and t.get("actionable") is True]
                w(fh, f"    actionable=true 的格: {len(actionable)}")
        else:
            w(fh, f"  location = {json.dumps(loc, ensure_ascii=False)[:200]}")
        w(fh)


def dump_ledger(fh):
    for rel in LEDGERS:
        path = os.path.join(ROOT, rel)
        if not os.path.exists(path):
            w(fh, f"--- {rel}: 不存在")
            continue
        w(fh, f"=== {rel}")
        with open(path, "r", encoding="utf-8") as f:
            for i, raw in enumerate(f, 1):
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    ev = json.loads(raw)
                except Exception as exc:
                    w(fh, f"  L{i}: 解析失败 {exc}")
                    continue
                name = ev.get("event")
                if name == "day_start":
                    w(fh, f"  L{i} day_start day={ev.get('day')} tod={ev.get('timeOfDay')} loc={ev.get('location')} money={ev.get('money')} stamina={ev.get('stamina')}")
                elif name == "day_end":
                    final = ev.get("final") if isinstance(ev.get("final"), dict) else {}
                    farm = final.get("farm") if isinstance(final.get("farm"), dict) else None
                    w(fh, f"  L{i} day_end ended_by={ev.get('ended_by')} verified={ev.get('verified')}")
                    w(fh, f"       final 键: {sorted(final.keys())}")
                    if farm is not None:
                        w(fh, f"       final.farm: {json.dumps(farm, ensure_ascii=False, sort_keys=True)}")
                    else:
                        w(fh, f"       final.farm = {json.dumps(final.get('farm'), ensure_ascii=False)}")
                    w(fh, f"       final.counts_scope={final.get('counts_scope')} crops={final.get('crops')} unwatered={final.get('unwatered_crops')} tillable={final.get('tillable')}")
                elif name == "clear_dead_scope":
                    w(fh, f"  L{i} clear_dead_scope {json.dumps({k: v for k, v in ev.items() if k not in ('event', 't')}, ensure_ascii=False)[:300]}")
        w(fh)


def dump_shape(fh):
    """看 location/farm 里各个列表字段的真实形状（用来判断能不能拿到全农场的分类计数）。"""
    for name in OBSERVE:
        path = os.path.join(ROOT, "scratch", name)
        if not os.path.exists(path):
            continue
        with open(path, "r", encoding="utf-8") as f:
            doc = json.load(f)
        doc = doc.get("observe") if isinstance(doc.get("observe"), dict) else doc
        w(fh, f"=== {name}")
        for holder, key in (("farm", "tiles"), ("location", "tiles"), ("location", "objects"),
                            ("location", "terrainFeatures"), ("location", "debris"),
                            ("location", "furniture"), ("location", "characters"),
                            ("location", "refillTiles"), ("location", "doors"),
                            ("location", "tillable")):
            obj = doc.get(holder) if isinstance(doc.get(holder), dict) else {}
            val = obj.get(key)
            if val is None:
                w(fh, f"  {holder}.{key} = <缺失>")
                continue
            if isinstance(val, list):
                w(fh, f"  {holder}.{key}: list len={len(val)}")
                if val and isinstance(val[0], dict):
                    w(fh, f"      首元素键: {sorted(val[0].keys())}")
                    w(fh, f"      首元素: {json.dumps(val[0], ensure_ascii=False)[:300]}")
                    for fld in ("kind", "feature", "tool", "objId", "index", "parentSheetIndex", "clumpIndex"):
                        hist = Counter(str(x.get(fld)) for x in val if isinstance(x, dict) and fld in x)
                        if hist:
                            w(fh, f"      {fld} 直方图({sum(hist.values())}/{len(val)}): {dict(hist.most_common(12))}")
                else:
                    w(fh, f"      值: {json.dumps(val, ensure_ascii=False)[:200]}")
            elif isinstance(val, dict):
                w(fh, f"  {holder}.{key}: dict 键={sorted(val.keys())}")
            else:
                w(fh, f"  {holder}.{key} = {json.dumps(val, ensure_ascii=False)[:160]}")
        w(fh)


def main():
    what = sys.argv[1] if len(sys.argv) > 1 else "all"
    with open(OUT, "w", encoding="utf-8") as fh:
        if what in ("all", "observe"):
            w(fh, "########## 外部观测（scratch/run9c-observe-*.json） ##########")
            dump_observe(fh)
        if what in ("all", "shape"):
            w(fh, "########## 列表字段形状 ##########")
            dump_shape(fh)
        if what in ("all", "ledger"):
            w(fh, "########## 账本 day_end.final.farm ##########")
            dump_ledger(fh)
    print(f"wrote {OUT} ({os.path.getsize(OUT)} B)")


if __name__ == "__main__":
    main()
