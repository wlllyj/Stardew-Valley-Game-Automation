# -*- coding: utf-8 -*-
"""task-10 B: dump farm block + location/clock/player keys from arbitrary observe-like json files.
Read-only. Usage: python scratch\_farm_dump.py <file> [<file> ...]"""
import json, os, sys, io

sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
ROOT = r"D:\Deepseek Harness Workspace\星露谷游戏自动化"

FARM_KEYS = ("loaded", "complete", "scanSeq", "hoeDirt", "emptyDirt", "crops", "ripeCrops",
             "unwateredCrops", "weeds", "stones", "twigs", "trees", "grass", "sprinklers",
             "machinesTotal", "machinesReady", "animals", "tiles")


def walk_farms(obj, path=""):
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


def brief(d):
    return " ".join(f"{k}={d[k]!r}" for k in FARM_KEYS if k in d)


for arg in sys.argv[1:]:
    fp = arg if os.path.isabs(arg) else os.path.join(ROOT, arg)
    print("=" * 90)
    print(fp)
    if not os.path.exists(fp):
        print("  MISSING")
        continue
    try:
        d = json.load(open(fp, encoding="utf-8"))
    except Exception as e:
        print(f"  parse failed: {e}")
        continue
    if isinstance(d, dict):
        print("  toplevel keys:", sorted(d.keys()))
        for k in ("schema", "ok", "worldSeq", "generatedAt", "event", "t", "reason", "notes"):
            if k in d:
                print(f"  {k} = {json.dumps(d[k], ensure_ascii=False)[:300]}")
        for k in ("clock", "player", "location", "summary", "final", "before", "after", "checks"):
            v = d.get(k)
            if isinstance(v, dict):
                keep = {kk: v[kk] for kk in v if kk in
                        ("day", "season", "year", "timeOfDay", "name", "displayName", "tile",
                         "isInBed", "stamina", "money", "isOutdoorFarm", "isFarm",
                         "tilesTruncated", "tileCount", "crops", "unwatered_crops", "tillable",
                         "location", "unwatered", "dirt")}
                print(f"  {k}: {json.dumps(keep, ensure_ascii=False)}")
    for path, f in walk_farms(d):
        print(f"  {path}: {brief(f)}")
        if "tiles" in f and isinstance(f["tiles"], list):
            print(f"      tiles len = {len(f['tiles'])}")
