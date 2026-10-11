# -*- coding: utf-8 -*-
"""task-10 B：把 run2 里所有 farm 读数（含 scanSeq/complete/位置）拉成一条时间线。
只读，不写任何生产文件。"""
import json, os, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = r"D:\Deepseek Harness Workspace\星露谷游戏自动化"

def walk_farms(obj, path=""):
    """递归找出所有 'farm' 块（含 crops 键的 dict）。"""
    out = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            p = f"{path}.{k}" if path else k
            if k == "farm" and isinstance(v, dict):
                out.append((p, v))
            out.extend(walk_farms(v, p))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            out.extend(walk_farms(v, f"{path}[{i}]"))
    return out

def brief_place(farm):
    return " ".join(f"{k}={farm.get(k)}" for k in
                    ("loaded", "complete", "scanSeq", "hoeDirt", "crops", "ripeCrops",
                     "unwateredCrops", "weeds", "stones", "twigs", "trees", "grass")
                    if k in farm)

def ctx(d, *keys):
    parts = []
    for k in keys:
        if k in d:
            parts.append(f"{k}={json.dumps(d[k], ensure_ascii=False)}")
    return " ".join(parts)

print("=" * 100)
print("A. logs\\longrun-3day-llm-run2.jsonl 里出现的每个 farm 块")
print("=" * 100)
p = os.path.join(ROOT, "logs", "longrun-3day-llm-run2.jsonl")
for ln, line in enumerate(open(p, encoding="utf-8"), 1):
    line = line.strip()
    if not line:
        continue
    try:
        d = json.loads(line)
    except Exception as e:
        print(f"[{ln}] 解析失败 {e}")
        continue
    farms = walk_farms(d)
    if not farms:
        continue
    head = ctx(d, "event", "t", "day", "timeOfDay", "location")
    if isinstance(d.get("final"), dict):
        head += " " + ctx(d["final"], "timeOfDay", "location", "tile", "isInBed")
    if isinstance(d.get("before"), dict):
        head += " before:" + ctx(d["before"], "timeOfDay", "stamina")
    for path, f in farms:
        print(f"[{ln}] {head}\n      {path}: {brief_place(f)}")

print()
print("=" * 100)
print("B. 三个 observe json 的 farm/时钟/位置")
print("=" * 100)
for name in ("observe-farm-sample.json", "run2-observe-start.json", "run2-observe-end.json"):
    fp = os.path.join(ROOT, "logs", name)
    if not os.path.exists(fp):
        print(f"{name}: 不存在")
        continue
    d = json.load(open(fp, encoding="utf-8"))
    print(f"--- {name} (顶层键: {sorted(d.keys())})")
    print("    " + ctx(d, "schema", "worldSeq", "ok"))
    for key in ("clock", "player", "location", "summary"):
        if key in d and not isinstance(d[key], (dict, list)):
            print(f"    {key}={d[key]}")
    for path, f in walk_farms(d):
        print(f"    {path}: {brief_place(f)}")
    # clock / player / location 详细
    for key in ("clock", "player", "location"):
        v = d.get(key)
        if isinstance(v, dict):
            keep = {k: v[k] for k in v if k in
                    ("day", "season", "year", "timeOfDay", "name", "tile", "tileX", "tileY",
                     "isInBed", "stamina", "money", "isOutdoorFarm", "isFarm", "displayName",
                     "tilesTruncated", "loaded")}
            print(f"    {key}: {json.dumps(keep, ensure_ascii=False)}")
