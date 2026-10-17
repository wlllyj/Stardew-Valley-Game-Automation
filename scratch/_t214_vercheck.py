# -*- coding: utf-8 -*-
"""task-214 前置体检：装机 dll 到底有没有 task-213 的内省面？

现象：0.7.37 已装（SMAPI 日志 23:23:19 报 `v0.7.37 已就绪`，插件描述里写着 debug_dump /
add_missed_recipes），但真机 `debug_dump` 回 `unknown_skill`。
本脚本对比「装机 dll」与「仓库 Release 构建产物」的指纹与嵌入字符串，定位是"装的是旧 dll"
还是"新代码没编进 dll"。
只读：只读文件、只调一次 health。
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "brain"))

GAME = Path(os.environ.get("STARDEW_GAME_PATH") or r"D:\Program Files (x86)\Steam\steamapps\common\Stardew Valley")
DEPLOYED = GAME / "Mods" / "AgentFarm.Bridge"
BUILD = REPO / "mod" / "AgentFarm.Bridge" / "bin" / "Release"

PROBES = [b"debug_dump", b"add_missed_recipes", b"DebugDumpSkill", b"AddMissedRecipesSkill",
          b"DebugDumpArgs", b"AddMissedRecipesResponse", b"upgrade_tool", b"readyTiles", b"0.7.37",
          b"0.7.39", b"crafting_recipes", b"trigger_actions"]


def stat(path: Path) -> dict:
    if not path.exists():
        return {"path": str(path), "exists": False}
    b = path.read_bytes()
    return {"path": str(path), "exists": True, "size": len(b),
            "mtime": __import__("datetime").datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="milliseconds"),
            "sha256": hashlib.sha256(b).hexdigest()}


def scan(path: Path) -> dict:
    if not path.exists():
        return {}
    raw = path.read_bytes()
    return {p.decode(): (p in raw) for p in PROBES}


def main() -> int:
    out = {"deployed_dir": str(DEPLOYED), "build_dir": str(BUILD)}
    for label, d in (("deployed", DEPLOYED), ("build", BUILD)):
        out[f"{label}_dll"] = stat(d / "AgentFarm.Bridge.dll")
        out[f"{label}_manifest"] = stat(d / "manifest.json")
        out[f"{label}_strings"] = scan(d / "AgentFarm.Bridge.dll")
    mf = DEPLOYED / "manifest.json"
    if mf.exists():
        try:
            out["deployed_manifest_version"] = json.loads(mf.read_text(encoding="utf-8-sig")).get("Version")
        except Exception as exc:  # noqa: BLE001
            out["deployed_manifest_version_error"] = f"{type(exc).__name__}: {exc}"
    mfb = BUILD / "manifest.json"
    if mfb.exists():
        try:
            out["build_manifest_version"] = json.loads(mfb.read_text(encoding="utf-8-sig")).get("Version")
        except Exception as exc:  # noqa: BLE001
            out["build_manifest_version_error"] = f"{type(exc).__name__}: {exc}"
    try:
        from agentfarm.bridge import BridgeClient
        h = BridgeClient().health()
        out["health"] = {k: h.get(k) for k in ("ok", "status", "modVersion", "runtime")}
    except Exception as exc:  # noqa: BLE001
        out["health"] = f"{type(exc).__name__}: {exc}"

    print(f"装机目录 = {DEPLOYED}  (exists={DEPLOYED.exists()})")
    print(f"构建目录 = {BUILD}")
    for label in ("deployed", "build"):
        d, m = out[f"{label}_dll"], out[f"{label}_manifest"]
        print(f"\n[{label}] dll      : exists={d.get('exists')} size={d.get('size')} mtime={d.get('mtime')}")
        print(f"[{label}] dll sha  : {d.get('sha256')}")
        print(f"[{label}] manifest : size={m.get('size')} mtime={m.get('mtime')} version={out.get(label + '_manifest_version')}")
    print(f"\n字符串探针：")
    keys = [p.decode() for p in PROBES]
    print(f"  {'probe':24} {'deployed':>10} {'build':>10}")
    for k in keys:
        print(f"  {k:24} {str(out['deployed_strings'].get(k)):>10} {str(out['build_strings'].get(k)):>10}")
    print(f"\nhealth = {json.dumps(out['health'], ensure_ascii=False)[:400]}")
    p = REPO / "logs" / "run10e-dll-vercheck.json"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n已写出 {p}（{p.stat().st_size} B）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
